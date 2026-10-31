"""Vigilante de páginas web (9.4): «avísame cuando publiquen algo nuevo en https://…».

Jarvis revisa la página cada cierto tiempo (6 horas por defecto), compara su texto con la vez anterior y, si aparece
contenido nuevo, te avisa con lo nuevo (resumido por la IA si está conectada). Sirve para circulares de la Secretaría de
Educación, convocatorias, noticias del colegio o cualquier página pública.
"""
import datetime
import hashlib
import json
import os
import re
import threading
import uuid

_lock = threading.Lock()
_path = None
items = []          # [{"id", "url", "nombre", "horas", "lineas": [hash], "ultima", "cambio", "creado"}]
MAX = 20


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "paginas_vigiladas.json")
    load()


def load():
    global items
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        items = d if isinstance(d, list) else []
    except (OSError, ValueError, TypeError):
        items = []


def save():
    if not _path:
        return
    try:
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        with open(_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
        os.replace(_path + ".tmp", _path)
    except OSError:
        pass


def _lines(text):
    """Frases con contenido (sin números que cambian solos, como fechas y contadores de visitas)."""
    out = []
    for ln in re.split(r"(?<=[.!?])\s+|\n+", str(text)):
        ln = re.sub(r"\s+", " ", ln).strip()
        if len(ln) >= 25:
            out.append(ln)
    return out


def _key(line):
    return hashlib.sha1(re.sub(r"\d+", "#", line.lower()).encode("utf-8")).hexdigest()[:12]


def add(url, nombre="", horas=6):
    with _lock:
        for x in items:
            if x["url"] == url:
                return x, False
        it = {"id": uuid.uuid4().hex[:6], "url": url, "nombre": nombre or url.split("//")[-1].split("/")[0], "horas": horas,
              "lineas": [], "ultima": "", "cambio": "", "creado": datetime.date.today().isoformat()}
        items.append(it)
        del items[:-MAX]
        save()
    return it, True


def remove(words):
    w = re.sub(r"[\W_]+", "", str(words).lower())
    with _lock:
        for x in items:
            if w and (w in re.sub(r"[\W_]+", "", x["nombre"].lower()) or w in re.sub(r"[\W_]+", "", x["url"].lower())):
                items.remove(x)
                save()
                return x
    return None


def due(now=None):
    now = now or datetime.datetime.now()
    out = []
    for x in items:
        if not x["ultima"]:
            out.append(x)
            continue
        last = datetime.datetime.fromisoformat(x["ultima"])
        if (now - last).total_seconds() >= x["horas"] * 3600:
            out.append(x)
    return out


def check(item, text, now=None):
    """Compara el texto nuevo con el guardado. Devuelve las frases nuevas (la primera vez, [] y solo guarda)."""
    now = now or datetime.datetime.now()
    lines = _lines(text)
    keys = [_key(ln) for ln in lines]
    first = not item["lineas"]
    old = set(item["lineas"])
    new = [ln for ln, k in zip(lines, keys) if k not in old]
    with _lock:
        item["lineas"] = keys[:3000]
        item["ultima"] = now.isoformat(timespec="minutes")
        if new and not first:
            item["cambio"] = now.isoformat(timespec="minutes")
        save()
    if first:
        return []
    return new if len(new) >= 1 else []


def summary_prompt(nombre, new_lines):
    return (f"En la página «{nombre}» apareció este texto nuevo. Resume en 1 a 3 frases, en español y sin inventar nada, qué "
            "publicaron de nuevo (si es solo un cambio menor de menús o fechas, dilo en una frase):\n" + "\n".join(new_lines[:40])[:5000])
