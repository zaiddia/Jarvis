"""Centro de aprobaciones (7.6): lo que Jarvis va a hacer por su cuenta y es importante, primero te lo pregunta.

Cada aprobación tiene un número corto (para decir «sí 3» desde el celular), un título y un detalle. Se aprueba o se
rechaza por voz, desde el HUD, el reactor, el panel del celular o Telegram; si nadie responde, caduca (y no se hace).
Todo queda en el registro de acciones: qué se pidió, quién lo aprobó y cuándo.
jarvis.py guarda qué hacer al aprobar; aquí solo están los datos.
"""
import datetime
import json
import os
import threading
import time

_lock = threading.Lock()
_dir = None
items = []                 # [{"id", "tipo", "titulo", "detalle", "creada", "caduca", "estado", "por", "resuelta"}]
_seq = {"n": 0}
LOG_KEEP_DAYS = 90


def configure(config_dir):
    global _dir
    _dir = os.path.join(config_dir, "registro")


def add(tipo, titulo, detalle="", ttl=900, now=None):
    now = now or time.time()
    with _lock:
        _seq["n"] = _seq["n"] % 99 + 1
        while any(i["id"] == _seq["n"] and i["estado"] == "pendiente" for i in items):
            _seq["n"] = _seq["n"] % 99 + 1
        item = {"id": _seq["n"], "tipo": tipo, "titulo": str(titulo)[:200], "detalle": str(detalle)[:2000],
                "creada": now, "caduca": now + ttl, "estado": "pendiente", "por": "", "resuelta": 0}
        items.append(item)
        del items[:-60]
    log("pedida", item, now=now)
    return item


def expire(now=None):
    """Marca como caducadas las que nadie respondió. Devuelve las que caducaron ahora."""
    now = now or time.time()
    out = []
    with _lock:
        for i in items:
            if i["estado"] == "pendiente" and now > i["caduca"]:
                i.update(estado="caducada", resuelta=now)
                out.append(i)
    for i in out:
        log("caducada", i, now=now)
    return out


def pending(now=None):
    expire(now)
    return [i for i in items if i["estado"] == "pendiente"]


def get(aid):
    return next((i for i in items if i["id"] == aid), None)


def latest(now=None):
    p = pending(now)
    return p[-1] if p else None


def resolve(aid, ok, por="voz", now=None):
    """Aprueba (ok=True) o rechaza una pendiente. Devuelve la aprobación o None si ya no estaba pendiente."""
    now = now or time.time()
    expire(now)
    with _lock:
        i = get(aid)
        if not i or i["estado"] != "pendiente":
            return None
        i.update(estado="aprobada" if ok else "rechazada", por=por, resuelta=now)
    log(i["estado"], i, now=now)
    return i


# ----------------------------------------------------------------------------- registro de acciones
def log(evento, item=None, texto="", now=None):
    """Una línea en el registro: aprobaciones y acciones que Jarvis hizo por su cuenta. Nunca falla."""
    if not _dir:
        return
    now = now or time.time()
    d = datetime.datetime.fromtimestamp(now)
    line = {"ts": d.isoformat(timespec="seconds"), "evento": evento, "texto": str(texto)[:300]}
    if item:
        line.update(id=item["id"], tipo=item["tipo"], titulo=item["titulo"], por=item.get("por", ""))
    try:
        os.makedirs(_dir, exist_ok=True)
        with open(os.path.join(_dir, d.strftime("%Y-%m") + ".jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass


def history(days=1, now=None):
    if not _dir or not os.path.isdir(_dir):
        return []
    now = now or time.time()
    since = datetime.datetime.fromtimestamp(now) - datetime.timedelta(days=days)
    out = []
    for name in sorted(os.listdir(_dir)):
        if not name.endswith(".jsonl") or name[:7] < since.strftime("%Y-%m"):
            continue
        try:
            with open(os.path.join(_dir, name), encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                        if datetime.datetime.fromisoformat(e["ts"]) >= since:
                            out.append(e)
                    except (ValueError, KeyError):
                        continue
        except OSError:
            continue
    return out


def spoken_history(entries):
    acts = [e for e in entries if e["evento"] in ("hecha", "aprobada", "rechazada", "caducada")]
    if not acts:
        return "Hoy no he hecho nada por mi cuenta."
    parts = []
    for e in acts[-8:]:
        hora = e["ts"][11:16]
        what = e.get("titulo") or e.get("texto") or ""
        verb = {"hecha": "hice", "aprobada": "aprobaste", "rechazada": "rechazaste", "caducada": "nadie aprobó"}[e["evento"]]
        parts.append(f"a las {hora} {verb}: {what}")
    return "Por mi cuenta, hoy: " + "; ".join(parts) + "."
