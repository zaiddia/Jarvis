"""Ticket de salida y semáforo de comprensión (9.6): los estudiantes responden en su celular, en la red del colegio.

En el proyector aparece un código QR. Cada estudiante abre la página (sin cuenta), escribe su nombre y responde. Jarvis
cuenta al momento qué porcentaje acertó cada pregunta y quién necesita refuerzo. La página de los estudiantes solo
funciona mientras el ticket está abierto y con su código; no muestra nada de Jarvis ni de otros estudiantes.
"""
import datetime
import re
import secrets
import threading
import time

_lock = threading.Lock()
SEMAFORO = {"enunciado": "¿Cómo te fue con el tema de hoy?", "opciones": ["🟢 Lo entendí bien", "🟡 Tengo algunas dudas", "🔴 No lo entendí"],
            "respuesta": None}
state = {"open": False, "code": "", "tipo": "", "tema": "", "curso": "", "preguntas": [], "respuestas": {}, "abierto": 0.0,
         "ips": {}}


def open_ticket(preguntas, tipo="ticket", tema="", curso=""):
    with _lock:
        state.update(open=True, code=secrets.token_urlsafe(5)[:6].replace("-", "x").replace("_", "y"), tipo=tipo, tema=tema,
                     curso=curso, preguntas=preguntas, respuestas={}, abierto=time.time(), ips={})
    return state["code"]


def from_quiz(quiz, n=2):
    """Las primeras n preguntas de un quiz (formato de aula) para el ticket."""
    out = []
    for q in (quiz.get("preguntas") or [])[:n]:
        out.append({"enunciado": q["enunciado"], "opciones": list(q["opciones"])[:4], "respuesta": "abcd".find(q["respuesta"])})
    return out


def public(code):
    """Lo que ve el estudiante (sin las respuestas correctas). None si el código no sirve."""
    if not state["open"] or code != state["code"]:
        return None
    return {"tipo": state["tipo"], "tema": state["tema"], "preguntas": [{"enunciado": q["enunciado"], "opciones": q["opciones"]}
                                                                         for q in state["preguntas"]]}


def _clean_name(n):
    n = re.sub(r"[^\w\sáéíóúñüÁÉÍÓÚÑÜ.-]", "", str(n)).strip()
    return re.sub(r"\s+", " ", n)[:40]


def submit(code, nombre, respuestas, ip=""):
    """Guarda las respuestas. Devuelve (ok, mensaje)."""
    if not state["open"] or code != state["code"]:
        return False, "Este ticket ya se cerró."
    nombre = _clean_name(nombre)
    if len(nombre) < 2:
        return False, "Escribe tu nombre."
    try:
        ans = [int(x) for x in respuestas][:len(state["preguntas"])]
    except (TypeError, ValueError):
        return False, "Respuesta no válida."
    if len(ans) != len(state["preguntas"]) or any(not 0 <= a < len(q["opciones"]) for a, q in zip(ans, state["preguntas"])):
        return False, "Responde todas las preguntas."
    with _lock:
        n_ip = state["ips"].get(ip, 0)
        key = nombre.lower()
        if key not in state["respuestas"] and n_ip >= 3:
            return False, "Ya se enviaron varias respuestas desde este celular."
        if key not in state["respuestas"]:
            state["ips"][ip] = n_ip + 1
        if len(state["respuestas"]) >= 80 and key not in state["respuestas"]:
            return False, "El ticket ya está lleno."
        state["respuestas"][key] = {"nombre": nombre, "r": ans, "t": datetime.datetime.now().strftime("%H:%M:%S")}
    return True, "¡Gracias! Tu respuesta quedó guardada."


def results():
    """Resumen: por pregunta (% correcto o conteo por opción) y quién necesita refuerzo."""
    rs = list(state["respuestas"].values())
    per = []
    for i, q in enumerate(state["preguntas"]):
        counts = [0] * len(q["opciones"])
        for r in rs:
            counts[r["r"][i]] += 1
        ok = counts[q["respuesta"]] if q.get("respuesta") is not None and q["respuesta"] >= 0 else None
        per.append({"enunciado": q["enunciado"], "opciones": q["opciones"], "conteo": counts,
                    "correcta": q.get("respuesta"), "pct": round(100 * ok / len(rs)) if rs and ok is not None else None})
    refuerzo = []
    graded = [i for i, q in enumerate(state["preguntas"]) if q.get("respuesta") is not None and q["respuesta"] >= 0]
    if graded:
        for r in rs:
            hits = sum(1 for i in graded if r["r"][i] == state["preguntas"][i]["respuesta"])
            if hits < (len(graded) + 1) // 2:
                refuerzo.append(r["nombre"])
    sem = None
    if state["tipo"] == "semaforo" and rs:
        c = per[0]["conteo"]
        sem = {"verde": round(100 * c[0] / len(rs)), "amarillo": round(100 * c[1] / len(rs)), "rojo": round(100 * c[2] / len(rs))}
    total_pct = round(sum(p["pct"] for p in per if p["pct"] is not None) / max(1, sum(1 for p in per if p["pct"] is not None))) \
        if any(p["pct"] is not None for p in per) else None
    return {"n": len(rs), "preguntas": per, "refuerzo": sorted(refuerzo), "semaforo": sem, "pct": total_pct,
            "tipo": state["tipo"], "tema": state["tema"], "curso": state["curso"]}


def close():
    with _lock:
        state["open"] = False
    return results()


def spoken(res):
    if not res["n"]:
        return "Nadie respondió el ticket."
    if res["tipo"] == "semaforo" and res["semaforo"]:
        s = res["semaforo"]
        txt = f"Respondieron {res['n']}: {s['verde']} % lo entendió bien, {s['amarillo']} % tiene dudas y {s['rojo']} % no lo entendió."
        if s["rojo"] >= 30 or s["rojo"] + s["amarillo"] >= 60:
            txt += " Conviene repasar el tema en la próxima clase."
        return txt
    txt = f"Respondieron {res['n']}" + (f", con {res['pct']} % de aciertos" if res["pct"] is not None else "") + ". "
    txt += " ".join(f"Pregunta {i + 1}: {p['pct']} %." for i, p in enumerate(res["preguntas"]) if p["pct"] is not None)
    if res["refuerzo"]:
        txt += f" Necesitan refuerzo: {', '.join(res['refuerzo'][:10])}" + ("…" if len(res["refuerzo"]) > 10 else "") + "."
    return txt
