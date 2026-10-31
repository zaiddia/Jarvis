"""Valoraciones de los periodos ya cerrados (10.2), para el acumulado del año (VF) y lo que falta (VRA), como en Zeti.

Se llenan solas al cerrar cada periodo con Jarvis, o pegando la tabla de Zeti de un periodo
(Ajustes › Memoria › Periodos anteriores). Son datos de estudiantes: se cifran con los demás si lo activaste.
"""
import re
import threading
import unicodedata

import datos

_lock = threading.Lock()
_path = None
data = {}           # {curso: {estudiante: {"1": 3.3, "2": 4.2}}}
locked = False


def configure(config_dir):
    global _path
    import os
    _path = os.path.join(config_dir, "periodos.json")
    load()


def load():
    global data, locked
    try:
        d = datos.read_json(_path)
        data, locked = (d if isinstance(d, dict) else {}), False
    except datos.DataLocked:
        data, locked = {}, True
    except (OSError, ValueError, TypeError):
        data = {}


def save():
    if not _path or locked:
        return
    try:
        datos.write_json(_path, data)
    except OSError:
        pass


def set_val(curso, estudiante, periodo, val):
    with _lock:
        data.setdefault(curso, {}).setdefault(estudiante, {})[str(int(periodo))] = round(float(val), 1)
        save()


def vals(curso, estudiante, before):
    """[val del periodo 1, …, val del periodo before-1] (None donde no hay)."""
    d = data.get(curso, {}).get(estudiante, {})
    return [d.get(str(p)) for p in range(1, before)]


# ----------------------------------------------------------------------------- pegar la tabla de Zeti
_LETTERS = {"S", "A", "B", "BJ"}
_NUM = re.compile(r"^\d(?:[.,]\d{1,2})?$")


def _plain(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn")


def parse_paste(text):
    """La tabla copiada de «Valoraciones Periódicas de Desempeño» → [{"nombre", "val", "vf"}].

    En cada fila: el número de lista, el nombre (Apellidos Nombres), las notas, la Val, la letra (S, A, B, Bj), VF y VRA."""
    out = []
    for line in str(text or "").splitlines():
        line = line.replace(" ", " ").strip()
        m = re.match(r"^(?:\d{1,3}[.)]?\s+)?([A-Za-zÁÉÍÓÚÑÜáéíóúñü][A-Za-zÁÉÍÓÚÑÜáéíóúñü'´ .-]*?)(?=\s*(?:\t|\s(?:Nvo|Rei|Ret|Ing)\b|\s\d|$))", line)
        if not m:
            continue
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        if len(name.split()) < 2 or _plain(name).startswith(("apellidos", "estudiante", "nombre")):
            continue
        toks = [x for x in re.split(r"[\s\t]+", line[m.end():]) if x]
        idx = max((i for i, x in enumerate(toks) if x.upper() in _LETTERS), default=None)
        num = lambda x: float(x.replace(",", ".")) if _NUM.match(x) else None
        val = vf = None
        if idx is not None:
            before = [num(x) for x in toks[:idx] if num(x) is not None]
            after = [num(x) for x in toks[idx + 1:] if num(x) is not None]
            val = before[-1] if before else None
            vf = after[0] if after else None
        if val is None and vf is None:
            continue
        if val is not None and not 1.0 <= val <= 5.0:
            continue
        out.append({"nombre": name, "val": val, "vf": vf})
    return out
