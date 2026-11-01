"""El momento del día del docente (11.8): el HUD se organiza distinto antes de clase, en clase, entre clases, después
de clases, en la noche (planear mañana) y en los días libres. Lógica pura.
"""
import datetime

TITLES = {"clase": "En clase", "preparar": "Prepárate", "inicio": "Antes de clases", "entre": "Entre clases", "cierre": "Después de clases",
          "noche": "Planear mañana", "libre": "Día libre", "jornada": "Jornada"}


def _at(now, hhmm):
    h, m = map(int, hhmm.split(":"))
    return datetime.datetime.combine(now.date(), datetime.time(h, m))


def moment(now, today_items, in_class=False, live_on=False, work_from=6, work_to=17):
    """→ {"id", "titulo", "siguiente": item o None, "en": minutos o None, "quedan": clases que faltan hoy}."""
    items = sorted(today_items or [], key=lambda x: x["inicio"])
    upcoming = [x for x in items if _at(now, x["inicio"]) > now]
    nxt = upcoming[0] if upcoming else None
    mins = int((_at(now, nxt["inicio"]) - now).total_seconds() // 60) if nxt else None
    started = [x for x in items if _at(now, x["inicio"]) <= now]
    base = {"siguiente": nxt, "en": mins, "quedan": len(upcoming)}
    if in_class or live_on:
        mid = "clase"
    elif now.hour >= max(work_to, 17) or now.hour < 5:
        mid = "libre" if now.weekday() in (4, 5) else "noche"     # viernes y sábado en la noche: descanso; domingo a jueves: mañana
    elif now.weekday() >= 5 and not items:
        mid = "libre"
    elif nxt and mins <= 20:
        mid = "preparar"
    elif nxt and not started:
        mid = "inicio"
    elif nxt:
        mid = "entre"
    elif items:
        mid = "cierre"
    else:
        mid = "jornada"
    return {"id": mid, "titulo": TITLES[mid], **base}
