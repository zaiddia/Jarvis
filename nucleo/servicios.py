"""Actualizaciones desde GitHub y copias de seguridad.

Parte de Jarvis (antes dentro de jarvis.py). Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import actualizar
import aula
import datetime
import habilidades
import aprendizaje
import tareas
import json
import notas
import os
import perfil
import platform
import re
import respaldo
import rutinas
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from nucleo import J


# =============================================================================
# ACTUALIZACIONES desde GitHub (lógica en actualizar.py)
# =============================================================================
UPDATE_STATE_PATH = os.path.join(J.CONFIG_DIR, "actualizacion.json")
upd = {"busy": False, "info": None, "last_error": "", "step": ""}
_upd_lock = threading.Lock()


def _upd_load():
    try:
        with open(J.UPDATE_STATE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _upd_save(**changes):
    d = J._upd_load()
    d.update(changes)
    try:
        os.makedirs(J.CONFIG_DIR, exist_ok=True)
        with open(J.UPDATE_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except OSError:
        pass


def _upd_progress(step, pct=None, done=False, ok=True, msg=""):
    J.upd["step"] = step
    J.socketio.emit("update_progress", {"step": step, "pct": pct, "done": done, "ok": ok, "msg": msg})


def update_status():
    """Lo que necesita la sección Acerca de."""
    b = None
    try:
        b = actualizar.last_backup(J.APP_DIR)
    except Exception:
        pass
    return {"version": J.VERSION, "repo": J.settings["update_repo"], "busy": J.upd["busy"], "info": J.upd["info"],
            "frozen": bool(getattr(sys, "frozen", False)),
            "backup": {"from": b.get("desde"), "to": b.get("hacia"), "date": b.get("fecha")} if b else None,
            "last_check": J._upd_load().get("checked", 0)}


def check_updates():
    """Consulta GitHub. Devuelve la info (o lanza actualizar.UpdateError con un mensaje claro)."""
    if not J.settings["update_repo"].strip():
        raise actualizar.UpdateError("Primero escribe en Ajustes › Acerca de el repositorio de GitHub "
                                     "donde se publican las versiones de Jarvis (usuario/nombre).")
    if J.is_offline():
        raise actualizar.UpdateError("Ahora mismo no hay internet.")
    info = actualizar.latest(J.settings["update_repo"], J.VERSION, J.settings["github_api_key"].strip())
    J.upd["info"] = info
    J._upd_save(checked=time.time())
    return info


def _update_worker():
    """Una vez al día (si está activado) mira si hay versión nueva y lo avisa sin interrumpir."""
    time.sleep(90)
    while True:
        try:
            if (J.settings["update_auto"] and J.settings["update_repo"].strip() and not J.upd["busy"]
                    and time.time() - J._upd_load().get("checked", 0) > 20 * 3600 and not J.is_offline()):
                info = J.check_updates()
                if info["newer"] and J._upd_load().get("notified") != info["version"]:
                    J._upd_save(notified=info["version"])
                    msg = (f"Hay una versión nueva de Jarvis: la {info['version']} (tienes la {J.VERSION}). "
                           "Para instalarla: Ajustes › Acerca de › Actualizar.")
                    J.log_terminal(msg, "ACTUALIZACIÓN")
                    J.push_chat("jarvis", msg, "ACTUALIZACIÓN")
        except actualizar.UpdateError as e:
            J.log_terminal(f"Buscar actualizaciones: {e}", "AVISO")
        except Exception as e:
            J.log_terminal(f"Buscar actualizaciones: {e}", "AVISO")
        time.sleep(3600)


def _python_console():
    """python.exe junto a pythonw.exe (para instalar componentes sin abrir ventanas raras)."""
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        cand = exe[:-len("pythonw.exe")] + "python.exe"
        if os.path.exists(cand):
            return cand
    return exe


def restart_jarvis(delay=1.0):
    """Abre un Jarvis nuevo (que espera a que este se cierre) y cierra este."""
    args = [sys.executable, os.path.join(J.APP_DIR, "jarvis.py"), *sys.argv[1:]]
    env = dict(os.environ, JARVIS_WAIT_PID=str(os.getpid()))
    kw = {"cwd": J.APP_DIR, "env": env, "close_fds": True}
    if J.IS_WIN:
        kw["creationflags"] = 0x00000008 | 0x00000200          # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen(args, **kw)
    threading.Timer(delay, J.quit_app).start()


def install_update():
    """Descarga, instala (con copia de seguridad) y reinicia. Corre en su propio hilo."""
    if getattr(sys, "frozen", False):
        J._upd_progress("Esta copia de Jarvis es el .exe compilado: actualiza la carpeta del código "
                      "y vuelve a ejecutar compilar.bat.", done=True, ok=False)
        return
    with J._upd_lock:
        if J.upd["busy"]:
            return
        J.upd["busy"] = True
    tmp = os.path.join(tempfile.gettempdir(), f"jarvis_actualizacion_{uuid.uuid4().hex}.zip")
    try:
        info = J.upd["info"] if J.upd["info"] and J.upd["info"].get("newer") else J.check_updates()
        if not info["newer"]:
            J._upd_progress(f"Ya tienes la última versión ({J.VERSION}).", done=True)
            return
        J._upd_progress(f"Descargando la versión {info['version']}…", 0)
        token = J.settings["github_api_key"].strip()
        actualizar.download(info, tmp, token, lambda got, total: J._upd_progress(
            f"Descargando la versión {info['version']}…", round(got * 100 / total) if total else None))
        zv = actualizar.zip_version(tmp)
        if actualizar.parse_version(zv) <= actualizar.parse_version(J.VERSION):
            raise actualizar.UpdateError(f"El archivo publicado trae la versión {zv}, que no es más nueva "
                                         f"que la tuya ({J.VERSION}). Revisa la Release en GitHub.")
        J._upd_progress("Instalando (con copia de seguridad)…", 0)
        res = actualizar.apply(tmp, J.APP_DIR, J.VERSION,
                               lambda i, n: J._upd_progress("Instalando (con copia de seguridad)…", round(i * 100 / n)))
        J.log_terminal(f"Actualizado a la versión {res['version']}: {len(res['changed'])} archivos cambiados, "
                     f"{len(res['added'])} nuevos. Copia de seguridad en {res['backup']}.", "ACTUALIZACIÓN")
        if res["requirements_changed"]:
            J._upd_progress("Instalando componentes nuevos (puede tardar unos minutos)…")
            try:
                r = subprocess.run([J._python_console(), "-m", "pip", "install", "-q", "-r",
                                    os.path.join(J.APP_DIR, "requirements.txt")], cwd=J.APP_DIR,
                                   capture_output=True, text=True, timeout=900,
                                   creationflags=0x08000000 if J.IS_WIN else 0)
                if r.returncode != 0:
                    J.log_terminal("Algunos componentes nuevos no se instalaron; ejecuta instalar.bat. "
                                 + (r.stderr or "")[-300:], "AVISO")
            except Exception as e:
                J.log_terminal(f"No pude instalar componentes nuevos ({e}); ejecuta instalar.bat.", "AVISO")
        J._upd_save(installed=res["version"], notified=res["version"], just_updated=res["version"], boot_count=0)  # 8.3
        J._upd_progress(f"Listo: versión {res['version']} instalada. Reiniciando Jarvis…", 100, done=True)
        J.reply(f"Me actualicé a la versión {res['version']}. Me reinicio en un momento.", "ACTUALIZACIÓN")
        J.restart_jarvis(delay=3.0)
    except actualizar.UpdateError as e:
        J.upd["last_error"] = str(e)
        J._upd_progress(str(e), done=True, ok=False)
    except Exception as e:
        J.upd["last_error"] = str(e)
        J.log_terminal(f"Actualización fallida: {e}", "ERROR")
        J._upd_progress(f"No se pudo actualizar: {e}. Si algo quedó mal, usa «Deshacer la última actualización».",
                      done=True, ok=False)
    finally:
        J.upd["busy"] = False
        try:
            os.remove(tmp)
        except OSError:
            pass


def rollback_update():
    if J.upd["busy"]:
        return {"ok": False, "error": "Hay una actualización en curso."}
    try:
        res = actualizar.rollback(J.APP_DIR)
    except actualizar.UpdateError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"No se pudo deshacer: {e}"}
    J.log_terminal(f"Actualización deshecha: vuelvo a la versión {res['version']}.", "ACTUALIZACIÓN")
    J._upd_save(notified=res["from"])               # no volver a avisar de la versión que deshiciste
    J.restart_jarvis(delay=2.0)
    return {"ok": True, "version": res["version"]}


_UPD_RE = re.compile(r"\b(?:busca|buscar|buscame|hay|revisa|comprueba|mira si hay|tienes|instala|instalar|descarga|descargar)\b.*\bactualizacion(?:es)?\b"
                     r"|\binstala(?:r)? (?:la )?(?:nueva version|version nueva)\b|\bponte al dia\b|\bactualizate\b|\bactualiza (?:a )?jarvis\b|\b(?:version nueva|nueva version) de jarvis\b"
                     r"|\bque version (?:eres|tienes)\b|\ben que version (?:estas|vas)\b")


def update_voice(text, t):
    """«Jarvis, ¿hay actualizaciones?», «¿qué versión eres?» consultan; «actualízate» o «instala la actualización»
    instalan, pero siempre preguntando antes (así nunca se reinicia en mitad de una clase sin querer)."""
    if not J._UPD_RE.search(t):
        return False
    if re.search(r"\bque version\b|\ben que version\b", t):
        J.reply(f"Soy Jarvis {J.VERSION}.", "ACTUALIZACIÓN")
        return True
    try:
        info = J.check_updates()
    except actualizar.UpdateError as e:
        J.reply(f"No pude buscar actualizaciones: {e}", "ACTUALIZACIÓN")
        return True
    install = bool(re.search(r"\b(?:actualizate|actualizarte|actualiza (?:a )?jarvis|instala(?:r)? (?:la )?(?:actualizacion|nueva version|version nueva)|"
                             r"descarga(?:r)? (?:la )?actualizacion|ponte al dia)\b", t))
    if info["newer"] and install:
        J.upd["info"] = info
        J.run_skill("instalar_actualizacion", {})       # pide confirmación (y desde el celular no se hace)
    elif info["newer"]:
        J.reply(f"Hay una versión nueva: la {info['version']}; tienes la {J.VERSION}. Di «actualízate» para "
              "instalarla, o pulsa Actualizar en Ajustes, sección Acerca de.", "ACTUALIZACIÓN")
    else:
        J.reply(f"Estás al día: tienes la versión {J.VERSION}, la última publicada.", "ACTUALIZACIÓN")
    return True



# =============================================================================
# COPIAS DE SEGURIDAD (ajustes, notas, cursos, rutinas, memoria). Lógica en respaldo.py.
# =============================================================================
BACKUP_KEEP_AUTO = 8
# Se restauran solo si la copia es de este mismo equipo o la ruta existe aquí
_MACHINE_KEYS = {"mic_device", "output_dir", "talleres_dir", "piper_voice", "alarm_sound", "backup_dir",
                 "camera_index"}
_bak_lock = threading.Lock()


def backup_folder():
    return J.settings["backup_dir"].strip() or os.path.join(J.settings["output_dir"], "Respaldos")


def make_backup(kind="manual", include_secrets=None):
    with J._bak_lock:
        res = respaldo.create(J.CONFIG_DIR, J.backup_folder(), J.settings, J.SECRET_FIELDS,
                              J.settings["backup_secrets"] if include_secrets is None else include_secrets,
                              J.VERSION, kind)
        if kind in ("auto", "antes"):
            respaldo.prune(J.backup_folder(), J.BACKUP_KEEP_AUTO, kind)
    J.log_terminal(f"Copia de seguridad guardada: {res['path']}", "RESPALDO")
    if kind in ("auto", "manual"):
        J.after_backup(res)                            # 8.9: también a tu Drive
    return res


def _backup_summary(res):
    c = res.get("counts", {})

    def n(k, one, many):
        v = c.get(k) or 0
        return f"{v} {one if v == 1 else many}"
    bits = ["tus ajustes"]
    if "notas" in res["parts"]:
        bits.append(n("notas", "nota", "notas"))
    if "aula" in res["parts"]:
        bits.append(n("aula", "curso", "cursos") + " con sus listas")
    if "rutinas" in res["parts"]:
        bits.append(n("rutinas", "rutina", "rutinas"))
    if "perfil" in res["parts"]:
        bits.append(n("perfil", "cosa que sé de ti", "cosas que sé de ti"))
    if "habilidades" in res["parts"]:
        bits.append(n("habilidades", "habilidad", "habilidades"))
    return ", ".join(bits[:-1]) + " y " + bits[-1] if len(bits) > 1 else bits[0]


def _backup_worker():
    """Una copia automática a la semana (se guardan las 8 últimas)."""
    time.sleep(300)
    while True:
        try:
            if J.settings["backup_auto"]:
                autos = [b for b in respaldo.listing(J.backup_folder()) if b["kind"] == "auto"]
                last = 0.0
                if autos:
                    try:
                        last = datetime.datetime.fromisoformat(autos[0]["date"]).timestamp()
                    except ValueError:
                        last = 0.0
                if time.time() - last > 7 * 86400:
                    J.make_backup("auto")
        except Exception as e:
            J.log_terminal(f"Copia de seguridad automática: {e}", "AVISO")
        time.sleep(3600)


def restore_backup(name, parts):
    """Restaura las partes elegidas de una copia de la carpeta de copias.
    Antes guarda una copia de cómo está todo ahora, por si te arrepientes."""
    path = os.path.join(J.backup_folder(), respaldo.safe_name(name))
    info = respaldo.inspect(path)
    parts = [p for p in parts if p in respaldo.PARTS and p in {x["part"] for x in info["parts"]}]
    if not parts:
        raise respaldo.BackupError("Elige al menos una parte para restaurar.")
    safety = J.make_backup("antes")
    skipped = []
    if "ajustes" in parts:
        cfg = respaldo.read_config(path)
        same_pc = info["computer"] and info["computer"] == platform.node()
        data = {}
        for k, v in cfg.items():
            if k not in J.DEFAULT_SETTINGS or k in ("hud_x", "hud_y"):
                continue
            if k in J._MACHINE_KEYS and not same_pc:
                if k == "mic_device" or not (isinstance(v, str) and v and os.path.exists(v)):
                    if v not in ("", None) and v != J.DEFAULT_SETTINGS[k]:
                        skipped.append(k)
                    continue
            data[k] = v
        errs = J.apply_settings(data)                       # valida cada valor; claves vacías = conservar
        if errs:
            J.log_terminal("Restaurar ajustes: " + "; ".join(errs), "AVISO")
    done = respaldo.restore(path, J.CONFIG_DIR, parts)
    if "notas" in done:
        notas.load()
    if "aula" in done:
        aula.load()
    if "rutinas" in done:
        rutinas.load()
    if "horario" in done:                              # 8.1
        J.horario.load()
    if "observador" in done:                           # 8.2
        J.informes.load()
    if "registro" in done:                             # 8.8
        J.diarioclase.load()
    if "periodos" in done:                             # 10.2
        J.periodos.load()
    if "examenes" in done:                             # 10.5
        J.examenes.load()
    if "saber" in done:                                # 10.6
        J.saber.load()
    if "practica" in done:                             # 10.7
        J.practica.load()
    if "planeacion" in done:                           # 10.8
        J.anual.load()
    if "compromisos" in done:                          # 9.3
        J.compromisos.load()
    if "lecciones" in done:                            # 9.4
        J.lecciones.load()
    if "paginas" in done:
        J.paginas.load()
    if "estilo" in done:                               # 9.5
        J.estilo.load()
    if "memoria" in done:
        J.load_memory()
    if "perfil" in done:
        perfil.load()
        J._profile_changed()
    if "habilidades" in done:
        habilidades.load()
        tareas.load()                                  # 7.4
        J.seguimiento.load()                           # 7.8
        J.banco.load()
        aprendizaje.load()
    J.socketio.emit("settings_updated", J.public_settings())
    names = [respaldo.PARTS[p].lower() for p in parts]
    J.log_terminal(f"Restaurado desde «{info['name']}»: {', '.join(names)}. "
                 f"Copia previa en «{safety['name']}».", "RESPALDO")
    return {"ok": True, "parts": parts, "safety": safety["name"], "skipped": skipped,
            "secrets_missing": "ajustes" in parts and not info["with_secrets"]}


_BAK_RE = re.compile(r"\b(?:haz|hazme|hacer|crea|crear|guarda|guardar|saca|sacar|genera)\b.{0,25}\b(?:copia de seguridad|respaldo|backup)\b"
                     r"|\brespalda(?:r|me)?\b.{0,20}\b(?:ajustes|configuracion|datos|todo|notas|cursos)\b")


def backup_voice(text, t):
    """«Jarvis, haz una copia de seguridad». Restaurar es solo desde Ajustes (reemplaza datos)."""
    if not J._BAK_RE.search(t):
        return False
    try:
        res = J.make_backup("manual")
    except Exception as e:
        J.reply(f"No pude hacer la copia de seguridad: {e}", "RESPALDO")
        return True
    where = ("tu carpeta Documentos, en Jarvis, Respaldos" if not J.settings["backup_dir"].strip()
             else "la carpeta de copias que elegiste en Ajustes")
    J.reply(f"Listo, guardé {J._backup_summary(res)} en {where}.", "RESPALDO")
    return True


__all__ = [
    'BACKUP_KEEP_AUTO',
    'UPDATE_STATE_PATH',
    '_BAK_RE',
    '_MACHINE_KEYS',
    '_UPD_RE',
    '_backup_summary',
    '_backup_worker',
    '_bak_lock',
    '_python_console',
    '_upd_load',
    '_upd_lock',
    '_upd_progress',
    '_upd_save',
    '_update_worker',
    'backup_folder',
    'backup_voice',
    'check_updates',
    'install_update',
    'make_backup',
    'restart_jarvis',
    'restore_backup',
    'rollback_update',
    'upd',
    'update_status',
    'update_voice',
]
