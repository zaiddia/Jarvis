"""¿Qué necesita mi atención? (9.3): todo lo urgente en una lista priorizada, y el «pulso» que avisa de lo nuevo.

Cada cosa es {"k": clave única, "p": prioridad 1 (ya) a 3 (pronto), "t": texto, "cmd": orden para atenderla}.
"""


def order(items):
    return sorted(items, key=lambda x: (x["p"], x["t"]))


def spoken(items, limit=7):
    if not items:
        return "Nada urgente: todo está al día. 👌"
    items = order(items)
    now = [x for x in items if x["p"] == 1]
    txt = (f"Tienes {len(items)} cosa{'s' if len(items) != 1 else ''} pendiente{'s' if len(items) != 1 else ''}"
           + (f", {len(now)} para ya" if now else "") + ": ")
    txt += "; ".join(f"{i + 1}) {x['t']}" for i, x in enumerate(items[:limit]))
    if len(items) > limit:
        txt += f"; y {len(items) - limit} más en el panel Hoy"
    return txt + "."


def new_items(items, seen):
    """Las importantes (prioridad 1) que no se habían avisado."""
    return [x for x in order(items) if x["p"] == 1 and x["k"] not in seen]
