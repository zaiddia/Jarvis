"""Turno de noche (12.0): lo que Jarvis deja listo mientras duermes. Lógica pura, sin Jarvis.

Cuándo toca, qué clases hay al día siguiente, qué nota proponer por un procedimiento revisado y el resumen de los
buenos días («te dejé lista la clase de 10A, califiqué 23 entregas y hay 2 mensajes por aprobar»).
"""
import datetime


def next_school_day(today, has_classes):
    """El siguiente día (desde mañana) con clases en el horario; si no hay horario, mañana si es entre semana."""
    for d in range(1, 8):
        day = today + datetime.timedelta(days=d)
        if has_classes(day):
            return day
    day = today + datetime.timedelta(days=1)
    while day.weekday() >= 5:
        day += datetime.timedelta(days=1)
    return day


def due(now, enabled, hour, last_run, first_class_today=None):
    """→ "noche" (toca el turno de la noche), "madrugada" (el equipo estaba apagado: se hace temprano para HOY) o "".
    last_run: la fecha (iso) de la noche que ya se trabajó."""
    if not enabled:
        return ""
    today = now.date().isoformat()
    if now.hour >= hour and last_run != today:
        return "noche"
    yesterday = (now.date() - datetime.timedelta(days=1)).isoformat()
    if 4 <= now.hour < 12 and last_run not in (yesterday, today) and first_class_today:
        start = datetime.datetime.combine(now.date(), datetime.time(*map(int, first_class_today.split(":"))))
        if (start - now).total_seconds() >= 25 * 60:
            return "madrugada"
    return ""


def classes_for(items, day):
    """Las clases de ese día, sin repetir curso y asignatura: [(curso, materia, inicio)]."""
    seen, out = set(), []
    for x in sorted((x for x in items if x.get("dia") == day.weekday()), key=lambda x: x.get("inicio", "")):
        k = (x.get("curso", ""), x.get("materia", ""))
        if k in seen or not (k[0] or k[1]):
            continue
        seen.add(k)
        out.append((x.get("curso", ""), x.get("materia", ""), x.get("inicio", "")))
    return out


def grade_from_review(res, scale_min=1.0, scale_max=5.0):
    """Nota propuesta por un procedimiento revisado: todo bien = la máxima; un error tarde vale más que uno al comienzo.
    → nota (float con un decimal) o None si no se pudo leer."""
    if not res or not res.get("legible"):
        return None
    pasos = max(1, len(res.get("pasos") or []))
    err = res.get("error")
    span = scale_max - scale_min
    if not err:
        if res.get("respuesta_ok") is False:
            return round(scale_min + span * 0.7, 1)
        return round(scale_max, 1)
    avance = max(0, err.get("paso", 1) - 1) / pasos           # qué tanto llevaba bien antes de equivocarse
    return round(scale_min + span * (0.3 + 0.45 * avance), 1)


def morning_line(rep, name=""):
    """La frase de los buenos días a partir del informe de la noche."""
    if not rep:
        return ""
    parts = []
    clases = rep.get("clases") or []
    if clases:
        cs = [c for c in clases if c.get("ok")]
        if cs:
            names = [c["curso"] or c["materia"] for c in cs]
            parts.append("te dejé lista la clase de " + _join(names) if len(names) <= 3 else f"te dejé listas {len(names)} clases ({_join(names[:3])}…)")
    n = rep.get("calificadas", 0)
    if n:
        parts.append(f"califiqué {n} entrega{'s' if n != 1 else ''}")
    m = rep.get("mensajes", 0)
    ap = rep.get("aprobar", 0)
    if ap:
        parts.append(f"hay {ap} cosa{'s' if ap != 1 else ''} por aprobar" + (f" ({m} mensaje{'s' if m != 1 else ''} a padres)" if m else ""))
    if not parts:
        return ""
    head = "Buenos días" + (f", {name}" if name else "") + ": " if rep.get("hola", True) else ""
    t = head + _join(parts) + "."
    fails = rep.get("fallos") or []
    if fails:
        t += f" No pude con: {_join(fails[:3])}."
    return t[0].upper() + t[1:]


def _join(xs):
    xs = [str(x) for x in xs if str(x)]
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " y " + xs[-1] if xs else ""
