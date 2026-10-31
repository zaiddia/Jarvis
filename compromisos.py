"""Compromisos y seguimiento (9.3): lo que prometiste hacer y los correos que te toca responder.

«Quedé en enviarle el taller a la coordinadora el viernes», «me comprometí a llamar a la mamá de Juan mañana»,
«¿qué compromisos tengo?», «ya le envié el taller a la coordinadora». Jarvis te recuerda lo que vence y lo que se
venció. Los correos importantes que piden respuesta («quedo atento», «¿podría…?») aparecen como «por responder» hasta
que los contestas con Jarvis o los descartas.
"""
import datetime
import json
import os
import re
import threading
import unicodedata
import uuid

import notas

_lock = threading.Lock()
_path = None
data = {"items": [], "respondidos": [], "descartados": []}

_TRIGGER = re.compile(r"^(?:(?:anota|apunta|registra)\s+(?:el|un|como)?\s*compromiso(?:\s+de)?:?\s+|(?:yo\s+)?(?:quede|me comprometi|prometi|"
                      r"me toca|tengo el compromiso de|debo cumplir con)\s+(?:en\s+|a\s+|con\s+)?)(.+)$")
_DONE = re.compile(r"^(?:ya\s+)(?:(?:se\s+)?(?:le|les|lo|la|los|las)\s+)?(?:cumpli(?: con)?|hice|envie|mande|entregue|llame|escribi|confirme|revise|pase|respondi|termine)\b\s*(.*)$")
_ASKS = re.compile(r"\b(?:quedo atent[oa]|quedamos atent[oa]s|agradezco (?:su|tu) respuesta|me confirma|nos confirma|por favor "
                   r"(?:confirm|envi|respond|indiqu)|podria(?:s)?\b|puede(?:s)? (?:enviar|confirmar|revisar)|necesito que|a la espera de "
                   r"(?:su|tu) respuesta|favor (?:confirmar|responder)|\?)")


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "compromisos.json")
    load()


def load():
    global data
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        data = d if isinstance(d, dict) else {}
    except (OSError, ValueError, TypeError):
        data = {}
    for k in ("items", "respondidos", "descartados"):
        data.setdefault(k, [])


def save():
    if not _path:
        return
    try:
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        with open(_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(_path + ".tmp", _path)
    except OSError:
        pass


def parse_voice(t):
    """«quede en enviarle el taller a la coordinadora el viernes» → texto del compromiso, o None."""
    m = _TRIGGER.match(t)
    return m.group(1).strip() if m and len(m.group(1).strip()) > 3 else None


def add(texto, origen="voz", now=None):
    texto = re.sub(r"\s+", " ", str(texto)).strip(" .,;")
    texto = texto[:1].upper() + texto[1:]
    fecha, hora = notas.parse_when(texto, now)
    it = {"id": uuid.uuid4().hex[:8], "texto": texto[:300], "fecha": fecha.isoformat() if fecha else "", "hora": hora,
          "origen": origen, "estado": "pendiente", "creado": (now or datetime.datetime.now()).isoformat(timespec="minutes")}
    with _lock:
        data["items"].append(it)
        save()
    return it


def pending():
    return [x for x in data["items"] if x["estado"] == "pendiente"]


def find(words):
    """El compromiso pendiente que más se parece a lo que dices."""
    w = {x for x in norm(words).split() if len(x) > 3}
    best, score = None, 0
    for x in pending():
        xw = set(norm(x["texto"]).split())
        stems = {y[:5] for y in xw}
        sc = sum(1 for y in w if y in xw or y[:5] in stems)
        if sc > score:
            best, score = x, sc
    return best if score else None


def done(cid):
    with _lock:
        for x in data["items"]:
            if x["id"] == cid:
                x["estado"] = "hecho"
                x["hecho"] = datetime.datetime.now().isoformat(timespec="minutes")
        save()


def status(x, today=None):
    """«vencido», «hoy», «mañana», «pronto» (≤ 7 días) o «sin fecha»."""
    today = today or datetime.date.today()
    if not x.get("fecha"):
        return "sin fecha"
    d = datetime.date.fromisoformat(x["fecha"])
    if d < today:
        return "vencido"
    if d == today:
        return "hoy"
    if d == today + datetime.timedelta(days=1):
        return "mañana"
    return "pronto" if (d - today).days <= 7 else "después"


def spoken(items, today=None):
    if not items:
        return "No tienes compromisos pendientes."
    parts = []
    for x in sorted(items, key=lambda x: (x["fecha"] or "9999", x["hora"]))[:8]:
        st = status(x, today)
        when = {"vencido": " (¡vencido!)", "hoy": " (hoy)", "mañana": " (mañana)"}.get(st, f" ({x['fecha'][8:10]}/{x['fecha'][5:7]})" if x["fecha"] else "")
        parts.append(x["texto"] + when)
    return f"Tienes {len(items)} compromiso{'s' if len(items) != 1 else ''}: " + "; ".join(parts) + "."


# ----------------------------------------------------------------------------- correos por responder
def asks_reply(m):
    """¿El correo te pide algo? (no masivo, y con una petición o pregunta)."""
    if m.get("masivo"):
        return False
    return bool(_ASKS.search(norm(m.get("asunto", "")) + " " + norm(str(m.get("texto", ""))[:1500]) + (" ?" if "?" in str(m.get("texto", ""))[:1500] else "")))


def to_answer(msgs, me=""):
    me = (me or "").lower()
    out = []
    for m in msgs:
        key = m.get("msgid") or f"{m.get('de')}|{m.get('asunto')}"
        if key in data["respondidos"] or key in data["descartados"] or (me and m.get("de", "").lower() == me):
            continue
        if asks_reply(m):
            out.append(m)
    return out


def mark_answered(m, discard=False):
    key = m.get("msgid") or f"{m.get('de')}|{m.get('asunto')}"
    with _lock:
        lst = data["descartados" if discard else "respondidos"]
        if key not in lst:
            lst.append(key)
            del lst[:-500]
        save()
