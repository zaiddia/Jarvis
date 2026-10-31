"""Personalidad según el momento y color del día del reactor (9.9). Lógica pura, sin Jarvis.

· Personalidad: en clase, Jarvis es breve y claro (lo escuchan los estudiantes); en la jornada, concentrado y
  eficiente; en la tarde, la noche y el fin de semana, cálido y relajado. Se puede fijar a mano.
· Color del día: el reactor (HUD y orbe de la barra de tareas) cambia de color según cómo viene el día:
  tranquilo (el color de tu tema), cargado (ámbar), urgente (coral) o de celebración (verde).
"""
import re

MODES = {
    "clase": ("de clase", " MODO CLASE: estás en clase y te escuchan los estudiantes. Responde muy breve y claro, en lenguaje "
                          "sencillo y respetuoso, sin chistes ni temas personales del docente."),
    "jornada": ("concentrado", " MODO JORNADA: es horario de trabajo. Ve al grano, sé eficiente y concreto; nada de charla."),
    "relajado": ("relajado", " MODO RELAJADO: es tiempo libre del docente. Puedes ser más cálido y cercano, con algo de humor "
                             "suave, sin dejar de ser útil. Si pide trabajo, ayúdale, pero no le recuerdes pendientes sin que pregunte."),
}
_SET = re.compile(r"\b(?:ponte|personalidad|actitud|pon la personalidad|cambia la personalidad a)\s+(?:de\s+|en\s+|a\s+)?"
                  r"(serio|seria|formal|concentrado|concentrada|trabajo|jornada|relajado|relajada|descansado|tranquilo|tranquila|clase|"
                  r"automatico|automatica|auto)\b|\bmodo (serio|formal|relajado|relajada)\b|\b(?:vuelve a la )?personalidad automatica\b")
_ALIAS = {"seria": "jornada", "concentrada": "jornada", "tranquila": "relajado", "serio": "jornada", "formal": "jornada", "concentrado": "jornada", "concentracion": "jornada", "trabajo": "jornada",
          "jornada": "jornada", "relajado": "relajado", "relajada": "relajado", "descansado": "relajado", "tranquilo": "relajado",
          "clase": "clase", "automatico": "auto", "automatica": "auto", "auto": "auto"}


def parse_set(t):
    """«ponte relajado» → "relajado"; «modo automático» → "auto"; None si no es eso."""
    m = _SET.search(t)
    if not m:
        return None
    return _ALIAS.get(m.group(1) or m.group(2) or "auto", "auto")


def auto_mode(now, in_class, work_from=6, work_to=17):
    if in_class:
        return "clase"
    if now.weekday() >= 5 or not (work_from <= now.hour < work_to):
        return "relajado"
    return "jornada"


# ----------------------------------------------------------------------------- color del día
MOODS = {"tranquilo": None, "cargado": (255, 176, 46), "urgente": (255, 107, 74), "celebracion": (95, 211, 138)}
LABELS = {"tranquilo": "día tranquilo", "cargado": "día cargado", "urgente": "hay algo urgente", "celebracion": "día de celebrar"}


def day_mood(items, celebrate=False):
    """items: los de «¿qué necesita mi atención?» (con prioridad p). → (ánimo, motivo)."""
    urgent = [x for x in items if x.get("p") == 1 and re.match(r"(?:se venció|atrasado|en \d+ min)", x.get("t", ""))]
    if urgent:
        return "urgente", urgent[0]["t"]
    if len(items) >= 4 or sum(1 for x in items if x.get("p") == 1) >= 2:
        return "cargado", f"{len(items)} cosas pendientes"
    if celebrate:
        return "celebracion", celebrate if isinstance(celebrate, str) else "algo para celebrar"
    return "tranquilo", "todo en orden"


def hexrgb(rgb):
    return "%02x%02x%02x" % tuple(rgb)
