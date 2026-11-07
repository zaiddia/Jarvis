"""12.5: qué IA está respondiendo (la de la nube o la de tu equipo) a la vista en el HUD y en Ajustes, y un diagnóstico
claro de lo que falta para funcionar sin internet (Ollama instalado, abierto, con un modelo; la voz Piper), con botones
para dejarlo listo (siempre con tu «sí»).

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import importlib
import importlib.util
import os
import re
import shutil
import subprocess
import threading
import time

from nucleo import J

_last = {"ai_now": None}


# ============================================================================ ¿QUIÉN RESPONDE?
def ai_now():
    """{"donde": "nube"|"local"|"ninguna", "texto", "proveedor", "modelo", "sin_internet", "respaldo"}."""
    try:
        cfg = J._ai_cfg()
    except Exception:
        return {"donde": "ninguna", "texto": "Sin IA", "proveedor": "", "modelo": "", "sin_internet": False, "respaldo": ""}
    off = bool(J.net.get("offline"))
    local = cfg["kind"] == "ollama" or bool(cfg["spec"].get("local"))
    ok = J.state.get("ai") in ("ok", "warn", "unknown", "")
    model = cfg.get("model") or ""
    if cfg.get("ai_provider") == "motor":              # 12.6: la IA integrada
        model = J.motor_name() if J.motor_ready() else ""
        donde, prov = ("local" if model else "ninguna"), "Jarvis local"
    elif local:
        donde = "local" if model else "ninguna"
        prov = "Ollama"
    else:
        donde = "nube" if (cfg.get("key") or cfg["spec"].get("custom")) and not off else "ninguna"
        prov = cfg.get("label") or cfg["spec"].get("short", "")
    if J.state.get("ai") == "error":
        donde = "ninguna" if not local else donde
    texto = {"nube": f"IA en la nube · {prov}", "local": f"IA de tu equipo · {model}", "ninguna": "Sin IA"}[donde]
    if donde == "ninguna" and off:
        texto = "Sin internet y sin IA local"
    elif donde == "ninguna" and J.state.get("ai") == "error":
        texto = f"{prov}: no responde"
    return {"donde": donde, "texto": texto, "proveedor": prov, "modelo": model, "sin_internet": off,
            "respaldo": J.net.get("local_model") or "", "estado": J.state.get("ai", ""), "ok": ok and donde != "ninguna"}


@J.socketio.on("ai_now")
def handle_ai_now(data=None):
    return J.ai_now()


def _ai_now_worker():
    while True:
        try:
            d = J.ai_now()
            if d != _last["ai_now"]:
                _last["ai_now"] = d
                J.socketio.emit("ai_now", d)
        except Exception:
            pass
        time.sleep(10)


# ============================================================================ ¿QUÉ FALTA PARA FUNCIONAR SIN INTERNET?
def _ollama_exe():
    if shutil.which("ollama"):
        return shutil.which("ollama")
    if J.IS_WIN:
        for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", "")):
            for rel in (("Programs", "Ollama", "ollama.exe"), ("Ollama", "ollama.exe")):
                p = os.path.join(base, *rel) if base else ""
                if p and os.path.isfile(p):
                    return p
    return ""


def offline_detail():
    """El diagnóstico de lo que hay para trabajar sin internet. → dict con cada pieza y el texto de qué falta."""
    lib = J.ollama is not None
    exe = J._ollama_exe()
    models = None
    if lib:
        try:
            models = [n for n in J.ai_list_models(J._ai_cfg({"ai_provider": "ollama"})) if "embed" not in n.lower()]
        except Exception:
            models = None
    running = models is not None
    model = J.local_ai_model(refresh=True) if running else ""
    motor_ok = J.motor_ready()                         # 12.6: la IA integrada no necesita Ollama
    piper_lib = bool(J.PIPER_INSTALLED)
    piper_voice = bool(J.find_piper_voice())
    if motor_ok:
        ia, ia_paso, model = f"IA integrada lista: {J.motor_name()} (no hace falta Ollama).", "", J.motor_name()
    elif model and not model.startswith("motor:"):
        ia = f"IA de tu equipo lista (Ollama): {model}."
        ia_paso = ""
    elif not lib:
        ia, ia_paso = "Falta el componente de Ollama en Jarvis.", "componente"
    elif running:
        ia, ia_paso = "Ollama está abierto pero no tiene ningún modelo descargado.", "modelo"
    elif exe:
        ia, ia_paso = "Ollama está instalado pero cerrado.", "abrir"
    else:
        ia, ia_paso = "Ollama no está instalado en este equipo.", "instalar"
    if piper_lib and piper_voice:
        voz, voz_paso = "Voz sin internet lista (Piper).", ""
    elif piper_lib:
        voz, voz_paso = "Piper está, pero falta descargar la voz en español.", "voz"
    else:
        voz, voz_paso = "Falta la voz sin internet (Piper).", "voz"
    if ia_paso:                                        # la forma más fácil: la IA integrada (sin instalar ni abrir Ollama)
        ia += " Lo más fácil: instalar la IA integrada de Jarvis."
    return {"offline": bool(J.net.get("offline")), "local_model": model, "motor": J.motor_status(), "piper": piper_lib and piper_voice,
            "ollama_lib": lib, "ollama_exe": bool(exe), "ollama_running": running, "modelos": (models or [])[:8],
            "ia": ia, "ia_paso": ia_paso, "voz": voz, "voz_paso": voz_paso, "frozen": bool(getattr(J.sys, "frozen", False)),
            "ahora": J.ai_now()}


# ============================================================================ DEJARLO LISTO (CON TU «SÍ»)
piper_job = {"busy": False}


def install_piper(voice="es"):
    """Instala Piper (si falta y se puede) y descarga la voz en español. → mensaje de error o ""."""
    if not J.PIPER_INSTALLED:
        if getattr(J.sys, "frozen", False):
            return "En la versión .exe la voz Piper no se puede instalar desde aquí; usa la versión de Python de Jarvis."
        r = subprocess.run([J._python_console(), "-m", "pip", "install", "-q", "piper-tts"], capture_output=True, text=True, timeout=1200,
                           creationflags=0x08000000 if J.IS_WIN else 0)
        if r.returncode != 0:
            return "No pude instalar Piper: " + (r.stderr or r.stdout or "")[-200:].strip()
        importlib.invalidate_caches()
        J.PIPER_INSTALLED = importlib.util.find_spec("piper") is not None
        if not J.PIPER_INSTALLED:
            return "Instalé Piper, pero hay que reiniciar Jarvis para usarlo."
    if not J.find_piper_voice():
        import descargar_voz
        rel, _desc = descargar_voz.VOCES.get(voice, descargar_voz.VOCES["es"])
        name = rel.split("/")[-1]
        dest = os.path.join(J.APP_DIR, "recursos", "piper")
        os.makedirs(dest, exist_ok=True)
        for ext in (".onnx", ".onnx.json"):
            path = os.path.join(dest, name + ext)
            if not (os.path.exists(path) and os.path.getsize(path) > 0):
                tmp = path + ".part"
                J._download(f"{descargar_voz.ROOT}/{rel}{ext}", tmp)
                os.replace(tmp, path)
    return ""


def _download(url, dst):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": f"Jarvis/{J.VERSION}"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)


def open_ollama():
    """Abre Ollama si está instalado y cerrado. → True si quedó respondiendo."""
    exe = J._ollama_exe()
    if not exe:
        return False
    app = os.path.join(os.path.dirname(exe), "ollama app.exe")
    try:
        if J.IS_WIN and os.path.isfile(app):
            subprocess.Popen([app], creationflags=0x08000000)
        else:
            subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=0x08000000 if J.IS_WIN else 0)
    except OSError:
        return False
    for _ in range(20):
        time.sleep(1)
        try:
            J.ai_list_models(J._ai_cfg({"ai_provider": "ollama"}))
            return True
        except Exception:
            continue
    return False


@J.socketio.on("offline_setup")
def handle_offline_setup(data=None):
    """Los botones de «Si se cae el internet»: what = "voz" | "instalar" | "abrir" | "modelo"."""
    what = str((data or {}).get("what") or "")
    if what == "voz":
        if piper_job["busy"]:
            return {"ok": True, "msg": "Ya estoy instalando la voz."}

        def go():
            piper_job["busy"] = True

            def work():
                try:
                    err = J.install_piper()
                except Exception as e:
                    err = f"No pude descargar la voz: {e}"
                finally:
                    piper_job["busy"] = False
                J.notify(err or "Lista la voz sin internet (Piper). Si se cae el internet, sigo hablando.", "VOZ")
            J.start_job("Instalando la voz sin internet", work, "piper")
        J.request_approval("instalar", "Instalar la voz sin internet (Piper, unos 60 MB)", "Baja Piper y la voz en español para hablar sin conexión.",
                           on_ok=go, on_no=lambda: None, ttl=1800, say="¿Instalo la voz sin internet? Son unos 60 MB. Di «sí» o «no».")
        return {"ok": True, "msg": "Te pedí permiso en el HUD: di «sí» o apruébalo en la bandeja."}
    if what == "abrir":
        def work():
            J.notify("Abrí Ollama: la IA sin internet ya responde." if J.open_ollama() else "No pude abrir Ollama; ábrelo tú desde el menú Inicio.",
                     "IA LOCAL")
        J.start_job("Abriendo Ollama", work, "ollama-abrir")
        return {"ok": True, "msg": "Abriendo Ollama…"}
    if what == "componente":
        def go():
            def work():
                try:
                    r = subprocess.run([J._python_console(), "-m", "pip", "install", "-q", "ollama"], capture_output=True, text=True, timeout=600,
                                       creationflags=0x08000000 if J.IS_WIN else 0)
                    importlib.invalidate_caches()
                    J.ollama = importlib.import_module("ollama") if r.returncode == 0 else J.ollama
                except Exception:
                    pass
                J.notify("Listo el componente de Ollama. " + J.offline_detail()["ia"] if J.ollama is not None else
                         "No pude instalar el componente de Ollama; ejecuta instalar.bat otra vez.", "IA LOCAL")
            J.start_job("Instalando el componente de Ollama", work, "ollama-lib")
        J.request_approval("instalar", "Instalar el componente de Ollama en Jarvis", "Es pequeño: deja a Jarvis hablar con Ollama.", on_ok=go,
                           on_no=lambda: None, ttl=1800, say="¿Instalo el componente de Ollama en Jarvis? Di «sí» o «no».")
        return {"ok": True, "msg": "Te pedí permiso en el HUD: di «sí» o apruébalo en la bandeja."}
    if what in ("instalar", "modelo"):
        J.submit_command("instala ollama" if what == "instalar" else "prepara la IA sin internet", "texto")
        return {"ok": True, "msg": "Te pedí permiso en el HUD: di «sí» o apruébalo en la bandeja."}
    return {"ok": False, "msg": "Acción desconocida."}


_AI_WHO = re.compile(r"\b(?:que|cual) (?:ia|inteligencia artificial|cerebro) (?:estas usando|usas|esta activa|esta respondiendo|tienes activa)\b|"
                     r"\b(?:estas|estas usando) (?:la ia|la inteligencia artificial) (?:de la nube|local)\b|\b(?:ia|cerebro) (?:local|de la nube) o (?:local|de la nube)\b")
_PIPER_INST = re.compile(r"\b(?:instala|descarga|baja)\s+(?:la\s+)?(?:voz sin internet|voz offline|voz piper|voz local)\b")


def ai_who_voice(text, t):
    if _PIPER_INST.search(t):
        J.reply(J.handle_offline_setup({"what": "voz"})["msg"], "VOZ")
        return True
    if not _AI_WHO.search(t):
        return False
    a, d = J.ai_now(), J.offline_detail()
    if a["donde"] == "nube":
        msg = f"Estoy usando la IA en la nube: {a['proveedor']}" + (f", modelo {a['modelo']}" if a["modelo"] else "") + ". "
    elif a["donde"] == "local":
        msg = f"Estoy usando la IA de tu equipo: {a['modelo']}" + (", porque no hay internet" if a["sin_internet"] else "") + ". "
    else:
        msg = a["texto"] + ". "
    msg += ("Si se cae el internet, sigo con " + d["local_model"] + "." if d["local_model"] else
            "Si se cae el internet no tengo IA de respaldo: " + d["ia"][:1].lower() + d["ia"][1:] + " En Ajustes › IA te dejo el botón para prepararla.")
    J.reply(msg, "IA")
    return True


def ai_state_start():
    threading.Thread(target=_ai_now_worker, daemon=True, name="ai-now").start()


__all__ = ['_AI_WHO', '_PIPER_INST', '_ai_now_worker', '_download', '_last', '_ollama_exe', 'ai_now', 'ai_state_start', 'ai_who_voice',
           'handle_ai_now', 'handle_offline_setup', 'install_piper', 'offline_detail', 'open_ollama', 'piper_job']
