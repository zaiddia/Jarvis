"""10.4: áreas y asignaturas (Matemáticas, Tecnología e Informática…): escoger la asignatura, notas aparte por asignatura
en el mismo grupo y revisión de trabajos según el área, con la nota de 1,0 a 5,0 anotada en su asignatura.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import re

import asignaturas
import aula
import horario
import periodos
import seguimiento
from nucleo import J


def subject_choices():
    return asignaturas.choices(J.settings["subjects"] or asignaturas.DEFAULT)


def _subjects_text():
    return J.settings["subjects"] or asignaturas.DEFAULT


def subjects_for(course):
    """Las asignaturas tuyas en ese curso: las de Ajustes (curso: asignaturas) y las de tu horario."""
    base = asignaturas.split(course)[0]
    out = []
    for c, subs in asignaturas.parse_course_subjects(J.settings["course_subjects"]).items():
        if aula.course_key(c) == aula.course_key(base):
            out += subs
    for x in horario.items:
        if x.get("materia") and aula.course_key(x.get("curso", "")) == aula.course_key(base):
            out.append(x["materia"])
    seen, res = set(), []
    for s in out:
        k = asignaturas.norm(asignaturas.area_of(s, _subjects_text()) or s)    # «Trigonometría» y «Matemáticas» = una área
        if k not in seen:
            seen.add(k)
            res.append(s)
    return res


def current_subject(course=""):
    """La asignatura que escogiste («estamos en tecnología») o, si estás en clase, la de tu horario."""
    now = horario.now_class()
    if now and now.get("materia") and (not course or aula.course_key(now.get("curso", "")) == aula.course_key(asignaturas.split(course)[0])):
        return now["materia"]
    return J.settings["subject_current"]


def grade_key(course, text="", ask=True, origin="AULA"):
    """La clave donde van las notas de ese curso: el curso o «curso · asignatura». None si preguntó cuál."""
    base, given = asignaturas.split(course)
    subs = subjects_for(base)
    if len(subs) < 2:
        return base if not given else course
    if given:
        return course
    s = asignaturas.find(text, subs, _subjects_text()) if text else None
    if not s:
        cur = current_subject(base)
        s = asignaturas.find(cur, subs, _subjects_text()) if cur else None
    if not s:
        if ask:
            J.reply(f"En {base} tienes {' y '.join(subs)}. ¿De cuál es? Dímelo con la asignatura, por ejemplo «ponle 4 a Juan en el taller "
                    f"de {subs[-1].split()[0].lower()} de {base}», o escoge la asignatura con «estamos en {subs[-1].split()[0].lower()}».", origin)
        return None
    return asignaturas.key(base, s, True)


def keys_of(course):
    """Todas las claves de notas de un curso (el curso y «curso · asignatura»)."""
    base = asignaturas.split(course)[0]
    ks = [k for k in set(seguimiento.data) | set(periodos.data) if asignaturas.split(k)[0] == base]
    return sorted(ks) or [base]


_SUBJ_SET = re.compile(r"^(?:jarvis\s+)?(?:estamos en|estoy en|vamos con|cambia a|cambiar a|pasa a|asignatura|area|selecciona)\s+(?:la\s+)?(?:clase de\s+|asignatura\s+|area\s+(?:de\s+)?)?(.+)$")
_SUBJ_ASK = re.compile(r"\b(?:en que|cual) (?:asignatura|area) (?:estamos|estoy|tengo)\b|\bque asignaturas? (?:tengo|doy|dicto)\b")


def subject_voice(text, t):
    if _SUBJ_ASK.search(t):
        cur = current_subject()
        J.reply((f"Estamos en {cur}. " if cur else "No has escogido asignatura. ") + "Tus áreas: " + "; ".join(
            a["area"] + (f" ({', '.join(x for x in a['asigs'] if x != a['area'])})" if len(a["asigs"]) > 1 else "")
            for a in asignaturas.parse(_subjects_text())) + ". Cámbiala con «estamos en tecnología».", "ASIGNATURA")
        return True
    m = _SUBJ_SET.match(t)
    if not m:
        return False
    s = asignaturas.find(m.group(1), subject_choices(), _subjects_text())
    if not s:
        return False                                   # «estamos en clase», «cambia a modo…»: no es una asignatura
    J.settings["subject_current"] = s
    try:
        J.save_settings_file()
    except OSError:
        pass
    J.socketio.emit("subject", {"subject": s})
    J.reply(f"Listo, estamos en {s}: las notas y las revisiones van a esa asignatura en los cursos donde das varias.", "ASIGNATURA")
    return True


@J.socketio.on("subjects_info")
def handle_subjects_info(data=None):
    d = data or {}
    if "set" in d:
        s = str(d["set"] or "").strip()
        J.settings["subject_current"] = s if (not s or s in subject_choices()) else J.settings["subject_current"]
        try:
            J.save_settings_file()
        except OSError:
            pass
    courses = sorted(aula.data.get("cursos", {}), key=aula.course_sort_key)
    return {"choices": subject_choices(), "current": J.settings["subject_current"], "now": current_subject(),
            "cursos": {c: subjects_for(c) for c in courses},
            "areas": asignaturas.parse(_subjects_text())}


# ============================================================================ REVISIÓN SEGÚN EL ÁREA
AREA_HINTS = {
    "matematicas": (" Es de Matemáticas: comprueba cada operación, el procedimiento y las unidades; un resultado correcto con un "
                    "procedimiento equivocado no es un acierto completo; un error de cálculo con buen razonamiento es parcial."),
    "tecnologia e informatica": (" Es de Tecnología e Informática: revisa el procedimiento, el uso correcto de herramientas y conceptos "
                                 "(algoritmos, diagramas de flujo, partes del computador, ofimática, programación por bloques o código), "
                                 "la lógica de las soluciones, la creatividad y la presentación."),
}


def area_hint(subject):
    ar = asignaturas.norm(asignaturas.area_of(subject, _subjects_text()) or subject)
    for k, v in AREA_HINTS.items():
        if k in ar or ar in k:
            return v
    return f" La asignatura es {subject}: evalúa con los criterios propios de esa área." if subject else ""


def propose_review_grade(course, estudiante, que, nota, subject=""):
    """Tras revisar: «¿Anoto 4,2 a Juan en Tecnología (7A)?» con tu aprobación."""
    if not (estudiante and nota is not None and course):
        return None
    key = asignaturas.key(asignaturas.split(course)[0], subject, len(subjects_for(course)) >= 2) if subject else \
        J.grade_key(course, que, ask=False)
    if not key:
        return None
    names = aula.students(key)
    name = estudiante if (not names or estudiante in names) else (aula.find_student(estudiante, names)[0] or estudiante)
    act = (que or "Trabajo revisado").strip()[:80]
    nota = max(1.0, min(5.0, round(float(nota), 1)))
    where = key.replace(asignaturas.SEP, ", ")
    return J.request_approval("nota", f"Anotar {str(nota).replace('.', ',')} a {name} en «{act}» ({where})",
                              f"Nota sugerida por la revisión (escala 1,0 a 5,0). Puedes corregirla diciendo «ponle … a {name}…».",
                              on_ok=lambda: (seguimiento.add(key, name, act, nota, origen="revision"),
                                             J.reply(f"Anotada: {str(nota).replace('.', ',')} a {name} en {act} ({where}).", "REVISION")),
                              on_no=lambda: J.reply("Vale, no la anoto.", "REVISION"), ttl=8 * 3600,
                              say=f"¿Anoto {str(nota).replace('.', ',')} a {name} en {act} ({where})? Di «sí» o «no».")


def areas_start():
    pass


__all__ = ['asignaturas', 'AREA_HINTS', '_SUBJ_ASK', '_SUBJ_SET', '_subjects_text', 'area_hint', 'areas_start', 'current_subject', 'grade_key',
           'handle_subjects_info', 'keys_of', 'propose_review_grade', 'subject_choices', 'subject_voice', 'subjects_for']
