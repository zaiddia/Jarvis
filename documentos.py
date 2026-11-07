"""Generador de documentos (12.14): Word, PDF, texto, Excel, PowerPoint y CSV a partir de una descripción.

Lógica pura: plantillas, instrucciones para la IA, validación y armado de los archivos.
jarvis.py (nucleo/generador.py) llama a la IA y guarda el historial.

Tres formas de contenido según el formato:
- «doc»    (Word, PDF, texto): título y secciones con párrafos, viñetas, pasos, preguntas y tablas.
- «slides» (PowerPoint): el formato de oficina.pptx_prompt.
- «table»  (Excel, CSV): columnas y filas.
"""
import csv
import datetime
import json
import os
import re

import oficina

FORMATS = {
    "word": ("Word", "docx", "doc"), "pdf": ("PDF", "pdf", "doc"), "texto": ("Texto", "txt", "doc"),
    "excel": ("Excel", "xlsx", "table"), "powerpoint": ("PowerPoint", "pptx", "slides"), "csv": ("CSV", "csv", "table"),
}
# id: (nombre, qué pedirle a la IA, formatos que tienen sentido)
TEMPLATES = {
    "libre": ("Documento libre", "", tuple(FORMATS)),
    "informe": ("Informe", "Un informe formal: introducción, desarrollo por apartados, conclusiones y recomendaciones.", tuple(FORMATS)),
    "guia": ("Guía de aprendizaje", "Una guía de aprendizaje para estudiantes: objetivo, saberes previos, explicación con ejemplos resueltos, "
             "actividades paso a paso y autoevaluación.", ("word", "pdf", "texto", "powerpoint")),
    "taller": ("Taller", "Un taller de ejercicios para estudiantes, de menor a mayor dificultad, con instrucciones claras. "
               "Al final, una sección «Respuestas (para el docente)».", ("word", "pdf", "texto", "excel", "csv")),
    "evaluacion": ("Evaluación con hoja de respuestas", "Una evaluación: datos del estudiante, instrucciones, preguntas (la mayoría de "
                   "selección múltiple con 4 opciones, A a D, una sola correcta) y al final la sección «Hoja de respuestas (para el docente)» "
                   "con la respuesta correcta de cada pregunta y por qué.", ("word", "pdf", "texto", "excel", "csv")),
    "planeador": ("Planeador de clase", "Un planeador de clase: datos (grado, asignatura, tiempo), estándar o DBA, objetivo, momentos de la "
                  "clase (inicio, desarrollo, cierre) con tiempos y actividades, recursos y evaluación.", ("word", "pdf", "texto", "excel", "csv")),
    "rubrica": ("Rúbrica", "Una rúbrica de evaluación en una tabla: criterios en filas y niveles Superior, Alto, Básico y Bajo en columnas, "
                "con descriptores claros.", ("word", "pdf", "texto", "excel", "csv")),
    "circular": ("Circular para padres", "Una circular para padres de familia: fecha, saludo, asunto, información clara y amable, "
                 "qué se espera de las familias, despedida y firma del docente.", ("word", "pdf", "texto")),
    "acta": ("Acta", "Un acta de reunión: fecha, hora, lugar, asistentes, orden del día, desarrollo de cada punto, compromisos "
             "(responsable y fecha) y firmas.", ("word", "pdf", "texto")),
    "notas": ("Planilla de notas", "", ("excel", "csv", "word", "pdf")),
    "asistencia": ("Lista de asistencia", "", ("excel", "csv", "word", "pdf")),
}
LOCAL = ("notas", "asistencia")                    # se arman con la lista del curso, sin IA
LENGTHS = {"corto": ("1 página", 450, 5), "medio": ("2 páginas", 900, 8), "largo": ("5 páginas", 2200, 12)}


def kind_of(fmt):
    return FORMATS[fmt][2]


def ok_format(template, fmt):
    return fmt in FORMATS and template in TEMPLATES and fmt in TEMPLATES[template][2]


def _s(v, limit=400):
    return re.sub(r"[ \t]+", " ", str(v if v is not None else "")).strip()[:limit]


