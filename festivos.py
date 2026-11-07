"""Calendario escolar (12.12): festivos de Colombia, recesos, cierres de periodo y entregas. Lógica pura.

Los festivos se calculan con la ley colombiana (Ley 51 de 1983, «Ley Emiliani»): los fijos que no se mueven, los que pasan
al lunes siguiente y los que dependen de la Semana Santa. No necesita internet.
Lo del colegio (recesos, cierres, entregas a coordinación, reuniones) lo agregas tú: «semana de receso del 6 al 10 de
octubre», «entrega de notas a coordinación el 20 de noviembre».
"""
import datetime
import json
import os
import re
import threading
import unicodedata
import uuid

_lock = threading.Lock()
_path = None
data = {"eventos": []}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
DIAS_TXT = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
TIPOS = {"receso": "Receso", "cierre": "Cierre de periodo", "entrega": "Entrega", "reunion": "Reunión", "izada": "Izada de bandera",
         "evento": "Evento"}


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s/]", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


# ----------------------------------------------------------------------------- festivos
def easter(year):
    """Domingo de Pascua (algoritmo gregoriano anónimo)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return datetime.date(year, month, day)


def _monday(d):
    return d + datetime.timedelta(days=(7 - d.weekday()) % 7)


def holidays(year):
    """{fecha: nombre} de los festivos de Colombia de ese año."""
    D = datetime.date
    out = {D(year, 1, 1): "Año Nuevo", D(year, 5, 1): "Día del Trabajo", D(year, 7, 20): "Día de la Independencia",
           D(year, 8, 7): "Batalla de Boyacá", D(year, 12, 8): "Inmaculada Concepción", D(year, 12, 25): "Navidad"}
    for (m, d), name in (((1, 6), "Reyes Magos"), ((3, 19), "San José"), ((6, 29), "San Pedro y San Pablo"), ((8, 15), "Asunción de la Virgen"),
                         ((10, 12), "Día de la Raza"), ((11, 1), "Todos los Santos"), ((11, 11), "Independencia de Cartagena")):
        out[_monday(D(year, m, d))] = name
    e = easter(year)
    td = datetime.timedelta
    out[e - td(days=3)] = "Jueves Santo"
    out[e - td(days=2)] = "Viernes Santo"
    out[_monday(e + td(days=39))] = "Ascensión del Señor"
    out[_monday(e + td(days=60))] = "Corpus Christi"
    out[_monday(e + td(days=68))] = "Sagrado Corazón"
    return dict(sorted(out.items()))


def holiday(d):
    """Nombre del festivo de ese día, o ""."""
    return holidays(d.year).get(d, "")


def next_holidays(today, n=3):
    out = []
    for y in (today.year, today.year + 1):
        out += [(d, name) for d, name in holidays(y).items() if d >= today]
    return out[:n]


# ----------------------------------------------------------------------------- fechas dichas
def parse_date(text, today):
    """«hoy», «mañana», «pasado mañana», «el lunes», «el 20 de noviembre», «20/11» → fecha o None (la próxima vez que llegue)."""
    t = norm(text)
    if re.search(r"\bpasado manana\b", t):
        return today + datetime.timedelta(days=2)
    if re.search(r"\bmanana\b", t):
        return today + datetime.timedelta(days=1)
    if re.search(r"\bhoy\b", t):
        return today
    m = re.search(r"\b(\d{1,2})\s+de\s+(" + "|".join(MESES) + r")(?:\s+(?:de|del)\s+(\d{4}))?", t)
    if m:
        y = int(m.group(3)) if m.group(3) else today.year
        try:
            d = datetime.date(y, MESES.index(m.group(2)) + 1, int(m.group(1)))
        except ValueError:
            return None
        return d if m.group(3) or d >= today - datetime.timedelta(days=60) else d.replace(year=y + 1)
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    if m:
        y = int(m.group(3)) if m.group(3) else today.year
        y = y + 2000 if y < 100 else y
        try:
            return datetime.date(y, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"\b(?:el\s+)?(?:proximo\s+)?(" + "|".join(DIAS) + r")\b", t)
    if m:
        delta = (DIAS.index(m.group(1)) - today.weekday()) % 7
        return today + datetime.timedelta(days=delta or 7)
    return None


def parse_range(text, today):
    """«del 6 al 10 de octubre», «del 28 de septiembre al 2 de octubre» → (desde, hasta) o None."""
    t = norm(text)
    m = re.search(r"\bdel?\s+(\d{1,2})(?:\s+de\s+(" + "|".join(MESES) + r"))?\s+al?\s+(\d{1,2})\s+de\s+(" + "|".join(MESES) + r")", t)
    if not m:
        return None
    m2 = MESES.index(m.group(4)) + 1
    m1 = MESES.index(m.group(2)) + 1 if m.group(2) else m2
    y = today.year
    try:
        a, b = datetime.date(y, m1, int(m.group(1))), datetime.date(y, m2, int(m.group(3)))
    except ValueError:
        return None
    if b < today - datetime.timedelta(days=60):
        a, b = a.replace(year=y + 1), b.replace(year=y + 1)
    return (a, b) if a <= b else None


def spoken(d, today=None):
    today = today or datetime.date.today()
    if d == today:
        return "hoy"
    if d == today + datetime.timedelta(days=1):
        return "mañana"
    return f"el {DIAS_TXT[d.weekday()]} {d.day} de {MESES[d.month - 1]}"


# ----------------------------------------------------------------------------- calendario del colegio
def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "calendario_escolar.json")
    load()


def load():
    global data
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        data = d if isinstance(d, dict) and isinstance(d.get("eventos"), list) else {"eventos": []}
    except (OSError, ValueError, TypeError):
        data = {"eventos": []}


def save():
    if not _path:
        return
    with _lock:
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        with open(_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(_path + ".tmp", _path)


def kind_of(text):
    t = norm(text)
    for k, rx in (("receso", r"\b(?:receso|vacaciones|semana de desarrollo|semana institucional|sin clases)\b"),
                  ("cierre", r"\bcierre\b|\bfin del periodo\b|\bterminan? el periodo\b"),
                  ("entrega", r"\bentrega\b|\bentregar\b|\bplazo\b"), ("reunion", r"\breunion\b|\bconsejo\b|\bcomite\b|\bescuela de padres\b"),
                  ("izada", r"\bizada\b")):
        if re.search(rx, t):
            return k
    return "evento"


def add_event(titulo, desde, hasta=None, tipo=None):
    ev = {"id": uuid.uuid4().hex[:8], "titulo": str(titulo).strip()[:120], "tipo": tipo or kind_of(titulo), "desde": desde.isoformat(),
          "hasta": (hasta or desde).isoformat(), "avisos": []}
    data["eventos"].append(ev)
    data["eventos"].sort(key=lambda e: e["desde"])
    save()
    return ev


def remove_event(text):
    n = norm(text)
    hit = next((e for e in data["eventos"] if n and n in norm(e["titulo"])), None)
    if hit:
        data["eventos"].remove(hit)
        save()
    return hit


def events_between(a, b):
    return [e for e in data["eventos"] if e["desde"] <= b.isoformat() and e["hasta"] >= a.isoformat()]


def day_info(d):
    """Lo que tiene ese día: (festivo, [eventos]). Sirve para «¿mañana hay clase?»."""
    return holiday(d), events_between(d, d)


def no_class(d):
    """El motivo por el que ese día no hay clase ("" si sí hay): fin de semana, festivo o receso."""
    if d.weekday() >= 5:
        return "es fin de semana"
    h = holiday(d)
    if h:
        return f"es festivo ({h})"
    rec = next((e for e in events_between(d, d) if e["tipo"] == "receso"), None)
    return f"hay {rec['titulo'].lower()}" if rec else ""


def describe(e, today=None):
    a, b = datetime.date.fromisoformat(e["desde"]), datetime.date.fromisoformat(e["hasta"])
    when = spoken(a, today) if a == b else f"del {a.day} de {MESES[a.month - 1]} al {b.day} de {MESES[b.month - 1]}"
    return f"{e['titulo']} {when}"


def to_warn(today):
    """Avisos de hoy: festivo o receso mañana, y eventos del colegio en 3 días y el mismo día. Los marca como dados."""
    out = []
    tomorrow = today + datetime.timedelta(days=1)
    reason = no_class(tomorrow)
    if reason and tomorrow.weekday() < 5:
        out.append(f"Mañana no hay clase: {reason}.")
    for e in data["eventos"]:
        a = datetime.date.fromisoformat(e["desde"])
        left = (a - today).days
        key = today.isoformat()
        if left in (3, 0) and e["tipo"] != "receso" and key not in e.get("avisos", []):
            e.setdefault("avisos", []).append(key)
            out.append(f"{'Hoy' if left == 0 else 'En 3 días'}: {e['titulo']}.")
    if out:
        save()
    return out
