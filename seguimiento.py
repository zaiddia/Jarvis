"""Seguimiento por estudiante (7.8): notas, promedio, fallas y alertas de riesgo.

«Ponle 4,5 a Juan Pérez en el quiz de fracciones de 7A», «¿cómo va Juan en 7A?», «¿quiénes están en riesgo en 7A?».
Las notas van en la escala colombiana (1.0 a 5.0). Las fallas se toman de la asistencia del aula. También se pueden
traer las notas de Google Classroom.
"""
import datetime
import json
import os
import re
import threading
import unicodedata

import datos
import zeti

_lock = threading.Lock()
_path = None
data = {}           # {curso: {estudiante: [{"actividad", "nota", "fecha", "origen"}]}}


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "notas_estudiantes.json")
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


def save():
    if not _path or locked:
        return
    try:
        datos.write_json(_path, data)
    except OSError:
        pass


def parse_grade(text):
    """«4,5», «4.5», «cuatro cinco», «tres» → 4.5 / 3.0. None si no hay nota válida (1.0 a 5.0)."""
    t = norm(text).replace(",", ".")
    m = re.search(r"\b([1-5])(?:[.\s]([0-9]))?\b", t)
    words = {"uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "cero": 0, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9}
    if m:
        v = float(m.group(1)) + (int(m.group(2)) / 10 if m.group(2) else 0)
    else:
        w = re.search(r"\b(uno|dos|tres|cuatro|cinco)(?:\s+(?:punto|coma|con)?\s*(cero|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve))?\b", t)
        if not w:
            return None
        v = words[w.group(1)] + (words[w.group(2)] / 10 if w.group(2) else 0)
    return v if 1.0 <= v <= 5.0 else None


def add(curso, estudiante, actividad, nota, origen="voz", fecha=None, dim=None):
    with _lock:
        lst = data.setdefault(curso, {}).setdefault(estudiante, [])
        act = str(actividad or "nota").strip()[:80]
        lst[:] = [x for x in lst if not (norm(x["actividad"]) == norm(act) and x.get("origen") == origen and origen != "voz")]
        it = {"actividad": act, "nota": round(float(nota), 1), "fecha": (fecha or datetime.date.today()).isoformat(), "origen": origen}
        if dim in zeti.WEIGHTS:                         # 10.1: Conocer, Hacer, Ser o Autoevaluación (si no, se deduce)
            it["dim"] = dim
        lst.append(it)
        save()


def average(curso, estudiante):
    """10.1: la valoración como la calcula Zeti (Conocer, Hacer, Ser y Autoevaluación con sus pesos)."""
    return zeti.valoracion(data.get(curso, {}).get(estudiante, []))["val"]


def report(curso, estudiante, faltas=0):
    lst = data.get(curso, {}).get(estudiante, [])
    avg = average(curso, estudiante)
    if not lst:
        txt = f"{estudiante} aún no tiene notas en {curso}"
    else:
        last = lst[-1]
        txt = (f"{estudiante} en {curso}: promedio {str(avg).replace('.', ',')} con {len(lst)} nota{'s' if len(lst) != 1 else ''}; "
               f"la última, {str(last['nota']).replace('.', ',')} en {last['actividad']}")
    if faltas:
        txt += f". Tiene {faltas} falla{'s' if faltas != 1 else ''}"
    return txt + "."


def at_risk(curso, names, absences, min_grade=3.0, max_absences=3):
    """[(estudiante, motivos)] de quienes están en riesgo en el curso."""
    out = []
    for n in names:
        why = []
        avg = average(curso, n)
        if avg is not None and avg < min_grade:
            why.append(f"promedio {str(avg).replace('.', ',')}")
        f = absences.get(n, 0)
        if f >= max_absences:
            why.append(f"{f} fallas")
        if why:
            out.append((n, why))
    return out


def spoken_risk(curso, risk):
    if not risk:
        return f"En {curso} nadie está en riesgo ahora mismo."
    items = [f"{n} ({' y '.join(w)})" for n, w in risk[:8]]
    return f"En {curso} hay {len(risk)} estudiante{'s' if len(risk) != 1 else ''} en riesgo: " + "; ".join(items) + "."


_GRADE_RE = re.compile(r"^(?:ponle|pon(?:le)?|anota(?:le)?|registra(?:le)?|califica(?:le)?\s+con|dale)\s+(?:un|una|nota\s+de\s+)?\s*(.+?)\s+a\s+(.+?)"
                       r"(?:\s+(?:en|por)\s+(?:el|la|los|las)?\s*(.+?))?(?:\s+de\s+(\d{1,2}\s?[a-z]|\d{1,2}|[a-z]+\s+[a-z]))?$")


def parse_voice_grade(t):
    """«ponle 4,5 a juan perez en el quiz de fracciones de 7a» → (nota, estudiante, actividad, curso o "")."""
    m = _GRADE_RE.match(t)
    if not m:
        return None
    nota = parse_grade(m.group(1))
    if nota is None:
        return None
    return nota, m.group(2).strip(), (m.group(3) or "nota").strip(), (m.group(4) or "").strip()
