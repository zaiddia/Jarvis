"""Retrospectiva del año (9.9): lo que hiciste con Jarvis durante el año escolar. Lógica pura, sin Jarvis."""
import datetime
import os
import re


def _in(fecha, year):
    return str(fecha or "")[:4] == str(year)


def compute(year, seg, obs, reg, projects, actividades, commitments, n_lessons=0, approvals=0, n_bank=0):
    """Cifras del año. seg/obs: {curso: {estudiante: [..]}}; reg: {curso: [{"fecha","tema"}]}."""
    notas = sum(1 for c in seg.values() for ns in c.values() for n in ns if _in(n.get("fecha"), year))
    estudiantes = len({(c, e) for c, es in seg.items() for e, ns in es.items() if any(_in(n.get("fecha"), year) for n in ns)})
    pos = sum(1 for c in obs.values() for es in c.values() for x in es if _in(x.get("fecha"), year) and x.get("tipo") == "positiva")
    anot = sum(1 for c in obs.values() for es in c.values() for x in es if _in(x.get("fecha"), year))
    temas = {c: [x["tema"] for x in lst if _in(x.get("fecha"), year)] for c, lst in reg.items()}
    temas = {c: t for c, t in temas.items() if t}
    prj = [p for p in projects if datetime.datetime.fromtimestamp(float(p.get("creado") or 0)).year == year]
    acts = [a for a in actividades if _in(a.get("fecha"), year) and a.get("resultado") is not None]
    best = sorted(acts, key=lambda a: -a["resultado"])[:5]
    done = [x for x in commitments if x.get("estado") == "hecho" and _in(x.get("creado"), year)]
    mejoras = []
    for c, es in seg.items():
        for e, ns in es.items():
            ys = sorted((n for n in ns if _in(n.get("fecha"), year)), key=lambda n: n.get("fecha", ""))
            if len(ys) >= 6:
                h = len(ys) // 2
                a, b = sum(n["nota"] for n in ys[:h]) / h, sum(n["nota"] for n in ys[h:]) / (len(ys) - h)
                if b - a >= 0.5:
                    mejoras.append((e, c, round(a, 1), round(b, 1)))
    mejoras.sort(key=lambda x: x[2] - x[3])
    return {"anio": year, "notas": notas, "estudiantes": estudiantes, "anotaciones": anot, "positivas": pos,
            "temas": temas, "n_temas": sum(len(t) for t in temas.values()), "proyectos": len(prj),
            "materiales": sum(len(p.get("pasos") or []) for p in prj), "mejores_actividades": best,
            "compromisos": len(done), "lecciones": n_lessons, "aprobaciones": approvals, "banco": n_bank, "mejoras": mejoras[:8]}


def _f(x):
    return str(x).replace(".", ",")


def spoken(s):
    parts = []
    if s["n_temas"]:
        parts.append(f"diste {s['n_temas']} tema{'s' if s['n_temas'] != 1 else ''} en {len(s['temas'])} curso{'s' if len(s['temas']) != 1 else ''}")
    if s["notas"]:
        parts.append(f"registraste {s['notas']} nota{'s' if s['notas'] != 1 else ''} de {s['estudiantes']} estudiante{'s' if s['estudiantes'] != 1 else ''}")
    if s["proyectos"]:
        parts.append(f"preparamos {s['proyectos']} proyectos con {s['materiales']} materiales")
    if s["positivas"]:
        parts.append(f"anotaste {s['positivas']} felicitaciones en el observador")
    if s["compromisos"]:
        parts.append(f"cumpliste {s['compromisos']} compromisos")
    if not parts:
        return f"Aún no tengo suficiente de {s['anio']} para una retrospectiva."
    txt = f"Tu {s['anio']} con Jarvis: " + ", ".join(parts[:-1]) + (" y " if len(parts) > 1 else "") + parts[-1] + "."
    if s["mejoras"]:
        e, c, a, b = s["mejoras"][0]
        txt += f" El mayor avance: {e} de {c}, que pasó de {_f(a)} a {_f(b)}."
    if s["mejores_actividades"]:
        txt += f" La actividad que mejor funcionó: {s['mejores_actividades'][0]['actividad'][:90]} ({s['mejores_actividades'][0]['resultado']} %)."
    return txt


def build_docx(s, out_dir, Document, carta="", docente="", institucion=""):
    doc = Document()
    doc.add_heading(f"Mi {s['anio']} como docente", 0)
    if docente or institucion:
        doc.add_paragraph(" · ".join(x for x in (docente, institucion) if x))
    if carta:
        doc.add_paragraph(carta)
    doc.add_heading("En cifras", 1)
    for label, v in (("Temas dados", s["n_temas"]), ("Notas registradas", s["notas"]), ("Estudiantes con notas", s["estudiantes"]),
                     ("Proyectos preparados con Jarvis", s["proyectos"]), ("Materiales de esos proyectos", s["materiales"]),
                     ("Anotaciones en el observador", s["anotaciones"]), ("Felicitaciones", s["positivas"]),
                     ("Compromisos cumplidos", s["compromisos"]), ("Preguntas en tu banco", s["banco"]),
                     ("Lecciones que le enseñaste a Jarvis", s["lecciones"])):
        if v:
            doc.add_paragraph(f"{label}: {v}", style="List Bullet")
    if s["temas"]:
        doc.add_heading("Lo que enseñaste", 1)
        for c, ts in s["temas"].items():
            doc.add_paragraph(f"{c} ({len(ts)}): " + "; ".join(dict.fromkeys(ts)))
    if s["mejoras"]:
        doc.add_heading("Estudiantes que más avanzaron", 1)
        for e, c, a, b in s["mejoras"]:
            doc.add_paragraph(f"{e} ({c}): de {_f(a)} a {_f(b)}", style="List Bullet")
    if s["mejores_actividades"]:
        doc.add_heading("Actividades que mejor funcionaron", 1)
        for a in s["mejores_actividades"]:
            doc.add_paragraph(f"{a['tema']} ({a['curso']}), {a['resultado']} %: {a['actividad'][:300]}", style="List Bullet")
    folder = os.path.join(out_dir, "Retrospectiva")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"Mi {s['anio']} como docente.docx")
    doc.save(path)
    return path


def letter_prompt(s, nombre=""):
    return ("Escribe una carta breve (2 párrafos, cálida, sincera, sin exagerar ni cursilerías) para un docente colombiano"
            + (f" llamado {nombre}" if nombre else "") + f", celebrando su año {s['anio']} con estos datos reales: "
            + re.sub(r"\s+", " ", spoken(s)) + " Habla de tú. Termina con una frase para el próximo año. Solo el texto.")
