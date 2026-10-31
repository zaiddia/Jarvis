"""Evaluaciones con hoja de respuestas (10.5): la clave, las hojas impresas y lo que sacó cada estudiante.

Son datos de estudiantes: se guardan cifrados con los demás si lo activaste.
"""
import datetime
import os
import random
import re
import threading

import datos

_lock = threading.Lock()
_path = None
data = {"examenes": {}}
locked = False


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "examenes.json")
    load()


def load():
    global data, locked
    try:
        d = datos.read_json(_path)
        data, locked = (d if isinstance(d, dict) and isinstance(d.get("examenes"), dict) else {"examenes": {}}), False
    except datos.DataLocked:
        data, locked = {"examenes": {}}, True
    except (OSError, ValueError, TypeError):
        data = {"examenes": {}}


def save():
    if not _path or locked:
        return
    try:
        datos.write_json(_path, data)
    except OSError:
        pass


def parse_key(text):
    """«a b c d», «1a 2c 3b», «ACBD…» → [0, 2, 1, 3, …]."""
    t = str(text or "").lower()
    pairs = re.findall(r"\b(\d{1,2})\s*[-.):]?\s*([a-e])\b", t)
    if pairs:
        out = {}
        for n, l in pairs:
            out[int(n)] = "abcde".index(l)
        return [out.get(i, 0) for i in range(1, max(out) + 1)]
    letters = re.findall(r"\b([a-e])\b", t) or (list(re.sub(r"[^a-e]", "", t)) if re.fullmatch(r"[a-e\s,;.-]+", t.strip()) else [])
    return ["abcde".index(l) for l in letters]


def new(titulo, curso, clave, n_opt, preguntas=None, estudiantes=None, tema="", tipo="hoja"):
    with _lock:
        code = random.randint(100, 16383)
        while str(code) in data["examenes"]:
            code = random.randint(100, 16383)
        ex = {"code": code, "titulo": str(titulo)[:120], "curso": curso, "tema": str(tema)[:120], "clave": list(clave),
              "n_opt": int(n_opt), "preguntas": list(preguntas or []), "estudiantes": {str(k): v for k, v in (estudiantes or {}).items()},
              "creado": datetime.datetime.now().isoformat(timespec="minutes"), "resultados": {}, "cerrado": False, "anotado": False,
              "tipo": tipo}
        data["examenes"][str(code)] = ex
        save()
    return ex


def get(code):
    return data["examenes"].get(str(code))


def latest(open_only=False, tipo=None):
    exs = [e for e in data["examenes"].values() if (not open_only or not e["cerrado"]) and (tipo is None or e.get("tipo") == tipo)]
    return max(exs, key=lambda e: e["creado"], default=None)


def add_result(code, student, answers, graded, nombre="", origen="omr"):
    with _lock:
        ex = data["examenes"][str(code)]
        if student:
            key = str(student)
        else:                                          # hoja en blanco (sin número): se numera aparte
            key = f"s{sum(1 for k in ex['resultados'] if k.startswith('s')) + 1}"
        nombre = nombre or ex["estudiantes"].get(str(student)) or f"Hoja sin nombre {key[1:]}"
        ex["resultados"][key] = {"nombre": nombre, "answers": answers, "aciertos": graded["aciertos"], "total": graded["total"],
                                 "nota": graded["nota"], "detalle": graded["detalle"], "origen": origen,
                                 "t": datetime.datetime.now().isoformat(timespec="seconds")}
        save()
        return ex["resultados"][key]


def rename(code, key, nombre):
    with _lock:
        ex = data["examenes"][str(code)]
        if key in ex["resultados"]:
            ex["resultados"][key]["nombre"] = nombre
            save()


def close(code):
    with _lock:
        ex = data["examenes"][str(code)]
        ex["cerrado"] = True
        save()
        return ex
