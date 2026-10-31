"""10.9: más HUD: línea del día (tus clases de hoy con botones rápidos), mapa del curso, modo clase, barra del año y
avisos con botones (en hud.js).

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import time

import asignaturas
import aula
import examenes
import horario
import semana
import seguimiento
import zeti
from nucleo import J


def _hp_mins(hhmm, now):
    h, m = map(int, hhmm.split(":"))
    return int((datetime.datetime.combine(now.date(), datetime.time(h, m)) - now).total_seconds() // 60)


def day_line(now=None):
    """Las clases de hoy: [{"inicio", "fin", "t", "curso", "estado": pasada|ahora|luego, "progreso", "acciones": [{t, cmd}]}]."""
    now = now or datetime.datetime.now()
    out = []
    for x in horario.today(now):
        a, b = _hp_mins(x["inicio"], now), _hp_mins(x["fin"], now)
        est = "pasada" if b <= 0 else "ahora" if a <= 0 else "luego"
        curso = x.get("curso", "")
        acts = [{"t": "Empezar clase", "cmd": f"empieza la clase en {curso}" if curso else "empieza la clase"},
                {"t": "Asistencia", "cmd": "llama a lista"},
                {"t": "Ticket de salida", "cmd": "lanza el ticket de salida"},
                {"t": "Práctica", "cmd": f"activa la práctica de {curso}" if curso else "activa la práctica"},
                {"t": "Calificar hojas", "cmd": "califica las hojas"}]
        if est == "luego":
            acts.insert(0, {"t": "Preparar", "cmd": f"prepárame la próxima clase de {curso}"})
        out.append({"inicio": x["inicio"], "fin": x["fin"], "t": horario.label(x), "curso": curso, "estado": est,
                    "progreso": round(min(1.0, max(0.0, -a / max(1, b - a))), 3) if est == "ahora" else (1.0 if est == "pasada" else 0.0),
                    "acciones": acts})
    return out


def year_bar(now=None):
    """Semana del año, periodo, cómo vas con la planeación y días para el cierre."""
    today = (now or datetime.datetime.now()).date()
    try:
        w, p, wp = J.where_now(today)
        wpp = J.year_weeks()
    except Exception:
        return None
    out = {"periodo": p, "periodos": wpp, "semana": w, "total": sum(wpp), "semana_periodo": wp,
           "cierre": semana.days_left(J.settings.get("period_end", ""), today)}
    if w is None and out["cierre"] is None:
        return None
    worst = None
    try:
        for k in J.anual.data["planes"]:
            st = J.plan_status(k)
            if st and st["semana_anio"] and (worst is None or st["diferencia"] < worst[1]):
                worst = (k, st["diferencia"])
    except Exception:
        worst = None
    out["plan"] = None if worst is None else {"curso": worst[0], "dif": worst[1]}
    return out


def in_class_panel():
    """Lo que está en vivo en el aula (clase conducida, ticket, práctica, calificación, quiz)."""
    lc = J.live_class
    out = {}
    if lc["on"] and lc["steps"]:
        st = lc["steps"][lc["i"]]
        out["clase"] = {"tema": lc["tema"], "curso": lc["curso"], "momento": st["nombre"], "i": lc["i"] + 1, "n": len(lc["steps"]),
                        "left": max(0, round(lc["end"] - time.time())), "min": st["min"]}
    qr = []
    if J.ticket.state["open"]:
        qr.append({"t": "Ticket" if J.ticket.state.get("tipo") != "semaforo" else "Semáforo", "n": len(J.ticket.state["respuestas"]),
                   "cmd": "cierra el ticket"})
    try:
        if J.ps.get("code"):
            qr.append({"t": f"Práctica {J.ps.get('curso', '')}".strip(), "n": len(J.ps.get("tokens", {})), "cmd": "cierra la práctica"})
    except Exception:
        pass
    try:
        if J.sess.get("code"):
            ex = examenes.get(J.sess["code"])
            if ex and not ex["cerrado"]:
                qr.append({"t": "Calificando", "n": len(ex["resultados"]), "de": len(ex["estudiantes"]), "cmd": "terminé de calificar"})
    except Exception:
        pass
    if qr:
        out["qr"] = qr
    return out or None


def hud_extras(now, out):
    out["dia"] = day_line(now)
    out["anio"] = year_bar(now)
    out["en_clase"] = in_class_panel()
    return out


def course_map(course):
    """El mapa del curso: estudiantes × actividades (las 12 más recientes), con Val y letra, para el HUD."""
    key = J._resolve_course(course) if course not in seguimiento.data else course
    grades = seguimiento.data.get(key, {})
    names = list(aula.students(key))
    names += [n for n in grades if n not in names]
    acts, seen = [], set()
    for n in names:
        for g in sorted(grades.get(n, []), key=lambda g: g.get("fecha", "")):
            k = (g.get("fecha", "")[:10], g["actividad"])
            if k not in seen:
                seen.add(k)
                acts.append(k)
    acts = sorted(acts)[-12:]
    rows = []
    for n in names:
        by = {(g.get("fecha", "")[:10], g["actividad"]): g["nota"] for g in grades.get(n, [])}
        v = zeti.valoracion(grades.get(n, []), zeti.WEIGHTS)
        rows.append({"n": n, "c": [by.get(a) for a in acts], "val": v["val"], "letra": v["letra"]})
    rows.sort(key=lambda r: (r["val"] is None, r["val"] if r["val"] is not None else 0))
    return {"curso": key, "acts": [{"f": f[5:].replace("-", "/") if f else "", "a": a[:30],
                                    "dim": zeti.infer_dim(a)} for f, a in acts], "rows": rows,
            "escala": dict(zeti.SCALE)}


@J.socketio.on("course_map")
def handle_course_map(data=None):
    c = str((data or {}).get("curso") or "")
    if not c:
        return {"cursos": sorted(set(seguimiento.data) | set(aula.data.get("cursos", {})), key=aula.course_sort_key)}
    return J.course_map(c)


__all__ = ['course_map', 'day_line', 'handle_course_map', 'hud_extras', 'in_class_panel', 'year_bar']
