"""12.8: boletines del periodo para las familias, un PDF por estudiante (todas las asignaturas que le das), listos para
mandar por WhatsApp o imprimir, con un PDF de todo el curso para imprimir y los mensajes para WhatsApp ya escritos.

«Jarvis, haz los boletines de 7A», «boletín de Ana Gómez de 7A», «boletines de todos los cursos». Nada se envía solo.
La lógica y el PDF están en boletin.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import os
import re
import subprocess
import sys
import webbrowser

import asignaturas
import aula
import boletin
import horario
import informes
import seguimiento
import zeti
from nucleo import J

_BOL_RE = re.compile(r"^(?:jarvis\s+)?(?:(?:haz|hazme|genera|generame|crea|creame|saca|sacame|prepara|preparame|dame|imprime|necesito)\s+)?"
                     r"(?:los\s+|el\s+|un\s+)?(?:boletin|boletines)\b(?:\s+(?:del|de este|de)\s+periodo)?"
                     r"(?:\s+(?:de|del|para|a)\s+(?:los\s+de\s+|la\s+de\s+)?(.+))?$")


def _bol_materia(key):
    base, subj = asignaturas.split(key)
    if subj:
        return subj
    return next((x.get("materia", "") for x in horario.items if aula.course_key(x.get("curso", "")) == aula.course_key(base)
                 and x.get("materia")), "")


def bol_course_keys(course):
    """Las claves de notas de ese curso: «7A» y, si das varias asignaturas, «7A · Tecnología»…"""
    ck = aula.course_key(course)
    keys = [k for k in seguimiento.data if aula.course_key(asignaturas.split(k)[0]) == ck]
    return sorted(keys, key=lambda k: (asignaturas.split(k)[1] != "", k)) or [course]


def bol_students(course):
    names = list(aula.students(course))
    for k in bol_course_keys(course):
        names += [n for n in seguimiento.data.get(k, {}) if n not in names]
    return names


def sheets_for(course, name):
    """[hoja por asignatura] del estudiante (solo las que tienen notas, o una vacía si no tiene ninguna)."""
    J.zeti_apply()
    per = int(J.settings["period_current"])
    fallas = J._absences(course).get(name, 0)
    obs = informes.entries(course, name)
    out = []
    for k in bol_course_keys(course):
        notas = seguimiento.data.get(k, {}).get(name)
        if notas is None:
            continue
        try:
            year = J.year_status(k, name)
        except Exception:
            year = None
        out.append(boletin.sheet(asignaturas.split(k)[0], name, notas, fallas, obs, year, zeti.WEIGHTS, J.settings["zeti_since"],
                                 _bol_materia(k), per))
    if not out:
        out.append(boletin.sheet(course, name, [], fallas, obs, None, zeti.WEIGHTS, "", _bol_materia(course), per))
    return out


def bol_comments(sheets):
    """El comentario de cada hoja con la IA (de a 10); las que no salgan, con reglas. → ([texto], usó_ia)."""
    texts, used = {}, False
    for start in range(0, len(sheets), 10):
        part = sheets[start:start + 10]
        try:
            raw = J.ai_chat([{"role": "user", "content": boletin.comment_prompt(part, J.settings["aula_docente"],
                                                                                 J.settings["aula_institucion"]) + J.style_ctx()}],
                            json_mode=True, max_tokens=4000)
            got = boletin.comment_validate(J._extract_json(raw), len(part))
            used = used or bool(got)
            texts.update({start + i: v for i, v in got.items()})
        except Exception as e:                         # sin IA o respuesta rara: siguen con reglas, el boletín sale igual
            J.log_terminal(f"Boletines: comentario con reglas ({str(e)[:80]})", "BOLETINES")
    return [texts.get(i) or boletin.fallback_comment(s) for i, s in enumerate(sheets)], used


def make_boletines(course, names):
    """Crea los PDF. → {"folder", "files", "all", "used_ai", "n"}."""
    plan = [(n, sheets_for(course, n)) for n in names]
    flat = [s for _, ss in plan for s in ss]
    texts, used = bol_comments(flat)
    per = int(J.settings["period_current"])
    folder = os.path.join(J.settings["output_dir"], "Boletines", boletin.folder_name(course, per))
    inst, doc = J.settings["aula_institucion"], J.settings["aula_docente"]
    files, all_pages, msgs, i = [], [], [], 0
    for n, ss in plan:
        pages = list(zip(ss, texts[i:i + len(ss)]))
        i += len(ss)
        files.append(boletin.build_pdf(pages, os.path.join(folder, boletin.safe(n) + ".pdf"), inst, doc))
        all_pages += pages
        msgs.append(f"{n}\n{boletin.message(n, ss, doc)}\n")
    whole = ""
    if len(plan) > 1:
        whole = boletin.build_pdf(all_pages, os.path.join(folder, f"_Todo el curso {boletin.safe(course)} (para imprimir).pdf"), inst, doc)
        with open(os.path.join(folder, "_Mensajes para WhatsApp.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(msgs))
    for p in files + ([whole] if whole else []):
        J.generated_files.add(p)
    return {"folder": folder, "files": files, "all": whole, "used_ai": used, "n": len(files)}


def _bol_open_folder(folder):
    try:
        if J.IS_WIN:
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            webbrowser.open(f"file://{folder}")
        return True
    except Exception:
        return False


def _bol_run(course, names, origin="BOLETINES"):
    if not boletin.available():
        J.reply("Para los boletines en PDF falta la librería «fpdf2»: ejecuta instalar.bat o actualiza Jarvis. Mientras tanto, "
                "di «informe para los padres de …» y te los hago en Word.", origin)
        return
    capture = getattr(J._tl, "capture", None)
    J.reply(f"Preparo {'el boletín de ' + names[0] if len(names) == 1 else f'{len(names)} boletines de {course}'}: notas por dimensión, "
            "fallas, cómo va el año, observador y un comentario para la familia…", origin)

    def work():
        try:
            r = make_boletines(course, names)
        except Exception as e:
            J.note_error("BOLETINES", e)
            J.notify(f"No pude hacer los boletines: {str(e)[:160]}", origin)
            return
        opened = J._open_doc(r["files"][0]) if r["n"] == 1 else _bol_open_folder(r["folder"])
        J.socketio.emit("aula", {"type": "boletines", "folder": r["folder"], "n": r["n"], "path": r["all"] or r["files"][0]})
        J.notify((f"Listo el boletín de {names[0]}" if r["n"] == 1 else
                  f"Listos {r['n']} boletines de {course}, uno por estudiante, más uno de todo el curso para imprimir y los mensajes "
                  "para WhatsApp ya escritos")
                 + ("" if r["used_ai"] else " (el comentario lo escribí con las notas, sin IA)")
                 + (". Te abrí la carpeta: revísalos antes de enviarlos." if opened and r["n"] > 1 else
                    ". Lo abrí: revísalo antes de enviarlo." if opened else ". Están en Documentos, Jarvis, Boletines."), origin)
    if capture is not None:
        work()
    else:
        J.start_job("Haciendo boletines", work, "boletines")


def boletines_for(target, origin="BOLETINES"):
    target = re.sub(r"^(?:todo el curso|todos los estudiantes|todos los de|todos|el curso|los de|la de|el de)\s+(?:de\s+)?", "",
                    str(target or "").strip())
    if not target:
        target = J.agent.get("curso") or ""
    if re.match(r"^(?:todos los cursos|todos mis cursos|cada curso|todos)$", target):
        courses = sorted({asignaturas.split(k)[0] for k in seguimiento.data}, key=aula.course_sort_key)
        if not courses:
            J.reply("No tengo notas de ningún curso todavía.", origin)
            return True
        for c in courses:
            names = bol_students(c)
            if names:
                _bol_run(c, names, origin)
        return True
    course = aula.find_course(target) if target else ""
    if not course and target.strip().upper() in {asignaturas.split(k)[0] for k in seguimiento.data}:
        course = target.strip().upper()
    if course:
        names = bol_students(course)
        if not names:
            J.reply(f"No tengo estudiantes en {course}.", origin)
            return True
        _bol_run(course, names, origin)
        return True
    if not target:
        J.reply("¿De qué curso? Por ejemplo: «boletines de 7A» o «boletín de Ana Gómez de 7A».", origin)
        return True
    course, name = J._student_or_ask(target, origin)
    if name:
        _bol_run(course, [name], origin)
    return True


def boletin_voice(text, t):
    m = _BOL_RE.search(t)
    if not m:
        return False
    return boletines_for(m.group(1) or "")


@J.socketio.on("boletines")
def handle_boletines(data=None):
    d = data or {}
    course = str(d.get("curso") or aula.data.get("activo") or "").strip()
    if not course:
        return {"ok": False, "error": "Elige primero un curso."}
    boletines_for(course)
    return {"ok": True}


__all__ = ['_BOL_RE', 'bol_comments', 'boletin', 'boletin_voice', 'boletines_for', 'bol_course_keys', 'handle_boletines', 'make_boletines',
           'sheets_for', 'bol_students']
