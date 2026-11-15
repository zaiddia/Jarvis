"""12.37: el Drive docente, armado y llenado por Jarvis.

- Jarvis crea en tu Drive la carpeta «Jarvis · Docente» con las 10 categorías y una carpeta por habilidad del catálogo
  (los mismos nombres y números que en catalogo_docente.py).
- Cada material del colegio que Jarvis crea se guarda solo en la carpeta de su habilidad (un quiz en «02 Material de
  clase › 01 Evaluación - quiz», los boletines en «05 Estudiantes y familias › 04 Boletines del periodo»…).
- Mantiene un índice en Excel en esa carpeta: cuántos archivos hay por habilidad, el último y el enlace a cada carpeta.

Solo usa el permiso «drive.file» que ya tenía Jarvis: ve y toca únicamente lo que él mismo creó, nada más de tu Drive.
"""
import json
import os
import re
import tempfile
import threading
import time
import urllib.parse

import aula
import catalogo_docente as C
import gservicios
import semana
from nucleo import J

FOLDER = "application/vnd.google-apps.folder"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ROOT_NAME = "Jarvis · Docente"
INDEX_NAME = "00 Índice de material docente.xlsx"
RECENT = 15 * 60                                   # un archivo nuevo es de la última habilidad usada si fue hace < 15 min
_dd = {"last": "", "t": 0.0, "cursos": [], "lock": threading.Lock()}
_LINK = "https://drive.google.com/drive/folders/"


# ---------------------------------------------------------------- nombres (iguales a la base de datos)
def tree_names():
    """{id habilidad: (nombre carpeta categoría, nombre carpeta habilidad)} y {id categoría: nombre carpeta}."""
    cats, skills = {}, {}
    for n, c in enumerate(C.by_cat(), 1):
        cats[c["id"]] = f"{n:02d} {c['nombre']}"
        for i, h in enumerate(c["habilidades"], 1):
            skills[h["id"]] = (c["id"], f"{i:02d} {h['nombre'].replace(' / ', ' - ')}")
    return cats, skills


def formats_search_url(sid):
    """Buscar en tu Drive la carpeta de formatos de esa habilidad (se abre en tu navegador; Jarvis no la lee)."""
    _cats, skills = tree_names()
    return "https://drive.google.com/drive/search?q=" + urllib.parse.quote(f'type:folder "{skills[sid][1]}"')


# ---------------------------------------------------------------- datos locales
def _path():
    return os.path.join(J.CONFIG_DIR, "drive_docente.json")


def dd_load():
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    for k, v in (("root", ""), ("cats", {}), ("skills", {}), ("index", ""), ("files", {})):
        d.setdefault(k, v)
    return d


def dd_save(d):
    tmp = _path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path())


# ---------------------------------------------------------------- qué habilidad se usó
def _words(s):
    return {w[:6] for w in re.findall(r"[a-z0-9]{3,}", C.norm(s))}


def skill_for(handler, t):
    """La habilidad del catálogo que más se parece a la frase, entre las que atiende esa función."""
    cands = [h for h in C.H if h["handler"] == handler]
    if not cands:
        return ""
    if len(cands) == 1:
        return cands[0]["id"]
    w = _words(t)
    best = max(cands, key=lambda h: max(len(w & _words(f)) for f in h["frases"]) * 2 + len(w & _words(h["nombre"])))
    return best["id"]


