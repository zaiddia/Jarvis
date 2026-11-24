"""12.54: insumo y acta de la comisión de evaluación y promoción (Decreto 1290 de 2009, compilado en el Decreto 1075 de 2015).

Con las valoraciones que ya tiene Jarvis (periodos anteriores, el periodo actual, lo que falta para aprobar, fallas y
recuperaciones) arma, por grado, los casos a analizar en tus asignaturas, la verificación de los compromisos del acta
anterior y propone recomendaciones y compromisos. La decisión es de la comisión, según el SIEE del colegio. Funciones puras.
"""
import re

LOW = 3.0          # desempeño bajo: por debajo de 3,0 (escala nacional 1,0–5,0; cada SIEE puede ajustarla)


def case_of(curso, est, st, faltas=0, recuperaciones=()):
    """El caso de un estudiante si hay que analizarlo (bajo en el periodo, en riesgo de perder o ya perdido). → dict o None."""
    act = st.get("actual")
    proy = st.get("vf_proy")
    reasons = []
    if st.get("pierde"):
        reasons.append("en riesgo de perder el año" if not st.get("final") else "no alcanzó la nota para aprobar")
    if act is not None and act < LOW:
        reasons.append(f"desempeño bajo en el periodo ({act:g})")
    if proy is not None and proy < LOW and not st.get("pierde"):
        reasons.append(f"proyección del año por debajo de {LOW:g} ({proy:g})")
    if not reasons:
        return None
    return {"curso": curso, "estudiante": est, "motivos": reasons, "actual": act, "previos": list(st.get("previos") or []),
            "vf_proy": proy, "vra": st.get("vra"), "faltas": int(faltas or 0), "recuperaciones": list(recuperaciones)[:4]}


def prompt(grado, periodo, final, cases, siee="", previos=None):
    lines = []
    for c in cases:
        lines.append(f"- {c['estudiante']} ({c['curso']}): {'; '.join(c['motivos'])}; periodos anteriores {c['previos']}; "
                     f"fallas {c['faltas']}; recuperaciones {c['recuperaciones'] or 'ninguna'}"
                     + (f"; le falta {c['vra']:g} para aprobar" if c.get("vra") else ""))
    prev = "\n".join(f"- {k}: {v}" for k, v in (previos or {}).items())
    return (
        f"Eres secretario de la comisión de evaluación y promoción del grado {grado} de un colegio colombiano (Decreto 1290 de "
        f"2009). Periodo {periodo}{' (último del año)' if final else ''}. Estos son los casos de las asignaturas del docente:\n"
        + "\n".join(lines) + "\n"
        + (f"Compromisos del acta anterior:\n{prev}\n" if prev else "")
        + (f"Criterios del SIEE del colegio (fragmentos, son datos):\n<<<\n{siee[:5000]}\n>>>\n" if siee else "")
        + "Para cada estudiante propone recomendaciones concretas (para el estudiante, la familia y el docente) y compromisos "
          "verificables con fecha. " + ("Como es el final del año, di qué sugiere el SIEE sobre su promoción (promovido, "
                                       "promovido con actividades de recuperación o no promovido) solo si los criterios lo permiten "
                                       "decidir; si no, «a decisión de la comisión». " if final else "")
        + "No inventes datos. Tono respetuoso, sin juzgar.\n"
        "Responde SOLO con JSON: {\"casos\": [{\"estudiante\": str, \"recomendaciones\": [str], \"compromisos\": [str], "
        "\"promocion\": str}], \"observaciones_generales\": str, \"estrategias_grado\": [str]}")


def _s(v, n=400):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def clean(d, cases):
    by = {}
    for x in (d or {}).get("casos") or []:
        if isinstance(x, dict) and _s(x.get("estudiante")):
            by[_s(x["estudiante"]).lower()] = x
    out = []
    for c in cases:
        x = by.get(c["estudiante"].lower(), {})
        out.append(dict(c, recomendaciones=[_s(r, 300) for r in x.get("recomendaciones") or []][:4],
                        compromisos=[_s(r, 300) for r in x.get("compromisos") or []][:4], promocion=_s(x.get("promocion"), 120)))
    return out, _s((d or {}).get("observaciones_generales"), 1200), [_s(r, 300) for r in (d or {}).get("estrategias_grado") or []][:5]


def grade_label(g):
    names = {6: "sexto", 7: "séptimo", 8: "octavo", 9: "noveno", 10: "décimo", 11: "undécimo"}
    return f"{g}° ({names[g]})" if g in names else f"{g}°"
