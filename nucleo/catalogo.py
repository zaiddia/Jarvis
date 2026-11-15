"""12.36: la base de datos de habilidades del modo docente, a la vista: página /docente con buscador y categorías,
«¿qué puedo hacer en modo docente?», «habilidades docentes de evaluación», y «exporta el catálogo docente» (Excel).
Los datos están en catalogo_docente.py."""
import os
import re

import catalogo_docente as C
from nucleo import J

_cd = {"win": None}


@J.app.route("/docente")
def teacher_catalog_page():
    from flask import render_template
    return render_template("docente.html", version=J.VERSION, asset_v=getattr(J, "ASSET_V", ""), look=J.settings.get("look", "clasico"))


@J.socketio.on("teacher_catalog")
def handle_teacher_catalog(data=None):
    q = str((data or {}).get("q") or "").strip()
    cats = C.by_cat()
    if q:
        ids = {h["id"] for h in C.search(q)}
        cats = [dict(c, habilidades=[h for h in c["habilidades"] if h["id"] in ids]) for c in cats]
        cats = [c for c in cats if c["habilidades"]]
    return {"categorias": cats, "total": len(C.H), "modo": J.current_mode()}


@J.socketio.on("teacher_try")
def handle_teacher_try(data=None):
    """Probar una frase del catálogo desde la página: la manda como si la escribieras."""
    frase = str((data or {}).get("frase") or "").strip()
    if not frase or not any(frase in h["frases"] for h in C.H):
        return {"ok": False}
    J.submit_command(frase)                             # como si la escribieras (pasa por la cola de órdenes)
    return {"ok": True}


def open_teacher_catalog():
    J._open_page("/docente", "Habilidades docentes", _cd)


def export_teacher_catalog():
    """El catálogo en Excel (una hoja por categoría y una con todo). → ruta."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Todas"
    head = ["Categoría", "Habilidad", "Qué hace", "Cómo pedirlo", "Qué produce", "Qué necesita", "Desde la versión"]
    cats = {cid: name for cid, name, _ in C.CATEGORIAS}

    def put(sheet, rows):
        sheet.append(head)
        for c in sheet[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="0F768A")
        for h in rows:
            sheet.append([cats[h["cat"]], h["nombre"], h["que"], "\n".join(f"«{f}»" for f in h["frases"]), h["produce"], h["necesita"], h["v"]])
        for col, w in zip("ABCDEFG", (20, 30, 60, 50, 24, 24, 10)):
            sheet.column_dimensions[col].width = w
        for row in sheet.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.freeze_panes = "A2"
    put(ws, C.H)
    for cid, name, _ in C.CATEGORIAS:
        rows = [h for h in C.H if h["cat"] == cid]
        if rows:
            put(wb.create_sheet(name[:31]), rows)
    folder = os.path.join(J.settings["output_dir"], "Jarvis")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "Catálogo de habilidades docentes.xlsx")
    wb.save(path)
    return path


_CAT_OPEN = re.compile(r"\b(?:abre|abreme|muestra|muestrame|ver)\s+(?:el\s+)?catalogo (?:docente|de (?:habilidades )?(?:docentes?|del docente|del colegio))\b|"
                       r"\bcatalogo docente\b(?!.*\bexcel\b)")
_CAT_ASK = re.compile(r"\bque (?:puedo hacer|puedes hacer|sabes hacer|haces)\s+(?:en (?:el )?modo docente|en (?:el )?colegio|como profe(?:sor)?|en (?:mis )?clases?)\b|"
                      r"\bhabilidades (?:docentes|del modo docente|del colegio)\b(?:\s+(?:de|para|sobre)\s+(.+))?$")
_CAT_EXPORT = re.compile(r"\b(?:exporta|pasa|guarda|descarga)\w*\s+(?:el\s+)?catalogo (?:docente|de habilidades docentes)\b")


def catalog_voice(text, t):
    if _CAT_EXPORT.search(t):
        try:
            path = export_teacher_catalog()
        except Exception as e:
            J.reply(f"No pude exportarlo: {e}", "CATÁLOGO")
            return True
        J.generated_files.add(path)
        if J.IS_WIN:
            try:
                os.startfile(path)
            except OSError:
                pass
        J.reply(f"Listo: el catálogo de {len(C.H)} habilidades docentes en Excel, con una hoja por categoría, en Documentos › Jarvis.", "CATÁLOGO")
        return True
    m = _CAT_ASK.search(t)
    if _CAT_OPEN.search(t) or m:
        q = (m.group(1) if m and m.lastindex else "") or ""
        if q:
            hits = C.search(q)[:6]
            if hits:
                J.reply(f"De «{q}» tengo: " + "; ".join(f"{h['nombre']} («{h['frases'][0]}»)" for h in hits) + ".", "CATÁLOGO")
                return True
        open_teacher_catalog()
        J.reply(f"Te abrí el catálogo docente: {len(C.H)} habilidades en {len(C.by_cat())} categorías (planeación, material, en el salón, "
                "evaluación, estudiantes, Saber, práctica, Classroom, gestión e inclusión), con las frases para pedirlas. "
                "Toca una frase para probarla.", "CATÁLOGO")
        return True
    return False


__all__ = ['_CAT_ASK', '_CAT_EXPORT', '_CAT_OPEN', '_cd', 'catalog_voice', 'export_teacher_catalog', 'handle_teacher_catalog',
           'handle_teacher_try', 'open_teacher_catalog', 'teacher_catalog_page']