# ============================================================================ INSTRUCCIONES PARA LA IA
_DOC_SHAPE = ('{"titulo": "…", "subtitulo": "…", "secciones": [\n'
              '  {"titulo": "…", "parrafos": ["…"], "vinetas": ["…"], "pasos": ["…"],\n'
              '   "preguntas": [{"enunciado": "…", "opciones": ["A) …", "B) …", "C) …", "D) …"]}],\n'
              '   "tabla": {"columnas": ["…"], "filas": [["…"]]}}\n'
              ']}')


def build_prompt(fmt, template, pedido, grado="", asignatura="", largo="medio", fuente=""):
    """Lo que se le pide a la IA (responde solo JSON)."""
    tname, hint, _ = TEMPLATES.get(template, TEMPLATES["libre"])
    label, words, slides = LENGTHS.get(largo, LENGTHS["medio"])
    ctx = "".join([f"Grado: {grado}. Ajusta el lenguaje y la profundidad a esa edad.\n" if grado else "",
                   f"Asignatura: {asignatura}.\n" if asignatura else "",
                   f"Tipo de documento: {tname}. {hint}\n" if hint else "",
                   ("Básate en este material que subió el docente (úsalo como fuente; no inventes datos que contradigan el material):\n"
                    f"<<<\n{fuente[:14000]}\n>>>\n") if fuente else ""])
    kind = kind_of(fmt)
    if kind == "slides":
        return oficina.pptx_prompt(f"{pedido}" + (f" ({tname})" if template != "libre" else ""), slides, grado) + "\n" + ctx
    if kind == "table":
        return oficina.table_prompt(pedido + (f" — {tname}. {hint}" if hint else "")) + "\n" + ctx
    return ("Eres un docente experto de Colombia y redactas documentos claros y correctos.\n"
            f"Petición del docente: «{pedido}».\n{ctx}"
            f"Extensión aproximada: {label} (unas {words} palabras).\n"
            "Responde SOLO con un JSON con esta forma (usa solo las claves que necesites en cada sección):\n"
            f"{_DOC_SHAPE}\n"
            "Reglas: secciones con títulos cortos; párrafos completos; matemáticas en texto plano (x^2, raíz(9), 3/4); "
            "tablas de máximo 8 columnas. Español de Colombia, sin markdown ni emojis.")


def revise_prompt(fmt, model, cambio):
    return ("Este es un documento en JSON. Aplica este cambio que pide el docente y devuelve el JSON COMPLETO con la misma forma "
            f"(no expliques nada):\nCambio: «{cambio}»\nDocumento:\n{json.dumps(model, ensure_ascii=False)[:30000]}")


# ============================================================================ VALIDAR
def _table(t, rows=200, cols=12):
    if not isinstance(t, dict):
        return None
    c = [_s(x, 80) for x in (t.get("columnas") or [])][:cols]
    if not c:
        return None
    out = []
    for r in (t.get("filas") or [])[:rows]:
        if isinstance(r, list):
            row = [v if isinstance(v, (int, float)) and not isinstance(v, bool) else _s(v, 600) for v in r[:len(c)]]
            out.append(row + [""] * (len(c) - len(row)))
    return {"columnas": c, "filas": out} if out else None


def validate_doc(d, pedido=""):
    if not isinstance(d, dict):
        raise ValueError("la respuesta no es un objeto")
    secs = []
    for s in (d.get("secciones") or [])[:40]:
        if not isinstance(s, dict):
            continue
        sec = {"titulo": _s(s.get("titulo"), 140),
               "parrafos": [_s(p, 4000) for p in (s.get("parrafos") or []) if _s(p)][:30],
               "vinetas": [_s(p, 600) for p in (s.get("vinetas") or []) if _s(p)][:40],
               "pasos": [_s(p, 600) for p in (s.get("pasos") or []) if _s(p)][:40],
               "preguntas": [], "tabla": _table(s.get("tabla"), 60, 8)}
        for q in (s.get("preguntas") or [])[:60]:
            if isinstance(q, dict) and _s(q.get("enunciado")):
                sec["preguntas"].append({"enunciado": _s(q["enunciado"], 1200),
                                         "opciones": [_s(o, 300) for o in (q.get("opciones") or []) if _s(o)][:6]})
            elif isinstance(q, str) and _s(q):
                sec["preguntas"].append({"enunciado": _s(q, 1200), "opciones": []})
        if sec["titulo"] or sec["parrafos"] or sec["vinetas"] or sec["pasos"] or sec["preguntas"] or sec["tabla"]:
            secs.append(sec)
    if not secs:
        raise ValueError("el documento vino vacío")
    return {"titulo": _s(d.get("titulo"), 140) or _s(pedido, 90) or "Documento", "subtitulo": _s(d.get("subtitulo"), 200), "secciones": secs}


