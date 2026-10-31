"""Conversiones entre archivos (11.6): imagen ↔ PDF, PDF → Word / imágenes / texto, Word / PowerPoint / Excel → PDF,
Excel ↔ CSV, cambiar el formato o el peso de una imagen, y unir, dividir o girar PDF. Lógica pura.

Las conversiones a PDF de Word, PowerPoint y Excel (y PDF → Word con el formato original) usan el Office de tu equipo
si lo tienes; si no, LibreOffice; si no hay ninguno, PDF → Word sale con el texto (editable) y lo demás lo avisa.
"""
import csv
import os
import re
import shutil
import subprocess
import sys

import adjuntos

TARGETS = {"pdf": "PDF", "word": "Word", "texto": "texto", "imagenes": "imágenes", "png": "PNG", "jpg": "JPG", "webp": "WEBP", "excel": "Excel",
           "csv": "CSV", "unir": "un solo PDF", "comprimir": "imagen más liviana", "dividir": "PDF por páginas", "girar": "PDF girado"}


class ConvertError(ValueError):
    pass


def _out(out_dir, base, ext):
    os.makedirs(out_dir, exist_ok=True)
    base = re.sub(r"^[0-9a-f]{8}_", "", os.path.splitext(os.path.basename(base))[0])
    path = os.path.join(out_dir, f"{base}.{ext}")
    n = 2
    while os.path.exists(path):
        path = os.path.join(out_dir, f"{base} ({n}).{ext}")
        n += 1
    return path


