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


def _exe_for(backend):
    if backend == "gpu":
        return motorlocal.find_exe(_dir("bin", "gpu"), J.IS_WIN, skip=()) if os.path.isdir(_dir("bin", "gpu")) else ""
    return motorlocal.find_exe(_dir("bin"), J.IS_WIN) if os.path.isdir(_dir("bin")) else ""


def _backend():
    """«gpu» si está instalada la versión con tarjeta gráfica y no se descartó; si no, «cpu»."""
    want = J.settings.get("motor_backend", "auto")
    if want != "cpu" and _exe_for("gpu"):
        return "gpu"
    return "cpu"


def motor_paths():
    """(ruta de llama-server o "", ruta del modelo o "")."""
    exe = _exe_for(_backend()) or _exe_for("cpu")
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


def motor_mmproj():
    """12.8: el archivo de visión del modelo en uso (motor/vision/<modelo>.gguf), o "" si no tiene o no sirvió."""
    _exe, model = J.motor_paths()
    if not model or engine.get("no_mm"):
        return ""
    p = _dir("vision", os.path.basename(model))
    return p if os.path.exists(p) else ""


def motor_sees():
    """¿La IA integrada puede ver imágenes? (instalada y con su archivo de visión)."""
    return bool(J.motor_ready() and motor_mmproj())


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
        gpu = _backend() == "gpu" and exe == _exe_for("gpu")
        mm = motor_mmproj()
        if not _mt_alive():
            phys = (J.psutil.cpu_count(logical=False) if J.psutil else None) or max(1, (os.cpu_count() or 4) // 2)
            engine["proc"] = subprocess.Popen(motorlocal.server_args(exe, model, ctx=8192 if mm else 4096, threads=phys,
                                                                     threads_batch=os.cpu_count() or phys, gpu=gpu, mmproj=mm),
                                              cwd=os.path.dirname(exe), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                              creationflags=0x08000000 if J.IS_WIN else 0)
            engine["gpu"], engine["mm"] = gpu, bool(mm)
            J.log_terminal(f"Enciendo la IA integrada ({motor_name()}{', con la tarjeta gráfica' if gpu else ''}{', con visión' if mm else ''})…",
                           "IA LOCAL")
        t0 = time.time()
        while time.time() - t0 < wait:
            if not _mt_alive():
                engine["proc"] = None
                if engine.get("mm"):                   # 12.8: con la visión no arrancó (memoria o motor viejo): sin ella
                    J.log_terminal("La IA integrada no arrancó con la visión; la enciendo solo para texto.", "IA LOCAL")
                    engine["no_mm"], engine["mm"] = True, False
                    engine["lock"].release()
                    try:
                        return J.motor_start(wait)
                    finally:
                        engine["lock"].acquire()
                if engine.get("gpu"):                  # 12.7: la tarjeta gráfica no sirvió: se usa el procesador
                    J.log_terminal("La IA integrada no arrancó con la tarjeta gráfica; uso el procesador.", "IA LOCAL")
                    J.settings["motor_backend"] = "cpu"
                    engine["gpu"] = False
                    engine["lock"].release()
                    try:
                        return J.motor_start(wait)
                    finally:
                        engine["lock"].acquire()
                J.log_terminal("La IA integrada no pudo arrancar (¿poca memoria?).", "IA LOCAL")
                return False
            if _health():
                threading.Thread(target=J.motor_warmup, daemon=True).start()
                return True
            time.sleep(0.5)
        return False


def motor_warmup():
    """12.7: deja leído el comienzo fijo de las instrucciones de Jarvis, así la primera pregunta no espera."""
    try:
        cfg = J._ai_cfg({"ai_provider": "motor"})
        J._post(cfg["base"] + "/chat/completions", {}, {"model": "jarvis", "max_tokens": 1, "cache_prompt": True,
                                                         "messages": [{"role": "system", "content": J.system_static()},
                                                                      {"role": "user", "content": "hola"}]}, {})
    except Exception:
        pass


def motor_bench():
    """Tokens por segundo de la IA integrada encendida (para escoger tarjeta gráfica o procesador)."""
    cfg = J._ai_cfg({"ai_provider": "motor"})
    t0 = time.time()
    r = J._post(cfg["base"] + "/chat/completions", {}, {"model": "jarvis", "max_tokens": 48, "temperature": 0,
                                                        "messages": [{"role": "user", "content": "Explica en dos frases qué es una fracción."}]}, {})
    tps = motorlocal.tokens_per_second(r)
    return tps or (48 / max(0.1, time.time() - t0))


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
                        why="la IA integrada no está instalada. En Ajustes › Inteligencia artificial pulsa «Instalar la IA integrada»")
    if not J.motor_start():
        raise J.AIError("La IA integrada no arrancó.", kind="net", why="la IA integrada no pudo arrancar; puede faltar memoria")


