"""Lecciones (9.4): Jarvis aprende de tus correcciones, pero solo guarda lo que tú apruebas.

Reglas tuyas («cuando digo 7A me refiero a matemáticas de séptimo A», «de ahora en adelante los quices con 5
preguntas», «nunca uses la palabra alumnos») se guardan al momento: las dijiste tú. Cuando corriges una respuesta («no,
me refería a…», «eso no es lo que pedí»), Jarvis propone una lección y te pide aprobarla. Las lecciones guardadas se le
dan a la IA en cada respuesta y al preparar material.
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
items = []          # [{"id", "texto", "origen": "tú"|"corrección", "fecha"}]
MAX = 40

RULE_RE = re.compile(r"^(?:(?:jarvis\s+)?(?:de ahora en adelante|a partir de ahora|desde ahora|en adelante|siempre que (?:te (?:pida|diga)|diga|pida)|"
                     r"cuando (?:te )?(?:digo|diga|pida|pido|hable de)|nunca|no vuelvas a|recuerda siempre|ten en cuenta siempre que|"
                     r"aprende que)\b)\s*(.+)$")
CORRECTION_RE = re.compile(r"^(?:no+\s*,?\s*)?(?:me referia a|me refiero a|quise decir|yo dije|lo que (?:quiero|queria|pedi) (?:es|era)|"
                           r"eso no es lo que (?:pedi|te pedi|queria)|te equivocaste|esta mal|no es eso|no era eso|asi no|"
                           r"no,? (?:era|es) (?:al|el|la|lo|en|de|para|con)\b)")


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "lecciones.json")
    load()


def load():
    global items
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        items = [x for x in d if isinstance(x, dict) and x.get("texto")] if isinstance(d, list) else []
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


def add(texto, origen="tú"):
    texto = re.sub(r"\s+", " ", str(texto)).strip(" .")
    texto = texto[:1].upper() + texto[1:]
    k = norm(texto)
    with _lock:
        if any(norm(x["texto"]) == k for x in items):
            return None
        items.append({"id": uuid.uuid4().hex[:6], "texto": texto[:300], "origen": origen,
                      "fecha": datetime.date.today().isoformat()})
        del items[:-MAX]
        save()
    return items[-1]


def remove(words):
    w = {x for x in norm(words).split() if len(x) > 3}
    with _lock:
        best = max(items, key=lambda x: len(w & set(norm(x["texto"]).split())), default=None)
        if best and w & set(norm(best["texto"]).split()):
            items.remove(best)
            save()
            return best
    return None


def delete(lid):
    with _lock:
        before = len(items)
        items[:] = [x for x in items if x["id"] != lid]
        save()
        return len(items) != before


def context(limit=15):
    if not items:
        return ""
    return (" Lecciones que el usuario te enseñó (síguelas siempre): " +
            " ".join(f"({i + 1}) {x['texto']}." for i, x in enumerate(items[-limit:])))


def rule_from(text):
    """La regla tal como la dijiste («de ahora en adelante los quices con 5 preguntas»)."""
    m = RULE_RE.match(norm(text))
    if not m or len(m.group(1).split()) < 2:
        return None
    return re.sub(r"^(?:jarvis[,\s]+)", "", text.strip(), flags=re.I).rstrip(".")


def propose_prompt(user_cmd, jarvis_reply, correction):
    return ("Un asistente respondió mal y el usuario lo corrigió. Escribe UNA lección corta y general (máximo 25 palabras, en "
            "segunda persona, en español) para no repetir el error en el futuro. Si la corrección es solo de este caso y no "
            "sirve como regla general, devuelve una lección vacía.\n"
            f"Pedido: «{user_cmd[:400]}»\nRespuesta del asistente: «{jarvis_reply[:600]}»\nCorrección: «{correction[:400]}»\n"
            'Devuelve SOLO JSON: {"leccion": "…"}')
