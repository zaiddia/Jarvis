"""Clase en vivo (9.6): Jarvis conduce la clase contigo, momento a momento, con el plan de clase y el proyector.

«Empieza la clase de fracciones»: toma tu plan (o lo prepara), muestra en el proyector la pregunta de enganche, el
momento actual con sus actividades y su cuenta regresiva, y al final propone el ticket de salida y anota el diario de
clase. «Siguiente momento», «dame 5 minutos más», «termina la clase».

También guarda las actividades que funcionaron (según el ticket de salida o el semáforo) para proponerlas otra vez.
"""
import datetime
import json
import os
import re
import threading
import unicodedata

_lock = threading.Lock()
_path = None
data = {"planes": [], "actividades": []}     # planes: últimos planes de clase; actividades: lo que funcionó


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "clases.json")
    load()


def load():
    global data
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        data = d if isinstance(d, dict) else {}
    except (OSError, ValueError, TypeError):
        data = {}
    data.setdefault("planes", [])
    data.setdefault("actividades", [])


def save():
    if not _path:
        return
    try:
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        with open(_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(_path + ".tmp", _path)
    except OSError:
        pass


def remember_plan(m, curso=""):
    with _lock:
        data["planes"].append({"tema": m.get("tema") or m.get("titulo", ""), "titulo": m.get("titulo", ""), "curso": curso,
                               "objetivo": m.get("objetivo", ""), "momentos": m.get("momentos", []),
                               "fecha": datetime.date.today().isoformat()})
        del data["planes"][:-30]
        save()


def find_plan(tema):
    w = {x for x in norm(tema).split() if len(x) > 3}
    best, score = None, 0
    for p in reversed(data["planes"]):
        pw = set(norm(p["tema"] + " " + p["titulo"]).split())
        sc = len(w & pw)
        if sc > score:
            best, score = p, sc
    return best if (score and score >= max(1, len(w) // 2)) else None


def minutes(text, default=10):
    m = re.search(r"(\d{1,3})\s*(?:min|minutos)", norm(text))
    return max(1, min(120, int(m.group(1)))) if m else default


def steps(plan):
    """[{"nombre", "min", "actividades"}] a partir de los momentos del plan."""
    out = []
    for mo in plan.get("momentos") or []:
        out.append({"nombre": mo.get("nombre", "Momento"), "min": minutes(mo.get("duracion", ""), 15),
                    "actividades": mo.get("actividades", "")})
    return out or [{"nombre": "Clase", "min": 50, "actividades": plan.get("objetivo", "")}]


def hook_question(plan):
    """La pregunta de enganche: la primera pregunta del momento de inicio (o una genérica sobre el tema)."""
    first = (plan.get("momentos") or [{}])[0].get("actividades", "")
    q = re.findall(r"¿[^?]{8,200}\?", first)
    return q[0] if q else f"¿Qué sabes sobre {plan.get('tema') or 'el tema de hoy'}? ¿Dónde lo ves en tu vida diaria?"


def record_outcome(tema, curso, actividades, resultado):
    """Guarda cómo le fue a una actividad (resultado: % de aciertos del ticket, o % en verde del semáforo)."""
    with _lock:
        data["actividades"].append({"tema": tema, "curso": curso, "actividad": str(actividades)[:600], "resultado": resultado,
                                    "fecha": datetime.date.today().isoformat()})
        del data["actividades"][:-200]
        save()


def worked(tema, minimo=70, n=3):
    w = {x for x in norm(tema).split() if len(x) > 3}
    hits = [a for a in data["actividades"] if a["resultado"] is not None and a["resultado"] >= minimo and w & set(norm(a["tema"]).split())]
    return sorted(hits, key=lambda a: -a["resultado"])[:n]


def worked_ctx(tema):
    hits = worked(tema)
    if not hits:
        return ""
    return (" Actividades que ya funcionaron con este docente en este tema (reutilízalas o adáptalas si encajan): " +
            " | ".join(f"{a['actividad'][:200]} ({a['resultado']} %)" for a in hits))
