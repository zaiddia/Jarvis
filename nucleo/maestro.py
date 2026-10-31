"""9.4: lecciones de tus correcciones, vigilante de páginas web y modo tutor socrático para la clase.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import re
import threading
import time

import investigar
import lecciones
import paginas
from nucleo import J


# ============================================================================ LECCIONES
_L_LIST = re.compile(r"\b(?:que|cuales)\s+lecciones\s+(?:tienes|has aprendido|te he ensenado)\b|\bque has aprendido de mis correcciones\b|"
                     r"\bmis lecciones\b")
_L_DEL = re.compile(r"^(?:olvida|borra|quita|elimina)\s+la leccion\s+(?:de|sobre|que dice)?\s*(.+)$")


def _last_turn():
    """(lo último que pediste, lo último que respondió Jarvis) antes de esta orden."""
    user, jarvis = "", ""
    for item in reversed(list(J.chat_buffer)[:-1] if J.chat_buffer and J.chat_buffer[-1].get("role") == "user" else list(J.chat_buffer)):
        if not jarvis and item.get("role") != "user":
            jarvis = item["text"]
        elif jarvis and item.get("role") == "user":
            user = item["text"]
            break
    return user, jarvis


def lessons_voice(text, t):
    if _L_LIST.search(t):
        if not lecciones.items:
            J.reply("Aún no tengo lecciones. Enséñame con «de ahora en adelante…» o corrígeme cuando me equivoque.", "LECCIONES")
        else:
            J.reply(f"Tengo {len(lecciones.items)} {'lecciones' if len(lecciones.items) != 1 else 'lección'}: " +
                    "; ".join(x["texto"] for x in lecciones.items[-8:]) + ".", "LECCIONES")
        return True
    m = _L_DEL.match(t)
    if m:
        x = lecciones.remove(m.group(1))
        J.reply(f"Olvidé la lección: {x['texto']}." if x else "No encuentro esa lección.", "LECCIONES")
        return True
    rule = lecciones.rule_from(text)
    if rule and not re.search(r"\b(?:recuerdame|avisame|cada (?:dia|lunes|martes|miercoles|jueves|viernes|semana)|a las \d)\b", t):
        x = lecciones.add(rule, "tú")
        J.reply(("Entendido, lo tendré en cuenta siempre: " + x["texto"] + ".") if x else "Eso ya lo tenía aprendido.", "LECCIONES")
        return True
    if lecciones.CORRECTION_RE.match(t) and J.settings["lessons_learn"]:
        user, jarvis = _last_turn()
        if not (user and jarvis):
            return False
        threading.Thread(target=J._propose_lesson, args=(user, jarvis, text), daemon=True, name="leccion").start()
        return False                                   # la corrección se atiende igual: la lección es aparte
    return False


def _propose_lesson(user, jarvis, correction):
    try:
        raw = J.ai_chat([{"role": "user", "content": lecciones.propose_prompt(user, jarvis, correction)}], json_mode=True, max_tokens=200)
        text = str(J._extract_json(raw).get("leccion", "")).strip()
    except Exception:
        return
    if len(text.split()) < 3:
        return
    J.request_approval("leccion", f"Aprender: {text[:160]}", f"Pedido: {user[:200]}\nCorrección: {correction[:200]}",
                       on_ok=lambda: J.reply(f"Aprendido: {text}.", "LECCIONES") if lecciones.add(text, "corrección") else None,
                       on_no=lambda: None, ttl=3600,
                       say=f"¿Quieres que aprenda esto para la próxima: «{text}»? Di «sí» o «no».")


def lessons_ctx():
    return lecciones.context()


@J.socketio.on("lessons")
def handle_lessons(data=None):
    d = data or {}
    if d.get("delete"):
        lecciones.delete(str(d["delete"]))
    if d.get("add"):
        lecciones.add(str(d["add"]), "tú")
    return {"items": lecciones.items[::-1]}


# ============================================================================ VIGILANTE DE PÁGINAS WEB
_URL_W = re.compile(r"https?://[^\s<>«»\"']+", re.I)
_W_ADD = re.compile(r"\b(?:vigila|vigilame|monitorea|sigue|revisa cada cierto tiempo|avisame (?:cuando|si) (?:publiquen|cambie|haya algo nuevo|"
                    r"salga algo)|estate pendiente de)\b")
_W_LIST = re.compile(r"\bque paginas (?:estas vigilando|vigilas|sigues)\b|\bpaginas vigiladas\b")
_W_DEL = re.compile(r"\b(?:deja de vigilar|ya no vigiles|no vigiles mas|quita la vigilancia de)\s+(?:la pagina\s+(?:de\s+)?)?(.+)$")


def page_watch_voice(text, t):
    if _W_LIST.search(t):
        if not paginas.items:
            J.reply("No estoy vigilando ninguna página. Dime «avísame cuando publiquen algo nuevo en https://…».", "VIGILANTE WEB")
        else:
            J.reply(f"Vigilo {len(paginas.items)} página{'s' if len(paginas.items) != 1 else ''}: " + "; ".join(
                f"{x['nombre']} (cada {x['horas']} h" + (f", último cambio {x['cambio'][:10]}" if x["cambio"] else "") + ")" for x in paginas.items) + ".",
                "VIGILANTE WEB")
        return True
    m = _W_DEL.search(t)
    if m:
        x = paginas.remove(m.group(1).strip())
        J.reply(f"Dejé de vigilar {x['nombre']}." if x else "No encuentro esa página entre las vigiladas.", "VIGILANTE WEB")
        return True
    url = _URL_W.search(text)
    if not (_W_ADD.search(t) and ("pagina" in t or "web" in t or url)):
        return False
    if not url:
        J.reply("Pásame el enlace de la página (https://…) y la vigilo. Por ejemplo: «avísame cuando publiquen algo nuevo en https://…».",
                "VIGILANTE WEB")
        return True
    link = url.group(0).rstrip(".,;)")
    hm = re.search(r"\bcada\s+(\d{1,2})\s+horas?\b", t)
    nm = re.search(r"\b(?:la pagina de|la web de|el sitio de)\s+(.+?)(?:\s+https?|$)", t)
    it, new = paginas.add(link, (nm.group(1).strip().title() if nm else ""), int(hm.group(1)) if hm else J.settings["watch_hours"])
    if not new:
        J.reply(f"Ya estaba vigilando {it['nombre']}.", "VIGILANTE WEB")
        return True
    J.reply(f"Listo, vigilo {it['nombre']} cada {it['horas']} horas y te aviso cuando publiquen algo nuevo.", "VIGILANTE WEB")
    J.start_job(f"Leyendo {it['nombre']} por primera vez", lambda: J.watch_check(it), "vigilante")
    return True


@J.socketio.on("pages")
def handle_pages(data=None):
    d = data or {}
    if d.get("delete"):
        paginas.items[:] = [x for x in paginas.items if x["id"] != d["delete"]]
        paginas.save()
    return {"items": [{k: x[k] for k in ("id", "url", "nombre", "horas", "ultima", "cambio")} for x in paginas.items]}


def watch_check(item):
    """Revisa una página. Devuelve el aviso (o "")."""
    try:
        text = investigar.page_text(J._get_text(item["url"], timeout=20)[:1500000], limit=200000)
    except Exception as e:
        J.log_terminal(f"Vigilante web, {item['nombre']}: {e}", "AVISO")
        return ""
    new = paginas.check(item, text)
    if not new:
        return ""
    summary = ""
    if J.state.get("ai") == "ok":
        try:
            summary = J.ai_chat([{"role": "user", "content": paginas.summary_prompt(item["nombre"], new)}], max_tokens=300).strip()
        except Exception:
            summary = ""
    msg = f"Novedad en {item['nombre']}: " + (summary or ("; ".join(new[:3])[:400])) + f" ({item['url']})"
    J.alert(msg, "VIGILANTE WEB")
    return msg


def _page_watch_worker():
    time.sleep(300)
    while True:
        try:
            if not J.is_offline():
                for it in paginas.due():
                    J.watch_check(it)
        except Exception as e:
            J.note_error("VIGILANTE WEB", e)
        time.sleep(600)


# ============================================================================ MODO TUTOR SOCRÁTICO
tutor = {"on": False, "materia": "", "grado": ""}
_T_ON = re.compile(r"\b(?:activa|activar|pon|inicia|empieza|modo)\s+(?:el\s+)?(?:modo\s+)?tutor(?:\s+socratico)?\b(?:\s+(?:de|en)\s+(.+?))?"
                   r"(?:\s+(?:para|de)\s+((?:\d{1,2}\s?[a-z]?|sexto|septimo|octavo|noveno|undecimo|decimo|onceavo|once|quinto|primaria|bachillerato)\b.*))?$")
_T_OFF = re.compile(r"\b(?:desactiva|quita|apaga|termina|sal del|salir del|cierra)\s+(?:el\s+)?modo tutor\b|\bmodo normal\b")

TUTOR_RULE = (" MODO TUTOR SOCRÁTICO: ahora hablas con estudiantes de colegio en clase{extra}. NUNCA des la respuesta final de un "
              "ejercicio o tarea: guía con UNA pregunta o pista corta a la vez, pide que expliquen su razonamiento, celebra lo que "
              "hagan bien y corrige con amabilidad. Si piden la respuesta directa, explica que la idea es que lleguen ellos y da "
              "una pista más. Usa lenguaje sencillo, frases cortas y ejemplos cotidianos de Colombia. Temas no escolares o "
              "inapropiados: redirige con respeto a la clase.")


def tutor_ctx():
    if not tutor["on"]:
        return ""
    extra = "".join(x for x in ((f" de {tutor['materia']}" if tutor["materia"] else ""), (f", grado {tutor['grado']}" if tutor["grado"] else "")))
    return TUTOR_RULE.format(extra=extra)


def tutor_voice(text, t):
    if _T_OFF.search(t):
        if tutor["on"]:
            tutor.update(on=False)
            J.socketio.emit("tutor", {"on": False})
            J.reply("Salí del modo tutor. Vuelvo a responder normal.", "TUTOR")
            return True
        return False
    m = _T_ON.search(t)
    if not m or "tutor" not in t:
        return False
    tutor.update(on=True, materia=(m.group(1) or "").strip(), grado=(m.group(2) or "").strip())
    J.socketio.emit("tutor", {"on": True, "materia": tutor["materia"], "grado": tutor["grado"]})
    J.reply("Modo tutor activado" + (f" para {tutor['materia']}" if tutor["materia"] else "") +
            ". Guiaré a los estudiantes con preguntas y pistas, sin darles la respuesta. Si quieres verlo en el televisor, di "
            "«modo proyector». Para terminar: «desactiva el modo tutor».", "TUTOR")
    return True


def tutor_relay(item):
    """Lo que se dice en modo tutor también va al proyector (en grande)."""
    if tutor["on"] and item.get("text"):
        try:
            J.socketio.emit("tutor_msg", {"role": item.get("role"), "text": str(item["text"])[:800]})
        except Exception:
            pass


@J.socketio.on("tutor_state")
def handle_tutor_state(data=None):
    return dict(tutor)


def teacher_plus_start():
    lecciones.configure(J.CONFIG_DIR)
    paginas.configure(J.CONFIG_DIR)
    threading.Thread(target=J._page_watch_worker, daemon=True, name="vigilante-web").start()


__all__ = [
    'TUTOR_RULE', '_L_DEL', '_L_LIST', '_T_OFF', '_T_ON', '_URL_W', '_W_ADD', '_W_DEL', '_W_LIST', '_last_turn', '_propose_lesson',
    '_page_watch_worker', 'handle_lessons', 'handle_pages', 'handle_tutor_state', 'lessons_ctx', 'lessons_voice', 'teacher_plus_start', 'tutor',
    'tutor_ctx', 'tutor_relay', 'tutor_voice', 'watch_check', 'page_watch_voice',
]
