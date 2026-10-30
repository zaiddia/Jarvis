"""Jarvis aprende de lo que haces (7.4): propone rutinas a partir de tus costumbres y las mejora cuando las corriges.

Tres cosas, sin IA y sin internet:
  · Secuencias: si repites las mismas órdenes seguidas (p. ej. «abre Word», «volumen al 30», «pon música
    para concentrarse») en 3 días distintos, propone guardarlas como rutina.
  · Horarios: si das la misma orden a la misma hora (±20 min) en 4 días distintos, propone hacerlo solo.
  · Correcciones: si justo después de una rutina cambias algo que ella hizo («volumen al 25» tras una rutina
    que lo pone al 40), propone corregir ese paso para la próxima vez.

Cada acción se guarda con su «clave» (qué acción y con qué datos), no solo con el texto, así que «sube el
volumen» y «súbele el volumen» cuentan igual. jarvis.py decide cuándo preguntar.
"""
import datetime
import json
import os
import threading
import time

_lock = threading.Lock()
_path = None
data = {"acciones": [], "rechazadas": [], "hechas": []}

MAX_ACTIONS = 1500
KEEP_DAYS = 45
SESSION_GAP = 10 * 60          # más de 10 min sin órdenes = otra sesión
STEP_GAP = 5 * 60              # dentro de una secuencia, como mucho 5 min entre pasos
MIN_DAYS_SEQ = 3
MIN_DAYS_TIME = 4
TIME_TOL = 20                  # minutos
CORRECTION_WINDOW = 180        # segundos tras terminar una rutina


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "aprendizaje.json")
    load()


