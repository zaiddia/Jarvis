"""12.52: nueve habilidades nuevas, inspiradas en lo que salió en los asistentes del mercado (noviembre de 2026):

1. (El vigía de páginas ya existía desde la 9.4: «avísame cuando publiquen algo nuevo en https://…».)
2. Escritura de toda la clase  «retroalimenta estas redacciones» (con los archivos que subiste)
3. «Piénsalo bien» / «rápido»  cuánto piensa, en la misma frase
4. Conversación privada        «modo privado»: no se guarda historial, diario ni costumbres
5. Lo clave primero            la primera frase dice lo principal (y en el HUD va en negrita)
6. (El pódcast con dos voces ya existía desde la 11.4: «haz un podcast de repaso de fracciones para 9A».)
7. Infografías                 «hazme una infografía del ciclo del agua para quinto»
8. Herramientas a tu medida    «créame una herramienta para llevar el préstamo de calculadoras»
9. Estilos de personalidad     «modo breve», «modo amable», «modo divertido», «modo formal», «modo normal»

La lógica está en escrituraclase.py, infografia.py, misherramientas.py y estilojarvis.py.
Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import glob
import os
import re
import time

import adjuntos
import animar
import diario
import escrituraclase as EC
import estilojarvis as EJ
import infografia as IG
import investigar
import misherramientas as MH
import recuerdos
from nucleo import J

# ============================================================================ 4. CONVERSACIÓN PRIVADA
priv = {"on": False, "since": 0.0, "keep": 0}
PRIV_IDLE = 60 * 60


def private_on():
    return priv["on"]


def private_set(on):
    """Entra o sale del modo privado. Al salir, lo conversado en privado se olvida (no queda ni en la memoria de la charla)."""
    if on and not priv["on"]:
        priv.update(on=True, since=time.time(), keep=len(J.chat_history))
    elif not on and priv["on"]:
        del J.chat_history[priv["keep"]:]
        priv.update(on=False)
        J.save_memory()
    diario.paused = recuerdos.paused = bool(on)
    J.set_state(private=bool(on))


_PRIV_ON = re.compile(r"^(?:jarvis\s+)?(?:(?:activa|pon|ponte en|entra en|entra al|inicia|abre|empieza)\s+(?:el\s+|la\s+|una\s+)?)?"
                      r"(?:modo privado|modo incognito|conversacion privada|charla privada|chat privado)\b"
                      r"|^(?:jarvis\s+)?(?:esto es|hablemos en|hablemos)\s+(?:privado|en privado|confidencial)\b")
_PRIV_OFF = re.compile(r"\b(?:sal|salir|salte|termina|desactiva|quita|apaga|cierra|acaba)\s+(?:del?\s+|el\s+|la\s+)?"
                       r"(?:modo privado|modo incognito|conversacion privada|chat privado)\b|\bya no (?:es|estamos en) privado\b")
_PRIV_Q = re.compile(r"\b(?:estoy|estamos|sigo|seguimos)\s+en\s+(?:el\s+)?modo privado\b")


def private_voice(text, t):
    if _PRIV_OFF.search(t):
        if not priv["on"]:
            J.reply("No estábamos en modo privado.", "PRIVADO")
        else:
            private_set(False)
            J.reply("Salí del modo privado. Lo que hablamos en privado ya lo olvidé; desde ahora vuelvo a guardar el historial.", "PRIVADO")
        return True
    if _PRIV_Q.search(t):
        J.reply("Sí, estamos en modo privado: no guardo nada." if priv["on"] else "No, ahora no estamos en modo privado.", "PRIVADO")
        return True
    if _PRIV_ON.search(t):
        private_set(True)
        J.reply("Modo privado: mientras dure, no guardo el historial ni el diario, y no aprendo de lo que digas. "
                "Cuando termines, di «sal del modo privado» y lo olvido.", "PRIVADO")
        return True
    return False


def private_tick():
    """Si te fuiste y quedó abierto, se cierra solo a la hora sin actividad."""
    last = getattr(J, "_ag", {}).get("last_user", 0) if isinstance(getattr(J, "_ag", None), dict) else 0
    if priv["on"] and time.time() - max(priv["since"], last) > PRIV_IDLE:
        private_set(False)
        J.log_terminal("Cerré el modo privado (una hora sin actividad) y olvidé lo conversado.", "PRIVADO")


# ============================================================================ 9 y 5. ESTILOS Y «LO CLAVE PRIMERO»
def style_rule():
    """La regla que va en las instrucciones de la IA: el estilo elegido y «lo clave primero»."""
    return EJ.rule(J.settings.get("assistant_style", "normal"))


def persona_style_voice(text, t):
    st = EJ.style_from(t)
    if not st:
        return False
    J.settings["assistant_style"] = st
    try:
        J.save_settings_file()
    except OSError:
        pass
    J.reply({"normal": "Vuelvo a mi estilo de siempre.", "breve": "Modo breve: contesto en una frase.",
             "amable": "Modo amable activado.", "divertido": "Modo divertido: con un poco de humor, sin perder la exactitud.",
             "formal": "Modo formal: trato de usted y lenguaje profesional."}[st], "ESTILO")
    return True


# ============================================================================ 3. «PIÉNSALO BIEN» / «RÁPIDO»
def think_voice(text, t):
    q = EJ.deep_question(t)
    if q:
        raw_q = re.sub(r"^\W*(?:jarvis\W+)?\S+(?:\s+\S+)?\s*[:,.]\s*", "", text.strip(), count=1) or q
        if J.state.get("ai") != "ok":
            J.reply("Para pensarlo a fondo necesito la IA conectada.", "IA")
            return True
        J.reply("Lo pienso con calma; te respondo en un momento.", "IA")

        def work():
            try:
                msgs = [{"role": "system", "content": J.settings["system_prompt"] + J.ACTION_RULE + style_rule() + J._user_ctx(raw_q)},
                        {"role": "user", "content": EJ.deep_prompt(raw_q)}]
                ans = J.motorlocal.clean_reply(J.ai_chat(msgs, max_tokens=3000)).strip()
            except J.AIError as e:
                J.notify(J.ai_error_reply(e), "IA")
                return
            J.chat_history.extend([{"role": "user", "content": raw_q}, {"role": "assistant", "content": ans}])
            del J.chat_history[:-40]
            J.save_memory()
            J.notify(ans, "IA")
        J.start_job("Pensando a fondo", work, "piensa")
        return True
    q = EJ.fast_question(t)
    if q and J.QUESTION_RE.search(q):
        raw_q = re.sub(r"^\W*(?:jarvis\W+)?\S+\s*[:,.]\s*", "", text.strip(), count=1) or q
        old = getattr(J._tl, "fast_model", "")
        J._tl.fast_model = J.fast_model()
        try:
            _kind, ans = J.ask_ai(raw_q + " (Responde en una o dos frases.)", route=False)
        finally:
            J._tl.fast_model = old
        J.reply(ans, "IA")
        return True
    return False


# ============================================================================ 2. ESCRITURA DE TODA LA CLASE
wf_state = {"busy": False}


def _upload_batch(limit=EC.MAX_TEXTS):
    """Lo último que subiste junto (hasta 40), o lo más reciente."""
    its = [adjuntos.get(x) for x in J._batch.get("ids", [])]
    its = [i for i in its if i and time.time() - i.get("t", 0) < 3600]
    return (its or adjuntos.recent(3600, n=limit))[:limit]


def _text_of_item(it):
    if it["tipo"] == "imagen":
        return J.ocr(it)
    text = adjuntos.text_of(it, 20000)
    if it["tipo"] == "pdf" and adjuntos.is_scanned(it, text):
        text = J.ocr(it)
    return text


def writing_feedback(its, consigna="", curso="", progress=None):
    """Revisa cada texto y arma el informe del grupo en Word. → (ruta, revisiones, errores comunes)."""
    reviews = []
    for k, it in enumerate(its):
        if progress:
            progress(k, len(its))
        text = (J._text_of_item(it) or "").strip()
        if len(text.split()) < 15:
            continue
        raw = J.ai_chat([{"role": "user", "content": EC.student_prompt(text, consigna, curso)}], json_mode=True, max_tokens=1500)
        r = EC.clean_student(J._extract_json(raw), it["nombre"])
        r["archivo"] = it["nombre"]
        reviews.append(r)
    if not reviews:
        raise ValueError("no encontré texto que revisar en los archivos (¿están borrosas las fotos?)")
    common = EC.common_errors(reviews)
    lesson = None
    if common:
        try:
            lesson = EC.clean_lesson(J._extract_json(J.ai_chat([{"role": "user", "content": EC.class_prompt(common, len(reviews), curso)}],
                                                               json_mode=True, max_tokens=2600)))
        except Exception:
            lesson = None
    path = _wf_docx(reviews, common, lesson, consigna, curso)
    return path, reviews, common


def _wf_docx(reviews, common, lesson, consigna, curso):
    import docx
    doc = docx.Document()
    doc.add_heading("Retroalimentación de escritura" + (f" · {curso}" if curso else ""), 0)
    doc.add_paragraph(f"{len(reviews)} textos revisados · {datetime.date.today().strftime('%d/%m/%Y')}"
                      + (f" · Consigna: {consigna}" if consigna else ""))
    lv = EC.levels(reviews)
    if lv:
        doc.add_paragraph("Desempeño: " + ", ".join(f"{n} en {lvl}" for lvl, n in lv) + ".")
    doc.add_heading("Lo que más se repite en el grupo", 1)
    for t, k, ex in common:
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(f"{t.capitalize()}: ").bold = True
        p.add_run(f"{k} de {len(reviews)} estudiantes. Ej.: " + "; ".join(f"«{e['dice']}» → «{e['debe_decir']}»" for e in ex[:2]))
    if lesson:
        doc.add_heading("Mini-clase para corregirlo (15 minutos)", 1)
        if lesson["objetivo"]:
            doc.add_paragraph().add_run("Objetivo: " + lesson["objetivo"]).bold = True
        if lesson["explicacion"]:
            doc.add_paragraph(lesson["explicacion"])
        for i, e in enumerate(lesson["ejercicios"], 1):
            doc.add_paragraph(f"{i}. {e['enunciado']}", style="List Number")
        if lesson["ejercicios"]:
            doc.add_paragraph("Respuestas: " + " · ".join(f"{i}) {e['respuesta']}" for i, e in enumerate(lesson["ejercicios"], 1)))
        if lesson["cierre"]:
            doc.add_paragraph(lesson["cierre"])
    doc.add_heading("Resumen por estudiante", 1)
    tb = doc.add_table(rows=1, cols=3)
    tb.style = "Light Grid Accent 1"
    for c, h in zip(tb.rows[0].cells, ("Estudiante", "Nivel", "Errores")):
        c.text = h
    for r in reviews:
        row = tb.add_row().cells
        row[0].text, row[1].text, row[2].text = r["estudiante"], r["nivel"] or "—", str(len(r["errores"]))
    for r in reviews:
        doc.add_page_break()
        doc.add_heading(r["estudiante"], 2)
        if r["comentario"]:
            doc.add_paragraph(r["comentario"])
        if r["fortalezas"]:
            doc.add_paragraph("Lo que hiciste bien: " + "; ".join(r["fortalezas"]))
        if r["mejorar"]:
            doc.add_paragraph("Para mejorar: " + "; ".join(r["mejorar"]))
        for e in r["errores"]:
            doc.add_paragraph(f"{e['tipo'].capitalize()}: «{e['dice']}» → «{e['debe_decir']}»", style="List Bullet")
    out = os.path.join(J.settings["output_dir"], "Retroalimentación")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f"Escritura {curso + ' ' if curso else ''}{time.strftime('%Y-%m-%d %H%M')}.docx".replace("/", "-"))
    doc.save(path)
    return path


_WF = re.compile(r"\b(?:retroalimenta|retroalimentame|revisa|revisame|corrige|corrigeme|califica|evalua)\s+"
                 r"(?:la\s+(?:escritura|redaccion|ortografia)\s+de\s+)?(?:estas|estos|las|los)\s+"
                 r"(?:redacciones|textos|ensayos|composiciones|escritos|cuentos|parrafos|cronicas|resenas|cartas)\b"
                 r"|\bretroalimentacion de escritura\b")
_WF_CONS = re.compile(r"\b(?:la\s+)?consigna\s+(?:era|es|fue)\s+(.+)$")


def writing_voice(text, t):
    if not _WF.search(t):
        return False
    its = _upload_batch()
    if not its:
        J.reply("Primero sube las redacciones al chat (fotos, PDF o Word; puedes subir varias a la vez) y luego dime "
                "«retroalimenta estas redacciones».", "ESCRITURA")
        return True
    if J.state.get("ai") != "ok":
        J.reply("Para revisar los textos necesito la IA conectada.", "ESCRITURA")
        return True
    if wf_state["busy"]:
        J.reply("Ya estoy revisando un grupo de textos; te aviso al terminar.", "ESCRITURA")
        return True
    m = _WF_CONS.search(t)
    consigna = m.group(1).strip() if m else ""
    cm = re.search(r"\b(?:de|del|para)\s+(\d{1,2}\s?[a-z]?|sexto|septimo|octavo|noveno|decimo|once)\b", t)
    curso = (J._resolve_course(cm.group(1)) or cm.group(1)) if cm else ""
    _writing_start(its, consigna, curso)
    return True


def _writing_start(its, consigna="", curso=""):
    wf_state["busy"] = True
    J.reply(f"Reviso {len(its)} texto(s): a cada uno le dejo su retroalimentación, y al grupo, los errores más comunes y una "
            "mini-clase. Te aviso al terminar.", "ESCRITURA")

    def work():
        try:
            path, reviews, common = writing_feedback(its, consigna, curso)
        except J.AIError as e:
            J.notify(J.ai_error_reply(e), "ESCRITURA")
            return
        except Exception as e:
            J.notify(f"No pude revisar los textos: {str(getattr(e, 'why', e))[:160]}", "ESCRITURA")
            return
        finally:
            wf_state["busy"] = False
        J.generated_files.add(path)
        J._open_doc(path)
        top = ", ".join(f"{t} ({k} de {len(reviews)})" for t, k, _ in common) or "sin errores repetidos"
        J.notify(f"Listo: revisé {len(reviews)} textos. Lo que más se repite: {top}. Te dejé un Word con la retroalimentación de "
                 "cada estudiante y una mini-clase para corregirlo, en Documentos, Jarvis, Retroalimentación.", "ESCRITURA")
    J.start_job("Revisando la escritura del grupo", work, "escritura")


# ============================================================================ 7. INFOGRAFÍAS
def make_infographic(tema, curso="", fuente="", style="colorido"):
    raw = J.ai_chat([{"role": "user", "content": IG.prompt(tema, curso, fuente)}], json_mode=True, max_tokens=1800)
    g = IG.clean(J._extract_json(raw))
    img = IG.render(g, animar.font, style)
    out = os.path.join(J.settings["output_dir"], "Infografías")
    os.makedirs(out, exist_ok=True)
    base = os.path.join(out, animar.safe_name(g["titulo"]) + time.strftime(" %Y-%m-%d %H%M"))
    img.save(base + ".png")
    img.save(base + ".pdf", "PDF", resolution=150.0)
    return {"png": base + ".png", "pdf": base + ".pdf", "titulo": g["titulo"]}


_IG = re.compile(r"^(?:jarvis\s+)?(?:haz|hazme|crea|creame|genera|generame|disena|disename|prepara|preparame|arma|armame)\s+"
                 r"(?:una|la)\s+infografia(?:\s+(?:oscura|sobria|colorida|formal|seria))?\s+(?:sobre|de|del|de la|acerca de)\s+(.+?)"
                 r"(?:\s+(?:para|en)\s+(?:el\s+|los\s+de\s+)?((?:grado\s+)?(?:\d{1,2}\s?[a-z]?|sexto|septimo|octavo|noveno|decimo|once|"
                 r"primero|segundo|tercero|cuarto|quinto))\b.*)?$")
_IG_DOC = re.compile(r"\b(?:convierte|pasa|vuelve|haz)(?:lo|la)?\s+(?:esta|este|estos|estas|el|la)?\s*(?:guia|documento|archivo|texto|pdf|lectura)?"
                     r"\s*(?:en|a)\s+(?:una\s+)?infografia\b")


def infographic_voice(text, t):
    fuente, tema, curso = "", "", ""
    if _IG_DOC.search(t):
        its = _upload_batch(3)
        if not its:
            J.reply("Sube primero el documento al chat y luego dime «conviértelo en infografía».", "INFOGRAFÍA")
            return True
        fuente = "\n\n".join(_text_of_item(i) or "" for i in its)[:10000]
        tema = its[0]["nombre"].rsplit(".", 1)[0]
    else:
        m = _IG.match(t)
        if not m:
            return False
        tema = m.group(1).strip()
        if m.group(2):
            curso = J._resolve_course(m.group(2)) or m.group(2)
    if J.state.get("ai") != "ok":
        J.reply("Para preparar la infografía necesito la IA conectada.", "INFOGRAFÍA")
        return True
    style = IG.style_in(t)
    J.reply(f"Preparo la infografía sobre «{tema}»…", "INFOGRAFÍA")

    def work():
        try:
            r = make_infographic(tema, curso, fuente, style)
        except J.AIError as e:
            J.notify(J.ai_error_reply(e), "INFOGRAFÍA")
            return
        except Exception as e:
            J.notify(f"No pude hacer la infografía: {str(getattr(e, 'why', e))[:160]}", "INFOGRAFÍA")
            return
        J.generated_files.add(r["png"])
        J.generated_files.add(r["pdf"])
        J._open_doc(r["png"])
        J.notify(f"Lista la infografía «{r['titulo']}»: en Documentos, Jarvis, Infografías, en imagen y en PDF para imprimir. "
                 "Para mostrarla en grande: «proyecta eso».", "INFOGRAFÍA")
    J.start_job("Haciendo la infografía", work, "infografia")
    return True


# ============================================================================ 8. HERRAMIENTAS A TU MEDIDA
def tools_dir():
    return os.path.join(J.settings["output_dir"], "Mis herramientas")


def make_tool(pedido):
    raw = J.ai_chat([{"role": "user", "content": MH.prompt(pedido)}], max_tokens=9000)
    page = MH.harden(MH.extract_html(raw))
    title = MH.title_of(page, pedido)
    os.makedirs(tools_dir(), exist_ok=True)
    path = os.path.join(tools_dir(), MH.safe_name(title) + ".html")
    if os.path.exists(path):
        path = path[:-5] + time.strftime(" %Y-%m-%d %H%M") + ".html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return path, title


_MH_NEW = re.compile(r"^(?:jarvis\s+)?(?:crea|creame|haz|hazme|construye|construyeme|programa|programame|disena|disename|arma|armame)\s+"
                     r"(?:una|un)\s+(?:herramienta|mini ?app|miniaplicacion|aplicacion|app|aplicativo)\s+(?:para|que|de|donde|con la que)\s+(.{6,})$")
_MH_OPEN = re.compile(r"\babre\s+(?:mis herramientas|la carpeta de (?:mis )?herramientas)\b|"
                      r"\babre\s+(?:la|mi)\s+herramienta\s+(?:de|del|para)\s+(.+)$")


def tools_voice(text, t):
    m = _MH_OPEN.search(t)
    if m:
        want = (m.group(1) or "").strip()
        files = sorted(glob.glob(os.path.join(tools_dir(), "*.html")), key=os.path.getmtime)
        if want:
            words = [w for w in re.findall(r"\w{4,}", want)]
            hit = next((f for f in reversed(files) if words and all(w in J.normalize(os.path.basename(f)) for w in words)), None) or \
                next((f for f in reversed(files) if any(w in J.normalize(os.path.basename(f)) for w in words)), None)
            if not hit:
                J.reply("No encuentro esa herramienta. Di «abre mis herramientas» para ver todas.", "HERRAMIENTAS")
                return True
            J._open_doc(hit)
            J.reply(f"Abrí «{os.path.basename(hit)[:-5]}».", "HERRAMIENTAS")
            return True
        os.makedirs(tools_dir(), exist_ok=True)
        J._open_doc(tools_dir())
        J.reply(f"Abrí tus herramientas ({len(files)}).", "HERRAMIENTAS")
        return True
    m = _MH_NEW.match(t)
    if not m:
        return False
    if J.state.get("ai") != "ok":
        J.reply("Para construir la herramienta necesito la IA conectada.", "HERRAMIENTAS")
        return True
    pedido = text.strip()
    J.reply("La construyo: queda como una página que funciona sin internet y guarda sus datos en este equipo. Te aviso.", "HERRAMIENTAS")

    def work():
        try:
            path, title = make_tool(pedido)
        except J.AIError as e:
            J.notify(J.ai_error_reply(e), "HERRAMIENTAS")
            return
        except Exception as e:
            J.notify(f"No pude construir la herramienta: {str(getattr(e, 'why', e))[:160]}", "HERRAMIENTAS")
            return
        J.generated_files.add(path)
        J._open_doc(path)
        J.notify(f"Lista la herramienta «{title}». Quedó en Documentos, Jarvis, Mis herramientas; para abrirla otro día: "
                 "«abre mis herramientas». Funciona sin internet y no puede enviar tus datos a ninguna parte.", "HERRAMIENTAS")
    J.start_job("Construyendo tu herramienta", work, "herramienta")
    return True


# ============================================================================ TODO JUNTO
def nuevas52_voice(text, t):
    """Las órdenes de las 9 habilidades (menos «piénsalo bien / rápido» y el modo privado, que van antes)."""
    for fn in (persona_style_voice, writing_voice, infographic_voice, tools_voice):
        if fn(text, t):
            return True
    return False


def nuevas52_tick():
    for fn in (private_tick,):
        try:
            fn()
        except Exception as e:
            J.note_error("NUEVAS", e)


__all__ = ["priv", "PRIV_IDLE", "private_on", "private_set", "private_voice", "private_tick", "_PRIV_ON", "_PRIV_OFF", "_PRIV_Q",
           "style_rule", "persona_style_voice", "think_voice",
           "wf_state", "_upload_batch", "_text_of_item", "writing_feedback", "_wf_docx", "writing_voice", "_writing_start", "_WF", "_WF_CONS",
           "make_infographic", "infographic_voice", "_IG", "_IG_DOC",
           "tools_dir", "make_tool", "tools_voice", "_MH_NEW", "_MH_OPEN",
           "nuevas52_voice", "nuevas52_tick"]
