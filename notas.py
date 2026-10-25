"""Memoria personal de Jarvis: notas y pendientes, con fecha y hora opcionales.

«recuerda que la reunión de padres es el jueves a las 3»  -> nota para el jueves 15:00
«¿qué tengo pendiente?» / «¿qué tengo mañana?»           -> lista
«ya hice lo de la reunión»                               -> marcada como hecha

Se guarda en notas.json, en la carpeta de configuración (solo en tu equipo).
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
notes = []          # [{id, texto, creado, fecha (AAAA-MM-DD|""), hora (HH:MM|""), hecho, avisado}]

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
_WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
_MONTHS = {normalize_m: i + 1 for i, normalize_m in enumerate(
    ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
     "septiembre", "octubre", "noviembre", "diciembre"])}
_MONTHS["setiembre"] = 9
_HOUR_WORDS = {"una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
               "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12}
_DAY_WORDS = {**_HOUR_WORDS, "primero": 1, "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16,
              "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21,
              "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
              "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
              "treinta": 30, "treinta y uno": 31}


def normalize(text):
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s:/]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------------------
# Guardado
# ---------------------------------------------------------------------------
def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "notas.json")
    load()


def load():
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, list):
            notes[:] = [n for n in d if isinstance(n, dict) and n.get("texto")]
    except (FileNotFoundError, ValueError, OSError, TypeError):
        pass


def save():
    if not _path:
        return
    os.makedirs(os.path.dirname(_path), exist_ok=True)
    tmp = _path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path)


# ---------------------------------------------------------------------------
# Fechas habladas en español
# ---------------------------------------------------------------------------
def _num(word):
    w = normalize(word)
    return int(w) if w.isdigit() else _DAY_WORDS.get(w)


def parse_when(text, now=None):
    """Busca un día y/o una hora en la frase. Devuelve (fecha|None, "HH:MM"|"").
    Entiende: hoy, mañana, pasado mañana, el jueves, el próximo lunes, el 15 de noviembre,
    15/11, a las 3, a las 3 y media, a las 10:30 de la mañana, al mediodía."""
    now = now or datetime.datetime.now()
    today = now.date()
    t = normalize(text)
    date = None

    if re.search(r"\bpasado manana\b", t):
        date = today + datetime.timedelta(days=2)
    elif re.search(r"(?<!de la )(?<!por la )\bmanana\b", t):
        date = today + datetime.timedelta(days=1)
    elif re.search(r"\b(?:hoy|esta tarde|esta noche|esta manana)\b", t):
        date = today

    m = re.search(r"\b(?:el |este |esta |proximo |el proximo |la proxima semana el )?"
                  r"(lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b", t)
    if m and date is None:
        wd = _WEEKDAYS[m.group(1)]
        ahead = (wd - today.weekday()) % 7
        if ahead == 0 and re.search(r"\b(?:proximo|proxima semana)\b", t):
            ahead = 7
        date = today + datetime.timedelta(days=ahead)

    m = re.search(r"\b(?:el )?(\d{1,2}|" + "|".join(sorted(_DAY_WORDS, key=len, reverse=True)) +
                  r") de (" + "|".join(_MONTHS) + r")(?: de (\d{4}))?\b", t)
    if m:
        d, mo = _num(m.group(1)), _MONTHS[m.group(2)]
        y = int(m.group(3)) if m.group(3) else today.year
        try:
            cand = datetime.date(y, mo, d)
            if not m.group(3) and cand < today:
                cand = datetime.date(y + 1, mo, d)
            date = cand
        except (TypeError, ValueError):
            pass
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    if m and date is None:
        try:
            y = int(m.group(3)) if m.group(3) else today.year
            y = y + 2000 if y < 100 else y
            cand = datetime.date(y, int(m.group(2)), int(m.group(1)))
            if not m.group(3) and cand < today:
                cand = datetime.date(y + 1, cand.month, cand.day)
            date = cand
        except ValueError:
            pass

    hora, midnight = "", False
    if re.search(r"\b(?:al|a) mediodia\b", t):
        hora = "12:00"
    m = re.search(r"\ba la(?:s)? (\d{1,2}|" + "|".join(_HOUR_WORDS) + r")"
                  r"(?::(\d{2})| y (media|cuarto)| y (\d{1,2}))?"
                  r"(?:\s*(am|pm|a m|p m|de la manana|de la tarde|de la noche|del mediodia))?\b", t)
    if m:
        h = _num(m.group(1))
        if h is not None and 0 <= h <= 23:
            mins = int(m.group(2)) if m.group(2) else 30 if m.group(3) == "media" else \
                15 if m.group(3) == "cuarto" else int(m.group(4)) if m.group(4) else 0
            suf = m.group(5) or ""
            if h == 12 and suf == "de la noche":   # «las doce de la noche» = medianoche, al final de ese día
                h, midnight = 0, True
            elif suf in ("pm", "p m", "de la tarde", "de la noche", "del mediodia") and h < 12:
                h += 12
            elif suf in ("am", "a m", "de la manana") and h == 12:
                h = 0
            elif not suf and 1 <= h <= 6:
                h += 12               # «a las 3» en un día de trabajo casi siempre es de la tarde
            if 0 <= mins < 60:
                hora = f"{h:02d}:{mins:02d}"
    if midnight and date is not None:
        date += datetime.timedelta(days=1)
    elif midnight:
        date = today + datetime.timedelta(days=1)
    if hora and date is None:         # solo hora: hoy si aún no ha pasado, si no mañana
        hh, mm = map(int, hora.split(":"))
        date = today if (hh, mm) > (now.hour, now.minute) else today + datetime.timedelta(days=1)
    return date, hora


def when_spoken(n, today=None, with_day=True):
    """«hoy a las 3 de la tarde», «el jueves 30 de octubre», «» si no tiene fecha.
    with_day=False: solo la hora (cuando ya se dijo «hoy tienes…»)."""
    if not n.get("fecha"):
        return ""
    today = today or datetime.date.today()
    d = datetime.date.fromisoformat(n["fecha"])
    delta = (d - today).days
    if delta == 0:
        dia = "hoy"
    elif delta == 1:
        dia = "mañana"
    elif delta == -1:
        dia = "ayer"
    elif 1 < delta < 7:
        dia = f"el {DIAS[d.weekday()]}"
    else:
        dia = f"el {DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"
    if n.get("hora"):
        h, m = map(int, n["hora"].split(":"))
        franja = "de la mañana" if h < 12 else "del mediodía" if h == 12 else "de la tarde" if h < 19 else "de la noche"
        h12 = h if h <= 12 else h - 12
        h12 = 12 if h12 == 0 else h12
        minutos = "" if m == 0 else " y media" if m == 30 else f" y {m}"
        dia += f" a las {h12}{minutos} {franja}" if h12 != 1 else f" a la una{minutos} {franja}"
    if not with_day:
        return dia.split(" ", 1)[1] if " a la" in dia else ""
    return dia


_WHEN_RE = re.compile(
    r"\b(?:pasado\s+ma[ñn]ana|ma[ñn]ana(?!\s+de\b)|hoy|esta\s+(?:tarde|noche|ma[ñn]ana)|"
    r"(?:el\s+|este\s+|esta\s+)?(?:pr[óo]ximo\s+)?(?:lunes|martes|mi[ée]rcoles|jueves|viernes|s[áa]bado|domingo)|"
    r"(?:el\s+)?\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|sep?tiembre|octubre|noviembre|diciembre)(?:\s+de\s+\d{4})?|"
    r"(?:el\s+)?\d{1,2}/\d{1,2}(?:/\d{2,4})?|"
    r"a\s+la(?:s)?\s+(?:\d{1,2}(?::\d{2})?|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)"
    r"(?:\s+y\s+(?:media|cuarto|\d{1,2}))?(?:\s*(?:a\.?\s?m\.?|p\.?\s?m\.?|de\s+la\s+(?:ma[ñn]ana|tarde|noche)|del\s+mediod[íi]a))?|"
    r"al?\s+mediod[íi]a)\b", re.I)


def what(n):
    """Lo que hay que hacer, sin la fecha (que se dice aparte y siempre actualizada)."""
    t = n["texto"]
    if n.get("fecha") or n.get("hora"):
        t = _WHEN_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip(" ,.;:")
    t = re.sub(r"^(?:que|de que)\s+", "", t, flags=re.I)
    t = re.sub(r"^(?:es|son|ser[áa]|hay)\s+", "", t, flags=re.I)
    t = re.sub(r"\s+(?:es|son|ser[áa]|va a ser|para|el|la|de)$", "", t, flags=re.I).strip(" ,.;:")
    return t or n["texto"]


def spoken(n, today=None, with_day=True):
    cuando = when_spoken(n, today, with_day)
    return f"{cuando}, {what(n)}" if cuando else what(n)


# ---------------------------------------------------------------------------
# Operaciones
# ---------------------------------------------------------------------------
def add(texto, now=None):
    texto = re.sub(r"\s+", " ", str(texto)).strip(" .,;")
    if not texto:
        raise ValueError("¿Qué quieres que recuerde?")
    fecha, hora = parse_when(texto, now)
    n = {"id": uuid.uuid4().hex[:8], "texto": texto[:500], "creado": datetime.datetime.now().isoformat(timespec="minutes"),
         "fecha": fecha.isoformat() if fecha else "", "hora": hora, "hecho": False, "avisado": []}
    with _lock:
        notes.append(n)
        save()
    return n


def pending():
    return [n for n in notes if not n.get("hecho")]


def _sort_key(n):
    return (0, n["fecha"], n.get("hora") or "99:99") if n.get("fecha") else (1, n["creado"], "")


def listing(scope="todo", today=None):
    """scope: todo | hoy | manana | semana | vencidas"""
    today = today or datetime.date.today()
    out = []
    for n in pending():
        d = datetime.date.fromisoformat(n["fecha"]) if n.get("fecha") else None
        if scope == "hoy" and d != today:
            continue
        if scope == "manana" and d != today + datetime.timedelta(days=1):
            continue
        if scope == "semana" and not (d and today <= d <= today + datetime.timedelta(days=7)):
            continue
        out.append(n)
    return sorted(out, key=_sort_key)


_STOP = {"de", "la", "el", "los", "las", "lo", "que", "a", "y", "en", "un", "una", "con", "para", "por",
         "es", "del", "al", "mi", "mis", "nota", "notas", "hice", "ya", "sobre"}


def find(query):
    """La nota pendiente que mejor encaja con lo dicho («lo de la reunión»)."""
    q = {w for w in normalize(query).split() if w not in _STOP and len(w) > 2}
    if not q:
        return None
    best, score = None, 0
    for n in pending():
        words = set(normalize(n["texto"]).split())
        hits = sum(1 for w in q if w in words or any(x.startswith(w[:5]) for x in words if len(w) >= 5))
        if hits > score:
            best, score = n, hits
    return best if score else None


def set_done(note_id, done=True):
    with _lock:
        for n in notes:
            if n["id"] == note_id:
                n["hecho"] = bool(done)
                save()
                return n
    return None


def delete(note_id):
    with _lock:
        before = len(notes)
        notes[:] = [n for n in notes if n["id"] != note_id]
        save()
        return len(notes) != before


def clear_done():
    with _lock:
        notes[:] = [n for n in notes if not n.get("hecho")]
        save()


def due_alerts(now=None, before_min=30):
    """Avisos que tocan ahora: (nota, "antes"|"hora"). Marca cada aviso para no repetirlo."""
    now = now or datetime.datetime.now()
    out = []
    with _lock:
        for n in pending():
            if not (n.get("fecha") and n.get("hora")):
                continue
            due = datetime.datetime.fromisoformat(f"{n['fecha']}T{n['hora']}")
            avisado = n.setdefault("avisado", [])
            if before_min and "antes" not in avisado and due - datetime.timedelta(minutes=before_min) <= now < due:
                avisado.append("antes")
                out.append((n, "antes"))
            if "hora" not in avisado and due <= now < due + datetime.timedelta(minutes=15):
                avisado.append("hora")
                if "antes" not in avisado:
                    avisado.append("antes")
                out.append((n, "hora"))
        if out:
            save()
    return out


def context_for_ai(limit=20, today=None):
    """Resumen para que la IA pueda contestar «¿cuándo era lo de los padres?»."""
    items = listing("todo", today)[:limit]
    if not items:
        return ""
    lines = []
    for n in items:
        cuando = when_spoken(n, today)
        lines.append(f"- {what(n)}" + (f" ({cuando})" if cuando else ""))
    return (" Notas y pendientes que el usuario te pidió recordar (úsalas si pregunta por ellas):\n"
            + "\n".join(lines))