def load():
    global data
    d = {"acciones": [], "rechazadas": [], "hechas": []}
    try:
        with open(_path, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for k in d:
                if isinstance(raw.get(k), list):
                    d[k] = raw[k]
    except (OSError, ValueError, TypeError):
        pass
    data = d


def save():
    if not _path:
        return
    try:
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        with open(_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(_path + ".tmp", _path)
    except OSError:
        pass


def note(key, text, now=None):
    """Anota una acción que pediste (clave = qué hizo; text = cómo lo dijiste)."""
    if not key or not str(text).strip():
        return
    now = now or time.time()
    cutoff = now - KEEP_DAYS * 86400
    with _lock:
        acts = [a for a in data["acciones"] if a.get("ts", 0) >= cutoff]
        acts.append({"ts": now, "key": str(key), "text": str(text).strip()[:160]})
        data["acciones"] = acts[-MAX_ACTIONS:]
        save()


def _day(ts):
    return datetime.datetime.fromtimestamp(ts).date()


def _sessions(acts):
    out, cur = [], []
    for a in sorted(acts, key=lambda x: x["ts"]):
        if cur and a["ts"] - cur[-1]["ts"] > SESSION_GAP:
            out.append(cur)
            cur = []
        cur.append(a)
    if cur:
        out.append(cur)
    return out


def seq_id(keys):
    return "seq:" + " > ".join(keys)


def find_sequence(acts=None, known_steps=(), min_days=MIN_DAYS_SEQ, max_len=5):
    """La secuencia repetida más útil: {"id", "keys", "texts", "days"} o None.
    known_steps: listas de claves de las rutinas que ya existen (para no proponer lo que ya tienes)."""
    acts = data["acciones"] if acts is None else acts
    blocked = set(data["rechazadas"]) | set(data["hechas"])
    known = {tuple(k) for k in known_steps}
    seen = {}                                          # tupla de claves -> {"days": set, "texts": [...]}
    for s in _sessions(acts):
        for i in range(len(s)):
            for n in range(2, max_len + 1):
                chunk = s[i:i + n]
                if len(chunk) < n:
                    break
                if any(chunk[j + 1]["ts"] - chunk[j]["ts"] > STEP_GAP for j in range(n - 1)):
                    break
                keys = tuple(a["key"] for a in chunk)
                if len(set(keys)) < n:                 # «sube, sube, sube» no es una rutina
                    continue
                e = seen.setdefault(keys, {"days": set(), "texts": [a["text"] for a in chunk]})
                e["days"].add(_day(chunk[0]["ts"]))
    best = None
    for keys, e in seen.items():
        if len(e["days"]) < min_days or seq_id(keys) in blocked or keys in known:
            continue
        if any(set(keys) <= set(k) for k in known):
            continue
        score = (len(keys), len(e["days"]))
        if best is None or score > best[0]:
            best = (score, keys, e)
    if not best:
        return None
    _, keys, e = best
    # si una secuencia más larga la contiene con los mismos días, ya ganó por longitud
    return {"id": seq_id(keys), "keys": list(keys), "texts": e["texts"], "days": len(e["days"])}


def find_time_habit(acts=None, now=None, min_days=MIN_DAYS_TIME, scheduled_keys=()):
    """Una orden que das casi siempre a la misma hora: {"id", "key", "text", "at": (h, m), "weekdays": bool,
    "days"} o None. scheduled_keys: claves que ya se lanzan solas."""
    acts = data["acciones"] if acts is None else acts
    now = now or time.time()
    blocked = set(data["rechazadas"]) | set(data["hechas"])
    recent = [a for a in acts if a["ts"] >= now - 21 * 86400]
    by_key = {}
    for a in recent:
        by_key.setdefault(a["key"], []).append(a)
    best = None
    for key, items in by_key.items():
        if key in scheduled_keys or key.startswith("temporizador:"):
            continue
        mins = []
        for a in items:
            d = datetime.datetime.fromtimestamp(a["ts"])
            mins.append((d.date(), d.hour * 60 + d.minute, d.weekday(), a["text"]))
        for _, center, _, text in mins:
            days = {}
            for day, m, wd, _t in mins:
                if abs(m - center) <= TIME_TOL:
                    days.setdefault(day, (m, wd))
            if len(days) < min_days:
                continue
            avg = round(sum(m for m, _ in days.values()) / len(days) / 5) * 5    # a los 5 minutos
            hid = f"hora:{key}@{avg // 60:02d}:{avg % 60:02d}"
            if hid in blocked:
                continue
            weekdays = all(wd < 5 for _, wd in days.values())
            cand = {"id": hid, "key": key, "text": text, "at": (avg // 60 % 24, avg % 60), "weekdays": weekdays,
                    "days": len(days)}
            if best is None or cand["days"] > best["days"]:
                best = cand
    return best


def find_correction(routine_steps_keys, routine_steps, act_key, act_text):
    """Tras una rutina: si la acción cambia uno de sus pasos (misma acción, otros datos), qué paso cambiar.
    Devuelve {"index", "old", "new"} o None."""
    if ":" not in act_key:
        return None
    skill, args = act_key.split(":", 1)
    try:
        new_args = json.loads(args)
    except ValueError:
        return None
    for i, k in enumerate(routine_steps_keys):
        if not k or ":" not in k:
            continue
        s2, a2 = k.split(":", 1)
        if s2 != skill or k == act_key:
            continue
        try:
            old_args = json.loads(a2)
        except ValueError:
            continue
        # misma clase de acción (fijar volumen, brillo al…): mismos campos, otros valores
        if isinstance(old_args, dict) and isinstance(new_args, dict) and set(old_args) == set(new_args) \
                and old_args.get("accion") == new_args.get("accion"):
            return {"index": i, "old": routine_steps[i], "new": act_text}
    return None


def mark(sid, accepted):
    with _lock:
        lst = data["hechas"] if accepted else data["rechazadas"]
        if sid not in lst:
            lst.append(sid)
        save()


def clear():
    with _lock:
        data["acciones"] = []
        save()


def spoken_steps(texts):
    texts = [f"«{t}»" for t in texts]
    return ", ".join(texts[:-1]) + " y " + texts[-1] if len(texts) > 1 else texts[0]


def default_name(seq_texts, when=None):
    """Un nombre que se pueda decir: «Mi rutina de la mañana», «Mi rutina de la tarde»…"""
    h = (when or datetime.datetime.now()).hour
    part = "de la mañana" if h < 12 else "de la tarde" if h < 19 else "de la noche"
    return f"Mi rutina {part}"
