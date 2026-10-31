"""8.2: observador del estudiante e informes para padres (uno o todo el curso).

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import re
import threading

import aula
import informes
import seguimiento
from nucleo import J

_OBS_ADD = re.compile(r"^(?:anota|anotale|registra|registrale|escribe|pon|ponle|agrega)\s+(?:en\s+)?(?:el\s+)?observador\s+"
                      r"(?:de|a|del estudiante)\s+(.+?)\s+que\s+(.+)$")
_OBS_ASK = re.compile(r"\b(?:que (?:tiene|hay de|dice el observador de)|como va el observador de)\s+(.+?)(?:\s+en el observador)?$")
_OBS_DOC = re.compile(r"\b(?:genera|haz|hazme|exporta|imprime|saca|sacame|dame)\s+(?:el\s+)?observador\s+(?:de|del estudiante)\s+(.+)$")
_LETTER = re.compile(r"\b(?:haz|hazme|genera|generame|prepara|preparame|redacta|redactame|escribe|elabora)\b.*?"
                     r"\b(?:informe|informes|carta|cartas|reporte|reportes)\b.*?\b(?:padres|acudientes|familia|familias)\s+"
                     r"(?:de|del|para)\s+(.+)$")


def _split_student(spoken):
    """«juan perez de 7a» → (curso, nombre del estudiante o "", [candidatos])."""
    m = re.match(r"^(.+?)\s+(?:de|del|en)\s+((?:\d{1,2}\s?[a-z]?|sexto|septimo|octavo|noveno|decimo|once|quinto)(?:\s+[a-z])?)$", spoken.strip())
    who, course_txt = (m.group(1), m.group(2)) if m else (spoken.strip(), "")
    course = J._resolve_course(course_txt)
    names = sorted(set(aula.data.get("cursos", {}).get(course, [])) | set(seguimiento.data.get(course, {}))
                   | set(informes.data.get(course, {})))
    if not names:
        return course, who.title(), []
    name, cands = aula.find_student(who, names)
    return course, name or "", cands


def _student_or_ask(spoken, origin="AULA"):
    course, name, cands = _split_student(spoken)
    if not course:
        J.reply("¿De qué curso? Dímelo al final, por ejemplo «de 7A».", origin)
        return None, None
    if not name:
        J.reply(("¿Cuál? " + ", ".join(cands[:4]) + ".") if cands else f"No encuentro a «{spoken}» en {course}.", origin)
        return None, None
    return course, name


def _facts(course, name):
    return informes.facts(course, name, seguimiento.data.get(course, {}).get(name, []), J._absences(course).get(name, 0))


def family_voice(text, t):
    m = _OBS_ADD.match(t)
    if m:
        orig = re.split(r"\bque\s+", text, maxsplit=1, flags=re.I)
        course, name = _student_or_ask(m.group(1), "OBSERVADOR")
        if not name:
            return True
        x = informes.add(course, name, orig[-1].strip() if len(orig) > 1 else m.group(2))
        J.reply(f"Anotado en el observador de {name} ({course}), como anotación {x['tipo']}.", "OBSERVADOR")
        return True
    m = _OBS_DOC.search(t)
    if m:
        course, name = _student_or_ask(m.group(1), "OBSERVADOR")
        if not name:
            return True
        if not informes.entries(course, name):
            J.reply(f"{name} no tiene anotaciones en el observador.", "OBSERVADOR")
            return True
        if J.Document is None:
            J.reply("No puedo crear documentos: falta python-docx.", "ERROR")
            return True
        path = informes.build_observer(course, name, J.settings["output_dir"], J.Document, J.settings["aula_institucion"])
        J.generated_files.add(path)
        opened = J._open_doc(path)
        J.reply(f"Listo el observador de {name}" + (", lo abrí." if opened else ": está en Documentos, Jarvis, Observador."), "OBSERVADOR")
        return True
    if "observador" in t:
        m = _OBS_ASK.search(t)
        if m:
            course, name = _student_or_ask(m.group(1), "OBSERVADOR")
            if name:
                J.reply(informes.spoken(course, name), "OBSERVADOR")
            return True
    m = _LETTER.search(t)
    if not m:
        return False
    target = re.sub(r"^(?:todo el curso|todos los estudiantes|todos los de|todos|el curso|los de)\s+(?:de\s+)?", "", m.group(1).strip())
    whole = aula.find_course(target) or (target.strip().upper() in seguimiento.data and target.strip().upper())
    if whole:
        course = whole
        names = sorted(set(aula.data.get("cursos", {}).get(course, [])) | set(seguimiento.data.get(course, {})))
        if not names:
            J.reply(f"No tengo estudiantes en {course}.", "INFORMES")
            return True
    else:
        course, name = _student_or_ask(target, "INFORMES")
        if not name:
            return True
        names = [name]
    if J.Document is None:
        J.reply("No puedo crear documentos: falta python-docx.", "ERROR")
        return True
    J.reply(f"Redacto {'el informe' if len(names) == 1 else f'{len(names)} informes'} para "
            f"{'la familia de ' + names[0] if len(names) == 1 else 'las familias de ' + course}…", "INFORMES")
    capture = getattr(J._tl, "capture", None)

    def work():
        facts = [_facts(course, n) for n in names]
        texts = {}
        try:
            for start in range(0, len(facts), 8):
                part = facts[start:start + 8]
                raw = J.ai_chat([{"role": "user", "content": informes.letter_prompt(part, J.settings["aula_docente"],
                                                                                     J.settings["aula_institucion"])}],
                                json_mode=True, max_tokens=8000)
                texts.update({start + i: v for i, v in informes.letter_validate(J._extract_json(raw), len(part)).items()})
        except J.AIError as e:
            J.notify(J.ai_error_reply(e), "INFORMES")
            return
        except (ValueError, TypeError) as e:
            J.notify(f"La IA no devolvió los informes bien: {e}", "INFORMES")
            return
        reports = [(facts[i], texts[i]) for i in sorted(texts)]
        if not reports:
            J.notify("La IA no devolvió informes válidos. Inténtalo otra vez.", "INFORMES")
            return
        path = informes.build_letters(reports, J.settings["output_dir"], J.Document, J.settings["aula_docente"],
                                      J.settings["aula_institucion"], title=(names[0] if len(names) == 1 else f"Curso {course}"))
        J.generated_files.add(path)
        opened = J._open_doc(path)
        miss = len(names) - len(reports)
        J.notify(f"Listo{'s' if len(reports) > 1 else ''} {len(reports)} informe{'s' if len(reports) != 1 else ''} para padres"
                 + (f" ({miss} no salieron, pídemelos otra vez)" if miss else "")
                 + (". Lo abrí: revísalo antes de enviarlo." if opened else ". Están en Documentos, Jarvis, Informes para padres."),
                 "INFORMES")
    if capture is not None:
        work()
    else:
        J.start_job("Redactando informes para padres", work, "informes")
    return True


def family_start():
    informes.configure(J.CONFIG_DIR)


__all__ = ['_LETTER', '_OBS_ADD', '_OBS_ASK', '_OBS_DOC', '_facts', '_split_student', '_student_or_ask', 'family_start',
           'family_voice']
