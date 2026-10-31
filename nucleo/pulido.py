"""9.5: el resumen de la mañana como nota de voz, tu estilo al escribir y la retroalimentación de textos de estudiantes.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import os
import re
import threading

import aula
import compromisos
import estilo
import horario
import seguimiento
from nucleo import J


# ============================================================================ RESUMEN DE LA MAÑANA EN NOTA DE VOZ
def morning_brief_text(now=None):
    """El resumen para escuchar: fecha, clima, clases, agenda, compromisos y lo que necesita tu atención."""
    now = now or datetime.datetime.now()
    name = J.settings["address_name"].strip()
    parts = [f"Buenos días{', ' + name if name else ''}. Hoy es {J.fecha_hablada(now.date())}."]
    if J.settings["weather_city"].strip() and not J.is_offline():
        try:
            w = J.weather_text()
            if not w.lower().startswith(("no ", "ahora no", "para darte")):
                parts.append(w)
        except Exception:
            pass
    clases = horario.today(now)
    if clases:
        parts.append(horario.spoken_day(clases, "hoy"))
    try:
        lines = J.agenda("hoy")
        if lines:
            parts.append("En tu agenda: " + "; ".join(lines[:6]) + ".")
    except Exception:
        pass
    hoy = [x for x in compromisos.pending() if compromisos.status(x, now.date()) in ("hoy", "vencido")]
    if hoy:
        parts.append("Compromisos para hoy: " + "; ".join(x["texto"] for x in hoy[:4]) + ".")
    try:
        items = [x for x in J.attention_items(now) if x["p"] == 1 and not x["k"].startswith("co:")]
        if items:
            parts.append("También necesita tu atención: " + "; ".join(x["t"] for x in items[:4]) + ".")
    except Exception:
        pass
    parts.append("¡Que tengas un excelente día!")
    return " ".join(parts)


def send_morning_voice():
    """Manda el resumen a Telegram: el texto y la nota de voz. True si salió."""
    if not J.telegram_ready():
        return False
    text = J.morning_brief_text()
    J.telegram_send("☀️ " + text)
    return bool(J.tg_send_voice(text))


_MV_RE = re.compile(r"\b(?:mandame|enviame|pasame|dame)\b.*\b(?:resumen|reporte)\b.*\b(?:manana|del dia|de hoy)\b.*\b(?:audio|nota de voz|voz)\b|"
                    r"\b(?:resumen|reporte) (?:de la manana|matutino) en (?:audio|nota de voz)\b")


def morning_voice(text, t):
    if not _MV_RE.search(t):
        return False
    if not J.telegram_ready():
        J.reply("Para mandarte el resumen en audio necesito Telegram conectado (Ajustes › Integraciones). Te lo digo aquí: " +
                J.morning_brief_text(), "RESUMEN")
        return True
    J.start_job("Preparando el resumen en audio", lambda: J.notify("Te mandé el resumen de la mañana en audio a Telegram." if J.send_morning_voice()
                                                                   else "Te mandé el resumen por Telegram (el audio no salió).", "RESUMEN"), "resumen-voz")
    return True


# ============================================================================ TU ESTILO AL ESCRIBIR
def learn_style(texto, tipo="correo"):
    """Guarda un texto que enviaste o aprobaste; con varios, la IA resume tu estilo (en segundo plano)."""
    if not J.settings["style_learn"]:
        return
    if estilo.add_example(texto, tipo) and J.state.get("ai") == "ok":
        def work():
            try:
                estilo.set_profile(J.ai_chat([{"role": "user", "content": estilo.profile_prompt()}], max_tokens=400))
                J.log_terminal("Actualicé tu estilo de escritura.", "ESTILO")
            except Exception as e:
                J.note_error("ESTILO", e)
        threading.Thread(target=work, daemon=True, name="estilo").start()


@J.socketio.on("style_info")
def handle_style_info(data=None):
    if (data or {}).get("forget"):
        estilo.clear()
    return {"perfil": estilo.data["perfil"], "n": len(estilo.data["ejemplos"])}


def style_ctx():
    return estilo.context() if J.settings["style_learn"] else ""


_ST_LEARN = re.compile(r"^(?:aprende|copia|imita)\s+mi\s+(?:estilo|forma de escribir)(?:\s+(?:con|de))?\s+(?:este|estos)\s+(?:texto|correo|mensaje|"
                       r"textos|correos)s?\s*:?\s*(.*)$")
_ST_SHOW = re.compile(r"\bcomo escribo\b|\bcual es mi estilo\b|\bque sabes de mi (?:estilo|forma de escribir)\b")
_ST_FORGET = re.compile(r"\b(?:olvida|borra)\s+mi\s+(?:estilo|forma de escribir)\b")


def style_voice(text, t):
    if _ST_FORGET.search(t):
        estilo.clear()
        J.reply("Listo, olvidé tu estilo de escritura y los ejemplos que tenía.", "ESTILO")
        return True
    if _ST_SHOW.search(t):
        if estilo.data["perfil"]:
            J.reply("Así escribes, según lo que has enviado conmigo: " + estilo.data["perfil"], "ESTILO")
        else:
            n = len(estilo.data["ejemplos"])
            J.reply(f"Aún estoy aprendiendo: tengo {n} texto{'s' if n != 1 else ''} tuyo{'s' if n != 1 else ''} (necesito 3). "
                    "También puedes decirme «aprende mi estilo con este texto: …».", "ESTILO")
        return True
    m = _ST_LEARN.match(t)
    if m:
        body = re.split(r":\s*", text, maxsplit=1)
        body = body[1].strip() if len(body) == 2 else ""
        if len(body) < 60:
            J.reply("Pégame el texto después de los dos puntos: «aprende mi estilo con este texto: …».", "ESTILO")
            return True
        prev = estilo.data["perfil"]
        J.learn_style(body, "ejemplo")
        n = len(estilo.data["ejemplos"])
        J.reply(f"Gracias, ya tengo {n} texto{'s' if n != 1 else ''} tuyo{'s' if n != 1 else ''}." +
                ("" if prev or n >= 3 else f" Con {3 - n} más entiendo tu estilo."), "ESTILO")
        return True
    return False


# ============================================================================ RETROALIMENTACIÓN DE TEXTOS
_TFB_RE = re.compile(r"^(?:retroalimenta|revisa|corrige|califica|evalua|da(?:me)? retroalimentacion (?:de|a|sobre))\s+(?:este|el|esta|la)\s+"
                    r"(?:texto|escrito|ensayo|redaccion|cuento|parrafo|composicion|resumen)\b(.*)$")


def text_fb_prompt(texto, estudiante="", grado="", rubrica=""):
    return ("Eres un docente de lenguaje en Colombia. Da retroalimentación a este texto de un estudiante: amable, concreta y útil "
            "para que mejore. " + (f"Grado: {grado}. " if grado else "") + (f"Rúbrica o criterios: {rubrica[:1500]}. " if rubrica else "")
            + "Señala fortalezas, aspectos por mejorar (estructura, coherencia, argumentos, vocabulario), los errores de ortografía y "
              "gramática más importantes con su corrección (máximo 8) y una nota sugerida de 1.0 a 5.0 (3.0 aprueba). No reescribas "
              "todo el texto.\n\nTexto" + (f" de {estudiante}" if estudiante else "") + f":\n«{texto[:8000]}»\n\n"
              'Devuelve SOLO JSON: {"fortalezas": [str], "mejorar": [str], "errores": [{"dice": str, "debe_decir": str}], '
              '"nota": 3.8, "comentario": str}')


def text_fb_validate(d):
    if not isinstance(d, dict):
        raise ValueError("respuesta no válida")
    try:
        nota = round(float(str(d.get("nota", "")).replace(",", ".")), 1)
    except ValueError:
        nota = None
    if nota is not None and not 1.0 <= nota <= 5.0:
        nota = None
    out = {"fortalezas": [str(x)[:300] for x in (d.get("fortalezas") or []) if str(x).strip()][:6],
           "mejorar": [str(x)[:300] for x in (d.get("mejorar") or []) if str(x).strip()][:6],
           "errores": [{"dice": str(e.get("dice", ""))[:200], "debe_decir": str(e.get("debe_decir", ""))[:200]}
                       for e in (d.get("errores") or []) if isinstance(e, dict) and str(e.get("dice", "")).strip()][:8],
           "nota": nota, "comentario": str(d.get("comentario", "")).strip()[:900]}
    if not (out["fortalezas"] or out["mejorar"] or out["comentario"]):
        raise ValueError("la IA no devolvió retroalimentación")
    return out


def _text_fb_docx(fb, texto, estudiante, curso):
    folder = os.path.join(J.settings["output_dir"], "Retroalimentación")
    os.makedirs(folder, exist_ok=True)
    name = aula.safe_filename(f"Texto de {estudiante or 'estudiante'}{' ' + curso if curso else ''}")
    path = os.path.join(folder, f"{name} {datetime.datetime.now():%Y-%m-%d %H%M}.docx")
    doc = J.Document()
    doc.add_heading(f"Retroalimentación · {estudiante or 'Texto del estudiante'}", 1)
    if fb["nota"] is not None:
        doc.add_paragraph(f"Nota sugerida: {str(fb['nota']).replace('.', ',')}" + (f"   ·   {curso}" if curso else ""))
    for title, key in (("Fortalezas", "fortalezas"), ("Para mejorar", "mejorar")):
        if fb[key]:
            doc.add_heading(title, 2)
            for x in fb[key]:
                doc.add_paragraph(x, style="List Bullet")
    if fb["errores"]:
        doc.add_heading("Ortografía y gramática", 2)
        tb = doc.add_table(rows=1, cols=2)
        tb.style = "Table Grid"
        tb.rows[0].cells[0].paragraphs[0].add_run("Dice").bold = True
        tb.rows[0].cells[1].paragraphs[0].add_run("Debe decir").bold = True
        for e in fb["errores"]:
            row = tb.add_row().cells
            row[0].text, row[1].text = e["dice"], e["debe_decir"]
    if fb["comentario"]:
        doc.add_heading("Comentario para el estudiante", 2)
        doc.add_paragraph(fb["comentario"])
    doc.add_heading("Texto revisado", 2)
    doc.add_paragraph(texto[:8000])
    doc.save(path)
    return path


def text_feedback_voice(text, t):
    m = _TFB_RE.match(t)
    if not m:
        return False
    parts = re.split(r":\s*", text, maxsplit=1)
    texto = parts[1].strip() if len(parts) == 2 else ""
    if len(texto) < 80:
        J.reply("Pégame el texto después de los dos puntos, por ejemplo: «retroalimenta este texto de Juan de 7A: …».", "RETROALIMENTACIÓN")
        return True
    head = J.normalize(parts[0])
    who = re.search(r"\bde\s+(.+?)(?:\s+(?:de|del)\s+((?:\d{1,2}\s?[a-z]?|sexto|septimo|octavo|noveno|decimo|once)(?:\s+[a-z])?))?(?:\s+con\s+la\s+rubrica.*)?$",
                    head.split("texto", 1)[-1] if "texto" in head else head)
    estudiante, curso = "", ""
    if who and who.group(1).strip() not in ("un estudiante", "una estudiante", "mi estudiante"):
        course, name, _ = J._split_student(who.group(1).strip() + (f" de {who.group(2)}" if who.group(2) else ""))
        estudiante, curso = (name or who.group(1).strip().title()), (course or "")
    rub = re.search(r"\bcon la rubrica\s*:?\s*(.+)$", parts[0], re.I)
    if J.state.get("ai") != "ok":
        J.reply("Para revisar textos necesito la IA conectada (Ajustes › IA).", "RETROALIMENTACIÓN")
        return True
    J.reply("Leo el texto y preparo la retroalimentación…", "RETROALIMENTACIÓN")
    capture = getattr(J._tl, "capture", None)

    def work():
        try:
            raw = J.ai_chat([{"role": "user", "content": text_fb_prompt(texto, estudiante, curso, rub.group(1) if rub else "")
                              + J.lessons_ctx()}], json_mode=True, max_tokens=2500)
            fb = text_fb_validate(J._extract_json(raw))
        except J.AIError as e:
            J.notify(J.ai_error_reply(e), "RETROALIMENTACIÓN")
            return
        except (ValueError, TypeError) as e:
            J.notify(f"No pude revisarlo: {e}", "RETROALIMENTACIÓN")
            return
        path = _text_fb_docx(fb, texto, estudiante, curso) if J.Document else ""
        if path:
            J.generated_files.add(path)
            J._open_doc(path)
        nota = str(fb["nota"]).replace(".", ",") if fb["nota"] is not None else "sin nota"
        msg = (f"Listo{' · ' + estudiante if estudiante else ''}: nota sugerida {nota}. Fortalezas: " + "; ".join(fb["fortalezas"][:2]) +
               ". Para mejorar: " + "; ".join(fb["mejorar"][:2]) + "." + (" Todo el detalle está en el Word." if path else ""))
        J.notify(msg, "RETROALIMENTACIÓN")
        if estudiante and curso and fb["nota"] is not None:
            J.request_approval("notas", f"Guardar {nota} a {estudiante} ({curso}) por el texto", fb["comentario"][:300],
                               on_ok=lambda: (seguimiento.add(curso, estudiante, "Texto escrito", fb["nota"], origen="revision"),
                                              J.reply(f"Guardé {nota} a {estudiante} en {curso}.", "RETROALIMENTACIÓN")),
                               on_no=lambda: None, ttl=1800,
                               say=f"¿Guardo el {nota} de {estudiante} en el seguimiento de {curso}? Di «sí» o «no».")
    if capture is not None:
        work()
    else:
        J.start_job("Revisando el texto del estudiante", work, "retro-texto")
    return True


def polish_start():
    estilo.configure(J.CONFIG_DIR)


__all__ = [
    '_TFB_RE', '_MV_RE', '_ST_FORGET', '_ST_LEARN', '_ST_SHOW', '_text_fb_docx', 'text_fb_prompt', 'text_fb_validate', 'learn_style',
    'handle_style_info', 'morning_brief_text', 'morning_voice', 'polish_start', 'send_morning_voice', 'style_ctx', 'style_voice', 'text_feedback_voice',
]
