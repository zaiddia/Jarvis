"""Horario de clases (8.1): Jarvis sabe qué curso tienes a cada hora.

Se escribe una clase por línea en Ajustes › Memoria › Horario («lunes 7:00-7:55 7A Matemáticas») o por voz
(«los lunes de 7 a 8 tengo 7A matemáticas»). Con el horario: «¿qué clase tengo ahora?», «¿cuál es mi próxima
clase?», «mi horario de hoy», «prepárame la próxima clase» y el curso activo del aula cambia solo.
"""
import datetime
import json
import os
import re
import threading
import unicodedata

DAYS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
_lock = threading.Lock()
_path = None
items = []          # [{"dia": 0-6, "inicio": "07:00", "fin": "07:55", "curso": "7A", "materia": "Matemáticas"}]


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "horario.json")
    load()


def load():
    global items
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        items = [x for x in d if isinstance(x, dict) and "dia" in x] if isinstance(d, list) else []
    except (OSError, ValueError, TypeError):
        items = []


def save():
    if not _path:
        return
    with _lock:
        try:
            os.makedirs(os.path.dirname(_path), exist_ok=True)
            with open(_path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=1)
            os.replace(_path + ".tmp", _path)
        except OSError:
            pass


def _hhmm(h, m=None, ampm=""):
    h, m = int(h), int(m or 0)
    if ampm.startswith("p") and h < 12:
        h += 12
    elif not ampm and 1 <= h <= 5:          # «de 1 a 2» en un colegio es por la tarde
        h += 12
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError
    return f"{h:02d}:{m:02d}"


_TIME = r"(\d{1,2})(?:[:.h](\d{2}))?\s*(a\.?\s?m\.?|p\.?\s?m\.?|am|pm)?"
_LINE = re.compile(rf"^\s*(?:los\s+|el\s+)?({'|'.join(DAYS)})s?\s+(?:de\s+)?{_TIME}\s*(?:-|a|hasta)\s*{_TIME}\s+(?:tengo\s+)?(.+?)\s*$")


def parse_line(line):
    """«lunes 7:00-7:55 7A Matemáticas» → item. None si no se entiende."""
    m = _LINE.match(norm(line).replace("–", "-"))
    if not m:
        return None
    day, h1, m1, a1, h2, m2, a2, rest = m.groups()
    try:
        ini, fin = _hhmm(h1, m1, (a1 or "").replace(".", "").replace(" ", "")), _hhmm(h2, m2, (a2 or a1 or "").replace(".", "").replace(" ", ""))
    except ValueError:
        return None
    if fin <= ini:
        return None
    orig = re.sub(r"^.*?\d{1,2}(?:[:.h]\d{2})?\s*(?:[ap]\.?\s?m\.?)?\s*(?:-|–|a|hasta)\s*\d{1,2}(?:[:.h]\d{2})?\s*(?:[ap]\.?\s?m\.?)?\s+(?:tengo\s+)?",
                  "", line.strip(), count=1, flags=re.I)
    parts = (orig or rest).split(None, 1)
    curso = parts[0].upper() if re.match(r"^\d{1,2}[a-zA-Z]?$|^\d{1,2}-?\d$", parts[0]) else ""
    materia = (parts[1] if curso and len(parts) > 1 else ("" if curso else orig or rest)).strip()
    return {"dia": DAYS.index(day), "inicio": ini, "fin": fin, "curso": curso, "materia": materia[:60]}


def parse_text(text):
    """Todas las líneas del cuadro de Ajustes. Devuelve (items, líneas que no entendí)."""
    out, bad = [], []
    for line in str(text).splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        it = parse_line(line)
        (out.append(it) if it else bad.append(line.strip()))
    return sorted(out, key=lambda x: (x["dia"], x["inicio"])), bad


def to_text(lst=None):
    return "\n".join(f"{DAYS[x['dia']]} {x['inicio']}-{x['fin']} {x['curso']} {x['materia']}".replace("  ", " ").strip()
                     for x in sorted(lst if lst is not None else items, key=lambda x: (x["dia"], x["inicio"])))


def set_all(lst):
    global items
    items = list(lst)
    save()


def add(it):
    items[:] = [x for x in items if not (x["dia"] == it["dia"] and x["inicio"] == it["inicio"])] + [it]
    items.sort(key=lambda x: (x["dia"], x["inicio"]))
    save()


def now_class(at=None):
    at = at or datetime.datetime.now()
    hm = at.strftime("%H:%M")
    for x in items:
        if x["dia"] == at.weekday() and x["inicio"] <= hm < x["fin"]:
            return x
    return None


def next_class(at=None):
    """(item, fecha) de la próxima clase que aún no ha empezado."""
    at = at or datetime.datetime.now()
    for d in range(0, 8):
        day = (at + datetime.timedelta(days=d)).date()
        for x in sorted((x for x in items if x["dia"] == day.weekday()), key=lambda x: x["inicio"]):
            if d > 0 or x["inicio"] > at.strftime("%H:%M"):
                return x, day
    return None, None


def today(at=None):
    at = at or datetime.datetime.now()
    return sorted((x for x in items if x["dia"] == at.weekday()), key=lambda x: x["inicio"])


def label(x):
    return " ".join(p for p in (x["curso"], x["materia"]) if p) or "clase"


def spoken_day(lst, when="hoy"):
    if not lst:
        return f"No tienes clases {when}."
    return f"{when.capitalize()} tienes {len(lst)} clase{'s' if len(lst) != 1 else ''}: " + "; ".join(
        f"{label(x)} de {x['inicio']} a {x['fin']}" for x in lst) + "."
