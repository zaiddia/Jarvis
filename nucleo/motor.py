"""12.6: la IA local integrada. Jarvis descarga una sola vez el motor llama.cpp y un modelo, y lo enciende solo cuando
hace falta (sin internet, o si eliges «Jarvis local» como IA); lo apaga a los 20 minutos sin uso para liberar memoria.
No hay que instalar ni abrir Ollama, y funciona también en la versión .exe.

La lógica está en motorlocal.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import json
import os
import re
import shutil
import subprocess
import tarfile
import threading
import time
import urllib.request
import zipfile

import motorlocal
from nucleo import J

engine = {"proc": None, "last": 0.0, "busy": False, "job": False, "msg": "", "lock": threading.Lock()}
IDLE_STOP = 20 * 60


def _dir(*parts):
    return os.path.join(J.CONFIG_DIR, "motor", *parts)


def motor_paths():
    """(ruta de llama-server o "", ruta del modelo o "")."""
    exe = motorlocal.find_exe(_dir("bin"), J.IS_WIN) if os.path.isdir(_dir("bin")) else ""
    want = J.settings.get("motor_model", "").strip()
    mdir = _dir("modelos")
    models = sorted(f for f in os.listdir(mdir) if f.lower().endswith(".gguf")) if os.path.isdir(mdir) else []
    model = want if want in models else (models[0] if models else "")
    return exe, (os.path.join(mdir, model) if model else "")


def motor_ready():
    exe, model = J.motor_paths()
    return bool(exe and model)


def motor_name():
    _exe, model = J.motor_paths()
    return os.path.splitext(os.path.basename(model))[0] if model else ""


def _mt_alive():
    p = engine["proc"]
    return p is not None and p.poll() is None


def _health(timeout=1.5):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{motorlocal.PORT}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def motor_start(wait=120):
    """Enciende el motor (si no está) y espera a que cargue el modelo. → True si responde."""
    with engine["lock"]:
        engine["last"] = time.time()
        if _mt_alive() and _health():
            return True
        exe, model = J.motor_paths()
        if not (exe and model):
            return False
        if not _mt_alive():
            threads = max(1, (os.cpu_count() or 4) - 1)
            engine["proc"] = subprocess.Popen(motorlocal.server_args(exe, model, threads=threads), cwd=os.path.dirname(exe),
                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                              creationflags=0x08000000 if J.IS_WIN else 0)
            J.log_terminal(f"Enciendo la IA integrada ({motor_name()})…", "IA LOCAL")
        t0 = time.time()
        while time.time() - t0 < wait:
            if not _mt_alive():
                J.log_terminal("La IA integrada no pudo arrancar (¿poca memoria?).", "IA LOCAL")
                engine["proc"] = None
                return False
            if _health():
                return True
            time.sleep(0.5)
        return False


def motor_stop():
    p = engine["proc"]
    engine["proc"] = None
    if p is not None and p.poll() is None:
        try:
            p.terminate()
            p.wait(timeout=8)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


def motor_ensure():
    """Antes de preguntarle: lo enciende si hace falta. Lanza AIError si no se puede."""
    engine["last"] = time.time()
    if _mt_alive() and _health(0.8):
        return
    if not J.motor_ready():
        raise J.AIError("La IA integrada no está instalada.", kind="config",
                        why="la IA integrada no está instalada. En Ajustes › IA pulsa «Instalar la IA integrada»")
    if not J.motor_start():
        raise J.AIError("La IA integrada no arrancó.", kind="net", why="la IA integrada no pudo arrancar; puede faltar memoria")


def _idle_worker():
    while True:
        time.sleep(30)
        try:
            if J.net.get("offline") and J.settings.get("offline_auto") and J.motor_ready() and not _mt_alive() and not engine["job"]:
                threading.Thread(target=J.motor_start, daemon=True).start()     # sin internet: se enciende antes de que preguntes
            keep = J.settings.get("ai_provider") == "motor" and not J.settings.get("motor_autostop", True)
            if _mt_alive() and not keep and time.time() - engine["last"] > IDLE_STOP and not J.net.get("offline"):
                motor_stop()
                J.log_terminal("Apagué la IA integrada (no se usaba) para liberar memoria.", "IA LOCAL")
        except Exception:
            pass


# ============================================================================ INSTALAR (UNA SOLA VEZ, CON TU «SÍ»)
def _mt_get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": f"Jarvis/{J.VERSION}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _mt_fetch(url, dst, progress=None, label=""):
    """Descarga con reanudación (si se corta, sigue donde iba)."""
    part = dst + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    headers = {"User-Agent": f"Jarvis/{J.VERSION}"}
    if have:
        headers["Range"] = f"bytes={have}-"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        if have and r.status != 206:
            have = 0
        total = have + int(r.headers.get("Content-Length") or 0)
        mode = "ab" if have else "wb"
        done, last = have, 0.0
        with open(part, mode) as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress and time.time() - last > 2:
                    last = time.time()
                    progress(label, done / total if total else 0)
    os.replace(part, dst)
    return dst


def install_engine(progress=None):
    """Baja el motor llama.cpp para este sistema. → ruta de llama-server."""
    exe, _m = J.motor_paths()
    if exe:
        return exe
    rel = motorlocal.pick_release(J._motor_get_json(motorlocal.RELEASES_API), J.IS_WIN)
    if not rel:
        raise ValueError("no encontré el motor para este sistema en las versiones de llama.cpp")
    url, name, tag = rel
    os.makedirs(_dir("bin"), exist_ok=True)
    arc = J._motor_fetch(url, _dir(name), progress, "el motor")
    if arc.endswith(".zip"):
        with zipfile.ZipFile(arc) as z:
            z.extractall(_dir("bin"))
    else:
        with tarfile.open(arc) as t:
            t.extractall(_dir("bin"), filter="data")
    os.remove(arc)
    exe = motorlocal.find_exe(_dir("bin"), J.IS_WIN)
    if not exe:
        raise ValueError("el archivo del motor no trae llama-server")
    if not J.IS_WIN:
        os.chmod(exe, 0o755)
    with open(_dir("bin", "version.txt"), "w", encoding="utf-8") as f:
        f.write(tag)
    return exe


def install_model(mid=None, progress=None):
    """Baja el modelo del catálogo (el recomendado para este equipo si no se dice cuál). → ruta del .gguf."""
    m = motorlocal.by_id(mid) if mid else J.motor_recommend()
    if not m:
        raise ValueError("este equipo no tiene memoria o disco suficiente para una IA local")
    info = J._motor_get_json(motorlocal.hf_api(m["repo"]))
    name = motorlocal.pick_gguf(info.get("siblings") or [], m["patron"])
    if not name:
        raise ValueError(f"no encontré el archivo del modelo {m['nombre']}")
    os.makedirs(_dir("modelos"), exist_ok=True)
    dst = _dir("modelos", os.path.basename(name))
    if not os.path.exists(dst):
        J._motor_fetch(motorlocal.hf_file(m["repo"], name), dst, progress, m["nombre"])
    J.settings["motor_model"] = os.path.basename(dst)
    try:
        J.save_settings_file()
    except OSError:
        pass
    return dst


def motor_recommend():
    ram = J.psutil.virtual_memory().total / 1e9 if J.psutil else 8.0
    try:
        free = shutil.disk_usage(J.CONFIG_DIR).free / 1e9
    except OSError:
        free = 0
    return motorlocal.recommend(ram, free)


def motor_install_job(mid=None):
    if engine["job"]:
        return False
    engine["job"] = True

    def prog(label, frac):
        engine["msg"] = f"Descargando {label}: {int(frac * 100)} %"
        J.socketio.emit("motor", J.motor_status())

    def work():
        try:
            J.install_engine(prog)
            path = J.install_model(mid, prog)
            engine["msg"] = "Probando…"
            ok = J.motor_start(180)
            if ok:
                r = J.motor_ask([{"role": "user", "content": "Responde en una frase: ¿cuánto es 7 por 8?"}], max_tokens=40)
                msg = (f"Lista la IA integrada ({os.path.splitext(os.path.basename(path))[0]}). Respondió: «{r[:80]}». Si se cae el internet, la uso sola; "
                       "no hace falta Ollama.")
            else:
                msg = "Descargué la IA integrada, pero no arrancó en este equipo (puede faltar memoria). Prueba un modelo más liviano en Ajustes › IA."
        except Exception as e:
            msg = f"No pude instalar la IA integrada: {str(e)[:160]}"
        finally:
            engine["job"] = False
            engine["msg"] = ""
            J.net.update(local_at=0)
        J.notify(msg, "IA LOCAL")
        J.socketio.emit("motor", J.motor_status())
    J.start_job("Instalando la IA integrada", work, "motor")
    return True


def motor_ask(messages, max_tokens=400, json_mode=False):
    """Pregunta directa a la IA integrada (para la prueba y para el respaldo sin internet)."""
    J.motor_ensure()
    cfg = J._ai_cfg({"ai_provider": "motor"})
    return motorlocal.clean_reply(J.openai_chat(cfg, messages, json_mode, max_tokens))


def motor_status():
    exe, model = J.motor_paths()
    rec = J.motor_recommend()
    return {"motor": bool(exe), "modelo": os.path.basename(model) if model else "", "corriendo": _mt_alive(), "instalando": engine["job"],
            "msg": engine["msg"], "recomendado": rec["nombre"] if rec else "", "recomendado_gb": rec["gb"] if rec else 0,
            "catalogo": [{"id": m["id"], "nombre": m["nombre"], "gb": m["gb"]} for m in motorlocal.CATALOG]}


@J.socketio.on("motor")
def handle_motor(data=None):
    d = data or {}
    act = str(d.get("action") or "")
    if act == "instalar":
        mid = str(d.get("modelo") or "") or None
        m = motorlocal.by_id(mid) if mid else J.motor_recommend()
        if not m:
            return {"ok": False, "msg": "Este equipo no tiene memoria o disco suficiente para una IA local.", **J.motor_status()}
        J.request_approval("instalar", f"Instalar la IA integrada: {m['nombre']} (unos {m['gb']} GB)",
                           "Baja una sola vez el motor llama.cpp y el modelo a la carpeta de Jarvis. Después funciona sin internet y sin Ollama.",
                           on_ok=lambda: J.motor_install_job(m["id"]), on_no=lambda: None, ttl=1800,
                           say=f"¿Instalo la IA integrada {m['nombre']}? Son unos {m['gb']} gigas, una sola vez. Di «sí» o «no».")
        return {"ok": True, "msg": "Te pedí permiso en el HUD: di «sí» o apruébalo en la bandeja.", **J.motor_status()}
    if act == "apagar":
        motor_stop()
        return {"ok": True, "msg": "Apagué la IA integrada.", **J.motor_status()}
    if act == "encender":
        threading.Thread(target=J.motor_start, daemon=True).start()
        return {"ok": True, "msg": "Encendiendo la IA integrada…", **J.motor_status()}
    return {"ok": True, **J.motor_status()}


_MOTOR_INST = re.compile(r"\b(?:instala|descarga|prepara|baja)\s+(?:la\s+)?(?:ia|inteligencia artificial)\s+(?:integrada|de jarvis|interna|dentro de jarvis)\b|"
                         r"\b(?:ia|cerebro) (?:integrad[oa]|sin ollama)\b")


def motor_voice(text, t):
    if not _MOTOR_INST.search(t):
        return False
    if J.motor_ready():
        J.reply(f"La IA integrada ya está lista ({J.motor_name()}). Si se cae el internet, la uso sola.", "IA LOCAL")
        return True
    J.reply(J.handle_motor({"action": "instalar"})["msg"], "IA LOCAL")
    return True


def motor_start_services():
    threading.Thread(target=_idle_worker, daemon=True, name="motor-idle").start()


_motor_get_json = _mt_get_json
_motor_fetch = _mt_fetch

__all__ = ['IDLE_STOP', '_MOTOR_INST', '_motor_fetch', '_motor_get_json', 'engine', 'handle_motor', 'install_engine', 'install_model', 'motor_ask',
           'motor_ensure', 'motor_install_job', 'motor_name', 'motor_paths', 'motor_ready', 'motor_recommend', 'motor_start', 'motor_start_services',
           'motor_status', 'motor_stop', 'motor_voice', 'motorlocal']
