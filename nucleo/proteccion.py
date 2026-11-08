"""8.9: datos de estudiantes cifrados (con clave de recuperación) y copia de seguridad automática en tu Google Drive.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import os
import re
import threading
import time

import aula
import classroom
import copianube
import datos
import salon
import diarioclase
import dominio
import procedimiento
import gservicios
import informes
import examenes
import periodos
import entregas
import practica
import retos
import saber
import seguimiento
from nucleo import J

STUDENT_FILES = {"aula.json": aula, "notas_estudiantes.json": seguimiento, "observador.json": informes,
                 "registro_clase.json": diarioclase, "periodos.json": periodos, "examenes.json": examenes, "saber.json": saber, "practica.json": practica,
                 "entregas.json": entregas, "retos.json": retos, "tarjetas.json": dominio,
                 "mapa_errores.json": procedimiento, "salon.json": salon}


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
def _drive_backup_folder(client):
    root = gservicios.ensure_folder(client, J.settings["drive_folder_id"])
    sub = gservicios.ensure_subfolder(client, root, "Respaldos", J.settings["drive_backup_folder_id"])
    if root != J.settings["drive_folder_id"] or sub != J.settings["drive_backup_folder_id"]:
        J.apply_settings({"drive_folder_id": root, "drive_backup_folder_id": sub})
    return sub


def _sealed_copy(path):
    """12.8: la copia cifrada con tu clave (y la clave de los datos de estudiantes adentro). → ruta del .jvbk temporal."""
    with open(path, "rb") as f:
        raw = f.read()
    blob = copianube.seal(copianube.with_key(raw, J.settings.get("data_key", "")), J.settings["cloud_pass"])
    tmp_dir = os.path.join(J.CONFIG_DIR, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    out = os.path.join(tmp_dir, copianube.cloud_name(path))
    with open(out, "wb") as f:
        f.write(blob)
    return out


def backup_to_drive(path):
    """Sube la copia a «Jarvis/Respaldos» de tu Drive y deja solo las últimas. 12.8: si pusiste la clave de las copias,
    va cifrada entera (.jvbk). Devuelve el nombre o lanza error."""
    client = J.classroom_client()
    sub = _drive_backup_folder(client)
    sealed = bool(J.settings.get("cloud_pass"))
    up = _sealed_copy(path) if sealed else path
    try:
        f = gservicios.upload(client, up, sub)
    finally:
        if sealed:
            try:
                os.remove(up)
            except OSError:
                pass
    keep = J.settings["drive_backup_keep"]
    for old in [x for x in gservicios.list_folder(client, sub) if copianube.is_copy(x["name"])][keep:]:
        try:
            gservicios.delete(client, old["id"])
        except classroom.ClassroomError:
            pass
    if sealed:
        J.apply_settings({"cloud_last": datetime.datetime.now().isoformat(timespec="seconds"), "cloud_last_error": ""})
    return f.get("name", os.path.basename(up))


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


# ============================================================================ 12.8: CADA NOCHE, CIFRADA, EN TU DRIVE
cloud_state = {"busy": False, "tried": 0.0}


def cloud_ready():
    """(lista, qué falta)."""
    if not J.settings.get("cloud_nightly"):
        return False, "la copia de cada noche está apagada"
    if not J.gdrive_ready():
        return False, "falta conectar tu cuenta de Google (Ajustes › Memoria › Cuenta de Google)"
    if not J.settings.get("cloud_pass"):
        return False, "falta poner la clave de las copias (Ajustes › Memoria › Copias de seguridad)"
    if not datos.available():
        return False, "falta la librería «cryptography»"
    return True, ""


def cloud_backup_now(kind="auto"):
    """Hace la copia y la sube cifrada. → nombre en Drive (lanza error si no se pudo)."""
    if cloud_state["busy"]:
        raise RuntimeError("ya estoy subiendo una copia")
    cloud_state["busy"] = True
    try:
        res = J.make_backup(kind, upload=False)
        return backup_to_drive(res["path"])
    except Exception as e:
        J.apply_settings({"cloud_last_error": f"{datetime.datetime.now():%Y-%m-%d %H:%M} · {str(e)[:160]}"})
        raise
    finally:
        cloud_state["busy"] = False


def _cloud_worker():
    time.sleep(240)
    while True:
        try:
            ok, _why = cloud_ready()
            if ok and not J.is_offline() and time.time() - cloud_state["tried"] > 3600 and \
                    copianube.due(datetime.datetime.now(), J.settings.get("cloud_last", ""), int(J.settings.get("cloud_hour", 21))):
                cloud_state["tried"] = time.time()
                name = cloud_backup_now("auto")
                J.log_terminal(f"Copia de la noche, cifrada, en tu Drive: {name}", "RESPALDO")
        except Exception as e:
            J.note_error("RESPALDO", e)
            J.log_terminal(f"No pude subir la copia de la noche a Drive: {e}", "AVISO")
        time.sleep(600)


def cloud_info():
    ok, why = cloud_ready()
    return {"ok": True, "lista": ok, "falta": why, "google": bool(J.gdrive_ready()), "clave": bool(J.settings.get("cloud_pass")),
            "activa": bool(J.settings.get("cloud_nightly")), "hora": J.settings.get("cloud_hour", 21),
            "ultima": J.settings.get("cloud_last", ""), "error": J.settings.get("cloud_last_error", ""), "subiendo": cloud_state["busy"]}


def cloud_list():
    client = J.classroom_client()
    sub = _drive_backup_folder(client)
    return [{"id": x["id"], "nombre": x["name"], "fecha": x.get("createdTime", ""), "kb": max(1, int(x.get("size") or 0) // 1024),
             "cifrada": x["name"].lower().endswith(copianube.EXT)} for x in gservicios.list_folder(client, sub) if copianube.is_copy(x["name"])]


def cloud_fetch(file_id, password=""):
    """Trae una copia de tu Drive a la carpeta de copias (la descifra con tu clave). Lo que se restaura lo eliges después,
    como con cualquier copia: aquí nada se reemplaza. → {"name", "info", "clave_datos"}."""
    import respaldo
    client = J.classroom_client()
    meta = next((x for x in cloud_list() if x["id"] == file_id), None)
    if not meta:
        raise ValueError("esa copia ya no está en tu Drive")
    blob = gservicios.download(client, file_id)
    key_note = ""
    if copianube.is_sealed(blob):
        raw = copianube.unseal(blob, password or J.settings.get("cloud_pass", ""))
        raw, data_key = copianube.split_key(raw)
        if data_key and data_key != J.settings.get("data_key"):
            if not J.settings.get("data_key") or students_locked():
                unlock_students(data_key)              # equipo nuevo: la clave de las notas viene en la copia
                key_note = "puse"
            else:
                key_note = "distinta"
    else:
        raw = blob
    folder = J.backup_folder()
    os.makedirs(folder, exist_ok=True)
    name = f"Jarvis respaldo de la nube {datetime.datetime.now():%Y-%m-%d %H%M%S}.zip"
    path = os.path.join(folder, name)
    with open(path, "wb") as f:
        f.write(raw)
    try:
        info = respaldo.inspect(path)
    except respaldo.BackupError:
        os.remove(path)
        raise
    return {"name": name, "info": info, "clave_datos": key_note}


@J.socketio.on("cloud_backup")
def handle_cloud_backup(data=None):
    d = data or {}
    act = str(d.get("action") or "")
    if act in ("listar", "ahora", "traer") and not J.gdrive_ready():          # 12.16.2: el motivo claro
        why = ("tu cuenta de Google no está conectada: ve a Ajustes › Memoria › Cuenta de Google y pulsa «Conectar con Google»"
               if not J.classroom_client() else "a tu conexión de Google le falta el permiso de Drive: pulsa otra vez «Conectar con Google» "
               "y acepta todo lo que pide")
        return {**cloud_info(), "ok": False, "error": f"No puedo usar tu Drive: {why}."}
    try:
        if act == "listar":
            return {**cloud_info(), "items": cloud_list()}
        if act == "ahora":
            if not J.settings.get("cloud_pass"):
                return {**cloud_info(), "ok": False, "error": "Primero escribe la clave de las copias y guarda."}
            name = cloud_backup_now("manual")
            return {**cloud_info(), "msg": f"Copia cifrada subida a tu Drive: {name}."}
        if act == "traer":
            r = cloud_fetch(str(d.get("id") or ""), str(d.get("clave") or ""))
            return {**cloud_info(), **r, **J._bak_list()}
    except copianube.WrongPassword:
        return {**cloud_info(), "ok": False, "error": "Esa no es la clave de esa copia."}
    except Exception as e:
        return {**cloud_info(), "ok": False, "error": str(e)[:200]}
    return cloud_info()


_CLOUD_WHEN = re.compile(r"\b(?:cuando (?:fue|hiciste|se hizo)|hay) (?:la )?(?:ultima )?(?:copia|respaldo)\b.*\b(?:nube|drive)\b|"
                         r"\b(?:ultima copia|ultimo respaldo) (?:en la nube|en drive|de la nube)\b")
_CLOUD_FETCH = re.compile(r"\b(?:trae|traeme|descarga|baja|recupera)\b.*\b(?:copia|respaldo)\b.*\b(?:nube|drive)\b")


def cloud_voice(text, t):
    if _CLOUD_FETCH.search(t):
        if not J.gdrive_ready():
            J.reply("Primero conecta tu cuenta de Google en Ajustes › Memoria › Cuenta de Google.", "RESPALDO")
            return True
        try:
            items = cloud_list()
            if not items:
                J.reply("No hay copias en tu Drive todavía.", "RESPALDO")
                return True
            r = cloud_fetch(items[0]["id"])
        except copianube.WrongPassword:
            J.reply("La copia de tu Drive tiene otra clave: escríbela en Ajustes › Memoria › Copias de seguridad, «Traer de mi Drive».",
                    "RESPALDO")
            return True
        except Exception as e:
            J.reply(f"No pude traer la copia: {str(e)[:160]}", "RESPALDO")
            return True
        J.reply(f"Traje la copia más reciente de tu Drive. Para restaurarla, en Ajustes › Memoria › Copias de seguridad pulsa «Restaurar…» "
                "y elige qué recuperar; nada se reemplazó todavía." + (" Ya puse la clave de las notas que venía en la copia." if r["clave_datos"] == "puse"
                                                                        else ""), "RESPALDO")
        return True
    if _CLOUD_WHEN.search(t):
        i = cloud_info()
        if i["ultima"]:
            J.reply(f"La última copia cifrada en tu Drive fue el {i['ultima'][:10]} a las {i['ultima'][11:16]}."
                    + ("" if i["lista"] else f" Ojo: {i['falta']}."), "RESPALDO")
        else:
            J.reply("Todavía no hay copias cifradas en tu Drive" + (f": {i['falta']}." if i["falta"] else "; la primera sale esta noche."),
                    "RESPALDO")
        return True
    return False


def cloud_start():
    threading.Thread(target=_cloud_worker, daemon=True, name="copia-nube").start()


def students_start():
    """Tras leer los ajustes (con la clave): abre lo que se cargó antes de tenerla."""
    for m in STUDENT_FILES.values():
        if getattr(m, "locked", False) and getattr(m, "_path", None):
            m.load()
    left = students_locked()
    if left:
        J.log_terminal("Hay datos de estudiantes cifrados con otra clave (" + ", ".join(left) + "): pega la clave de "
                       "recuperación en Ajustes › Memoria para abrirlos.", "AVISO")


__all__ = ['STUDENT_FILES', '_BK_RE', '_CLOUD_FETCH', '_CLOUD_WHEN', '_drive_backup_folder', '_sealed_copy', 'cloud_backup_now', 'cloud_fetch',
           'cloud_info', 'cloud_list', 'cloud_ready', 'cloud_start', 'cloud_state', 'cloud_voice', 'handle_cloud_backup', '_resave_all', 'after_backup', 'backup_drive_voice', 'backup_to_drive',
           'handle_students_info', 'handle_students_protect', 'protect_students', 'students_info', 'students_locked', 'students_start',
           'unlock_students']
