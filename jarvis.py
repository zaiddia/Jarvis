"""
J.A.R.V.I.S. 3 — Asistente virtual local para Windows
------------------------------------------------------
HUD flotante, semitransparente y siempre visible (pywebview) · icono en la bandeja
STT offline (Vosk) · IA local (Ollama) o compatible OpenAI · TTS (Edge-TTS + Pygame)
Control del PC: abrir/cerrar aplicaciones, ventanas, web, multimedia, sistema (skills.py)

Atajos globales:  Ctrl+Alt+J  mostrar/ocultar HUD   ·   Ctrl+Alt+Espacio  hablar sin decir «Jarvis»

Uso:
    Jarvis.vbs                     -> inicia sin ninguna ventana de consola (recomendado)
    pythonw jarvis.py              -> igual que el anterior
    python jarvis.py --tray        -> inicia oculto en la bandeja
    python jarvis.py --browser     -> abre el HUD en el navegador en vez de en una ventana propia
Registro: %APPDATA%\\Jarvis\\jarvis.log   ·   Ajustes: %APPDATA%\\Jarvis\\config.json

Organización (7.1): este archivo tiene lo básico (rutas, ajustes, estado, el procesador de órdenes y el
arranque); cada área está en nucleo/ (voz, ia, escucha, ventanas, web, aula…). Esas partes usan los
nombres de aquí como J.<nombre>, así que todo sigue siendo un mismo programa.
"""

import os
import re
import sys
import json
import time
import uuid
import array
import hmac
import queue
import random
import socket
import asyncio
import tempfile
import platform
import threading
import datetime
import subprocess
import unicodedata
import webbrowser
import urllib.error
import urllib.parse
import urllib.request
from collections import deque

import nucleo  # noqa: E402  (las partes de Jarvis: nucleo/*.py)
nucleo.J = sys.modules[__name__]

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

VERSION = "10.5"
HOST = "127.0.0.1"
IS_WIN = os.name == "nt"
CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0
HUD_TITLE = "Jarvis HUD"


# =============================================================================
# RUTAS Y REGISTRO EN ARCHIVO (sin consola)
# =============================================================================
APP_DIR = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
           else os.path.dirname(os.path.abspath(__file__)))


def get_resource_path(relative_path):
    """Primero junto al programa (permite cambiar model_es o recursos sin recompilar),
    después dentro del paquete de PyInstaller (_MEIPASS)."""
    local = os.path.join(APP_DIR, relative_path)
    if os.path.exists(local):
        return local
    return os.path.join(getattr(sys, "_MEIPASS", APP_DIR), relative_path)


# Modo portable (USB): si existe un archivo llamado «portable» junto al programa, los ajustes,
# el registro y los documentos se guardan en la propia memoria y no en el PC donde se use.
PORTABLE = os.path.exists(os.path.join(APP_DIR, "portable")) or "--portable" in sys.argv


def _config_dir():
    if PORTABLE:
        return os.path.join(APP_DIR, "datos")
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "Jarvis")


CONFIG_DIR = _config_dir()
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
LOG_PATH = os.path.join(CONFIG_DIR, "jarvis.log")
STARTUP_VBS = os.path.join(os.environ.get("APPDATA", ""),
                           "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
                           "iniciar_jarvis.vbs")


def _setup_logfile():
    """Con pythonw o el .exe no hay consola: todo lo que se imprima va a jarvis.log."""
    if sys.stdout is not None and sys.stdout.isatty():
        return
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 2_000_000:
            os.replace(LOG_PATH, LOG_PATH + ".old")
    except OSError:
        pass
    f = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = f


_setup_logfile()

# Nota: no se activa faulthandler. En Windows imprime «Windows fatal exception» ante avisos
# internos que el sistema resuelve solo (p. ej. 0x8001010d de WebView2): falsas alarmas.


def _boot(msg):
    print(f"[{time.strftime('%H:%M:%S')}] [ARRANQUE] {msg}", flush=True)


_boot(f"Iniciando Jarvis {VERSION} · Python {sys.version.split()[0]} · {sys.executable}")


# =============================================================================
# PUERTO E INSTANCIA ÚNICA
# Antes, si el puerto 5000 estaba ocupado, Jarvis se cerraba en silencio. Ahora:
#  · el mismo Jarvis ya abierto  -> se muestra su panel y este se cierra (anotándolo);
#  · un Jarvis anterior o colgado (p. ej. una versión vieja que arranca con Windows)
#    -> se cierra y arranca este;
#  · otro programa usa el puerto -> se usa otro puerto libre.
# =============================================================================
def _port_busy(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, port)) == 0


def _http_text(url, timeout=1.5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read(200).decode("utf-8", "replace").strip()
    except Exception:
        return None


def _port_owner(port):
    try:
        import psutil
        for c in psutil.net_connections(kind="tcp"):
            if c.laddr and c.laddr.port == port and c.status == psutil.CONN_LISTEN and c.pid:
                return psutil.Process(c.pid)
    except Exception:
        pass
    return None


def _proc_is_jarvis(proc, allow_self=False):
    """¿Es un proceso de Jarvis? Estricto, para no tocar nunca otro programa: debe ser
    jarvis.exe, o un python/pythonw que esté ejecutando un archivo jarvis.py."""
    try:
        if not allow_self and os.getpid() == proc.pid:
            return False
        name = (proc.name() or "").lower()
        if name == "jarvis.exe":
            return True
        if not name.startswith("python"):
            return False
        return any(os.path.basename(a).lower() == "jarvis.py" for a in (proc.cmdline() or []))
    except Exception:
        return False


def _my_family():
    """PIDs de este mismo Jarvis: el proceso, su lanzador de .venv y sus hijos."""
    import psutil
    me = psutil.Process()
    fam = {me.pid}
    try:
        for p in me.parents():
            if not _proc_is_jarvis(p, allow_self=True):
                break
            fam.add(p.pid)
        fam.update(c.pid for c in me.children(recursive=True))
    except Exception:
        pass
    return fam


def _listening_ports(proc):
    try:
        import psutil
        return sorted({c.laddr.port for c in psutil.net_connections(kind="tcp")
                       if c.pid == proc.pid and c.status == psutil.CONN_LISTEN and c.laddr})
    except Exception:
        return []


def _close_other_jarvis():
    """Antes de arrancar: si hay otro Jarvis igual funcionando, se usa ese. Si hay uno
    viejo o colgado (aunque no tenga puerto: p. ej. atascado al arrancar), se cierra.
    Devuelve el puerto del Jarvis igual que ya funciona, o None."""
    try:
        import psutil
    except ImportError:
        return None
    fam = _my_family()
    others = [p for p in psutil.process_iter(["pid", "name"])
              if p.pid not in fam and _proc_is_jarvis(p)]
    # Un Jarvis con lanzador (.venv) son 2 procesos: se tratan juntos por el de abajo.
    pids = {p.pid for p in others}
    roots = []
    for p in others:
        try:
            if p.ppid() not in pids:
                roots.append(p)
        except Exception:
            roots.append(p)
    for root in roots:
        try:
            tree = [root] + root.children(recursive=True)
        except Exception:
            tree = [root]
        for proc in tree:
            for port in _listening_ports(proc):
                if _http_text(f"http://{HOST}:{port}/api/ping") == f"jarvis {VERSION}":
                    return port
        why = "otra versión" if any(_listening_ports(p) for p in tree) else "no respondía"
        _boot(f"Cierro otro Jarvis que seguía abierto ({why}, proceso {root.pid}).")
        _kill_proc(root)
    return None


def _kill_proc(proc):
    try:
        import psutil
        family = [proc] + proc.children(recursive=True)
        try:                                   # lanzador de .venv (pythonw.exe padre)
            parent = proc.parent()
            if parent and _proc_is_jarvis(parent) and parent.pid not in _my_family():
                family.append(parent)
        except Exception:
            pass
        for p in family:
            try:
                p.kill()
            except Exception:
                pass
        psutil.wait_procs(family, timeout=5)
    except Exception as e:
        _boot(f"No pude cerrar el proceso anterior: {e}")


SAME_JARVIS_RUNNING = False


def _resolve_port():
    global SAME_JARVIS_RUNNING
    if not _port_busy(5000):                 # puerto libre: arranque rápido, sin escanear procesos
        return 5000
    same = _close_other_jarvis()
    if same:
        SAME_JARVIS_RUNNING = True
        return same
    for port in [5000, *range(5057, 5070)]:
        if not _port_busy(port):
            return port
        ping = _http_text(f"http://{HOST}:{port}/api/ping")
        if ping == f"jarvis {VERSION}":
            SAME_JARVIS_RUNNING = True
            return port
        owner = _port_owner(port)
        if owner is not None and _proc_is_jarvis(owner):
            _boot(f"Cierro un Jarvis anterior que seguía abierto en el puerto {port} "
                  f"({ping or 'versión antigua o bloqueado'}, proceso {owner.pid}).")
            _kill_proc(owner)
            for _ in range(30):
                if not _port_busy(port):
                    return port
                time.sleep(0.2)
        elif owner is not None:
            try:
                name = owner.name()
            except Exception:
                name = "desconocido"
            _boot(f"El puerto {port} lo usa otro programa ({name}); pruebo otro.")
        elif _http_text(f"http://{HOST}:{port}/api/show") == "ok":
            _boot(f"Hay un Jarvis antiguo en el puerto {port} que no puedo cerrar. "
                  "Ciérralo desde el icono de la bandeja (Salir). Mientras, uso otro puerto.")
        else:
            _boot(f"El puerto {port} está ocupado; pruebo otro.")
    return 5000


def _wait_previous():
    """Tras actualizar o deshacer: espera a que el Jarvis anterior termine de cerrarse."""
    pid = os.environ.pop("JARVIS_WAIT_PID", "")
    if not pid.isdigit():
        return
    try:
        import psutil
        for _ in range(60):
            if not psutil.pid_exists(int(pid)):
                return
            time.sleep(0.25)
    except Exception:
        time.sleep(4)


_wait_previous()
PORT = _resolve_port()
URL = f"http://{HOST}:{PORT}"
import windows_shell  # noqa: E402
START_LINK = windows_shell.find_link(sys.argv)     # abierto desde el clic derecho, la lista de saltos o un enlace


def _forward_start_link():
    """Ya hay un Jarvis abierto: se le pasa el enlace con su código secreto y este se cierra al instante."""
    try:
        with open(os.path.join(CONFIG_DIR, "enlace.json"), encoding="utf-8") as f:
            d = json.load(f)
        req = urllib.request.Request(d["url"] + "/api/enlace", data=json.dumps({"url": START_LINK}).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "X-Jarvis-Token": d["token"]},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=4) as r:
            return bool(json.loads(r.read().decode("utf-8")).get("ok"))
    except Exception as e:
        _boot(f"No pude pasarle el enlace al Jarvis abierto: {e}")
        return False


if START_LINK and SAME_JARVIS_RUNNING and _forward_start_link():
    sys.exit(0)
if PORT != 5000:
    _boot(f"Uso el puerto {PORT}.")

import schedule
from flask import Flask, render_template, request, abort
from flask_socketio import SocketIO, emit

import skills
import mates
import aula
import notas
import revision
import rutinas
import calendario
import actualizar
import respaldo
import envivo
import oficina
import sismos
import perfil
import correo
import infodia
import buscar
import diario
import rapidez
import recuerdos
import aprobaciones
import banco
import seguimiento
import proactivo
import vigilante
import habilidades
import mcp_cliente
import errores
import horario
import formularios
import informes
import gmail
import exportar
import gservicios
import recuperacion
import diarioclase
import datos
import compromisos
import atencion
import lecciones
import paginas
import estilo
import ticket
import clasevivo
import secreto


# =============================================================================
# DEPENDENCIAS OPCIONALES (si falta alguna, el resto sigue funcionando)
# =============================================================================
def _optional_import(name):
    try:
        return __import__(name)
    except Exception:
        return None


pygame = _optional_import("pygame")
edge_tts = _optional_import("edge_tts")
import importlib.util
# Piper trae onnxruntime, que tarda en cargar: se importa solo cuando se usa, no al arrancar.
PiperVoice = SynthesisConfig = None
PIPER_INSTALLED = importlib.util.find_spec("piper") is not None


def _ensure_piper():
    global PiperVoice, SynthesisConfig
    if PiperVoice is None and PIPER_INSTALLED:
        try:
            from piper import PiperVoice as _PV
            from piper.config import SynthesisConfig as _SC
            PiperVoice, SynthesisConfig = _PV, _SC
        except Exception:
            pass
    return PiperVoice is not None
ollama = _optional_import("ollama")
pyaudio = _optional_import("pyaudio")
if pyaudio is None:                 # Python 3.14+: PyAudio no instala -> sounddevice
    try:
        import audio_compat as pyaudio
    except Exception:
        pyaudio = None
try:
    from vosk import Model, KaldiRecognizer, SetLogLevel
except Exception:
    Model = KaldiRecognizer = SetLogLevel = None
try:
    from docx import Document
except Exception:
    Document = None
try:
    import webview
except Exception:
    webview = None


