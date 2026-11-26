"""12.65: evaluación diagnóstica para iniciar el año. Lógica pura, sin Jarvis.

La IA escribe preguntas de selección múltiple alineadas con los DBA del grado anterior, cada una con su competencia o
tema. Los estudiantes responden en el celular; aquí se califica, se resume por competencia y se arman grupos.
"""
import json
import re
import unicodedata


def norm(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


def prompt(asignatura, grado, n=15):
    prev = max(0, int(grado) - 1)
    return (f"Eres un docente colombiano de {asignatura}. Escribe una evaluación diagnóstica para iniciar el año con estudiantes "
            f"que llegan a grado {grado}: mide lo que debían dominar en grado {prev}, según los Derechos Básicos de Aprendizaje "
            f"(DBA) y los Estándares Básicos de Competencias del MEN. Haz {n} preguntas de selección múltiple con única "
            "respuesta (4 opciones), de dificultad creciente, agrupadas en 3 a 5 competencias o temas clave del área. "
            "Lenguaje claro para la edad, sin trampas. Responde SOLO con JSON: {\"preguntas\": [{\"competencia\": str, "
            "\"enunciado\": str, \"opciones\": [str, str, str, str], \"correcta\": 0-3, \"dba\": str}]}.")


def parse(raw, n_max=30):
    m = re.search(r"\{.*\}", str(raw or ""), re.S)
    if not m:
        raise ValueError("la IA no devolvió las preguntas")
    try:
        d = json.loads(m.group(0))
    except ValueError:
        raise ValueError("la IA devolvió las preguntas incompletas")
    out = []
    for q in d.get("preguntas") or []:
        ops = [str(o).strip()[:200] for o in (q.get("opciones") or []) if str(o).strip()]
        try:
            ok = int(q.get("correcta"))
        except (TypeError, ValueError):
            continue
        if len(ops) < 3 or not 0 <= ok < len(ops) or not str(q.get("enunciado") or "").strip():
            continue
        out.append({"competencia": str(q.get("competencia") or "General").strip()[:60], "enunciado": str(q["enunciado"]).strip()[:600],
                    "opciones": ops[:5], "correcta": ok, "dba": str(q.get("dba") or "")[:200]})
    if len(out) < 3:
        raise ValueError("la IA no escribió suficientes preguntas válidas")
    return out[:n_max]


def score(questions, answers):
    """answers: [índice escogido | None]. → {"aciertos", "total", "nota", "por_comp": {comp: (bien, total)}}."""
    por = {}
    ok = 0
    for i, q in enumerate(questions):
        a = answers[i] if i < len(answers) else None
        good = a is not None and int(a) == q["correcta"]
        b, tot = por.get(q["competencia"], (0, 0))
        por[q["competencia"]] = (b + good, tot + 1)
        ok += good
    tot = len(questions)
    return {"aciertos": ok, "total": tot, "nota": round(1 + 4 * ok / tot, 1) if tot else 1.0, "por_comp": por}


LEVELS = ((0.8, "domina"), (0.6, "en proceso"), (0.0, "necesita refuerzo"))


def level(frac):
    return next(name for lim, name in LEVELS if frac >= lim)


def course_summary(results):
    """results: {estudiante: score}. → {"comp": {comp: % del curso}, "refuerzo": {comp: [estudiantes]}, "grupos": [[...]]}."""
    comp_tot = {}
    refuerzo = {}
    for est, r in results.items():
        for c, (b, t) in r["por_comp"].items():
            bb, tt = comp_tot.get(c, (0, 0))
            comp_tot[c] = (bb + b, tt + t)
            if t and b / t < 0.6:
                refuerzo.setdefault(c, []).append(est)
    comp = {c: round(100 * b / t) for c, (b, t) in comp_tot.items() if t}
    return {"comp": comp, "refuerzo": refuerzo, "grupos": groups(results)}


def groups(results, size=4):
    """Grupos heterogéneos: se reparten de mayor a menor nota en serpentina, para que cada grupo tenga quien jalone."""
    names = sorted(results, key=lambda e: -results[e]["nota"])
    if not names:
        return []
    k = max(1, round(len(names) / size))
    gs = [[] for _ in range(k)]
    for i, n in enumerate(names):
        row, col = divmod(i, k)
        gs[col if row % 2 == 0 else k - 1 - col].append(n)
    return [g for g in gs if g]


def spoken(summary, curso):
    if not summary["comp"]:
        return f"Todavía nadie de {curso} ha respondido el diagnóstico."
    best = max(summary["comp"], key=summary["comp"].get)
    worst = min(summary["comp"], key=summary["comp"].get)
    txt = (f"En {curso}, lo que más dominan es {best.lower()} ({summary['comp'][best]} %); lo más débil, {worst.lower()} "
           f"({summary['comp'][worst]} %).")
    need = summary["refuerzo"].get(worst, [])
    if need:
        txt += f" Necesitan refuerzo en eso {len(need)} estudiantes."
    return txt + " Te dejé el informe con grupos de trabajo sugeridos."
