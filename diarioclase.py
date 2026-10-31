"""Diario de clase (8.8): qué se vio en cada clase, y qué temas de la malla del periodo faltan.

«Hoy en 7A vimos fracciones equivalentes», «¿qué vimos en 7A?», «¿qué temas me faltan del periodo en 7A?». La malla
de cada curso se guarda sola cuando Jarvis te la prepara («haz la malla curricular…»). El registro se puede exportar a
Excel para pasarlo al registro de clase de la plataforma del colegio.
"""
import datetime
import json
import os
import re
import threading
import unicodedata

import datos

_lock = threading.Lock()
_path = None
data = {"registro": {}, "mallas": {}}     # registro: {curso: [{"fecha", "tema", "nota"}]}; mallas: {curso: malla}
STOP = {"para", "como", "entre", "sobre", "desde", "hasta", "segun", "cada", "tema", "temas", "clase", "unidad", "semana",
        "introduccion", "repaso", "practica", "ejercicios", "taller", "evaluacion", "conceptos", "basicos"}


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "registro_clase.json")
    load()


locked = False      # 8.9: cifrado con otra clave: no se lee ni se sobrescribe


def load():
    global data, locked
    try:
        d = datos.read_json(_path)
        data, locked = (d if isinstance(d, dict) else {}), False
    except datos.DataLocked:
        data, locked = {}, True
    except (OSError, ValueError, TypeError):
        data = {}
    data.setdefault("registro", {})
    data.setdefault("mallas", {})


def save():
    if not _path or locked:
        return
    try:
        datos.write_json(_path, data)
    except OSError:
        pass


def add(curso, tema, fecha=None, nota=""):
    tema = str(tema).strip().rstrip(".")
    tema = tema[:1].upper() + tema[1:]
    with _lock:
        data["registro"].setdefault(curso, []).append({"fecha": (fecha or datetime.date.today()).isoformat(),
                                                       "tema": tema[:300], "nota": str(nota)[:300]})
        save()
    return data["registro"][curso][-1]


def entries(curso):
    return list(data["registro"].get(curso, []))


def set_malla(curso, malla):
    with _lock:
        data["mallas"][curso] = {"titulo": malla.get("titulo", ""), "periodo": malla.get("periodo", ""),
                                 "semanas": [{"semana": s["semana"], "tema": s["tema"]} for s in malla.get("semanas", [])],
                                 "fecha": datetime.date.today().isoformat()}
        save()


def _words(t):
    return {w for w in norm(t).split() if len(w) > 3 and w not in STOP}


def covered(tema, registro):
    """¿Algún registro trata este tema? (comparte la mitad o más de sus palabras importantes)."""
    w = _words(tema)
    if not w:
        return False
    for r in registro:
        rw = _words(r["tema"])
        stems = {x[:6] for x in rw}
        hits = sum(1 for x in w if x in rw or x[:6] in stems)
        if hits >= max(1, (len(w) + 1) // 2):
            return True
    return False


def pending(curso):
    """(temas vistos, temas que faltan) según la malla guardada del curso. None si no hay malla."""
    m = data["mallas"].get(curso)
    if not m:
        return None
    reg = entries(curso)
    seen, missing = [], []
    for s in m["semanas"]:
        (seen if covered(s["tema"], reg) else missing).append(s)
    return seen, missing


def export_xlsx(curso, out_dir):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Registro de clase"
    ws.append(["Fecha", "Curso", "Tema", "Observación"])
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in entries(curso):
        ws.append([r["fecha"], curso, r["tema"], r.get("nota", "")])
    ws.column_dimensions["C"].width = 60
    ws.column_dimensions["D"].width = 40
    folder = os.path.join(out_dir, "Exportaciones")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"Registro de clase {curso} {datetime.date.today():%Y-%m-%d}.xlsx")
    wb.save(path)
    return path