# ----------------------------------------------------------------------------- Office / LibreOffice
def _office(app, src, dst, fmt):
    """Convierte con Word / PowerPoint / Excel por COM (solo en Windows con Office). True si lo logró."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return False
    pythoncom.CoInitialize()
    try:
        src, dst = os.path.abspath(src), os.path.abspath(dst)
        if app == "word":
            w = win32com.client.DispatchEx("Word.Application")
            w.Visible, w.DisplayAlerts = False, 0
            try:
                d = w.Documents.Open(src, ConfirmConversions=False, ReadOnly=True, AddToRecentFiles=False)
                d.SaveAs2(dst, FileFormat=fmt)           # 17 = PDF, 16 = DOCX
                d.Close(False)
            finally:
                w.Quit()
        elif app == "powerpoint":
            p = win32com.client.DispatchEx("PowerPoint.Application")
            try:
                pr = p.Presentations.Open(src, ReadOnly=True, WithWindow=False)
                pr.SaveAs(dst, 32)                       # 32 = PDF
                pr.Close()
            finally:
                p.Quit()
        elif app == "excel":
            x = win32com.client.DispatchEx("Excel.Application")
            x.Visible, x.DisplayAlerts = False, False
            try:
                wb = x.Workbooks.Open(src, ReadOnly=True)
                wb.ExportAsFixedFormat(0, dst)           # 0 = PDF
                wb.Close(False)
            finally:
                x.Quit()
        return os.path.exists(dst)
    except Exception:
        return False
    finally:
        pythoncom.CoUninitialize()


def _soffice():
    for c in ("soffice", "libreoffice", r"C:\Program Files\LibreOffice\program\soffice.exe", r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"):
        p = shutil.which(c) or (c if os.path.exists(c) else None)
        if p:
            return p
    return None


def _libre(src, out_dir, ext):
    exe = _soffice()
    if not exe:
        return None
    try:
        subprocess.run([exe, "--headless", "--convert-to", ext, "--outdir", out_dir, src], capture_output=True, timeout=180,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return None
    got = os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0] + "." + ext)
    return got if os.path.exists(got) else None


def _to_pdf_office(it, out_dir):
    app = {"word": "word", "powerpoint": "powerpoint", "excel": "excel"}[it["tipo"]]
    dst = _out(out_dir, it["nombre"], "pdf")
    if _office(app, it["ruta"], dst, 17):
        return dst
    got = _libre(it["ruta"], out_dir, "pdf")
    if got:
        final = _out(out_dir, it["nombre"], "pdf") if os.path.basename(got) != os.path.basename(dst) else dst
        if got != final:
            os.replace(got, final)
        return final
    raise ConvertError("para pasar a PDF un archivo de Office necesito Microsoft Office o LibreOffice en tu equipo")


# ----------------------------------------------------------------------------- conversiones
def images_to_pdf(its, out_dir):
    from PIL import Image
    pages = []
    for it in its:
        im = Image.open(it["ruta"])
        im.seek(0)
        im = im.convert("RGB")
        pages.append(im)
    dst = _out(out_dir, its[0]["nombre"] if len(its) == 1 else f"{os.path.splitext(its[0]['nombre'])[0]} y {len(its) - 1} más", "pdf")
    pages[0].save(dst, "PDF", resolution=150, save_all=True, append_images=pages[1:])
    return dst


def image_to(it, out_dir, fmt, compress=False):
    from PIL import Image
    im = Image.open(it["ruta"])
    im.seek(0)
    if compress:
        im.thumbnail((1600, 1600))
    ext = {"jpg": "jpg", "png": "png", "webp": "webp"}[fmt]
    dst = _out(out_dir, it["nombre"] + (" (liviana)" if compress else ""), ext)
    if ext == "jpg":
        im.convert("RGB").save(dst, quality=72 if compress else 90, optimize=True)
    elif ext == "webp":
        im.save(dst, quality=72 if compress else 88)
    else:
        im.save(dst, optimize=True)
    return dst


def pdf_to_word(it, out_dir, Document, ocr_text=""):
    """Con Word: conserva el formato. Sin Word: el texto de cada página (o el leído por la IA si es escaneado)."""
    dst = _out(out_dir, it["nombre"], "docx")
    if _office("word", it["ruta"], dst, 16):
        return dst, "formato"
    if Document is None:
        raise ConvertError("falta python-docx")
    text = ocr_text or adjuntos.text_of(it, 400000)
    if not text.strip():
        raise ConvertError("el PDF no trae texto (parece escaneado) y no tengo la IA con visión para leerlo")
    doc = Document()
    doc.add_heading(os.path.splitext(re.sub(r"^[0-9a-f]{8}_", "", it["nombre"]))[0], 1)
    for block in re.split(r"\n(?=\[Página \d+\])", text):
        m = re.match(r"\[Página (\d+)\]\n?", block)
        if m and int(m.group(1)) > 1:
            doc.add_page_break()
        body = block[m.end():] if m else block
        for para in re.split(r"\n{2,}|(?<=[.:;])\n", body):
            if para.strip():
                doc.add_paragraph(re.sub(r"\s*\n\s*", " ", para.strip()))
    doc.save(dst)
    return dst, "texto"


def to_text(it, out_dir, text=""):
    dst = _out(out_dir, it["nombre"], "txt")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(text or adjuntos.text_of(it, 2_000_000))
    return dst


def excel_to_csv(it, out_dir):
    rows = adjuntos.table_rows(it, 1_000_000)
    dst = _out(out_dir, it["nombre"], "csv")
    with open(dst, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f, delimiter=";").writerows(rows)              # «;» para que Excel en español lo abra bien
    return dst


def csv_to_excel(it, out_dir):
    from openpyxl import Workbook
    rows = adjuntos.table_rows(it, 1_000_000)
    wb = Workbook()
    ws = wb.active
    for r in rows:
        out = []
        for v in r:
            s = str(v).strip()
            if re.fullmatch(r"-?\d+", s):
                out.append(int(s))
            elif re.fullmatch(r"-?\d+[.,]\d+", s):
                out.append(float(s.replace(",", ".")))
            else:
                out.append(v)
        ws.append(out)
    dst = _out(out_dir, it["nombre"], "xlsx")
    wb.save(dst)
    return dst


def merge_pdfs(its, out_dir):
    import pypdf
    w = pypdf.PdfWriter()
    for it in its:
        for p in pypdf.PdfReader(it["ruta"]).pages:
            w.add_page(p)
    dst = _out(out_dir, f"{os.path.splitext(its[0]['nombre'])[0]} (unido)", "pdf")
    with open(dst, "wb") as f:
        w.write(f)
    return dst


def split_pdf(it, out_dir, first=None, last=None):
    """Solo las páginas first..last, o un PDF por página si no se dicen."""
    import pypdf
    r = pypdf.PdfReader(it["ruta"])
    n = len(r.pages)
    if first:
        last = min(n, last or first)
        w = pypdf.PdfWriter()
        for i in range(first - 1, last):
            w.add_page(r.pages[i])
        dst = _out(out_dir, f"{os.path.splitext(it['nombre'])[0]} (páginas {first}-{last})", "pdf")
        with open(dst, "wb") as f:
            w.write(f)
        return [dst]
    out = []
    for i in range(min(n, 200)):
        w = pypdf.PdfWriter()
        w.add_page(r.pages[i])
        dst = _out(out_dir, f"{os.path.splitext(it['nombre'])[0]} - página {i + 1}", "pdf")
        with open(dst, "wb") as f:
            w.write(f)
        out.append(dst)
    return out


def rotate_pdf(it, out_dir, degrees=90):
    import pypdf
    w = pypdf.PdfWriter()
    for p in pypdf.PdfReader(it["ruta"]).pages:
        w.add_page(p.rotate(degrees))
    dst = _out(out_dir, f"{os.path.splitext(it['nombre'])[0]} (girado)", "pdf")
    with open(dst, "wb") as f:
        w.write(f)
    return dst


def options_for(its):
    """Las conversiones que tienen sentido para estos adjuntos."""
    kinds = {i["tipo"] for i in its}
    if len(its) > 1:
        if kinds == {"imagen"}:
            return ["pdf"]
        if kinds == {"pdf"}:
            return ["unir"]
        return []
    k = its[0]["tipo"]
    if k == "imagen":
        own = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".webp": "webp"}.get(its[0].get("ext", ""))
        return [x for x in ["pdf", "png", "jpg", "webp", "comprimir"] if x != own]
    return {"imagen": ["pdf", "png", "jpg", "webp", "comprimir"], "pdf": ["word", "imagenes", "texto", "dividir", "girar"],
            "word": ["pdf", "texto"], "powerpoint": ["pdf", "texto"], "excel": ["pdf", "csv"], "csv": ["excel"], "texto": []}.get(k, [])
