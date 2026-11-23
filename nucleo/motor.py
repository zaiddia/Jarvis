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

import frasesnl
import motorlocal
from nucleo import J

engine = {"proc": None, "last": 0.0, "busy": False, "job": False, "msg": "", "lock": threading.Lock(), "tune": None}
mini = {"proc": None, "last": 0.0, "lock": threading.Lock(), "fail": 0.0}      # 12.41: el cerebro mini (entiende órdenes)
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


def motor_draft():
    """12.41: el «adivinador» MTP del modelo en uso (motor/mtp/<modelo>.gguf), o "" si no tiene."""
    _exe, model = J.motor_paths()
    if not model:
        return ""
    p = _dir("mtp", os.path.basename(model))
    return p if os.path.exists(p) else ""


def _phys():
    return (J.psutil.cpu_count(logical=False) if J.psutil else None) or max(1, (os.cpu_count() or 4) // 2)


def _speed_opts():
    """12.41: núcleos, adivinador y memoria comprimida que usa el motor (los de la prueba de velocidad, o los guardados)."""
    c = engine.get("tune") or {"threads": J.settings.get("motor_threads", 0), "mtp": J.settings.get("motor_mtp_n", 0),
                               "kv": J.settings.get("motor_kv", "")}
    if engine.get("no_extra") and not engine.get("tune"):
        c = {"threads": c.get("threads", 0), "mtp": 0, "kv": ""}
    try:
        threads = int(c.get("threads") or 0) or _phys()
        n = int(c.get("mtp") or 0)
    except (TypeError, ValueError):
        threads, n = _phys(), 0
    kv = str(c.get("kv") or "") if str(c.get("kv") or "") in ("q8_0", "q4_0") else ""
    draft = motor_draft() if n else ""
    return threads, (n if draft else 0), draft, kv


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
            threads, n, draft, kv = _speed_opts()
            engine["proc"] = subprocess.Popen(motorlocal.server_args(exe, model, ctx=8192 if mm else 4096, threads=threads,
                                                                     threads_batch=max(threads, os.cpu_count() or threads), gpu=gpu,
                                                                     mmproj=mm, draft=draft, draft_n=n, kv=kv),
                                              cwd=os.path.dirname(exe), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                              creationflags=0x08000000 if J.IS_WIN else 0)
            engine["gpu"], engine["mm"], engine["extra"] = gpu, bool(mm), bool(n or kv)
            J.log_terminal(f"Enciendo la IA integrada ({motor_name()}{', con la tarjeta gráfica' if gpu else ''}{', con visión' if mm else ''})…",
                           "IA LOCAL")
        t0 = time.time()
        while time.time() - t0 < wait:
            if not _mt_alive():
                engine["proc"] = None
                if engine.get("extra") and not engine.get("tune"):   # 12.41: con el adivinador o la memoria comprimida no arrancó
                    J.log_terminal("La IA integrada no arrancó con los ajustes de velocidad; la enciendo con los normales.", "IA LOCAL")
                    engine["no_extra"], engine["extra"] = True, False
                    engine["lock"].release()
                    try:
                        return J.motor_start(wait)
                    finally:
                        engine["lock"].acquire()
                if engine.get("tune"):
                    return False                       # en la prueba de velocidad: esa combinación no sirve en este equipo
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


# ============================================================================ 12.41: EL CEREBRO MINI (ENTIENDE LAS ÓRDENES)
def mini_path():
    d = _dir("mini")
    fs = sorted(f for f in os.listdir(d) if f.lower().endswith(".gguf")) if os.path.isdir(d) else []
    return os.path.join(d, fs[0]) if fs else ""


def _mini_alive():
    p = mini["proc"]
    return p is not None and p.poll() is None


def _mini_health(timeout=1.0):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{motorlocal.MINI_PORT}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def mini_start(wait=60):
    """Enciende el cerebro mini (0.8B, contexto corto). → True si responde."""
    with mini["lock"]:
        mini["last"] = time.time()
        if _mini_alive() and _mini_health():
            return True
        exe = _exe_for(_backend()) or _exe_for("cpu")
        path = mini_path()
        if not (exe and path) or time.time() - mini["fail"] < 600:
            return False
        if not _mini_alive():
            gpu = _backend() == "gpu" and exe == _exe_for("gpu")
            mini["proc"] = subprocess.Popen(motorlocal.server_args(exe, path, port=motorlocal.MINI_PORT, ctx=4096,
                                                                   threads=max(1, _phys() // 2), gpu=gpu),
                                            cwd=os.path.dirname(exe), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                            creationflags=0x08000000 if J.IS_WIN else 0)
        t0 = time.time()
        while time.time() - t0 < wait:
            if not _mini_alive():
                mini["proc"], mini["fail"] = None, time.time()
                return False
            if _mini_health():
                return True
            time.sleep(0.3)
        return False


def mini_stop():
    p = mini["proc"]
    mini["proc"] = None
    if p is not None and p.poll() is None:
        try:
            p.terminate()
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


def mini_use(json_mode, image_path, max_tokens):
    """¿Esta pregunta la contesta el mini? Solo «entender una orden» (JSON corto, sin imagen) y si la prueba lo aprobó.
    J._tl.mini_force: «on»/«off» lo fuerza (lo usa la prueba de velocidad)."""
    force = getattr(J._tl, "mini_force", "")
    if force == "off" or image_path or not json_mode or (max_tokens or 999) > 300:
        return False
    if force != "on" and not J.settings.get("motor_mini"):
        return False
    return bool(mini_path())


def mini_chat(cfg, messages, json_mode, max_tokens):
    """Pregunta al mini. Lanza excepción si no está o no responde (quien llama sigue con la IA grande)."""
    if not mini_start():
        raise J.AIError("El cerebro mini no arrancó.", kind="net", why="el cerebro mini no arrancó")
    mini["last"] = time.time()
    c = dict(cfg, base=f"http://127.0.0.1:{motorlocal.MINI_PORT}/v1")
    return motorlocal.clean_reply(J.openai_chat(c, messages, json_mode, max_tokens))


def install_mini(progress=None):
    """Baja el cerebro mini (unos 0,6 GB) a motor/mini. → ruta."""
    m = motorlocal.by_id(motorlocal.MINI_ID)
    info = J._motor_get_json(motorlocal.hf_api(m["repo"]))
    sib = info.get("siblings") or []
    name = motorlocal.pick_gguf(sib, m["patron"])
    if not name:
        raise ValueError("no encontré el archivo del cerebro mini")
    os.makedirs(_dir("mini"), exist_ok=True)
    dst = _dir("mini", os.path.basename(name))
    if not os.path.exists(dst):
        J._motor_fetch(motorlocal.hf_file(m["repo"], name), dst, progress, "el cerebro mini")
        verify_download(dst, motorlocal.hf_sha256(sib, name), "el cerebro mini")
    return dst


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
            if _mini_alive() and time.time() - mini["last"] > IDLE_STOP and not engine["job"]:
                mini_stop()
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


def engine_date(gpu=False):
    """12.41: fecha de publicación del motor instalado (segunda línea de version.txt), o "" si no se sabe."""
    try:
        with open(os.path.join(_dir("bin", "gpu") if gpu else _dir("bin"), "version.txt"), encoding="utf-8") as f:
            lines = f.read().split()
        return lines[1] if len(lines) > 1 else ""
    except OSError:
        return ""


def engine_old():
    """¿Hay motor instalado pero anterior al que piden Qwen3.5, Gemma 4 y el adivinador MTP?"""
    return any(_exe_for(be) and motorlocal.engine_date_old(engine_date(be == "gpu")) for be in ("cpu", "gpu"))


def _clear_engine(dest, gpu):
    """Quita el motor viejo (la carpeta del de procesador guarda adentro la del de tarjeta gráfica: esa no se toca)."""
    if not os.path.isdir(dest):
        return
    for f in os.listdir(dest):
        if not gpu and f == "gpu":
            continue
        p = os.path.join(dest, f)
        try:
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        except OSError:
            pass


def install_engine(progress=None, gpu=False, update=False):
    """Baja el motor llama.cpp para este sistema (12.7: o su versión con tarjeta gráfica). → ruta de llama-server.
    12.41: update=True cambia un motor viejo por el más nuevo."""
    exe = _exe_for("gpu" if gpu else "cpu")
    if exe and not (update and motorlocal.engine_date_old(engine_date(gpu))):
        return exe
    releases = J._motor_get_json(motorlocal.RELEASES_API)
    rel = motorlocal.pick_release(releases, J.IS_WIN, gpu)
    if not rel:
        raise ValueError("no encontré el motor para este sistema en las versiones de llama.cpp")
    url, name, tag = rel
    date = next((str(r.get("published_at") or "")[:10] for r in releases or [] if r.get("tag_name") == tag), "")
    dest = _dir("bin", "gpu") if gpu else _dir("bin")
    if exe:
        motor_stop()
        mini_stop()
        _clear_engine(dest, gpu)
        J.log_terminal(f"Actualizo el motor de la IA integrada a {tag} (lo piden los modelos nuevos).", "IA LOCAL")
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
        f.write(f"{tag}\n{date}")
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
    if m.get("mtp"):                                   # 12.41: su adivinador (unos 100 MB) para la decodificación especulativa
        try:
            install_mtp(m, dst, info, progress)
        except Exception as e:
            J.log_terminal(f"No bajé el adivinador del modelo: {e}", "IA LOCAL")
    J.settings["motor_model"] = os.path.basename(dst)
    try:
        J.save_settings_file()
    except OSError:
        pass
    return dst


def install_mtp(m, model_path, info=None, progress=None):
    """12.41: baja el «adivinador» MTP del modelo a motor/mtp/<modelo>.gguf. → ruta o "" si el modelo no trae."""
    info = info or J._motor_get_json(motorlocal.hf_api(m["repo"]))
    sib = info.get("siblings") or []
    name = motorlocal.pick_mtp(sib)
    if not name:
        return ""
    os.makedirs(_dir("mtp"), exist_ok=True)
    dst = _dir("mtp", os.path.basename(model_path))
    if not os.path.exists(dst):
        J._motor_fetch(motorlocal.hf_file(m["repo"], name), dst, progress, "el adivinador de " + m["nombre"])
        verify_download(dst, motorlocal.hf_sha256(sib, name), "el adivinador de " + m["nombre"])
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
            J.install_engine(prog, update=True)        # 12.41: Gemma 4 pide un motor reciente (si ya lo es, no baja nada)
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
            m = motorlocal.by_id(mid) if mid else J.motor_recommend()
            J.install_engine(prog, update=bool(m and m.get("nuevo")))      # 12.41: los modelos de 2026 piden un motor reciente
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
            try:                                       # 12.41: y ajusta núcleos y adivinador a este equipo
                tuned = J.motor_tune_run(prog, with_mini=False)
                speed = tuned.get("tps") or speed
            except Exception as e:
                J.log_terminal(f"No pude ajustar la velocidad: {e}", "IA LOCAL")
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


# ============================================================================ 12.41: PRUEBA DE VELOCIDAD Y AJUSTE A TU PC
TUNE_PHRASES = 10


def _ram_gb():
    return J.psutil.virtual_memory().total / 1e9 if J.psutil else 8.0


def _mini_check(n=TUNE_PHRASES):
    """Pasa las mismas frases del banco por la IA grande y por el mini. → (bien_grande, bien_mini, s_grande, s_mini, n)."""
    import random
    rows = frasesnl.rows()
    rows = random.Random(41).sample(rows, min(n, len(rows)))
    out = {"off": [0, 0.0], "on": [0, 0.0]}
    for mode in ("off", "on"):
        old = getattr(J._tl, "mini_force", "")
        J._tl.mini_force = mode
        try:
            for nat, can, _alt in rows:
                t0 = time.time()
                try:                                   # directo a la IA integrada (sea cual sea tu IA de siempre)
                    msgs = [{"role": "user", "content": J.nl_prompt(nat, *J.nl_catalog(nat))}]
                    d = J.nl_parse(J._cloud_chat(J._ai_cfg({"ai_provider": "motor"}), msgs, True, max_tokens=220))
                except Exception:
                    d = {}
                out[mode][1] += time.time() - t0
                out[mode][0] += frasesnl.grade(d or {}, can, nat) == "bien"
        finally:
            J._tl.mini_force = old
    return out["off"][0], out["on"][0], out["off"][1], out["on"][1], len(rows)


def motor_tune_run(progress=None, with_mini=True):
    """Mide en ESTE equipo varias combinaciones (núcleos, adivinador MTP, memoria comprimida) y deja la más rápida.
    Con with_mini también prueba el cerebro mini para entender órdenes y lo deja solo si acierta casi igual y es más rápido.
    → {"tps", "base", "cfg", "mini", "texto"}."""
    if not J.motor_ready():
        raise ValueError("la IA integrada no está instalada")
    _exe, model = J.motor_paths()
    m = motorlocal.entry_for_file(model) or {}
    if m.get("nuevo") or m.get("mtp"):
        J.install_engine(progress, update=True)
    if m.get("mtp") and not motor_draft():
        try:
            install_mtp(m, model, None, progress)
        except Exception as e:
            J.log_terminal(f"No bajé el adivinador: {e}", "IA LOCAL")
    low = _ram_gb() <= 8.5
    cands = motorlocal.tune_candidates(_phys(), os.cpu_count() or _phys(), has_mtp=bool(motor_draft()), low_ram=low)
    results = []
    try:
        for i, c in enumerate(cands):
            engine["msg"] = f"Probando la velocidad ({i + 1} de {len(cands)})…"
            J.socketio.emit("motor", J.motor_status())
            motor_stop()
            engine["tune"] = c
            v = 0.0
            try:
                if J.motor_start(180):
                    J.motor_bench()                    # la primera vuelta calienta; cuenta la segunda
                    v = J.motor_bench()
            except Exception:
                v = 0.0
            results.append((c, v))
    finally:
        engine["tune"] = None
        motor_stop()
    best, tps = motorlocal.pick_best(results)
    base = results[0][1] if results else 0.0
    if best:
        J.settings.update(motor_threads=best["threads"], motor_mtp_n=best["mtp"], motor_kv=best["kv"])
        engine["no_extra"] = False
    J.log_terminal("Prueba de velocidad: " + "; ".join(f"{c['threads']} núcleos" + (f", adivina {c['mtp']}" if c["mtp"] else "")
                                                       + (", memoria comprimida" if c["kv"] else "") + f" → {v:.1f} tok/s"
                                                       for c, v in results), "IA LOCAL")
    parts = []
    if best:
        parts.append(f"{tps:.0f} palabras por segundo" + (f" (antes {base:.0f})" if base and tps > base * 1.05 else ""))
        if best["mtp"]:
            parts.append(f"con el adivinador ({best['mtp']} por paso)")
        if best["kv"]:
            parts.append("con la memoria comprimida")
        if best["threads"] != _phys():
            parts.append(f"{best['threads']} núcleos")
    mini_txt = ""
    if with_mini:
        try:
            engine["msg"] = "Probando el cerebro mini…"
            J.socketio.emit("motor", J.motor_status())
            install_mini(progress)
            J.motor_start(180)
            big, small, s_big, s_small, n = _mini_check()
            ok = n and small >= big - 1 and s_small < s_big * 0.8
            J.settings["motor_mini"] = bool(ok)
            mini_txt = (f"el cerebro mini entiende las órdenes ({small} de {n}, la grande {big}) en {s_small / max(1, n):.1f} s "
                        f"en vez de {s_big / max(1, n):.1f} s: queda encendido" if ok else
                        f"el cerebro mini no convenció ({small} de {n} contra {big} de {n}; {s_small / max(1, n):.1f} s contra "
                        f"{s_big / max(1, n):.1f} s): sigo con una sola IA")
            if not ok:
                mini_stop()
        except Exception as e:
            J.settings["motor_mini"] = False
            mini_txt = f"no pude probar el cerebro mini ({str(e)[:80]})"
    texto = "Ajusté la IA integrada a este equipo: " + (", ".join(parts) or "sin cambios") + (f". Además, {mini_txt}" if mini_txt else "") + "."
    J.settings["motor_tuned"] = texto[:300]
    try:
        J.save_settings_file()
    except OSError:
        pass
    return {"tps": tps, "base": base, "cfg": best, "mini": J.settings.get("motor_mini"), "texto": texto}


def motor_tune_job():
    if engine["job"]:
        return False
    engine["job"] = True

    def prog(label, frac):
        engine["msg"] = f"Descargando {label}: {int(frac * 100)} %"
        J.socketio.emit("motor", J.motor_status())

    def work():
        try:
            msg = J.motor_tune_run(prog)["texto"]
        except Exception as e:
            msg = f"No pude hacer la prueba de velocidad: {str(e)[:160]}"
        finally:
            engine["job"] = False
            engine["msg"] = ""
        J.notify(msg, "IA LOCAL")
        J.socketio.emit("motor", J.motor_status())
    J.start_job("Ajustando la velocidad de la IA integrada", work, "motor-ajuste")
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
            "gpu": _backend() == "gpu", "ve": motor_sees(),
            "mini": bool(J.settings.get("motor_mini") and mini_path()), "adivina": int(J.settings.get("motor_mtp_n") or 0),
            "ajuste": J.settings.get("motor_tuned", ""), "viejo": engine_old(),
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
    if act == "ajustar":                               # 12.41: prueba de velocidad (puede bajar el motor nuevo y el mini)
        if not J.motor_ready():
            return {"ok": False, "msg": "Primero instala la IA integrada.", **J.motor_status()}
        if engine["job"]:
            return {"ok": False, "msg": "Ya estoy trabajando en la IA integrada; espera a que termine.", **J.motor_status()}
        J.request_approval("instalar", "Probar y ajustar la velocidad de la IA integrada",
                           "Mide varias combinaciones en este equipo (unos minutos) y deja la más rápida. Puede bajar el motor nuevo "
                           "(unos 50 MB), el adivinador del modelo (unos 100 MB) y el cerebro mini (unos 0,6 GB).",
                           on_ok=J.motor_tune_job, on_no=lambda: None, ttl=1800,
                           say="¿Pruebo y ajusto la velocidad de la IA local? Tarda unos minutos y puede bajar hasta 0,8 gigas. Di «sí» o «no».")
        return {"ok": True, "msg": "Te pedí permiso en el HUD: di «sí» o apruébalo en la bandeja.", **J.motor_status()}
    if act == "apagar":
        motor_stop()
        mini_stop()
        return {"ok": True, "msg": "Apagué la IA integrada.", **J.motor_status()}
    if act == "encender":
        threading.Thread(target=J.motor_start, daemon=True).start()
        return {"ok": True, "msg": "Encendiendo la IA integrada…", **J.motor_status()}
    return {"ok": True, **J.motor_status()}


_MOTOR_INST = re.compile(r"\b(?:instala|descarga|prepara|baja)\s+(?:la\s+)?(?:ia|inteligencia artificial)\s+(?:integrada|de jarvis|interna|dentro de jarvis)\b|"
                         r"\b(?:ia|cerebro) (?:integrad[oa]|sin ollama)\b")


_MOTOR_EYES = re.compile(r"\b(?:dale|darle|ponle|instala(?:le)?|activa(?:le)?)\s+(?:la\s+)?vision\s+(?:a\s+)?(?:la\s+)?(?:ia|inteligencia artificial)"
                         r"(?:\s+(?:local|integrada|sin internet))?\b|\bque la (?:ia|inteligencia artificial) (?:local|integrada|sin internet) (?:vea|pueda ver)\b")


_MOTOR_TUNE = re.compile(r"\b(?:optimiza|optimizar|optimices|optimizes|optimice|acelera|acelerar|acelere|afina|afinar|afine|ajusta|ajustar|ajuste|"
                         r"mejora|mejorar|mejore|(?:mejore|ajuste|pruebe|mida) la velocidad de|hagame mas rapida|haga mas rapida|"
                         r"(?:mejora|mejorar|ajusta|ajustar|prueba|probar|mide|medir) la velocidad de|haz mas rapida|hazme mas rapida)\s+(?:a\s+)?"
                         r"(?:la\s+|tu\s+|mi\s+|el\s+|su\s+)?(?:ia|inteligencia artificial|modelo|motor)\s+(?:local|integrad[oa]|sin internet|de jarvis)\b|"
                         r"\b(?:optimiza|optimizar|optimices|optimice|acelera|acelerar|acelere)\s+(?:la\s+|tu\s+|su\s+)?(?:ia|inteligencia artificial)$|"
                         r"\bque la (?:ia|inteligencia artificial) (?:local|integrada) (?:sea|vaya|responda|conteste) mas rapid[oa]\b|"
                         r"\bhaz (?:la )?prueba de velocidad(?: de la (?:ia|inteligencia artificial)(?: local| integrada)?)?$")


def motor_voice(text, t):
    if _MOTOR_TUNE.search(t):
        J.reply(J.handle_motor({"action": "ajustar"})["msg"], "IA LOCAL")
        return True
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
           'motor_status', 'motor_stop', 'motor_voice', 'motorlocal', 'mini', 'motor_draft', 'mini_path', 'mini_start', 'mini_stop', 'mini_use',
           'mini_chat', 'install_mini', 'install_mtp', 'engine_date', 'engine_old', 'motor_tune_run', 'motor_tune_job', 'TUNE_PHRASES',
           '_MOTOR_TUNE', '_mini_check', '_speed_opts', '_phys', '_ram_gb', '_mini_alive', '_mini_health', '_clear_engine']
