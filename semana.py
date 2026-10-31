"""Semana lista y cierre de periodo (9.8). Lógica pura, sin Jarvis.

· Semana lista: el domingo Jarvis mira tu horario de la semana y, por cada curso, el siguiente tema de la malla
  (o el último del diario de clase), y arma un proyecto con el plan de clase y una evaluación corta de cada curso.
· Cierre de periodo: cuántos días faltan, y el consolidado de cada curso (promedio, desempeños, en riesgo, quién
  no tiene notas y los temas de la malla que no alcanzaste a ver).
"""
import datetime
import re
import unicodedata

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
         "diciembre"]


def _plain(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn")


# ----------------------------------------------------------------------------- semana lista
def courses_of_week(items):
    """{curso: {"materia", "dias": [0..4], "sesiones"}} de las clases de lunes a viernes del horario."""
    out = {}
    for x in sorted(items, key=lambda x: (x["dia"], x["inicio"])):
        if x["dia"] > 4 or not x.get("curso"):
            continue
        c = out.setdefault(x["curso"], {"materia": x.get("materia", ""), "dias": [], "sesiones": 0})
        c["sesiones"] += 1
        if x["dia"] not in c["dias"]:
            c["dias"].append(x["dia"])
        if not c["materia"] and x.get("materia"):
            c["materia"] = x["materia"]
    return out


def week_plan(items, topic_for, monday, with_quiz=True, max_steps=8):
    """Plan de proyecto (formato de proyectos.validate_plan) y lista de cursos sin tema. topic_for(curso) → tema o ""."""
    courses = courses_of_week(items)
    pasos, sin_tema = [], []
    for curso, c in courses.items():
        tema = (topic_for(curso) or "").strip()
        if not tema:
            sin_tema.append(curso)
            continue
        dias = ", ".join(DIAS[d] for d in c["dias"])
        mat = f" de {c['materia']}" if c["materia"] else ""
        n = c["sesiones"]
        pid = re.sub(r"\W", "", curso)[:8] or f"c{len(pasos)}"
        pasos.append({"id": f"pl{pid}", "tipo": "plan", "titulo": f"Plan de clase {curso}: {tema}",
                      "pedido": f"Plan de clase{mat} para el curso {curso} sobre «{tema}», para {n} {'sesiones' if n != 1 else 'sesión'} "
                                f"de la semana ({dias}), con actividades para cada sesión.", "depende": []})
        if with_quiz:
            pasos.append({"id": f"qz{pid}", "tipo": "quiz", "titulo": f"Evaluación corta {curso}: {tema}",
                          "pedido": f"Evaluación corta de 5 preguntas{mat} para {curso} sobre «{tema}», para el cierre de la semana.",
                          "depende": [f"pl{pid}"]})
    if len(pasos) > max_steps:                         # muchos cursos: primero los planes, luego las evaluaciones que quepan
        plans = [p for p in pasos if p["tipo"] == "plan"][:max_steps]
        rest = [p for p in pasos if p["tipo"] != "plan" and p["depende"][0] in {x["id"] for x in plans}]
        pasos = plans + rest[:max_steps - len(plans)]
    return {"nombre": f"Semana del {monday:%d/%m}", "pasos": pasos}, sin_tema


def next_monday(today):
    return today + datetime.timedelta(days=(7 - today.weekday()) % 7 or 7)


# ----------------------------------------------------------------------------- cierre de periodo
def parse_date(t, today=None):
    """«28 de noviembre», «el 28/11», «2026-11-28» → date (el próximo si no dices el año)."""
    today = today or datetime.date.today()
    t = _plain(t)
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})\s*(?:de\s+)?(" + "|".join(MESES) + r")(?:\s+(?:de|del)?\s*(\d{4}))?\b", t)
    if m:
        d, mo, y = int(m.group(1)), MESES.index(m.group(2)) + 1, m.group(3)
    else:
        m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b", t)
        if not m:
            return None
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        dt = datetime.date(int(y) if y else today.year, mo, d)
    except ValueError:
        return None
    if not y and dt < today - datetime.timedelta(days=30):
        dt = dt.replace(year=today.year + 1)
    return dt


