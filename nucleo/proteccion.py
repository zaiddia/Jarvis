"""8.9: datos de estudiantes cifrados (con clave de recuperación) y copia de seguridad automática en tu Google Drive.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import os
import re
import threading

import aula
import classroom
import datos
import diarioclase
import gservicios
import informes
import examenes
import periodos
import practica
import saber
import seguimiento
from nucleo import J

STUDENT_FILES = {"aula.json": aula, "notas_estudiantes.json": seguimiento, "observador.json": informes,
                 "registro_clase.json": diarioclase, "periodos.json": periodos, "examenes.json": examenes, "saber.json": saber, "practica.json": practica}


# ============================================================================ DATOS DE ESTUDIANTES CIFRADOS
datos.configure(lambda: J.settings.get("data_key", ""), lambda: bool(J.settings.get("protect_students")))


def students_locked():
    return [f for f, m in STUDENT_FILES.items() if getattr(m, "locked", False)]


def _resave_all():
    for m in STUDENT_FILES.values():
        if not getattr(m, "locked", False) and getattr(m, "_path", None):
            m.save()


def protect_students(on):
    """Activa o desactiva el cifrado y reescribe los archivos. Devuelve un mensaje."""
    if on and not datos.available():
        return {"ok": False, "msg": "Falta la librería «cryptography»: ejecuta instalar.bat (o actualiza Jarvis) y vuelve a intentarlo."}
    if students_locked():
        return {"ok": False, "msg": "Hay datos bloqueados con otra clave: pega primero la clave de recuperación."}
    changes = {"protect_students": bool(on)}
    if on and not J.settings["data_key"]:
        changes["data_key"] = datos.new_key()
    J.apply_settings(changes)
    J.settings.update(changes)
    _resave_all()
    if on:
        return {"ok": True, "msg": "Listo: notas, observador, cursos con asistencia y diario de clase quedaron cifrados. Copia la "
                                   "clave de recuperación y guárdala en un lugar seguro: la necesitas para usar estos datos en "
                                   "otro equipo o restaurar una copia en un equipo nuevo."}
    return {"ok": True, "msg": "Listo: los datos de estudiantes se guardan sin cifrar."}


def unlock_students(key):
    """Pegas la clave de recuperación (de otro equipo o de una copia): se guarda y se abren los datos."""
    key = str(key or "").strip()
    if not datos.valid_key(key):
        return {"ok": False, "msg": "Esa no parece una clave de recuperación (son 44 caracteres)."}
    J.apply_settings({"data_key": key, "protect_students": True})
    J.settings.update(data_key=key, protect_students=True)
    for m in STUDENT_FILES.values():
        if getattr(m, "_path", None):
            m.load()
    left = students_locked()
    if left:
        return {"ok": False, "msg": "La clave se guardó, pero estos archivos siguen sin abrir (son de otra clave): " + ", ".join(left)}
    return {"ok": True, "msg": "Listo: los datos de estudiantes se abrieron con esa clave."}


@J.socketio.on("students_protect")
def handle_students_protect(data=None):
    d = data or {}
    if "key" in d:
        return {**unlock_students(d["key"]), **students_info()}
    return {**protect_students(bool(d.get("on"))), **students_info()}


@J.socketio.on("students_info")
def handle_students_info(data=None):
    out = students_info()
    if (data or {}).get("reveal") and J.settings["data_key"]:
        out["key"] = J.settings["data_key"]                 # solo se muestra en Ajustes, en tu equipo, al pedirla
    return out


def students_info():
    return {"available": datos.available(), "on": bool(J.settings["protect_students"]), "has_key": bool(J.settings["data_key"]),
            "locked": students_locked(),
            "files": {f: datos.file_state(os.path.join(J.CONFIG_DIR, f)) for f in STUDENT_FILES}}


# ============================================================================ COPIA DE SEGURIDAD EN DRIVE
def backup_to_drive(path):
    """Sube la copia (.zip) a «Jarvis/Respaldos» de tu Drive y deja solo las últimas. Devuelve el nombre o lanza error."""
    client = J.classroom_client()
    root = gservicios.ensure_folder(client, J.settings["drive_folder_id"])
    sub = gservicios.ensure_subfolder(client, root, "Respaldos", J.settings["drive_backup_folder_id"])
    if root != J.settings["drive_folder_id"] or sub != J.settings["drive_backup_folder_id"]:
        J.apply_settings({"drive_folder_id": root, "drive_backup_folder_id": sub})
    f = gservicios.upload(client, path, sub)
    keep = J.settings["drive_backup_keep"]
    for old in [x for x in gservicios.list_folder(client, sub) if x["name"].endswith(".zip")][keep:]:
        try:
            gservicios.delete(client, old["id"])
        except classroom.ClassroomError:
            pass
    return f.get("name", os.path.basename(path))


def after_backup(res):
    """Llamado tras cada copia local: si está activado y Google está conectado, también va a tu Drive."""
    if not (J.settings["backup_drive"] and J.gdrive_ready()):
        return

    def work():
        try:
            name = backup_to_drive(res["path"])
            J.log_terminal(f"Copia de seguridad también en tu Drive: {name}", "RESPALDO")
        except (classroom.ClassroomError, OSError) as e:
            J.note_error("RESPALDO", e)
            J.log_terminal(f"No pude subir la copia a Drive: {e}", "AVISO")
    J.start_job("Subiendo la copia a Drive", work, "respaldo-drive")


_BK_RE = re.compile(r"\b(?:haz|hazme|crea|guarda|sube)\b.*\b(?:copia|respaldo|backup)\b.*\bdrive\b|\b(?:respalda|respaldame)\b.*\bdrive\b")


def backup_drive_voice(text, t):
    if not _BK_RE.search(t):
        return False
    if not J.gdrive_ready():
        J.reply("Para guardar copias en tu Drive pulsa «Conectar con Google» en Ajustes › Memoria › Cuenta de Google.", "RESPALDO")
        return True
    res = J.make_backup("manual")
    try:
        name = backup_to_drive(res["path"])
    except (classroom.ClassroomError, OSError) as e:
        J.reply(f"Hice la copia en tu equipo, pero no pude subirla a Drive: {e}", "RESPALDO")
        return True
    J.reply(f"Listo: copia de seguridad en tu equipo y en tu Drive (Jarvis › Respaldos › {name})." +
            (" Los datos de estudiantes van cifrados." if J.settings["protect_students"] else ""), "RESPALDO")
    return True


def students_start():
    """Tras leer los ajustes (con la clave): abre lo que se cargó antes de tenerla."""
    for m in STUDENT_FILES.values():
        if getattr(m, "locked", False) and getattr(m, "_path", None):
            m.load()
    left = students_locked()
    if left:
        J.log_terminal("Hay datos de estudiantes cifrados con otra clave (" + ", ".join(left) + "): pega la clave de "
                       "recuperación en Ajustes › Memoria para abrirlos.", "AVISO")


__all__ = ['STUDENT_FILES', '_BK_RE', '_resave_all', 'after_backup', 'backup_drive_voice', 'backup_to_drive',
           'handle_students_info', 'handle_students_protect', 'protect_students', 'students_info', 'students_locked', 'students_start',
           'unlock_students']
