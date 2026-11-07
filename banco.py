"""Banco de preguntas (7.8): cada quiz que Jarvis crea guarda sus preguntas para reutilizarlas.

«¿Cuántas preguntas tengo de fracciones?», «haz un quiz de 10 preguntas de fracciones con el banco» (sin IA, al
instante, mezclando preguntas de quizzes anteriores). Las preguntas iguales no se repiten.
"""
import json
import os
import random
import re
import threading
import unicodedata

_lock = threading.Lock()
_path = None
items = []          # [{"enunciado", "opciones", "respuesta", "explicacion", "tema", "grado", "usos"}]
MAX = 3000


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "banco_preguntas.json")
    load()


def load():
    global items
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        items = d if isinstance(d, list) else []
    except (OSError, ValueError, TypeError):
        items = []


def save():
    if not _path:
        return
    try:
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        with open(_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
        os.replace(_path + ".tmp", _path)
    except OSError:
        pass


def add_quiz(m):
    """Guarda las preguntas de un quiz (el formato de aula.validate). Devuelve cuántas nuevas."""
    tema, grado = str(m.get("tema") or m.get("titulo") or "").strip(), str(m.get("grado") or "").strip()
    new = 0
    with _lock:
        seen = {norm(q["enunciado"]) for q in items}
        for q in m.get("preguntas") or []:
            k = norm(q.get("enunciado", ""))
            if not k or k in seen:
                continue
            items.append({"enunciado": q["enunciado"], "opciones": list(q["opciones"])[:4], "respuesta": q["respuesta"],
                          "explicacion": q.get("explicacion", ""), "tema": tema, "grado": grado, "usos": 0})
            seen.add(k)
            new += 1
        del items[:-MAX]
        save()
    return new


def search(tema, grado="", n=None):
    """Preguntas del tema (por palabras del tema y del enunciado), las menos usadas primero."""
    words = [w for w in norm(tema).split() if len(w) > 3]
    g = norm(grado)
    scored = []
    for q in items:
        hay = norm(q["tema"] + " " + q["enunciado"])
        sc = sum(1 for w in words if w in hay or (len(w) > 5 and w[:-1] in hay))
        if words and sc == 0:
            continue
        if g and q["grado"] and g not in norm(q["grado"]) and norm(q["grado"]) not in g:
            sc -= 0.5
        scored.append((sc, -q.get("usos", 0), random.random(), q))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    out = [q for *_, q in scored]
    return out[:n] if n else out


def build_quiz(tema, n=10, grado=""):
    """Un quiz armado con el banco (formato de aula.validate) o None si no hay suficientes preguntas."""
    qs = search(tema, grado, n)
    if not qs:
        return None
    with _lock:
        for q in qs:
            q["usos"] = q.get("usos", 0) + 1
        save()
    pick = [dict(enunciado=q["enunciado"], opciones=q["opciones"], respuesta=q["respuesta"], explicacion=q.get("explicacion", ""))
            for q in qs]
    random.shuffle(pick)
    return {"titulo": f"Evaluación: {tema}", "grado": grado or (qs[0].get("grado") or ""), "tema": tema,
            "instrucciones": "Lee cada pregunta y marca con una X la única respuesta correcta.", "preguntas": pick}


def count(tema=""):
    return len(search(tema)) if tema else len(items)


# ============================================================================ 12.12: DIFICULTAD MEDIDA CON TUS ESTUDIANTES
MIN_N = 5                                                # con menos respuestas no se juzga la dificultad
LEVELS = ("fácil", "media", "difícil")


def level(q):
    """fácil (la acierta ≥ 75 %), media, difícil (< 40 %), o "" si aún no hay suficientes respuestas."""
    n, ok = int(q.get("n") or 0), int(q.get("ok") or 0)
    if n < MIN_N:
        return ""
    p = ok / n
    return "fácil" if p >= 0.75 else "difícil" if p < 0.40 else "media"


def refresh_stats(exams):
    """Recalcula aciertos por pregunta con TODAS las evaluaciones corregidas (sin contar dos veces). → preguntas con datos."""
    acc = {}
    for ex in exams:
        pregs = ex.get("preguntas") or []
        for r in (ex.get("resultados") or {}).values():
            for i, ok in enumerate(r.get("detalle") or []):
                if ok is None or i >= len(pregs):
                    continue
                k = norm((pregs[i] or {}).get("enunciado", "") if isinstance(pregs[i], dict) else pregs[i])
                if k:
                    a = acc.setdefault(k, [0, 0])
                    a[0] += 1
                    a[1] += 1 if ok else 0
    n = 0
    with _lock:
        for q in items:
            a = acc.get(norm(q["enunciado"]))
            if a:
                q["n"], q["ok"] = a
                n += 1
        save()
    return n


def difficulty_counts(tema=""):
    qs = search(tema) if tema else items
    c = {lv: 0 for lv in LEVELS}
    c["sin datos"] = 0
    for q in qs:
        c[level(q) or "sin datos"] += 1
    return c


def build_balanced(tema, n=10, grado="", mix=(0.3, 0.5, 0.2)):
    """Un examen con 30 % fáciles, 50 % medias y 20 % difíciles (completa con preguntas sin datos). → quiz o None."""
    qs = search(tema, grado)
    if len(qs) < n:
        return None
    by = {lv: [q for q in qs if level(q) == lv] for lv in LEVELS}
    want = [round(n * m) for m in mix]
    want[1] = n - want[0] - want[2]
    pick = []
    for lv, k in zip(LEVELS, want):
        pick += by[lv][:k]
    rest = [q for q in qs if q not in pick]
    rest.sort(key=lambda q: (level(q) == "", q.get("usos", 0)))
    pick += rest[:n - len(pick)]
    with _lock:
        for q in pick:
            q["usos"] = q.get("usos", 0) + 1
        save()
    out = [dict(enunciado=q["enunciado"], opciones=q["opciones"], respuesta=q["respuesta"], explicacion=q.get("explicacion", "")) for q in pick]
    order = {"fácil": 0, "media": 1, "difícil": 2, "": 1}
    out.sort(key=lambda d: order[level(next(q for q in pick if q["enunciado"] == d["enunciado"]))])     # de la más fácil a la más difícil
    counts = {lv: sum(1 for q in pick if level(q) == lv) for lv in LEVELS}
    return {"titulo": f"Evaluación: {tema}", "grado": grado or (pick[0].get("grado") or ""), "tema": tema,
            "instrucciones": "Lee cada pregunta y marca con una X la única respuesta correcta.", "preguntas": out, "niveles": counts}
