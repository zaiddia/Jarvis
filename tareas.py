"""Tareas programadas que trabajan solas (7.4): «cada lunes a las 6 resume mis pendientes y mándamelo al celular».

Una tarea es una orden normal de Jarvis con su horario y a dónde llevar el resultado:
    {"id", "orden", "cuando": "18:00 lun", "entrega": "voz" | "celular" | "ambos", "activa": True, "ultima": "AAAA-MM-DD"}
jarvis.py la ejecuta con las reglas del celular (nada de apagar, cerrar, escribir en ventanas ni borrar) y entrega
lo que conteste. El horario usa el mismo formato que las rutinas (rutinas.parse_when).
"""
import datetime
import json
import os
import re
import threading
import unicodedata
import uuid

import rutinas

_lock = threading.Lock()
_path = None
tasks = []
MAX_TASKS = 40


def norm(text):
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s:]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "tareas.json")
    load()


def load():
    global tasks
    try:
        with open(_path, encoding="utf-8") as f:
            raw = json.load(f)
        tasks = [t for t in raw if isinstance(t, dict) and t.get("orden") and rutinas.parse_when(t.get("cuando", ""))] \
            if isinstance(raw, list) else []
    except (OSError, ValueError, TypeError):
        tasks = []


def save():
    if not _path:
        return
    try:
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        with open(_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=1)
        os.replace(_path + ".tmp", _path)
    except OSError:
        pass


_DELIVERY = re.compile(r"\s*(?:,\s*)?\b(?:y\s+)?(?:(?:me\s+lo|me\s+la|me\s+los|me\s+las)\s+(?:mandas|envias|pasas)|"
                       r"mandamel[oa]s?|enviamel[oa]s?|pasamel[oa]s?|mandame(?:lo)?|enviame(?:lo)?)?\s*"
                       r"(?:(?:al|a mi|por el|por mi|en el|en mi|por|a)\s+)?(?:celular|telefono|movil|telegram|whatsapp)\b\s*")
_BOTH = re.compile(r"\b(?:y\s+)?(?:dimelo tambien|tambien en voz alta|en voz alta tambien|dimelo)\b")
_WHEN_PARTS = [
    r"\b(?:cada|todos los|todas las)\s+(?:dias?|lunes|martes|miercoles|jueves|viernes|sabados?|domingos?|mananas|tardes|noches)\b",
    r"\b(?:de lunes a viernes|entre semana|los fines de semana|fines de semana|cada fin de semana)\b",
    r"\b(?:los|las)\s+(?:lunes|martes|miercoles|jueves|viernes|sabados|domingos)(?:\s+(?:y|,)\s+(?:lunes|martes|miercoles|jueves|viernes|sabados|domingos))*\b",
    r"\b(?:y|,)\s+(?:los\s+)?(?:lunes|martes|miercoles|jueves|viernes|sabados|domingos)\b",
    r"\ba las?\s+\d{1,2}(?::\d{2})?\s*(?:a\s?m|p\s?m|de la manana|de la tarde|de la noche|en punto)?\b",
]
_LEAD = re.compile(r"^(?:jarvis\s+)?(?:programa(?:me)?|crea|agenda|configura|pon)?\s*(?:una\s+)?(?:tarea\s+)?(?:para\s+)?(?:que\s+)?")
_VERB = re.compile(r"\b(?:resume|resumeme|dime|di|dame|mandame|enviame|revisa|lee|leeme|busca|investiga|averigua|"
                   r"cuenta|cuentame|haz|hazme|prepara|preparame|crea|creame|genera|generame|arma|armame|"
                   r"recuerdame que|pon|abre|muestrame|que tengo|como esta|como va|"
                   r"cuales son|que hay|cuanto)\b")


def _with_accents(original, plain):
    """Recupera las tildes del texto original para la orden ya limpia («dime que tengo hoy» → «dime qué tengo hoy»)."""
    words = re.sub(r"[^\w\s:]", " ", str(original).lower()).split()
    normed = [norm(w) for w in words]
    target = plain.split()
    for i in range(len(normed) - len(target) + 1):
        if normed[i:i + len(target)] == target:
            return " ".join(words[i:i + len(target)])
    return plain


def parse_voice(text):
    """«cada lunes a las 6 de la tarde resume mis pendientes y mándamelo al celular» →
    {"orden": "resume mis pendientes", "cuando": "18:00 lun", "entrega": "celular"}. None si no es una tarea."""
    t = norm(text)
    if re.match(r"^(?:recuerdame|recuerda|avisame|alarma)\b", t):
        return None                                    # eso son recordatorios (notas)
    if not re.search(r"\b(?:cada|todos los|todas las|de lunes a viernes|entre semana|fines de semana|los (?:lunes|martes|miercoles|jueves|viernes|sabados|domingos))\b", t):
        return None
    if not re.search(r"\ba las?\s+\d", t):
        return None
    # el horario se lee solo de sus trozos («cada lunes», «a las 6 de la tarde»), no de toda la frase
    when_txt = " ".join(m.group(0) for rx in _WHEN_PARTS for m in re.finditer(rx, t))
    w = rutinas.parse_when(when_txt)
    if not w or w["kind"] != "hora":
        return None
    entrega = "voz"
    if _DELIVERY.search(t):
        entrega = "ambos" if _BOTH.search(t) else "celular"
    rest = _DELIVERY.sub(" ", t)
    rest = _BOTH.sub(" ", rest)
    for rx in _WHEN_PARTS:
        rest = re.sub(rx, " ", rest)
    rest = _LEAD.sub("", re.sub(r"\s+", " ", rest).strip())
    rest = re.sub(r"^(?:y|que|a)\s+", "", rest).strip(" ,")
    rest = re.sub(r"(?:\s+y)+$", "", rest).strip(" ,")
    if len(rest) < 3 or not _VERB.search(rest):
        return None
    rest = _with_accents(text, rest)
    return {"orden": rest, "cuando": w["text"], "entrega": entrega}