def _idle_worker():
    while True:
        time.sleep(30)
        try:
            if J.net.get("offline") and J.settings.get("offline_auto") and J.motor_ready() and not _mt_alive() and not engine["job"]:
                threading.Thread(target=J.motor_start, daemon=True).start()     # sin internet: se enciende antes de que preguntes
            keep = J.settings.get("ai_provider") == "motor" or not J.settings.get("motor_autostop", True)   # 12.7: si es tu IA, siempre lista
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


def verify_download(path, want, label):
    """12.11: que lo descargado sea exactamente lo publicado (huella SHA-256). Si no coincide, se borra y no se usa."""
    if not want:
        J.log_terminal(f"Sin huella publicada para {label}: no la pude verificar.", "IA LOCAL")
        return False
    if motorlocal.sha256_file(path) != want:
        try:
            os.remove(path)
        except OSError:
            pass
        raise ValueError(f"la huella de {label} no coincide con la publicada (archivo dañado o alterado); lo borré y no lo uso")
    J.log_terminal(f"Huella de {label} verificada.", "IA LOCAL")
    return True


def install_engine(progress=None, gpu=False):
    """Baja el motor llama.cpp para este sistema (12.7: o su versión con tarjeta gráfica). → ruta de llama-server."""
    exe = _exe_for("gpu" if gpu else "cpu")
    if exe:
        return exe
    releases = J._motor_get_json(motorlocal.RELEASES_API)
    rel = motorlocal.pick_release(releases, J.IS_WIN, gpu)
    if not rel:
        raise ValueError("no encontré el motor para este sistema en las versiones de llama.cpp")
    url, name, tag = rel
    dest = _dir("bin", "gpu") if gpu else _dir("bin")
    os.makedirs(dest, exist_ok=True)
    arc = J._motor_fetch(url, _dir(name), progress, "el motor con la tarjeta gráfica" if gpu else "el motor")
    verify_download(arc, motorlocal.asset_sha256(releases, name), "el motor")           # 12.11
    if arc.endswith(".zip"):
        with zipfile.ZipFile(arc) as z:
            z.extractall(dest)
    else:
        with tarfile.open(arc) as t:
            t.extractall(dest, filter="data")
    os.remove(arc)
    exe = motorlocal.find_exe(dest, J.IS_WIN, skip=() if gpu else ("gpu",))
    if not exe:
        raise ValueError("el archivo del motor no trae llama-server")
    if not J.IS_WIN:
        os.chmod(exe, 0o755)
    with open(os.path.join(dest, "version.txt"), "w", encoding="utf-8") as f:
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
        verify_download(dst, motorlocal.hf_sha256(info.get("siblings") or [], name), m["nombre"])     # 12.11
    J.settings["motor_model"] = os.path.basename(dst)
    try:
        J.save_settings_file()
    except OSError:
        pass
    return dst


