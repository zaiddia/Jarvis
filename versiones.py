"""Evaluaciones en varias versiones (11.0): el mismo quiz con las preguntas y las opciones en otro orden (A, B, C, D).

Cada estudiante recibe su versión en la hoja de respuestas; al leer la foto se califica con la clave de esa versión y
las respuestas se pasan al orden original, para que el análisis de la evaluación sea uno solo. Lógica pura.
"""
import datetime
import os
import random
import re

LETTERS = "ABCDEFGH"


def make(n_opts, k=4, seed=None):
    """n_opts: [opciones de cada pregunta]. → [{"v": "A", "orden": [preguntas base], "ops": [[opción base de cada opción]…]}].
    La versión A es la original; las demás, barajadas (sin repetir el orden de A)."""
    rnd = random.Random(seed)
    n = len(n_opts)
    out = [{"v": "A", "orden": list(range(n)), "ops": [list(range(m)) for m in n_opts]}]
    for i in range(1, max(1, min(len(LETTERS), k))):
        orden = list(range(n))
        for _ in range(5):
            rnd.shuffle(orden)
            if orden != list(range(n)) or n < 2:
                break
        ops = []
        for q in orden:
            o = list(range(n_opts[q]))
            rnd.shuffle(o)
            ops.append(o)
        out.append({"v": LETTERS[i], "orden": orden, "ops": ops})
    return out


def key_for(ver, base_key):
    """La clave de una versión (en su orden de preguntas y opciones)."""
    return [ver["ops"][j].index(base_key[q]) if base_key[q] in ver["ops"][j] else 0 for j, q in enumerate(ver["orden"])]


def to_base(answers, ver):
    """Respuestas leídas en el orden de la versión → en el orden original (para el análisis)."""
    base = [None] * len(ver["orden"])
    for j, q in enumerate(ver["orden"]):
        a = answers[j] if j < len(answers) else None
        base[q] = ver["ops"][j][a] if isinstance(a, int) and 0 <= a < len(ver["ops"][j]) else a
    return base


def assign(students, k):
    """{número de estudiante: letra} en el orden de la lista (A, B, C, D, A…): los vecinos quedan con versiones distintas."""
    return {str(s): LETTERS[i % k] for i, s in enumerate(students)}


def version_questions(preguntas, ver):
    """Las preguntas de una versión, con sus opciones en el orden de la versión."""
    out = []
    for j, q in enumerate(ver["orden"]):
        p = dict(preguntas[q])
        p["opciones"] = [preguntas[q]["opciones"][o] for o in ver["ops"][j]]
        out.append(p)
    return out


def docx(ex, out_dir, Document, docente="", institucion="", picture=None):
    """Un cuadernillo por versión y, al final, la clave de cada versión (solo para el docente).
    picture(doc, spec): dibuja la gráfica de una pregunta si la tiene."""
    from docx.enum.text import WD_BREAK
    from docx.shared import Cm, Pt
    doc = Document()
    vers = ex["versiones"]
    for vi, ver in enumerate(vers):
        if vi:
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        h = doc.add_paragraph()
        r = h.add_run(f"{ex['titulo']} · VERSIÓN {ver['v']}")
        r.bold, r.font.size = True, Pt(15)
        doc.add_paragraph(" · ".join(x for x in (institucion, docente, ex["curso"].replace(" · ", " – ")) if x))
        doc.add_paragraph(f"Versión {ver['v']}: marca tus respuestas en la hoja de respuestas que dice VERSIÓN {ver['v']}.")
        for i, q in enumerate(version_questions(ex["preguntas"], ver), 1):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.keep_with_next = True
            p.add_run(f"{i}. ").bold = True
            p.add_run(q.get("enunciado", ""))
            if picture and q.get("grafica"):
                try:
                    picture(doc, q["grafica"])
                except Exception:
                    pass
            for letter, opt in zip("abcde", q["opciones"]):
                op = doc.add_paragraph(f"{letter}) {opt}")
                op.paragraph_format.left_indent = Cm(0.8)
                op.paragraph_format.space_after = Pt(0)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    h = doc.add_paragraph()
    h.add_run("Claves por versión (solo para el docente)").bold = True
    t = doc.add_table(rows=1, cols=len(vers) + 1)
    t.style = "Table Grid"
    t.rows[0].cells[0].text = "Pregunta"
    for vi, ver in enumerate(vers):
        t.rows[0].cells[vi + 1].text = f"Versión {ver['v']}"
    keys = [key_for(v, ex["clave"]) for v in vers]
    for i in range(len(ex["clave"])):
        row = t.add_row().cells
        row[0].text = str(i + 1)
        for vi in range(len(vers)):
            row[vi + 1].text = "abcde"[keys[vi][i]]
    folder = os.path.join(out_dir, "Hojas de respuesta")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', " ", f"{ex['titulo']} {ex['curso']}").strip()
    path = os.path.join(folder, f"{safe} - versiones {datetime.date.today():%Y-%m-%d}.docx")
    doc.save(path)
    return path
