"""Archivos que subes al chat de Jarvis (11.6): imágenes, PDF, Word, Excel, CSV, PowerPoint y texto.

Se guardan en tu equipo (carpeta «adjuntos» de Jarvis, se borran solos a los 7 días) y de cada uno se saca lo que la
IA necesita para leerlo: el texto (por páginas en los PDF), las tablas de las hojas de cálculo y, para las imágenes y
los PDF escaneados, las imágenes que se le muestran a la IA con visión. Solo trabaja con lo que TÚ subes al chat.
Lógica pura.
"""
import csv
import io
import os
import re
import time
import uuid

try:
    import pypdf
except ImportError:                                    # pragma: no cover
    pypdf = None
try:
    import pypdfium2                                   # para ver las páginas de un PDF como imágenes
except ImportError:                                    # pragma: no cover
    pypdfium2 = None

_dir = None
items = []                     # los últimos adjuntos: [{"id", "nombre", "tipo", "ruta", "ext", "t", "paginas", "bytes"}]
MAX_BYTES = 18_000_000
MAX_MEDIA = 300_000_000        # 12.23: audios y videos (se suben por partes)
MEDIA = ("audio", "video")
KINDS = {"imagen": (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"), "pdf": (".pdf",), "word": (".docx",),
         "excel": (".xlsx", ".xlsm"), "csv": (".csv", ".tsv"), "powerpoint": (".pptx",), "texto": (".txt", ".md", ".json", ".html", ".htm", ".py",
                                                                                                   ".js", ".css", ".xml", ".java", ".c", ".h", ".cpp", ".cc", ".hpp",
                                                                                                   ".cs", ".php", ".sql", ".sh", ".bat", ".ps1", ".ino", ".kt",
                                                                                                   ".go", ".rb", ".rs", ".ts", ".mjs", ".pyw", ".pde")}
KINDS["audio"] = (".mp3", ".wav", ".m4a", ".ogg", ".oga", ".opus", ".aac", ".flac", ".wma", ".amr", ".weba")
KINDS["video"] = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".3gp", ".m4v", ".wmv")
KIND_NAMES = {"audio": "audio", "video": "video", "imagen": "imagen", "pdf": "PDF", "word": "documento de Word", "excel": "hoja de Excel", "csv": "tabla CSV",
              "powerpoint": "presentación", "texto": "archivo de texto"}


def configure(config_dir):
    global _dir
    _dir = os.path.join(config_dir, "adjuntos")
    os.makedirs(_dir, exist_ok=True)
    purge()


def purge(days=7):
    if not _dir:
        return
    lim = time.time() - days * 86400
    for name in os.listdir(_dir):
        p = os.path.join(_dir, name)
        try:
            if os.path.isfile(p) and os.path.getmtime(p) < lim:
                os.remove(p)
        except OSError:
            pass


def kind_of(name):
    ext = os.path.splitext(str(name).lower())[1]
    for k, exts in KINDS.items():
        if ext in exts:
            return k
    return ""


def safe_name(name):
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", os.path.basename(str(name))).strip() or "archivo"
    return base[:120]


def add(name, data):
    """Guarda un archivo subido. → el adjunto. Lanza ValueError si no se puede."""
    if len(data) > MAX_BYTES:
        raise ValueError("el archivo es muy grande (máximo 18 MB)")
    name = safe_name(name)
    k = kind_of(name)
    if not k:
        raise ValueError("ese tipo de archivo no lo puedo leer (imágenes, PDF, Word, Excel, CSV, PowerPoint, texto, audio o video)")
    aid = uuid.uuid4().hex[:8]
    path = os.path.join(_dir, f"{aid}_{name}")
    with open(path, "wb") as f:
        f.write(data)
    return _register(aid, name, k, path, len(data))


def add_path(name, src):
    """12.23: registra un archivo que ya está en el disco de Jarvis (un audio o video subido por partes). Lo mueve."""
    name = safe_name(name)
    k = kind_of(name)
    if k not in MEDIA:
        raise ValueError("por partes solo se suben audios y videos")
    size = os.path.getsize(src)
    if not size:
        raise ValueError("vino vacío")
    if size > MAX_MEDIA:
        raise ValueError("el archivo es muy grande (máximo 300 MB)")
    aid = uuid.uuid4().hex[:8]
    path = os.path.join(_dir, f"{aid}_{name}")
    os.replace(src, path)
    return _register(aid, name, k, path, size)


def _register(aid, name, k, path, size):
    it = {"id": aid, "nombre": name, "tipo": k, "ruta": path, "ext": os.path.splitext(name)[1].lower(), "t": time.time(), "bytes": size,
          "paginas": pages_of(path, k)}
    items.append(it)
    del items[:-12]
    return it


def get(aid):
    return next((x for x in items if x["id"] == aid), None)


def recent(seconds=1800, n=6):
    now = time.time()
    return [x for x in items if now - x["t"] < seconds][-n:]


def pages_of(path, k):
    try:
        if k == "pdf" and pypdf:
            return len(pypdf.PdfReader(path).pages)
        if k == "powerpoint":
            from pptx import Presentation
            return len(Presentation(path).slides)
        if k == "excel":
            from openpyxl import load_workbook
            return len(load_workbook(path, read_only=True).sheetnames)
    except Exception:
        return 0
    return 1