def add(orden, cuando, entrega="voz"):
    orden = str(orden or "").strip()[:300]
    w = rutinas.parse_when(cuando)
    if not orden:
        raise ValueError("Escribe qué debe hacer la tarea.")
    if not w or w["kind"] != "hora":
        raise ValueError("No entendí la hora. Usa por ejemplo 07:30, 18:00 lun-vie o 06:00 lun.")
    if entrega not in ("voz", "celular", "ambos"):
        entrega = "voz"
    item = {"id": uuid.uuid4().hex[:8], "orden": orden, "cuando": w["text"], "entrega": entrega, "activa": True, "ultima": ""}
    with _lock:
        if len(tasks) >= MAX_TASKS:
            raise ValueError(f"Ya tienes {MAX_TASKS} tareas: borra alguna antes.")
        tasks.append(item)
        save()
    return item


def remove(tid):
    with _lock:
        n = len(tasks)
        tasks[:] = [t for t in tasks if t["id"] != tid]
        save()
        return len(tasks) < n


def set_active(tid, on):
    with _lock:
        for t in tasks:
            if t["id"] == tid:
                t["activa"] = bool(on)
                save()
                return t
    return None


def find(words):
    """La tarea a la que se refiere «borra la tarea de los pendientes» (o la única que hay)."""
    w = [x for x in norm(words).split() if len(x) > 3 and x not in ("tarea", "tareas", "programada", "borra", "quita",
                                                                     "elimina", "pausa", "reanuda", "activa")]
    best, score = None, 0
    for t in tasks:
        s = sum(1 for x in w if x in norm(t["orden"]))
        if s > score:
            best, score = t, s
    if best is None and len(tasks) == 1:
        return tasks[0]
    return best


def due(now):
    """Las tareas que tocan ahora (en sus 10 minutos siguientes) y no se han hecho hoy."""
    out = []
    today = now.date().isoformat()
    for t in tasks:
        if not t.get("activa", True) or t.get("ultima") == today:
            continue
        w = rutinas.parse_when(t["cuando"])
        if not w or w["kind"] != "hora" or not w["days"][now.weekday()]:
            continue
        start = now.replace(hour=w["at"][0], minute=w["at"][1], second=0, microsecond=0)
        if start <= now < start + datetime.timedelta(minutes=10):
            out.append(t)
    return out


def missed(now, hours=6):
    """Al arrancar: las de hoy cuya hora ya pasó (hace menos de «hours» horas) y no se hicieron (equipo apagado)."""
    out = []
    today = now.date().isoformat()
    for t in tasks:
        if not t.get("activa", True) or t.get("ultima") == today:
            continue
        w = rutinas.parse_when(t["cuando"])
        if not w or w["kind"] != "hora" or not w["days"][now.weekday()]:
            continue
        start = now.replace(hour=w["at"][0], minute=w["at"][1], second=0, microsecond=0)
        if start <= now < start + datetime.timedelta(hours=hours):
            out.append(dict(t, _missed=start + datetime.timedelta(minutes=10) <= now))
    return out


def mark_done(tid, day):
    with _lock:
        for t in tasks:
            if t["id"] == tid:
                t["ultima"] = day.isoformat()
        save()


_DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos"]


def when_text(cuando):
    """«18:00 lun» → «los lunes a las 18:00»; «07:00» → «todos los días a las 7:00»."""
    w = rutinas.parse_when(cuando)
    if not w or w["kind"] != "hora":
        return cuando
    h, m = w["at"]
    at = f"a las {h}:{m:02d}"
    days = [i for i, on in enumerate(w["days"]) if on]
    if len(days) == 7:
        return f"todos los días {at}"
    if days == [0, 1, 2, 3, 4]:
        return f"de lunes a viernes {at}"
    if days == [5, 6]:
        return f"los fines de semana {at}"
    names = [_DAY_NAMES[i] for i in days]
    return "los " + (", ".join(names[:-1]) + " y " + names[-1] if len(names) > 1 else names[0]) + f" {at}"


def spoken(t):
    dest = {"voz": "", "celular": " y te lo mando al celular", "ambos": ", te lo digo y te lo mando al celular"}[t.get("entrega", "voz")]
    return f"{when_text(t['cuando'])}: {t['orden']}{dest}"