def validate(fmt, d, pedido=""):
    kind = kind_of(fmt)
    if kind == "slides":
        return oficina.pptx_validate(d, pedido)
    if kind == "table":
        return oficina.table_validate(d, pedido)
    return validate_doc(d, pedido)


# ============================================================================ SIN IA: LISTAS DEL CURSO
def local_table(template, curso, names, n_notas=5, dias=20, today=None):
    names = [n for n in names if str(n).strip()]
    if not names:
        raise ValueError("ese curso no tiene estudiantes en el Aula")
    if template == "notas":
        cols = ["N°", "Estudiante"] + [f"Nota {i}" for i in range(1, n_notas + 1)] + ["Definitiva"]
        rows = [[i, n] + [""] * (n_notas + 1) for i, n in enumerate(names, 1)]
        return {"titulo": f"Planilla de notas {curso}", "columnas": cols, "filas": rows}
    today = today or datetime.date.today()
    days, d = [], today - datetime.timedelta(days=today.weekday())          # desde el lunes de esta semana
    while len(days) < dias:
        if d.weekday() < 5:
            days.append(d.strftime("%d/%m"))
        d += datetime.timedelta(days=1)
    return {"titulo": f"Lista de asistencia {curso}", "columnas": ["N°", "Estudiante"] + days[:10],
            "filas": [[i, n] + [""] * len(days[:10]) for i, n in enumerate(names, 1)]}


def table_as_doc(m):
    return {"titulo": m["titulo"], "subtitulo": "", "secciones": [{"titulo": "", "parrafos": [], "vinetas": [], "pasos": [], "preguntas": [],
                                                                   "tabla": {"columnas": m["columnas"], "filas": m["filas"]}}]}


# ============================================================================ TEXTO PLANO (vista, proyector y .txt)
def plain(kind, m):
    out = [m.get("titulo", "")]
    if m.get("subtitulo"):
        out.append(m["subtitulo"])
    out.append("")
    if kind == "slides":
        for i, s in enumerate(m["diapositivas"], 1):
            out.append(f"{i}. {s['titulo']}")
            out += [f"   - {p}" for p in s.get("puntos") or []]
            if s.get("pregunta"):
                out.append(f"   ¿? {s['pregunta']}")
        return "\n".join(out)
    if kind == "table":
        m = table_as_doc(m)
    for s in m["secciones"]:
        if s["titulo"]:
            out += [s["titulo"].upper(), ""]
        for p in s["parrafos"]:
            out += [p, ""]
        out += [f"- {v}" for v in s["vinetas"]]
        out += [f"{i}. {v}" for i, v in enumerate(s["pasos"], 1)]
        for i, q in enumerate(s["preguntas"], 1):
            out.append(f"{i}. {q['enunciado']}")
            out += [f"   {o}" for o in q["opciones"]]
        if s["tabla"]:
            out.append(" | ".join(map(str, s["tabla"]["columnas"])))
            out += [" | ".join(map(str, r)) for r in s["tabla"]["filas"]]
        out.append("")
    return "\n".join(out).strip()


# ============================================================================ ARMAR LOS ARCHIVOS
def _header_lines(docente, institucion, curso):
    return [x for x in (institucion, f"Docente: {docente}" if docente else "", f"Curso: {curso}" if curso else "",
                        datetime.date.today().strftime("Fecha: %d/%m/%Y")) if x]


