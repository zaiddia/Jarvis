"""12.11: Modo Código para Tecnología e Informática. Revisa, explica y mejora código que subes al chat (.py, .js, .html…) o
que pegas: «revisa este código: …», «explícame este código», «corrige mi programa», «haz ejercicios con este código».

Nunca ejecuta el código: primero el analizador encuentra los errores de sintaxis reales (con su línea) y después la IA explica,
busca errores de lógica, sugiere mejoras y da el código corregido. El informe completo queda en Word (Documentos › Jarvis ›
Código). Solo trabaja con lo que TÚ pegas o subes. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import os
import re

import adjuntos
import codigo
from nucleo import J

_CODE_ASK = re.compile(r"^(?:jarvis\s+)?(?:por favor\s+)?(revisa(?:me)?|explica(?:me)?|corrige(?:me)?|analiza(?:me)?|mejora(?:me)?|depura(?:me)?|"
                       r"que hace|que errores tiene|encuentra (?:los )?errores (?:de|en))\s+(?:este|el|mi|ese|esto|este\s+programa|el\s+programa)?\s*"
                       r"(?:codigo|programa|script)\b")
_CODE_EX = re.compile(r"\b(?:haz(?:me)?|crea(?:me)?|genera(?:me)?|arma(?:me)?|dame)\s+(?:unos\s+|\d+\s+)?(?:ejercicios|retos|actividades)\s+"
                      r"(?:con|sobre|de|a partir de)\s+(?:este|el|ese)\s+(?:codigo|programa)\b")


def _cd_goal(verb):
    return "explicar" if verb.startswith(("explica", "que hace")) else "corregir" if verb.startswith(("corrige", "depura", "que errores", "encuentra")) else "revisar"


def _code_from_text(text):
    """El código pegado después de «:» o del primer salto de línea."""
    raw = str(text or "")
    for sep in ("\n", ":"):
        if sep in raw:
            body = raw.split(sep, 1)[1].strip("\n ")
            body = re.sub(r"^```[\w+-]*\n|\n?```\s*$", "", body)
            if codigo.looks_like_code(body):
                return body
    return ""


def _recent_code_file():
    for it in reversed(adjuntos.recent(1800)):
        if str(it.get("nombre", "")).lower().endswith(codigo.CODE_EXTS):
            return it
    return None


def _cd_read(it):
    with open(it["ruta"], encoding="utf-8", errors="replace") as f:
        return f.read(codigo.MAX_CHARS * 2)


def _cd_report(name, lang, code, r, exercises=None):
    """El informe en Word: resumen, errores (línea, problema, arreglo), mejoras, paso a paso, código corregido y ejercicios."""
    from docx import Document
    from docx.shared import Pt
    doc = Document()
    doc.add_heading(f"Revisión de código: {name or 'código pegado'}", 1)
    doc.add_paragraph(f"{lang} · {len(code.splitlines())} líneas · {datetime.date.today():%d/%m/%Y}" + (f" · nivel {r['nivel']}" if r.get("nivel") else ""))
    if r.get("resumen"):
        doc.add_heading("Qué hace", 2)
        doc.add_paragraph(r["resumen"])
    doc.add_heading("Errores", 2)
    if r["errores"]:
        t = doc.add_table(rows=1, cols=3)
        t.style = "Light Grid Accent 1"
        for c, h in zip(t.rows[0].cells, ("Línea", "Problema", "Cómo arreglarlo")):
            c.text = h
        for e in r["errores"]:
            row = t.add_row().cells
            row[0].text, row[1].text, row[2].text = str(e["linea"] or "—"), e["problema"], e.get("arreglo", "")
    else:
        doc.add_paragraph("No se encontraron errores.")
    if r.get("mejoras"):
        doc.add_heading("Mejoras", 2)
        for m in r["mejoras"]:
            doc.add_paragraph(m, style="List Bullet")
    if r.get("pasos"):
        doc.add_heading("Paso a paso", 2)
        for p in r["pasos"]:
            doc.add_paragraph(p, style="List Number")

    def code_block(title, text):
        doc.add_heading(title, 2)
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.font.name = "Consolas"
        run.font.size = Pt(9)
    if r.get("corregido"):
        code_block("Código corregido", r["corregido"])
    code_block("Código original", code[:codigo.MAX_CHARS])
    for i, e in enumerate(exercises or [], 1):
        doc.add_heading(f"Ejercicio {i}: {e['tipo']}", 2)
        doc.add_paragraph(e["enunciado"])
        if e.get("codigo"):
            p = doc.add_paragraph()
            run = p.add_run(e["codigo"])
            run.font.name = "Consolas"
            run.font.size = Pt(9)
        doc.add_paragraph("Respuesta (docente): " + e["respuesta"])
    folder = os.path.join(J.settings["output_dir"], "Código")
    os.makedirs(folder, exist_ok=True)
    base = re.sub(r'[<>:"/\\|?*]+', " ", os.path.splitext(name or "codigo pegado")[0]).strip()[:50] or "codigo"
    path = os.path.join(folder, f"{base} - {'ejercicios' if exercises else 'revisión'} {datetime.datetime.now():%Y-%m-%d %H%M}.docx")
    doc.save(path)
    J.generated_files.add(path)
    return path


def code_review(code, name="", goal="revisar", origin="CÓDIGO"):
    """Revisa el código (analizador + IA). → (texto para el chat, ruta del informe o "")."""
    lang = codigo.lang_of(name, code)
    findings = codigo.syntax_check(code, lang)
    n = len(code.splitlines())
    try:
        raw = J.ai_chat([{"role": "user", "content": codigo.review_prompt(code, lang, name, findings, goal)}], json_mode=True, max_tokens=4000)
        r = codigo.review_validate(J._extract_json(raw), findings)
    except Exception as e:                             # sin IA: al menos los errores reales del analizador
        J.log_terminal(f"Modo Código sin IA: {str(e)[:80]}", "CÓDIGO")
        r = codigo.review_validate({}, findings)
        msg = (f"Sin IA solo pude revisar la sintaxis de {('«' + name + '»') if name else 'tu código'} ({lang}). " +
               ("Errores: " + "; ".join((f"línea {f['linea']}: " if f["linea"] else "") + f["problema"] for f in findings) + "."
                if findings else "No tiene errores de sintaxis; para errores de lógica y mejoras necesito la IA."))
        return msg, ""
    path = _cd_report(name, lang, code, r)
    return codigo.spoken(r, name, lang, n) + " Te dejé el informe completo, con el código corregido, en Documentos › Jarvis › Código.", path


def code_exercises(code, name="", origin="CÓDIGO"):
    lang = codigo.lang_of(name, code)
    raw = J.ai_chat([{"role": "user", "content": codigo.exercises_prompt(code, lang, J.agent.get("curso", ""))}], json_mode=True, max_tokens=4000)
    ex = codigo.exercises_validate(J._extract_json(raw))
    if not ex:
        return "No pude armar los ejercicios; prueba otra vez.", ""
    path = _cd_report(name, lang, code, codigo.review_validate({}), ex)
    return (f"Listos {len(ex)} ejercicios con {('«' + name + '»') if name else 'tu código'}: " + ", ".join(e["tipo"] for e in ex) +
            ". Están en Word con las respuestas para ti (Documentos › Jarvis › Código).", path)


def _cd_run(fn, code, name, *args):
    def work():
        try:
            msg, path = fn(code, name, *args)
        except J.AIError as e:
            msg, path = J.ai_error_reply(e), ""
        except Exception as e:
            J.note_error("CÓDIGO", e)
            msg, path = f"No pude revisar el código: {str(e)[:150]}", ""
        J.notify(msg, "CÓDIGO")
    if getattr(J._tl, "capture", None) is not None:
        work()
    else:
        J.start_job("Revisando el código", work, "codigo")


def code_review_voice(text, t):
    ask, ex = _CODE_ASK.match(t), _CODE_EX.search(t)
    if not (ask or ex):
        return False
    code, name = _code_from_text(text), ""
    if not code:
        it = _recent_code_file()
        if it:
            code, name = _cd_read(it), it["nombre"]
    if not code:
        J.reply("Pega el código después de la orden (por ejemplo «revisa este código:» y debajo el código) o súbelo con el clip "
                "(.py, .js, .html, .java, .c, .ino…).", "CÓDIGO")
        return True
    if ex:
        J.reply(f"Armo ejercicios con {('«' + name + '»') if name else 'tu código'}…", "CÓDIGO")
        _cd_run(code_exercises, code, name)
    else:
        goal = _cd_goal(ask.group(1))
        J.reply(f"{'Te explico' if goal == 'explicar' else 'Reviso'} {('«' + name + '»') if name else 'tu código'}: primero la sintaxis, sin ejecutarlo, "
                "y luego errores de lógica y mejoras…", "CÓDIGO")
        _cd_run(code_review, code, name, goal)
    return True


def code_attach_action(it, action):
    """Desde la tarjeta del archivo subido: «Revisar código» o «Ejercicios con este código»."""
    code = _cd_read(it)
    if action == "codigo_ej":
        _cd_run(code_exercises, code, it["nombre"])
    else:
        _cd_run(code_review, code, it["nombre"], "revisar")


__all__ = ['_CODE_ASK', '_CODE_EX', 'code_attach_action', 'code_exercises', 'code_review', 'code_review_voice']
