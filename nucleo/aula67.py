"""12.67: cinco funciones nuevas.

  1. Juegos de repaso para imprimir: «haz una sopa de letras de la célula para sexto» · «crucigrama del sistema solar» ·
     «juego de emparejar de la Independencia» · «juegos de repaso de fracciones» (los tres). Word para el estudiante y Word aparte
     con las respuestas. «… de lo que subí» los saca del documento subido.
  2. Mapas: «haz un mapa conceptual de la fotosíntesis para séptimo» · «mapa mental del documento que subí» (o el botón «Mapa
     conceptual» del archivo). Imagen y PDF, y la versión en blanco para que los estudiantes la completen.
  3. Fluidez lectora: sube el audio de un estudiante leyendo y di «evalúa la lectura de Juan Pérez de 3A con este texto: …» (o sube
     también el texto). Palabras por minuto, correctas por minuto, omitidas, cambiadas y repetidas, y el nivel del grado.
     «¿Cómo va la fluidez de 3A?» → el avance del curso en el año, en Word. Jarvis solo analiza audios que tú subes: no graba.
  4. «Carta de recomendación para Ana Ruiz de 11A para la beca de la Universidad del Valle, destaca que lidera el club de
     robótica»: con sus notas registradas, en Word con firma («guarda esta imagen como mi firma» con la foto de la firma).
  5. Pico y placa (Cali): «mi placa es ABC123» · «¿tengo pico y placa hoy / mañana / el viernes?» · «¿cuándo tengo pico y placa?»
     · «ya pagué la tasa por congestión» · «no me avises del pico y placa». Avisa en la mañana los días que aplica; la rotación
     se verifica en internet cada semestre.

La lógica pura está en cole67.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import threading

import adjuntos
import animar
import aula
import cole67 as C
import festivos
import seguimiento
import vocacional
from nucleo import J

A67_ACTIONS = {"fluidez": "Evaluar lectura", "mapa67": "Mapa conceptual"}
_a67_lock = threading.Lock()
_A67_COURSE = (r"(?:grado\s+)?(?:\d{1,2}\s?-?\s?[a-z0-9]?|sexto|septimo|octavo|noveno|decimo|once|undecimo|primero|segundo|tercero|"
               r"cuarto|quinto)")
_A67_MESES = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()


def _a67_path():
    return os.path.join(J.CONFIG_DIR, "aula67.json")


def a67_data():
    try:
        with open(_a67_path(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d.setdefault("fluidez", {})
    d.setdefault("pyp", {})
    return d


def a67_save(d):
    with _a67_lock:
        os.makedirs(J.CONFIG_DIR, exist_ok=True)
        tmp = _a67_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1, default=str)
        os.replace(tmp, _a67_path())


def _a67_folder(name):
    folder = os.path.join(J.settings["output_dir"], name)
    os.makedirs(folder, exist_ok=True)
    return folder


def _a67_safe(s):
    return re.sub(r'[\\/:*?"<>|]+', "-", str(s)).strip()[:90] or "Jarvis"


def _a67_recent(kinds, skip=None):
    for it in adjuntos.recent(1800):
        if it["tipo"] in kinds and (skip is None or it["id"] != skip):
            return it
    return None


def _a67_course(spoken):
    try:
        return J._resolve_course(spoken) if spoken else None
    except Exception:
        return None


def _a67_long_date(d):
    return f"{d.day} de {_A67_MESES[d.month - 1]} de {d.year}"


def _a67_doc_header(doc, title, student_line=True):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    inst = J.settings.get("aula_institucion", "")
    if inst:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run(inst).bold = True
    h = doc.add_heading(title, 1)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if student_line:
        doc.add_paragraph("Nombre: ____________________________________   Curso: ________   Fecha: ____________")


def _a67_shade(cell, hex_color):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    tc = cell._tc.get_or_add_tcPr()
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear")
    sh.set(qn("w:color"), "auto")
    sh.set(qn("w:fill"), hex_color)
    tc.append(sh)


def _a67_cell(cell, text, size=13, bold=False, color=None):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.bold = bold
    if color:
        r.font.color.rgb = RGBColor(*color)


def _a67_grid_table(doc, rows, cols, cm):
    from docx.shared import Cm
    tb = doc.add_table(rows=rows, cols=cols)
    tb.style = "Table Grid"
    for row in tb.rows:
        row.height = Cm(cm)
        for c in row.cells:
            c.width = Cm(cm)
    return tb


# ============================================================================ 1. JUEGOS DE REPASO
def a67_wordsearch_doc(doc, ws, pairs, answers=False):
    n = ws["size"]
    cm = min(1.0, 16.5 / n)
    tb = _a67_grid_table(doc, n, n, cm)
    sol = ws["solucion"]
    for r in range(n):
        for c in range(n):
            if answers:
                if sol[r][c]:
                    _a67_cell(tb.cell(r, c), sol[r][c], 12, True)
                    _a67_shade(tb.cell(r, c), "FFE08A")
                else:
                    _a67_cell(tb.cell(r, c), ws["grid"][r][c], 10, False, (190, 190, 190))
            else:
                _a67_cell(tb.cell(r, c), ws["grid"][r][c], 12)
    placed = {p["palabra"] for p in ws["placed"]}
    doc.add_paragraph()
    doc.add_paragraph("Busca estas palabras (pueden estar en horizontal, vertical, diagonal" +
                      (" y al revés" if any(p["dr"] < 0 or p["dc"] < 0 for p in ws["placed"]) else "") + "):").runs[0].bold = True
    doc.add_paragraph("   ·   ".join(C.letters(p["termino"]) for p in pairs if C.letters(p["termino"]) in placed))


def a67_crossword_doc(doc, cw, answers=False):
    num = {(p["fila"], p["col"]): p["num"] for p in cw["palabras"]}
    cm = min(0.95, 16.5 / max(cw["w"], 1))
    tb = _a67_grid_table(doc, cw["h"], cw["w"], cm)
    for r in range(cw["h"]):
        for c in range(cw["w"]):
            cell = tb.cell(r, c)
            if (r, c) not in cw["cells"]:
                _a67_shade(cell, "262626")
                continue
            txt = cw["cells"][(r, c)] if answers else ""
            lab = str(num[(r, c)]) if (r, c) in num else ""
            if lab and not answers:
                _a67_cell(cell, lab, 7, True, (60, 60, 60))
            else:
                _a67_cell(cell, (lab + " " if lab and answers else "") + txt, 10 if answers else 7, answers)
    doc.add_paragraph()
    for d, name in (("H", "Horizontales"), ("V", "Verticales")):
        ps = [p for p in cw["palabras"] if p["dir"] == d]
        if ps:
            doc.add_paragraph(name).runs[0].bold = True
            for p in ps:
                doc.add_paragraph(f"{p['num']}. {p['pista']}" + (f"  →  {p['palabra']}" if answers else ""))


def a67_matching_doc(doc, mt, answers=False):
    if answers:
        doc.add_paragraph("   ·   ".join(f"{n} → {L}" for n, L in mt["clave"].items()))
        return
    doc.add_paragraph("Escribe en el paréntesis la letra de la definición que corresponde a cada término.")
    tb = doc.add_table(rows=len(mt["izq"]), cols=2)
    tb.style = "Table Grid"
    for i, ((n, term), (L, clue)) in enumerate(zip(mt["izq"], mt["der"])):
        tb.cell(i, 0).text = f"{n}. {term}   (    )"
        tb.cell(i, 1).text = f"{L}. {clue}"


def make_games(tema, curso="", which="todos", fuente=""):
    """→ {"alumno": ruta, "respuestas": ruta, "titulo", "n", "faltan"}"""
    raw = J.ai_chat([{"role": "user", "content": C.games_prompt(tema, curso, 12 if which != "emparejar" else 10, fuente)}],
                    json_mode=True, max_tokens=2000)
    g = C.clean_pairs(J._extract_json(raw), 12)
    pairs = g["pares"]
    grade = aula.grade_of(curso) if curso else None
    kinds = ["sopa", "crucigrama", "emparejar"] if which == "todos" else [which]
    built = {}
    if "sopa" in kinds:
        built["sopa"] = C.wordsearch([p["termino"] for p in pairs], hard=grade is None or grade >= 5)
    if "crucigrama" in kinds:
        built["crucigrama"] = C.crossword(pairs[:10])
    if "emparejar" in kinds:
        built["emparejar"] = C.matching(pairs[:10])
    names = {"sopa": "Sopa de letras", "crucigrama": "Crucigrama", "emparejar": "Emparejar"}
    label = names[kinds[0]] if len(kinds) == 1 else "Juegos de repaso"
    out = {}
    for answers in (False, True):
        doc = J.Document()
        for i, k in enumerate(kinds):
            if i:
                doc.add_page_break()
            _a67_doc_header(doc, f"{names[k]}: {g['titulo']}" + (" (respuestas)" if answers else ""), not answers)
            if k == "sopa":
                a67_wordsearch_doc(doc, built[k], pairs, answers)
            elif k == "crucigrama":
                a67_crossword_doc(doc, built[k], answers)
            else:
                a67_matching_doc(doc, built[k], answers)
        base = _a67_safe(f"{label} - {g['titulo']}" + (f" - {curso}" if curso else ""))
        path = os.path.join(_a67_folder("Juegos de repaso"), base + (" (respuestas)" if answers else "") + ".docx")
        doc.save(path)
        out["respuestas" if answers else "alumno"] = path
    faltan = (built.get("sopa", {}).get("faltan") or []) + [C.letters(p["termino"]) for p in built.get("crucigrama", {}).get("faltan") or []]
    out.update(titulo=g["titulo"], n=len(pairs), faltan=faltan, label=label)
    return out


_A67_GAME = re.compile(r"^(?:jarvis\s+)?(?:haz|hazme|crea|creame|genera|generame|prepara|preparame|arma|armame|disena|disename)\s+"
                       r"(?:una|un|el|la|los|unos)\s+(sopa de letras|crucigrama|juego de emparejar|juego de relacionar|juego de unir|"
                       r"juegos de repaso|juegos para repasar)\s+(?:sobre|de|del|de la|de los|de las|con|acerca de)\s+(.+?)"
                       rf"(?:\s+(?:para|en)\s+(?:el\s+|los de\s+)?({_A67_COURSE})\b.*)?$")
_A67_FROM_DOC = re.compile(r"^(?:esto|este documento|el documento|el archivo|este archivo|lo que (?:te )?subi|el pdf|la guia|la lectura)"
                           r"(?: que (?:te )?subi)?$")


def _a67_source(tema):
    """Si el tema es «lo que subí»: (texto, nombre) del documento subido; si no, ("", tema)."""
    if not _A67_FROM_DOC.match(tema):
        return "", tema, None
    it = _a67_recent(("pdf", "word", "texto", "powerpoint", "imagen"))
    if not it:
        return "", "", None
    return (J._text_of_item(it) or "")[:12000], it["nombre"].rsplit(".", 1)[0], it


def _a67_games_voice(text, t):
    m = _A67_GAME.match(t)
    if not m:
        return False
    word = m.group(1)
    which = "sopa" if word.startswith("sopa") else "crucigrama" if word == "crucigrama" else "todos" if word.startswith("juegos") else "emparejar"
    fuente, tema, it = _a67_source(m.group(2).strip())
    if not tema:
        J.reply("Sube primero el documento y luego pídeme el juego «de lo que subí».", "JUEGOS")
        return True
    if J.state.get("ai") != "ok":
        J.reply("Para escoger las palabras y las pistas necesito la IA conectada.", "JUEGOS")
        return True
    curso = _a67_course(m.group(3) or "") or (m.group(3) or "").upper().replace(" ", "")
    what = {"todos": "los juegos de repaso", "sopa": "la sopa de letras", "crucigrama": "el crucigrama", "emparejar": "el juego de emparejar"}
    J.reply(f"Preparo {what[which]} de {tema}…", "JUEGOS")

    def work():
        try:
            r = J.make_games(tema, curso, which, fuente)
        except (J.AIError, ValueError) as e:
            J.notify(J.ai_error_reply(e) if isinstance(e, J.AIError) else f"No pude armar el juego: {e}.", "JUEGOS")
            return
        J.generated_files.add(r["alumno"])
        J.generated_files.add(r["respuestas"])
        J.notify(f"Listo: {r['label'].lower()} de «{r['titulo']}» con {r['n']} términos, en Word para imprimir, y la hoja de respuestas "
                 "aparte, en Documentos, Jarvis, Juegos de repaso." +
                 (f" No cupieron: {', '.join(r['faltan'][:4])}." if r["faltan"] else ""), "JUEGOS")
        if J.settings.get("aula_open_docs", True):
            J._open_doc(r["alumno"])
    J.start_job("Armando el juego de repaso", work, "juegos")
    return True


# ============================================================================ 2. MAPAS MENTALES Y CONCEPTUALES
def make_map(tema, kind="mental", curso="", fuente=""):
    raw = J.ai_chat([{"role": "user", "content": C.map_prompt(tema, kind, curso, fuente)}], json_mode=True, max_tokens=1800)
    m = C.clean_map(J._extract_json(raw), kind)
    folder = _a67_folder("Mapas")
    base = os.path.join(folder, _a67_safe(f"Mapa {kind} - {m['titulo']}" + (f" - {curso}" if curso else "")))
    out = {"titulo": m["titulo"]}
    for blank, suf in ((False, ""), (True, " (en blanco)")):
        img = C.render_map(m, animar.font, blank)
        img.save(base + suf + ".png")
        img.save(base + suf + ".pdf", "PDF", resolution=150.0)
        out["blank" if blank else "png"] = base + suf + ".png"
        out["blank_pdf" if blank else "pdf"] = base + suf + ".pdf"
    return out


_A67_MAP = re.compile(r"^(?:jarvis\s+)?(?:haz|hazme|crea|creame|genera|generame|prepara|preparame|arma|armame|dibuja|dibujame)\s+"
                      r"(?:un|el)\s+mapa\s+(mental|conceptual)\s+(?:sobre|de|del|de la|de los|de las|acerca de|con)\s+(.+?)"
                      rf"(?:\s+(?:para|en)\s+(?:el\s+|los de\s+)?({_A67_COURSE})\b.*)?$")


def _a67_map_start(tema, kind, curso, fuente):
    def work():
        try:
            r = J.make_map(tema, kind, curso, fuente)
        except (J.AIError, ValueError) as e:
            J.notify(J.ai_error_reply(e) if isinstance(e, J.AIError) else f"No pude hacer el mapa: {e}.", "MAPAS")
            return
        for k in ("png", "pdf", "blank", "blank_pdf"):
            J.generated_files.add(r[k])
        J.notify(f"Listo el mapa {kind} de «{r['titulo']}», en imagen y PDF, y la versión en blanco para que tus estudiantes lo "
                 "completen, en Documentos, Jarvis, Mapas.", "MAPAS")
        if J.settings.get("aula_open_docs", True):
            J._open_doc(r["png"])
    J.start_job("Dibujando el mapa", work, "mapa")


def _a67_map_voice(text, t):
    m = _A67_MAP.match(t)
    if not m:
        return False
    fuente, tema, it = _a67_source(m.group(2).strip())
    if not tema:
        J.reply("Sube primero el documento y luego pídeme el mapa «del documento que subí».", "MAPAS")
        return True
    if J.state.get("ai") != "ok":
        J.reply("Para armar el mapa necesito la IA conectada.", "MAPAS")
        return True
    curso = _a67_course(m.group(3) or "") or (m.group(3) or "").upper().replace(" ", "")
    J.reply(f"Dibujo el mapa {m.group(1)} de {tema}…", "MAPAS")
    _a67_map_start(tema, m.group(1), curso, fuente)
    return True


# ============================================================================ 3. FLUIDEZ LECTORA
def a67_duration(path):
    """Segundos del audio (lo dice ffmpeg). 0 si no se sabe."""
    exe = J._ffmpeg()
    if not exe:
        return 0
    try:
        r = subprocess.run([exe, "-hide_banner", "-i", path], capture_output=True, stdin=subprocess.DEVNULL, timeout=60,
                           creationflags=0x08000000 if J.IS_WIN else 0)
    except (OSError, subprocess.SubprocessError):
        return 0
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", (r.stderr or b"").decode("utf-8", "replace"))
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0


def a67_transcribe(it):
    """Transcripción literal (con repeticiones y errores). Gemini con la instrucción de lectura; si no, la transcripción normal."""
    import base64
    import tempfile
    cfg = None if J.is_offline() else J._gemini_for_stt()
    if cfg:
        tmp = tempfile.mkdtemp(prefix="jarvis_fl_")
        try:
            out = []
            for p in J.media_chunks(it["ruta"], tmp):
                with open(p, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                body = {"contents": [{"role": "user", "parts": [{"inline_data": {"mime_type": "audio/mp3", "data": b64}},
                                                               {"text": C.VERBATIM_PROMPT}]}],
                        "generationConfig": {"maxOutputTokens": 8192, "temperature": 0}}
                txt = (J._with_fallback(cfg, lambda c: J._gemini_text(J._post(f"{J.GEMINI_BASE}/models/{c['model']}:generateContent",
                                                                             J._gemini_headers(c), body, (), timeout=240))) or "").strip()
                if txt.lower().strip(" .") != "(nada)":
                    out.append(txt)
            return " ".join(out).strip()
        except J.AIError:
            pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return J.transcribe_media(it)[0]


def _a67_find_student(name, curso=""):
    """→ (nombre de la lista, curso). Busca en el curso dicho o en todos."""
    courses = [curso] if curso else list(aula.data.get("cursos", {}))
    for c in courses:
        hit = vocacional.match_student(name, aula.students(c)) if aula.students(c) else ""
        if hit:
            return hit, c
    return re.sub(r"\s+", " ", name).strip().title()[:60], curso


def evaluate_reading(audio, ref_text, student, curso=""):
    """→ (texto para decir, registro guardado)"""
    secs = J.a67_duration(audio["ruta"])
    if not secs:
        raise ValueError("no pude saber cuánto dura el audio")
    said = J.a67_transcribe(audio)
    if not said.strip():
        raise ValueError("no se oye la lectura en ese audio")
    grade = aula.grade_of(curso) if curso else None
    r = C.fluency(ref_text, said, secs, grade)
    rec = {"fecha": str(datetime.date.today()), "ppm": r["ppm"], "pcm": r["pcm"], "precision": r["precision"], "nivel": r["nivel"],
           "palabras": r["total"]}
    d = a67_data()
    d["fluidez"].setdefault(curso or "Sin curso", {}).setdefault(student, []).append(rec)
    a67_save(d)
    prev = d["fluidez"][curso or "Sin curso"][student][:-1]
    txt = C.fluency_text(student, r)
    if prev:
        diff = r["ppm"] - prev[0]["ppm"]
        txt += (f" Desde la primera medición ({prev[0]['fecha']}) {'subió' if diff >= 0 else 'bajó'} {abs(diff)} palabras por minuto.")
    return txt, rec


_A67_READ = re.compile(r"^(?:jarvis\s+)?(?:evalua|evaluame|mide|mideme|revisa|revisame|califica|analiza|analizame)\s+(?:la\s+)?"
                       r"(?:lectura|fluidez(?: lectora)?|velocidad lectora|velocidad de lectura)\s+(?:de|del estudiante|de la estudiante|de el)\s+"
                       r"(.+?)(?:\s+con (?:este|el) texto\b.*)?$")
_A67_READ_COURSE = re.compile(rf"^(.+?)\s+(?:de|del|en)\s+({_A67_COURSE})$")
_A67_FL_REPORT = re.compile(r"^(?:jarvis\s+)?(?:como va|como van|como esta|como estan|informe de|reporte de|seguimiento de)\s+(?:la\s+)?"
                            r"(?:fluidez(?: lectora)?|lectura|velocidad lectora)\s+(?:de|del|en|de los de)\s+(.+)$")


def _a67_ref_text(text, skip_id=None):
    m = re.search(r"(?is)\bcon (?:este|el) texto\s*[:,]?\s*(.+)$", text or "")
    if m and len(m.group(1).split()) >= 8:
        return m.group(1).strip()
    it = _a67_recent(("texto", "pdf", "word", "imagen"), skip_id)
    return (J._text_of_item(it) or "") if it else ""


def _a67_reading_start(audio, ref, student, curso):
    def work():
        try:
            txt, _rec = J.evaluate_reading(audio, ref, student, curso)
        except (ValueError, J.AIError) as e:
            J.notify(J.ai_error_reply(e) if isinstance(e, J.AIError) else f"No pude evaluar la lectura: {e}.", "LECTURA")
            return
        J.notify(txt, "LECTURA")
    J.start_job("Evaluando la lectura", work, "lectura")


def _a67_read_voice(text, t):
    m = _A67_READ.match(t)
    if m:
        who = m.group(1).strip()
        mc = _A67_READ_COURSE.match(who)
        spoken_course = mc.group(2) if mc else ""
        if mc:
            who = mc.group(1)
        curso = _a67_course(spoken_course) or ""
        audio = _a67_recent(("audio", "video"))
        if not audio:
            J.reply("Súbeme el audio del estudiante leyendo (lo grabas con el celular) y vuelve a pedírmelo. Yo no grabo: solo "
                    "analizo el audio que me subes.", "LECTURA")
            return True
        ref = _a67_ref_text(text, audio["id"])
        if len(ref.split()) < 8:
            J.reply("Me falta el texto que leyó: dímelo así «… con este texto: …» o súbelo (Word, PDF o foto).", "LECTURA")
            return True
        student, curso = _a67_find_student(who, curso)
        J.reply(f"Escucho la lectura de {student} y la comparo con el texto…", "LECTURA")
        _a67_reading_start(audio, ref, student, curso)
        return True
    m = _A67_FL_REPORT.match(t)
    if m:
        J.reply(J.fluency_report(m.group(1).strip()), "LECTURA")
        return True
    return False


def fluency_report(spoken):
    d = a67_data()["fluidez"]
    curso = _a67_course(spoken)
    if not curso or curso not in d:
        for c, studs in d.items():                                   # ¿es un estudiante?
            for s, lst in studs.items():
                if vocacional.match_student(spoken, [s]):
                    first, last = lst[0], lst[-1]
                    return (f"{s} ({c}): {len(lst)} medición{'es' if len(lst) != 1 else ''}; la última, {last['ppm']} palabras por minuto"
                            + (f" ({last['nivel']})" if last["nivel"] else "") +
                            (f"; empezó en {first['ppm']} el {first['fecha']}" if len(lst) > 1 else "") + ".")
        return "Aún no tengo lecturas evaluadas de ese curso o estudiante. Sube el audio y di «evalúa la lectura de … de 3A»."
    studs = d[curso]
    rows = sorted(studs.items(), key=lambda kv: kv[1][-1]["ppm"])
    low = [s for s, lst in rows if lst[-1]["nivel"] in ("requiere apoyo", "se acerca al estándar")]
    ups = [lst[-1]["ppm"] - lst[0]["ppm"] for _s, lst in rows if len(lst) > 1]
    doc = J.Document()
    _a67_doc_header(doc, f"Fluidez lectora · {curso} · {datetime.date.today():%d/%m/%Y}", False)
    tb = doc.add_table(rows=1, cols=5)
    tb.style = "Table Grid"
    for i, h in enumerate(("Estudiante", "Mediciones (PPM)", "Última PPM", "Precisión", "Nivel")):
        tb.cell(0, i).text = h
    for s, lst in sorted(studs.items()):
        c = tb.add_row().cells
        c[0].text, c[1].text = s, " → ".join(str(x["ppm"]) for x in lst)
        c[2].text, c[3].text, c[4].text = str(lst[-1]["ppm"]), f"{lst[-1]['precision']} %", lst[-1]["nivel"] or "-"
    doc.add_paragraph()
    doc.add_paragraph("PPM: palabras leídas por minuto. Referencia: tabla de niveles de la SEP por grado; el MEN (Todos a Aprender) "
                      "solo publica cortes para 3° (óptimo 85-89) y 5° (115-124).")
    path = os.path.join(_a67_folder("Fluidez lectora"), _a67_safe(f"Fluidez {curso} {datetime.date.today():%Y-%m-%d}") + ".docx")
    doc.save(path)
    J.generated_files.add(path)
    avg = round(sum(lst[-1]["ppm"] for _s, lst in rows) / len(rows))
    txt = f"{curso}: {len(rows)} estudiante{'s' if len(rows) != 1 else ''} evaluado{'s' if len(rows) != 1 else ''}, promedio {avg} palabras por minuto."
    if ups:
        txt += f" Los que tienen más de una medición subieron en promedio {round(sum(ups) / len(ups))}."
    if low:
        txt += f" Necesitan apoyo: {', '.join(low[:6])}."
    return txt + " Te dejé la tabla en Documentos, Jarvis, Fluidez lectora."


# ============================================================================ 4. CARTA DE RECOMENDACIÓN
def _a67_firma():
    return os.path.join(J.CONFIG_DIR, "firma.png")


def a67_student_facts(student, curso):
    """Lo que Jarvis sabe del estudiante: promedio y mejores notas por asignatura, fallas y lectura."""
    lines = []
    base = str(curso).split(" · ")[0] if curso else ""
    for c, studs in seguimiento.data.items():
        if base and not (c == curso or c.split(" · ")[0] == base):
            continue
        for e, lst in studs.items():
            if lst and (e == student or vocacional.match_student(student, [e])):
                best = sorted(lst, key=lambda x: -x["nota"])[:3]
                lines.append(f"- {c}: valoración {str(seguimiento.average(c, e)).replace('.', ',')} con {len(lst)} notas; mejores: "
                             + ", ".join(f"{x['actividad']} ({str(x['nota']).replace('.', ',')})" for x in best))
    try:
        faltas = J._absences(base).get(student, 0) if base else 0
        lines.append(f"- Fallas registradas: {faltas}")
    except Exception:
        pass
    for c, studs in a67_data()["fluidez"].items():
        if student in studs:
            lines.append(f"- Lectura en voz alta: {studs[student][-1]['ppm']} palabras por minuto ({studs[student][-1]['nivel'] or 'sin nivel'})")
    return "\n".join(lines)


def make_letter(student, curso, proposito, extra=""):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm
    docente = J.settings.get("aula_docente", "")
    inst = J.settings.get("aula_institucion", "")
    body = J.ai_chat([{"role": "user", "content": C.letter_prompt(student, curso, proposito, J.a67_student_facts(student, curso),
                                                                  extra, docente, inst)}], max_tokens=1600)
    doc = J.Document()
    if inst:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run(inst).bold = True
    city = J.settings.get("weather_city", "") or "Santiago de Cali"
    doc.add_paragraph(f"{city}, {_a67_long_date(datetime.date.today())}")
    doc.add_paragraph()
    doc.add_paragraph(f"Señores\n{proposito}" if proposito else "A quien pueda interesar")
    doc.add_paragraph()
    doc.add_paragraph(f"Asunto: carta de recomendación de {student}").runs[0].bold = True
    doc.add_paragraph("Respetados señores:" if proposito else "Cordial saludo:")
    for line in str(body).splitlines():
        if line.strip():
            q = doc.add_paragraph(line.strip().strip("*#"))
            q.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    doc.add_paragraph("Atentamente,")
    if os.path.exists(_a67_firma()):
        doc.add_picture(_a67_firma(), width=Cm(5))
    else:
        doc.add_paragraph("\n")
    doc.add_paragraph("_______________________________")
    doc.add_paragraph(docente or "[Nombre del docente]").runs[0].bold = True
    doc.add_paragraph("Docente" + (f" · {inst}" if inst else ""))
    path = os.path.join(_a67_folder("Cartas"), _a67_safe(f"Carta de recomendación - {student} {datetime.date.today():%Y-%m-%d}") + ".docx")
    doc.save(path)
    return path


_A67_LETTER = re.compile(r"^(?:jarvis\s+)?(?:haz|hazme|escribe|escribeme|redacta|redactame|prepara|preparame)\s+(?:una\s+|la\s+)?"
                         r"carta de recomendacion\s+(?:para|de|a)\s+(.+?)(?:\s+(?:para|con destino a|dirigida a|ante)\s+(.+?))?"
                         r"(?:\s+(?:y\s+)?(?:destaca|resalta|menciona|di|cuenta)\s+que\s+(.+))?$")
_A67_SIGN = re.compile(r"^(?:jarvis\s+)?(?:guarda|usa|pon|toma)\s+(?:esta|la)\s+(?:imagen|foto)\s+(?:como|de)\s+(?:mi\s+)?firma$|"
                       r"^(?:jarvis\s+)?(?:esta|esa) es mi firma$")


def _a67_letter_voice(text, t):
    if _A67_SIGN.match(t):
        it = _a67_recent(("imagen",))
        if not it:
            J.reply("Sube primero la foto de tu firma (en papel blanco, bien recortada) y repite «guarda esta imagen como mi firma».", "CARTAS")
            return True
        os.makedirs(J.CONFIG_DIR, exist_ok=True)
        try:
            from PIL import Image
            Image.open(it["ruta"]).convert("RGB").save(_a67_firma(), "PNG")
        except Exception:
            J.reply("No pude leer esa imagen.", "CARTAS")
            return True
        J.reply("Guardé tu firma: va en las cartas que te prepare.", "CARTAS")
        return True
    m = _A67_LETTER.match(t)
    if not m:
        return False
    who = m.group(1).strip()
    mc = _A67_READ_COURSE.match(who)
    curso = _a67_course(mc.group(2)) if mc else ""
    student, curso = _a67_find_student(mc.group(1) if mc else who, curso or "")
    proposito = ""
    if m.group(2):
        raw = re.split(r"(?i)\s+(?:para|con destino a|dirigida a|ante)\s+", re.sub(r"(?i)\s+(?:y\s+)?(?:destaca|resalta|menciona|di|cuenta)\s+que\s+.*$", "", text))
        proposito = raw[-1].strip(" ,.") if len(raw) > 2 else m.group(2)
    ex = re.search(r"(?is)\b(?:destaca|resalta|menciona|di|cuenta)\s+que\s+(.+)$", text)
    extra = ex.group(1).strip() if ex else ""
    if J.state.get("ai") != "ok":
        J.reply("Para redactar la carta necesito la IA conectada.", "CARTAS")
        return True
    J.reply(f"Redacto la carta de recomendación de {student}" + (f" ({curso})" if curso else "") + " con lo que tengo registrado…", "CARTAS")

    def work():
        try:
            path = J.make_letter(student, curso, proposito, extra)
        except J.AIError as e:
            J.notify(J.ai_error_reply(e), "CARTAS")
            return
        J.generated_files.add(path)
        J.notify("Lista la carta en Word, en Documentos, Jarvis, Cartas. Revisa lo que quedó [entre corchetes]" +
                 ("." if os.path.exists(_a67_firma()) else " y fírmala (o sube la foto de tu firma y di «guarda esta imagen como mi firma»)."),
                 "CARTAS")
        if J.settings.get("aula_open_docs", True):
            J._open_doc(path)
    J.start_job("Redactando la carta", work, "carta")
    return True


# ============================================================================ 5. PICO Y PLACA
def _a67_holidays(day):
    try:
        return set(festivos.holidays(day.year))
    except Exception:
        return set()


def a67_pyp_table(sem, d=None):
    d = d or a67_data()
    return (d["pyp"].get("tablas") or {}).get(f"{sem[0]}-{sem[1]}")


def a67_pyp_check(day, d=None):
    """→ (aplica, par, confirmado) para la placa guardada."""
    d = d or a67_data()
    digit = C.plate_digit(d["pyp"].get("placa", ""))
    if digit is None:
        return False, None, True
    tb = a67_pyp_table(C.semester(day), d)
    return C.restricted(day, digit, _a67_holidays(day), {k: v for k, v in tb.items() if k.isdigit()} if tb else None)


def a67_pyp_verify(sem):
    """Busca la rotación oficial del semestre y la guarda si la IA la saca clara. → True si quedó verificada."""
    y, s = sem
    try:
        res = J._web_results(f"pico y placa Cali {'primer' if s == 1 else 'segundo'} semestre {y} rotación Secretaría de Movilidad")
    except Exception:
        res = []
    if not res:
        return False
    snip = "\n".join(f"[{r.get('fuente', '')} {r.get('url', '')}] {r.get('titulo', '')}. {r.get('resumen', '')}" for r in res[:8])
    try:
        raw = J.ai_chat([{"role": "user", "content": C.verify_prompt(sem, snip)}], json_mode=True, max_tokens=400)
        js = J._extract_json(raw)
    except Exception:
        return False
    tb = C.parse_table(js)
    if not tb:
        return False
    d = a67_data()
    tb["fuente"] = str(js.get("fuente", ""))[:160]
    d["pyp"].setdefault("tablas", {})[f"{y}-{s}"] = tb
    a67_save(d)
    return True


def _a67_day_from(t):
    today = datetime.date.today()
    if re.search(r"\bpasado manana\b", t):
        return today + datetime.timedelta(days=2)
    if re.search(r"\bmanana\b", t):
        return today + datetime.timedelta(days=1)
    for i, name in enumerate(("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")):
        if re.search(rf"\b{name}\b", t):
            return today + datetime.timedelta(days=(i - today.weekday()) % 7)
    return today


_A67_PLATE = re.compile(r"^(?:jarvis\s+)?(?:mi placa es|la placa de mi (?:carro|moto|vehiculo) es|mi (?:carro|moto|vehiculo) es (?:de )?(?:placa|placas)|"
                        r"mi (?:carro|moto|vehiculo) tiene (?:la )?placa|anota mi placa|guarda mi placa|mi placa)\s*:?\s*([a-z]{3}\s*-?\s*\d{2}\s*[a-z0-9])$")
_A67_PYP_ASK = re.compile(r"^(?:jarvis\s+)?(?:(?:tengo|hay|me toca|aplica|tiene mi carro)\s+pico y placa\b|que placas tienen pico y placa\b|"
                          r"pico y placa (?:de |para )?(?:hoy|manana|pasado manana|el (?:lunes|martes|miercoles|jueves|viernes))$|"
                          r"(?:puedo|me deja) (?:sacar|usar|mover) el carro\b)")
_A67_PYP_WHEN = re.compile(r"^(?:jarvis\s+)?(?:cuando|que dia|que dias)\s+(?:tengo|me toca|hay|es mi)\s+(?:el\s+)?pico y placa$|"
                           r"^(?:jarvis\s+)?(?:como (?:esta|va|quedo)|cual es)\s+(?:el|la rotacion del)\s+pico y placa(?: en cali)?(?: este semestre)?$")
_A67_PYP_EXEMPT = re.compile(r"^(?:jarvis\s+)?(?:ya\s+)?(?:pague|tengo|saque)\s+(?:la\s+)?(?:tasa por congestion|excepcion del pico y placa)$")
_A67_PYP_OFF = re.compile(r"^(?:jarvis\s+)?(?:no me avises|deja de avisarme|ya no me avises)\s+(?:del|el|de)\s+pico y placa$|"
                          r"^(?:jarvis\s+)?(?:borra|olvida|quita)\s+mi placa$|^(?:jarvis\s+)?ya no tengo carro$")
_A67_PYP_ON = re.compile(r"^(?:jarvis\s+)?(?:avisame|vuelve a avisarme)\s+(?:del|el)\s+pico y placa$")


def _a67_pair(p):
    return f"{p[0]} y {p[1]}"


def _a67_pyp_voice(text, t):
    m = _A67_PLATE.match(t)
    if m:
        plate = re.sub(r"[\s-]", "", m.group(1)).upper()
        if C.is_moto(plate):
            J.reply("Esa es placa de moto, y en Cali las motos no tienen pico y placa: no te aviso nada.", "PICO Y PLACA")
            return True
        digit = C.plate_digit(plate)
        if digit is None:
            J.reply("No entendí la placa; dímela así: «mi placa es ABC123».", "PICO Y PLACA")
            return True
        d = a67_data()
        d["pyp"].update(placa=plate, off=False)
        a67_save(d)
        rot, ok = C.rotation(C.semester(datetime.date.today()), a67_pyp_table(C.semester(datetime.date.today()), d))
        day = [C.DAYS[k] for k, p in rot.items() if digit in p]
        J.reply(f"Anotada la placa {plate} (termina en {digit}). Este semestre te toca pico y placa los {day[0]}, {C.HOURS}"
                + ("" if ok else " (rotación estimada; la confirmo en internet)") + ". Te aviso en la mañana de esos días, menos en festivos.",
                "PICO Y PLACA")
        return True
    if _A67_PYP_OFF.match(t):
        d = a67_data()
        if re.search(r"borra|olvida|quita|ya no tengo", t):
            d["pyp"].pop("placa", None)
        d["pyp"]["off"] = True
        a67_save(d)
        J.reply("Listo, ya no te aviso del pico y placa.", "PICO Y PLACA")
        return True
    if _A67_PYP_ON.match(t):
        d = a67_data()
        d["pyp"].update(off=False, exento=False)
        a67_save(d)
        J.reply("Listo, te vuelvo a avisar del pico y placa." if d["pyp"].get("placa") else "Dime primero tu placa: «mi placa es ABC123».",
                "PICO Y PLACA")
        return True
    if _A67_PYP_EXEMPT.match(t):
        d = a67_data()
        d["pyp"].update(exento=True, off=True)
        a67_save(d)
        J.reply("Anotado: con la tasa por congestión pagada puedes circular. No te aviso más hasta que me digas «avísame del pico y placa».",
                "PICO Y PLACA")
        return True
    ask, when = _A67_PYP_ASK.match(t), _A67_PYP_WHEN.match(t)
    if not (ask or when):
        return False
    d = a67_data()
    day = _a67_day_from(t)
    rot, ok = C.rotation(C.semester(day), a67_pyp_table(C.semester(day), d))
    note = "" if ok else " Ojo: es la rotación estimada; aún no encontré la oficial de este semestre (cali.gov.co)."
    digit = C.plate_digit(d["pyp"].get("placa", ""))
    if when:
        mine = ("; la tuya (termina en " + str(digit) + ") los " + [C.DAYS[k] for k, p in rot.items() if digit in p][0]) if digit is not None else ""
        J.reply("Pico y placa en Cali este semestre, " + C.HOURS + ": " + ", ".join(f"{C.DAYS[k]} {_a67_pair(p)}" for k, p in rot.items())
                + mine + ". No aplica fines de semana ni festivos; las motos no tienen." + note, "PICO Y PLACA")
        return True
    label = "hoy" if day == datetime.date.today() else "mañana" if day == datetime.date.today() + datetime.timedelta(days=1) else f"el {C.DAYS[day.weekday()] if day.weekday() < 5 else 'fin de semana'}"
    if day.weekday() > 4 or day in _a67_holidays(day):
        J.reply(f"{label.capitalize()} no hay pico y placa en Cali ({'es fin de semana' if day.weekday() > 4 else 'es festivo'}).", "PICO Y PLACA")
        return True
    pair = rot[day.weekday()]
    if digit is None:
        J.reply(f"{label.capitalize()} tienen pico y placa en Cali las placas terminadas en {_a67_pair(pair)}, {C.HOURS}. "
                "Si me dices tu placa («mi placa es ABC123»), te aviso en la mañana." + note, "PICO Y PLACA")
        return True
    if d["pyp"].get("exento"):
        J.reply(f"{label.capitalize()} es para placas {_a67_pair(pair)}, pero me dijiste que pagaste la tasa por congestión.", "PICO Y PLACA")
        return True
    J.reply((f"Sí: {label} tienes pico y placa (tu placa termina en {digit}), {C.HOURS}." if digit in pair else
             f"No, {label} puedes sacar el carro: el pico y placa es para las placas {_a67_pair(pair)}.") + note, "PICO Y PLACA")
    return True


def aula67_tick(now=None):
    """En la mañana de los días que aplica, un aviso. La rotación del semestre se verifica en internet (una vez al día si falta)."""
    now = now or datetime.datetime.now()
    d = a67_data()
    p = d["pyp"]
    if not p.get("placa") or C.plate_digit(p["placa"]) is None:
        return
    today = now.date()
    sem = C.semester(today)
    nxt = (today.year + 1, 1) if sem[1] == 2 else (today.year, 2)
    pend = [s for s in ([sem] + ([nxt] if (today.month, today.day) >= ((12, 15) if sem[1] == 2 else (6, 15)) else []))
            if not a67_pyp_table(s, d) and s not in C.KNOWN]
    if pend and p.get("verif") != str(today) and not J.is_offline():
        p["verif"] = str(today)
        a67_save(d)
        threading.Thread(target=lambda: [J.a67_pyp_verify(s) for s in pend], daemon=True).start()
    if p.get("off") or p.get("avisado") == str(today) or not (5 <= now.hour < 11):
        return
    hit, pair, ok = a67_pyp_check(today, d)
    if not hit:
        return
    p["avisado"] = str(today)
    a67_save(d)
    J.notify(f"Hoy tienes pico y placa: tu placa termina en {C.plate_digit(p['placa'])} y hoy es para {_a67_pair(pair)}, {C.HOURS}."
             + ("" if ok else " (Rotación estimada: confírmala en cali.gov.co.)"), "PICO Y PLACA")


# ============================================================================ archivos y enrutador
def a67_card_actions(its):
    if len(its) != 1:
        return []
    k = its[0]["tipo"]
    acts = []
    if k == "audio":
        acts.append("fluidez")
    if k in ("pdf", "word", "texto", "powerpoint"):
        acts.append("mapa67")
    return [{"a": a, "t": A67_ACTIONS[a]} for a in acts]


def a67_attach(its, action, pregunta=""):
    it = its[0]
    if action == "mapa67":
        if J.state.get("ai") != "ok":
            J.notify("Para armar el mapa necesito la IA conectada.", "MAPAS")
            return None
        J.notify(f"Dibujo el mapa conceptual de «{it['nombre']}»…", "MAPAS")
        _a67_map_start(it["nombre"].rsplit(".", 1)[0], "conceptual", "", (J._text_of_item(it) or "")[:12000])
    elif action == "fluidez":
        ref = pregunta if len((pregunta or "").split()) >= 8 else _a67_ref_text("", it["id"])
        if len(ref.split()) < 8:
            J.notify("Para evaluar la lectura necesito también el texto que leyó: súbelo (Word, PDF o foto) o di «evalúa la lectura "
                     "de Juan Pérez de 3A con este texto: …».", "LECTURA")
            return None
        student, curso = _a67_find_student(re.sub(r"[_-]+", " ", it["nombre"].rsplit(".", 1)[0]))
        J.notify(f"Evalúo la lectura de {student}…", "LECTURA")
        _a67_reading_start(it, ref, student, curso)
    return None


def aula67_voice(text, t):
    for fn in (_a67_games_voice, _a67_map_voice, _a67_read_voice, _a67_letter_voice, _a67_pyp_voice):
        if fn(text, t):
            return True
    return False


__all__ = ['A67_ACTIONS', '_A67_COURSE', '_A67_FL_REPORT', '_A67_FROM_DOC', '_A67_GAME', '_A67_LETTER', '_A67_MAP', '_A67_MESES',
           '_A67_PLATE', '_A67_PYP_ASK', '_A67_PYP_EXEMPT', '_A67_PYP_OFF', '_A67_PYP_ON', '_A67_PYP_WHEN', '_A67_READ',
           '_A67_READ_COURSE', '_A67_SIGN', '_a67_cell', '_a67_course', '_a67_day_from', '_a67_doc_header', '_a67_find_student',
           '_a67_firma', '_a67_folder', '_a67_games_voice', '_a67_grid_table', '_a67_holidays', '_a67_letter_voice', '_a67_lock',
           '_a67_long_date', '_a67_map_start', '_a67_map_voice', '_a67_pair', '_a67_path', '_a67_pyp_voice', '_a67_read_voice',
           '_a67_reading_start', '_a67_recent', '_a67_ref_text', '_a67_safe', '_a67_shade', '_a67_source', 'a67_attach',
           'a67_card_actions', 'a67_data', 'a67_duration', 'a67_pyp_check', 'a67_pyp_table', 'a67_pyp_verify', 'a67_save',
           'a67_student_facts', 'a67_transcribe', 'a67_wordsearch_doc', 'a67_crossword_doc', 'a67_matching_doc', 'aula67_tick',
           'aula67_voice', 'evaluate_reading', 'fluency_report', 'make_games', 'make_letter', 'make_map']
