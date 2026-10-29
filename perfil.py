"""Memoria que aprende sola: cosas que el usuario cuenta de sí mismo o sus gustos, sin
tener que decir «recuerda». Jarvis las guarda y las tiene en cuenta al responder.

Es determinista (no inventa): solo guarda una frase cuando empieza por un giro claro de
preferencia o dato personal («trabajo en…», «prefiero…», «soy profe de…», «mi colegio es…»).
Se ven y se borran en Ajustes › Memoria.
"""
import json
import os
import re
import threading
import unicodedata

_lock = threading.Lock()
_path = None
facts = []        # [{"id": str, "texto": str, "fecha": "YYYY-MM-DD"}]
MAX = 60

# Giros con los que una frase es claramente un dato o preferencia del usuario.
_LEADS = [
    r"trabajo en", r"trabajo como", r"soy (?:profe|profesor|profesora|docente|maestr[oa]) de",
    r"soy de", r"vivo en", r"mi colegio es", r"mi colegio se llama", r"mi institucion es",
    r"enseno", r"dicto (?:clase|clases)? ?(?:de|en)?", r"doy clase[s]? de", r"mi curso es",
    r"mis estudiantes", r"mi grado es", r"mi materia es", r"mi area es",
    r"prefiero", r"me gusta que", r"no me gusta que", r"odio que", r"me molesta que",
    r"siempre (?:uso|hago|empiezo)", r"normalmente", r"por lo general",
    r"mi correo es", r"mi numero es", r"mi cumpleanos es", r"mi aniversario es",
    r"recuerda siempre que", r"ten en cuenta que", r"para que sepas",
]
_LEAD_RE = re.compile(r"^(?:oye |mira |jarvis |por favor )?(?:que )?(" + "|".join(_LEADS) + r")\b", re.I)
_FORGET_RE = re.compile(r"^(?:oye |jarvis )?(?:olvida(?:te)?|borra|elimina|quita)\b.*?\b"
                        r"(?:que |lo de |eso de )?(.+)$", re.I)
# Cosas que NO son datos del perfil aunque empiecen parecido (órdenes, recordatorios)
_NOT = re.compile(r"\b(?:recuerdame|recordatorio|alarma|avisame|manda|abre|cierra|pon|busca|reproduce|"
                  r"temporizador|cronometro|llama)\b", re.I)


def normalize(text):
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "perfil.json")
    load()


def load():
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, list):
            facts[:] = [x for x in d if isinstance(x, dict) and x.get("texto")][:MAX]
    except (FileNotFoundError, ValueError, OSError, TypeError):
        facts[:] = []


def save():
    if not _path:
        return
    os.makedirs(os.path.dirname(_path), exist_ok=True)
    tmp = _path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path)


def _clean(texto):
    texto = re.sub(r"\s+", " ", str(texto)).strip().strip(" .,;:")
    # quita un «jarvis» o muletilla al principio
    texto = re.sub(r"^(?:oye|mira|jarvis|por favor)[, ]+", "", texto, flags=re.I).strip()
    return texto[:200]


def detect(text):
    """Si la frase es un dato/preferencia del usuario, devuelve el texto a guardar; si no, None."""
    t = normalize(text)
    if len(t) < 6 or _NOT.search(t) or t.endswith("?") or "?" in text:
        return None
    if not _LEAD_RE.match(t):
        return None
    return _clean(text)


def add(texto, now=None):
    import datetime
    texto = _clean(texto)
    if not texto:
        return None
    key = normalize(texto)
    with _lock:
        for fct in facts:
            if normalize(fct["texto"]) == key:
                return fct
        import uuid
        fct = {"id": uuid.uuid4().hex[:8], "texto": texto,
               "fecha": (now or datetime.date.today()).isoformat() if hasattr(now or datetime.date.today(), "isoformat") else ""}
        facts.insert(0, fct)
        del facts[MAX:]
        save()
    return fct


def forget(text):
    """«olvida que trabajo en…»: borra lo que más se parezca. Devuelve el texto borrado o None."""
    m = _FORGET_RE.match(normalize(text))
    if not m:
        return None
    target = m.group(1).strip()
    if len(target) < 3:
        return None
    import difflib
    best, score = None, 0.0
    with _lock:
        for fct in facts:
            s = difflib.SequenceMatcher(None, target, normalize(fct["texto"])).ratio()
            if target in normalize(fct["texto"]):
                s = max(s, 0.9)
            if s > score:
                best, score = fct, s
        if best and score >= 0.5:
            facts.remove(best)
            save()
            return best["texto"]
    return None


def delete(fid):
    with _lock:
        before = len(facts)
        facts[:] = [f for f in facts if f["id"] != fid]
        if len(facts) != before:
            save()


def clear():
    with _lock:
        facts[:] = []
        save()


def context_for_ai(limit=30):
    items = facts[:limit]
    if not items:
        return ""
    return (" Lo que sabes del usuario por lo que te ha contado (tenlo en cuenta con naturalidad, "
            "no lo recites): " + "; ".join(f["texto"] for f in items) + ".")


def snapshot():
    return [{"id": f["id"], "texto": f["texto"], "fecha": f.get("fecha", "")} for f in facts]
