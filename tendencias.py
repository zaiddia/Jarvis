"""Alertas tempranas y celebraciones (9.7): Jarvis mira la tendencia de cada estudiante, no solo su promedio.

· «Bajó»: venía bien y sus dos últimas notas cayeron (antes de quedar en riesgo).
· «Fallas»: faltó 2 o más veces en la última semana, o suele faltar el mismo día de la semana.
· «Mejoró»: sus dos últimas notas superan claramente su promedio anterior → para felicitarlo.
"""
import datetime

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _fmt(x):
    return str(round(x, 1)).replace(".", ",")


def grade_trend(notas, delta=0.8):
    """("baja"|"mejora", detalle) o None, con las notas ordenadas por fecha (necesita al menos 4)."""
    ns = [n for n in sorted(notas, key=lambda n: (n.get("fecha", ""),)) if n.get("nota") is not None]
    if len(ns) < 4:
        return None
    before = [n["nota"] for n in ns[:-2]]
    last = [n["nota"] for n in ns[-2:]]
    b, l = sum(before) / len(before), sum(last) / 2
    if b >= 3.4 and b - l >= delta and min(last) < b - 0.5:
        return "baja", f"venía en {_fmt(b)} y sus dos últimas notas son {_fmt(last[0])} y {_fmt(last[1])}"
    if l - b >= delta and min(last) >= 3.5:
        return "mejora", f"subió de {_fmt(b)} a {_fmt(l)} en sus dos últimas notas"
    return None


def absence_trend(dias_falla, today=None):
    """dias_falla: fechas ISO en que faltó. ("fallas", detalle) o None."""
    today = today or datetime.date.today()
    ds = sorted({datetime.date.fromisoformat(d) for d in dias_falla if d})
    week = [d for d in ds if 0 <= (today - d).days <= 7]
    if len(week) >= 2:
        return "fallas", f"faltó {len(week)} veces en la última semana"
    by = {}
    for d in ds:
        if (today - d).days <= 60:
            by[d.weekday()] = by.get(d.weekday(), 0) + 1
    if by:
        wd, n = max(by.items(), key=lambda kv: kv[1])
        if n >= 3:
            return "fallas", f"ha faltado {n} {DIAS[wd]} en los últimos dos meses"
    return None


def scan(seg_data, attendance, today=None):
    """Todas las alertas: [{"k", "curso", "estudiante", "tipo", "detalle"}]."""
    out = []
    for curso, est in seg_data.items():
        for name, notas in est.items():
            t = grade_trend(notas)
            if t:
                out.append({"k": f"{t[0]}:{curso}:{name}:{len(notas)}", "curso": curso, "estudiante": name, "tipo": t[0], "detalle": t[1]})
    for curso, days in attendance.items():
        per = {}
        for day, names in days.items():
            for n in names:
                per.setdefault(n, []).append(day)
        for name, ds in per.items():
            t = absence_trend(ds, today)
            if t:
                out.append({"k": f"fallas:{curso}:{name}:{max(ds)}", "curso": curso, "estudiante": name, "tipo": "fallas", "detalle": t[1]})
    return out


def spoken(alerts):
    if not alerts:
        return "No veo tendencias preocupantes: nadie viene bajando ni faltando seguido."
    bad = [a for a in alerts if a["tipo"] != "mejora"]
    good = [a for a in alerts if a["tipo"] == "mejora"]
    txt = ""
    if bad:
        txt += "Atención temprana: " + "; ".join(f"{a['estudiante']} ({a['curso']}) {a['detalle']}" for a in bad[:6]) + ". "
    if good:
        txt += "Para felicitar: " + "; ".join(f"{a['estudiante']} ({a['curso']}) {a['detalle']}" for a in good[:6]) + "."
    return txt.strip()
