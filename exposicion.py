"""12.65: evaluar una exposición desde su video. Lógica pura, sin Jarvis.

La IA (Gemini) ve y escucha el video y califica cada criterio de la rúbrica de 1,0 a 5,0. Aquí están la rúbrica por
defecto, la instrucción, la lectura de su respuesta (JSON) y la nota sugerida ponderada.
"""
import json
import re

RUBRIC = (
    ("Dominio del tema", 30, "explica con seguridad y precisión, responde sin leer, usa el vocabulario del área"),
    ("Claridad y organización", 20, "introducción, desarrollo y cierre; ideas en orden; ejemplos"),
    ("Expresión oral", 20, "volumen, ritmo, pronunciación, muletillas"),
    ("Lenguaje corporal", 15, "postura, contacto visual con el público, gestos, manejo del espacio"),
    ("Apoyo visual y tiempo", 15, "carteleras o diapositivas legibles y útiles; ajuste al tiempo"),
)


def rubric_text(rubric=RUBRIC):
    return "\n".join(f"- {n} ({w} %): {d}" for n, w, d in rubric)


def prompt(estudiante="", tema="", rubric_custom="", rubric=RUBRIC):
    who = f" del estudiante {estudiante}" if estudiante else ""
    about = f" sobre «{tema}»" if tema else ""
    crit = rubric_custom.strip()[:4000] if rubric_custom.strip() else rubric_text(rubric)
    return (f"Eres un docente colombiano que evalúa la exposición oral{who}{about} que ves y escuchas en este video. "
            "Califica cada criterio de la rúbrica de 1,0 a 5,0 (escala colombiana, 3,0 aprueba), con base solo en lo que se ve y "
            "se oye; si algo no se puede ver (por ejemplo, no se ven las diapositivas), dilo y califica con lo que hay.\n"
            f"RÚBRICA:\n{crit}\n\n"
            "Responde SOLO con JSON: {\"criterios\": [{\"nombre\": str, \"nota\": number, \"evidencia\": str (lo que viste u oíste, "
            "con el minuto aproximado), \"mejorar\": str}], \"fortalezas\": [str], \"aspectos_a_mejorar\": [str], "
            "\"comentario_estudiante\": str (3 a 5 frases cálidas y concretas, en segunda persona), \"duracion_min\": number}. "
            "Sé justo y específico; no inventes lo que no está en el video.")


def parse(raw, rubric=RUBRIC):
    """La respuesta de la IA → dict con «criterios» (nombre, nota, evidencia, mejorar, peso) y «nota» (ponderada)."""
    s = str(raw or "")
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        raise ValueError("la IA no devolvió la evaluación")
    try:
        d = json.loads(m.group(0))
    except ValueError:
        raise ValueError("la IA devolvió la evaluación incompleta")
    crit = []
    weights = {n.lower(): w for n, w, _ in rubric}
    for c in d.get("criterios") or []:
        try:
            nota = round(min(5.0, max(1.0, float(str(c.get("nota", "")).replace(",", ".")))), 1)
        except ValueError:
            continue
        name = str(c.get("nombre") or "Criterio").strip()[:80]
        crit.append({"nombre": name, "nota": nota, "evidencia": str(c.get("evidencia") or "")[:600],
                     "mejorar": str(c.get("mejorar") or "")[:400], "peso": weights.get(name.lower())})
    if not crit:
        raise ValueError("la IA no calificó ningún criterio")
    d["criterios"] = crit
    d["nota"] = weighted(crit)
    for k in ("fortalezas", "aspectos_a_mejorar"):
        d[k] = [str(x)[:300] for x in (d.get(k) or [])][:6]
    d["comentario_estudiante"] = str(d.get("comentario_estudiante") or "")[:1200]
    return d


def weighted(crit):
    """Nota ponderada por los pesos de la rúbrica (o promedio simple si los criterios no son los de la rúbrica)."""
    if all(c.get("peso") for c in crit):
        tot = sum(c["peso"] for c in crit)
        return round(sum(c["nota"] * c["peso"] for c in crit) / tot, 1)
    return round(sum(c["nota"] for c in crit) / len(crit), 1)


def spoken(d, estudiante=""):
    who = f"{estudiante}: " if estudiante else ""
    best = max(d["criterios"], key=lambda c: c["nota"])
    worst = min(d["criterios"], key=lambda c: c["nota"])
    return (f"{who}nota sugerida {str(d['nota']).replace('.', ',')}. Lo mejor: {best['nombre'].lower()} "
            f"({str(best['nota']).replace('.', ',')}); lo que más debe mejorar: {worst['nombre'].lower()} "
            f"({str(worst['nota']).replace('.', ',')}). La nota final la pones tú.")