def courses_in(t):
    """12.38: los cursos tuyos que nombra la frase o el nombre de archivo («7A», «7-A», «7 A», «Séptimo B»…), en orden."""
    s = re.sub(r"[-_.·]+", " ", C.norm(t))
    s = re.sub(r"\b(\d{1,2})\s+([a-f])\b", r"\1\2", s)
    out = []
    for c in aula.data.get("cursos") or {}:
        base = re.sub(r"[-_.·]+", " ", C.norm(str(c).split(" · ")[0])).strip()
        tight = base.replace(" ", "")
        if not base:
            continue
        if any(re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", s) for k in {base, tight}):
            out.append(c)
    return sorted(out, key=aula.course_sort_key)


def course_folder(courses):
    """La subcarpeta dentro de la habilidad: el curso («7A»), o el grado si son varios del mismo («Grado 7°»), o ninguna."""
    if len(courses) == 1:
        return re.sub(r"[\\/:*?\"<>|]", "-", courses[0])
    gs = {semana.grade_key(c) for c in courses}
    if courses and len(gs) == 1 and None not in gs:
        return f"Grado {gs.pop()}°"
    return ""


def note_skill(handler, t):
    """Lo llama el envoltorio de cada habilidad docente cuando atendió una frase del colegio."""
    if not J.school_ok(t):
        return
    sid = skill_for(handler, t)
    if sid:
        _dd["last"], _dd["t"], _dd["cursos"] = sid, time.time(), courses_in(t)


def note_skill_direct(sid, courses):
    """Para lo automático (respaldo, resumen, clase de mañana): qué habilidad produce el archivo que viene."""
    _dd["last"], _dd["t"], _dd["cursos"] = sid, time.time(), list(courses or [])


def recent_skill():
    return _dd["last"] if _dd["last"] and time.time() - _dd["t"] < RECENT else ""


# ---------------------------------------------------------------- Drive
def _ensure(client, fid, name, parent):
    if fid:
        try:
            f = client.call("GET", f"files/{fid}", {"fields": "id,trashed"}, base=gservicios.DRIVE_API)
            if not f.get("trashed"):
                return fid
        except Exception:
            pass
    body = {"name": name, "mimeType": FOLDER, "parents": [parent]}
    return client.call("POST", "files", {"fields": "id"}, body=body, base=gservicios.DRIVE_API)["id"]


def ensure_skill_folder(client, d, sid):
    cats, skills = tree_names()
    if not d["root"] or d.get("_checked_root") is None:
        parent = gservicios.ensure_folder(client, J.settings["drive_folder_id"])
        if parent != J.settings["drive_folder_id"]:
            J.apply_settings({"drive_folder_id": parent})
        d["root"] = _ensure(client, d["root"], ROOT_NAME, parent)
        d["_checked_root"] = True
    cid, sname = skills[sid]
    d["cats"][cid] = _ensure(client, d["cats"].get(cid, ""), cats[cid], d["root"])
    d["skills"][sid] = _ensure(client, d["skills"].get(sid, ""), sname, d["cats"][cid])
    return d["skills"][sid]


def build_tree():
    """Las 64 carpetas (o las que falten). → número de carpetas de habilidad."""
    client = J.classroom_client()
    with _dd["lock"]:
        d = dd_load()
        d.pop("_checked_root", None)
        for h in C.H:
            ensure_skill_folder(client, d, h["id"])
        d.pop("_checked_root", None)
        write_index(client, d)
        dd_save(d)
    return len(d["skills"])


def file_material(path, sid, courses=()):
    """Sube el archivo a la carpeta de su habilidad (y del curso o grado) y actualiza el índice. → enlace del archivo."""
    client = J.classroom_client()
    with _dd["lock"]:
        d = dd_load()
        folder = ensure_skill_folder(client, d, sid)
        d.pop("_checked_root", None)
        sub = course_folder(list(courses or []))
        if sub:                                        # 12.38: varios cursos y grados: una subcarpeta por curso (o grado)
            key = f"{sid}|{sub}"
            d.setdefault("subs", {})[key] = _ensure(client, d.get("subs", {}).get(key, ""), sub, folder)
            folder = d["subs"][key]
        f = gservicios.upload(client, path, folder)
        d["files"].setdefault(sid, []).append({"n": os.path.basename(path), "l": f.get("webViewLink", ""), "t": time.strftime("%Y-%m-%d %H:%M")})
        d["files"][sid] = d["files"][sid][-200:]
        write_index(client, d)
        dd_save(d)
    return f.get("webViewLink", "")


def index_xlsx(d, out):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    cats, skills = tree_names()
    wb = Workbook()
    ws = wb.active
    ws.title = "Material de Jarvis"
    ws.append(["Categoría", "Habilidad", "Archivos que hizo Jarvis", "Último archivo", "Fecha", "Carpeta"])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0F768A")
    for c in C.by_cat():
        for h in c["habilidades"]:
            files = d["files"].get(h["id"], [])
            last = files[-1] if files else {}
            row = [cats[c["id"]], skills[h["id"]][1], len(files), last.get("n", ""), last.get("t", ""), ""]
            ws.append(row)
            r = ws.max_row
            if last.get("l"):
                ws.cell(r, 4).hyperlink = last["l"]
                ws.cell(r, 4).font = Font(color="0563C1", underline="single")
            if d["skills"].get(h["id"]):
                ws.cell(r, 6, "Abrir carpeta").hyperlink = _LINK + d["skills"][h["id"]]
                ws.cell(r, 6).font = Font(color="0563C1", underline="single")
    n = ws.max_row
    ws.append(["Total", "", f"=SUM(C2:C{n})", "", "", ""])
    ws.cell(ws.max_row, 1).font = Font(bold=True)
    for col, w in zip("ABCDEF", (26, 36, 14, 44, 16, 16)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    wb.save(out)


def write_index(client, d):
    tmp = os.path.join(tempfile.gettempdir(), INDEX_NAME)
    index_xlsx(d, tmp)
    with open(tmp, "rb") as f:
        data = f.read()
    if d["index"]:
        try:
            client.raw("PATCH", gservicios.UPLOAD + f"/{d['index']}?uploadType=media&fields=id", data, XLSX)
            return
        except Exception:
            d["index"] = ""                          # lo borraste: se crea otro
    body, ctype = gservicios.multipart({"name": INDEX_NAME, "parents": [d["root"]]}, data, XLSX)
    d["index"] = client.raw("POST", gservicios.UPLOAD + "?uploadType=multipart&fields=id", body, ctype)["id"]


# ---------------------------------------------------------------- automático
def docente_file(path, sid=None):
    """Desde on_new_file: si el archivo es de una habilidad docente reciente, va a su carpeta. True si se encargó."""
    sid = sid or recent_skill()
    if not (sid and J.settings.get("drive_docente", True) and J.gdrive_ready()):
        return False
    if os.path.splitext(path)[1].lower() not in (".docx", ".pptx", ".xlsx", ".pdf", ".png", ".jpg", ".mp4", ".csv", ".zip", ".mp3"):
        return False
    _cats, skills = tree_names()
    courses = courses_in(os.path.splitext(os.path.basename(path))[0]) or list(_dd.get("cursos") or [])

    def work():
        try:
            J.drive_docente_upload(path, sid, courses)
            sub = course_folder(courses)
            J.log_terminal(f"Guardado en Drive › {ROOT_NAME} › {skills[sid][1]}{' › ' + sub if sub else ''}: {os.path.basename(path)}", "DRIVE")
        except Exception as e:
            J.note_error("DRIVE", e)
    J.start_job("Guardando en el Drive docente", work, "drive")
    return True


def drive_docente_upload(path, sid, courses=()):
    return file_material(path, sid, courses)


def folder_links():
    """{id habilidad: enlace a su carpeta de Jarvis en Drive} (las que ya existen)."""
    return {sid: _LINK + fid for sid, fid in dd_load()["skills"].items() if fid}


_TREE = re.compile(r"\b(?:crea|creame|arma|armame|organiza|prepara)\w*\s+(?:las\s+|mis\s+)?carpetas\s+(?:docentes|del (?:colegio|modo docente)|de (?:las )?habilidades docentes)\b"
                   r"|\b(?:crea|arma|organiza)\w*\s+(?:el|mi)\s+drive\s+docente\b")
_OPEN = re.compile(r"\b(?:abre|abreme|muestra|muestrame)\s+(?:el|mi)\s+drive\s+docente\b")


def drive_docente_voice(text, t):
    if _TREE.search(t):
        if not J.gdrive_ready():
            J.reply("Para crear las carpetas en tu Drive necesito Google conectado (Ajustes › Conexiones › Google).", "DRIVE")
            return True

        def work():
            try:
                n = build_tree()
            except Exception as e:
                J.reply(f"No pude crear las carpetas en Drive: {e}", "DRIVE")
                return
            J.reply(f"Listo: en tu Drive quedó «Jarvis › {ROOT_NAME}» con las 10 categorías, {n} carpetas de habilidad y un índice. "
                    "Desde ahora, cada material del colegio que yo haga se guarda solo en su carpeta.", "DRIVE")
        J.reply("Creando las carpetas docentes en tu Drive…", "DRIVE")
        J.start_job("Carpetas docentes en Drive", work, "drive")
        return True
    if _OPEN.search(t):
        d = dd_load()
        if not d["root"]:
            J.reply("Aún no he creado tu Drive docente. Di «crea las carpetas docentes en Drive».", "DRIVE")
            return True
        J._open_link(_LINK + d["root"])
        J.reply(f"Te abrí «{ROOT_NAME}» en tu navegador.", "DRIVE")
        return True
    return False


__all__ = ['FOLDER', 'INDEX_NAME', 'RECENT', 'ROOT_NAME', 'XLSX', '_LINK', '_OPEN', '_TREE', '_dd', '_ensure', '_path', '_words',
           'build_tree', 'course_folder', 'courses_in', 'dd_load', 'dd_save', 'docente_file', 'drive_docente_upload', 'drive_docente_voice', 'ensure_skill_folder',
           'file_material', 'folder_links', 'formats_search_url', 'index_xlsx', 'note_skill', 'note_skill_direct', 'recent_skill', 'skill_for',
           'tree_names', 'write_index']