# ----------------------------------------------------------------------------- leer el contenido
def text_of(it, limit=60000):
    """El texto del archivo (o "" si es imagen o un PDF escaneado)."""
    p, k = it["ruta"], it["tipo"]
    try:
        if k == "pdf" and pypdf:
            parts = []
            for i, pg in enumerate(pypdf.PdfReader(p).pages):
                t = (pg.extract_text() or "").strip()
                if t:
                    parts.append(f"[Página {i + 1}]\n{t}")
                if sum(len(x) for x in parts) > limit:
                    break
            return "\n\n".join(parts)[:limit]
        if k == "word":
            from docx import Document
            doc = Document(p)
            out = [para.text for para in doc.paragraphs if para.text.strip()]
            for ti, table in enumerate(doc.tables[:10]):
                out.append(f"[Tabla {ti + 1}]")
                for row in table.rows[:60]:
                    out.append(" | ".join(c.text.strip() for c in row.cells))
            return "\n".join(out)[:limit]
        if k == "excel":
            from openpyxl import load_workbook
            wb = load_workbook(p, read_only=True, data_only=True)
            out = []
            for ws in wb.worksheets[:6]:
                out.append(f"[Hoja «{ws.title}»]")
                for r, row in enumerate(ws.iter_rows(values_only=True)):
                    if r >= 300:
                        out.append("…")
                        break
                    if any(v not in (None, "") for v in row):
                        out.append(" | ".join("" if v is None else str(v) for v in row))
            return "\n".join(out)[:limit]
        if k == "csv":
            raw = open(p, "rb").read().decode("utf-8-sig", "replace")
            return raw[:limit]
        if k == "powerpoint":
            from pptx import Presentation
            out = []
            for i, s in enumerate(Presentation(p).slides, 1):
                txt = [sh.text_frame.text for sh in s.shapes if getattr(sh, "has_text_frame", False) and sh.text_frame.text.strip()]
                out.append(f"[Diapositiva {i}]\n" + "\n".join(txt))
            return "\n\n".join(out)[:limit]
        if k == "texto":
            return open(p, "rb").read().decode("utf-8", "replace")[:limit]
    except Exception as e:
        return f"(No pude leer el contenido: {str(e)[:100]})"
    return ""


def is_scanned(it, text=None):
    return it["tipo"] == "pdf" and len((text if text is not None else text_of(it, 4000)).strip()) < 80 * max(1, min(3, it.get("paginas") or 1))


def page_images(it, out_dir, first=1, last=None, scale=2.0, fmt="png"):
    """Las páginas de un PDF como imágenes (necesita pypdfium2). → [rutas]."""
    if pypdfium2 is None:
        raise ValueError("falta la librería pypdfium2 para ver las páginas del PDF (actualiza Jarvis)")
    pdf = pypdfium2.PdfDocument(it["ruta"])
    n = len(pdf)
    last = min(n, last or n)
    os.makedirs(out_dir, exist_ok=True)
    out = []
    base = os.path.splitext(it["nombre"])[0]
    for i in range(max(1, first) - 1, last):
        img = pdf[i].render(scale=scale).to_pil()
        path = os.path.join(out_dir, f"{base} - página {i + 1}.{fmt}")
        if fmt in ("jpg", "jpeg"):
            img.convert("RGB").save(path, quality=90)
        else:
            img.save(path)
        out.append(path)
    pdf.close()
    return out


def vision_images(it, tmp_dir, max_pages=4):
    """Las imágenes que se le muestran a la IA: la imagen misma (reducida) o las primeras páginas del PDF."""
    from PIL import Image
    os.makedirs(tmp_dir, exist_ok=True)
    if it["tipo"] == "imagen":
        im = Image.open(it["ruta"])
        im.seek(0)
        im = im.convert("RGB")
        im.thumbnail((2000, 2000))
        p = os.path.join(tmp_dir, f"v_{it['id']}.jpg")
        im.save(p, quality=88)
        return [p]
    if it["tipo"] == "pdf":
        return page_images(it, tmp_dir, 1, max_pages, scale=1.6, fmt="jpg")
    return []


def describe(it):
    size = it["bytes"] / 1024
    s = f"{size / 1024:.1f} MB" if size > 1024 else f"{size:.0f} KB"
    extra = {"pdf": f", {it['paginas']} página(s)", "powerpoint": f", {it['paginas']} diapositiva(s)", "excel": f", {it['paginas']} hoja(s)"}.get(it["tipo"], "")
    return f"{KIND_NAMES.get(it['tipo'], it['tipo'])} «{it['nombre']}» ({s}{extra})"


def table_rows(it, limit=2000):
    """Las filas de una hoja de cálculo o CSV (para convertir)."""
    if it["tipo"] == "csv":
        raw = open(it["ruta"], "rb").read().decode("utf-8-sig", "replace")
        dialect = csv.Sniffer().sniff(raw[:4000], delimiters=",;\t") if raw.strip() else csv.excel
        return [r for r in csv.reader(io.StringIO(raw), dialect)][:limit]
    from openpyxl import load_workbook
    ws = load_workbook(it["ruta"], read_only=True, data_only=True).worksheets[0]
    return [["" if v is None else v for v in r] for r in ws.iter_rows(values_only=True)][:limit]