# =============================================================================
# AJUSTES
# =============================================================================
SPANISH_VOICES = [
    ("es-ES-AlvaroNeural", "Álvaro · España · masculina"),
    ("es-ES-ElviraNeural", "Elvira · España · femenina"),
    ("es-ES-XimenaNeural", "Ximena · España · femenina"),
    ("es-CO-GonzaloNeural", "Gonzalo · Colombia · masculina"),
    ("es-CO-SalomeNeural", "Salomé · Colombia · femenina"),
    ("es-MX-JorgeNeural", "Jorge · México · masculina"),
    ("es-MX-DaliaNeural", "Dalia · México · femenina"),
    ("es-AR-TomasNeural", "Tomás · Argentina · masculina"),
    ("es-AR-ElenaNeural", "Elena · Argentina · femenina"),
    ("es-CL-LorenzoNeural", "Lorenzo · Chile · masculina"),
    ("es-CL-CatalinaNeural", "Catalina · Chile · femenina"),
    ("es-PE-AlexNeural", "Alex · Perú · masculina"),
    ("es-PE-CamilaNeural", "Camila · Perú · femenina"),
    ("es-VE-SebastianNeural", "Sebastián · Venezuela · masculina"),
    ("es-VE-PaolaNeural", "Paola · Venezuela · femenina"),
    ("es-US-AlonsoNeural", "Alonso · EE. UU. · masculina"),
    ("es-US-PalomaNeural", "Paloma · EE. UU. · femenina"),
]

THEMES = {
    "cyan": ("Cian reactor", (46, 230, 255)),
    "ambar": ("Ámbar", (255, 181, 71)),
    "rojo": ("Rojo Mark III", (255, 77, 94)),
    "verde": ("Verde terminal", (61, 255, 154)),
    "violeta": ("Violeta", (180, 140, 255)),
    "azul": ("Azul profundo", (79, 157, 255)),
    "magenta": ("Magenta", (255, 92, 200)),
    "hielo": ("Blanco frío", (169, 221, 255)),
}

HUD_SIZES = {"orbe": (96, 96), "compacto": (430, 150), "expandido": (440, 620)}
# 9.1: el HUD expandido puede ser más ancho, para ver el panel «Hoy» al lado de la conversación
HUD_EXPANDED = {"estrecho": (440, 620), "amplio": (940, 680), "grande": (1200, 800)}
HUD_POSITIONS = {
    "inf-der": "Abajo a la derecha", "sup-der": "Arriba a la derecha",
    "inf-izq": "Abajo a la izquierda", "sup-izq": "Arriba a la izquierda",
    "libre": "Donde lo deje (arrastrando)",
}

DEFAULT_SYSTEM_PROMPT = (
    "Eres Jarvis, el asistente personal de confianza del usuario. Hablas español con "
    "naturalidad y calidez, como un asistente atento y con clase, nunca como un robot ni "
    "como un manual. Tuteas al usuario salvo que él te pida otra cosa.\n"
    "Tus respuestas se ESCUCHAN en voz alta, así que suenan a conversación hablada, no a "
    "texto escrito: frases cortas, lenguaje sencillo y directo. Nada de markdown, viñetas, "
    "asteriscos, emojis ni leer URLs o rutas largas.\n"
    "Ve al grano. Para la mayoría de cosas, una o dos frases bastan; solo te extiendes si "
    "te piden una explicación. Si algo es muy largo, das lo esencial y ofreces ampliar.\n"
    "Eres cálido pero sobrio: puedes tener un toque de humor fino si encaja, sin exagerar. "
    "Si no sabes algo o no estás seguro, lo dices con naturalidad en vez de inventar. Si una "
    "petición es ambigua, haces una sola pregunta breve para aclararla.\n"
    "Recuerda el contexto de la conversación y responde como quien sigue el hilo, no como "
    "quien empieza de cero cada vez."
)

# Regla fija (no editable en Ajustes): evita que la IA diga que hizo algo que no hizo.
ACTION_RULE = (
    " " +
    "En esta conversación tú NO ejecutas acciones: las acciones del PC (abrir programas, enviar "
    "mensajes, poner música...) las hace otro sistema. Nunca digas que enviaste, abriste o hiciste "
    "algo; si te lo piden, di que no pudiste hacerlo y sugiere decirlo como orden, por ejemplo "
    "«manda un WhatsApp a Andrea diciendo...»."
)

# =============================================================================
# PROVEEDORES DE IA
#   kind   cómo se habla con él: "ollama", "gemini", "anthropic" o "openai" (API compatible)
#   base   URL de la API · model  modelo por defecto
#   prefer patrones para elegir el mejor modelo de tu cuenta si el guardado no sirve
#   vision puede analizar capturas · no_temp  rechaza el parámetro «temperature»
# =============================================================================
PROVIDERS = {
    "ollama": dict(label="Ollama (en tu equipo, sin internet)", short="Ollama", kind="ollama",
                   group="local"),
    "openai": dict(label="Personalizado (LM Studio u otro compatible con OpenAI)",
                   short="API personalizada", kind="openai", group="local", custom=True),
    "gemini": dict(label="Google Gemini", short="Gemini", kind="gemini", group="cloud",
                   model="gemini-3.5-flash-lite", vision=True,
                   prefer=[r"^gemini-[\d.]+-flash-lite$", r"^gemini-[\d.]+-flash$", r"^gemini-[\d.]+-flash"],
                   key_url="https://aistudio.google.com/apikey", key_hint="AIza…",
                   note="Tiene nivel gratuito. Conversación natural y puede ver la pantalla."),
    "anthropic": dict(label="Claude (Anthropic)", short="Claude", kind="anthropic", group="cloud",
                      base="https://api.anthropic.com/v1", model="claude-haiku-5-5", vision=True,
                      no_temp=True, prefer=[r"^claude-haiku", r"^claude-sonnet", r"^claude"],
                      key_url="https://console.anthropic.com/settings/keys", key_hint="sk-ant-…",
                      note="Muy natural en español y puede ver la pantalla. Pago por uso."),
    "chatgpt": dict(label="ChatGPT (OpenAI)", short="ChatGPT", kind="openai", group="cloud",
                    base="https://api.openai.com/v1", model="", vision=True, no_temp=True,
                    tokens_param="max_completion_tokens",
                    prefer=[r"^gpt-[\d.]+-mini$", r"^gpt-[\d.]+-nano$", r"^gpt-[\d.]+$"],
                    key_url="https://platform.openai.com/api-keys", key_hint="sk-…",
                    note="Pago por uso. Puede ver la pantalla."),
    "deepseek": dict(label="DeepSeek", short="DeepSeek", kind="openai", group="cloud",
                     base="https://api.deepseek.com", model="deepseek-flash",
                     prefer=[r"flash", r"chat", r"deepseek"],
                     key_url="https://platform.deepseek.com/api_keys", key_hint="sk-…",
                     note="Muy económico. No puede ver la pantalla."),
    "kimi": dict(label="Kimi (Moonshot AI)", short="Kimi", kind="openai", group="cloud",
                 base="https://api.moonshot.ai/v1", model="kimi-k3", no_temp=True,
                 prefer=[r"^kimi-k\d+(\.\d+)?$", r"^kimi", r"moonshot"],
                 key_url="https://platform.moonshot.ai/console/api-keys", key_hint="sk-…",
                 note="Si tu cuenta de Moonshot es de China, usa «Personalizado» con https://api.moonshot.cn/v1."),
    "xai": dict(label="Grok (xAI)", short="Grok", kind="openai", group="cloud",
                base="https://api.x.ai/v1", model="", prefer=[r"^grok.*fast", r"^grok"],
                key_url="https://console.x.ai", key_hint="xai-…", note="Pago por uso."),
    "mistral": dict(label="Mistral AI", short="Mistral", kind="openai", group="cloud",
                    base="https://api.mistral.ai/v1", model="mistral-small-latest",
                    prefer=[r"^mistral-small-latest$", r"-small-latest$", r"-latest$"],
                    key_url="https://console.mistral.ai/api-keys", key_hint="",
                    note="Empresa europea."),
    "groq": dict(label="Groq", short="Groq", kind="openai", group="cloud",
                 base="https://api.groq.com/openai/v1", model="",
                 prefer=[r"llama.*versatile", r"llama", r"gpt-oss", r"qwen"],
                 key_url="https://console.groq.com/keys", key_hint="gsk_…",
                 note="Respuestas muy rápidas con modelos abiertos."),
    "openrouter": dict(label="OpenRouter (cientos de modelos)", short="OpenRouter", kind="openai",
                       group="cloud", base="https://openrouter.ai/api/v1", model="openrouter/auto",
                       prefer=[r"^openrouter/auto$"],
                       key_url="https://openrouter.ai/keys", key_hint="sk-or-…",
                       note="Una sola clave para modelos de muchas marcas (Claude, GPT, Llama, DeepSeek…)."),
}
# Modelos de la lista que no sirven para conversar (imagen, audio, embeddings...)
MODEL_EXCLUDE = re.compile(r"embed|whisper|tts|audio|realtime|transcri|image|imagen|dall-e|"
                           r"moderation|search|guard|rerank|ocr|computer-use|live|robotics|"
                           r"nano-banana|omni|veo|lyria|orpheus|playai|codex", re.I)

# Regla fija: la IA sabe que lo que le llega por voz puede venir con errores de reconocimiento.
VOICE_RULE = (
    " Lo que dice el usuario te llega por reconocimiento de voz y puede traer errores: palabras "
    "parecidas, nombres mal escritos o frases cortadas (por ejemplo «guasa» o «wasap» es WhatsApp). "
    "Interpreta la intención más probable según el contexto. Solo si de verdad no se entiende, "
    "pide en una frase corta que lo repita."
)

