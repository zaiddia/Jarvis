"""Reto matemático de la semana (11.1): tres preguntas (bronce, plata y oro) en el celular, puntos, insignias y ranking.

Puntos: bronce 1, plata 2, oro 3 (a la primera; con un segundo intento, la mitad); +1 al primero en resolver todo;
+1 por cada semana seguida participando desde la tercera. Insignias: Oro, Perfecto, Primero, Racha 3, Racha 5, Mejora.
Datos de estudiantes: se cifran con los demás si lo activaste. Lógica pura.
"""
import datetime
import os
import threading

import datos

_lock = threading.Lock()
_path = None
data = {"retos": {}, "puntos": {}}   # retos: {curso: {"code", "semana", "tema", "preguntas", "respuestas": {est: {q: {"ok", "intentos"}}}, "orden": [est], "cerrado"}}
locked = False                        # puntos: {curso: {est: {"total", "semanas": {semana: pts}, "insignias": [..]}}}
LEVELS = (("Bronce", 1), ("Plata", 2), ("Oro", 3))
BADGES = {"oro": "🥇 Oro", "perfecto": "💯 Perfecto", "primero": "⚡ Primero", "racha3": "🔥 Racha 3", "racha5": "🔥🔥 Racha 5", "mejora": "📈 Mejora"}


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "retos.json")
    load()


def load():
    global data, locked
    try:
        d = datos.read_json(_path)
        data, locked = (d if isinstance(d, dict) and "retos" in d else {"retos": {}, "puntos": {}}), False
        data.setdefault("puntos", {})
    except datos.DataLocked:
        data, locked = {"retos": {}, "puntos": {}}, True
    except (OSError, ValueError, TypeError):
        data = {"retos": {}, "puntos": {}}


def save():
    if not _path or locked:
        return
    try:
        datos.write_json(_path, data)
    except OSError:
        pass


def week_id(today=None):
    y, w, _ = (today or datetime.date.today()).isocalendar()
    return f"{y}-S{w:02d}"


def prompt(grado, tema, asignatura="Matemáticas"):
    return (f"Crea el reto de la semana de {asignatura} para estudiantes de grado {grado} en Colombia" + (f", sobre {tema}" if tema else "") +
            ": tres problemas de opción múltiple (4 opciones, una correcta) de dificultad creciente: bronce (accesible), plata (pide pensar) y "
            "oro (desafiante, tipo olimpiada escolar). Que sean retadores pero justos, con situaciones interesantes. La explicación es corta. "
            'Responde SOLO con JSON: {"tema": str, "preguntas": [{"nivel": "Bronce", "enunciado": str, "opciones": [str, str, str, str], '
            '"respuesta": "a"|"b"|"c"|"d", "explicacion": str}]}')


def clean(d):
    if not isinstance(d, dict):
        raise ValueError("el reto no vino en el formato esperado")
    qs = []
    for i, q in enumerate((d.get("preguntas") or [])[:3]):
        if not isinstance(q, dict):
            continue
        ops = [str(o).strip()[:300] for o in (q.get("opciones") or [])][:4]
        ans = str(q.get("respuesta", "")).strip().lower()[:1]
        if len(ops) == 4 and all(ops) and ans in "abcd" and ans and str(q.get("enunciado", "")).strip():
            qs.append({"nivel": LEVELS[len(qs)][0], "enunciado": str(q["enunciado"]).strip()[:900], "opciones": ops,
                       "respuesta": "abcd".index(ans), "explicacion": str(q.get("explicacion", ""))[:400]})
    if len(qs) < 3:
        raise ValueError("el reto necesita tres preguntas válidas")
    return {"tema": str(d.get("tema") or "")[:100], "preguntas": qs}


def open_challenge(curso, code, reto, today=None):
    with _lock:
        data["retos"][curso] = {"code": code, "semana": week_id(today), "tema": reto["tema"], "preguntas": reto["preguntas"], "respuestas": {},
                                "orden": [], "cerrado": False, "abierto": datetime.datetime.now().isoformat(timespec="minutes")}
        save()
    return data["retos"][curso]


def answer(curso, est, q, opcion):
    """→ {"ok": bool, "fin": bool (ya no puede reintentar), "puntos"}. Dos intentos por pregunta."""
    r = data["retos"].get(curso)
    if not r or r["cerrado"] or not 0 <= q < len(r["preguntas"]):
        return None
    with _lock:
        st = r["respuestas"].setdefault(est, {})
        cur = st.get(str(q))
        if cur and (cur["ok"] or cur["intentos"] >= 2):
            return {"ok": cur["ok"], "fin": True, "repetida": True}
        ok = int(opcion) == r["preguntas"][q]["respuesta"]
        cur = {"ok": ok, "intentos": (cur["intentos"] if cur else 0) + 1}
        st[str(q)] = cur
        if all(st.get(str(i), {}).get("ok") for i in range(len(r["preguntas"]))) and est not in r["orden"]:
            r["orden"].append(est)
        save()
    return {"ok": ok, "fin": ok or cur["intentos"] >= 2}


def points_for(st, n_q=3):
    pts = 0.0
    for i in range(n_q):
        a = st.get(str(i))
        if a and a["ok"]:
            pts += LEVELS[i][1] * (1 if a["intentos"] == 1 else 0.5)
    return pts


def close(curso):
    """Cierra el reto de la semana: suma puntos e insignias. → [(est, puntos de la semana, [insignias nuevas])] ordenado."""
    r = data["retos"].get(curso)
    if not r or r["cerrado"]:
        return []
    out = []
    with _lock:
        tab = data["puntos"].setdefault(curso, {})
        for est, st in r["respuestas"].items():
            p = tab.setdefault(est, {"total": 0.0, "semanas": {}, "insignias": []})
            pts = points_for(st, len(r["preguntas"]))
            if r["orden"] and r["orden"][0] == est:
                pts += 1
            weeks = sorted(set(p["semanas"]) | {r["semana"]})
            streak = _streak(weeks, r["semana"])
            if streak >= 3:
                pts += 1
            prev = [v for k, v in sorted(p["semanas"].items()) if k < r["semana"]][-3:]
            p["semanas"][r["semana"]] = pts
            p["total"] = round(sum(p["semanas"].values()), 1)
            new = []
            def give(b):
                if b not in p["insignias"]:
                    p["insignias"].append(b)
                    new.append(BADGES[b])
            if st.get("2", {}).get("ok"):
                give("oro")
            if all(st.get(str(i), {}).get("ok") and st[str(i)]["intentos"] == 1 for i in range(len(r["preguntas"]))):
                give("perfecto")
            if r["orden"] and r["orden"][0] == est:
                give("primero")
            if streak >= 3:
                give("racha3")
            if streak >= 5:
                give("racha5")
            if prev and pts > max(prev) + 1:
                give("mejora")
            out.append((est, pts, new))
        r["cerrado"] = True
        save()
    return sorted(out, key=lambda x: -x[1])


def _streak(weeks, current):
    """Semanas seguidas participando hasta la actual («2026-S44», «2026-S43»…)."""
    def prev(w):
        y, n = int(w[:4]), int(w[-2:])
        d = datetime.date.fromisocalendar(y, n, 1) - datetime.timedelta(days=7)
        return week_id(d)
    s, w, have = 0, current, set(weeks)
    while w in have:
        s += 1
        w = prev(w)
    return s


def ranking(curso, n=10):
    tab = data["puntos"].get(curso, {})
    return sorted(({"nombre": k, "total": v["total"], "insignias": [BADGES[b] for b in v["insignias"] if b in BADGES]} for k, v in tab.items()),
                  key=lambda x: -x["total"])[:n]
