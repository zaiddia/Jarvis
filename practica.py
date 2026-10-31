"""Tutor personal de cada estudiante (10.7): práctica a la medida desde el celular. Lógica pura, sin Jarvis.

Cada estudiante practica lo que más le cuesta (lo que falló en las evaluaciones con hoja, su competencia Saber más
floja, sus notas bajas o el tema de la clase). Los ejercicios suben o bajan de nivel según cómo le va; si se equivoca,
recibe una pista (sin la respuesta) y vuelve a intentar; a la tercera, la explicación paso a paso.
Lo que avanza cada uno queda guardado (cifrado con los datos de estudiantes si lo activaste).
"""
import datetime
import hashlib
import os
import random
import threading
import uuid

import datos

_lock = threading.Lock()
_path = None
data = {"cursos": {}}           # {curso: {estudiante: {"pin", "ej", "puntos", "temas": {tema: {"n", "ok", "nivel", "racha"}}, "dias": [..]}}}
locked = False
pool = {}                       # {(curso, tema, nivel): [ejercicio…]} (en memoria)


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "practica.json")
    load()


def load():
    global data, locked
    try:
        d = datos.read_json(_path)
        data, locked = (d if isinstance(d, dict) and isinstance(d.get("cursos"), dict) else {"cursos": {}}), False
    except datos.DataLocked:
        data, locked = {"cursos": {}}, True
    except (OSError, ValueError, TypeError):
        data = {"cursos": {}}


def save():
    if not _path or locked:
        return
    try:
        datos.write_json(_path, data)
    except OSError:
        pass


def _hash(curso, est, pin):
    return hashlib.sha256(f"jarvis|{curso}|{est}|{pin}".encode()).hexdigest()[:24]


def student(curso, est):
    with _lock:
        return data["cursos"].setdefault(curso, {}).setdefault(est, {"pin": "", "ej": 0, "puntos": 0.0, "temas": {}, "dias": []})


def check_pin(curso, est, pin):
    """Primera vez: guarda el PIN. Después: debe coincidir. → (ok, mensaje)."""
    pin = str(pin or "").strip()
    if not (pin.isdigit() and len(pin) == 4):
        return False, "El PIN son 4 números."
    s = student(curso, est)
    with _lock:
        if not s["pin"]:
            s["pin"] = _hash(curso, est, pin)
            save()
            return True, "PIN guardado. Recuérdalo para la próxima vez."
        if s["pin"] != _hash(curso, est, pin):
            return False, "Ese no es tu PIN. Si lo olvidaste, pídele a tu profe que lo borre."
    return True, ""


def reset_pin(curso, est):
    with _lock:
        s = data["cursos"].get(curso, {}).get(est)
        if s:
            s["pin"] = ""
            save()
            return True
    return False


def pick_topic(curso, est, focus):
    """El tema que toca: el de menor dominio entre los temas foco (y de vez en cuando otro, para repasar)."""
    s = student(curso, est)
    if not focus:
        return None
    scored = []
    for f in focus:
        t = s["temas"].get(f["tema"], {})
        n, ok = t.get("n", 0), t.get("ok", 0)
        scored.append(((ok + 1) / (n + 2) + random.random() * 0.15, f))
    return min(scored, key=lambda x: x[0])[1]


def level(curso, est, tema):
    return student(curso, est)["temas"].get(tema, {}).get("nivel", 1)


def record(curso, est, tema, first_try, tries):
    """Registra un ejercicio. first_try: acertó a la primera. Sube de nivel con 2 aciertos seguidos, baja con 2 fallos."""
    s = student(curso, est)
    with _lock:
        t = s["temas"].setdefault(tema, {"n": 0, "ok": 0, "nivel": 1, "racha": 0})
        t["n"] += 1
        s["ej"] += 1
        if first_try:
            t["ok"] += 1
            s["puntos"] += 1.0
            t["racha"] = max(1, t["racha"] + 1) if t["racha"] >= 0 else 1
        else:
            s["puntos"] += 0.5 if tries <= 3 else 0.0
            t["racha"] = min(-1, t["racha"] - 1) if t["racha"] <= 0 else -1
        if t["racha"] >= 2 and t["nivel"] < 3:
            t["nivel"] += 1
            t["racha"] = 0
        elif t["racha"] <= -2 and t["nivel"] > 1:
            t["nivel"] -= 1
            t["racha"] = 0
        day = datetime.date.today().isoformat()
        if day not in s["dias"]:
            s["dias"].append(day)
            del s["dias"][:-120]
        save()
        return t["nivel"]


