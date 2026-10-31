"""Reuniones de área (10.0): agenda y acta a partir de lo que dictas, punto por punto. Lógica pura, sin Jarvis.

No se graba la reunión: tú (o quien lleva el acta) le dices a Jarvis los puntos, los acuerdos y las tareas, y al
terminar arma el acta formal en Word, con la tabla de compromisos.
"""
import datetime
import os
import re
import unicodedata


def _plain(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn")


def new(nombre="Reunión de área", agenda=None):
    return {"on": True, "nombre": nombre[:80], "fecha": datetime.date.today().isoformat(),
            "inicio": datetime.datetime.now().strftime("%H:%M"), "asistentes": [], "agenda": list(agenda or []),
            "puntos": [], "acuerdos": [], "tareas": []}


_TASK = re.compile(r"^(?:tarea|compromiso|responsable)\s+(?:para|de)\s+(.+?)\s*[:,]\s*(.+)$|^(.+?)\s+(?:se encarga de|queda encargad[oa] de|se compromete a)\s+(.+)$")
_DATE = re.compile(r"\b(?:para el|antes del|el)\s+((?:lunes|martes|miercoles|jueves|viernes|sabado|domingo)|\d{1,2}(?:\s+de\s+\w+|/\d{1,2})?)\b")


def classify(text):
    """("asistentes"|"acuerdo"|"tarea"|"punto", valor) de una frase dictada (ya sin «anota en el acta»)."""
    raw = text.strip().strip(".")
    t = _plain(raw)
    m = re.match(r"^(?:asistentes|asisten|estan presentes|presentes)\s*[:,]?\s*(.+)$", t)
    if m:
        names = [x.strip().title() for x in re.split(r",|\by\b", raw[len(raw) - len(m.group(1)):]) if x.strip()]
        return "asistentes", names
    m = re.match(r"^(?:acuerdo|acordamos|se acuerda|se acordo|decidimos|se decide)\s*(?:que)?\s*[:,]?\s*(.+)$", t)
    if m:
        return "acuerdo", _cap(raw[len(raw) - len(m.group(1)):])
    m = re.match(r"^(?:yo\s+)?(?:me encargo de|me comprometo a|me toca)\s+(.+)$", t)
    if m:
        d = _DATE.search(m.group(1))
        return "tarea", {"quien": "Yo", "que": _cap(raw[len(raw) - len(m.group(1)):]), "cuando": d.group(1) if d else ""}
    m = _TASK.match(t)
    if m:
        who = (m.group(1) or m.group(3)).strip()
        what_plain = (m.group(2) or m.group(4)).strip()
        what = raw[len(raw) - len(what_plain):]
        d = _DATE.search(what_plain)
        return "tarea", {"quien": who.title() if who not in ("yo", "mi", "a mi") else "Yo", "que": _cap(what), "cuando": d.group(1) if d else ""}
    return "punto", _cap(raw)


def _cap(x):
    x = str(x).strip(" .,:")
    return x[:1].upper() + x[1:]


def add(st, text):
    kind, val = classify(text)
    if kind == "asistentes":
        st["asistentes"] += [v for v in val if v not in st["asistentes"]]
    elif kind == "acuerdo":
        st["acuerdos"].append(val)
    elif kind == "tarea":
        st["tareas"].append(val)
    else:
        st["puntos"].append(val)
    return kind, val


def parse_agenda(text):
    """«1. informe de notas 2. salida pedagógica, y 3. varios» o «a, b y c» → [puntos]."""
    t = re.sub(r"\b(?:punto\s+)?(?:\d{1,2}|uno|dos|tres|cuatro|cinco|seis)\s*[.)-]\s*", "|", text)
    parts = re.split(r"\||;|,|\by\b(?=\s+\w)", t)
    return [_cap(p) for p in parts if len(p.strip(" .,:")) > 2][:12]


def agenda_prompt(tema, puntos, contexto=""):
    return ("Organiza la agenda (orden del día) de una reunión de área de docentes en Colombia. "
            f"Tema o motivo: «{tema}». Puntos que propone el docente: {puntos or 'ninguno'}. "
            + (f"Datos útiles del docente: {contexto}. " if contexto else "") +
            "Incluye al inicio verificación de asistencia y lectura del acta anterior, y al final varios. Entre 4 y 9 puntos, "
            'cada uno corto, con un tiempo estimado. Responde SOLO con JSON: {"agenda": ["Verificación de asistencia (5 min)", …]}')


def minutes_prompt(st):
    return ("Redacta el acta formal de esta reunión de área de docentes (Colombia), en tercera persona, clara y breve, a partir "
            "de las notas tomadas. No inventes datos que no estén en las notas.\n"
            f"Reunión: {st['nombre']}, {st['fecha']}, inicio {st['inicio']}.\nAsistentes: {', '.join(st['asistentes']) or 'no anotados'}.\n"
            f"Orden del día: {'; '.join(st['agenda']) or 'no definido'}.\nNotas: " + " | ".join(st["puntos"]) +
            "\nAcuerdos: " + " | ".join(st["acuerdos"]) +
            '\nResponde SOLO con JSON: {"desarrollo": ["párrafo por cada punto tratado", …]}')


def build_docx(st, out_dir, Document, desarrollo=None, institucion="", fin=""):
    doc = Document()
    doc.add_heading(f"Acta - {st['nombre']}", 0)
    if institucion:
        doc.add_paragraph(institucion)
    doc.add_paragraph(f"Fecha: {st['fecha']} · Hora de inicio: {st['inicio']}" + (f" · Hora de cierre: {fin}" if fin else ""))
    doc.add_heading("Asistentes", 1)
    doc.add_paragraph(", ".join(st["asistentes"]) or "(no se anotaron)")
    if st["agenda"]:
        doc.add_heading("Orden del día", 1)
        for i, a in enumerate(st["agenda"], 1):
            doc.add_paragraph(f"{i}. {a}")
    doc.add_heading("Desarrollo", 1)
    for p in (desarrollo or st["puntos"]) or ["(sin notas)"]:
        doc.add_paragraph(p)
    if st["acuerdos"]:
        doc.add_heading("Acuerdos", 1)
        for a in st["acuerdos"]:
            doc.add_paragraph(a, style="List Bullet")
    if st["tareas"]:
        doc.add_heading("Compromisos", 1)
        t = doc.add_table(rows=1, cols=3)
        t.style = "Table Grid"
        for c, h in zip(t.rows[0].cells, ("Responsable", "Compromiso", "Fecha")):
            c.text = h
        for x in st["tareas"]:
            r = t.add_row().cells
            r[0].text, r[1].text, r[2].text = x["quien"], x["que"], x["cuando"]
    doc.add_paragraph("\n\nFirma de quien preside: ____________________     Firma de quien redacta: ____________________")
    folder = os.path.join(out_dir, "Actas")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', " ", st["nombre"]).strip()
    path = os.path.join(folder, f"Acta {safe} - {st['fecha']}.docx")
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"Acta {safe} - {st['fecha']} ({n}).docx")
        n += 1
    doc.save(path)
    return path


def agenda_docx(nombre, agenda, out_dir, Document, fecha="", institucion=""):
    doc = Document()
    doc.add_heading(f"Agenda - {nombre}", 0)
    if institucion:
        doc.add_paragraph(institucion)
    if fecha:
        doc.add_paragraph(f"Fecha: {fecha}")
    doc.add_heading("Orden del día", 1)
    for i, a in enumerate(agenda, 1):
        doc.add_paragraph(f"{i}. {a}")
    folder = os.path.join(out_dir, "Actas")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', " ", nombre).strip()
    path = os.path.join(folder, f"Agenda {safe} - {datetime.date.today().isoformat()}.docx")
    doc.save(path)
    return path