DEFAULT_SETTINGS = {
    # General / HUD
    "theme": "cyan",
    "hud_start_size": "compacto",
    "hud_position": "inf-der",
    "hud_x": -1,
    "hud_y": -1,
    "hud_opacity": 82,
    "hud_dim_idle": True,
    "hud_on_top": True,
    "hud_transparent": True,       # False = fondo sólido (si la transparencia falla en ese equipo)
    "hud_hide_taskbar": True,
    "hud_start_hidden": False,     # arrancar en «modo sigilo»: oculto, escuchando
    "startup_announce": True,      # confirmar por voz que el núcleo se cargó
    "output_dir": (os.path.join(APP_DIR, "Documentos Jarvis") if PORTABLE
                   else os.path.join(os.path.expanduser("~"), "Documents", "Jarvis")),
    "talleres_dir": "",            # carpeta de formularios/talleres HTML (vacío = Documentos\\Jarvis\\Talleres)
    # Voz
    "tts_enabled": True,
    "tts_backend": "edge",         # "edge" (online), "piper" (offline) o "gemini" (muy natural, con tu clave)
    "gemini_tts_voice": "Charon",
    "gemini_tts_model": "gemini-3.8-flash-lite-tts",
    "gemini_tts_style": "natural, cálido y conversacional, a buen ritmo",
    "tts_voice": "es-ES-AlvaroNeural",
    "piper_voice": "",             # ruta a un modelo .onnx de Piper (vacío = busca en recursos\\piper)
    "tts_rate": 0,
    "tts_volume": 0,
    "tts_pitch": 0,
    # Escucha
    "mic_enabled": True,
    "mic_device": -1,
    "wake_word_enabled": True,
    "wake_words": "jarvis, yarvis, harvis, charvis, yarbis, asistente",
    "wake_window": 10,
    "followup_listen": 6,
    "listen_mode": "auto",         # "auto" (en vivo si hay clave de Gemini), "vivo" o "clasico"
    "live_model": "gemini-3.8-live",
    "live_idle": 15,               # segundos de silencio para cerrar la conversación en vivo
    "live_search": True,           # en vivo puede buscar en Google datos actuales
    "live_barge_level": 30,
    "live_provider": "gemini",     # "gemini" (gratis), "openai" (ChatGPT, de pago) o "deepgram" (con crédito)
    "live_fallback": True,         # si el elegido falla, probar los otros que tengan clave
    "openai_live_model": "gpt-realtime",
    "openai_live_voice": "marin",
    "deepgram_api_key": "",
    "deepgram_voice": "aura-2-celeste-es",
    "deepgram_think_model": "gpt-4o-mini",        # volumen de tu voz para interrumpirlo mientras habla (en vivo)          # segundos que sigue escuchando tras responder (0 = siempre decir «Jarvis»)
    "barge_in": True,              # poder interrumpirlo mientras habla («Jarvis, para» o una pregunta nueva)
    "mic_sensitivity": 0,          # 0 = no filtra (recomendado); subirlo ignora sonidos lejanos/flojos
    "require_hotkey": False,       # solo escuchar tras pulsar Ctrl+Alt+Espacio (anti ambiente total)
    "min_command_chars": 2,        # descarta transcripciones demasiado cortas (ruidos sueltos)
    "stt_backend": "vosk",         # "vosk" (ligero) o "whisper" (más preciso, más pesado)
    "whisper_model": "base",       # tiny / base / small
    "stt_refine": "auto",          # 2ª etapa para las frases dirigidas a Jarvis: auto | gemini | whisper | off
    # IA
    "ai_provider": "ollama",       # cualquiera de PROVIDERS
    "ollama_host": "http://127.0.0.1:11434",
    "ollama_model": "llama3.2",
    "offline_auto": True,          # sin internet: usar la IA de tu equipo (Ollama) y la voz Piper
    "offline_model": "",
    "update_repo": "zaiddia/Jarvis",  # repositorio de GitHub con las versiones (usuario/nombre)
    "update_auto": True,           # mirar una vez al día si hay versión nueva (solo avisa)
    "github_api_key": "",          # solo para repositorios privados
    "backup_auto": True,           # copia de seguridad automática cada semana
    "backup_dir": "",              # carpeta de copias ("" = Documentos\\Jarvis\\Respaldos)
    "backup_secrets": False,       # incluir las claves de API en las copias           # modelo de Ollama para ese caso ("" = el que tengas instalado)
    "openai_base_url": "http://127.0.0.1:1234/v1",
    "openai_model": "",
    "openai_api_key": "",
    "gemini_api_key": "",
    "gemini_model": PROVIDERS["gemini"]["model"],
    "ai_temperature": 0.7,
    "history_turns": 6,
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "steam_use_ai": True,
    # Control del PC
    "ai_router": True,
    "custom_commands": "",
    # Integraciones
    "notes_notice_min": 30,        # aviso N minutos antes de una nota con hora (0 = solo a la hora)
    "notes_ai_context": True,      # la IA conoce tus notas para contestar «¿cuándo era…?»
    "calendar_urls": "",           # enlaces iCal (secretos) de tus calendarios, uno por línea
    "calendar_notice_min": 10,     # aviso antes de cada evento con hora (0 = sin aviso)
    "aula_docente": "",            # encabezado del material de clase
    "aula_institucion": "",
    "aula_open_docs": True,        # abrir el Word al terminar de generarlo
    "aula_auto_open": True,        # abrir el tablero del aula al sortear, hacer grupos...
    "camera_index": 0,             # cámara para revisar trabajos (0 = la integrada)
    "copilot_enabled": False,      # copiloto: mira la pantalla y sugiere mientras trabajas
    "copilot_interval": 5,         # minutos entre miradas
    "copilot_speak": False,        # decir las sugerencias en voz alta (si no, solo en el HUD)
    "copilot_context": "",         # en qué trabajas (ayuda a que las sugerencias sean útiles)
    "vision_model": "moondream",   # modelo de visión de Ollama (moondream, llava, llama3.2-vision)
    "contacts": "",                # agenda: "Juan = +573001112233" (una por línea)
    "telegram_token": "",          # token del bot de Telegram (@BotFather)
    "telegram_chat": "",           # chat id a donde enviar (y el único que puede darle órdenes)
    "telegram_remote": False,      # recibir órdenes desde Telegram (solo de ese chat)
    "telegram_alerts": True,       # enviar recordatorios, avisos del calendario y temporizadores al celular
    "weather_city": "",            # ciudad para el clima («Bogotá», «Medellín»…)
    "morning_weather": True,       # clima en el reporte de la mañana
    "morning_news": False,         # noticias en el reporte de la mañana
    "news_feeds": "",              # direcciones RSS (una por línea); vacío = Google Noticias Colombia y BBC Mundo
    "quake_alerts": False,         # avisar de sismos (datos del USGS, gratis)
    "quake_min_mag": 4.5,          # magnitud mínima para el aviso suave
    "address_name": "",            # cómo quieres que Jarvis te trate ("profe", tu nombre…)
    "email_address": "",           # tu Gmail para enviar correos por voz
    "email_app_password": "",      # contraseña de aplicación (16 letras), no tu clave normal
    "email_sender_name": "",       # con qué nombre firmas los correos
    "email_book": "",              # agenda de correos: "Coordinadora = ana@colegio.edu.co" (una por línea)
    "spotify_client_id": "",       # opcional: para reproducir por nombre con la API
    "spotify_client_secret": "",
    # 7.0: Jarvis habla primero (con criterio)
    "proactive_enabled": True,     # avisos proactivos (pausas, batería, lluvia, saludo, ofrecer rutinas)
    "proactive_quiet": "21:30-06:30",   # horas en las que nunca habla por su cuenta
    "proactive_max": 12,           # como mucho tantos avisos al día
    "proactive_breaks": True,      # recordar pausas
    "proactive_break_min": 120,    # tras cuántos minutos seguidos en el equipo
    "proactive_battery": True,     # batería baja sin cargador
    "proactive_rain": True,        # lluvia a la hora de salida
    "proactive_greeting": True,    # saludo del primer uso del día
    "proactive_offer_routines": True,   # «¿activo el modo clase?» antes de un evento del calendario
    "leave_time": "",              # hora a la que sueles salir («12:30»), para avisar de lluvia
    # 7.0: diario, tarjetas, conectores, panel del celular
    "diary_enabled": True,         # anotar lo que haces con Jarvis («¿qué hice ayer?»)
    "diary_days": 30,              # cuántos días guardar
    "hud_cards": True,             # tarjetas holográficas en el HUD
    "onboarding_done": False,      # 7.1: ya vio la bienvenida (la primera vez se abre sola)
    "windows_integration": False,  # 7.2: clic derecho, Win+R «jarvis», enlaces jarvis:// y lista de saltos
    "windows_toasts": True,        # 7.2: los avisos también como notificación de Windows
    "learn_enabled": True,         # 7.4: aprende tus costumbres y propone rutinas
    "history_enabled": True,       # 7.4: historial de conversaciones buscable («¿qué te dije sobre…?»)
    "history_days": 180,           # cuántos días guardarlo
    "memory_semantic": True,       # buscar también por significado (con Gemini u Ollama, si los tienes)
    "tool_select": True,           # 7.5: la IA solo ve las herramientas que tienen que ver con la orden
    "tool_select_max": 20,         # cuántos conectores como mucho (las acciones propias van siempre)
    "approvals_telegram": True,    # 7.6: las aprobaciones también llegan a Telegram (si está conectado)
    "project_parallel": 3,         # 7.6: cuántos sub-agentes trabajan a la vez en un proyecto
    "email_read": True,            # 7.7: leer tu bandeja (IMAP) cuando se lo pides
    "email_days": 3,               # cuántos días de correos revisa
    "calendar_create": "google",   # 7.7: dónde crear los eventos: "google" (abre Google Calendar) o "ics" (Outlook/Calendario)
    "classroom_client_id": "",     # 7.8: Google Classroom (ID de cliente OAuth «App de escritorio»)
    "classroom_client_secret": "",
    "classroom_refresh": "",       # el permiso que guarda Jarvis al conectar (no tu contraseña)
    "risk_grade": 3.0,             # 7.8: promedio por debajo del cual un estudiante está en riesgo
    "risk_absences": 3,            # fallas a partir de las cuales avisa
    "risk_alerts": True,           # resumen de estudiantes en riesgo los viernes por la tarde
    "memory_proactive": True,      # 7.8: la IA recuerda sola lo relacionado que le contaste antes
    "telegram_voice_reply": True,  # 7.9: a una nota de voz por Telegram, responder también con voz
    "whatsapp_phone": "",          # 7.9: avisos al WhatsApp (CallMeBot): tu número con +57
    "whatsapp_apikey": "",
    "whatsapp_alerts": True,
    "image_model": "",             # 7.9: modelo de imágenes de Gemini (vacío = el que tenga tu cuenta)
    "sync_folder": "",             # 7.9: carpeta compartida (OneDrive…) para usar Jarvis en varios equipos
    "encrypt_secrets": True,       # 8.0: claves cifradas con la protección de Windows (no en modo USB)
    "checked_version": "",         # 8.0: versión con la que ya se hizo la revisión tras actualizar
    "schedule_auto_course": True,  # 8.1: el curso activo del aula sigue tu horario
    "schedule_warn": False,        # 8.1: avisarme 5 minutos antes de cada clase
    "weekly_summary": True,        # 8.3: resumen de la semana al celular
    "weekly_day": "viernes",
    "weekly_hour": 16,
    "weekly_sent": "",
    "update_night": True,          # 8.3: instalar de noche las versiones nuevas (con copia de seguridad)
    "google_scopes": "",           # 8.5: permisos que diste al conectar tu cuenta de Google (Gmail, Classroom, Forms)
    "hud_subtitles": True,         # 8.6: subtítulos de lo que dice Jarvis, palabra por palabra
    "hud_expanded": "amplio",      # 9.1: tamaño del HUD expandido (estrecho, amplio o grande)
    "hud_favorites": "",           # 9.2: órdenes favoritas (una por línea), como botones en el HUD
    "drive_auto": False,           # 8.7: subir a tu Drive cada material que Jarvis cree
    "drive_folder_id": "",
    "zeti_since": "",              # 8.7: notas desde esta fecha (AAAA-MM-DD), p. ej. el inicio del periodo
    "zeti_order": "lista",         # «lista» (como está el curso en Jarvis), «apellido» o «alfabetico» (ya escritos Apellidos Nombres)
    "zeti_weights": "35,30,30,5",  # 10.1: Conocer, Hacer, Ser y Autoevaluación (%)
    "zeti_url": "https://www.zeti.co/calificaciones/",
    "scale_superior": 4.5,         # 10.1: escala de desempeño de la institución
    "scale_alto": 4.0,
    "scale_basico": 3.0,
    "subjects": "Matemáticas: Matemáticas, Aritmética, Álgebra, Geometría, Estadística, Trigonometría, Cálculo\nTecnología e Informática: Tecnología e Informática, Tecnología, Informática, Sistemas",  # 10.4: tus áreas y asignaturas
    "course_subjects": "",         # 10.4: «7A: Matemáticas, Tecnología e Informática» (si no, se toma del horario)
    "subject_current": "",         # 10.4: la asignatura escogida («estamos en tecnología»)
    "period_current": 1,           # 10.2: periodo en curso (para el acumulado del año)
    "zeti_period_weights": "34,33,33",  # 10.2: peso de cada periodo en el año (%)
    "zeti_comma": True,            # definitivas con coma decimal (4,5)
    "recovery_days": 10,           # 8.8: plazo de los planes de recuperación
    "live_quiz_secs": 30,          # 8.8: segundos por pregunta en el quiz en vivo
    "protect_students": False,     # 8.9: cifrar notas, observador, cursos y diario de clase
    "data_key": "",                # 8.9: clave de esos datos (se guarda cifrada con la protección de Windows)
    "backup_drive": True,          # 8.9: cada copia de seguridad también a tu Drive (si conectaste Google)
    "drive_backup_folder_id": "",
    "drive_backup_keep": 10,
    "attention_pulse": True,       # 9.3: cada hora, avisar solo de lo nuevo que necesita tu atención
    "attention_from": 7,
    "attention_to": 19,
    "attention_weekend": False,
    "attention_phone": False,      # …y mandarlo también al celular
    "lessons_learn": True,         # 9.4: proponer lecciones cuando corriges a Jarvis
    "watch_hours": 6,              # 9.4: cada cuántas horas revisar las páginas vigiladas
    "morning_voice_note": True,    # 9.5: el reporte de la mañana también como nota de voz en Telegram
    "style_learn": True,           # 9.5: aprender tu forma de escribir de lo que envías con Jarvis
    "early_alerts": True,          # 9.7: alertas tempranas (quién viene bajando o faltando) y celebraciones
    "early_last": "",              # 9.7: último día en que avisó de las tendencias
    "week_prep": True,             # 9.8: el domingo propone preparar la semana (planes y evaluaciones por curso)
    "week_prep_hour": 17,          # 9.8: a partir de qué hora del domingo
    "week_prep_quiz": True,        # 9.8: incluir una evaluación corta por curso
    "week_prep_last": "",
    "period_end": "",              # 9.8: fecha de cierre del periodo (AAAA-MM-DD)
    "period_name": "",             # 9.8: p. ej. «Periodo 3»
    "period_closed": "",
    "period_warned": "",
    "inbox_drafts": True,          # 9.8: en la mañana redacta las respuestas de los correos que lo piden (por aprobar)
    "inbox_hour": 6,               # 9.8: desde qué hora de la mañana
    "inbox_max": 5,                # 9.8: máximo de respuestas por mañana
    "inbox_last": "",
    "persona_auto": True,          # 9.9: personalidad según el momento (breve en clase, concentrado, relajado)
    "orb_day_color": True,         # 9.9: el reactor cambia de color según cómo viene el día
    "retro_year": "",              # 9.9: año en que ya propuso la retrospectiva
    "mcp_servers": "",             # conectores MCP (JSON con el formato de Claude Desktop)
    "mcp_trusted": "",             # conectores que no piden confirmación (nombres separados por comas)
    "mcp_server_enabled": False,   # dejar que otras IA (Claude Desktop…) usen Jarvis por MCP
    "mobile_enabled": False,       # panel en el celular por la wifi de casa
    "mobile_port": 5055,
    "mobile_token": "",            # código secreto del panel (se genera solo)
    # Rutinas
    "morning_enabled": True,
    "morning_time": "07:30",
    "alarm_sound": "",           # vacío = automático (recursos\\sirena.mp3)
}
# Clave y modelo de cada proveedor en la nube: «deepseek_api_key», «deepseek_model»...
for _pid, _sp in PROVIDERS.items():
    if _sp["group"] == "cloud":
        DEFAULT_SETTINGS.setdefault(f"{_pid}_api_key", "")
        DEFAULT_SETTINGS.setdefault(f"{_pid}_model", _sp.get("model", ""))
API_KEY_FIELDS = tuple(k for k in DEFAULT_SETTINGS if k.endswith("_api_key"))
# Nunca salen hacia las páginas (solo «guardado sí/no»): claves y el enlace secreto del calendario
SECRET_FIELDS = API_KEY_FIELDS + ("calendar_urls", "telegram_token", "email_app_password", "mobile_token",
                                   "classroom_client_secret", "classroom_refresh", "whatsapp_apikey", "data_key") + (
    ("spotify_client_secret",) if "spotify_client_secret" in DEFAULT_SETTINGS else ())