def nota(s, meta=20):
    """Nota de la práctica (1,0 a 5,0): puntos frente a la meta del periodo."""
    return round(1.0 + 4.0 * min(1.0, s.get("puntos", 0) / float(max(1, meta))), 1)


def summary(curso):
    out = []
    for est, s in data["cursos"].get(curso, {}).items():
        n = s.get("ej", 0)
        ok = sum(t.get("ok", 0) for t in s.get("temas", {}).values())
        out.append({"nombre": est, "ej": n, "pct": round(100 * ok / n) if n else None, "dias": len(s.get("dias", [])),
                    "ultimo": (s.get("dias") or [""])[-1], "puntos": s.get("puntos", 0),
                    "temas": {k: {"nivel": v.get("nivel", 1), "pct": round(100 * v["ok"] / v["n"]) if v.get("n") else None}
                              for k, v in s.get("temas", {}).items()}})
    return sorted(out, key=lambda x: -x["ej"])


# ----------------------------------------------------------------------------- ejercicios
LEVELS = {1: "básico (un paso, números sencillos)", 2: "medio (dos o tres pasos)", 3: "avanzado (problema en contexto, varios pasos)"}


def exercise_prompt(tema, detalle, nivel, grado, asignatura="Matemáticas", n=6):
    return (f"Eres un tutor de {asignatura} para un estudiante de grado {grado} en Colombia. Crea {n} ejercicios de práctica sobre «{tema}»"
            + (f" (el estudiante falló algo así: «{detalle}»)" if detalle else "") + f", nivel {LEVELS.get(nivel, LEVELS[1])}. "
            "Cada ejercicio de selección múltiple con 4 opciones (las incorrectas, errores típicos), 2 pistas que guían con una pregunta o una "
            "idea SIN dar la respuesta (la segunda más concreta) y la explicación paso a paso para cuando ya no lo logre. Enunciados cortos que "
            "se lean bien en un celular. Texto plano, sin LaTeX (usa 3/4, x², √9). Responde SOLO con JSON: "
            '{"ejercicios": [{"enunciado": str, "opciones": [str, str, str, str], "respuesta": "a"|"b"|"c"|"d", "pistas": [str, str], '
            '"explicacion": str}]}')


def clean_exercises(d, tema, nivel):
    out = []
    for e in (d.get("ejercicios") or [])[:10] if isinstance(d, dict) else []:
        ops = [str(o).strip()[:200] for o in (e.get("opciones") or [])][:4]
        r = str(e.get("respuesta", "")).strip().lower()[:1]
        if len(ops) != 4 or r not in "abcd" or not str(e.get("enunciado", "")).strip():
            continue
        out.append({"id": uuid.uuid4().hex[:10], "tema": tema, "nivel": nivel, "enunciado": str(e["enunciado"]).strip()[:600], "opciones": ops,
                    "respuesta": "abcd".index(r), "pistas": [str(p).strip()[:300] for p in (e.get("pistas") or [])][:2],
                    "explicacion": str(e.get("explicacion", "")).strip()[:900]})
    return out


def from_bank(qs, tema, nivel):
    """Sin IA: preguntas del banco como ejercicios (sin pistas)."""
    out = []
    for q in qs:
        r = str(q.get("respuesta", "a"))[:1].lower()
        if len(q.get("opciones") or []) < 2 or r not in "abcd":
            continue
        out.append({"id": uuid.uuid4().hex[:10], "tema": tema, "nivel": nivel, "enunciado": q["enunciado"][:600], "opciones": list(q["opciones"])[:4],
                    "respuesta": "abcd".index(r), "pistas": [], "explicacion": q.get("explicacion", "")[:900]})
    return out


TUTOR_CHAT = ("Eres el tutor personal de un estudiante de colegio en Colombia ({grado}, {asignatura}). Está resolviendo: «{ejercicio}». "
              "NUNCA le des la respuesta ni la letra correcta: guíalo con UNA pregunta o pista corta, en lenguaje sencillo, y anímalo. "
              "Si pregunta algo que no es del colegio, llévalo con respeto a la práctica. Máximo 3 frases.")