def install_vision(progress=None):
    """12.8: los «ojos» de la IA integrada. Si tu modelo puede ver, baja solo su archivo de visión; si no, baja el modelo
    Qwen3 VL 4B (escribe tan bien como el otro y además ve) y lo deja como tu modelo. → nombre del modelo que ve."""
    _exe, model = J.motor_paths()
    m = motorlocal.entry_for_file(model)
    if not (m and m.get("vision")):
        m = motorlocal.by_id(motorlocal.VISION_ID)
        model = J.install_model(m["id"], progress)
    info = J._motor_get_json(motorlocal.hf_api(m["repo"]))
    name = motorlocal.pick_mmproj(info.get("siblings") or [])
    if not name:
        raise ValueError(f"{m['nombre']} no trae el archivo de visión")
    os.makedirs(_dir("vision"), exist_ok=True)
    dst = _dir("vision", os.path.basename(model))
    if not os.path.exists(dst):
        J._motor_fetch(motorlocal.hf_file(m["repo"], name), dst, progress, "la visión de " + m["nombre"])
        verify_download(dst, motorlocal.hf_sha256(info.get("siblings") or [], name), "la visión de " + m["nombre"])
    engine["no_mm"] = False
    return m["nombre"]


def vision_plan():
    """Qué haría «darle visión»: (texto para pedir permiso, GB a bajar)."""
    _exe, model = J.motor_paths()
    m = motorlocal.entry_for_file(model)
    if m and m.get("vision"):
        return f"Darle visión a la IA integrada ({m['nombre']}: unos {m['vision_gb']} GB)", m["vision_gb"]
    v = motorlocal.by_id(motorlocal.VISION_ID)
    return (f"Darle visión a la IA integrada: baja {v['nombre']} y su visión (unos {v['gb'] + v['vision_gb']:.1f} GB) y lo deja como tu "
            "modelo local"), v["gb"] + v["vision_gb"]


def motor_vision_job():
    if engine["job"]:
        return False
    engine["job"] = True

    def prog(label, frac):
        engine["msg"] = f"Descargando {label}: {int(frac * 100)} %"
        J.socketio.emit("motor", J.motor_status())

    def work():
        try:
            if not J.motor_ready():
                J.install_engine(prog)
            name = J.install_vision(prog)
            motor_stop()
            engine["msg"] = "Probando que vea…"
            ok = J.motor_start(240) and motor_sees()
            msg = (f"Lista: la IA integrada ya ve imágenes ({name}). Sin internet puedo revisar talleres en foto, leer la pizarra y "
                   "describir lo que subas." if ok else
                   "Bajé la visión, pero el motor no arrancó con ella (puede faltar memoria). Sigo usando la IA local solo para texto.")
        except Exception as e:
            msg = f"No pude darle visión a la IA integrada: {str(e)[:160]}"
        finally:
            engine["job"] = False
            engine["msg"] = ""
        J.notify(msg, "IA LOCAL")
        J.socketio.emit("motor", J.motor_status())
    J.start_job("Dándole visión a la IA integrada", work, "motor-vision")
    return True


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
            if (motorlocal.entry_for_file(path) or {}).get("vision"):     # 12.8: si el modelo puede ver, también sus ojos
                try:
                    J.install_vision(prog)
                except Exception as e:
                    J.log_terminal(f"No bajé la visión del modelo: {e}", "IA LOCAL")
            if J.IS_WIN:                               # 12.7: también la versión con tarjeta gráfica; se queda la más rápida
                try:
                    J.install_engine(prog, gpu=True)
                except Exception:
                    pass
            engine["msg"] = "Probando la velocidad…"
            speed = J.motor_pick_backend()
            ok = J.motor_start(180)
            if ok:
                r = J.motor_ask([{"role": "user", "content": "Responde en una frase: ¿cuánto es 7 por 8?"}], max_tokens=40)
                where = "con la tarjeta gráfica" if _backend() == "gpu" else "con el procesador"
                msg = (f"Lista la IA integrada ({os.path.splitext(os.path.basename(path))[0]}, {where}" + (f", unas {speed:.0f} palabras por segundo" if speed else "")
                       + f"). Respondió: «{r[:80]}». Si se cae el internet, la uso sola; no hace falta Ollama.")
            else:
                msg = "Descargué la IA integrada, pero no arrancó en este equipo (puede faltar memoria). Prueba un modelo más liviano en Ajustes › Inteligencia artificial."
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