AI_SETTING_KEYS = ({"ai_provider", "ollama_host", "ollama_model", "openai_base_url"}
                   | set(API_KEY_FIELDS) | {f"{p}_model" for p in PROVIDERS})
# Modelos por defecto antiguos que ya no admiten claves nuevas: se migran al actual.
LEGACY_DEFAULT_MODELS = {"gemini_model": ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash")}

RANGES = {
    "tts_rate": (-50, 50), "tts_volume": (-50, 50), "tts_pitch": (-50, 50),
    "wake_window": (3, 30), "followup_listen": (0, 20), "live_idle": (5, 120), "live_barge_level": (5, 80), "history_turns": (0, 30), "ai_temperature": (0.0, 2.0),
    "mic_device": (-1, 999), "hud_opacity": (30, 100),
    "mic_sensitivity": (0, 60), "min_command_chars": (0, 20), "quake_min_mag": (3.0, 7.0),
    "hud_x": (-1, 20000), "hud_y": (-1, 20000), "copilot_interval": (1, 60), "notes_notice_min": (0, 240), "calendar_notice_min": (0, 120),
    "camera_index": (0, 9),
    "proactive_max": (0, 50), "proactive_break_min": (30, 300), "diary_days": (1, 365), "history_days": (7, 730), "tool_select_max": (10, 80), "project_parallel": (1, 4), "email_days": (1, 14), "risk_grade": (1.0, 5.0), "risk_absences": (1, 30), "weekly_hour": (0, 23), "recovery_days": (3, 30), "live_quiz_secs": (10, 120), "drive_backup_keep": (2, 50), "attention_from": (0, 23), "attention_to": (1, 24), "watch_hours": (1, 72), "scale_superior": (3.0, 5.0), "period_current": (1, 6), "scale_alto": (2.5, 5.0), "scale_basico": (1.0, 4.5), "week_prep_hour": (0, 23), "inbox_hour": (4, 11), "inbox_max": (1, 10), "mobile_port": (1024, 65535),
}

settings = dict(DEFAULT_SETTINGS)
settings_lock = threading.Lock()


def normalize(text):
    """minúsculas, sin tildes, sin signos (conserva / + : para fechas y teléfonos)."""
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s/+:]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _validate(key, value):
    default = DEFAULT_SETTINGS[key]
    if isinstance(default, bool):
        if isinstance(value, str):
            return normalize(value) in ("1", "true", "si", "yes", "on", "verdadero")
        return bool(value)
    if isinstance(default, int):
        v = int(float(value))
        lo, hi = RANGES.get(key, (v, v))
        return max(lo, min(hi, v))
    if isinstance(default, float):
        v = float(value)
        lo, hi = RANGES.get(key, (v, v))
        return round(max(lo, min(hi, v)), 2)

    v = str(value).strip()[:6000]
    if key in ("zeti_since", "period_end") and v:                     # 8.7: una fecha AAAA-MM-DD
        v = datetime.date.fromisoformat(v[:10]).isoformat()
    if key == "zeti_weights":                          # 10.1: cuatro porcentajes que suman 100
        nums = [int(x) for x in re.findall(r"\d{1,3}", v)]
        if len(nums) != 4 or sum(nums) != 100:
            raise ValueError("escribe 4 porcentajes que sumen 100, por ejemplo 35,30,30,5")
        v = ",".join(map(str, nums))
    if key == "zeti_period_weights":                   # 10.2: los pesos de los periodos suman 100
        nums = [int(x) for x in re.findall(r"\d{1,3}", v)]
        if not 2 <= len(nums) <= 6 or sum(nums) != 100:
            raise ValueError("escribe el peso de cada periodo y que sumen 100, por ejemplo 34,33,33")
        v = ",".join(map(str, nums))
    if key == "zeti_url" and v and not v.startswith("https://"):
        raise ValueError("la dirección debe empezar por https://")
    choices = {"theme": THEMES, "ai_provider": tuple(PROVIDERS),
               "zeti_order": ("lista", "apellido", "alfabetico"), "hud_expanded": ("estrecho", "amplio", "grande"),
               "weekly_day": ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"),
               "hud_start_size": HUD_SIZES, "hud_position": HUD_POSITIONS,
               "tts_backend": ("edge", "piper", "gemini"), "stt_backend": ("vosk", "whisper"),
               "gemini_tts_model": ("gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts"),
               "stt_refine": ("auto", "gemini", "whisper", "off"), "calendar_create": ("google", "ics"),
               "listen_mode": ("auto", "vivo", "clasico"),
               "live_provider": ("gemini", "openai", "deepgram"),
               "openai_live_voice": tuple(v for v, _ in envivo.OPENAI_VOICES),
               "deepgram_voice": tuple(v for v, _ in envivo.DEEPGRAM_VOICES),
               "whisper_model": {k: 1 for k, _ in WHISPER_SIZES}}
    if key in choices and v not in choices[key]:
        raise ValueError("opción desconocida")
    if key in ("leave_time",) and v:
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", v)
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise ValueError("hora inválida, usa HH:MM")
        v = f"{int(m.group(1)):02d}:{m.group(2)}"
    if key == "proactive_quiet" and v and not proactivo.parse_range(v):
        raise ValueError("usa el formato 21:30-06:30")
    if key == "mcp_servers" and v:
        mcp_cliente.parse_config(v)               # lanza ValueError con un mensaje claro
    if key == "morning_time":
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", v)
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise ValueError("hora inválida, usa HH:MM")
        v = f"{int(m.group(1)):02d}:{m.group(2)}"
    if key == "update_repo" and v:
        v = actualizar.clean_repo(v)
    if key in ("openai_live_model", "deepgram_think_model") and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.\-_:]{1,80}", v):
        raise ValueError("nombre de modelo inválido")
    if key == "live_model" and not re.fullmatch(r"[a-z0-9][a-z0-9.\-]{2,80}", v):
        raise ValueError("nombre de modelo inválido")
    if key == "gemini_tts_voice" and v not in {n for n, _ in GEMINI_TTS_VOICES}:
        raise ValueError("voz de Gemini desconocida")
    if key == "gemini_tts_style":
        v = re.sub(r"[\r\n<>]+", " ", v)[:200].strip()
    if key == "tts_voice" and not re.fullmatch(r"[a-z]{2,3}-[A-Z]{2}-\w+Neural", v):
        raise ValueError("nombre de voz inválido")
    if key in ("ollama_host", "openai_base_url"):
        if not re.match(r"https?://", v):
            raise ValueError("debe empezar por http:// o https://")
        v = v.rstrip("/")
    if key == "system_prompt" and not v:
        v = DEFAULT_SYSTEM_PROMPT
    if key == "wake_words":
        words = [normalize(w) for w in v.split(",") if normalize(w)]
        if not words:
            raise ValueError("indica al menos una palabra de activación")
        v = ", ".join(dict.fromkeys(words))
    if key == "output_dir" and not v:
        v = DEFAULT_SETTINGS["output_dir"]
    return v


# -----------------------------------------------------------------------------
# Archivo .env (junto al programa): valores que mandan sobre config.json y nunca
# se escriben en él. Útil para claves de API o para llevar la configuración en la USB.
#   OPENAI_API_KEY=sk-...        OLLAMA_HOST=http://192.168.1.20:11434
#   JARVIS_TTS_VOICE=es-CO-GonzaloNeural     (cualquier ajuste con el prefijo JARVIS_)
# -----------------------------------------------------------------------------
ENV_PATH = os.path.join(APP_DIR, ".env")
ENV_ALIASES = {
    "OPENAI_API_KEY": "openai_api_key", "OPENAI_BASE_URL": "openai_base_url",
    "OPENAI_MODEL": "openai_model", "OLLAMA_HOST": "ollama_host", "OLLAMA_MODEL": "ollama_model",
    "GEMINI_API_KEY": "gemini_api_key", "GEMINI_MODEL": "gemini_model",
    "ANTHROPIC_API_KEY": "anthropic_api_key", "CLAUDE_API_KEY": "anthropic_api_key",
    "CHATGPT_API_KEY": "chatgpt_api_key", "DEEPSEEK_API_KEY": "deepseek_api_key",
    "MOONSHOT_API_KEY": "kimi_api_key", "KIMI_API_KEY": "kimi_api_key",
    "XAI_API_KEY": "xai_api_key", "MISTRAL_API_KEY": "mistral_api_key",
    "GROQ_API_KEY": "groq_api_key", "OPENROUTER_API_KEY": "openrouter_api_key",
}
env_overrides = {}
_file_values = {}


def _read_env():
    try:
        with open(ENV_PATH, encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    except OSError:
        return {}
    out = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k.lower().startswith("export "):
            k = k[7:].strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k] = v
    return out


def load_settings():
    data = {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"config.json ilegible, uso valores por defecto: {e}")
    _file_values.clear()
    lost = []
    for k in SECRET_FIELDS:                         # 8.0: claves cifradas con DPAPI
        if secreto.is_sealed(data.get(k)):
            data[k], ok = secreto.unseal(data[k])
            if not ok:
                lost.append(k)
    secrets_lost[:] = lost
    for k, v in data.items():
        if k in DEFAULT_SETTINGS:
            try:
                settings[k] = _file_values[k] = _validate(k, v)
            except Exception:
                pass
    for k, old in LEGACY_DEFAULT_MODELS.items():
        if settings.get(k) in old:
            settings[k] = DEFAULT_SETTINGS[k]
    if not settings["update_repo"]:                 # instalaciones anteriores: repositorio oficial
        settings["update_repo"] = DEFAULT_SETTINGS["update_repo"]
    for k, v in _read_env().items():
        ku = k.upper()
        key = ENV_ALIASES.get(ku) or (ku[7:].lower() if ku.startswith("JARVIS_") else None)
        if key in DEFAULT_SETTINGS:
            try:
                settings[key] = env_overrides[key] = _validate(key, v)
            except Exception as e:
                print(f".env: se ignora {k} ({e})")


def save_settings_file():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    data = dict(settings)
    for k, v in env_overrides.items():          # lo que viene del .env no se copia a config.json
        if data.get(k) == v:
            data[k] = _file_values.get(k, DEFAULT_SETTINGS[k])
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(secreto.seal_all(data, SECRET_FIELDS, settings["encrypt_secrets"] and not PORTABLE), f,
                  ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)
    _file_values.clear()
    _file_values.update(data)


def public_settings():
    s = {k: v for k, v in settings.items() if k not in SECRET_FIELDS}
    for k in SECRET_FIELDS:                      # las claves nunca salen hacia la página
        s[f"{k}_set"] = bool(settings[k])
    s["autostart"] = autostart_enabled()
    s["env_keys"] = sorted(env_overrides)
    return s


def get_wake_words():
    return [w.strip() for w in settings["wake_words"].split(",") if w.strip()]


# =============================================================================
# FLASK / SOCKETIO
# =============================================================================
app = Flask(__name__,
            template_folder=get_resource_path("templates"),
            static_folder=get_resource_path("static"))
app.config["SECRET_KEY"] = os.urandom(24).hex()
# Solo las páginas del propio Jarvis pueden conectarse (ninguna web externa puede darle órdenes).
socketio = SocketIO(app, async_mode="threading", max_http_buffer_size=25 * 1024 * 1024,
                    cors_allowed_origins=[URL, f"http://localhost:{PORT}"])

log_buffer = deque(maxlen=400)
chat_buffer = deque(maxlen=120)


def log_terminal(message, origin="JARVIS"):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] [{origin}] {message}"
    log_buffer.append(line)
    try:
        print(line, flush=True)
    except Exception:
        pass
    socketio.emit("terminal_log", {"data": line})
    if origin == "ERROR":                              # 8.0: queda en el registro de errores, con la orden
        errores.record("ERROR", message, getattr(_tl, "cmd_text", "") or "")
        try:
            notice_add(str(message)[:200], "error", "ERROR")   # 9.2: y en la campana del HUD
        except NameError:
            pass


# Lo que el orbe de la barra de tareas muestra (7.3): último mensaje, último aviso y nivel del micrófono.
orb_feed = {"seq": 0, "msg": "", "role": "", "alert_seq": 0, "alert": "", "level": 0.0}


def push_chat(role, text, source=""):
    now = datetime.datetime.now()
    item = {"role": role, "text": text, "source": source, "time": now.strftime("%H:%M"), "date": now.date().isoformat()}
    chat_buffer.append(item)
    recuerdos.log(role, text)                         # 7.4: historial buscable (sin claves ni contraseñas)
    orb_feed.update(seq=orb_feed["seq"] + 1, msg=str(text)[:400], role=role)
    socketio.emit("chat", item)
    try:
        tutor_relay(item)                              # 9.4: en modo tutor, también al proyector
    except NameError:
        pass


# =============================================================================
# ESTADO EN VIVO
# =============================================================================
jarvis_rest = {"on": False}              # «Jarvis, descansa»: oculto y solo atiende al nombre
# conversación en vivo (ver CONVERSACIÓN EN VIVO más abajo)
live = {"session": None, "player": None, "active": False, "connecting": False, "prebuf": bytearray(),
        "started": 0.0, "last": 0.0, "in_buf": "", "out_buf": "", "pause": {}, "provider": "", "why": "",
        "ending": False, "model": "", "turn_audio": False}
