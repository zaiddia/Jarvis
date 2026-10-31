"""8.7: Google Calendar y Google Drive con tu cuenta de Google, y exportaciones a Kahoot, Quizizz y Zeti.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import os
import re
import threading
import time
import webbrowser

import aula
import calendario
import classroom
import exportar
import gservicios
import seguimiento
from nucleo import J


# ============================================================================ GOOGLE CALENDAR
def gcal_ready():
    return bool(J.classroom_client()) and gservicios.has(J.settings["google_scopes"], gservicios.SCOPES[0])


def cal_configured():
    return bool(J._cal_urls()) or J.gcal_ready()


_gcal = {"t": 0.0, "events": [], "error": ""}


def gcal_merge(force=False):
    """Mezcla los eventos de tu Google Calendar con los del enlace .ics (cada 10 minutos)."""
    if not J.gcal_ready():
        return
    if force or time.time() - _gcal["t"] > 600:
        _gcal["t"] = time.time()
        try:
            _gcal.update(events=gservicios.list_events(J.classroom_client()), error="")
        except classroom.ClassroomError as e:
            if _gcal["error"] != str(e):
                J.log_terminal(f"Google Calendar: {e}", "AVISO")
            _gcal["error"] = str(e)
    have = {(e["titulo"], e["inicio"][:16]) for e in calendario.cache["events"] if e.get("cal") != "google"}
    evs = [e for e in calendario.cache["events"] if e.get("cal") != "google"]
    evs += [e for e in _gcal["events"] if (e["titulo"], e["inicio"][:16]) not in have]
    evs.sort(key=lambda x: (x["inicio"][:10], not x["todo_el_dia"], x["inicio"]))
    calendario.cache.update(events=evs, fetched=time.time())


def event_create_google(ev):
    """Crea el evento en tu Google Calendar. True si lo logró (si no, se usa el método de siempre)."""
    try:
        created = gservicios.create_event(J.classroom_client(), ev, meet=bool(ev.get("meet")))
    except classroom.ClassroomError as e:
        J.log_terminal(f"Google Calendar: {e}. Uso el método de siempre.", "AVISO")
        return False
    link = gservicios.meet_link(created)
    _gcal["t"] = 0.0
    J.reply("Listo, quedó en tu Google Calendar" + (f", con enlace de Meet: {link}" if link else "") + ".", "CALENDARIO")
    J.diario.log("orden", f"agendé {ev['titulo']} ({ev['fecha']} {ev['hora']})")
    return True


# ============================================================================ GOOGLE DRIVE
def gdrive_ready():
    return bool(J.classroom_client()) and gservicios.has(J.settings["google_scopes"], gservicios.SCOPES[1])


def drive_upload(path, convert=False):
    """Sube un archivo de Jarvis a la carpeta «Jarvis» de tu Drive. Devuelve el archivo de Drive."""
    client = J.classroom_client()
    folder = gservicios.ensure_folder(client, J.settings["drive_folder_id"])
    if folder != J.settings["drive_folder_id"]:
        J.apply_settings({"drive_folder_id": folder})
    return gservicios.upload(client, path, folder, convert)


def _last_file(exts=None):
    for p in reversed(list(getattr(J.generated_files, "order", ()))):
        if os.path.exists(p) and (not exts or os.path.splitext(p)[1].lower() in exts):
            return p
    return ""


def on_new_file(path):
    """Si activaste «Subir a Drive automáticamente», cada material nuevo va a tu Drive."""
    if not (J.settings["drive_auto"] and J.gdrive_ready()):
        return
    if os.path.splitext(path)[1].lower() not in (".docx", ".pptx", ".xlsx", ".pdf", ".png", ".jpg"):
        return

    def work():
        try:
            J.drive_upload(path)
            J.log_terminal(f"Subido a tu Drive: {os.path.basename(path)}", "DRIVE")
        except (classroom.ClassroomError, OSError) as e:
            J.note_error("DRIVE", e)
    threading.Thread(target=work, daemon=True, name="drive").start()


_DRIVE_RE = re.compile(r"\b(?:sube|subelo|subela|guarda|guardalo|guardala|pasa|pasalo|pasala|ponlo|ponla|convierte|conviertelo|"
                       r"conviertela|abrelo en|abrela en)\b.*\b(?:drive|google slides|slides|documento de google|google docs|"
                       r"hoja de google|google sheets)\b")
_SHARE_RE = re.compile(r"\b(?:compartelo|compartela|comparte el|dame el enlace|pasame el enlace|enlace para compartir)\b")


def drive_voice(text, t):
    share = _SHARE_RE.search(t)
    if not (_DRIVE_RE.search(t) or (share and "drive" in t)):
        return False
    if not J.gdrive_ready():
        J.reply("Para usar tu Drive pulsa «Conectar con Google» en Ajustes › Memoria › Cuenta de Google (activa la "
                "Google Drive API en tu proyecto de Google Cloud).", "DRIVE")
        return True
    want = (".pptx",) if re.search(r"\b(?:slides|presentacion)\b", t) else \
        (".docx",) if re.search(r"\b(?:documento|docs|word|guia|taller|quiz|informe|plan)\b", t) else \
        (".xlsx",) if re.search(r"\b(?:hoja|sheets|excel|planilla)\b", t) else None
    path = _last_file(want) or _last_file()
    if not path:
        J.reply("Aún no he creado ningún archivo en esta sesión. Pídeme un material y luego «súbelo a Drive».", "DRIVE")
        return True
    convert = bool(re.search(r"\b(?:google slides|slides|documento de google|google docs|hoja de google|google sheets|convierte)\b", t))

    def work():
        try:
            f = J.drive_upload(path, convert)
            link = f.get("webViewLink", "")
            if share:
                def go():
                    try:
                        url = gservicios.share_link(J.classroom_client(), f["id"])
                        J.reply(f"Listo: cualquiera con el enlace puede verlo. {url}", "DRIVE")
                    except classroom.ClassroomError as e:
                        J.reply(f"No pude compartirlo: {e}", "DRIVE")
                J.request_approval("drive", f"Compartir «{os.path.basename(path)}» con enlace público", link, on_ok=go,
                                   on_no=lambda: J.reply("Vale, queda solo en tu Drive.", "DRIVE"),
                                   say="Lo subí a tu Drive. ¿Lo comparto con enlace (cualquiera con el enlace puede verlo)? Di «sí» o «no».")
            else:
                J.notify(f"Listo, «{f.get('name', os.path.basename(path))}» está en la carpeta Jarvis de tu Drive"
                         + (" como archivo de Google" if convert else "") + ". Te lo abrí.", "DRIVE")
            if link:
                webbrowser.open(link)
        except (classroom.ClassroomError, OSError) as e:
            J.notify(f"No pude subirlo a Drive: {e}", "DRIVE")
    if getattr(J._tl, "capture", None) is not None:
        work()
    else:
        threading.Thread(target=work, daemon=True, name="drive").start()
    return True


# ============================================================================ KAHOOT, QUIZIZZ Y ZETI
_GAME_RE = re.compile(r"\b(?:exporta|exportalo|pasa|pasalo|convierte|conviertelo|llevalo|sube|subelo|haz|hazlo)\b.*\b(kahoot|quizizz|"
                      r"quizziz|quizis|wayground)\b")
_ZETI_RE = re.compile(r"\b(?:exporta|exportame|pasa|pasame|prepara|preparame|genera|haz|hazme|saca|sacame)\b.*\b(?:notas|calificaciones|"
                      r"planilla|seguimiento)\b.*\bzeti\b|\bzeti\b.*\b(?:notas|planilla)\b")


def export_voice(text, t):
    m = _GAME_RE.search(t)
    if m:
        quiz = J.last_quiz["m"]
        if not quiz:
            tm = re.search(r"\b(?:de|sobre)\s+(.+?)\s+(?:a|para|en)\s+(?:kahoot|quizizz|quizziz|quizis|wayground)\b", t)
            tema = (tm.group(1) if tm else "").strip()
            quiz = J.banco.build_quiz(tema, aula.detect_count(t) or 10) if tema else None
        if not quiz:
            J.reply("No tengo un quiz reciente. Prepárame uno («haz un quiz de fracciones») y luego «pásalo a Kahoot».", "EXPORTAR")
            return True
        kahoot = m.group(1) == "kahoot"
        path = (exportar.kahoot_xlsx if kahoot else exportar.quizizz_xlsx)(quiz, J.settings["output_dir"])
        J.generated_files.add(path)
        opened = J._open_doc(path)
        where = ("En Kahoot: Crear › Añadir pregunta › Importar hoja de cálculo, y elige este archivo." if kahoot else
                 "En Quizizz (Wayground): Crear › Cuestionario › Importar desde hoja de cálculo, y elige este archivo.")
        J.reply(f"Listo, «{quiz.get('titulo', 'quiz')}» para {'Kahoot' if kahoot else 'Quizizz'} con "
                f"{len(quiz.get('preguntas') or [])} preguntas" + (" (lo abrí)" if opened else "") + f". {where}", "EXPORTAR")
        return True
    if not _ZETI_RE.search(t):
        return False
    cm = re.search(r"\b(?:de|del|para el curso)\s+((?:\d{1,2}\s?[a-z]?|sexto|septimo|octavo|noveno|decimo|once|quinto)(?:\s+[a-z])?)\b", t)
    course = J._resolve_course(cm.group(1) if cm else "")
    if not course:
        J.reply("¿De qué curso? Por ejemplo: «exporta las notas de 7A para Zeti».", "EXPORTAR")
        return True
    names = list(aula.data.get("cursos", {}).get(course, []))
    names += [n for n in seguimiento.data.get(course, {}) if n not in names]
    if not names:
        J.reply(f"No tengo estudiantes ni notas de {course}.", "EXPORTAR")
        return True
    path, n, acts = exportar.zeti_xlsx(course, names, seguimiento.data.get(course, {}), J._absences(course),
                                      J.settings["output_dir"], J.settings["zeti_since"], J.settings["zeti_order"],
                                      J.settings["zeti_comma"], J.settings["aula_institucion"], J.settings["aula_docente"])
    J.generated_files.add(path)
    opened = J._open_doc(path)
    J.reply(f"Listo, la planilla de {course} para Zeti: {n} estudiantes y {acts} actividades, con definitiva, desempeño y "
            "fallas" + (". La abrí" if opened else "") + ". En la hoja «Para copiar» está la columna de definitivas lista para "
            "pegar en Zeti; revisa que el orden de la lista sea el mismo.", "EXPORTAR")
    return True


__all__ = [
    '_DRIVE_RE', '_GAME_RE', '_SHARE_RE', '_ZETI_RE', '_gcal', '_last_file', 'cal_configured', 'drive_upload',
    'drive_voice', 'event_create_google', 'export_voice', 'gcal_merge', 'gcal_ready', 'gdrive_ready',
    'on_new_file',
]