def days_left(period_end, today=None):
    if not period_end:
        return None
    try:
        return (datetime.date.fromisoformat(period_end) - (today or datetime.date.today())).days
    except ValueError:
        return None


def course_summary(curso, names, grades, absences, min_grade=3.0, max_absences=3, missing_topics=None):
    """Consolidado de un curso para el cierre."""
    avgs, sin_notas, riesgo = {}, [], []
    perf = {"Superior": 0, "Alto": 0, "Básico": 0, "Bajo": 0}
    for n in names:
        ns = [x["nota"] for x in grades.get(n, [])]
        if not ns:
            sin_notas.append(n)
            continue
        a = round(sum(ns) / len(ns), 2)
        avgs[n] = a
        perf["Superior" if a >= 4.6 else "Alto" if a >= 4.0 else "Básico" if a >= 3.0 else "Bajo"] += 1
    for n in names:
        why = []
        if n in avgs and avgs[n] < min_grade:
            why.append(f"promedio {str(avgs[n]).replace('.', ',')}")
        if absences.get(n, 0) >= max_absences:
            why.append(f"{absences[n]} fallas")
        if why:
            riesgo.append((n, why))
    prom = round(sum(avgs.values()) / len(avgs), 2) if avgs else None
    return {"curso": curso, "estudiantes": len(names), "promedio": prom, "desempenos": perf, "sin_notas": sin_notas,
            "riesgo": riesgo, "temas_pendientes": list(missing_topics or [])}


def spoken_close(sums, days=None):
    head = ("El periodo cierra hoy. " if days == 0 else f"Faltan {days} días para cerrar el periodo. " if days and days > 0 else "")
    parts = []
    for s in sums:
        p = f"{s['curso']}: promedio {str(s['promedio']).replace('.', ',') if s['promedio'] is not None else 'sin notas'}"
        if s["riesgo"]:
            p += f", {len(s['riesgo'])} en riesgo"
        if s["sin_notas"]:
            p += f", {len(s['sin_notas'])} sin notas"
        if s["temas_pendientes"]:
            p += f", {len(s['temas_pendientes'])} temas de la malla sin ver"
        parts.append(p)
    return head + ("; ".join(parts) + "." if parts else "No tengo cursos con notas todavía.")


def close_docx(sums, out_dir, Document, nombre="Cierre de periodo", docente="", institucion=""):
    import os
    doc = Document()
    doc.add_heading(nombre, 0)
    if institucion or docente:
        doc.add_paragraph(" · ".join(x for x in (institucion, docente) if x))
    doc.add_paragraph(f"Generado el {datetime.date.today():%d/%m/%Y}.")
    for s in sums:
        doc.add_heading(f"Curso {s['curso']}", 1)
        prom = str(s["promedio"]).replace(".", ",") if s["promedio"] is not None else "sin notas"
        doc.add_paragraph(f"Estudiantes: {s['estudiantes']} · Promedio del curso: {prom}")
        t = doc.add_table(rows=2, cols=4)
        t.style = "Table Grid"
        for i, (k, v) in enumerate(s["desempenos"].items()):
            t.rows[0].cells[i].text, t.rows[1].cells[i].text = k, str(v)
        if s["riesgo"]:
            doc.add_paragraph("En riesgo (necesitan plan de recuperación):")
            for n, why in s["riesgo"]:
                doc.add_paragraph(f"{n}: {', '.join(why)}", style="List Bullet")
        if s["sin_notas"]:
            doc.add_paragraph("Sin notas registradas: " + ", ".join(s["sin_notas"]))
        if s["temas_pendientes"]:
            doc.add_paragraph("Temas de la malla que no se alcanzaron a ver: " + "; ".join(s["temas_pendientes"]))
    folder = os.path.join(out_dir, "Cierre de periodo")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', " ", nombre).strip()
    path = os.path.join(folder, f"{safe} - {datetime.date.today():%Y-%m-%d}.docx")
    doc.save(path)
    return path