state = {"resting": False, "viewing": "", "live": False, "net": "online", "mic": "off", "ai": "unknown", "ai_label": "", "tts": "off", "mode": "idle", "copilot": False}
state_lock = threading.Lock()
thinking = 0
wake_until = 0.0


def set_state(**changes):
    with state_lock:
        if all(state.get(k) == v for k, v in changes.items()):
            return
        state.update(changes)
        snapshot = dict(state)
    socketio.emit("state", snapshot)


def refresh_mode():
    if live.get("active"):
        p = live.get("player")
        set_state(mode="speaking" if (p is not None and p.playing()) or tts_playing.is_set() else "awaiting")
        return
    if tts_playing.is_set():
        mode = "speaking"
    elif thinking > 0:
        mode = "thinking"
    elif time.time() < wake_until:
        mode = "awaiting"
    else:
        mode = "idle"
    set_state(mode=mode)


# =============================================================================
# UTILIDADES DE TEXTO
# =============================================================================
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

NUM_WORDS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11,
    "doce": 12, "quince": 15, "veinte": 20, "veinticinco": 25, "treinta": 30,
    "cuarenta": 40, "cuarenta y cinco": 45, "cincuenta": 50, "sesenta": 60,
    "noventa": 90,
}
_NUM_ALT = "|".join(sorted(map(re.escape, NUM_WORDS), key=len, reverse=True))
_DUR_RE = re.compile(rf"\ben\s+(\d+|{_NUM_ALT})\s+(segundos?|minutos?|horas?)\b")
_UNIT_SECONDS = {"seg": 1, "min": 60, "hor": 3600}


def has(pattern, t):
    return re.search(rf"\b(?:{pattern})\b", t) is not None


def fecha_hablada(d):
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} de {d.year}"


def parse_reminder(t):
    """'recuerdame en cinco minutos tomar agua' -> (300, 'tomar agua')."""
    m = re.search(r"\ben\s+media\s+hora\b", t)
    if m:
        seconds = 1800
    else:
        m = _DUR_RE.search(t)
        if not m:
            return None
        raw = m.group(1)
        qty = int(raw) if raw.isdigit() else NUM_WORDS[raw]
        seconds = qty * _UNIT_SECONDS[m.group(2)[:3]]
    label = t[m.end():].strip()
    label = re.sub(r"^(?:que|de|para|a)\s+", "", label) or "Recordatorio"
    return seconds, label


def is_stop_command(t):
    return t in {"para", "alto", "basta", "stop"} or has(
        r"detente|deten la voz|callate|deja de hablar|para de hablar", t)


# =============================================================================
# SÍNTESIS DE VOZ
# → nucleo/voz.py
# =============================================================================
from nucleo.voz import *  # noqa: F401,F403,E402


# =============================================================================
# CONECTOR DE IA: Ollama, Gemini, Claude y cualquier API compatible con OpenAI
# → nucleo/ia.py
# =============================================================================
from nucleo.ia import *  # noqa: F401,F403,E402


# =============================================================================
# MÓDULOS PROPIOS (recordatorios, documentos, numerología, rutinas)
# =============================================================================
SOUND_CANDIDATES = ("recursos/sirena.mp3", "sirena.mp3", "recursos/alarma.mp3", "alarma.mp3",
                    "recursos/sirena.wav", "recursos/alarma.wav")


def resolve_alarm_sound(value=None):
    """Ruta del sonido de alarma: la elegida en Ajustes o, si está vacía, sirena.mp3 de «recursos»."""
    v = (settings["alarm_sound"] if value is None else str(value)).strip().strip('"')
    if v:
        p = v if os.path.isabs(v) else os.path.join(APP_DIR, v)
        return p if os.path.isfile(p) else None
    for name in SOUND_CANDIDATES:
        p = get_resource_path(name)
        if os.path.isfile(p):
            return p
    return None


def trigger_alarm(seconds, label="Recordatorio"):
    def _fire():
        hud_show()
        play_sound(resolve_alarm_sound())
        reply(f"Atención: {label}.", "ALARMA")
        orb_feed.update(alert_seq=orb_feed["alert_seq"] + 1, alert=f"Atención: {label}.")
        windows_toast(f"Atención: {label}.", "ALARMA")

    t = threading.Timer(seconds, _fire)
    t.daemon = True
    t.start()
    diario.log("recordatorio", label)


# =============================================================================
# TEMPORIZADORES DE CLASE (cuenta regresiva visible en el HUD)
# → nucleo/temporizadores.py
# =============================================================================
from nucleo.temporizadores import *  # noqa: F401,F403,E402


# =============================================================================
# AUTOINICIO EN WINDOWS (sin ventana de consola)
# =============================================================================
def autostart_supported():
    # En modo USB no se toca el inicio de Windows del equipo prestado.
    return IS_WIN and bool(os.environ.get("APPDATA")) and not PORTABLE


def autostart_enabled():
    return autostart_supported() and os.path.exists(STARTUP_VBS)


def _fix_autostart_path():
    """Si el inicio automático apunta a otra carpeta (una copia vieja de Jarvis), lo
    corrige para que Windows arranque ESTA versión."""
    if not autostart_enabled():
        return
    try:
        with open(STARTUP_VBS, encoding="mbcs" if IS_WIN else "utf-8", errors="replace") as f:
            current = f.read()
        if _silent_command().replace('"', '""') not in current:
            set_autostart(True)
            log_terminal("El inicio automático apuntaba a otra copia de Jarvis; ahora abre esta.", "SISTEMA")
    except Exception as e:
        log_terminal(f"No pude revisar el inicio automático: {e}", "AVISO")


def _silent_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    return f'"{exe}" "{os.path.abspath(__file__)}"'


def set_autostart(enabled):
    if not autostart_supported():
        raise ValueError("el autoinicio solo está disponible en Windows")
    if not enabled:
        if os.path.exists(STARTUP_VBS):
            os.remove(STARTUP_VBS)
        return
    vbs_cmd = _silent_command().replace('"', '""')
    content = ('Set WshShell = CreateObject("WScript.Shell")\r\n'
               f'WshShell.Run "{vbs_cmd}", 0, False\r\n'
               'Set WshShell = Nothing\r\n')
    os.makedirs(os.path.dirname(STARTUP_VBS), exist_ok=True)
    with open(STARTUP_VBS, "w", encoding="mbcs" if IS_WIN else "utf-8") as f:
        f.write(content)


# =============================================================================
# PROCESADOR DE COMANDOS
# =============================================================================
HELP_TEXT = (
    "Puedo abrir y cerrar aplicaciones, carpetas y páginas web, controlar ventanas, "
    "volumen, brillo y música, manejar presentaciones y el videobeam, dictar al teclado, "
    "buscar en Google, YouTube o tus archivos, tomar capturas, escribir por ti, "
    "ponerte recordatorios, crear documentos STEAM y responder cualquier pregunta."
)

pending = {"skill": None, "args": None, "expires": 0.0}
# Pregunta de seguimiento: si una acción pidió un dato («¿Qué mensaje le envío?»),
# la siguiente frase del usuario se usa como ese dato en vez de ir a la IA.
followup = {"skill": None, "args": None, "need": None, "expires": 0.0}
SKILL_TIMEOUT = 40       # segundos; si una acción tarda más, Jarvis sigue atendiendo otras órdenes
CONFIRM_RE = r"(?:si|confirmar|confirmo|confirmado|hazlo|adelante|dale|de acuerdo|ok|okay|claro)"
DENY_RE = r"(?:no|cancela(?:r)?|cancelado|olvidalo|mejor no)"

# Modo dictado: la voz se escribe en la ventana activa en vez de interpretarse como orden.
dictation_on = threading.Event()
dictation_math = threading.Event()
DICTATION_STOP_RE = r"(?:termina(?:r)?|finaliza(?:r)?|cierra|deten(?:er)?|para(?:r)?|sal(?:ir)? del) (?:el )?dictado"
DICTATION_START_RE = (r"(?:inicia(?:r)?|empieza|comienza|activa(?:r)?|abre|pon) (?:el )?(?:modo )?dictado"
                      r"|empezar a dictar|modo dictado|dictar al teclado")


def _set_dictation(on):
    (dictation_on.set if on else dictation_on.clear)()
    if not on:
        dictation_math.clear()
    set_state(mode=state["mode"])          # fuerza refresco del indicador en el HUD
    socketio.emit("dictation", {"on": on})


def read_selection_aloud():
    """Copia el texto seleccionado (Ctrl+C) y lo lee en voz alta, frase por frase."""
    pg = skills.pyautogui
    if pg is None or skills.pyperclip is None:
        reply("Para leer necesito las librerías pyautogui y pyperclip.", "ERROR")
        return
    try:
        before = skills.pyperclip.paste()
    except Exception:
        before = ""
    pg.hotkey("ctrl", "c")
    time.sleep(0.25)
    try:
        texto = skills.pyperclip.paste()
    except Exception:
        texto = ""
    if not texto or texto == before:
        reply("No veo texto seleccionado. Selecciona el texto y di «lee esto».", "LECTOR")
        return
    texto = re.sub(r"\s+", " ", texto).strip()
    log_terminal(f"Leyendo {len(texto)} caracteres seleccionados.", "LECTOR")
    push_chat("jarvis", "Leyendo el texto seleccionado…", "LECTOR")
    for frase in re.split(r"(?<=[.!?…:])\s+", texto):
        frase = frase.strip()
        if frase:
            speak(frase)


# =============================================================================
# ACTUALIZACIONES desde GitHub (lógica en actualizar.py)
# → nucleo/servicios.py
# =============================================================================
from nucleo.servicios import *  # noqa: F401,F403,E402



# =============================================================================
# CONVERSACIÓN EN VIVO (Gemini Live). Protocolo en envivo.py.
# → nucleo/vivo.py
# =============================================================================
from nucleo.vivo import *  # noqa: F401,F403,E402



# =============================================================================
# CLIMA Y NOTICIAS (lógica en infodia.py)
# → nucleo/avisos.py
# =============================================================================
from nucleo.avisos import *  # noqa: F401,F403,E402


# =============================================================================
# CÓMO TE TRATA + MEMORIA QUE APRENDE SOLA (perfil). Lógica de perfil en perfil.py.
# → nucleo/personal.py
# =============================================================================
from nucleo.personal import *  # noqa: F401,F403,E402


# =============================================================================
# AULA: cursos, sorteo, grupos, asistencia, semáforo de ruido y material de clase
# → nucleo/clase.py
# =============================================================================
from nucleo.clase import *  # noqa: F401,F403,E402


# =============================================================================
# VISIÓN DE PANTALLA Y COPILOTO
# → nucleo/pantalla.py
# =============================================================================
from nucleo.pantalla import *  # noqa: F401,F403,E402


# =============================================================================
# PRUEBA COMPLETA (6.8): revisa todo lo que necesita Jarvis y dice qué falla y cómo arreglarlo
# → nucleo/diagnostico.py
# =============================================================================
from nucleo.diagnostico import *  # noqa: F401,F403,E402
_POLITE_RE = re.compile(r"^(?:(?:oye|jarvis|porfa|por favor|bueno|y)\s+)*(?:(?:me|le|nos)\s+)?"
                        r"(?:puedes|podrias|podria|puede|quieres|quisieras|seria posible|es posible|me haces el favor de|"
                        r"hazme el favor de|me ayudas a|te pido que|ayudame a)\s+(?:(?:me|le|nos)\s+)?(\w+)\s*(.*)$")
_ME_VERB_RE = re.compile(r"^(?:(?:oye|jarvis|porfa|y)\s+)*(?:me|le|nos)\s+(\w+)\b\s*(.*)$")
_TU_TO_IMP = {"pones": "pon", "abres": "abre", "subes": "sube", "bajas": "baja", "cierras": "cierra", "buscas": "busca",
              "pausas": "pausa", "quitas": "quita", "silencias": "silencia", "apagas": "apaga", "enciendes": "enciende",
              "prendes": "prende", "minimizas": "minimiza", "maximizas": "maximiza", "lees": "lee", "dices": "dime",
              "cuentas": "cuentame", "muestras": "muestrame", "ensenas": "ensename", "reproduces": "reproduce",
              "activas": "activa", "desactivas": "desactiva", "cambias": "cambia", "recuerdas": "recuerdame",
              "avisas": "avisame", "tomas": "toma", "haces": "haz", "mandas": "manda", "envias": "envia",
              "escribes": "escribe", "calculas": "calcula", "traduces": "traduce", "pasas": "pasa", "das": "dame"}
_INF_TO_IMP = {"poner": "pon", "ponerme": "pon", "abrir": "abre", "abrirme": "abre", "subir": "sube", "subirle": "sube",
               "bajar": "baja", "bajarle": "baja", "cerrar": "cierra", "buscar": "busca", "buscarme": "busca",
               "pausar": "pausa", "quitar": "quita", "silenciar": "silencia", "apagar": "apaga", "encender": "enciende",
               "prender": "prende", "minimizar": "minimiza", "maximizar": "maximiza", "leer": "lee", "leerme": "lee",
               "decir": "dime", "decirme": "dime", "contar": "cuentame", "contarme": "cuentame", "mostrar": "muestra",
               "mostrarme": "muestrame", "ensenarme": "ensename", "reproducir": "reproduce", "activar": "activa",
               "desactivar": "desactiva", "cambiar": "cambia", "tomar": "toma", "hacer": "haz", "hacerme": "haz",
               "mandar": "manda", "enviar": "envia", "escribir": "escribe", "recordarme": "recuerdame",
               "avisarme": "avisame", "calcular": "calcula", "traducir": "traduce", "pasar": "pasa", "dar": "dame",
               "darme": "dame", "llevarme": "llevame", "cancelar": "cancela", "iniciar": "inicia", "crear": "crea"}