def motor_pick_backend():
    """12.7: prueba la tarjeta gráfica y el procesador y deja el más rápido. → tokens por segundo del elegido."""
    res = {}
    for be in (["gpu", "cpu"] if _exe_for("gpu") else ["cpu"]):
        motor_stop()
        J.settings["motor_backend"] = be
        try:
            if J.motor_start(180) and _backend() == be:
                res[be] = J.motor_bench()
        except Exception:
            pass
    motor_stop()
    best = max(res, key=res.get) if res else "cpu"
    J.settings["motor_backend"] = best
    try:
        J.save_settings_file()
    except OSError:
        pass
    J.log_terminal("Velocidad de la IA integrada: " + ", ".join(f"{k} {v:.1f} tok/s" for k, v in res.items()) + f" → uso {best}.", "IA LOCAL")
    return res.get(best, 0.0)


def motor_ask(messages, max_tokens=400, json_mode=False):
    """Pregunta directa a la IA integrada (para la prueba y para el respaldo sin internet)."""
    J.motor_ensure()
    cfg = J._ai_cfg({"ai_provider": "motor"})
    return motorlocal.clean_reply(J.openai_chat(cfg, messages, json_mode, max_tokens))


def motor_status():
    exe, model = J.motor_paths()
    rec = J.motor_recommend()
    return {"motor": bool(exe), "modelo": os.path.basename(model) if model else "", "corriendo": _mt_alive(), "instalando": engine["job"],
            "gpu": _backend() == "gpu", "ve": motor_sees(),
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
    if act == "vision":
        if motor_sees():
            return {"ok": True, "msg": "La IA integrada ya ve imágenes.", **J.motor_status()}
        title, gb = vision_plan()
        J.request_approval("instalar", title, "Se baja una sola vez a la carpeta de Jarvis. Después, sin internet, puede revisar talleres en "
                           "foto, leer la pizarra y describir imágenes.", on_ok=J.motor_vision_job, on_no=lambda: None, ttl=1800,
                           say=f"¿Le doy visión a la IA integrada? Son unos {gb:.1f} gigas, una sola vez. Di «sí» o «no».")
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


_MOTOR_EYES = re.compile(r"\b(?:dale|darle|ponle|instala(?:le)?|activa(?:le)?)\s+(?:la\s+)?vision\s+(?:a\s+)?(?:la\s+)?(?:ia|inteligencia artificial)"
                         r"(?:\s+(?:local|integrada|sin internet))?\b|\bque la (?:ia|inteligencia artificial) (?:local|integrada|sin internet) (?:vea|pueda ver)\b")


def motor_voice(text, t):
    if _MOTOR_EYES.search(t):
        J.reply(J.handle_motor({"action": "vision"})["msg"], "IA LOCAL")
        return True
    if not _MOTOR_INST.search(t):
        return False
    if J.motor_ready():
        J.reply(f"La IA integrada ya está lista ({J.motor_name()}). Si se cae el internet, la uso sola.", "IA LOCAL")
        return True
    J.reply(J.handle_motor({"action": "instalar"})["msg"], "IA LOCAL")
    return True


def motor_start_services():
    threading.Thread(target=_idle_worker, daemon=True, name="motor-idle").start()
    if J.settings.get("ai_provider") == "motor" and J.motor_ready():      # 12.7: si es tu IA, queda lista desde que abre Jarvis
        threading.Thread(target=J.motor_start, daemon=True, name="motor-precarga").start()


_motor_get_json = _mt_get_json
_motor_fetch = _mt_fetch

__all__ = ['IDLE_STOP', '_exe_for', '_mt_alive', 'verify_download', '_MOTOR_EYES', '_MOTOR_INST', 'install_vision', 'motor_mmproj', 'motor_sees', 'motor_vision_job', 'vision_plan', '_motor_fetch', '_motor_get_json', 'engine', 'handle_motor', 'install_engine', 'install_model', 'motor_ask',
           'motor_bench', 'motor_ensure', 'motor_install_job', 'motor_pick_backend', 'motor_warmup', 'motor_name', 'motor_paths', 'motor_ready', 'motor_recommend', 'motor_start', 'motor_start_services',
           'motor_status', 'motor_stop', 'motor_voice', 'motorlocal']