def build_docx(m, path, Document, docente="", institucion="", curso=""):
    from docx.shared import Pt, RGBColor
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(11)
    head = _header_lines(docente, institucion, curso)
    if head:
        p = doc.add_paragraph(" · ".join(head))
        p.runs[0].font.size, p.runs[0].font.color.rgb = Pt(9), RGBColor(0x5B, 0x67, 0x78)
    doc.add_heading(m["titulo"], 0)
    if m.get("subtitulo"):
        doc.add_paragraph(m["subtitulo"]).runs[0].italic = True
    for s in m["secciones"]:
        if s["titulo"]:
            doc.add_heading(s["titulo"], 1)
        for p in s["parrafos"]:
            doc.add_paragraph(p)
        for v in s["vinetas"]:
            doc.add_paragraph(v, style="List Bullet")
        for v in s["pasos"]:
            doc.add_paragraph(v, style="List Number")
        for i, q in enumerate(s["preguntas"], 1):
            doc.add_paragraph().add_run(f"{i}. {q['enunciado']}").bold = True
            for o in q["opciones"]:
                doc.add_paragraph(o).paragraph_format.left_indent = Pt(18)
        t = s["tabla"]
        if t:
            tb = doc.add_table(rows=1, cols=len(t["columnas"]))
            tb.style = "Table Grid"
            for j, c in enumerate(t["columnas"]):
                tb.rows[0].cells[j].text = str(c)
                for r in tb.rows[0].cells[j].paragraphs[0].runs:
                    r.bold = True
            for row in t["filas"]:
                cells = tb.add_row().cells
                for j, v in enumerate(row):
                    cells[j].text = str(v)
            doc.add_paragraph()
    doc.save(path)
    return path


def build_pdf(m, path, docente="", institucion="", curso=""):
    from fpdf import FPDF

    import boletin
    d = boletin._Doc(FPDF)
    p = d.pdf
    p.add_page()
    W = p.w - p.l_margin - p.r_margin
    head = _header_lines(docente, institucion, curso)
    if head:
        d.font(8.5, False, (91, 103, 120))
        p.multi_cell(W, 4.5, d.t(" · ".join(head)), new_x="LMARGIN", new_y="NEXT")
        p.ln(2)
    d.font(17, True, (14, 40, 66))
    p.multi_cell(W, 8, d.t(m["titulo"]), new_x="LMARGIN", new_y="NEXT")
    if m.get("subtitulo"):
        d.font(10.5, False, (91, 103, 120))
        p.multi_cell(W, 5.5, d.t(m["subtitulo"]), new_x="LMARGIN", new_y="NEXT")
    p.ln(3)
    for s in m["secciones"]:
        if s["titulo"]:
            p.ln(2)
            d.font(12.5, True, (15, 118, 138))
            p.multi_cell(W, 6.5, d.t(s["titulo"]), new_x="LMARGIN", new_y="NEXT")
            p.ln(1)
        d.font(10.5)
        for x in s["parrafos"]:
            p.multi_cell(W, 5.4, d.t(x), new_x="LMARGIN", new_y="NEXT")
            p.ln(1.5)
        for x in s["vinetas"]:
            p.multi_cell(W, 5.4, d.t(f"•  {x}"), new_x="LMARGIN", new_y="NEXT")
        for i, x in enumerate(s["pasos"], 1):
            p.multi_cell(W, 5.4, d.t(f"{i}.  {x}"), new_x="LMARGIN", new_y="NEXT")
        for i, q in enumerate(s["preguntas"], 1):
            p.ln(1)
            d.font(10.5, True)
            p.multi_cell(W, 5.4, d.t(f"{i}. {q['enunciado']}"), new_x="LMARGIN", new_y="NEXT")
            d.font(10.5)
            for o in q["opciones"]:
                p.set_x(p.l_margin + 6)
                p.multi_cell(W - 6, 5.2, d.t(o), new_x="LMARGIN", new_y="NEXT")
        t = s["tabla"]
        if t:
            p.ln(1)
            n = len(t["columnas"])
            cw = W / n
            size = 9 if n <= 5 else 7.5
            d.font(size, True, (255, 255, 255))
            p.set_fill_color(15, 118, 138)
            for c in t["columnas"]:
                p.cell(cw, 6, d.t(str(c))[:40], border=1, fill=True)
            p.ln()
            d.font(size)
            for row in t["filas"]:
                texts = [d.t(str(v)) for v in row]
                lines = max(len(p.multi_cell(cw, 4.6, x, dry_run=True, output="LINES")) for x in texts) or 1
                h = 4.6 * lines + 1
                if p.get_y() + h > p.h - 18:
                    p.add_page()
                y, x0 = p.get_y(), p.l_margin
                for j, x in enumerate(texts):
                    p.rect(x0 + j * cw, y, cw, h)
                    p.set_xy(x0 + j * cw, y + 0.5)
                    p.multi_cell(cw, 4.6, x)
                p.set_xy(x0, y + h)
            p.ln(2)
    p.output(path)
    return path