def polite_to_order(t):
    """«puedes subir el volumen» → «sube el volumen». None si no es una petición con forma de pregunta."""
    t = t.strip()
    m = _POLITE_RE.match(t)
    if m and m.group(1) in _INF_TO_IMP:
        return (_INF_TO_IMP[m.group(1)] + " " + m.group(2)).strip()
    m = _ME_VERB_RE.match(t)
    if m and m.group(1) in _TU_TO_IMP:
        return (_TU_TO_IMP[m.group(1)] + " " + m.group(2)).strip()
    return None


def process_command(text):
    t = normalize(text)
    if not t:
        return
    rapidez.mark("orden")
    _tl.cmd_text = text                               # 7.4: para aprender tus costumbres
    if not getattr(_tl, "polite", False):
        order = polite_to_order(t)
        if order and order != t:
            log_terminal(f"Petición «{text.strip()}» → orden «{order}»", "COMPRENSIÓN")
            text, t = order, order

    if followup["skill"]:
        name, args, need = followup["skill"], followup["args"], followup["need"]
        live = time.time() < followup["expires"]
        followup.update(skill=None, args=None, need=None, expires=0)
        if live:
            # Solo «no», «cancela», «olvídalo»... a secas: «No se te olvide...» es un mensaje.
            if re.fullmatch(rf"{DENY_RE}(?: gracias| importa| lo envies| lo mandes)?", t):
                reply("Vale, lo dejo.", "PC")
                return
            args[need] = text.strip()
            run_skill(name, args)
            return

    if pending["skill"]:
        name, args = pending["skill"], pending["args"]
        live = time.time() < pending["expires"]
        pending.update(skill=None, args=None, expires=0)
        if live and re.fullmatch(rf"{CONFIRM_RE}(?: .*)?", t):
            run_skill(name, args, confirmed=True)
            return
        if live and re.fullmatch(rf"{DENY_RE}(?: .*)?", t):
            reply("Cancelado.", "PC")
            return

    if _email_confirm_pending(t):                      # «sí, envíalo» / «no» de un correo pendiente
        return
    if proactive_answer(t) or mcp_answer(t):           # «sí» a «¿activo el modo clase?» o a un conector
        return
    if learn_answer(t):                                # «sí» a «¿lo guardo como rutina?»
        return
    if approvals_answer(t):                            # «sí», «sí 3», «no 2» a una aprobación pendiente
        return
    if live_quiz_voice(text, t):                       # 8.8: «quiz en vivo», y durante el quiz «respuesta», «siguiente»
        return
    if live_class_voice(text, t):                      # 9.6: «empieza la clase de fracciones», «siguiente momento»
        return
    if ticket_voice(text, t):                          # 9.6: «lanza el ticket de salida», «semáforo de comprensión»
        return
    if activities_voice(text, t):                      # 9.6: «¿qué actividades funcionaron en fracciones?»
        return
    if link_material_voice(text, t):                   # 9.3: «haz un quiz con este artículo https://…», «nivela este texto: …»
        return
    if attention_voice(text, t):                       # 9.3: «¿qué necesita mi atención?»
        return
    if commitments_voice(text, t):                     # 9.3: «quedé en…», «¿qué compromisos tengo?», «ya le envié…»
        return
    if tutor_voice(text, t):                           # 9.4: «activa el modo tutor de matemáticas»
        return
    if page_watch_voice(text, t):                      # 9.4: «avísame cuando publiquen algo nuevo en https://…»
        return
    if early_voice(text, t):                           # 9.7: «¿quién viene bajando?», «¿a quién debo felicitar?»
        return
    if card_voice(text, t):                            # 9.7: «muéstrame a Juan de 7A», «ficha de Juan»
        return
    if week_voice(text, t):                            # 9.8: «prepárame la semana», «¿cómo viene la semana?»
        return
    if period_voice(text, t):                          # 9.8: «el periodo termina el 28 de noviembre», «cierra el periodo»
        return
    if inbox_voice(text, t):                           # 9.8: «redacta las respuestas de mis correos», «limpia mi bandeja»
        return
    if zeti_open_voice(text, t):                       # 10.1: «abre Zeti»
        return
    if sheets_voice(text, t):                          # 10.5: «prepara las hojas de respuesta del quiz para 7A»
        return
    if grading_voice(text, t):                         # 10.5: «califica las hojas», «terminé de calificar», «prepara el refuerzo»
        return
    if subject_voice(text, t):                         # 10.4: «estamos en tecnología», «¿en qué asignatura estamos?»
        return
    if year_voice(text, t):                            # 10.2: «¿cuánto necesita Juan de 7A para pasar?», «¿quiénes pueden perder el año?»
        return
    if meeting_voice(text, t):                         # 10.0: «prepara la agenda de la reunión de área», «empieza el acta»
        return
    if kit_voice(text, t):                             # 10.0: «exporta mi kit para colegas»
        return
    if persona_voice(text, t):                         # 9.9: «ponte relajado», «personalidad automática»
        return
    if mood_voice(text, t):                            # 9.9: «¿cómo viene mi día?»
        return
    if retro_voice(text, t):                           # 9.9: «haz mi retrospectiva del año»
        return
    if lessons_voice(text, t):                         # 9.4: «de ahora en adelante…», «¿qué lecciones tienes?»
        return
    if text_feedback_voice(text, t):                   # 9.5: «retroalimenta este texto de Juan de 7A: …»
        return
    if style_voice(text, t):                           # 9.5: «aprende mi estilo con este texto: …», «¿cómo escribo?»
        return
    if morning_voice(text, t):                         # 9.5: «mándame el resumen de la mañana en audio»
        return
    if _CHECK_RE.search(t):                            # «prueba completa», «revisa todo»
        if getattr(_tl, "remote", False):
            reply(check_report(run_system_check(speak_it=False)), "PRUEBA")
        else:
            show_system_check()
        return
    if _rest_voice(text, t):                           # «Jarvis, descansa» / «despierta»
        return

    if dictation_on.is_set():
        handle_dictation(text)
        return

    if re.search(DICTATION_START_RE, t):
        if skills.pyautogui is None:
            reply("No puedo dictar: falta la librería pyautogui.", "ERROR")
            return
        _set_dictation(True)
        reply("Dictado activado. Escribiré lo que digas en la ventana donde estés. "
              "Di «modo matemáticas» para fórmulas, o «terminar dictado» para parar.", "PC")
        return

    # Modo sigilo: ocultar o mostrar el panel por voz (sigue escuchando el micrófono)
    # Mostrar (se comprueba antes que ocultar para que «sal del modo sigilo» funcione)
    if re.search(r"\bsal del? (?:modo )?sigilo\b|\bmuestrate\b|\baparece\b"
                 r"|\b(?:mostrar|muestra(?:me)?|ensena(?:me)?|despliega) (?:el |la )?(?:panel|hud|interfaz|ventana)\b", t):
        hud_show()
        reply("Panel a la vista.", "SISTEMA")
        return
    if re.search(r"\b(?:modo sigilo|modo invisible|escondete|ocultate|desaparece)\b"
                 r"|\b(?:oculta(?:r)?|esconde(?:r)?) (?:el |la )?(?:panel|hud|interfaz|ventana)\b", t):
        reply("Modo sigilo. Seguiré escuchando; di «mostrar panel» cuando me necesites.", "SISTEMA")
        threading.Timer(1.6, hud_hide).start()     # deja que termine de hablar antes de ocultarse
        return

    if mates.looks_math(text):
        reply(mates.resolver(text), "MATE")
        return

    # Temporizadores de clase (cuenta regresiva visible)
    TIMER_WORDS = r"temporizador(?:es)?|cronometro|cuenta regresiva|cuenta atras|tempori\w*"
    if has(r"cancela(?:r)?|quita(?:r)?|deten(?:er)?|elimina(?:r)?|borra(?:r)?", t) and \
            has(TIMER_WORDS, t):
        m = re.search(rf"(?:{TIMER_WORDS})\s+(?:de\s+)?(.+)$", t)
        etiqueta = m.group(1).strip() if m and not re.fullmatch(r"(?:todos|todo)", m.group(1).strip()) else ""
        n = cancel_timers(etiqueta)
        reply("No había temporizadores activos." if n == 0 else
              ("Temporizador cancelado." if n == 1 else f"Cancelé {n} temporizadores."), "TIMER")
        return
    if has(r"cuanto (?:queda|falta)|que temporizador|temporizadores (?:hay|activos)|cuanto tiempo queda", t):
        snap = _timers_snapshot()
        if not snap:
            reply("No hay temporizadores activos.", "TIMER")
        else:
            partes = [f"{_spoken_duration(x['remaining'])}" + (f" para {x['label']}" if x["label"] else "")
                      for x in snap]
            reply("Queda " + "; ".join(partes) + ".", "TIMER")
        return
    _dur = parse_duration(t)
    _media = has(r"cancion|musica|video|pelicula|youtube|lista de reproduccion", t)
    if has(TIMER_WORDS, t) or \
            (has(r"pon(?:me|le)?|alarma|avisame|despiertame|cronometra", t) and _dur and not _media):
        if not _dur:
            reply("Dime cuánto, por ejemplo: pon un temporizador de quince minutos para el examen.", "TIMER")
            return
        m = re.search(r"\bpara\s+(.+)$", t) or re.search(r"\b(?:de|del)\s+(?:la |el )?(examen|prueba|taller|actividad|ejercicio|lectura|descanso|recreo|clase|quiz|evaluacion|parcial)\b", t)
        label = (m.group(1).strip() if m else "")
        label = re.sub(r"\b(?:el|la|los|las)\b\s*", "", label).strip()
        add_timer(_dur, label)
        extra = f" para {label}" if label else ""
        reply(f"Temporizador de {_spoken_duration(_dur)}{extra} en marcha.", "TIMER")
        learn_note("temporizador", {"segundos": int(_dur)})
        return

    if backup_drive_voice(text, t):                    # «haz una copia de seguridad en Drive»
        return
    if export_voice(text, t):                          # «pasa el quiz a Kahoot», «exporta las notas de 7A para Zeti»
        return
    if drive_voice(text, t):                           # «sube el taller a Drive», «pásalo a Google Slides»
        return
    if projector_voice(text, t):                       # «modo proyector»
        return
    if recurring_project(text, t):                     # «cada domingo a las 6 prepárame la semana de 7A sobre…»
        return
    if weekly_voice(text, t):                          # «dame el resumen semanal»
        return
    if approvals_voice(text, t):                       # «¿qué tengo por aprobar?», «¿qué hiciste por tu cuenta?»
        return
    if project_voice(text, t):                         # «prepárame la semana de 7A sobre fracciones»
        return
    if mail_voice(text, t):                            # «¿qué correos importantes tengo?», «contéstale que sí»
        return
    if event_voice(text, t):                           # «agenda una reunión con los padres de Juan el jueves a las 3»
        return
    if recovery_voice(text, t):                        # «haz los planes de recuperación de 7A»
        return
    if class_diary_voice(text, t):                     # «hoy en 7A vimos fracciones equivalentes», «¿qué temas me faltan…?»
        return
    if family_voice(text, t):                          # «anota en el observador de Juan que…», «informe para los padres de 7A»
        return
    if forms_voice(text, t):                           # «pasa el quiz a Forms», «trae las notas del formulario»
        return
    if feedback_voice(text, t):                        # «revisa las respuestas del taller en Classroom de 7A»
        return
    if schedule_voice(text, t):                        # «¿qué clase tengo ahora?», «prepárame la próxima clase»
        return
    if classroom_voice(text, t):                       # «¿quién no ha entregado el taller en Classroom de 7A?»
        return
    if student_voice(text, t):                         # «ponle 4,5 a Juan en el quiz», «¿quiénes están en riesgo en 7A?»
        return
    if bank_voice(text, t):                            # «haz un quiz de fracciones con el banco»
        return
    if image_voice(text, t):                           # «hazme una ilustración del ciclo del agua»
        return
    if health_voice(text, t):                          # «genera el informe de errores», «¿has tenido errores?»
        return
    if tasks_voice(text, t):                           # «cada lunes a las 6 resume mis pendientes y mándamelo al celular»
        return
    if recall_voice(text, t):                          # «¿qué te dije la semana pasada sobre el examen de 7A?»
        return
    if learn_voice(text, t):                           # «olvida mis costumbres»
        return
    # Rutinas: «modo clase», «fin de clase», «¿qué rutinas tengo?»
    if routine_voice(text, t):
        return
    if skill_voice(text, t):                           # habilidades instaladas («busca X en wikipedia»…)
        return
    if watch_voice(text, t):                           # «avísame cuando termine la descarga»
        return
    if diary_voice(text, t):                           # «¿qué hice ayer?», «resume mi semana»
        return
    if speed_voice(text, t):                           # «¿qué tan rápido respondes?», «¿cuánto tardas?»
        return
    if welcome_voice(text, t):                         # «repite la bienvenida», «primeros pasos»
        return
    if board_voice(text, t):                           # «lee lo que hay en el tablero», «haz un quiz con esta hoja»
        return

    # Calendario: «¿cuál es mi próxima clase?», «¿qué sigue?», «actualiza el calendario»
    if update_voice(text, t):
        return
    if backup_voice(text, t):
        return
    if calendar_voice(text, t):
        return

    # Memoria personal: «recuerda que…», «¿qué tengo pendiente?», «ya hice lo de…»
    if notes_voice(text, t):
        return
    if email_voice(text, t):                           # «escríbele un correo a…»
        return

    # Revisar trabajos: «revisa el taller de Juan», «califica este examen en la pantalla»
    if review_voice(text, t):
        return

    # Aula: sorteo, grupos, asistencia, semáforo, tablero y material de clase
    if info_voice(text, t):
        return
    if research_voice(text, t):                        # «investiga a fondo…» → informe con fuentes
        return
    if search_voice(text, t):                          # «busca en internet… / averigua…»
        return
    if office_voice(text, t):
        return
    if aula_voice(text, t):
        return
    if profile_voice(text, t):                         # aprende datos/gustos y «llámame X» (tras los comandos)
        return

    # Copiloto: «activa el copiloto», «copiloto cada 10 minutos», «desactiva el copiloto»
    if re.search(r"\bcopiloto\b", t):
        mi = re.search(r"\bcada\s+(\d+|un|una|dos|tres|cuatro|cinco|diez|quince|veinte|treinta)\s+minutos?\b", t)
        words = {"un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "diez": 10,
                 "quince": 15, "veinte": 20, "treinta": 30}
        every = (int(mi.group(1)) if mi.group(1).isdigit() else words[mi.group(1)]) if mi else None
        if re.search(r"\b(?:desactiva|apaga|deten|detener|para|quita|cierra|termina|sin)\b", t):
            set_copilot(False)
            reply("Copiloto desactivado. Ya no miraré tu pantalla por mi cuenta.", "COPILOTO")
        elif re.search(r"\b(?:que te parece|algo que decir|sugiere(?:me)? ya|revisa ahora|mira ahora)\b", t):
            if not copilot_tick(force=True):
                reply("Ahora mismo no veo nada que mejorar. Sigue así.", "COPILOTO")
        else:
            set_copilot(True, max(1, min(60, every)) if every else None)
            reply(f"Copiloto activado. Miraré tu pantalla cada {settings['copilot_interval']} minutos "
                  "mientras trabajas y solo te diré algo si tengo una sugerencia útil. "
                  "Di «desactiva el copiloto» para pararlo.", "COPILOTO")
        return

    # Ayuda con lo que estás haciendo: mira la pantalla y sugiere
    if re.search(r"\b(?:ayudame con (?:esto|esta pantalla|este documento|este archivo|esta tarea|lo que "
                 r"(?:estoy haciendo|tengo en (?:la )?pantalla|veo))|que (?:me )?sugieres(?: (?:aqui|con esto|para esto|hacer|que haga))?$|"
                 r"dame (?:una |alguna |unas |algunas )?(?:sugerencias?|ideas?|consejos?)(?: (?:sobre|para|con) esto)?$|"
                 r"tienes (?:alguna )?sugerencia(?: (?:aqui|para esto|con esto))?$|revisa (?:lo que estoy haciendo|mi pantalla|esto|este documento|"
                 r"mi trabajo)|como (?:mejoro|puedo mejorar|mejorar) esto|que opinas de (?:esto|lo que ves|mi pantalla|"
                 r"mi trabajo)|mira (?:lo que estoy haciendo|esto)|que le falta (?:a )?esto)\b", t):
        screen_assist(text, "help")
        return

    # Visión de pantalla: «¿qué hay en la pantalla?», «describe la pantalla», «qué ves»
    if re.search(r"\b(?:que hay en (?:la )?pantalla|describe (?:la |mi )?pantalla|mira (?:la )?pantalla|"
                 r"analiza (?:la )?pantalla|lee (?:la )?pantalla|que (?:ves|se ve)(?: en (?:la )?pantalla)?|"
                 r"que estoy viendo|describe lo que ves)\b", t):
        m = re.search(r"\b(?:pantalla|ves|viendo)\b\s+(.+)$", t)
        describe_screen(m.group(1) if m else "")
        return

    # Leer en voz alta el texto seleccionado (copia la selección y la lee frase a frase)
    if re.fullmatch(r"(?:lee(?:me)?|leer)(?: esto| la seleccion| el texto| en voz alta| lo seleccionado| lo que seleccione)+", t) \
            or re.fullmatch(r"lee(?:me)?|leer", t):
        read_selection_aloud()
        return

    if has(r"que hora es|dime la hora", t):
        reply(f"Son las {datetime.datetime.now():%H:%M}.")
    elif has(r"que dia es|que fecha es|fecha de hoy", t):
        reply(f"Hoy es {fecha_hablada(datetime.date.today())}.")
    elif has(r"recuerdame|recordatorio|alarma|avisame", t):
        parsed = parse_reminder(t)
        if parsed:
            seconds, label = parsed
            trigger_alarm(seconds, label)
            when = (datetime.datetime.now() + datetime.timedelta(seconds=seconds)).strftime("%H:%M")
            reply(f"Recordatorio programado para las {when}: {label}.", "ALARMA")
        else:
            reply("Dime cuándo, por ejemplo: recuérdame en diez minutos sacar la ropa.")
    elif has(r"documento steam", t):
        m = re.search(r"documento\s+steam\s*(?:sobre|acerca de|del|de)?\s*(.*)", text, re.I)
        topic = (m.group(1).strip(" .,:") if m else "") or "General"
        generate_steam_doc(topic)
    elif has(r"reporte matutino|reporte de la manana", t):
        morning_report()
    elif has(r"numerologia|sendero de vida", t):
        m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", t)
        if not m:
            reply("Escribe tu fecha de nacimiento, por ejemplo: numerología 15/08/1990.")
            return
        d, mo, y = map(int, m.groups())
        try:
            datetime.date(y, mo, d)
        except ValueError:
            reply("Esa fecha no es válida.")
            return
        val, meaning = calculate_life_path_number(d, mo, y)
        reply(f"Tu número de Sendero de Vida es {val}. Representa: {meaning}", "NUMEROLOGÍA")
    elif has(r"olvida (?:la|esta) conversacion|nueva conversacion|borra (?:el )?historial|borra(?:r)? (?:la )?memoria", t):
        clear_memory()
        reply("Memoria de conversación borrada.")
    elif has(r"ayuda|que puedes hacer", t):
        reply(HELP_TEXT)
    else:
        direct = skills.parse(text)
        if direct:
            run_skill(*direct)
            return
        if getattr(_tl, "live", False):
            _tl.no_order = True                        # en vivo: lo responde Gemini directamente
            return
        # Preguntas claras -> respuesta en streaming (más rápida, sin pasar por el enrutador).
        is_question = text.strip().endswith("?") or bool(QUESTION_RE.search(t))
        # Con conectores MCP, también las preguntas pasan por el enrutador («¿qué tengo en Notion?»).
        has_mcp = settings["ai_router"] and bool(mcp_hub.catalog(1))
        if (is_question or not settings["ai_router"]) and not getattr(_tl, "remote", False) and not has_mcp:
            answer_question_streaming(text)
            return
        result = ask_ai(text, route=True)
        if result[0] == "skill":
            run_skill(result[1], result[2])
        elif result[0] == "mcp":
            run_mcp(result[1], result[2], text)
        else:
            reply(result[1])


