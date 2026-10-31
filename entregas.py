"""Entregas de programación para Tecnología e Informática (11.1). Lógica pura, sin Jarvis.

Los estudiantes envían desde el celular su código (Python, pseudocódigo/PSeInt, JavaScript…) o la foto de su diagrama
de flujo o de su programa en Scratch. Jarvis lo revisa con la IA SIN ejecutarlo: qué funciona, el error explicado sin
darle la solución, una pista y una nota sugerida (de 1,0 a 5,0) que solo ve el docente. Puede reintentar (hasta 3).
Son datos de estudiantes: se cifran con los demás si lo activaste.
"""
import datetime
import os
import re
import threading

import datos

_lock = threading.Lock()
_path = None
data = {"tareas": {}}          # {id: {"curso", "consigna", "creado", "cerrada", "entregas": {est: [{"t", "tipo", "lenguaje", "texto", "rev"}]}}}
locked = False
MAX_TRIES = 3
LANGS = ("Python", "Pseudocódigo / PSeInt", "JavaScript", "Scratch (foto)", "Diagrama de flujo (foto)", "Otro")


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "entregas.json")
    load()


def load():
    global data, locked
    try:
        d = datos.read_json(_path)
        data, locked = (d if isinstance(d, dict) and isinstance(d.get("tareas"), dict) else {"tareas": {}}), False
    except datos.DataLocked:
        data, locked = {"tareas": {}}, True
    except (OSError, ValueError, TypeError):
        data = {"tareas": {}}


def save():
    if not _path or locked:
        return
    try:
        datos.write_json(_path, data)
    except OSError:
        pass


def new_task(tid, curso, consigna):
    with _lock:
        data["tareas"][tid] = {"curso": curso, "consigna": str(consigna or "").strip()[:1500], "creado": datetime.datetime.now().isoformat(timespec="minutes"),
                               "cerrada": False, "entregas": {}}
        save()
    return data["tareas"][tid]


def tries(task, est):
    return len(task["entregas"].get(est, []))


def add(task, est, tipo, lenguaje, texto, rev):
    with _lock:
        task["entregas"].setdefault(est, []).append({"t": datetime.datetime.now().isoformat(timespec="seconds"), "tipo": tipo,
                                                     "lenguaje": str(lenguaje)[:40], "texto": str(texto or "")[:12000], "rev": rev})
        save()


def best(task, est):
    """La mejor revisión de un estudiante (la de nota más alta; si empatan, la última)."""
    lst = [e for e in task["entregas"].get(est, []) if e.get("rev")]
    if not lst:
        return None
    return max(enumerate(lst), key=lambda x: ((x[1]["rev"].get("nota") or 0), x[0]))[1]


def review_prompt(consigna, lenguaje, codigo, grado="", foto=False):
    que = ("la foto de su " + ("programa en Scratch" if "scratch" in lenguaje.lower() else "diagrama de flujo o código")) if foto else f"su código ({lenguaje})"
    return ("Eres un docente de Tecnología e Informática en Colombia revisando " + que + f" de un estudiante{(' de grado ' + grado) if grado else ''}. "
            + (f"La tarea es: «{consigna}». " if consigna else "")
            + "NO ejecutes nada: analiza la lógica a mano. Sé claro y amable, en español sencillo. NUNCA escribas la solución completa ni el código "
              "corregido: explica el error y da una pista para que él mismo lo arregle. "
            + ("" if foto else f"\nCódigo del estudiante:\n```\n{codigo[:6000]}\n```\n")
            + 'Responde SOLO con JSON: {"funciona": bool, "bien": [str], "errores": [{"donde": str, "que": str}], "pista": str, '
              '"nota": number (1.0 a 5.0, 3.0 aprueba; cumple la tarea, lógica, orden y buenas prácticas), "para_docente": str}')


def validate(d):
    if not isinstance(d, dict):
        raise ValueError("la revisión no vino en el formato esperado")
    try:
        nota = max(1.0, min(5.0, round(float(d.get("nota")), 1)))
    except (TypeError, ValueError):
        nota = None
    errs = [{"donde": str(e.get("donde", ""))[:120], "que": str(e.get("que", ""))[:400]} for e in (d.get("errores") or []) if isinstance(e, dict)][:6]
    return {"funciona": bool(d.get("funciona")), "bien": [str(x)[:300] for x in (d.get("bien") or [])][:5], "errores": errs,
            "pista": str(d.get("pista") or "")[:500], "nota": nota, "para_docente": str(d.get("para_docente") or "")[:600]}


def leaks_solution(rev, codigo=""):
    """¿La pista trae código completo? (bloques largos con varias líneas de código): entonces se recorta."""
    txt = rev.get("pista", "") + " " + " ".join(e["que"] for e in rev.get("errores", []))
    return bool(re.search(r"```", txt)) or len(re.findall(r"(?m)^\s*(?:for|while|if|def|print|leer|escribir|mientras|si)\b.*$", txt)) >= 3


def summary(task, names):
    rows = []
    for n in names:
        b = best(task, n)
        rows.append({"nombre": n, "intentos": tries(task, n), "nota": b["rev"]["nota"] if b else None, "funciona": b["rev"]["funciona"] if b else None})
    return rows