def build_txt(kind, m, path, docente="", institucion="", curso=""):
    head = _header_lines(docente, institucion, curso)
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write(("\n".join(head) + "\n\n" if head else "") + plain(kind, m) + "\n")
    return path


def build_csv(m, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")            # Excel en español abre bien el punto y coma
        w.writerow(m["columnas"])
        w.writerows(m["filas"])
    return path


def build(fmt, kind, m, out_dir, Document=None, docente="", institucion="", curso="", grado=""):
    """Arma el archivo en la carpeta Documentos. → ruta."""
    label, ext, _ = FORMATS[fmt]
    path = oficina._out(out_dir, "Documentos", m["titulo"], ext)
    if fmt == "powerpoint":
        tmp = oficina.build_pptx(m, out_dir, docente, institucion, grado)
        os.replace(tmp, path)
        return path
    if fmt == "excel":
        tmp = oficina.build_table_xlsx(m if kind == "table" else doc_as_table(m), out_dir)
        os.replace(tmp, path)
        return path
    if fmt == "csv":
        return build_csv(m if kind == "table" else doc_as_table(m), path)
    doc = table_as_doc(m) if kind == "table" else m
    if fmt == "word":
        if Document is None:
            raise ValueError("falta python-docx para crear Word")
        return build_docx(doc, path, Document, docente, institucion, curso)
    if fmt == "pdf":
        return build_pdf(doc, path, docente, institucion, curso)
    return build_txt("doc", doc, path, docente, institucion, curso)


def doc_as_table(m):
    """Un documento llevado a una tabla (la primera tabla que tenga, o sus secciones)."""
    for s in m["secciones"]:
        if s.get("tabla"):
            return {"titulo": m["titulo"], **s["tabla"]}
    rows = []
    for s in m["secciones"]:
        for x in s["parrafos"] + s["vinetas"] + s["pasos"] + [q["enunciado"] + (" " + " ".join(q["opciones"]) if q["opciones"] else "")
                                                              for q in s["preguntas"]]:
            rows.append([s["titulo"], x])
    return {"titulo": m["titulo"], "columnas": ["Sección", "Contenido"], "filas": rows or [["", ""]]}


def compatible(kind, fmt):
    """¿Ese borrador se puede guardar en ese formato sin volver a pedirlo a la IA?"""
    k = kind_of(fmt)
    return k == kind or (kind == "table" and k == "doc") or (kind == "doc" and k == "table")


# ============================================================================ HISTORIAL
class History:
    def __init__(self):
        self.path, self.items = None, []

    def configure(self, config_dir):
        self.path = os.path.join(config_dir, "documentos_hist.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.items = d if isinstance(d, list) else []
        except (OSError, ValueError):
            self.items = []

    def add(self, item):
        self.items = [x for x in self.items if x.get("ruta") != item.get("ruta")] + [item]
        self.items = self.items[-80:]
        self.save()

    def save(self):
        if not self.path:
            return
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.items, f, ensure_ascii=False)
        except OSError:
            pass

    def listing(self):
        return [dict(x, existe=os.path.exists(x.get("ruta", ""))) for x in reversed(self.items)]


history = History()