command_queue = queue.Queue()


def submit_command(text, source="texto"):
    # Durante el dictado, «para» y demás son texto que se escribe, no la orden de detener la voz.
    if not dictation_on.is_set() and is_stop_command(normalize(text)):
        stop_speech()
        return
    if not dictation_on.is_set():
        if source != "voz":
            rapidez.begin(source)
        push_chat("user", text, source)
        diario.log("pregunta" if text.strip().endswith("?") else "orden", text)
    command_queue.put(text)


def _command_worker():
    while True:
        text = command_queue.get()
        try:
            process_command(text)
        except Exception as e:
            note_error("ORDEN", e, text)                # 8.0: con la traza, para poder arreglarlo
            log_terminal(f"Error procesando '{text}': {e}", "ERROR")
        if not (settings["tts_enabled"] and audio_ready):
            rapidez.finish_without_voice()
        if not tts_playing.is_set() and tts_queue.empty():
            open_followup()                            # orden sin respuesta hablada


# =============================================================================
# ESCUCHA CONTINUA (VOSK)
# → nucleo/escucha.py
# =============================================================================
from nucleo.escucha import *  # noqa: F401,F403,E402


# =============================================================================
# VENTANA HUD (pywebview), VENTANA DE AJUSTES, BANDEJA Y ATAJOS
# → nucleo/ventanas.py
# =============================================================================
from nucleo.ventanas import *  # noqa: F401,F403,E402


# =============================================================================
# AJUSTES: APLICAR CAMBIOS
# → nucleo/web.py
# =============================================================================
from nucleo.web import *  # noqa: F401,F403,E402


# =============================================================================
# 7.0 · TARJETAS DEL HUD: lo que Jarvis cuenta, también a la vista (clima, agenda, rutinas, avisos…)
# → nucleo/funciones70.py
# =============================================================================
from nucleo.funciones70 import *  # noqa: F401,F403,E402


# =============================================================================
# 7.2 · JARVIS DENTRO DE WINDOWS (clic derecho, jarvis://, lista de saltos, notificaciones, orbe)
# → nucleo/integracion.py (lo que toca Windows está en windows_shell.py)
# =============================================================================
from nucleo.integracion import *  # noqa: F401,F403,E402


# =============================================================================
# 7.4 · APRENDE TUS COSTUMBRES, MEMORIA BUSCABLE Y TAREAS PROGRAMADAS
# → nucleo/aprende.py (lógica en aprendizaje.py, recuerdos.py y tareas.py)
# =============================================================================
from nucleo.aprende import *  # noqa: F401,F403,E402


# =============================================================================
# 7.5 · HERRAMIENTAS POR SIGNIFICADO, HABILIDADES DE LA COMUNIDAD (SKILL.md) E INVESTIGACIÓN CON FUENTES
# → nucleo/herramientas.py (lógica en selector.py, guias.py e investigar.py)
# =============================================================================
from nucleo.herramientas import *  # noqa: F401,F403,E402


# =============================================================================
# 7.6 · CENTRO DE APROBACIONES Y PROYECTOS CON SUB-AGENTES
# → nucleo/agentes.py (lógica en aprobaciones.py y proyectos.py)
# =============================================================================
from nucleo.agentes import *  # noqa: F401,F403,E402


# =============================================================================
# 7.7 · GALERÍA DE CONECTORES, CORREO, CALENDARIO Y CONECTORES CON APROBACIÓN
# → nucleo/conecta.py (lógica en conectores.py, bandeja.py y eventos.py)
# =============================================================================
from nucleo.conecta import *  # noqa: F401,F403,E402


# =============================================================================
# 7.8 · AULA CONECTADA (CLASSROOM, SEGUIMIENTO, BANCO DE PREGUNTAS) Y MEMORIA EDITABLE
# → nucleo/aulaplus.py (lógica en classroom.py, seguimiento.py y banco.py)
# =============================================================================
from nucleo.aulaplus import *  # noqa: F401,F403,E402


# =============================================================================
# 7.9 · NOTAS DE VOZ, WHATSAPP, PANEL INSTALABLE, IMÁGENES Y VARIOS EQUIPOS
# → nucleo/alcance.py (lógica en imagenes.py, whatsapp.py y sincronizar.py)
# =============================================================================
from nucleo.alcance import *  # noqa: F401,F403,E402


# =============================================================================
# 8.0 · REGISTRO DE ERRORES, INFORME, CLAVES CIFRADAS Y REVISIÓN DE CONEXIONES
# → nucleo/salud.py (lógica en errores.py y secreto.py)
# =============================================================================
from nucleo.salud import *  # noqa: F401,F403,E402


# =============================================================================
# 8.1 · GOOGLE FORMS, RETROALIMENTACIÓN DE ENTREGAS Y HORARIO DE CLASES
# → nucleo/aulaconecta.py (lógica en formularios.py y horario.py)
# =============================================================================
from nucleo.aulaconecta import *  # noqa: F401,F403,E402


# =============================================================================
# 8.2 · OBSERVADOR E INFORMES PARA PADRES (materiales nuevos del aula: tipo Saber, malla del periodo y PIAR → aula.py)
# → nucleo/familia.py (lógica en informes.py)
# =============================================================================
from nucleo.familia import *  # noqa: F401,F403,E402


# =============================================================================
# 8.3 · RESUMEN SEMANAL, PROYECTOS QUE SE REPITEN Y ACTUALIZACIÓN DE NOCHE
# → nucleo/autonomia.py
# =============================================================================
from nucleo.autonomia import *  # noqa: F401,F403,E402


# =============================================================================
# 8.5 · CORREO CON TU CUENTA DE GOOGLE (SIN CONTRASEÑA DE APLICACIÓN)
# → nucleo/gcorreo.py (lógica en gmail.py)
# =============================================================================
from nucleo.gcorreo import *  # noqa: F401,F403,E402


