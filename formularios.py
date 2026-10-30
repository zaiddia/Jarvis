"""Google Forms (8.1): el quiz de Jarvis como formulario autocalificable, y sus notas de vuelta al seguimiento.

Usa la misma conexión de Google que Classroom (con permiso para crear formularios y leer sus respuestas). El
formulario pide el correo del estudiante, así Jarvis sabe de quién es cada nota.
"""
import re

LETTERS = "abcd"


def create_body(quiz):
    t = (quiz.get("titulo") or "Evaluación")[:120]
    return {"info": {"title": t, "documentTitle": t}}


def batch_requests(quiz, points=1):
    """Peticiones de batchUpdate: modo quiz, pedir correo y una pregunta de opción múltiple por cada una."""
    reqs = [{"updateSettings": {"settings": {"quizSettings": {"isQuiz": True}, "emailCollectionType": "VERIFIED"},
                                "updateMask": "quizSettings.isQuiz,emailCollectionType"}},
            {"updateFormInfo": {"info": {"description": (quiz.get("instrucciones") or "")[:900]}, "updateMask": "description"}}]
    for i, q in enumerate(quiz.get("preguntas") or []):
        opts = [str(o)[:500] for o in q["opciones"]]
        k = LETTERS.find(str(q.get("respuesta", "a"))[:1].lower())
        correct = opts[k if 0 <= k < len(opts) else 0]
        item = {"title": str(q["enunciado"])[:1000],
                "questionItem": {"question": {"required": True, "grading": {
                    "pointValue": points, "correctAnswers": {"answers": [{"value": correct}]},
                    **({"whenWrong": {"text": str(q["explicacion"])[:900]}} if q.get("explicacion") else {})},
                    "choiceQuestion": {"type": "RADIO", "options": [{"value": o} for o in _unique(opts)], "shuffle": True}}}}
        reqs.append({"createItem": {"item": item, "location": {"index": i}}})
    return reqs


def _unique(opts):
    """Forms no acepta opciones repetidas."""
    out, seen = [], set()
    for o in opts:
        v = o
        while v.lower() in seen:
            v += " "
        seen.add(v.lower())
        out.append(v)
    return out


def scores(responses, max_points):
    """{correo: nota 1.0-5.0} con la última respuesta de cada estudiante."""
    from classroom import to_scale
    best = {}
    for r in sorted(responses, key=lambda r: r.get("lastSubmittedTime", "")):
        mail = (r.get("respondentEmail") or "").strip().lower()
        if mail and r.get("totalScore") is not None:
            best[mail] = to_scale(r["totalScore"], max_points)
        elif mail and "totalScore" not in r:
            best[mail] = to_scale(0, max_points)
    return best


def match_names(by_mail, roster):
    """roster {correo: nombre}. Devuelve ({nombre: nota}, [correos sin estudiante])."""
    out, unknown = {}, []
    for mail, nota in by_mail.items():
        name = roster.get(mail)
        if name:
            out[name] = nota
        else:
            unknown.append(mail)
    return out, unknown


_FORMS_RE = re.compile(r"\b(?:google\s+)?(?:forms?|formulario)\b")


def is_forms(t):
    return bool(_FORMS_RE.search(t))