# =============================================================================
# 8.6 · EL PLUS DEL HUD: PANEL «HOY», TARJETAS, PALETA (CTRL+K), SUGERENCIAS Y MODO PROYECTOR
# → nucleo/tablero.py (páginas: templates/hud.html y templates/proyector.html)
# =============================================================================
from nucleo.tablero import *  # noqa: F401,F403,E402


# =============================================================================
# 8.7 · GOOGLE CALENDAR Y DRIVE DIRECTOS, Y EXPORTAR A KAHOOT, QUIZIZZ Y ZETI
# → nucleo/gintegra.py (lógica en gservicios.py y exportar.py)
# =============================================================================
from nucleo.gintegra import *  # noqa: F401,F403,E402


# =============================================================================
# 8.8 · PLANES DE RECUPERACIÓN, DIARIO DE CLASE Y QUIZ EN VIVO EN EL PROYECTOR
# → nucleo/aulavivo.py (lógica en recuperacion.py y diarioclase.py)
# =============================================================================
from nucleo.aulavivo import *  # noqa: F401,F403,E402


# =============================================================================
# 8.9 · DATOS DE ESTUDIANTES CIFRADOS Y COPIA DE SEGURIDAD EN DRIVE
# → nucleo/proteccion.py (lógica en datos.py)
# =============================================================================
from nucleo.proteccion import *  # noqa: F401,F403,E402


# =============================================================================
# 9.3 · ¿QUÉ NECESITA MI ATENCIÓN?, COMPROMISOS, LECTURA NIVELADA Y MATERIAL DESDE UN ENLACE
# → nucleo/atento.py (lógica en atencion.py y compromisos.py; la lectura nivelada en aula.py)
# =============================================================================
from nucleo.atento import *  # noqa: F401,F403,E402


# =============================================================================
# 9.4 · LECCIONES DE TUS CORRECCIONES, VIGILANTE DE PÁGINAS WEB Y MODO TUTOR SOCRÁTICO
# → nucleo/maestro.py (lógica en lecciones.py y paginas.py)
# =============================================================================
from nucleo.maestro import *  # noqa: F401,F403,E402


# =============================================================================
# 9.5 · RESUMEN DE LA MAÑANA EN NOTA DE VOZ, TU ESTILO AL ESCRIBIR Y RETROALIMENTACIÓN DE TEXTOS
# → nucleo/pulido.py (lógica en estilo.py)
# =============================================================================
from nucleo.pulido import *  # noqa: F401,F403,E402


# =============================================================================
# 9.6 · CLASE EN VIVO, TICKET DE SALIDA Y SEMÁFORO CON EL CELULAR, Y ACTIVIDADES QUE FUNCIONARON
# → nucleo/enclase.py (lógica en clasevivo.py y ticket.py; página de los estudiantes: templates/ticket.html)
# =============================================================================
from nucleo.enclase import *  # noqa: F401,F403,E402

# ── 9.7: alertas tempranas, ficha del estudiante y celebraciones
# → nucleo/estudiantes.py (lógica en tendencias.py)
from nucleo.estudiantes import *  # noqa: F401,F403,E402

# ── 9.8: semana lista el domingo, cierre de periodo y bandeja limpia
# → nucleo/semanal.py (lógica en semana.py)
from nucleo.semanal import *  # noqa: F401,F403,E402

# ── 9.9: personalidad según el momento, color del día del reactor y retrospectiva del año
# → nucleo/animado.py (lógica en animo.py y retro.py)
from nucleo.animado import *  # noqa: F401,F403,E402

# ── 10.0: kit para colegas y reuniones de área (agenda y acta)
# → nucleo/colegas.py (lógica en kit.py y reunion.py)
from nucleo.colegas import *  # noqa: F401,F403,E402

# ── 10.2: acumulado del año (VF) y lo que falta para aprobar (VRA), como en Zeti
# → nucleo/acumulado.py (lógica en zeti.py y periodos.py)
from nucleo.acumulado import *  # noqa: F401,F403,E402

# ── 10.4: áreas y asignaturas (notas aparte por asignatura y revisión según el área)
# → nucleo/areas.py (lógica en asignaturas.py)
from nucleo.areas import *  # noqa: F401,F403,E402

# ── 10.5: calificar con el celular (hojas de respuesta), análisis de la evaluación y refuerzo a la medida
# → nucleo/calificar.py (lógica en omr.py y examenes.py; página del celular: templates/calificar.html)
from nucleo.calificar import *  # noqa: F401,F403,E402


# =============================================================================
# ARRANQUE
# =============================================================================
def _port_in_use():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def _prepare_web_server():
    """Ajustes del servidor web interno (Werkzeug), que solo escucha en 127.0.0.1.
    · Arranque instantáneo: el servidor estándar de Python, entre abrir el puerto y empezar
      a escuchar, consulta en la red el nombre del equipo (socket.getfqdn). En Windows,
      con VPN o redes de colegio/empresa, eso puede tardar 30 s o más y el HUD no carga.
      Aquí no hace falta: se usa la dirección tal cual.
    · Sin buscar archivos .env de Flask por las carpetas superiores.
    · Sin el aviso «development server / production» (pensado para webs públicas) ni las
      líneas «GET /static/...» de cada petición."""
    import logging
    import http.server
    import socketserver

    def fast_bind(self):
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name, self.server_port = str(host), port
    http.server.HTTPServer.server_bind = fast_bind
    os.environ["FLASK_SKIP_DOTENV"] = "1"
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    try:
        import flask.cli
        flask.cli.show_server_banner = lambda *a, **k: None   # «* Serving Flask app ...»
    except Exception:
        pass


server_state = {"error": None, "done": threading.Event()}


def _run_server():
    _prepare_web_server()
    try:
        socketio.run(app, host=HOST, port=PORT, debug=False, log_output=False,
                     use_reloader=False, allow_unsafe_werkzeug=True)
    except BaseException as e:                       # antes este fallo era invisible
        server_state["error"] = e
        log_terminal(f"El servidor interno no pudo arrancar en el puerto {PORT}: {e}", "ERROR")
    finally:
        server_state["done"].set()


def _wait_server(timeout=20.0):
    """Espera a que el servidor interno escuche. Devuelve True si está listo."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if server_state["done"].is_set():            # el hilo terminó: falló
            return False
        if _port_busy(PORT):
            dt = time.time() - t0
            if dt > 2:
                log_terminal(f"El servidor interno tardó {dt:.0f} s en arrancar.", "AVISO")
            return True
        time.sleep(0.05)
    log_terminal(f"El servidor interno no responde tras {timeout:.0f} s. El HUD esperará "
                 "a que arranque.", "AVISO")
    return False


def announce_startup(hidden):
    """Confirmación auditiva: útil sobre todo en modo sigilo, cuando no se ve el panel."""
    if not settings["startup_announce"]:
        return
    frase = ("Jarvis en línea, en modo sigilo. Di «mostrar panel» cuando me necesites."
             if hidden else "Jarvis en línea. Sistemas cargados.")
    # Espera a que el audio y, si hace falta, el micrófono estén listos antes de hablar.
    threading.Timer(1.2, lambda: speak(frase, force=True)).start()


def main():
    force_browser = "--browser" in sys.argv
    first_run = not os.path.exists(CONFIG_PATH)
    load_settings()
    if not first_run and not settings["onboarding_done"] and "onboarding_done" not in _file_values:
        settings["onboarding_done"] = True              # ya lo usaba antes de la 7.1: no le salta la bienvenida
    start_hidden = ("--tray" in sys.argv or "--sigilo" in sys.argv
                    or settings["hud_start_hidden"]) and "--mostrar" not in sys.argv

    if SAME_JARVIS_RUNNING:            # ya hay un Jarvis igual abierto: mostrar su HUD y salir
        _boot("Ya hay un Jarvis abierto: muestro su panel (si estaba oculto, pulsa Ctrl+Alt+J).")
        if not (START_LINK and forward_link(START_LINK)):
            _http_text(f"{URL}/api/show", timeout=3)
        return

    _fix_autostart_path()
    skills.configure(output_dir=lambda: settings["output_dir"], hide_hud=_temp_hide,
                     custom=lambda: settings["custom_commands"],
                     talleres_dir=lambda: settings["talleres_dir"],
                     contacts=lambda: settings["contacts"],
                     setting=lambda key: settings.get(key, ""),
                     log=lambda m: log_terminal(m, "PC"))

    # El servidor se abre primero para estar «en línea» cuanto antes; lo pesado (audio, modelo de
    # voz, índice de apps, IA) se carga en segundo plano y no retrasa el arranque.
    threading.Thread(target=_run_server, daemon=True, name="servidor").start()
    server_ready = _wait_server()
    log_terminal(f"Jarvis {VERSION} en línea{' · modo USB portable' if PORTABLE else ''}.", "SISTEMA")
    if "onedrive" in APP_DIR.lower():
        log_terminal("Jarvis está dentro de OneDrive: la sincronización lo vuelve lento al instalar "
                     "y al arrancar. Te recomiendo moverlo a C:\\Jarvis (instalar.bat lo hace por ti).",
                     "AVISO")
    if env_overrides:
        log_terminal(f"Valores tomados de .env: {', '.join(sorted(env_overrides))}.", "SISTEMA")

    if settings["windows_integration"]:
        windows_shell.set_app_id()      # identidad propia en la barra de tareas (antes de crear ventanas)

    def _start_services():
        windows_at_start(START_LINK)      # enlace local, integración con Windows y el enlace de arranque
        learn_start()                     # 7.4: costumbres, historial y tareas programadas
        tools_start()                     # 7.5: habilidades de la comunidad
        agents_start()                    # 7.6: aprobaciones y proyectos
        aula_plus_start()                 # 7.8: seguimiento y banco de preguntas
        reach_start()                     # 7.9: sincronización entre equipos
        health_start()                    # 8.0: registro de errores y revisión tras actualizar
        classroom_plus_start()            # 8.1: horario de clases
        family_start()                    # 8.2: observador del estudiante
        autonomy_start()                  # 8.3: resumen semanal, actualización de noche y vuelta atrás
        hud_plus_start()                  # 8.6: el panel «Hoy» del HUD se actualiza solo
        class_plus_start()                # 8.8: diario de clase y quiz en vivo
        students_start()                  # 8.9: abre los datos de estudiantes cifrados (con la clave ya leída)
        attention_start()                 # 9.3: compromisos y pulso de atención
        teacher_plus_start()              # 9.4: lecciones y vigilante de páginas
        polish_start()                    # 9.5: tu estilo al escribir
        live_class_start()                # 9.6: clase en vivo y banco de actividades
        students_plus_start()             # 9.7: alertas tempranas y celebraciones
        routines98_start()                # 9.8: semana lista, cierre de periodo y bandeja limpia
        mood_start()                      # 9.9: personalidad y color del día
        colleagues_start()                # 10.0: retoma un acta abierta
        zeti_apply()                      # 10.1: pesos y escala de la institución
        year_start()                      # 10.2: valoraciones de los periodos anteriores
        grading_start()                   # 10.5: evaluaciones con hoja de respuestas
        load_memory()
        diario.configure(CONFIG_DIR, settings["diary_enabled"], settings["diary_days"])
        diario.purge()
        skills.start()
        _init_audio()
        if audio_ready:
            threading.Thread(target=_tts_worker, daemon=True).start()
        reschedule()
        set_state(copilot=settings["copilot_enabled"])
        for target in (_command_worker, _voice_worker, schedule_worker, audio_loop, _ai_monitor,
                       hotkey_loop, _timers_worker, _copilot_worker, _notes_worker, _cal_worker,
                       _net_worker, _update_worker, _backup_worker, _telegram_worker, _quake_worker,
                       _routines_worker, _proactive_worker, _watch_worker):
            threading.Thread(target=target, daemon=True).start()
        threading.Thread(target=check_ai, args=(True,), daemon=True).start()
        threading.Thread(target=warm_ai, daemon=True).start()
        announce_startup(start_hidden)      # confirma por voz que el núcleo se cargó
        threading.Timer(4.0, notes_today_summary).start()   # 📌 pendientes de hoy en el HUD
        threading.Timer(9.0, _routines_at_start).start()    # rutina «al iniciar», tras el saludo
        mcp_reconfigure()                                    # conectores MCP
        mcp_server_apply()                                   # Jarvis como servidor MCP (si está activado)
        mobile_apply()                                       # panel del celular (si está activado)
        threading.Timer(20.0, prewarm_voice).start()         # frases frecuentes listas para sonar al instante
        threading.Timer(35.0, mates.preload).start()         # 8.4: SymPy se carga después, sin frenar el arranque
        if not start_hidden:
            threading.Timer(2.5, welcome_at_start).start()   # la primera vez: la bienvenida

    threading.Thread(target=_start_services, daemon=True, name="servicios").start()
    start_tray()
    if start_hidden:
        log_terminal("Arranque en modo sigilo: panel oculto, micrófono activo. "
                     "Di «mostrar panel» o pulsa Ctrl+Alt+J.", "SISTEMA")
    if webview is not None and not force_browser:
        try:
            create_hud(start_hidden, loader=not server_ready)
            webview.start(private_mode=False, storage_path=os.path.join(CONFIG_DIR, "webview"))
            os._exit(0)
        except Exception as e:
            hud["window"] = None
            log_terminal(f"No se pudo abrir la ventana HUD ({e}); uso el navegador.", "AVISO")
    if not start_hidden:
        hud_show()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        import traceback
        _boot("Jarvis se detuvo por un error:\n" + traceback.format_exc())
        raise
