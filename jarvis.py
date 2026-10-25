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
"""

import os
import re
import sys
import json
import time
import uuid
import array
import queue
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

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

VERSION = "5.9"
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
try:
    from piper import PiperVoice
    from piper.config import SynthesisConfig
except Exception:
    PiperVoice = SynthesisConfig = None
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
}

HUD_SIZES = {"orbe": (96, 96), "compacto": (430, 150), "expandido": (440, 620)}
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
    "wake_window": 8,
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
    "update_repo": "",             # repositorio de GitHub con las versiones (usuario/nombre)
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
    "telegram_chat": "",           # chat id a donde enviar
    "spotify_client_id": "",       # opcional: para reproducir por nombre con la API
    "spotify_client_secret": "",
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
SECRET_FIELDS = API_KEY_FIELDS + ("calendar_urls",)
AI_SETTING_KEYS = ({"ai_provider", "ollama_host", "ollama_model", "openai_base_url"}
                   | set(API_KEY_FIELDS) | {f"{p}_model" for p in PROVIDERS})
# Modelos por defecto antiguos que ya no admiten claves nuevas: se migran al actual.
LEGACY_DEFAULT_MODELS = {"gemini_model": ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash")}

RANGES = {
    "tts_rate": (-50, 50), "tts_volume": (-50, 50), "tts_pitch": (-50, 50),
    "wake_window": (3, 30), "history_turns": (0, 30), "ai_temperature": (0.0, 2.0),
    "mic_device": (-1, 999), "hud_opacity": (30, 100),
    "mic_sensitivity": (0, 60), "min_command_chars": (0, 20),
    "hud_x": (-1, 20000), "hud_y": (-1, 20000), "copilot_interval": (1, 60), "notes_notice_min": (0, 240), "calendar_notice_min": (0, 120),
    "camera_index": (0, 9),
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
    choices = {"theme": THEMES, "ai_provider": tuple(PROVIDERS),
               "hud_start_size": HUD_SIZES, "hud_position": HUD_POSITIONS,
               "tts_backend": ("edge", "piper", "gemini"), "stt_backend": ("vosk", "whisper"),
               "gemini_tts_model": ("gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts"),
               "stt_refine": ("auto", "gemini", "whisper", "off"),
               "whisper_model": {k: 1 for k, _ in WHISPER_SIZES}}
    if key in choices and v not in choices[key]:
        raise ValueError("opción desconocida")
    if key == "morning_time":
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", v)
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise ValueError("hora inválida, usa HH:MM")
        v = f"{int(m.group(1)):02d}:{m.group(2)}"
    if key == "update_repo" and v:
        v = actualizar.clean_repo(v)
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
    for k, v in data.items():
        if k in DEFAULT_SETTINGS:
            try:
                settings[k] = _file_values[k] = _validate(k, v)
            except Exception:
                pass
    for k, old in LEGACY_DEFAULT_MODELS.items():
        if settings.get(k) in old:
            settings[k] = DEFAULT_SETTINGS[k]
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
        json.dump(data, f, ensure_ascii=False, indent=2)
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


def push_chat(role, text, source=""):
    item = {"role": role, "text": text, "source": source,
            "time": datetime.datetime.now().strftime("%H:%M")}
    chat_buffer.append(item)
    socketio.emit("chat", item)


# =============================================================================
# ESTADO EN VIVO
# =============================================================================
state = {"net": "online", "mic": "off", "ai": "unknown", "ai_label": "", "tts": "off", "mode": "idle", "copilot": False}
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
# =============================================================================
tts_queue = queue.Queue()
tts_playing = threading.Event()
tts_stop = threading.Event()
tts_gen = {"n": 0}                       # sube al interrumpir: lo que estaba en cola se descarta
tts_now = {"text": ""}                   # frase que suena ahora
tts_recent = deque(maxlen=6)             # (hora, frase) de lo último dicho: filtro de eco al interrumpir
audio_ready = False
from concurrent.futures import ThreadPoolExecutor
_synth_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="voz")


def _init_audio():
    global audio_ready
    if not pygame:
        log_terminal("Pygame no instalado: las respuestas solo se mostrarán en texto.", "AVISO")
        set_state(tts="error")
        return
    if not (edge_tts or PiperVoice or _gemini_for_stt()):
        log_terminal("Ni Edge-TTS ni Piper instalados: las respuestas solo se mostrarán en texto.", "AVISO")
        set_state(tts="error")
        return
    try:
        pygame.mixer.init()
        audio_ready = True
        set_state(tts="ok" if settings["tts_enabled"] else "off")
    except Exception as e:
        set_state(tts="error")
        log_terminal(f"No se pudo iniciar el audio de salida: {e}", "ERROR")


# ---- Piper (voz offline) --------------------------------------------------
_piper_cache = {}
_piper_lock = threading.Lock()


def find_piper_voice():
    """Ruta del modelo .onnx de Piper: el elegido en Ajustes o el primero de recursos\\piper."""
    v = settings["piper_voice"].strip().strip('"')
    if v:
        p = v if os.path.isabs(v) else os.path.join(APP_DIR, v)
        return p if os.path.isfile(p) else None
    for folder in (os.path.join(APP_DIR, "recursos", "piper"),
                   get_resource_path(os.path.join("recursos", "piper"))):
        if os.path.isdir(folder):
            for f in sorted(os.listdir(folder)):
                if f.endswith(".onnx"):
                    return os.path.join(folder, f)
    return None


def _get_piper(model_path):
    with _piper_lock:
        voice = _piper_cache.get(model_path)
        if voice is None:
            voice = PiperVoice.load(model_path)
            _piper_cache.clear()                 # solo un modelo cargado a la vez (memoria)
            _piper_cache[model_path] = voice
        return voice


def _piper_synth(text, path, rate, volume):
    model = find_piper_voice()
    if not model:
        raise RuntimeError("No hay voz de Piper. Ejecuta descargar_voz.py o indícala en Ajustes › Voz.")
    voice = _get_piper(model)
    # rate -50..+50 % -> length_scale (más alto = más lento); volume -50..+50 -> 0.5..1.5
    cfg = SynthesisConfig(length_scale=max(0.5, min(2.0, 1.0 - rate / 100.0)),
                          volume=max(0.1, min(1.5, 1.0 + volume / 100.0)))
    import wave
    with wave.open(path, "wb") as wav:
        voice.synthesize_wav(text, wav, syn_config=cfg)


# ---- Whisper (reconocimiento offline alternativo a Vosk) ------------------
WHISPER_SIZES = [("tiny", "Muy rápido · menos preciso"),
                 ("base", "Equilibrado (recomendado)"),
                 ("small", "Más preciso · más lento")]


def _whisper_installed():
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def _clean_for_speech(text):
    text = text.split("\n")[0]                                   # solo la primera línea
    text = re.sub(r"[A-Za-z]:\\\S+|/\S+/\S+", "", text)          # no leer rutas en voz alta
    return re.sub(r"[*#`_>|«»]", "", text).strip()


def speak(text, voice=None, rate=None, volume=None, pitch=None, force=False, backend=None, gemini=None):
    if not text or not audio_ready:
        return
    if not (settings["tts_enabled"] or force):
        return
    item = {"text": text, "voice": voice, "rate": rate, "volume": volume, "pitch": pitch,
            "backend": backend, "gemini": gemini or {}, "gen": tts_gen["n"]}
    # La voz se genera YA, en paralelo, mientras suena la frase anterior: así no hay
    # pausas entre frases aunque el motor (p. ej. Gemini) tarde un segundo en responder.
    item["future"] = _synth_pool.submit(_synthesize, item)
    tts_queue.put(item)


def _play_file(path, max_seconds=None):
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    t0 = time.time()
    while pygame.mixer.music.get_busy() and not tts_stop.is_set():
        if max_seconds and time.time() - t0 > max_seconds:
            break
        time.sleep(0.03)
    pygame.mixer.music.stop()


def play_sound(path, max_seconds=10):
    """Pone un sonido (p. ej. la sirena de alarma) en la misma cola que la voz."""
    if audio_ready and path:
        tts_queue.put({"sound": path, "max": max_seconds, "gen": tts_gen["n"]})


# ---- Voz de Gemini (muy natural; usa tu clave de Gemini) -------------------
GEMINI_TTS_MODELS = [("gemini-3.8-flash-lite-tts", "Rápida (recomendada)"),
                     ("gemini-3.8-flash-tts", "Máxima calidad, algo más lenta")]
GEMINI_TTS_VOICES = [("Charon", "Informativa"), ("Orus", "Firme"), ("Kore", "Firme"), ("Puck", "Animada"),
                     ("Zephyr", "Brillante"), ("Fenrir", "Entusiasta"), ("Leda", "Juvenil"), ("Aoede", "Ligera"),
                     ("Callirrhoe", "Relajada"), ("Autonoe", "Brillante"), ("Enceladus", "Susurrante"),
                     ("Iapetus", "Clara"), ("Umbriel", "Relajada"), ("Algieba", "Suave"), ("Despina", "Suave"),
                     ("Erinome", "Clara"), ("Algenib", "Grave"), ("Rasalgethi", "Informativa"),
                     ("Laomedeia", "Animada"), ("Achernar", "Suave"), ("Alnilam", "Firme"), ("Schedar", "Pareja"),
                     ("Gacrux", "Madura"), ("Pulcherrima", "Directa"), ("Achird", "Amigable"),
                     ("Zubenelgenubi", "Casual"), ("Vindemiatrix", "Gentil"), ("Sadachbia", "Vivaz"),
                     ("Sadaltager", "Experta"), ("Sulafat", "Cálida")]
VOICE_CACHE_DIR = os.path.join(CONFIG_DIR, "voz_cache")
_gtts = {"pause_until": 0.0, "warned": 0.0}


def _gemini_tts(text, path, over=None):
    """Pide la voz a Gemini (Interactions API) y deja un WAV en path.
    Devuelve la ruta a reproducir (puede ser la de la caché, que no se borra)."""
    import base64
    import hashlib
    cfg = _gemini_for_stt()
    if not cfg:
        raise AIError("Falta la clave de Gemini.", kind="config", why="falta la clave de Gemini")
    if time.time() < _gtts["pause_until"]:
        raise AIError("La voz de Gemini está en pausa.", kind="quota", why="en pausa")
    over = over or {}                                    # valores de «Probar voz» (sin guardar)
    voice = over.get("gemini_tts_voice") or settings["gemini_tts_voice"]
    model = over.get("gemini_tts_model") or settings["gemini_tts_model"]
    style = (over.get("gemini_tts_style", settings["gemini_tts_style"]) or "").strip()
    cacheable = len(text) <= 80                       # frases cortas y repetidas: «¿Sí?», «Hecho.»
    key = hashlib.sha1(f"{model}|{voice}|{style}|{text}".encode("utf-8")).hexdigest()
    cached = os.path.join(VOICE_CACHE_DIR, key + ".wav")
    if cacheable and os.path.exists(cached):
        return cached
    content = {"type": "text", "text": text}
    if style:
        content["annotations"] = [{"type": "speech_metadata", "style": style}]
    body = {"model": model, "input": [{"type": "user_input", "content": [content]}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": voice}]}}
    data = _http("POST", f"{GEMINI_BASE}/interactions", _gemini_headers(cfg), body, timeout=30)
    audio = None
    for step in data.get("steps") or []:
        for c in step.get("content") or []:
            if isinstance(c, dict) and c.get("type") == "audio" and c.get("data"):
                audio = c                                  # el último bloque de audio
    if not audio:
        raise AIError("Gemini no devolvió audio.", kind="bad", why="no devolvió audio")
    raw = base64.b64decode(audio["data"])
    if raw[:4] != b"RIFF":                                 # PCM sin cabecera: se envuelve en WAV
        raw = _wav_bytes(raw, int(audio.get("sample_rate") or 24000))
    with open(path, "wb") as f:
        f.write(raw)
    if cacheable:
        try:
            os.makedirs(VOICE_CACHE_DIR, exist_ok=True)
            files = sorted(os.scandir(VOICE_CACHE_DIR), key=lambda e: e.stat().st_mtime)
            for old in files[:-300]:                       # como mucho 300 frases guardadas
                os.remove(old.path)
            with open(cached, "wb") as f:
                f.write(raw)
        except OSError:
            pass
    return path


def _synthesize(item):
    """Genera el audio de una frase. Devuelve (ruta, borrar_después) o (None, False).
    Si el motor elegido falla, prueba el siguiente: Gemini → Edge → Piper."""
    if item.get("gen") != tts_gen["n"]:
        return None, False                                 # se canceló (interrupción) antes de empezar
    text = _clean_for_speech(item["text"])
    if not text:
        return None, False
    rate = settings["tts_rate"] if item["rate"] is None else int(item["rate"])
    volume = settings["tts_volume"] if item["volume"] is None else int(item["volume"])
    pitch = settings["tts_pitch"] if item["pitch"] is None else int(item["pitch"])
    first = item.get("backend") or settings["tts_backend"]
    order = {"gemini": ["gemini", "edge", "piper"], "edge": ["edge", "piper"], "piper": ["piper", "edge"]}.get(first, ["edge", "piper"])
    if is_offline():
        order = ["piper", "edge"]                          # sin internet: directo a la voz del equipo
    last_err = None
    for b in order:
        try:
            if b == "gemini":
                path = os.path.join(tempfile.gettempdir(), f"jarvis_{uuid.uuid4().hex}.wav")
                out = _gemini_tts(text, path, item.get("gemini"))
                return out, out == path
            if b == "piper":
                if PiperVoice is None:
                    continue
                path = os.path.join(tempfile.gettempdir(), f"jarvis_{uuid.uuid4().hex}.wav")
                _piper_synth(text, path, rate, volume)
                return path, True
            if edge_tts is None:
                continue
            path = os.path.join(tempfile.gettempdir(), f"jarvis_{uuid.uuid4().hex}.mp3")
            voice = item["voice"] or settings["tts_voice"]
            communicate = edge_tts.Communicate(text, voice, rate=f"{rate:+d}%", volume=f"{volume:+d}%",
                                               pitch=f"{pitch:+d}Hz")
            asyncio.run(communicate.save(path))
            return path, True
        except AIError as e:
            last_err = e
            if b == "gemini" and e.why != "en pausa":
                # cuota agotada, sin saldo, clave… : pausa 15 min y avisa una sola vez
                _gtts["pause_until"] = time.time() + (900 if e.kind in ("quota", "balance", "key", "perm", "model", "config") else 60)
                if time.time() - _gtts["warned"] > 900:
                    _gtts["warned"] = time.time()
                    log_terminal(f"La voz de Gemini no está disponible ({e.why}); mientras tanto uso la de Edge.", "AVISO")
        except Exception as e:
            last_err = e
    raise last_err or RuntimeError("no hay motor de voz disponible")


def _tts_worker():
    while True:
        item = tts_queue.get()
        if item.get("gen") != tts_gen["n"]:               # cancelado por una interrupción
            continue
        tts_stop.clear()
        tts_playing.set()
        refresh_mode()
        path, delete = None, False
        try:
            if item.get("sound"):
                _play_file(item["sound"], item.get("max"))
            else:
                path, delete = item["future"].result(timeout=60)
                if path and item.get("gen") == tts_gen["n"]:
                    if settings["tts_enabled"]:
                        set_state(tts="ok")
                    tts_now["text"] = normalize(item["text"])
                    tts_recent.append((time.time(), tts_now["text"]))
                    if not tts_stop.is_set():
                        _play_file(path)
        except Exception as e:
            if item.get("sound"):
                log_terminal(f"No se pudo reproducir el sonido {item['sound']}: {e}", "ERROR")
            else:
                set_state(tts="error")
                log_terminal(f"Fallo en síntesis de voz (revisa la conexión o la voz elegida en Ajustes): {e}", "ERROR")
        finally:
            tts_now["text"] = ""
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass
            if path and delete:
                try:
                    os.remove(path)
                except OSError:
                    pass
            if tts_queue.empty():
                time.sleep(0.4)
                tts_playing.clear()
                refresh_mode()


def stop_speech(log=True):
    tts_gen["n"] += 1                                    # invalida lo que estaba en cola o generándose
    while not tts_queue.empty():
        try:
            tts_queue.get_nowait()
        except queue.Empty:
            break
    tts_stop.set()
    if log:
        log_terminal("Reproducción de audio detenida.", "SISTEMA")


_tl = threading.local()                 # _tl.quiet: este hilo ejecuta una rutina (no hablar cada paso)


def reply(text, origin="JARVIS"):
    log_terminal(text, origin)
    push_chat("jarvis", text, origin)
    if not getattr(_tl, "quiet", False):
        speak(text)


def list_edge_voices():
    async def _fetch():
        return await asyncio.wait_for(edge_tts.list_voices(), timeout=10)

    out = []
    for v in asyncio.run(_fetch()):
        if str(v.get("Locale", "")).startswith("es-"):
            name = v.get("ShortName")
            gender = "femenina" if v.get("Gender") == "Female" else "masculina"
            friendly = name.split("-")[-1].replace("Neural", "").replace("Multilingual", " multilingüe")
            out.append((name, f"{friendly} · {v.get('Locale')} · {gender}"))
    return sorted(out, key=lambda x: (x[0][:5] != "es-CO", x[0]))


# =============================================================================
# CONECTOR DE IA: Ollama, Gemini, Claude y cualquier API compatible con OpenAI
# (ChatGPT, DeepSeek, Kimi, Grok, Mistral, Groq, OpenRouter, LM Studio...)
# =============================================================================
class AIError(Exception):
    """Error de IA con explicación en español.
    why  = motivo corto y claro (se dice en voz alta)
    kind = key | quota | balance | model | region | perm | server | bad | net | config"""

    def __init__(self, msg, code=None, raw="", kind="bad", why=None):
        super().__init__(msg)
        self.code, self.raw, self.kind = code, raw or msg, kind
        self.why = why or msg


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
_SHORT_REASON = {"key": "clave inválida", "quota": "sin cuota", "balance": "sin saldo",
                 "model": "modelo no disponible", "region": "región no admitida",
                 "perm": "sin permiso", "server": "servicio caído", "net": "sin conexión",
                 "config": "falta configurar", "bad": "error"}


def _api_message(body):
    """Saca el mensaje legible de un error JSON de cualquier proveedor."""
    try:
        d = json.loads(body)
    except ValueError:
        return re.sub(r"\s+", " ", body).strip()[:220]
    if isinstance(d, list) and d:
        d = d[0]
    err = d.get("error", d) if isinstance(d, dict) else d
    if isinstance(err, dict):
        return str(err.get("message") or err.get("type") or err)[:300]
    return str(err)[:300]


def _classify(code, body):
    msg = _api_message(body)
    low = f"{msg} {body[:600]}".lower()
    if "location is not supported" in low or ("region" in low and "not supported" in low):
        kind, why = "region", "el servicio no está disponible en tu país o región"
    elif (code == 401 or "api key not valid" in low or "invalid api key" in low
          or "invalid x-api-key" in low or "incorrect api key" in low or "api_key_invalid" in low
          or "invalid_api_key" in low or "authentication" in low or "unauthorized" in low):
        kind, why = "key", "la clave de API no es válida. Revísala o crea una nueva"
    elif (code == 402 or "insufficient balance" in low or "credit balance" in low
          or "insufficient_quota" in low or "billing" in low or "payment" in low):
        kind, why = "balance", "tu cuenta no tiene saldo o crédito disponible"
    elif code == 429 or "quota" in low or "resource_exhausted" in low or "rate limit" in low:
        kind, why = "quota", "se agotó la cuota o hay demasiadas peticiones. Espera un minuto o revisa tu plan"
    elif (code == 404 or "model_not_found" in low or "no longer available" in low
          or ("model" in low and ("not found" in low or "does not exist" in low
                                  or "not available" in low or "not supported" in low
                                  or "no access" in low or "not have access" in low))):
        kind, why = "model", "el modelo elegido no existe o tu cuenta no tiene acceso a él"
    elif code == 403 or "permission" in low:
        kind, why = "perm", "tu clave no tiene permiso. Activa la API en tu cuenta del proveedor"
    elif (code or 0) >= 500 or "overloaded" in low:
        kind, why = "server", "el servicio está caído o saturado en este momento"
    else:
        kind, why = "bad", "el servicio rechazó la petición"
    return kind, why, msg


def _host(url):
    return urllib.parse.urlsplit(url).netloc or url


def _http(method, url, headers=None, payload=None, timeout=120, stream=False):
    """Petición HTTP con errores traducidos. Nunca incluye la URL completa en los mensajes
    (podría llevar una clave)."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    h = {"Content-Type": "application/json", "User-Agent": f"Jarvis/{VERSION}"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        kind, why, msg = _classify(e.code, body)
        raise AIError(f"{why}. (HTTP {e.code}: {msg})", code=e.code, raw=body[:800], kind=kind, why=why)
    except urllib.error.URLError as e:
        raise AIError(f"Sin conexión con {_host(url)}: {e.reason}. Revisa tu internet.",
                      code=0, kind="net", why=f"no hay conexión con {_host(url)}. Revisa tu internet")
    except (TimeoutError, socket.timeout):
        raise AIError(f"{_host(url)} tardó demasiado en responder.", code=0, kind="net",
                      why="el servicio tardó demasiado en responder")
    if stream:
        return r
    with r:
        txt = r.read().decode("utf-8", "replace")
    try:
        return json.loads(txt)
    except ValueError:
        raise AIError(f"Respuesta no válida de {_host(url)}: {txt[:150]}")


def _http_json(method, url, api_key="", payload=None, timeout=120):
    """Compatibilidad con código antiguo."""
    return _http(method, url, {"Authorization": f"Bearer {api_key}"} if api_key else None,
                 payload, timeout)


def _drop_path(obj, path):
    obj = json.loads(json.dumps(obj))
    cur, parts = obj, path.split(".")
    for p in parts[:-1]:
        cur = cur.get(p) if isinstance(cur, dict) else None
        if cur is None:
            return obj
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)
    return obj


def _post(url, headers, payload, optional=(), timeout=180, stream=False):
    """POST que se adapta: si el proveedor rechaza un parámetro opcional (temperatura,
    modo JSON, «pensamiento»...), lo quita y reintenta una vez."""
    try:
        return _http("POST", url, headers, payload, timeout, stream)
    except AIError as e:
        if e.code != 400 or e.kind != "bad":
            raise
        low = e.raw.lower()
        drop = [p for p, words in optional if any(w in low for w in words)]
        if not drop and any(w in low for w in ("unsupported", "not supported", "unknown",
                                                "unrecognized", "invalid", "extra", "not allowed")):
            drop = [p for p, _ in optional]
        if not drop:
            raise
        for p in drop:
            payload = _drop_path(payload, p)
        log_terminal(f"{_host(url)} no acepta {', '.join(p.split('.')[-1] for p in drop)}; "
                     "reintento sin ello.", "IA")
        return _http("POST", url, headers, payload, timeout, stream)


def _sse_lines(resp):
    """Recorre las líneas «data: ...» de una respuesta en streaming (SSE)."""
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk and chunk != "[DONE]":
                    yield chunk


def _png_b64(path):
    import base64
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _model_name(m):
    for key in ("model", "name"):
        v = m.get(key) if isinstance(m, dict) else getattr(m, key, None)
        if v:
            return str(v)
    return ""


def _ai_cfg(override=None):
    """Configuración efectiva del proveedor (los valores de «override» vienen de la página
    de Ajustes al pulsar «Probar»; los vacíos se toman de lo guardado)."""
    o = {k: v for k, v in (override or {}).items() if v not in (None, "")}
    pid = str(o.get("ai_provider") or settings["ai_provider"])
    if pid not in PROVIDERS:
        pid = "ollama"
    sp = PROVIDERS[pid]

    def get(k):
        return str(o.get(k, settings.get(k, "")) or "").strip()

    base = get("openai_base_url") if sp.get("custom") else sp.get("base", "")
    if override is None and pid != "ollama" and is_offline() and net["local_model"]:
        # sin internet: la IA de tu equipo (Ollama) responde mientras vuelve la conexión
        return dict(_ai_cfg({"ai_provider": "ollama", "ollama_model": net["local_model"]}),
                    label="Ollama (sin internet)", offline=True)
    return {"ai_provider": pid, "kind": sp["kind"], "spec": sp, "label": sp["short"],
            "model": get(f"{pid}_model"), "key": "" if pid == "ollama" else get(f"{pid}_api_key"),
            "base": base.rstrip("/"),
            "ollama_host": get("ollama_host").rstrip("/") or DEFAULT_SETTINGS["ollama_host"]}


def _need_key(cfg):
    if cfg["kind"] != "ollama" and not cfg["spec"].get("custom") and not cfg["key"]:
        raise AIError(f"Falta la clave de API de {cfg['label']} (Ajustes › IA).", kind="config",
                      why=f"falta poner la clave de {cfg['label']} en Ajustes, sección IA")


# ---- Gemini (Google) --------------------------------------------------------
def _gemini_headers(cfg):
    return {"x-goog-api-key": cfg["key"]}          # la clave va en cabecera, no en la URL


def _gemini_body(cfg, messages, max_tokens, json_mode=False, image_path=None,
                 audio_wav=None, temperature=None):
    system = " ".join(m["content"] for m in messages if m["role"] == "system")
    contents = []
    for m in messages:
        if m["role"] == "system":
            continue
        role = "model" if m["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    if image_path:
        if not contents:
            contents.append({"role": "user", "parts": []})
        contents[-1]["parts"].append({"inlineData": {"mimeType": "image/png", "data": _png_b64(image_path)}})
    if audio_wav:
        import base64
        if not contents:
            contents.append({"role": "user", "parts": []})
        contents[-1]["parts"].append({"inlineData": {"mimeType": "audio/wav",
                                                     "data": base64.b64encode(audio_wav).decode()}})
    gen = {"temperature": settings["ai_temperature"] if temperature is None else temperature,
           "maxOutputTokens": max_tokens}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    # «Pensamiento»: consume tokens de salida y retrasa la respuesta. Para hablar conviene
    # poco: Gemini 2.x flash se apaga (presupuesto 0); Gemini 3 flash en nivel bajo. Los
    # flash-lite ya vienen al mínimo y los pro piensan siempre. Si el modelo no acepta
    # este ajuste, _post lo quita solo.
    ml = cfg["model"].lower()
    if re.match(r"gemini-[12]\.", ml):
        if "flash" in ml:
            gen["thinkingConfig"] = {"thinkingBudget": 0}
    elif "flash" in ml and "lite" not in ml:
        gen["thinkingConfig"] = {"thinkingLevel": "low"}
    body = {"contents": contents, "generationConfig": gen}
    if system.strip():
        body["systemInstruction"] = {"parts": [{"text": system}]}
    return body


_GEMINI_OPTIONAL = (("generationConfig.thinkingConfig", ("thinking",)),
                    ("generationConfig.responseMimeType", ("mime",)),
                    ("generationConfig.temperature", ("temperature",)))


def _gemini_text(data, strip=True):
    if isinstance(data, dict) and data.get("error"):
        kind, why, msg = _classify(data["error"].get("code"), json.dumps(data))
        raise AIError(f"Gemini: {msg}", kind=kind, why=why)
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return ""
    txt = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return txt.strip() if strip else txt


def gemini_chat(cfg, messages, json_mode=False, max_tokens=2048, image_path=None):
    url = f"{GEMINI_BASE}/models/{cfg['model']}:generateContent"
    data = _post(url, _gemini_headers(cfg),
                 _gemini_body(cfg, messages, max_tokens, json_mode, image_path), _GEMINI_OPTIONAL)
    return _gemini_text(data)


def gemini_stream(cfg, messages, image_path=None):
    url = f"{GEMINI_BASE}/models/{cfg['model']}:streamGenerateContent?alt=sse"
    resp = _post(url, _gemini_headers(cfg), _gemini_body(cfg, messages, 2048, image_path=image_path),
                 _GEMINI_OPTIONAL, stream=True)

    def it():
        for chunk in _sse_lines(resp):
            try:
                txt = _gemini_text(json.loads(chunk), strip=False)
            except ValueError:
                continue
            if txt:
                yield txt
    return it()


# ---- Claude (Anthropic) -----------------------------------------------------
def _anthropic_headers(cfg):
    return {"x-api-key": cfg["key"], "anthropic-version": "2023-06-01"}


def _anthropic_body(cfg, messages, max_tokens, image_path=None, stream=False):
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    conv = []
    for m in messages:                       # Claude exige turnos alternos usuario/asistente
        if m["role"] == "system":
            continue
        role = "assistant" if m["role"] == "assistant" else "user"
        if conv and conv[-1]["role"] == role:
            conv[-1]["content"][0]["text"] += "\n" + m["content"]
        else:
            conv.append({"role": role, "content": [{"type": "text", "text": m["content"]}]})
    if conv and conv[0]["role"] == "assistant":
        conv.insert(0, {"role": "user", "content": [{"type": "text", "text": "(continuamos)"}]})
    if image_path and conv:
        conv[-1]["content"].insert(0, {"type": "image", "source": {
            "type": "base64", "media_type": "image/png", "data": _png_b64(image_path)}})
    # Sin «temperature»: los modelos Claude actuales la rechazan si no es la de fábrica.
    body = {"model": cfg["model"], "max_tokens": max_tokens, "messages": conv}
    if system:
        body["system"] = system
    if stream:
        body["stream"] = True
    return body


def anthropic_chat(cfg, messages, max_tokens=1024, image_path=None):
    data = _post(cfg["base"] + "/messages", _anthropic_headers(cfg),
                 _anthropic_body(cfg, messages, max_tokens, image_path))
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()


def anthropic_stream(cfg, messages, image_path=None):
    resp = _post(cfg["base"] + "/messages", _anthropic_headers(cfg),
                 _anthropic_body(cfg, messages, 1024, image_path, stream=True), stream=True)

    def it():
        for chunk in _sse_lines(resp):
            try:
                ev = json.loads(chunk)
            except ValueError:
                continue
            if ev.get("type") == "error":
                kind, why, msg = _classify(None, chunk)
                raise AIError(f"Claude: {msg}", kind=kind, why=why)
            d = ev.get("delta") or {}
            if ev.get("type") == "content_block_delta" and d.get("type") == "text_delta" and d.get("text"):
                yield d["text"]
    return it()


# ---- APIs compatibles con OpenAI ----------------------------------------------
def _oa_headers(cfg):
    h = {"Authorization": f"Bearer {cfg['key']}"} if cfg["key"] else {}
    if cfg["ai_provider"] == "openrouter":
        h["X-Title"] = "Jarvis"
    return h


def _oa_body(cfg, messages, max_tokens, json_mode=False, stream=False, image_path=None):
    sp = cfg["spec"]
    msgs = [dict(m) for m in messages]
    if image_path and msgs:
        msgs[-1]["content"] = [{"type": "text", "text": msgs[-1]["content"]},
                               {"type": "image_url",
                                "image_url": {"url": "data:image/png;base64," + _png_b64(image_path)}}]
    tp = sp.get("tokens_param", "max_tokens")
    body = {"model": cfg["model"], "messages": msgs, tp: max_tokens}
    if not sp.get("no_temp"):
        body["temperature"] = settings["ai_temperature"]
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if stream:
        body["stream"] = True
    return body, (("temperature", ("temperature",)), ("response_format", ("response_format", "json")),
                  (tp, (tp,)))


def openai_chat(cfg, messages, json_mode=False, max_tokens=1024, image_path=None):
    body, opt = _oa_body(cfg, messages, max_tokens, json_mode, image_path=image_path)
    data = _post(cfg["base"] + "/chat/completions", _oa_headers(cfg), body, opt)
    try:
        return (data["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError):
        raise AIError(f"Respuesta inesperada de {cfg['label']}: {str(data)[:200]}")


def openai_stream(cfg, messages, image_path=None):
    body, opt = _oa_body(cfg, messages, 1024, stream=True, image_path=image_path)
    resp = _post(cfg["base"] + "/chat/completions", _oa_headers(cfg), body, opt, stream=True)

    def it():
        for chunk in _sse_lines(resp):
            try:
                d = json.loads(chunk)
            except ValueError:
                continue
            if d.get("error"):
                kind, why, msg = _classify(None, chunk)
                raise AIError(f"{cfg['label']}: {msg}", kind=kind, why=why)
            for ch in d.get("choices") or []:
                txt = (ch.get("delta") or {}).get("content")
                if txt:
                    yield txt
    return it()


# ---- Lista de modelos y elección automática -----------------------------------
def ai_list_models(cfg):
    kind = cfg["kind"]
    if kind == "ollama":
        if ollama is None:
            raise AIError("Falta la librería 'ollama' (pip install ollama).", kind="config")
        try:
            resp = ollama.Client(host=cfg["ollama_host"], timeout=8).list()
        except Exception as e:
            raise AIError(f"Ollama no responde en {cfg['ollama_host']}: {e}", kind="net",
                          why="Ollama no está abierto en este equipo")
        models = resp.models if hasattr(resp, "models") else resp["models"]
        return sorted(filter(None, (_model_name(m) for m in models)))
    _need_key(cfg)
    if kind == "gemini":
        data = _http("GET", f"{GEMINI_BASE}/models?pageSize=200", _gemini_headers(cfg), timeout=10)
        out = []
        for m in data.get("models", []):
            name = (m.get("name") or "").replace("models/", "")
            if ("generateContent" in (m.get("supportedGenerationMethods") or [])
                    and name.startswith("gemini") and not MODEL_EXCLUDE.search(name)):
                out.append(name)
        return sorted(set(out))
    if kind == "anthropic":
        data = _http("GET", cfg["base"] + "/models?limit=100", _anthropic_headers(cfg), timeout=10)
        return sorted(m["id"] for m in data.get("data", []) if m.get("id"))
    data = _http("GET", cfg["base"] + "/models", _oa_headers(cfg), timeout=10)
    items = data.get("data", data if isinstance(data, list) else [])
    ids = [m.get("id", "") for m in items if isinstance(m, dict)]
    return sorted(i for i in ids if i and not MODEL_EXCLUDE.search(i))


def _version_key(name):
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", name)[:3]]
    unstable = bool(re.search(r"preview|exp|beta|alpha|\d{4}-\d{2}|\d{8}", name))
    return (not unstable, nums, -len(name))


def _recommend_model(pid, models, exclude=()):
    """El modelo más adecuado para hablar entre los que tiene tu cuenta."""
    sp = PROVIDERS[pid]
    models = [m for m in models if m not in exclude]
    if not models:
        return ""
    if sp.get("model") in models:
        return sp["model"]
    for pat in sp.get("prefer", []):
        cands = [m for m in models if re.search(pat, m)]
        if cands:
            return max(cands, key=_version_key)
    return "" if sp["kind"] == "ollama" else models[0]


def _switch_model(cfg, new, reason):
    key = f"{cfg['ai_provider']}_model"
    old = settings.get(key, "")
    with settings_lock:
        settings[key] = new
        try:
            save_settings_file()
        except Exception:
            pass
    log_terminal(f"{cfg['label']}: uso el modelo «{new}» en vez de «{old or 'ninguno'}» ({reason}).", "IA")
    try:
        socketio.emit("settings_updated", public_settings())
    except Exception:
        pass
    return dict(cfg, model=new)


def _ensure_model(cfg):
    """Si no hay modelo elegido, toma el mejor de la cuenta."""
    if cfg["model"] or cfg["kind"] == "ollama":
        return cfg
    best = _recommend_model(cfg["ai_provider"], ai_list_models(cfg))
    if not best:
        raise AIError("No hay modelo seleccionado. Elige uno en Ajustes › IA.", kind="config",
                      why="no hay modelo elegido. Elige uno en Ajustes, sección IA")
    return _switch_model(cfg, best, "no había ninguno elegido")


def _with_fallback(cfg, fn):
    """Ejecuta fn(cfg). Si el modelo no existe o la cuenta no tiene acceso (p. ej. Gemini 2.5
    con claves nuevas), cambia solo al mejor modelo disponible y reintenta."""
    cfg = _ensure_model(cfg)
    try:
        return fn(cfg)
    except AIError as e:
        if e.kind != "model" or cfg["kind"] == "ollama":
            raise
        try:
            models = ai_list_models(cfg)
        except AIError:
            raise e
        best = _recommend_model(cfg["ai_provider"], models, exclude=(cfg["model"],))
        if not best:
            raise
        return fn(_switch_model(cfg, best, "el anterior no está disponible para tu cuenta"))


def _cloud_chat(cfg, messages, json_mode=False, image_path=None, max_tokens=None):
    tokens = max_tokens or (1024 if json_mode else 2048)
    if cfg["kind"] == "gemini":
        return gemini_chat(cfg, messages, json_mode, tokens, image_path)
    if cfg["kind"] == "anthropic":
        return anthropic_chat(cfg, messages, tokens, image_path)
    return openai_chat(cfg, messages, json_mode, tokens, image_path)


def _cloud_stream(cfg, messages, image_path=None):
    if cfg["kind"] == "gemini":
        return gemini_stream(cfg, messages, image_path)
    if cfg["kind"] == "anthropic":
        return anthropic_stream(cfg, messages, image_path)
    return openai_stream(cfg, messages, image_path)


def _current_model(cfg):
    return cfg["model"]


def ai_chat(messages, json_mode=False, max_tokens=None):
    global thinking
    cfg = _ai_cfg()
    if cfg["kind"] == "ollama" and not cfg["model"]:
        raise AIError("No hay modelo seleccionado. Elige uno en Ajustes › IA.", kind="config",
                      why="no hay modelo elegido. Elige uno en Ajustes, sección IA")
    thinking += 1
    refresh_mode()
    try:
        if cfg["kind"] == "ollama":
            if ollama is None:
                raise AIError("Falta la librería 'ollama'.", kind="config")
            kwargs = {"format": "json"} if json_mode else {}
            # keep_alive mantiene el modelo cargado en RAM (no se recarga en cada orden);
            # num_predict limita la longitud -> responde/habla antes.
            opts = {"temperature": settings["ai_temperature"],
                    "num_predict": max_tokens or (120 if json_mode else 220)}
            try:
                r = ollama.Client(host=cfg["ollama_host"], timeout=180).chat(
                    model=cfg["model"], messages=messages, options=opts, keep_alive="30m", **kwargs)
            except Exception as e:
                raise AIError(str(e), kind="net", why="Ollama no responde")
            return r["message"]["content"].strip()
        _need_key(cfg)
        try:
            return _with_fallback(cfg, lambda c: _cloud_chat(c, messages, json_mode, max_tokens=max_tokens))
        except AIError as e:
            # Se cayó el internet a mitad de la petición: se repite con la IA del equipo.
            if e.kind == "net" and net_recheck() and _ai_cfg()["kind"] == "ollama":
                log_terminal("Sin internet: respondo con la IA de tu equipo.", "RED")
                return ai_chat(messages, json_mode, max_tokens)
            raise
    finally:
        thinking -= 1
        refresh_mode()


def ai_test(override=None):
    """Prueba REAL: lista modelos y además pide una respuesta corta. Así «conectado»
    significa que Jarvis podrá contestar, no solo que la clave abre la lista."""
    cfg = _ai_cfg(override)
    models = ai_list_models(cfg)
    rec = _recommend_model(cfg["ai_provider"], models) if models else ""
    model = cfg["model"] or rec
    if not model:
        return {"models": models, "recommended": rec, "test_ok": False,
                "test_msg": "No hay modelos disponibles."}
    msgs = [{"role": "user", "content": "Responde solo con la palabra: listo"}]
    t0 = time.time()
    try:
        if cfg["kind"] == "ollama":
            out = ollama.Client(host=cfg["ollama_host"], timeout=60).chat(
                model=model, messages=msgs, options={"num_predict": 8})["message"]["content"]
        else:
            out = _cloud_chat(dict(cfg, model=model), msgs)
        return {"models": models, "recommended": rec, "model": model, "test_ok": True,
                "test_msg": f"responde bien con «{model}» ({time.time() - t0:.1f} s): «{out.strip()[:40]}»"}
    except Exception as e:
        why = getattr(e, "why", str(e))
        res = {"models": models, "recommended": rec, "model": model, "test_ok": False,
               "test_msg": f"la lista abre, pero «{model}» no responde: {why}."}
        if getattr(e, "kind", "") == "model":
            alt = _recommend_model(cfg["ai_provider"], models, exclude=(model,))
            if alt:
                try:
                    _cloud_chat(dict(cfg, model=alt), msgs)
                    res.update(suggest=alt, test_msg=res["test_msg"] + f" «{alt}» sí funciona: lo dejo elegido.")
                except Exception:
                    pass
        return res


def check_ai(verbose=False):
    cfg = _ai_cfg()
    label = cfg["label"]
    try:
        models = ai_list_models(cfg)
    except AIError as e:
        if e.code == 404 and cfg["kind"] != "ollama":   # el servicio no publica su lista
            set_state(ai="ok", ai_label=f"{label} · {cfg['model'] or 'auto'}")
            return True
        set_state(ai="error", ai_label=f"{label} · {_SHORT_REASON.get(e.kind, 'sin conexión')}")
        if verbose:
            log_terminal(f"{label}: {e}", "AVISO")
        return False
    model = cfg["model"]
    present = bool(model) and any(m == model or m.startswith(model + ":") for m in models)
    if not present and cfg["kind"] != "ollama" and models:
        best = _recommend_model(cfg["ai_provider"], models)
        if best and best != model:
            _switch_model(cfg, best, "el elegido no está en tu cuenta" if model else "no había ninguno elegido")
            model, present = best, True
        elif cfg["ai_provider"] == "openrouter" and model:
            present = True                              # «openrouter/auto» no sale en la lista
    if present:
        set_state(ai="ok", ai_label=f"{label} · {model}")
    else:
        set_state(ai="warn", ai_label=f"{label} · falta modelo")
        if verbose:
            hint = f" Ejecuta: ollama pull {model}" if cfg["kind"] == "ollama" and model else ""
            log_terminal(f"El modelo '{model or '(ninguno)'}' no está disponible.{hint}", "AVISO")
    return present


def _ai_monitor():
    while True:
        time.sleep(60)
        check_ai()

# =============================================================================
# SIN INTERNET: Jarvis sigue funcionando solo. Si se cae la conexión, la IA pasa a
# Ollama (en tu equipo), la voz a Piper y la escucha a lo local. Cuando vuelve, regresa.
# =============================================================================
net = {"offline": False, "since": 0.0, "fails": 0, "local_model": "", "local_at": 0.0}
_net_lock = threading.Lock()
NET_PROBES = (("1.1.1.1", 443), ("8.8.8.8", 53), ("208.67.222.222", 443))
NET_HTTP_PROBE = "http://www.msftconnecttest.com/connecttest.txt"   # la misma que usa Windows


def _internet_ok():
    """¿Hay internet? Primero conexiones directas (rápidas); si fallan, una petición web
    normal, que sí pasa por el proxy del colegio si lo hay."""
    for host, port in NET_PROBES:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            pass
    try:
        with urllib.request.urlopen(NET_HTTP_PROBE, timeout=4) as r:
            return r.status < 500
    except Exception:
        return False


def local_ai_model(refresh=False):
    """Modelo de Ollama instalado en este equipo para usar sin internet ('' si no hay)."""
    if not refresh and time.time() - net["local_at"] < 120:
        return net["local_model"]
    model = ""
    try:
        if ollama is not None:
            names = ai_list_models(_ai_cfg({"ai_provider": "ollama"}))
            names = [n for n in names if "embed" not in n.lower()]

            def present(m):
                return next((n for n in names if m and (n == m or n.startswith(m + ":"))), "")
            model = (present(settings["offline_model"].strip()) or present(settings["ollama_model"].strip())
                     or (names[0] if names else ""))
    except Exception:
        model = ""
    net.update(local_model=model, local_at=time.time())
    return model


def is_offline():
    return net["offline"] and settings["offline_auto"]


def _net_set(online):
    with _net_lock:
        if online:
            net["fails"] = 0
            if not net["offline"]:
                return False
            mins = (time.time() - net["since"]) / 60
            net.update(offline=False)
        else:
            net["fails"] += 1
            if net["offline"] or net["fails"] < 2:    # 2 fallos seguidos: evita falsas alarmas
                return False
            net.update(offline=True, since=time.time())
    if online:
        log_terminal(f"Volvió el internet (estuvo caído {mins:.0f} min).", "RED")
        set_state(net="online")
        threading.Thread(target=check_ai, daemon=True).start()
        if settings["offline_auto"] and settings["ai_provider"] != "ollama":
            reply(f"Volvió el internet. Vuelvo a usar {_ai_cfg()['label']}.", "RED")
        return True
    set_state(net="offline")
    log_terminal("Sin internet.", "RED")
    if not settings["offline_auto"]:
        return True
    m = local_ai_model(refresh=True)
    threading.Thread(target=check_ai, daemon=True).start()
    if settings["ai_provider"] == "ollama":
        msg = "Se cayó el internet. Sigo funcionando normal con la IA de tu equipo."
    elif m:
        msg = f"Se cayó el internet. Sigo funcionando sin conexión, con la IA de tu equipo ({m.split(':')[0]})."
    else:
        msg = ("Se cayó el internet. Las órdenes del computador siguen funcionando, pero para "
               "responder preguntas necesito internet o una IA local con Ollama.")
    reply(msg, "RED")
    return True


def net_recheck():
    """Tras un error de red en una petición: comprueba ya. True si estamos sin internet."""
    if not settings["offline_auto"]:
        return False
    if _internet_ok():
        _net_set(True)
        return False
    net["fails"] = max(net["fails"], 1)               # el error de la petición cuenta como un fallo
    _net_set(False)
    return net["offline"]


def _net_worker():
    while True:
        time.sleep(10 if net["offline"] else 20)
        try:
            _net_set(_internet_ok())
        except Exception as e:
            log_terminal(f"Comprobación de red: {e}", "AVISO")



def warm_ai():
    """Carga el modelo en memoria al arrancar para que la primera orden sea rápida."""
    cfg = _ai_cfg()
    if cfg["kind"] != "ollama" or ollama is None or not cfg["model"]:
        return
    try:
        ollama.Client(host=cfg["ollama_host"], timeout=120).chat(
            model=cfg["model"], messages=[{"role": "user", "content": "hola"}],
            options={"num_predict": 1}, keep_alive="30m")
        log_terminal("Modelo de IA precargado y listo.", "SISTEMA")
    except Exception:
        pass


def ai_error_reply(e):
    """Frase hablada cuando la IA falla: dice el motivo real, no un genérico."""
    cfg = _ai_cfg()
    why = getattr(e, "why", "") or "no respondió"
    return f"No pude usar {cfg['label']}: {why}."


chat_history = []
MEMORY_PATH = os.path.join(CONFIG_DIR, "memoria.json")


def load_memory():
    try:
        with open(MEMORY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            chat_history[:] = [m for m in data if isinstance(m, dict) and "role" in m and "content" in m][-40:]
    except (FileNotFoundError, ValueError, OSError):
        pass


def save_memory():
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = MEMORY_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(chat_history[-40:], f, ensure_ascii=False)
        os.replace(tmp, MEMORY_PATH)
    except OSError:
        pass


def clear_memory():
    chat_history.clear()
    try:
        os.remove(MEMORY_PATH)
    except OSError:
        pass


# Resumen de todo lo que Jarvis sabe hacer (para mostrarlo en Ajustes › Acerca de).
CAPABILITIES = [
    ("Control del PC", ["abre Spotify", "cierra esto", "cambia a Excel", "minimiza todo", "pantalla completa", "¿qué ventanas hay?"]),
    ("Leer en voz alta", ["selecciona un texto y di: lee esto", "léeme la selección"]),
    ("Audio y música", ["sube el volumen", "volumen al 30", "silencio", "pausa", "siguiente canción"]),
    ("Clase y presentaciones", ["siguiente diapositiva", "inicia la presentación", "activa el videobeam", "abre el taller de estadística"]),
    ("Dictado por voz", ["inicia el dictado", "modo matemáticas", "marca la casilla", "siguiente campo", "terminar dictado"]),
    ("Matemáticas", ["cuánto es el 15% de 240", "resuelve 2x+3=7", "deriva x al cuadrado", "factoriza x al cuadrado menos 4"]),
    ("Temporizadores", ["pon un temporizador de 15 minutos para el examen", "cuánto queda", "cancela el temporizador"]),
    ("Recordatorios y rutinas", ["recuérdame en 10 minutos sacar la ropa", "reporte matutino"]),
    ("Documentos", ["crear documento STEAM sobre energía solar", "numerología 15/08/1990"]),
    ("Web y búsquedas", ["busca recetas de arepas", "pon Despacito en YouTube", "abre youtube"]),
    ("Visión de pantalla", ["¿qué hay en la pantalla?", "describe la pantalla", "qué ves"]),
    ("Rutinas", ["modo clase", "fin de clase", "modo planeación", "¿qué rutinas tengo?",
                 "silencia las notificaciones", "activa las notificaciones"]),
    ("Calendario", ["¿qué tengo hoy?", "¿cuál es mi próxima clase?", "¿qué sigue?", "¿qué tengo esta semana?",
                    "actualiza el calendario"]),
    ("Memoria", ["recuerda que la reunión de padres es el jueves a las 3", "anota que debo comprar marcadores",
                 "¿qué tengo pendiente?", "¿qué tengo mañana?", "ya hice lo de los marcadores",
                 "borra la nota de la reunión", "¿cuándo era la reunión de padres?"]),
    ("Aula", ["escoge un estudiante", "¿quién pasa al tablero?", "haz grupos de 4", "haz parejas",
              "llama a lista", "falta Juan", "guarda la asistencia", "usa el curso 7A",
              "activa el semáforo de ruido", "abre el tablero"]),
    ("Revisar trabajos", ["revisa el taller de Juan (muéstralo a la cámara)",
                          "califica este examen en la pantalla", "corrige la tarea de Sofía"]),
    ("Material de clase (Word)", ["crea un quiz de 10 preguntas sobre fracciones para séptimo",
                                  "hazme un taller de ecuaciones para grado 8",
                                  "prepara una rúbrica para exposiciones orales",
                                  "haz un plan de clase sobre el ciclo del agua"]),
    ("Ayuda con tu pantalla", ["ayúdame con esto", "¿qué me sugieres?", "revisa lo que estoy haciendo",
                               "activa el copiloto", "copiloto cada 10 minutos", "desactiva el copiloto"]),
    ("Música (Spotify)", ["reproduce Despacito en Spotify", "pausa Spotify", "siguiente en Spotify"]),
    ("Mensajería", ["manda un whatsapp a Juan que llego tarde", "manda un telegram diciendo reunión a las 3"]),
    ("Pantalla y archivos", ["toma una captura de pantalla", "busca el archivo informe", "brillo al 70"]),
    ("Modo sigilo", ["modo sigilo", "mostrar panel"]),
    ("Sistema (piden confirmación)", ["bloquea el equipo", "apaga el equipo", "vacía la papelera"]),
    ("Inteligencia artificial", ["cualquier pregunta: ¿cuál es la capital de Francia?", "escríbeme un poema"]),
]


ROUTER_PROMPT = """

Además controlas este PC con Windows mediante estas acciones:
{skills}

Responde SIEMPRE con un único objeto JSON con este formato:
{{"accion": "nombre_de_la_accion o chat", "args": {{...}}, "respuesta": "texto"}}
- Si el usuario pide hacer algo en el PC que corresponde a una acción, pon su nombre en "accion" y sus datos en "args".
- Si es una pregunta o una conversación, usa "accion": "chat" y escribe tu respuesta en "respuesta".
- No inventes acciones que no estén en la lista."""


def _extract_json(text):
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def ask_ai(prompt, route=False):
    """Devuelve ('chat', respuesta) o ('skill', nombre, args)."""
    system = settings["system_prompt"] + ACTION_RULE + VOICE_RULE + f" Hoy es {fecha_hablada(datetime.date.today())}." + _notes_ctx()
    if route:
        # Seguridad: la IA solo ve acciones NO destructivas. Apagar, reiniciar, vaciar la
        # papelera, etc. nunca se activan por interpretación: solo con la orden directa exacta.
        safe = "\n".join(s.describe() for s in skills.REGISTRY.values() if not s.dangerous)
        system += ROUTER_PROMPT.format(skills=safe)
    user_msg = {"role": "user", "content": prompt}
    keep = settings["history_turns"] * 2
    history = chat_history[-keep:] if keep else []
    try:
        raw = ai_chat([{"role": "system", "content": system}, *history, user_msg], json_mode=route)
    except AIError as e:
        log_terminal(f"Error de IA: {e}", "ERROR")
        threading.Thread(target=check_ai, daemon=True).start()
        return ("chat", ai_error_reply(e))

    answer = raw
    if route:
        try:
            data = _extract_json(raw)
        except Exception:
            data = {"accion": "chat", "respuesta": raw}
        if not isinstance(data, dict):
            data = {"accion": "chat", "respuesta": str(data)}
        action = str(data.get("accion") or "chat").strip()
        args = data.get("args") if isinstance(data.get("args"), dict) else {}
        sk = skills.REGISTRY.get(action)
        if sk and sk.dangerous:
            # Blindaje: nunca ejecutar acciones destructivas elegidas por la IA.
            log_terminal(f"IA propuso una acción peligrosa ({action}); la ignoro por seguridad.", "AVISO")
            sk = None
            action = "chat"
        if sk:
            chat_history.extend([user_msg, {"role": "assistant", "content": f"(ejecuté la acción {action})"}])
            del chat_history[:-max(keep, 2)]
            save_memory()
            return ("skill", action, args)
        answer = str(data.get("respuesta") or "").strip() or "No estoy seguro de cómo ayudarte con eso."

    chat_history.extend([user_msg, {"role": "assistant", "content": answer}])
    del chat_history[:-max(keep, 2)]
    save_memory()
    return ("chat", answer)


# Preguntas claras: se responden en streaming (Jarvis habla la 1ª frase mientras genera el resto).
QUESTION_RE = re.compile(
    r"\b(?:que|quien|quienes|cual|cuales|como|cuando|donde|por que|para que|cuanto|cuanta|cuantos|"
    r"explica|explicame|define|definicion|dime|cuentame|hablame|resume|resumen|traduce|significa|"
    r"sabes|conoces|describe|diferencia)\b")
_SENT_END = re.compile(r"[.!?…:](\s|$)")


def _stream_chunks(cfg, msgs):
    """Fragmentos de texto del proveedor actual, a medida que se generan.
    La conexión se abre ya (así, si el modelo no existe, se cambia por otro antes de hablar)."""
    if cfg["kind"] != "ollama":
        _need_key(cfg)
        return _with_fallback(cfg, lambda c: _cloud_stream(c, msgs))

    def oll():
        stream = ollama.Client(host=cfg["ollama_host"], timeout=180).chat(
            model=cfg["model"], messages=msgs, stream=True, keep_alive="30m",
            options={"temperature": settings["ai_temperature"], "num_predict": 240})
        for part in stream:
            chunk = (part.get("message") or {}).get("content", "")
            if chunk:
                yield chunk
    return oll()


def answer_question_streaming(prompt):
    """Responde una pregunta hablando por frases a medida que el modelo las genera."""
    global thinking
    cfg = _ai_cfg()
    if cfg["kind"] == "ollama" and (ollama is None or not cfg["model"]):
        reply(ask_ai(prompt, route=False)[1])
        return
    system = settings["system_prompt"] + ACTION_RULE + VOICE_RULE + f" Hoy es {fecha_hablada(datetime.date.today())}." + _notes_ctx()
    user_msg = {"role": "user", "content": prompt}
    keep = settings["history_turns"] * 2
    history = chat_history[-keep:] if keep else []
    msgs = [{"role": "system", "content": system}, *history, user_msg]

    thinking += 1
    refresh_mode()
    full, buf = "", ""
    try:
        for chunk in _stream_chunks(cfg, msgs):
            full += chunk
            buf += chunk
            m = _SENT_END.search(buf)
            while m:                                  # habla cada frase completa al instante
                sent = buf[:m.end()].strip()
                buf = buf[m.end():]
                if len(sent) > 1:
                    speak(_clean_for_speech(sent))
                m = _SENT_END.search(buf)
    except Exception as e:
        log_terminal(f"Error de IA (streaming): {e}", "ERROR")
        if (not full.strip() and getattr(e, "kind", "") == "net" and cfg["kind"] != "ollama"
                and net_recheck() and _ai_cfg()["kind"] == "ollama"):
            reply(ask_ai(prompt, route=False)[1])     # sin internet: responde la IA del equipo
            return
        threading.Thread(target=check_ai, daemon=True).start()
        if full.strip():                              # ya había dicho parte: se queda ahí
            push_chat("jarvis", full.strip(), "JARVIS")
        else:
            reply(ai_error_reply(e))
        return
    finally:
        thinking -= 1
        refresh_mode()

    if buf.strip():
        speak(_clean_for_speech(buf))
    full = full.strip() or "No estoy seguro de cómo responder."
    log_terminal(full, "JARVIS")
    push_chat("jarvis", full, "JARVIS")
    chat_history.extend([user_msg, {"role": "assistant", "content": full}])
    del chat_history[:-max(keep, 2)]
    save_memory()


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

    t = threading.Timer(seconds, _fire)
    t.daemon = True
    t.start()


# =============================================================================
# TEMPORIZADORES DE CLASE (cuenta regresiva visible en el HUD)
# =============================================================================
timers = {}                       # id -> {"label", "end", "total"}
timers_lock = threading.Lock()
_timer_seq = 0


def _spoken_duration(seconds):
    m, s = divmod(int(round(seconds)), 60)
    h, m = divmod(m, 60)
    partes = []
    if h:
        partes.append(f"{h} hora" + ("s" if h != 1 else ""))
    if m:
        partes.append(f"{m} minuto" + ("s" if m != 1 else ""))
    if s and not h:
        partes.append(f"{s} segundo" + ("s" if s != 1 else ""))
    return " y ".join(partes) or "0 segundos"


def parse_duration(t):
    """Extrae segundos de «de/por/en 15 minutos», «media hora», «hora y media»."""
    if re.search(r"\b(?:una )?hora y media\b", t):
        return 5400
    if re.search(r"\bmedia hora\b", t):
        return 1800
    total = 0
    found = False
    for m in re.finditer(rf"(\d+|{_NUM_ALT})\s*(segundos?|minutos?|horas?)", t):
        raw = m.group(1)
        qty = int(raw) if raw.isdigit() else NUM_WORDS.get(raw, 0)
        total += qty * _UNIT_SECONDS[m.group(2)[:3]]
        found = True
    return total if found else None


def _timers_snapshot():
    now = time.time()
    with timers_lock:
        return [{"id": i, "label": d["label"], "total": d["total"],
                 "remaining": max(0, round(d["end"] - now))}
                for i, d in sorted(timers.items(), key=lambda kv: kv[1]["end"])]


def _emit_timers():
    socketio.emit("timers", {"timers": _timers_snapshot()})


def add_timer(seconds, label=""):
    global _timer_seq
    _timer_seq += 1
    tid = _timer_seq
    with timers_lock:
        timers[tid] = {"label": label.strip(), "end": time.time() + seconds, "total": seconds}
    _emit_timers()
    return tid


def cancel_timers(label=""):
    label = normalize(label)
    with timers_lock:
        if not label or label in ("todos", "todo", "el temporizador", "los temporizadores"):
            n = len(timers)
            timers.clear()
        else:
            ids = [i for i, d in timers.items() if label in normalize(d["label"])]
            for i in ids:
                del timers[i]
            n = len(ids)
    _emit_timers()
    return n


def _timers_worker():
    while True:
        time.sleep(1)
        now = time.time()
        due = []
        with timers_lock:
            for i, d in list(timers.items()):
                if d["end"] <= now:
                    due.append(d)
                    del timers[i]
        if due:
            _emit_timers()
        for d in due:
            hud_show()
            play_sound(resolve_alarm_sound())
            lbl = f" de {d['label']}" if d["label"] else ""
            reply(f"¡Tiempo{lbl}! Terminó el temporizador de {_spoken_duration(d['total'])}.", "TIMER")
        if timers:
            _emit_timers()        # refresca la cuenta regresiva cada segundo mientras haya alguno


def send_whatsapp_message(phone, message):
    """Abre WhatsApp Web en el navegador y envía el mensaje (requiere sesión iniciada)."""
    try:
        log_terminal(f"Enviando mensaje a {phone}...", "WHATSAPP")
        skills.send_whatsapp(phone, message)
        reply("Mensaje de WhatsApp enviado.", "WHATSAPP")
    except Exception as e:
        log_terminal(f"Error al enviar mensaje por WhatsApp: {e}", "ERROR")


STEAM_DEFAULT = {
    "ciencia": "Fundamentos teóricos y fenómenos observables relacionados.",
    "tecnologia": "Herramientas digitales, sensores y software integrados.",
    "ingenieria": "Proceso de diseño, prototipado y resolución de problemas técnicos.",
    "arte": "Diseño estético, visualización conceptual y ergonomía.",
    "matematicas": "Modelos cuantitativos, fórmulas y análisis estadístico.",
}
STEAM_SECTIONS = [
    ("1. Ciencia (Science)", "ciencia"),
    ("2. Tecnología (Technology)", "tecnologia"),
    ("3. Ingeniería (Engineering)", "ingenieria"),
    ("4. Arte (Arts)", "arte"),
    ("5. Matemáticas (Mathematics)", "matematicas"),
]


def _steam_content(topic):
    if not settings["steam_use_ai"]:
        return STEAM_DEFAULT
    prompt = (
        f"Escribe el contenido de un proyecto educativo STEAM sobre '{topic}'. "
        "Responde SOLO con un objeto JSON con las claves ciencia, tecnologia, "
        "ingenieria, arte y matematicas. Cada valor es un párrafo de 2 a 4 "
        "oraciones en español, concreto y aplicable en el aula."
    )
    try:
        data = _extract_json(ai_chat([{"role": "user", "content": prompt}], json_mode=True))
        return {k: (str(data.get(k) or "").strip() or v) for k, v in STEAM_DEFAULT.items()}
    except Exception as e:
        log_terminal(f"La IA no pudo redactar el contenido, uso la plantilla base: {e}", "AVISO")
        return STEAM_DEFAULT


def generate_steam_doc(topic):
    if Document is None:
        reply("No puedo crear documentos: falta instalar python-docx.", "ERROR")
        return
    reply(f"Generando el documento STEAM sobre {topic}.", "OFFICE")
    content = _steam_content(topic)
    doc = Document()
    doc.add_heading(f"Proyecto Educativo STEAM: {topic}", level=0)
    doc.add_paragraph(f"Generado por Jarvis el {fecha_hablada(datetime.date.today())}.")
    for heading, key in STEAM_SECTIONS:
        doc.add_heading(heading, level=1)
        doc.add_paragraph(content[key])
    out_dir = settings["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    slug = re.sub(r"[^\w]+", "_", normalize(topic)).strip("_")[:40] or "general"
    path = os.path.join(out_dir, f"STEAM_{slug}_{datetime.datetime.now():%Y%m%d_%H%M}.docx")
    doc.save(path)
    log_terminal(f"Documento guardado en: {path}", "OFFICE")
    push_chat("jarvis", f"Documento listo: {os.path.basename(path)}", "OFFICE")
    speak("El documento de planificación STEAM está listo en tu carpeta de salida.")


def calculate_life_path_number(day, month, year):
    def reduce_sum(n):
        while n > 9 and n not in (11, 22, 33, 44):
            n = sum(int(d) for d in str(n))
        return n

    total = reduce_sum(reduce_sum(day) + reduce_sum(month) + reduce_sum(year))
    meanings = {
        1: "Liderazgo, individualidad, ambición e iniciativa.",
        2: "Diplomacia, cooperación, sensibilidad y empatía.",
        3: "Creatividad, autoexpresión, optimismo y comunicación.",
        4: "Disciplina, trabajo estructurado, constancia y método.",
        5: "Libertad, versatilidad, aventura y adaptabilidad.",
        6: "Responsabilidad, protección, familia y armonía comunitaria.",
        7: "Introspección, análisis intelectual, búsqueda mística.",
        8: "Poder material, gestión ejecutiva, éxito financiero.",
        9: "Humanitarismo, altruismo, vocación universal.",
        11: "Número Maestro: alta intuición, inspiración e iluminación.",
        22: "Número Maestro: el gran constructor, materialización de grandes obras.",
        33: "Número Maestro: amor universal incondicional y guía espiritual.",
        44: "Número Maestro: gran capacidad de resolución y perseverancia material.",
    }
    return total, meanings.get(total, "Vibración numérica singular.")


def morning_report():
    hoy = fecha_hablada(datetime.date.today())
    hora = datetime.datetime.now().strftime("%H:%M")
    ia = "operativo" if check_ai() else "sin conexión o sin modelo; revisa los ajustes"
    reply(f"Buenos días. Hoy es {hoy}, son las {hora}. El modelo de inteligencia artificial está {ia}.", "RUTINA")
    notes_today_summary(speak_it=True)


def reschedule():
    schedule.clear("morning")
    if settings["morning_enabled"]:
        schedule.every().day.at(settings["morning_time"]).do(morning_report).tag("morning")


def schedule_worker():
    while True:
        schedule.run_pending()
        time.sleep(15)


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
# =============================================================================
UPDATE_STATE_PATH = os.path.join(CONFIG_DIR, "actualizacion.json")
upd = {"busy": False, "info": None, "last_error": "", "step": ""}
_upd_lock = threading.Lock()


def _upd_load():
    try:
        with open(UPDATE_STATE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _upd_save(**changes):
    d = _upd_load()
    d.update(changes)
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(UPDATE_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except OSError:
        pass


def _upd_progress(step, pct=None, done=False, ok=True, msg=""):
    upd["step"] = step
    socketio.emit("update_progress", {"step": step, "pct": pct, "done": done, "ok": ok, "msg": msg})


def update_status():
    """Lo que necesita la sección Acerca de."""
    b = None
    try:
        b = actualizar.last_backup(APP_DIR)
    except Exception:
        pass
    return {"version": VERSION, "repo": settings["update_repo"], "busy": upd["busy"], "info": upd["info"],
            "frozen": bool(getattr(sys, "frozen", False)),
            "backup": {"from": b.get("desde"), "to": b.get("hacia"), "date": b.get("fecha")} if b else None,
            "last_check": _upd_load().get("checked", 0)}


def check_updates():
    """Consulta GitHub. Devuelve la info (o lanza actualizar.UpdateError con un mensaje claro)."""
    if not settings["update_repo"].strip():
        raise actualizar.UpdateError("Primero escribe en Ajustes › Acerca de el repositorio de GitHub "
                                     "donde se publican las versiones de Jarvis (usuario/nombre).")
    if is_offline():
        raise actualizar.UpdateError("Ahora mismo no hay internet.")
    info = actualizar.latest(settings["update_repo"], VERSION, settings["github_api_key"].strip())
    upd["info"] = info
    _upd_save(checked=time.time())
    return info


def _update_worker():
    """Una vez al día (si está activado) mira si hay versión nueva y lo avisa sin interrumpir."""
    time.sleep(90)
    while True:
        try:
            if (settings["update_auto"] and settings["update_repo"].strip() and not upd["busy"]
                    and time.time() - _upd_load().get("checked", 0) > 20 * 3600 and not is_offline()):
                info = check_updates()
                if info["newer"] and _upd_load().get("notified") != info["version"]:
                    _upd_save(notified=info["version"])
                    msg = (f"Hay una versión nueva de Jarvis: la {info['version']} (tienes la {VERSION}). "
                           "Para instalarla: Ajustes › Acerca de › Actualizar.")
                    log_terminal(msg, "ACTUALIZACIÓN")
                    push_chat("jarvis", msg, "ACTUALIZACIÓN")
        except actualizar.UpdateError as e:
            log_terminal(f"Buscar actualizaciones: {e}", "AVISO")
        except Exception as e:
            log_terminal(f"Buscar actualizaciones: {e}", "AVISO")
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
    args = [sys.executable, os.path.join(APP_DIR, "jarvis.py"), *sys.argv[1:]]
    env = dict(os.environ, JARVIS_WAIT_PID=str(os.getpid()))
    kw = {"cwd": APP_DIR, "env": env, "close_fds": True}
    if IS_WIN:
        kw["creationflags"] = 0x00000008 | 0x00000200          # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen(args, **kw)
    threading.Timer(delay, quit_app).start()


def install_update():
    """Descarga, instala (con copia de seguridad) y reinicia. Corre en su propio hilo."""
    if getattr(sys, "frozen", False):
        _upd_progress("Esta copia de Jarvis es el .exe compilado: actualiza la carpeta del código "
                      "y vuelve a ejecutar compilar.bat.", done=True, ok=False)
        return
    with _upd_lock:
        if upd["busy"]:
            return
        upd["busy"] = True
    tmp = os.path.join(tempfile.gettempdir(), f"jarvis_actualizacion_{uuid.uuid4().hex}.zip")
    try:
        info = upd["info"] if upd["info"] and upd["info"].get("newer") else check_updates()
        if not info["newer"]:
            _upd_progress(f"Ya tienes la última versión ({VERSION}).", done=True)
            return
        _upd_progress(f"Descargando la versión {info['version']}…", 0)
        token = settings["github_api_key"].strip()
        actualizar.download(info, tmp, token, lambda got, total: _upd_progress(
            f"Descargando la versión {info['version']}…", round(got * 100 / total) if total else None))
        zv = actualizar.zip_version(tmp)
        if actualizar.parse_version(zv) <= actualizar.parse_version(VERSION):
            raise actualizar.UpdateError(f"El archivo publicado trae la versión {zv}, que no es más nueva "
                                         f"que la tuya ({VERSION}). Revisa la Release en GitHub.")
        _upd_progress("Instalando (con copia de seguridad)…", 0)
        res = actualizar.apply(tmp, APP_DIR, VERSION,
                               lambda i, n: _upd_progress("Instalando (con copia de seguridad)…", round(i * 100 / n)))
        log_terminal(f"Actualizado a la versión {res['version']}: {len(res['changed'])} archivos cambiados, "
                     f"{len(res['added'])} nuevos. Copia de seguridad en {res['backup']}.", "ACTUALIZACIÓN")
        if res["requirements_changed"]:
            _upd_progress("Instalando componentes nuevos (puede tardar unos minutos)…")
            try:
                r = subprocess.run([_python_console(), "-m", "pip", "install", "-q", "-r",
                                    os.path.join(APP_DIR, "requirements.txt")], cwd=APP_DIR,
                                   capture_output=True, text=True, timeout=900,
                                   creationflags=0x08000000 if IS_WIN else 0)
                if r.returncode != 0:
                    log_terminal("Algunos componentes nuevos no se instalaron; ejecuta instalar.bat. "
                                 + (r.stderr or "")[-300:], "AVISO")
            except Exception as e:
                log_terminal(f"No pude instalar componentes nuevos ({e}); ejecuta instalar.bat.", "AVISO")
        _upd_save(installed=res["version"], notified=res["version"])
        _upd_progress(f"Listo: versión {res['version']} instalada. Reiniciando Jarvis…", 100, done=True)
        reply(f"Me actualicé a la versión {res['version']}. Me reinicio en un momento.", "ACTUALIZACIÓN")
        restart_jarvis(delay=3.0)
    except actualizar.UpdateError as e:
        upd["last_error"] = str(e)
        _upd_progress(str(e), done=True, ok=False)
    except Exception as e:
        upd["last_error"] = str(e)
        log_terminal(f"Actualización fallida: {e}", "ERROR")
        _upd_progress(f"No se pudo actualizar: {e}. Si algo quedó mal, usa «Deshacer la última actualización».",
                      done=True, ok=False)
    finally:
        upd["busy"] = False
        try:
            os.remove(tmp)
        except OSError:
            pass


def rollback_update():
    if upd["busy"]:
        return {"ok": False, "error": "Hay una actualización en curso."}
    try:
        res = actualizar.rollback(APP_DIR)
    except actualizar.UpdateError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"No se pudo deshacer: {e}"}
    log_terminal(f"Actualización deshecha: vuelvo a la versión {res['version']}.", "ACTUALIZACIÓN")
    _upd_save(notified=res["from"])               # no volver a avisar de la versión que deshiciste
    restart_jarvis(delay=2.0)
    return {"ok": True, "version": res["version"]}


_UPD_RE = re.compile(r"\b(?:busca|buscar|buscame|hay|revisa|comprueba|mira si hay|tienes)\b.*\bactualizacion(?:es)?\b"
                     r"|\bactualizate\b|\bactualiza (?:a )?jarvis\b|\b(?:version nueva|nueva version) de jarvis\b"
                     r"|\bque version (?:eres|tienes)\b|\ben que version (?:estas|vas)\b")


def update_voice(text, t):
    """«Jarvis, ¿hay actualizaciones?», «actualízate», «¿qué versión eres?». Solo consulta:
    instalar se hace con el botón (así nunca se reinicia en mitad de una clase)."""
    if not _UPD_RE.search(t):
        return False
    if re.search(r"\bque version\b|\ben que version\b", t):
        reply(f"Soy Jarvis {VERSION}.", "ACTUALIZACIÓN")
        return True
    try:
        info = check_updates()
    except actualizar.UpdateError as e:
        reply(f"No pude buscar actualizaciones: {e}", "ACTUALIZACIÓN")
        return True
    if info["newer"]:
        reply(f"Hay una versión nueva: la {info['version']}; tienes la {VERSION}. Para instalarla abre "
              "Ajustes, sección Acerca de, y pulsa Actualizar.", "ACTUALIZACIÓN")
    else:
        reply(f"Estás al día: tienes la versión {VERSION}, la última publicada.", "ACTUALIZACIÓN")
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
    return settings["backup_dir"].strip() or os.path.join(settings["output_dir"], "Respaldos")


def make_backup(kind="manual", include_secrets=None):
    with _bak_lock:
        res = respaldo.create(CONFIG_DIR, backup_folder(), settings, SECRET_FIELDS,
                              settings["backup_secrets"] if include_secrets is None else include_secrets,
                              VERSION, kind)
        if kind in ("auto", "antes"):
            respaldo.prune(backup_folder(), BACKUP_KEEP_AUTO, kind)
    log_terminal(f"Copia de seguridad guardada: {res['path']}", "RESPALDO")
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
    return ", ".join(bits[:-1]) + " y " + bits[-1] if len(bits) > 1 else bits[0]


def _backup_worker():
    """Una copia automática a la semana (se guardan las 8 últimas)."""
    time.sleep(300)
    while True:
        try:
            if settings["backup_auto"]:
                autos = [b for b in respaldo.listing(backup_folder()) if b["kind"] == "auto"]
                last = 0.0
                if autos:
                    try:
                        last = datetime.datetime.fromisoformat(autos[0]["date"]).timestamp()
                    except ValueError:
                        last = 0.0
                if time.time() - last > 7 * 86400:
                    make_backup("auto")
        except Exception as e:
            log_terminal(f"Copia de seguridad automática: {e}", "AVISO")
        time.sleep(3600)


def restore_backup(name, parts):
    """Restaura las partes elegidas de una copia de la carpeta de copias.
    Antes guarda una copia de cómo está todo ahora, por si te arrepientes."""
    path = os.path.join(backup_folder(), respaldo.safe_name(name))
    info = respaldo.inspect(path)
    parts = [p for p in parts if p in respaldo.PARTS and p in {x["part"] for x in info["parts"]}]
    if not parts:
        raise respaldo.BackupError("Elige al menos una parte para restaurar.")
    safety = make_backup("antes")
    skipped = []
    if "ajustes" in parts:
        cfg = respaldo.read_config(path)
        same_pc = info["computer"] and info["computer"] == platform.node()
        data = {}
        for k, v in cfg.items():
            if k not in DEFAULT_SETTINGS or k in ("hud_x", "hud_y"):
                continue
            if k in _MACHINE_KEYS and not same_pc:
                if k == "mic_device" or not (isinstance(v, str) and v and os.path.exists(v)):
                    if v not in ("", None) and v != DEFAULT_SETTINGS[k]:
                        skipped.append(k)
                    continue
            data[k] = v
        errs = apply_settings(data)                       # valida cada valor; claves vacías = conservar
        if errs:
            log_terminal("Restaurar ajustes: " + "; ".join(errs), "AVISO")
    done = respaldo.restore(path, CONFIG_DIR, parts)
    if "notas" in done:
        notas.load()
    if "aula" in done:
        aula.load()
    if "rutinas" in done:
        rutinas.load()
    if "memoria" in done:
        load_memory()
    socketio.emit("settings_updated", public_settings())
    names = [respaldo.PARTS[p].lower() for p in parts]
    log_terminal(f"Restaurado desde «{info['name']}»: {', '.join(names)}. "
                 f"Copia previa en «{safety['name']}».", "RESPALDO")
    return {"ok": True, "parts": parts, "safety": safety["name"], "skipped": skipped,
            "secrets_missing": "ajustes" in parts and not info["with_secrets"]}


_BAK_RE = re.compile(r"\b(?:haz|hazme|hacer|crea|crear|guarda|guardar|saca|sacar|genera)\b.{0,25}\b(?:copia de seguridad|respaldo|backup)\b"
                     r"|\brespalda(?:r|me)?\b.{0,20}\b(?:ajustes|configuracion|datos|todo|notas|cursos)\b")


def backup_voice(text, t):
    """«Jarvis, haz una copia de seguridad». Restaurar es solo desde Ajustes (reemplaza datos)."""
    if not _BAK_RE.search(t):
        return False
    try:
        res = make_backup("manual")
    except Exception as e:
        reply(f"No pude hacer la copia de seguridad: {e}", "RESPALDO")
        return True
    where = ("tu carpeta Documentos, en Jarvis, Respaldos" if not settings["backup_dir"].strip()
             else "la carpeta de copias que elegiste en Ajustes")
    reply(f"Listo, guardé {_backup_summary(res)} en {where}.", "RESPALDO")
    return True



# =============================================================================
# CALENDARIO (Google, Outlook… por su enlace iCal, solo lectura). Lógica en calendario.py.
# =============================================================================
cal_state = {"missing_lib": False}


def _cal_urls():
    return calendario.clean_urls(settings["calendar_urls"])


def cal_refresh(force=False):
    urls = _cal_urls()
    if not urls:
        calendario.cache.update(events=[], errors=[], urls=())
        return calendario.cache
    try:
        before = calendario.cache["fetched"]
        c = calendario.refresh(urls, force=force)
        if c["fetched"] != before:
            for err in c["errors"]:
                log_terminal(f"Calendario: {err}", "AVISO")
    except ImportError:
        if not cal_state["missing_lib"]:
            cal_state["missing_lib"] = True
            log_terminal("Para leer el calendario falta un componente: ejecuta instalar.bat otra vez.", "AVISO")
    return calendario.cache


def _cal_worker():
    """Actualiza el calendario cada 10 minutos y avisa antes de cada evento."""
    while True:
        try:
            if _cal_urls():
                cal_refresh()
                for ev, mins in calendario.due_alerts(before_min=settings["calendar_notice_min"]):
                    hud_show()
                    reply(f"En {mins} minuto{'s' if mins != 1 else ''}: {calendario.what(ev)}.", "CALENDARIO")
        except Exception as e:
            log_terminal(f"Calendario: {e}", "AVISO")
        time.sleep(30)


def _event_line(ev, with_day=True):
    if ev["todo_el_dia"]:
        d = notas.when_spoken(calendario.as_note(ev)) if with_day else ""
        return (f"{d}, " if d else "") + f"todo el día, {calendario.what(ev)}"
    return f"{notas.when_spoken(calendario.as_note(ev), with_day=with_day)}, {calendario.what(ev)}"


def agenda(scope, with_day=True):
    """Notas + eventos del calendario de ese periodo, ordenados por hora. Lista de frases."""
    today = datetime.date.today()
    d1, d2 = {"hoy": (today, today), "manana": (today + datetime.timedelta(days=1),) * 2,
              "semana": (today, today + datetime.timedelta(days=7))}[scope]
    items = [((n["fecha"] or "9999"), (n.get("hora") or "99:99"), notas.spoken(n, with_day=with_day))
             for n in notas.listing(scope)]
    if _cal_urls():
        cal_refresh()
        for ev in calendario.between(d1, d2):
            hora = "00:00" if ev["todo_el_dia"] else ev["inicio"][11:16]
            items.append((ev["inicio"][:10] if not ev["todo_el_dia"] else max(ev["inicio"][:10], d1.isoformat()),
                          hora, _event_line(ev, with_day)))
    return [x[2] for x in sorted(items)]


def _say_agenda(scope, vacio, titulo):
    lines = agenda(scope, with_day=scope == "semana")
    if not lines:
        reply(vacio, "AGENDA")
        return
    if len(lines) > 1:
        lines[-1] = "y " + lines[-1]
    extra = f" Y {len(lines) - 8} cosas más." if len(lines) > 8 else ""
    reply(f"{titulo}: " + "; ".join(lines[:8]) + "." + extra, "AGENDA")


def calendar_voice(text, t):
    """«¿cuál es mi próxima clase?», «¿qué sigue?», «actualiza el calendario». True si era para esto."""
    if re.search(r"\b(?:actualiza|recarga|refresca|sincroniza)\b.*\bcalendario\b", t):
        if not _cal_urls():
            reply("Aún no conectaste tu calendario. En Ajustes, sección Memoria, pega su dirección iCal.", "CALENDARIO")
            return True
        c = cal_refresh(force=True)
        n = len(calendario.between(datetime.date.today(), datetime.date.today() + datetime.timedelta(days=30)))
        reply(f"Calendario actualizado: {n} eventos en el próximo mes."
              + (f" Ojo: {c['errors'][0]}" if c["errors"] else ""), "CALENDARIO")
        return True
    m = re.search(r"\b(?:mi |la |el )?proxim[ao] (clase|reunion|evento|cita|actividad|compromiso)\b"
                  r"|\bque (?:sigue|me toca|tengo ahora)\b|\bque (?:hay|tengo) en (?:el|mi) calendario\b", t)
    if not m:
        return False
    if not _cal_urls():
        if "calendario" in t or m.group(1):
            reply("Aún no conectaste tu calendario. En Ajustes, sección Memoria, pega la «dirección secreta "
                  "en formato iCal» de Google Calendar (o el enlace ICS de Outlook).", "CALENDARIO")
            return True
        return False
    cal_refresh()
    if "calendario" in t:
        _say_agenda("hoy", "Hoy no tienes nada en el calendario ni en tus notas.", "Hoy tienes")
        return True
    kw = {"clase": "clase", "reunion": "reuni", "cita": "cita"}.get(m.group(1) or "", "")
    nx = calendario.upcoming(limit=1, keyword=kw)
    if not nx and kw:
        nx = calendario.upcoming(limit=1)
    if not nx:
        reply("No tienes más eventos con hora en tu calendario este mes.", "CALENDARIO")
        return True
    ev = nx[0]
    ini = datetime.datetime.fromisoformat(ev["inicio"])
    fin = datetime.datetime.fromisoformat(ev["fin"])
    if ini <= datetime.datetime.now(ini.tzinfo):
        reply(f"Ahora mismo: {calendario.what(ev)}, hasta las {fin.strftime('%H:%M')}.", "CALENDARIO")
    else:
        que = {"clase": "Tu próxima clase", "reunion": "Tu próxima reunión", "cita": "Tu próxima cita"}.get(
            m.group(1) or "", "Lo próximo")
        reply(f"{que}: {_event_line(ev)}.", "CALENDARIO")
    return True


# =============================================================================
# RUTINAS CON NOMBRE («modo clase», «fin de clase»…). La lógica está en rutinas.py.
# =============================================================================
rutinas.configure(CONFIG_DIR)
routine_state = {"running": None}


def run_routine(r):
    """Ejecuta los pasos en orden, en segundo plano. Cada paso escribe en el HUD pero no
    habla (si no, oirías «Abriendo Word… Volumen al 40…»); solo hablan los pasos «decir»
    y el aviso final. Nunca ejecuta acciones peligrosas ni otras rutinas."""
    if routine_state["running"]:
        reply(f"Ya estoy ejecutando la rutina {routine_state['running']}.", "RUTINA")
        return
    routine_state["running"] = r["nombre"]
    log_terminal(f"Rutina «{r['nombre']}»: {len(r['pasos'])} pasos.", "RUTINA")

    def work():
        saltados, hablo_al_final = [], False
        try:
            for i, step in enumerate(r["pasos"]):
                kind, val = rutinas.step_kind(step)
                hablo_al_final = False
                if kind == "esperar":
                    time.sleep(val)
                    continue
                if kind == "decir":
                    reply(val, "RUTINA")
                    hablo_al_final = i == len(r["pasos"]) - 1
                    continue
                direct = skills.parse(val)
                sk = skills.REGISTRY.get(direct[0]) if direct else None
                if sk and sk.dangerous:
                    saltados.append(val)
                    log_terminal(f"Rutina: me salto «{val}» (acción delicada; dímela tú directamente).", "AVISO")
                    continue
                if rutinas.find(val):
                    saltados.append(val)
                    log_terminal(f"Rutina: me salto «{val}» (una rutina no puede lanzar otra).", "AVISO")
                    continue
                log_terminal(f"Paso {i + 1}: {val}", "RUTINA")
                _tl.quiet = True
                try:
                    process_command(val)
                finally:
                    _tl.quiet = False
                time.sleep(0.6)                     # deja que la ventana o el ajuste termine de aplicarse
        except Exception as e:
            log_terminal(f"Rutina «{r['nombre']}»: {e}", "ERROR")
        finally:
            _tl.quiet = False
            routine_state["running"] = None
        if saltados:
            n = len(saltados)
            reply(f"Rutina {r['nombre']} lista, pero me salté {n} paso{'s' if n != 1 else ''} que no "
                  f"se pueden usar en una rutina. Los ves en el Registro.", "RUTINA")
        elif not hablo_al_final:
            reply(f"Rutina {r['nombre']} lista.", "RUTINA")
    threading.Thread(target=work, daemon=True, name="rutina").start()


def routine_voice(text, t):
    """«modo clase», «activa la rutina fin de clase», «¿qué rutinas tengo?». True si era para esto."""
    if re.search(r"\b(?:que|cuales) rutinas\b|\bmis rutinas\b|\blista de rutinas\b", t):
        if not rutinas.routines:
            reply("No tienes rutinas. Créalas en Ajustes, sección Rutinas.", "RUTINA")
        else:
            nombres = [r["nombre"] for r in rutinas.routines]
            reply(f"Tienes {len(nombres)} rutinas: {', '.join(nombres[:-1]) + ' y ' + nombres[-1] if len(nombres) > 1 else nombres[0]}. "
                  "Dime su nombre para lanzarla.", "RUTINA")
        return True
    if re.search(r"\b(?:crea|creame|haz|nueva|agrega|edita|cambia)\b.*\brutina\b", t):
        open_settings_window()
        reply("Las rutinas se crean en Ajustes, sección Rutinas: un nombre, las frases para lanzarla "
              "y una orden por línea. Te abro los ajustes.", "RUTINA")
        return True
    r = rutinas.find(t)
    if r:
        run_routine(r)
        return True
    return False


# =============================================================================
# MEMORIA PERSONAL: notas y pendientes («recuerda que…», «¿qué tengo pendiente?»)
#   La lógica está en notas.py; aquí se conecta con la voz, los avisos y la IA.
# =============================================================================
notas.configure(CONFIG_DIR)


def _notes_ctx():
    if not settings["notes_ai_context"]:
        return ""
    ctx = notas.context_for_ai()
    if _cal_urls():
        ctx += calendario.context_for_ai(notas.when_spoken)
    return ctx


def _notes_changed():
    socketio.emit("notes_updated", notes_snapshot())


def notes_snapshot():
    today = datetime.date.today()
    items = sorted(notas.notes, key=lambda n: (n.get("hecho", False), notas._sort_key(n)))
    return [{"id": n["id"], "texto": n["texto"], "que": notas.what(n), "cuando": notas.when_spoken(n, today),
             "fecha": n.get("fecha", ""), "hora": n.get("hora", ""), "hecho": bool(n.get("hecho"))}
            for n in items]


def _say_list(items, vacio, titulo, with_day=True):
    if not items:
        reply(vacio, "NOTAS")
        return
    partes = [notas.spoken(n, with_day=with_day) for n in items[:6]]
    if len(partes) > 1:
        partes[-1] = "y " + partes[-1]
    extra = f" Y {len(items) - 6} más en Ajustes, sección Memoria." if len(items) > 6 else ""
    reply(f"{titulo}: " + "; ".join(partes) + "." + extra, "NOTAS")


_NOTE_ADD = re.compile(
    r"^(?:por favor )?(?:jarvis )?(?:recuerda(?:me)?|recuerde(?:me)?|acuerdate|no (?:me )?dejes olvidar|"
    r"no (?:te )?olvides|anota(?:me)?|apunta(?:me)?|toma nota|guarda (?:una|esta) nota|agenda(?:me)?|"
    r"ten en cuenta)\b(?:\s+(?:que|de que|de|esto|lo siguiente))?\s*(.*)$")


def notes_voice(text, t):
    """Órdenes de voz de la memoria personal. Devuelve True si la frase era para ella."""
    m = _NOTE_ADD.match(t)
    if m:
        if parse_reminder(t):                      # «recuérdame en 10 minutos…» = alarma de siempre
            return False
        resto_n = m.group(1).strip()
        if not resto_n:
            reply("¿Qué quieres que recuerde? Por ejemplo: recuerda que la reunión de padres es el jueves a las 3.", "NOTAS")
            return True
        # mismo número de palabras que el disparador, pero del texto original (con tildes y mayúsculas)
        skip = len(t[:m.start(1)].split())
        original = " ".join(text.split()[skip:]).strip() or resto_n
        n = notas.add(original)
        _notes_changed()
        cuando = notas.when_spoken(n)
        reply(f"Anotado{': ' + cuando if cuando else ''}, {notas.what(n)}."
              + (" Te aviso antes." if n.get("hora") and settings["notes_notice_min"] else ""), "NOTAS")
        return True

    scope = None
    if re.search(r"\bque (?:tengo|tenia|hay)(?: anotado| agendado| pendiente)? (?:para )?hoy\b", t):
        scope, vacio, titulo = "hoy", "Para hoy no tienes nada anotado.", "Hoy tienes"
    elif re.search(r"\bque (?:tengo|tenia|hay)(?: anotado| agendado| pendiente)? (?:para )?manana\b", t):
        scope, vacio, titulo = "manana", "Para mañana no tienes nada anotado.", "Mañana tienes"
    elif re.search(r"\bque (?:tengo|tenia|hay)(?: anotado| agendado| pendiente)? (?:para )?esta semana\b", t):
        scope, vacio, titulo = "semana", "Esta semana no tienes nada anotado.", "Esta semana tienes"
    elif re.search(r"\b(?:que|cuales) (?:tengo|tenia|hay|son mis) (?:pendientes?|por hacer|anotado|agendado)\b|"
                   r"\bmis (?:pendientes|notas)\b|\bque (?:notas|pendientes) tengo\b|"
                   r"\blee(?:me)? (?:mis |las )?(?:notas|pendientes)\b|\bque te pedi que (?:recordaras|anotaras)\b", t):
        scope, vacio, titulo = "todo", "No tienes pendientes anotados.", None
    if scope in ("hoy", "manana", "semana"):
        _say_agenda(scope, vacio, titulo)              # notas + calendario, por hora
        return True
    if scope:
        items = notas.listing(scope)
        _say_list(items, vacio, titulo or (f"Tienes {len(items)} pendiente" + ("s" if len(items) != 1 else "")),
                  with_day=True)
        if _cal_urls():
            nx = calendario.upcoming(limit=1)
            if nx:
                reply(f"Y en tu calendario, lo próximo: {_event_line(nx[0])}.", "AGENDA")
        return True

    m = re.match(r"^(?:ya (?:hice|termine|complete|entregue|pase|cumpli|resolvi|compre|llame|envie|fui a|"
                 r"mande|hable con|pague)|tacha|marca como hech[oa]|completa|completado|listo|hecho)\s+(.+)$", t)
    if m:
        n = notas.find(m.group(1)) or notas.find(t)
        if not n:
            return False                            # no hablaba de una nota: que siga el resto
        notas.set_done(n["id"])
        _notes_changed()
        reply(f"Hecho: {notas.what(n)}. Lo taché de tus pendientes.", "NOTAS")
        return True
    m = re.match(r"^(?:borra|elimina|quita|olvida)\s+(?:la nota|el pendiente|el recordatorio|lo)\s+(?:de |sobre |del |que )?(.+)$", t)
    if m:
        n = notas.find(m.group(1))
        if not n:
            reply("No encontré esa nota. Dime alguna palabra de lo que anotaste.", "NOTAS")
            return True
        notas.delete(n["id"])
        _notes_changed()
        reply(f"Borrada la nota: {notas.what(n)}.", "NOTAS")
        return True
    if re.search(r"\b(?:borra|limpia|quita)\b.*\b(?:notas|pendientes) (?:hechas|hechos|terminadas|completadas|tachadas)\b", t):
        notas.clear_done()
        _notes_changed()
        reply("Listo, borré las notas que ya estaban hechas.", "NOTAS")
        return True
    return False


def _notes_worker():
    """Avisos de las notas con hora: unos minutos antes y a la hora."""
    while True:
        time.sleep(30)
        try:
            for n, tipo in notas.due_alerts(before_min=settings["notes_notice_min"]):
                que = notas.what(n)
                hud_show()
                if tipo == "antes":
                    reply(f"Recordatorio: en {settings['notes_notice_min']} minutos, {que}.", "NOTAS")
                else:
                    play_sound(resolve_alarm_sound())
                    reply(f"Es la hora: {que}.", "NOTAS")
                _notes_changed()
        except Exception as e:
            log_terminal(f"Avisos de notas: {e}", "AVISO")


def notes_today_summary(speak_it=False):
    items = agenda("hoy", with_day=False)
    if not items:
        return ""
    txt = "Hoy tienes: " + "; ".join(items[:6]) + "."
    if speak_it:
        reply(txt, "NOTAS")
    else:
        push_chat("jarvis", "📌 " + txt, "NOTAS")
    return txt


# =============================================================================
# AULA: cursos, sorteo, grupos, asistencia, semáforo de ruido y material de clase
#   La lógica está en aula.py; aquí se conecta con la voz, el tablero y la IA.
# =============================================================================
aula.configure(CONFIG_DIR)
aula_ui = {"last": None, "view": "ruleta", "attendance_until": 0.0}
material_job = {"busy": False}
generated_files = set()                     # solo estos archivos se pueden abrir desde el tablero


def aula_emit(event):
    """Envía algo al tablero y lo recuerda (si el tablero se abre después, lo muestra)."""
    if event.get("type") in ("pick", "groups"):
        aula_ui["last"] = event
    if event.get("view"):
        aula_ui["view"] = event["view"]
    socketio.emit("aula", event)


def open_aula_window(view=None):
    if view:
        aula_ui["view"] = view
        socketio.emit("aula", {"type": "view", "view": view})
    if webview is None or hud["window"] is None:
        if not hud.get("aula_browser"):
            hud["aula_browser"] = True
            webbrowser.open(f"{URL}/aula")
        return
    w = hud.get("aula_win")
    if w is not None:
        try:
            w.show()
            w.restore()
            return
        except Exception:
            hud["aula_win"] = None
    w = webview.create_window("Aula · Jarvis", f"{URL}/aula", width=1120, height=720,
                              min_size=(640, 420), background_color="#03060c")

    def _closed():
        hud["aula_win"] = None
    w.events.closed += _closed
    hud["aula_win"] = w


def _maybe_open_board(view):
    if settings["aula_auto_open"]:
        open_aula_window(view)
    else:
        aula_emit({"type": "view", "view": view})


def aula_pick():
    name, quedan, total = aula.pick()
    aula_emit({"type": "pick", "name": name, "quedan": quedan, "total": total,
               "curso": aula.data["activo"], "view": "ruleta"})
    _maybe_open_board("ruleta")
    reply(f"Le toca a {name}.", "AULA")


def aula_groups(size=None, count=None):
    cur, groups = aula.make_groups(size=size, count=count)
    aula_emit({"type": "groups", "groups": groups, "curso": cur, "view": "grupos"})
    _maybe_open_board("grupos")
    tam = sorted({len(g) for g in groups})
    reply(f"Listo: {len(groups)} grupos de {' y '.join(map(str, tam))} en {cur}. Los muestro en el tablero.", "AULA")


def aula_start_attendance():
    cur, names = aula.active()
    aula_ui["attendance_until"] = time.time() + 3 * 3600
    open_aula_window("asistencia")
    reply(f"Abro la lista de {cur}, con {len(names)} estudiantes. Toca en el tablero a quien falte, "
          "o dime por ejemplo «falta Juan». Al terminar di «guarda la asistencia».", "AULA")


def aula_mark_voice(spoken, present):
    cur, names = aula.active()
    done, unknown = [], []
    for part in re.split(r"\s*,\s*|\s+y\s+", spoken):
        if not part.strip():
            continue
        name, cands = aula.find_student(part, names)
        if name:
            aula.mark(name, present)
            done.append(name)
        elif len(cands) > 1:
            reply(f"Hay varios: {', '.join(cands[:4])}. Dime el nombre completo.", "AULA")
            return
        else:
            unknown.append(part)
    aula_emit({"type": "attendance", **aula.snapshot()})
    if done:
        reply(f"{', '.join(done)}: {'presente' if present else 'ausente'}.", "AULA")
    if unknown:
        reply(f"No encontré a {', '.join(unknown)} en {cur}.", "AULA")


def aula_export_attendance():
    path, pres, tot = aula.export_attendance(settings["output_dir"])
    generated_files.add(path)
    aula_emit({"type": "exported", "path": path, "name": os.path.basename(path)})
    aula_ui["attendance_until"] = 0.0
    reply(f"Asistencia guardada: {pres} de {tot} presentes. El archivo está en la carpeta Asistencia.", "AULA")


def generate_material(request, kind=None, count=None, grade="", topic=""):
    """Genera quiz, taller, rúbrica o plan de clase con la IA y lo guarda en Word."""
    if Document is None:
        reply("No puedo crear documentos: falta instalar python-docx.", "ERROR")
        return
    kind = kind if kind in aula.KINDS else (aula.detect_kind(request) or "taller")
    label = aula.KINDS[kind][0]
    lo = {"quiz": "la evaluación", "taller": "el taller", "rubrica": "la rúbrica",
          "plan": "el plan de clase"}[kind]
    if material_job["busy"]:
        reply("Ya estoy preparando otro material. Te aviso cuando termine y luego hago este.", "AULA")
        return
    material_job["busy"] = True
    reply(f"Preparando {lo}. Te aviso cuando esté listo; suele tardar menos de un minuto.", "AULA")
    aula_emit({"type": "material", "status": "working", "label": label})

    def work():
        try:
            prompt = aula.build_prompt(kind, request, count or aula.detect_count(request), grade, topic)
            m, last_err = None, None
            for _ in range(2):                         # un reintento si la IA devuelve algo mal formado
                try:
                    raw = ai_chat([{"role": "user", "content": prompt}], json_mode=True, max_tokens=8000)
                    m = aula.validate(kind, _extract_json(raw), request)
                    break
                except (ValueError, TypeError) as e:
                    last_err = e
            if m is None:
                raise ValueError(str(last_err) or "respuesta no válida")
            path = aula.build_docx(kind, m, settings["output_dir"], Document, settings["aula_docente"],
                                   settings["aula_institucion"], aula.data["activo"])
            generated_files.add(path)
            log_terminal(f"Material guardado en: {path}", "AULA")
            aula_emit({"type": "material", "status": "done", "label": label, "title": m["titulo"],
                       "path": path, "name": os.path.basename(path)})
            if IS_WIN and settings["aula_open_docs"]:
                try:
                    os.startfile(path)
                except OSError:
                    pass
            reply(f"Listo {lo}: «{m['titulo']}». Lo guardé en la carpeta Material de clase"
                  + (" y lo abrí." if IS_WIN and settings["aula_open_docs"] else "."), "AULA")
        except AIError as e:
            aula_emit({"type": "material", "status": "error", "label": label, "error": e.why})
            reply(ai_error_reply(e), "AULA")
        except Exception as e:
            log_terminal(f"Material de clase: {e}", "ERROR")
            aula_emit({"type": "material", "status": "error", "label": label, "error": str(e)})
            reply(f"No me salió bien {lo}. Inténtalo otra vez, quizá con un tema más concreto.", "AULA")
        finally:
            material_job["busy"] = False
    threading.Thread(target=work, daemon=True, name="material").start()


_AULA_VERB = r"\b(?:crea|creame|haz|hazme|prepara|preparame|genera|generame|disena|disename|elabora|elaborame|redacta|arma|armame)\b"
# Si la frase habla de estas cosas, no es una orden del aula («crea un grupo de WhatsApp»...)
_AULA_NOT = re.compile(r"\b(?:calendario|recordatorio|alarma|carpeta|archivo|correo|whatsapp|telegram|"
                       r"spotify|youtube|steam|contacto|chat|playlist|lista de reproduccion)\b")


def aula_voice(text, t):
    """Órdenes de voz del aula. Devuelve True si la frase era para el aula."""
    if _AULA_NOT.search(t):
        return False
    try:
        # Material de clase: «crea un quiz de 10 preguntas sobre fracciones para séptimo»
        kind = aula.detect_kind(t)
        # palabras genéricas (actividad, tarea, prueba...) exigen decir el tema con «sobre»
        weak = not re.search(r"\b(?:taller|guia|ficha|quiz|evaluacion|examen|cuestionario|rubrica|"
                             r"plan de clase|planeacion|planificacion|secuencia didactica)\b", t)
        marker = r"\b(?:sobre|acerca)\b" if weak else r"\b(?:sobre|de|del|para|acerca)\b"
        if kind and re.search(_AULA_VERB, t) and re.search(marker, t):
            generate_material(text, kind)
            return True
        # Curso activo: «usa el curso 7A», «cambia al grado séptimo A»
        m = re.search(r"\b(?:usa|usar|cambia|cambiar|pasa|selecciona|estoy con|vamos con|trabaja con)\b"
                      r".*?\b(?:curso|grado)\s+(.+)$", t)
        if m and aula.data["cursos"]:
            cur = aula.find_course(m.group(1))
            if not cur:
                lista = ", ".join(aula.data["cursos"]) or "ninguno todavía"
                reply(f"No tengo el curso «{m.group(1)}». Tengo: {lista}.", "AULA")
            else:
                aula.set_active(cur)
                aula_emit({"type": "course", **aula.snapshot()})
                reply(f"Listo, trabajamos con {cur}: {len(aula.data['cursos'][cur])} estudiantes.", "AULA")
            return True
        if re.search(r"\breinici\w* (?:la )?(?:ruleta|sorteo|lista del sorteo)\b", t):
            aula.reset_pick()
            reply("Ruleta reiniciada: todos vuelven a participar.", "AULA")
            return True
        # Grupos: «haz grupos de 4», «forma 5 grupos», «haz parejas»
        if (re.search(r"\b(?:haz|hagan|forma|formar|arma|armar|crea|organiza|divide|dividelos|separa|reparte|hazme)\b", t)
                and re.search(r"\b(?:grupos?|equipos?|parejas|trios)\b", t)):
            size = count = None
            ms = re.search(r"\b(?:grupos?|equipos?) de (\w+)", t)
            mc = re.search(r"\b(\w+) (?:grupos|equipos)\b", t)
            if "parejas" in t:
                size = 2
            elif "trios" in t:
                size = 3
            elif ms and aula.to_int(ms.group(1)):
                size = aula.to_int(ms.group(1))
            elif mc and aula.to_int(mc.group(1)):
                count = aula.to_int(mc.group(1))
            aula_groups(size=size or (None if count else 4), count=count)
            return True
        # Sorteo: «escoge un estudiante», «¿quién pasa al tablero?», «otro»
        recien = time.time() - aula_ui.get("last_pick", 0) < 900       # sorteaste hace poco
        if (re.search(r"\b(?:escoge|escoja|elige|elija|selecciona|saca|sortea)\b.*\b(?:estudiante|alumno|alumna|"
                      r"alguien|persona)\b", t)
                or re.search(r"\bquien (?:pasa|sigue|responde|lee|sale|contesta)\b", t)
                or (recien and re.fullmatch(r"(?:(?:escoge |elige |saca |dame )?(?:a )?(?:otro|otra)(?: mas)?|"
                                            r"el siguiente|la siguiente|siguiente)", t))
                or re.search(r"\b(?:gira|usa) (?:la )?ruleta\b", t)):
            aula_ui["last_pick"] = time.time()
            aula_pick()
            return True
        # Asistencia
        if re.search(r"\b(?:llama(?:r)? (?:a )?lista|toma(?:r)? (?:la )?asistencia|pasa(?:r)? lista|lista de asistencia)\b", t):
            aula_start_attendance()
            return True
        if re.search(r"\b(?:guarda|exporta|termina|cierra)\b.*\basistencia\b", t):
            aula_export_attendance()
            return True
        if time.time() < aula_ui["attendance_until"]:
            m = re.match(r"^(?:falta|faltan|ausente|no vino|no esta|no llego|no asistio)\s+(.+)$", t)
            if m:
                aula_mark_voice(m.group(1), present=False)
                return True
            m = re.match(r"^(?:llego|presente|ya llego|si vino|vino|si esta)\s+(.+)$", t)
            if m:
                aula_mark_voice(m.group(1), present=True)
                return True
        # Semáforo de ruido
        if re.search(r"\bsemaforo\b", t):
            if re.search(r"\b(?:desactiva|apaga|quita|cierra|deten|para)\b", t):
                aula_emit({"type": "view", "view": "ruleta"})
                reply("Semáforo de ruido apagado.", "AULA")
            else:
                open_aula_window("semaforo")
                reply("Semáforo de ruido en el tablero. Verde está bien, amarillo es un aviso y rojo, silencio.", "AULA")
            return True
        # Tablero
        if re.search(r"\b(?:abre|muestra|pon|abrir)\b.*\b(?:tablero|pizarra)\b|\bmodo aula\b", t):
            open_aula_window()
            reply("Tablero del aula abierto. Puedes arrastrarlo al videobeam y ponerlo en pantalla completa.", "AULA")
            return True
    except ValueError as e:
        reply(str(e), "AULA")
        return True
    return False


# =============================================================================
# REVISIÓN DE TRABAJOS (cámara, pantalla o imagen). La lógica está en revision.py.
# =============================================================================
review_state = {"path": "", "source": "", "busy": False}


def _revision_tmp():
    return os.path.join(tempfile.gettempdir(), f"jarvis_trabajo_{uuid.uuid4().hex}.png")


def _set_review_image(path, source):
    old = review_state.get("path")
    if old and old != path and os.path.basename(old).startswith("jarvis_trabajo_"):
        try:
            os.remove(old)
        except OSError:
            pass
    review_state.update(path=path, source=source)


def _preview_b64(path, max_w=900):
    import base64
    import io
    from PIL import Image
    img = Image.open(path).convert("RGB")
    if img.width > max_w:
        img = img.resize((max_w, round(img.height * max_w / img.width)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def capture_camera(wait=0.0):
    """Toma una foto con la cámara del equipo y devuelve la ruta del PNG."""
    try:
        import cv2
    except ImportError:
        raise ValueError("Para usar la cámara falta un componente. Ejecuta instalar.bat otra vez "
                         "(o en la carpeta de Jarvis: .venv\\Scripts\\pip install opencv-python-headless). "
                         "Mientras tanto puedes usar Pantalla o subir una foto.")
    if wait:
        time.sleep(wait)
    idx = settings["camera_index"]
    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if IS_WIN else cv2.VideoCapture(idx)
    try:
        if not cap.isOpened():
            raise ValueError("No pude abrir la cámara. Revisa que no la esté usando otra aplicación "
                             "(Teams, Zoom…) y que Windows le dé permiso en Configuración › Privacidad › Cámara.")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        frame, t0 = None, time.time()
        while time.time() - t0 < 1.2:              # la cámara necesita un momento para ajustar luz y foco
            ok, f = cap.read()
            if ok:
                frame = f
        if frame is None:
            raise ValueError("La cámara no entregó imagen. Prueba con otra en el tablero (Revisar › Cámara).")
        path = _revision_tmp()
        cv2.imwrite(path, frame)
        return path
    finally:
        cap.release()


def capture_screen_for_review():
    """Captura la pantalla a buena resolución, ocultando también el tablero del aula."""
    w = hud.get("aula_win")
    hid = False
    if w is not None:
        try:
            w.hide()
            hid = True
        except Exception:
            pass
    try:
        path, _ = _capture_screen(hide_hud=True, max_w=2000)
    finally:
        if hid:
            try:
                w.show()
            except Exception:
                pass
    return path


def load_uploaded_image(data_url):
    import base64
    import io
    from PIL import Image, ImageOps
    m = re.match(r"^data:image/[\w.+-]+;base64,(.+)$", data_url or "", re.S)
    if not m:
        raise ValueError("Ese archivo no es una imagen. Usa una foto (JPG o PNG); si es un PDF, "
                         "ábrelo en pantalla y usa «Pantalla».")
    raw = base64.b64decode(m.group(1))
    if len(raw) > 15 * 1024 * 1024:
        raise ValueError("La imagen es muy grande (máximo 15 MB).")
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")   # fotos del celular, derechas
    if max(img.size) > 2400:
        img.thumbnail((2400, 2400))
    path = _revision_tmp()
    img.save(path)
    return path


def review_work(path, estudiante="", que="", clave="", grado=""):
    """Revisa el trabajo de la imagen. Devuelve (resultado, ruta del Word o "")."""
    cfg, err = _vision_cfg()
    if not cfg:
        raise ValueError(err)
    prompt = revision.build_prompt(que, clave, grado, estudiante)
    msgs = [{"role": "user", "content": prompt}]
    global thinking
    thinking += 1
    refresh_mode()
    try:
        if cfg["kind"] == "ollama":
            vmodel = settings["vision_model"].strip() or "moondream"
            r = ollama.Client(host=cfg["ollama_host"], timeout=240).chat(
                model=vmodel, format="json", options={"num_predict": 1500},
                messages=[{"role": "user", "content": prompt, "images": [path]}])
            raw = r["message"]["content"]
        else:
            _need_key(cfg)
            raw = _with_fallback(cfg, lambda c: _cloud_chat(c, msgs, json_mode=True, image_path=path,
                                                            max_tokens=4000))
    finally:
        thinking -= 1
        refresh_mode()
    res = revision.validate(_extract_json(raw))
    doc = ""
    if res["legible"] and Document is not None:
        doc = revision.save_docx(res, path, settings["output_dir"], Document, estudiante,
                                 aula.data.get("activo", ""), que, settings["aula_docente"])
        generated_files.add(doc)
    return res, doc


def start_review(source="actual", estudiante="", que="", clave="", grado="", voice=False):
    """Captura (si hace falta) y revisa en segundo plano. El resultado va al tablero y se dice."""
    if review_state["busy"]:
        reply("Ya estoy revisando un trabajo; espera un momento.", "REVISION")
        return
    review_state["busy"] = True

    def work():
        try:
            if source == "camara":
                if voice:
                    reply("Pon la hoja frente a la cámara, con buena luz. Tomo la foto en 3 segundos.", "REVISION")
                _set_review_image(capture_camera(wait=3.5 if voice else 0), "camara")
            elif source == "pantalla":
                _set_review_image(capture_screen_for_review(), "pantalla")
            path = review_state["path"]
            if not path or not os.path.exists(path):
                raise ValueError("Primero toma una foto, captura la pantalla o sube una imagen.")
            if voice:
                _maybe_open_board("revisar")
            aula_emit({"type": "review", "status": "working", "preview": _preview_b64(path), "view": "revisar"})
            res, doc = review_work(path, estudiante, que, clave, grado)
            aula_emit({"type": "review", "status": "done", "result": res, "doc": doc,
                       "docname": os.path.basename(doc) if doc else "", "estudiante": estudiante})
            reply(revision.spoken_summary(res, estudiante), "REVISION")
            if res["legible"] and res["retroalimentacion"]:
                push_chat("jarvis", "📝 " + res["retroalimentacion"], "REVISION")
        except AIError as e:
            aula_emit({"type": "review", "status": "error", "error": e.why})
            reply(ai_error_reply(e), "REVISION")
        except ValueError as e:
            aula_emit({"type": "review", "status": "error", "error": str(e)})
            reply(str(e), "REVISION")
        except Exception as e:
            log_terminal(f"Revisión de trabajo: {e}", "ERROR")
            aula_emit({"type": "review", "status": "error", "error": str(e)})
            reply("No pude revisar el trabajo. Inténtalo de nuevo.", "REVISION")
        finally:
            review_state["busy"] = False
    threading.Thread(target=work, daemon=True, name="revision").start()


_REVIEW_RE = re.compile(
    r"\b(?:revisa|revisame|revisar|corrige|corrigeme|corregir|califica|calificame|calificar|evalua|evaluame)\b"
    r".*?\b(?:trabajo|taller|examen|evaluacion|prueba|quiz|tarea|cuaderno|hoja|ejercicios?|actividad|guia)\b"
    r"(?:\s+(?:de|del estudiante|de la estudiante|del alumno|de la alumna)\s+(.+?))?"
    r"(?:\s+(?:en|con|por)\s+(?:la\s+)?(pantalla|camara|foto|imagen))?$")


def review_voice(text, t):
    """«revisa el taller de Juan», «califica este examen en la pantalla». True si era para esto."""
    m = _REVIEW_RE.search(t)
    # «revisa mi trabajo» / «lo que estoy haciendo» es la ayuda con tu pantalla, no un trabajo de estudiante
    if not m or re.search(r"\b(?:mi|mis|lo que estoy)\b", t):
        return False
    quien, medio = (m.group(1) or "").strip(), m.group(2) or ""
    estudiante = ""
    if quien and quien not in ("este", "esta", "esto", "aqui"):
        # «el examen de matemáticas de Juan»: el estudiante es lo último tras «de»
        opciones = [quien] + ([quien.rsplit(" de ", 1)[1]] if " de " in quien else [])
        try:
            _, names = aula.active()
            for op in reversed(opciones):
                estudiante, _c = aula.find_student(op, names)
                if estudiante:
                    break
        except ValueError:
            pass
        estudiante = estudiante or opciones[-1].title()
    source = "pantalla" if medio == "pantalla" else "actual" if medio in ("foto", "imagen") else "camara"
    start_review(source, estudiante=estudiante, voice=True)
    return True


# =============================================================================
# VISIÓN DE PANTALLA Y COPILOTO
#   · A demanda: «¿qué hay en la pantalla?» (describe) o «ayúdame con esto» (sugerencias).
#   · Copiloto: cada pocos minutos mira la pantalla y, SOLO si tiene algo útil, sugiere.
#   Nunca captura ventanas sensibles (contraseñas, bancos, pagos, navegación privada).
# =============================================================================
SENSITIVE_TITLES = re.compile(
    r"contrase|password|clave|iniciar sesi|inicio de sesi|sign.?in|log.?in|banco|bank|bancolombia|"
    r"davivienda|nequi|daviplata|paypal|pago|payment|checkout|tarjeta|inprivate|incognito|"
    r"privad[ao]|bitwarden|1password|keepass|lastpass", re.I)
copilot = {"last_run": 0.0, "thumb": None, "recent": deque(maxlen=6), "skipped_sensitive": 0.0}


def _foreground_title():
    """Título de la última ventana que usaste (no la de Jarvis)."""
    if not IS_WIN:
        return ""
    try:
        h = skills._last_ext.get("hwnd") or skills.user32.GetForegroundWindow()
        return skills._title_of(h) or ""
    except Exception:
        return ""


def _idle_seconds():
    """Segundos desde la última vez que tocaste teclado o ratón."""
    if not IS_WIN:
        return 0.0
    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        li = LASTINPUTINFO()
        li.cbSize = ctypes.sizeof(li)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li)):
            return (ctypes.windll.kernel32.GetTickCount() - li.dwTime) / 1000.0
    except Exception:
        pass
    return 0.0


def _capture_screen(hide_hud=True, max_w=1280):
    """Captura la pantalla reducida (más rápida y gasta menos cuota). Devuelve (ruta, imagen)."""
    path = os.path.join(tempfile.gettempdir(), f"jarvis_vista_{uuid.uuid4().hex}.png")
    if hide_hud:
        _temp_hide(True)
        time.sleep(0.35)
    try:
        img = skills.pyautogui.screenshot()
    finally:
        if hide_hud:
            _temp_hide(False)
    if img.width > max_w:
        img = img.resize((max_w, round(img.height * max_w / img.width)))
    img.save(path, optimize=True)
    return path, img


def _vision_cfg():
    """Proveedor que puede ver imágenes: el elegido si puede; si no, Gemini con tu clave."""
    cfg = _ai_cfg()
    if cfg["kind"] == "ollama":
        if ollama is None:
            return None, "Para la visión con Ollama falta la librería 'ollama'."
        return cfg, None
    if cfg["spec"].get("vision") and cfg["key"]:
        return cfg, None
    g = _gemini_for_stt()
    if g:
        return g, None
    return None, (f"Con {cfg['label']} no puedo ver la pantalla. Funciona con Gemini, Claude, ChatGPT "
                  "u Ollama con un modelo de visión; o guarda una clave de Gemini en Ajustes, sección IA.")


def _vision_chunks(cfg, prompt, path, history=()):
    """Fragmentos de la respuesta del modelo de visión, a medida que se generan."""
    msgs = [*history, {"role": "user", "content": prompt}]
    if cfg["kind"] != "ollama":
        _need_key(cfg)
        return _with_fallback(cfg, lambda c: _cloud_stream(c, msgs, image_path=path))
    vmodel = settings["vision_model"].strip() or "moondream"

    def oll():
        st = ollama.Client(host=cfg["ollama_host"], timeout=180).chat(
            model=vmodel, stream=True, keep_alive="30m",
            messages=[*history, {"role": "user", "content": prompt, "images": [path]}],
            options={"num_predict": 260})
        for part in st:
            c = (part.get("message") or {}).get("content", "")
            if c:
                yield c
    return oll()


def _work_context():
    title = _foreground_title()
    ctx = f" La ventana activa es «{title}»." if title else ""
    if settings["copilot_context"].strip():
        ctx += f" Sobre su trabajo, el usuario te contó: {settings['copilot_context'].strip()}"
    return title, ctx


def screen_assist(pregunta="", mode="describe"):
    """mode='describe': qué hay en pantalla. mode='help': sugerencias para lo que estás haciendo."""
    if skills.pyautogui is None:
        reply("Para ver la pantalla necesito la librería pyautogui.", "VISION")
        return
    cfg, err = _vision_cfg()
    if not cfg:
        reply(err, "VISION")
        return
    title, ctx = _work_context()
    if title and SENSITIVE_TITLES.search(title):
        reply("Esa ventana parece privada (contraseñas, banco o pagos), así que no la voy a capturar.", "VISION")
        return
    path, _ = _capture_screen(hide_hud=True)
    if mode == "help":
        prompt = ("Eres Jarvis, el asistente personal del usuario. Mira esta captura de su pantalla." + ctx +
                  " En una frase di qué está haciendo, y luego dale dos o tres sugerencias concretas y "
                  "útiles para esa tarea: errores que veas, algo que falte, una forma más rápida de "
                  "hacerlo o el siguiente paso. Responde en español hablado y breve, como una "
                  "conversación: sin listas, sin markdown, máximo cinco frases.")
        if pregunta.strip():
            prompt += f" Lo que te pidió exactamente: «{pregunta.strip()}»."
    else:
        prompt = ("Describe en español, de forma breve y clara, lo que se ve en esta captura de "
                  "pantalla de un computador. Si hay texto importante, menciónalo.")
        if pregunta.strip():
            prompt += f" En concreto: {pregunta.strip()}"
    global thinking
    thinking += 1
    refresh_mode()
    full, buf = "", ""
    try:
        for chunk in _vision_chunks(cfg, prompt, path):
            full += chunk
            buf += chunk
            m = _SENT_END.search(buf)
            while m:
                sent = buf[:m.end()].strip()
                buf = buf[m.end():]
                if len(sent) > 1:
                    speak(_clean_for_speech(sent))
                m = _SENT_END.search(buf)
    except Exception as e:
        msg = str(e)
        vmodel = settings["vision_model"].strip() or "moondream"
        if cfg["kind"] == "ollama" and ("not found" in msg.lower() or "pull" in msg.lower()):
            reply(f"No tengo el modelo de visión «{vmodel}». En una terminal ejecuta: ollama pull {vmodel}.", "VISION")
        else:
            log_terminal(f"Error de visión: {e}", "ERROR")
            reply(ai_error_reply(e) if isinstance(e, AIError) else "No pude analizar la pantalla.", "VISION")
        return
    finally:
        thinking -= 1
        refresh_mode()
        try:
            os.remove(path)
        except OSError:
            pass
    if buf.strip():
        speak(_clean_for_speech(buf))
    full = full.strip() or "No distinguí nada claro en la pantalla."
    log_terminal(full, "VISION")
    push_chat("jarvis", full, "VISION")
    # Se recuerda lo que vio: así puedes seguir preguntando («¿y cómo hago eso?»).
    keep = settings["history_turns"] * 2
    pedido = pregunta.strip() or ("ayúdame con lo que tengo en pantalla" if mode == "help" else "¿qué hay en la pantalla?")
    chat_history.extend([{"role": "user", "content": f"{pedido} (le mostré a Jarvis mi pantalla{': ' + title if title else ''})"},
                         {"role": "assistant", "content": full}])
    del chat_history[:-max(keep, 2)]
    save_memory()


def describe_screen(pregunta=""):
    screen_assist(pregunta, "describe")


def _screen_changed(img):
    """Compara una miniatura en grises con la anterior: si la pantalla casi no cambió, no
    tiene sentido gastar una consulta."""
    small = list(img.convert("L").resize((48, 27)).getdata())
    prev, copilot["thumb"] = copilot["thumb"], small
    if prev is None:
        return True
    diff = sum(abs(a - b) for a, b in zip(small, prev)) / len(small)
    return diff >= 3.0


def copilot_tick(force=False):
    """Una pasada del copiloto. Devuelve la sugerencia, o None si no había nada útil."""
    cfg, err = _vision_cfg()
    if not cfg or skills.pyautogui is None:
        return None
    title, ctx = _work_context()
    if title and SENSITIVE_TITLES.search(title):
        if time.time() - copilot["skipped_sensitive"] > 600:
            log_terminal("Copiloto en pausa: la ventana activa parece privada.", "COPILOTO")
            copilot["skipped_sensitive"] = time.time()
        return None
    path, img = _capture_screen(hide_hud=False)            # sin parpadeos del HUD
    try:
        if not force and not _screen_changed(img):
            return None
        anteriores = " | ".join(copilot["recent"]) or "ninguna"
        prompt = ("Eres el copiloto de Jarvis y observas la pantalla del usuario mientras trabaja." + ctx +
                  " Ignora el pequeño panel de Jarvis. Si ves algo concreto en lo que puedas ayudar ahora "
                  "mismo (un error, algo que falta, una forma más rápida de hacerlo o un dato útil para su "
                  "tarea), responde con UNA sola sugerencia breve, de máximo dos frases, en español, "
                  "dirigida al usuario. Si no hay nada realmente útil, responde exactamente: NADA. "
                  f"No describas la pantalla. No repitas estas sugerencias anteriores: {anteriores}.")
        text = "".join(_vision_chunks(cfg, prompt, path)).strip()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    clean = text.strip().strip('"«»').strip()
    if not clean or re.match(r"^\W*nada\b", clean, re.I):
        return None
    copilot["recent"].append(clean[:160])
    log_terminal(clean, "COPILOTO")
    push_chat("jarvis", "💡 " + clean, "COPILOTO")
    socketio.emit("copilot_tip", {"text": clean})
    chat_history.append({"role": "assistant", "content": f"(Sugerencia del copiloto mirando tu pantalla) {clean}"})
    save_memory()
    if settings["copilot_speak"]:
        speak(_clean_for_speech(clean))
    return clean


def _copilot_worker():
    while True:
        time.sleep(10)
        if not settings["copilot_enabled"]:
            continue
        if time.time() - copilot["last_run"] < settings["copilot_interval"] * 60:
            continue
        # Solo mientras trabajas: no si estás ausente, dictando o si Jarvis está hablando/pensando.
        if dictation_on.is_set() or tts_playing.is_set() or thinking or _idle_seconds() > 120:
            continue
        if is_offline() and _vision_cfg()[0] and _vision_cfg()[0]["kind"] != "ollama":
            continue                                       # sin internet: el copiloto espera
        copilot["last_run"] = time.time()
        try:
            copilot_tick()
        except AIError as e:
            log_terminal(f"Copiloto: {e.why}", "AVISO")
        except Exception as e:
            log_terminal(f"Copiloto: {e}", "AVISO")


def set_copilot(on, interval=None):
    changes = {"copilot_enabled": bool(on)}
    if interval:
        changes["copilot_interval"] = interval
    errs = apply_settings(changes)
    if on:
        copilot.update(thumb=None, last_run=time.time() - settings["copilot_interval"] * 60 + 20)
    return errs


def _key(*keys):
    """Pulsa una tecla o combinación en la ventana activa (si hay pyautogui)."""
    if skills.pyautogui is None:
        return
    if len(keys) == 1:
        skills.pyautogui.press(keys[0])
    else:
        skills.pyautogui.hotkey(*keys)


def dictation_control(t, text):
    """Comandos para operar controles de formularios HTML por voz durante el dictado.
    Devuelve True si manejó el comando. t = texto normalizado, text = texto original."""
    # Moverse entre campos y controles
    if re.fullmatch(r"(?:siguiente campo|tabulador|tab|siguiente control|pasa al siguiente|siguiente)", t):
        _key("tab"); return True
    if re.fullmatch(r"(?:campo anterior|control anterior|regresa el campo|anterior)", t):
        _key("shift", "tab"); return True

    # Casillas de verificación y botones de opción -> barra espaciadora
    if re.fullmatch(r"(?:marca(?:r)?|activa(?:r)?|selecciona(?:r)?|desmarca(?:r)?|quita(?:r)? la marca|pulsa (?:la )?barra|espacio|marca (?:la |esta )?casilla|activa (?:la |esta )?casilla)"
                    r"(?: (?:la |esta )?(?:casilla|opcion|opción))?", t):
        _key("space"); return True

    # Listas desplegables (<select>)
    if re.fullmatch(r"(?:abre(?:r)? (?:la )?lista|despliega(?:r)?|abre(?:r)? (?:el )?menu|muestra (?:las )?opciones|despliega el menu)", t):
        _key("alt", "down"); return True
    if re.fullmatch(r"(?:cierra (?:la )?lista|cierra (?:el )?menu|escape|cancela(?:r)?)", t):
        _key("esc"); return True

    # Flechas (botones de opción, listas, deslizadores)
    if re.fullmatch(r"(?:abajo|baja|siguiente opcion|siguiente opción|bajar)", t):
        _key("down"); return True
    if re.fullmatch(r"(?:arriba|sube|opcion anterior|opción anterior|subir)", t):
        _key("up"); return True
    if re.fullmatch(r"(?:derecha|a la derecha|aumenta(?:r)?)", t):
        _key("right"); return True
    if re.fullmatch(r"(?:izquierda|a la izquierda|disminuye(?:r)?|reduce)", t):
        _key("left"); return True
    if re.fullmatch(r"(?:primero|al principio|inicio)", t):
        _key("home"); return True
    if re.fullmatch(r"(?:ultimo|ultima|al final|final)", t):
        _key("end"); return True

    # Elegir una opción por su texto: «elige Grado once», «selecciona azul»
    m = re.match(r"^\s*(?:elige|escoge|selecciona|opcion|opción|pon)\s+(.+)$", text, re.I)
    if m and skills.pyautogui is not None:
        valor = m.group(1).strip(" .,:")
        if skills.pyperclip:                      # pegar es más fiable con tildes y espacios
            try:
                old = skills.pyperclip.paste()
            except Exception:
                old = None
            skills.pyperclip.copy(valor)
            skills.pyautogui.hotkey("ctrl", "v")
            if old is not None:
                threading.Timer(0.6, lambda: skills.pyperclip.copy(old)).start()
        else:
            skills.pyautogui.write(valor, interval=0.02)
        log_terminal(f"Opción: {valor}", "DICTADO")
        return True

    # Enviar / aceptar
    if re.fullmatch(r"(?:enviar(?: (?:el )?formulario)?|acepta(?:r)?|confirma(?:r)?)", t):
        _key("enter"); return True

    # Borrar
    if re.fullmatch(r"(?:borra(?:r)? (?:el )?campo|limpia(?:r)? (?:el )?campo)", t):
        _key("ctrl", "a"); _key("delete"); return True
    if re.fullmatch(r"(?:borra(?:r)?|borrar lo ultimo|retrocede)", t):
        if skills.pyautogui:
            skills.pyautogui.press("backspace", presses=12)
        return True
    return False


def handle_dictation(text):
    t = normalize(text)
    if re.search(DICTATION_STOP_RE, t):
        _set_dictation(False)
        reply("Dictado finalizado.", "PC")
        return
    if re.fullmatch(r"(?:activa(?:r)?|modo|empieza) (?:el )?(?:modo )?matematic[ao]s?", t):
        dictation_math.set()
        reply("Modo matemático activado: diré los números y símbolos como fórmula.", "PC")
        return
    if re.fullmatch(r"(?:desactiva(?:r)?|quita|modo) (?:el )?(?:modo )?(?:matematic[ao]s?|normal|texto)", t):
        dictation_math.clear()
        reply("Dictado de texto normal.", "PC")
        return
    if re.fullmatch(r"(?:nueva linea|salto de linea|nuevo renglon|enter)", t):
        _key("enter")
        return
    # Navegación de formularios HTML por voz (incluye controles especiales)
    if dictation_control(t, text):
        return
    try:
        out = skills.transcribe_math(text) if dictation_math.is_set() else text
        skills.dictation_type(out)
        log_terminal(f"Dictado: {out}", "DICTADO")
    except skills.SkillError as e:
        reply(str(e), "PC")
    except Exception as e:
        log_terminal(f"Error de dictado: {e}", "ERROR")


def run_skill(name, args, confirmed=False):
    sk = skills.REGISTRY.get(name)
    if not sk:
        return False
    if sk.dangerous and not confirmed:
        pending.update(skill=name, args=args, expires=time.time() + 25)
        reply(sk.confirm_text(args) + " Di «confirmar» o «cancelar».", "PC")
        return True
    log_terminal(f"Acción: {name} {json.dumps(args, ensure_ascii=False)}", "PC")
    _run_skill_guarded(name, sk, args)
    return True


def _deliver_skill(name, args, box):
    if "err" in box:
        e = box["err"]
        if getattr(e, "need", None):
            followup.update(skill=name, args=dict(args or {}), need=e.need,
                            expires=time.time() + 45)
        reply(str(e), "PC")
    elif "exc" in box:
        log_terminal(f"Fallo en la habilidad {name}: {box['exc']}", "ERROR")
        reply("No pude completar esa acción.", "PC")
    else:
        reply(box.get("out") or "Hecho.", "PC")


def _run_skill_guarded(name, sk, args):
    """Ejecuta la acción en su propio hilo. Si se cuelga (una ventana que no responde,
    una web que no carga...), Jarvis no se queda bloqueado: sigue con las demás órdenes
    y da el resultado cuando llegue."""
    box, lock, state = {}, threading.Lock(), {"done": False, "late": False}

    def work():
        try:
            box["out"] = sk.run(args)
        except skills.SkillError as e:
            box["err"] = e
        except Exception as e:
            box["exc"] = e
        with lock:
            state["done"] = True
            late = state["late"]
        if late:
            _deliver_skill(name, args, box)

    t = threading.Thread(target=work, daemon=True, name=f"skill-{name}")
    t.start()
    t.join(SKILL_TIMEOUT)
    with lock:
        if not state["done"]:
            state["late"] = True
    if state["late"]:
        log_terminal(f"La acción {name} tarda más de {SKILL_TIMEOUT} s; sigo atendiendo.", "AVISO")
        reply("Eso está tardando más de lo normal. Te aviso cuando termine.", "PC")
    else:
        _deliver_skill(name, args, box)


def process_command(text):
    t = normalize(text)
    if not t:
        return

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
        return

    # Rutinas: «modo clase», «fin de clase», «¿qué rutinas tengo?»
    if routine_voice(text, t):
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

    # Revisar trabajos: «revisa el taller de Juan», «califica este examen en la pantalla»
    if review_voice(text, t):
        return

    # Aula: sorteo, grupos, asistencia, semáforo, tablero y material de clase
    if aula_voice(text, t):
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
        # Preguntas claras -> respuesta en streaming (más rápida, sin pasar por el enrutador).
        is_question = text.strip().endswith("?") or bool(QUESTION_RE.search(t))
        if is_question or not settings["ai_router"]:
            answer_question_streaming(text)
            return
        result = ask_ai(text, route=True)
        if result[0] == "skill":
            run_skill(result[1], result[2])
        else:
            reply(result[1])


command_queue = queue.Queue()


def submit_command(text, source="texto"):
    # Durante el dictado, «para» y demás son texto que se escribe, no la orden de detener la voz.
    if not dictation_on.is_set() and is_stop_command(normalize(text)):
        stop_speech()
        return
    if not dictation_on.is_set():
        push_chat("user", text, source)
    command_queue.put(text)


def _command_worker():
    while True:
        text = command_queue.get()
        try:
            process_command(text)
        except Exception as e:
            log_terminal(f"Error procesando '{text}': {e}", "ERROR")


# =============================================================================
# ESCUCHA CONTINUA (VOSK)
# =============================================================================
mic_restart = threading.Event()
_pa = None
_pa_lock = threading.Lock()


def _get_pa():
    global _pa
    with _pa_lock:
        if _pa is None:
            _pa = pyaudio.PyAudio()
        return _pa


def list_mics():
    if pyaudio is None:
        return []
    pa = _get_pa()
    devices = []
    for i in range(pa.get_device_count()):
        try:
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                api = pa.get_host_api_info_by_index(info["hostApi"])["name"]
                devices.append({"index": i, "name": f"{info['name']} · {api}"})
        except Exception:
            continue
    return devices


def activate_listening():
    """Como decir «Jarvis»: la siguiente frase se toma como orden."""
    global wake_until
    wake_until = time.time() + settings["wake_window"]
    refresh_mode()
    threading.Timer(settings["wake_window"] + 0.1, refresh_mode).start()
    speak("¿Sí?")


# -----------------------------------------------------------------------------
# ESCUCHA EN DOS ETAPAS
# 1) Vosk escucha todo en el PC (gratis, sin enviar nada) solo para saber si le hablas a Jarvis.
# 2) Si la frase es para Jarvis, ese mismo audio se transcribe con un reconocedor preciso
#    (Gemini con tu clave, o Whisper en local) y se le dan las palabras que suelen aparecer
#    (contactos, apps, órdenes). Lo que se habla en el ambiente nunca sale del PC.
# -----------------------------------------------------------------------------
voice_queue = queue.Queue()
_WAKE_FILLERS = {"hola", "oye", "oiga", "ey", "hey", "eh", "ya", "la", "el", "a", "bueno",
                 "ok", "okay", "vale", "ahora", "y", "pues", "mira"}
_STT_WORDS = ("WhatsApp, Telegram, Spotify, YouTube, Google, Chrome, Edge, Word, Excel, PowerPoint, "
              "Gemini, temporizador, recordatorio, volumen, brillo, captura de pantalla, diapositiva, "
              "videobeam, dictado, modo sigilo, mostrar panel, calculadora, explorador de archivos")


def _match_wake(text):
    """¿La frase va dirigida a Jarvis? Tolera cómo suele transcribirse la palabra de
    activación («yarvis», «jarvi»...) y muletillas delante («hola jarvis», «ya jarvis»).
    Devuelve el resto de la frase (puede ser "") o None si no va dirigida a Jarvis."""
    import difflib
    orig = text.split()
    words = normalize(text).split()
    for w in get_wake_words():
        ww = normalize(w).split()
        n = len(ww)
        for start in range(0, min(3, len(words))):
            cand = " ".join(words[start:start + n])
            if not cand:
                continue
            ok = cand == " ".join(ww) or (len(cand) >= 4 and len(" ".join(ww)) >= 5 and
                                          difflib.SequenceMatcher(None, cand, " ".join(ww)).ratio() >= 0.8)
            if ok and all(x in _WAKE_FILLERS for x in words[:start]):
                rest = orig[start + n:] if len(orig) == len(words) else words[start + n:]
                return " ".join(rest).strip(" ,.:;")
    return None


def _stt_vocab_sentence():
    contacts = list(skills._parse_contacts().keys())[:25] if hasattr(skills, "_parse_contacts") else []
    wake = ", ".join(get_wake_words()) or "Jarvis"
    extra = f" Contactos: {', '.join(c.title() for c in contacts)}." if contacts else ""
    return f"Órdenes para el asistente {wake.title()}: {_STT_WORDS}.{extra}"


def _wav_bytes(raw, rate=16000):
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(raw)
    return buf.getvalue()


def _gemini_for_stt():
    """Configuración de Gemini para transcribir (sirve aunque la IA elegida sea otra)."""
    cfg = _ai_cfg({"ai_provider": "gemini"})
    return cfg if cfg["key"] else None


_whisper_refiner = {"model": None, "size": None, "failed": False}


def _whisper_transcribe(raw):
    if _whisper_refiner["failed"]:
        return None
    try:
        size = settings["whisper_model"]
        if _whisper_refiner["model"] is None or _whisper_refiner["size"] != size:
            from faster_whisper import WhisperModel
            _whisper_refiner.update(model=WhisperModel(size, device="cpu", compute_type="int8"), size=size)
        import numpy as np
        audio = np.frombuffer(raw, dtype=np.int16).astype("float32") / 32768.0
        segs, _ = _whisper_refiner["model"].transcribe(
            audio, language="es", beam_size=1, vad_filter=False, initial_prompt=_stt_vocab_sentence())
        return " ".join(sg.text for sg in segs).strip()
    except ImportError:
        _whisper_refiner["failed"] = True
        return None
    except Exception as e:
        log_terminal(f"Whisper no pudo transcribir: {e}", "AVISO")
        return None


def _gemini_transcribe(raw):
    cfg = _gemini_for_stt()
    if not cfg:
        return None
    prompt = ("Transcribe exactamente lo que dice la persona en este audio, en español de Colombia. "
              "Le está hablando a su asistente de voz en un computador con Windows. "
              f"Palabras que pueden aparecer: {_stt_vocab_sentence()} "
              "Devuelve SOLO la transcripción, sin comillas ni comentarios. "
              "Si no hay ninguna voz clara, devuelve exactamente: (nada)")
    body_msgs = [{"role": "user", "content": prompt}]

    def call(c):
        url = f"{GEMINI_BASE}/models/{c['model']}:generateContent"
        data = _post(url, _gemini_headers(c),
                     _gemini_body(c, body_msgs, 300, audio_wav=_wav_bytes(raw), temperature=0),
                     _GEMINI_OPTIONAL, timeout=12)
        return _gemini_text(data)
    try:
        out = _with_fallback(cfg, call)
    except AIError as e:
        log_terminal(f"Gemini no pudo transcribir ({e.why}); uso el reconocimiento local.", "AVISO")
        return None
    out = re.sub(r"^\s*(transcripci[oó]n|texto)\s*:\s*", "", out or "", flags=re.I).strip().strip('"«»“”')
    return "" if out.lower().strip(" .") == "(nada)" else out


def stt_refine_mode():
    """Qué 2ª etapa se usará ahora: 'gemini', 'whisper' u 'off'."""
    want = settings["stt_refine"]
    if want == "off":
        return "off"
    if want in ("auto", "gemini") and _gemini_for_stt() and not is_offline():
        return "gemini"
    if want in ("auto", "whisper") and settings["stt_backend"] != "whisper":
        try:
            import importlib.util
            if importlib.util.find_spec("faster_whisper"):
                return "whisper"
        except Exception:
            pass
    return "off"


def refine_speech(raw, fallback):
    """Transcribe bien una frase dirigida a Jarvis. Si no se puede, devuelve la de Vosk."""
    if not raw or len(raw) < 16000 * 2 * 0.4:            # menos de 0,4 s: nada que mejorar
        return fallback
    mode = stt_refine_mode()
    if mode == "off":
        return fallback
    t0 = time.time()
    out = _gemini_transcribe(raw) if mode == "gemini" else _whisper_transcribe(raw)
    if out is None or out == "":
        return fallback
    if normalize(out) != normalize(fallback):
        log_terminal(f"Entendido con {mode.title()} en {time.time() - t0:.1f} s "
                     f"(el reconocimiento local había oído: «{fallback}»)", "AUDIO")
    return out


def _voice_worker():
    while True:
        text, raw = voice_queue.get()
        try:
            handle_voice(text, raw)
        except Exception as e:
            log_terminal(f"Error procesando la voz: {e}", "ERROR")


def handle_voice(text, raw=None):
    global wake_until
    socketio.emit("heard", {"text": text})
    # En dictado, todo lo que se oye se escribe sin necesidad de decir «Jarvis».
    if dictation_on.is_set():
        text = refine_speech(raw, text)
        log_terminal(f'"{text}"', "VOZ")
        command_queue.put(text)
        return
    # Descarta transcripciones demasiado cortas (ruidos, sílabas sueltas del ambiente).
    if len(normalize(text)) < settings["min_command_chars"]:
        log_terminal(f'"{text}"', "VOZ")
        return

    window_open = (time.time() < wake_until
                   or (pending["skill"] and time.time() < pending["expires"])
                   or (followup["skill"] and time.time() < followup["expires"]))
    wake_rest = None
    if settings["require_hotkey"]:                     # solo tras Ctrl+Alt+Espacio
        if time.time() >= wake_until:
            log_terminal(f'"{text}"', "VOZ")
            return
    elif settings["wake_word_enabled"]:
        wake_rest = _match_wake(text)
        if wake_rest is None and not window_open:      # conversación del ambiente: no sale del PC
            log_terminal(f'"{text}"', "VOZ")
            return
        if wake_rest == "":                            # solo dijo «Jarvis»
            log_terminal(f'"{text}"', "VOZ")
            activate_listening()
            return

    # La frase es para Jarvis: 2ª etapa con el reconocedor preciso.
    final = refine_speech(raw, text)
    if settings["wake_word_enabled"]:                  # quita «Jarvis» de la versión precisa
        rest = _match_wake(final)
        if rest:
            final = rest
        elif rest == "":
            final = wake_rest or ""
    final = final.strip().rstrip(".").strip()
    log_terminal(f'"{final}"', "VOZ")
    if not final.strip():
        activate_listening()
        return
    wake_until = 0.0
    refresh_mode()
    submit_command(final, "voz")


def _passes_gate(text, peak):
    gate = settings["mic_sensitivity"] / 100
    if gate and peak < gate:
        log_terminal(f"Ignorado (sonido lejano/flojo): «{text}»", "AUDIO")
        return False
    return True


class VoskEngine:
    """Reconocimiento en streaming con Vosk (ligero, siempre disponible)."""
    label = "VOSK"

    def __init__(self):
        model_path = get_resource_path("model_es")
        if Model is None:
            raise RuntimeError("Vosk no está instalado.")
        if not os.path.isdir(model_path):
            raise RuntimeError(f"Modelo Vosk no encontrado en {model_path}. Ejecuta descargar_modelo.py.")
        SetLogLevel(-1)
        self.rec = KaldiRecognizer(Model(model_path), 16000)
        self.utt_peak = 0.0
        self.audio = bytearray()          # audio de la frase en curso (para la 2ª etapa)
        self.last_audio = b""

    MAX_AUDIO = 16000 * 2 * 20            # guarda como mucho 20 s

    def feed(self, data, peak):
        self.utt_peak = max(self.utt_peak, peak)
        self.audio += data
        if len(self.audio) > self.MAX_AUDIO:
            del self.audio[:len(self.audio) - self.MAX_AUDIO]
        if self.rec.AcceptWaveform(data):
            text = json.loads(self.rec.Result()).get("text", "").strip()
            up, self.utt_peak = self.utt_peak, 0.0
            self.last_audio, self.audio = bytes(self.audio), bytearray()
            if text and _passes_gate(text, up):
                return text
        return None

    def reset(self):
        self.rec.Reset()
        self.utt_peak = 0.0
        self.audio = bytearray()


class WhisperEngine:
    """Reconocimiento con faster-whisper (más preciso). Trocea por silencios (endpointing)."""
    label = "WHISPER"
    CHUNK_SEC = 0.25          # cada lectura son 4000 muestras a 16 kHz

    def __init__(self):
        from faster_whisper import WhisperModel
        import numpy as np
        self.np = np
        size = settings["whisper_model"]
        self.model = WhisperModel(size, device="cpu", compute_type="int8")
        self.buf = bytearray()
        self.speaking = False
        self.silence = 0
        self.speech_chunks = 0
        self.utt_peak = 0.0
        self.last_audio = b""

    def feed(self, data, peak):
        thr = max(0.02, settings["mic_sensitivity"] / 100)     # umbral de habla
        if peak >= thr:
            self.speaking = True
            self.silence = 0
            self.speech_chunks += 1
            self.buf += data
            self.utt_peak = max(self.utt_peak, peak)
        elif self.speaking:
            self.buf += data
            self.silence += 1
            if self.silence >= 3:                               # ~0.75 s de silencio -> fin de frase
                return self._finish()
        if len(self.buf) > 16000 * 2 * 15:                      # tope de 15 s
            return self._finish()
        return None

    def _finish(self):
        raw = bytes(self.buf)
        self.last_audio = raw
        up = self.utt_peak
        speech = self.speech_chunks
        self.reset()
        if speech < 2:                                          # menos de ~0,5 s de voz real: ruido
            return None
        audio = self.np.frombuffer(raw, dtype=self.np.int16).astype("float32") / 32768.0
        try:
            segs, _ = self.model.transcribe(audio, language="es", beam_size=1, vad_filter=False,
                                            initial_prompt=_stt_vocab_sentence())
            text = " ".join(s.text for s in segs).strip()
        except Exception as e:
            log_terminal(f"Fallo de Whisper: {e}", "ERROR")
            return None
        if text and _passes_gate(text, up):
            return text
        return None

    def reset(self):
        self.buf = bytearray()
        self.speaking = False
        self.silence = 0
        self.speech_chunks = 0
        self.utt_peak = 0.0


def make_stt_engine():
    if settings["stt_backend"] == "whisper":
        try:
            eng = WhisperEngine()
            log_terminal(f"Reconocimiento con Whisper ({settings['whisper_model']}).", "SISTEMA")
            return eng
        except Exception as e:
            log_terminal(f"No se pudo iniciar Whisper ({e}). Uso Vosk.", "AVISO")
    return VoskEngine()


_STOP_ALONE = {"basta", "callate", "silencio", "detente", "deja de hablar", "para de hablar",
               "ya basta", "ya callate", "para ya", "para para"}


def _is_echo(t):
    """¿Lo que oyó el micrófono es su propia voz saliendo por los parlantes?"""
    import difflib
    words = t.split()
    if not words:
        return True
    now = time.time()
    for ts, said in list(tts_recent):
        if now - ts > 25:
            continue
        if t in said:
            return True
        sw = said.split()
        n = len(words)
        for i in range(0, max(1, len(sw) - n + 1)):
            if difflib.SequenceMatcher(None, " ".join(sw[i:i + n]), t).ratio() >= 0.78:
                return True
    return False


def _barge_in(text, raw):
    """Oyó algo mientras Jarvis hablaba. Lo interrumpe solo si va dirigido a él."""
    t = normalize(text)
    if _is_echo(t):
        return False
    rest = _match_wake(text) if settings["wake_word_enabled"] else None
    stop_alone = t in _STOP_ALONE
    if rest is None and not stop_alone:
        return False                                   # ruido o conversación del salón
    stop_speech(log=False)
    log_terminal(f'Interrumpido: «{text}»', "VOZ")
    rest_n = normalize(rest or "")
    if stop_alone or is_stop_command(rest_n) or rest_n in _STOP_ALONE or rest_n in ("ya", "ok", "gracias", "listo"):
        return True                                    # solo quería que se callara
    voice_queue.put((text, raw))                       # una pregunta nueva: se atiende ya
    return True


def audio_loop():
    if pyaudio is None:
        set_state(mic="error")
        log_terminal("Falta sounddevice (o PyAudio): solo funcionarán los comandos escritos.", "AVISO")
        return
    try:
        engine = make_stt_engine()
    except Exception as e:
        set_state(mic="error")
        log_terminal(f"No se pudo iniciar el reconocimiento de voz: {e}", "ERROR")
        return

    while True:
        mic_restart.clear()
        if not settings["mic_enabled"]:
            set_state(mic="off")
            socketio.emit("mic_level", {"v": 0})
            mic_restart.wait()
            try:
                engine = make_stt_engine()          # recarga por si cambió el motor en Ajustes
            except Exception:
                pass
            continue

        device = settings["mic_device"]
        try:
            engine.reset()
            kwargs = dict(format=pyaudio.paInt16, channels=1, rate=16000,
                          input=True, frames_per_buffer=4000)
            if device >= 0:
                kwargs["input_device_index"] = device
            stream = _get_pa().open(**kwargs)
        except Exception as e:
            set_state(mic="error")
            log_terminal(f"No se pudo abrir el micrófono: {e}. Elige otro en Ajustes › Escucha.", "ERROR")
            mic_restart.wait(timeout=30)
            continue

        set_state(mic="on")
        log_terminal(f"Micrófono activo ({engine.label}).", "AUDIO")
        was_speaking = False
        last_level = 0.0
        try:
            while not mic_restart.is_set():
                data = stream.read(4000, exception_on_overflow=False)
                samples = array.array("h", data)
                peak = max(max(samples), -min(samples)) / 32768 if samples else 0
                now = time.time()
                if now - last_level > 0.12:
                    socketio.emit("mic_level", {"v": round(min(1.0, peak * 1.6), 3)})
                    last_level = now
                if tts_playing.is_set():
                    was_speaking = True
                    if not settings["barge_in"] or dictation_on.is_set():
                        continue
                    # Sigue escuchando mientras habla, pero solo le hace caso si lo llamas
                    # («Jarvis, para», «Jarvis, ¿y mañana?») o le pides que se calle.
                    text = engine.feed(data, peak)
                    if text:
                        _barge_in(text, getattr(engine, "last_audio", b""))
                    continue
                if was_speaking:
                    engine.reset()                  # descarta el eco de su propia voz
                    was_speaking = False
                text = engine.feed(data, peak)
                if text:
                    # La 2ª etapa (Gemini/Whisper) tarda ~1 s: se hace en otro hilo para no
                    # dejar de leer el micrófono mientras tanto.
                    voice_queue.put((text, getattr(engine, "last_audio", b"")))
        except Exception as e:
            set_state(mic="error")
            log_terminal(f"Lectura de micrófono interrumpida: {e}", "ERROR")
            time.sleep(2)
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        # Al reiniciar el micrófono (p. ej. cambio de motor en Ajustes), reconstruye el reconocedor.
        want_whisper = settings["stt_backend"] == "whisper"
        if want_whisper != isinstance(engine, WhisperEngine):
            try:
                engine = make_stt_engine()
            except Exception:
                pass


# =============================================================================
# VENTANA HUD (pywebview), VENTANA DE AJUSTES, BANDEJA Y ATAJOS
# =============================================================================
hud = {"window": None, "size": settings["hud_start_size"], "visible": False,
       "x": 0, "y": 0, "w": 0, "h": 0, "ignore_moves_until": 0.0,
       "settings_win": None, "quitting": False, "tray": None, "temp_hidden": False}
_save_pos_timer = None


def _work_area():
    """Área útil de la pantalla principal (sin la barra de tareas), en píxeles lógicos."""
    if IS_WIN:
        try:
            from ctypes import wintypes
            import ctypes
            rect = wintypes.RECT()
            ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0)
            try:
                scale = ctypes.windll.user32.GetDpiForSystem() / 96
            except Exception:
                scale = 1.0
            return (rect.left / scale, rect.top / scale,
                    (rect.right - rect.left) / scale, (rect.bottom - rect.top) / scale)
        except Exception:
            pass
    try:
        s = webview.screens[0]
        return s.x, s.y, s.width, s.height - 48
    except Exception:
        return 0, 0, 1366, 720


def _corner_xy(size, corner):
    w, h = HUD_SIZES[size]
    ax, ay, aw, ah = _work_area()
    m = 14
    x = ax + aw - w - m if corner.endswith("der") else ax + m
    y = ay + ah - h - m if corner.startswith("inf") else ay + m
    return int(x), int(y)


def _initial_xy(size):
    if settings["hud_position"] == "libre" and settings["hud_x"] >= 0 and settings["hud_y"] >= 0:
        return settings["hud_x"], settings["hud_y"]
    return _corner_xy(size, settings["hud_position"] if settings["hud_position"] != "libre" else "inf-der")


def _clamp(x, y, w, h):
    ax, ay, aw, ah = _work_area()
    x = max(ax, min(x, ax + aw - w))
    y = max(ay, min(y, ay + ah - h))
    return int(x), int(y)


def _on_hud_moved(x, y):
    global _save_pos_timer
    hud["x"], hud["y"] = x, y
    if time.time() < hud["ignore_moves_until"]:
        return
    if _save_pos_timer:
        _save_pos_timer.cancel()

    def _save():
        with settings_lock:
            settings.update(hud_position="libre", hud_x=max(0, int(x)), hud_y=max(0, int(y)))
            try:
                save_settings_file()
            except Exception:
                pass
    _save_pos_timer = threading.Timer(0.8, _save)
    _save_pos_timer.start()


def _apply_tool_window():
    """Quita el HUD de la barra de tareas y de Alt+Tab (sigue en la bandeja)."""
    if not (IS_WIN and settings["hud_hide_taskbar"]):
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, HUD_TITLE)
        if not hwnd:
            return
        ex = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, (ex | 0x80) & ~0x40000)     # TOOLWINDOW, sin APPWINDOW
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
    except Exception as e:
        log_terminal(f"No se pudo ocultar de la barra de tareas: {e}", "AVISO")


HUD_SOLID_BG = "#04090f"


def hud_transparency_supported():
    """¿Puede el HUD tener fondo transparente y seguir respondiendo al ratón?
    En Windows, pywebview 6 ya no hace transparente la ventana (sale un rectángulo negro o
    blanco), y forzarla con trucos de Windows deja pasar los clics a través del HUD. Así que
    con pywebview 6 en Windows se usa el fondo sólido, que funciona siempre."""
    if not IS_WIN:
        return True
    try:
        from importlib.metadata import version
        return int(version("pywebview").split(".")[0]) < 6
    except Exception:
        return False


def _on_hud_shown():
    hud["visible"] = True
    _apply_tool_window()


def _on_hud_closing():
    if hud["quitting"]:
        return True
    hud_hide()
    return False                       # cerrar = ocultar en la bandeja


HUD_LOADER = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;height:100%;background:__BG__;overflow:hidden;font:12px Consolas,monospace;color:#9fd8e6}
.box{position:fixed;inset:6px;display:flex;align-items:center;gap:14px;padding:0 16px;
background:rgba(4,10,18,.94);border:1px solid rgba(46,230,255,.32);border-radius:14px}
.ring{width:34px;height:34px;flex:none;border-radius:50%;border:3px solid rgba(46,230,255,.18);
border-top-color:#2ee6ff;animation:s 1s linear infinite}@keyframes s{to{transform:rotate(360deg)}}
b{display:block;color:#2ee6ff;letter-spacing:.2em;font-size:11px;margin-bottom:3px}
</style></head><body><div class="box"><div class="ring"></div><div><b>JARVIS</b>
<span id="t">Iniciando sistemas…</span></div></div><script>
var target="__TARGET__",ping="__PING__",n=0;
function tryit(){n++;fetch(ping,{mode:"no-cors",cache:"no-store"}).then(function(){location.replace(target)})
.catch(function(){if(n==40)document.getElementById("t").textContent="Sigue arrancando… (mira jarvis.log)";
setTimeout(tryit,500)})}tryit();
</script></body></html>"""


def create_hud(start_hidden=False, loader=False):
    """loader=True: el servidor interno aún no responde; la ventana muestra «Iniciando…»
    y entra al HUD en cuanto responde (antes mostraba una página de error)."""
    size = settings["hud_start_size"]
    w, h = HUD_SIZES[size]
    x, y = _clamp(*_initial_xy(size), w, h)
    hud.update(size=size, x=x, y=y, w=w, h=h, ignore_moves_until=time.time() + 2)
    solid = not (settings["hud_transparent"] and hud_transparency_supported())
    target = f"{URL}/?size={size}{'&solid=1' if solid else ''}"
    page = dict(url=target)
    if loader:
        page = dict(html=HUD_LOADER.replace("__TARGET__", target).replace("__PING__", f"{URL}/api/ping")
                    .replace("__BG__", HUD_SOLID_BG if solid else "transparent"))
    win = webview.create_window(
        HUD_TITLE, width=w, height=h, x=x, y=y, **page,
        frameless=True, easy_drag=False, transparent=not solid, resizable=False,
        on_top=settings["hud_on_top"], hidden=start_hidden, shadow=False,
        background_color=HUD_SOLID_BG if solid else "#000000", min_size=(80, 80))
    win.events.moved += _on_hud_moved
    win.events.shown += _on_hud_shown
    win.events.closing += _on_hud_closing
    hud["window"] = win
    hud["visible"] = not start_hidden
    return win


def _open_browser_hud():
    """Sin pywebview: abre el HUD como ventana de aplicación de Edge (sin barra de direcciones)."""
    w, h = HUD_SIZES["expandido"]
    if IS_WIN:
        try:
            subprocess.Popen(f'start "" msedge --app={URL}/?size=expandido --window-size={w},{h}',
                             shell=True, creationflags=CREATE_NO_WINDOW)
            return
        except Exception:
            pass
    webbrowser.open(f"{URL}/?size=expandido")


def hud_show():
    win = hud["window"]
    if win is None:
        if not hud.get("browser_opened"):
            hud["browser_opened"] = True
            _open_browser_hud()
        return
    win.show()
    hud["visible"] = True
    socketio.emit("hud_visible", {"visible": True})


def hud_hide():
    win = hud["window"]
    if win is not None:
        win.hide()
        hud["visible"] = False


def hud_toggle():
    if hud["window"] is None or not hud["visible"]:
        hud_show()
    else:
        hud_hide()


def _temp_hide(hidden):
    """Para las capturas de pantalla: esconde el HUD un momento."""
    if hidden:
        hud["temp_hidden"] = hud["visible"]
        if hud["temp_hidden"]:
            hud_hide()
    elif hud["temp_hidden"]:
        hud["temp_hidden"] = False
        hud_show()


def hud_set_size(size):
    if size not in HUD_SIZES:
        return
    win = hud["window"]
    hud["size"] = size
    socketio.emit("hud_size", {"size": size})
    if win is None:
        return
    nw, nh = HUD_SIZES[size]
    ax, ay, aw, ah = _work_area()
    x, y, w, h = hud["x"], hud["y"], hud["w"] or nw, hud["h"] or nh
    # Crece hacia el centro de la pantalla: si está a la derecha, crece hacia la izquierda, etc.
    nx = x + w - nw if x + w / 2 > ax + aw / 2 else x
    ny = y + h - nh if y + h / 2 > ay + ah / 2 else y
    nx, ny = _clamp(nx, ny, nw, nh)
    hud.update(x=nx, y=ny, w=nw, h=nh, ignore_moves_until=time.time() + 1.0)
    win.resize(nw, nh)
    win.move(nx, ny)


def hud_reposition():
    win = hud["window"]
    if win is None or settings["hud_position"] == "libre":
        return
    w, h = HUD_SIZES[hud["size"]]
    x, y = _corner_xy(hud["size"], settings["hud_position"])
    hud.update(x=x, y=y, w=w, h=h, ignore_moves_until=time.time() + 1.0)
    win.move(x, y)


def open_settings_window():
    if webview is None or hud["window"] is None:
        webbrowser.open(f"{URL}/ajustes")
        return
    sw = hud["settings_win"]
    if sw is not None:
        try:
            sw.show()
            sw.restore()
            return
        except Exception:
            hud["settings_win"] = None
    sw = webview.create_window("Ajustes · Jarvis", f"{URL}/ajustes", width=640, height=760,
                               min_size=(420, 520), background_color="#03060c")

    def _closed():
        hud["settings_win"] = None
    sw.events.closed += _closed
    hud["settings_win"] = sw


def close_settings_window():
    sw = hud["settings_win"]
    if sw is not None:
        try:
            sw.destroy()
        except Exception:
            pass
        hud["settings_win"] = None


def quit_app():
    hud["quitting"] = True
    log_terminal("Apagando Jarvis...", "SISTEMA")
    try:
        if hud["tray"]:
            hud["tray"].stop()
    except Exception:
        pass
    threading.Timer(0.4, lambda: os._exit(0)).start()


def toggle_mic():
    apply_settings({"mic_enabled": not settings["mic_enabled"]})
    socketio.emit("settings_updated", public_settings())


def _tray_icon_path():
    """Icono real para la bandeja/ejecutable: recursos\\icono.ico (tuyo) o static\\jarvis.ico."""
    for name in ("recursos/icono.ico", "recursos/icono.png", "jarvis.ico", "static/jarvis.ico"):
        p = get_resource_path(name)
        if os.path.isfile(p):
            return p
    return None


def start_tray():
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception:
        log_terminal("pystray/Pillow no instalados: no habrá icono en la bandeja.", "AVISO")
        return
    img = None
    icon_path = _tray_icon_path()
    if icon_path:
        try:
            img = Image.open(icon_path)      # usa tu icono.ico real si existe
        except Exception as e:
            log_terminal(f"No pude abrir el icono {icon_path}: {e}. Uso el generado.", "AVISO")
    if img is None:                          # respaldo: círculo dibujado con el color del tema
        r, g, b = THEMES[settings["theme"]][1]
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((3, 3, 61, 61), outline=(r, g, b, 255), width=5)
        d.ellipse((15, 15, 49, 49), outline=(r, g, b, 160), width=3)
        d.ellipse((24, 24, 40, 40), fill=(255, 255, 255, 255))
    item = pystray.MenuItem
    menu = pystray.Menu(
        item("Mostrar u ocultar HUD", lambda: hud_toggle(), default=True),
        item("Tamaño: orbe", lambda: (hud_show(), hud_set_size("orbe"))),
        item("Tamaño: compacto", lambda: (hud_show(), hud_set_size("compacto"))),
        item("Tamaño: expandido", lambda: (hud_show(), hud_set_size("expandido"))),
        pystray.Menu.SEPARATOR,
        item("Pausar micrófono", lambda: toggle_mic(), checked=lambda i: not settings["mic_enabled"]),
        item("Tablero del aula…", lambda: open_aula_window()),
        item("Ajustes…", lambda: open_settings_window()),
        item("Ver registro", lambda: os.startfile(LOG_PATH) if IS_WIN and os.path.exists(LOG_PATH) else None),
        pystray.Menu.SEPARATOR,
        item("Salir de Jarvis", lambda: quit_app()),
    )
    icon = pystray.Icon("jarvis", img, "Jarvis · Ctrl+Alt+J", menu)
    hud["tray"] = icon
    threading.Thread(target=icon.run, daemon=True).start()


def hotkey_loop():
    """Atajos globales: Ctrl+Alt+J (mostrar/ocultar) y Ctrl+Alt+Espacio (hablar)."""
    if not IS_WIN:
        return
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    mods = 0x0001 | 0x0002 | 0x4000            # ALT | CTRL | NOREPEAT
    ok1 = user32.RegisterHotKey(None, 1, mods, ord("J"))
    ok2 = user32.RegisterHotKey(None, 2, mods, 0x20)
    if not (ok1 and ok2):
        ocupados = [n for n, ok in (("Ctrl+Alt+J (mostrar/ocultar)", ok1),
                                    ("Ctrl+Alt+Espacio (hablar)", ok2)) if not ok]
        log_terminal(f"Atajo ocupado por otro programa: {', '.join(ocupados)}. "
                     "Lo demás funciona; puedes usar la palabra de activación.", "AVISO")
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == 0x0312:              # WM_HOTKEY
            try:
                if msg.wParam == 1:
                    hud_toggle()
                elif msg.wParam == 2:
                    hud_show()
                    activate_listening()
            except Exception as e:
                log_terminal(f"Error en atajo: {e}", "ERROR")


# =============================================================================
# AJUSTES: APLICAR CAMBIOS
# =============================================================================
def apply_settings(data):
    errors = []
    data = dict(data or {})

    if "autostart" in data:
        want = bool(data.pop("autostart"))
        if want != autostart_enabled():
            try:
                set_autostart(want)
            except Exception as e:
                errors.append(f"Autoinicio: {e}")

    for k in SECRET_FIELDS:                      # campo vacío = conservar la clave guardada
        if data.pop(f"{k}_clear", False):
            data[k] = ""
        elif not str(data.get(k) or "").strip():
            data.pop(k, None)

    changed = set()
    with settings_lock:
        for k, v in data.items():
            if k not in DEFAULT_SETTINGS or k in ("hud_x", "hud_y"):
                continue
            try:
                nv = _validate(k, v)
            except Exception as e:
                errors.append(f"{k}: {e}")
                continue
            if settings[k] != nv:
                settings[k] = nv
                changed.add(k)
        if changed:
            try:
                save_settings_file()
            except Exception as e:
                errors.append(f"No se pudo guardar config.json: {e}")

    if changed & {"mic_enabled", "mic_device", "wake_word_enabled", "wake_words",
                  "stt_backend", "whisper_model"}:
        mic_restart.set()
    if changed & {"morning_enabled", "morning_time"}:
        reschedule()
    if "tts_enabled" in changed and audio_ready:
        set_state(tts="ok" if settings["tts_enabled"] else "off")
        if not settings["tts_enabled"]:
            stop_speech()
    if "calendar_urls" in changed:
        threading.Thread(target=cal_refresh, kwargs={"force": True}, daemon=True).start()
    if changed & {"copilot_enabled", "copilot_interval"}:
        set_state(copilot=settings["copilot_enabled"])
        if "copilot_enabled" in changed:
            log_terminal("Copiloto " + (f"activado: miraré tu pantalla cada {settings['copilot_interval']} min."
                                        if settings["copilot_enabled"] else "desactivado."), "COPILOTO")
    if changed & AI_SETTING_KEYS:
        chat_history.clear()
        threading.Thread(target=check_ai, args=(True,), daemon=True).start()
    if "hud_on_top" in changed and hud["window"] is not None:
        hud["window"].on_top = settings["hud_on_top"]
    if "hud_position" in changed:
        hud_reposition()
    if changed:
        log_terminal(f"Ajustes guardados ({len(changed)} cambios).", "SISTEMA")
    return errors


# =============================================================================
# RUTAS Y EVENTOS WEB
# =============================================================================
@app.route("/")
def index():
    return render_template("hud.html", version=VERSION)


@socketio.on("calendar_test")
def handle_calendar_test(data):
    urls = calendario.clean_urls((data or {}).get("calendar_urls") or settings["calendar_urls"])
    if not urls:
        return {"ok": False, "error": "Pega primero el enlace iCal de tu calendario."}
    try:
        evs, errs = calendario.fetch(urls)
    except ImportError:
        return {"ok": False, "error": "Falta un componente para leer calendarios: ejecuta instalar.bat otra vez."}
    nx = calendario.upcoming(limit=1, events=evs)
    hoy = calendario.on_day(datetime.date.today(), evs)
    return {"ok": not errs or bool(evs), "errors": errs, "count": len(evs), "today": len(hoy),
            "next": _event_line(nx[0]) if nx else ""}


@socketio.on("rutinas_get")
def handle_rutinas_get(data=None):
    return {"rutinas": rutinas.routines}


@socketio.on("rutinas_save")
def handle_rutinas_save(data):
    d = data or {}
    try:
        rutinas.upsert(d.get("nombre"), d.get("frases"), d.get("pasos"), d.get("old"))
    except ValueError as e:
        return {"ok": False, "error": str(e), "rutinas": rutinas.routines}
    return {"ok": True, "rutinas": rutinas.routines}


@socketio.on("rutinas_delete")
def handle_rutinas_delete(data):
    rutinas.delete((data or {}).get("nombre", ""))
    return {"ok": True, "rutinas": rutinas.routines}


@socketio.on("rutinas_defaults")
def handle_rutinas_defaults(data=None):
    rutinas.restore_defaults()
    return {"ok": True, "rutinas": rutinas.routines}


@socketio.on("rutinas_run")
def handle_rutinas_run(data):
    r = next((x for x in rutinas.routines if x["nombre"] == (data or {}).get("nombre")), None)
    if not r:
        return {"ok": False, "error": "No encontré esa rutina."}
    run_routine(r)
    return {"ok": True}


@socketio.on("notes_get")
def handle_notes_get(data=None):
    return {"notes": notes_snapshot()}


@socketio.on("notes_add")
def handle_notes_add(data):
    try:
        notas.add((data or {}).get("texto", ""))
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    _notes_changed()
    return {"ok": True, "notes": notes_snapshot()}


@socketio.on("notes_done")
def handle_notes_done(data):
    d = data or {}
    notas.set_done(str(d.get("id")), bool(d.get("done", True)))
    _notes_changed()
    return {"ok": True, "notes": notes_snapshot()}


@socketio.on("notes_delete")
def handle_notes_delete(data):
    notas.delete(str((data or {}).get("id")))
    _notes_changed()
    return {"ok": True, "notes": notes_snapshot()}


@socketio.on("notes_clear_done")
def handle_notes_clear_done(data=None):
    notas.clear_done()
    _notes_changed()
    return {"ok": True, "notes": notes_snapshot()}


@app.route("/aula")
def aula_page():
    return render_template("aula.html", version=VERSION)


def _aula_state():
    return {"ok": True, **aula.snapshot(), "view": aula_ui["view"], "last": aula_ui["last"],
            "docente": settings["aula_docente"], "institucion": settings["aula_institucion"],
            "open_docs": settings["aula_open_docs"], "auto_open": settings["aula_auto_open"],
            "theme": settings["theme"], "busy": material_job["busy"], "mic": state.get("mic"),
            "native": hud.get("aula_win") is not None, "camera_index": settings["camera_index"],
            "review_busy": review_state["busy"]}


def _aula_call(fn, *a, **k):
    try:
        fn(*a, **k)
        return _aula_state()
    except ValueError as e:
        return {"ok": False, "error": str(e), **_aula_state(), "ok": False}


@socketio.on("aula_get")
def handle_aula_get(data=None):
    return _aula_state()


@socketio.on("aula_save_course")
def handle_aula_save_course(data):
    d = data or {}
    return _aula_call(aula.save_course, d.get("name"), d.get("text"), d.get("old"))


@socketio.on("aula_delete_course")
def handle_aula_delete_course(data):
    return _aula_call(aula.delete_course, (data or {}).get("name"))


@socketio.on("aula_set_active")
def handle_aula_set_active(data):
    return _aula_call(aula.set_active, (data or {}).get("name"))


@socketio.on("aula_pick")
def handle_aula_pick(data=None):
    return _aula_call(aula_pick)


@socketio.on("aula_reset_pick")
def handle_aula_reset_pick(data=None):
    return _aula_call(aula.reset_pick)


@socketio.on("aula_groups")
def handle_aula_groups(data):
    d = data or {}
    size, count = aula.to_int(str(d.get("size") or "")), aula.to_int(str(d.get("count") or ""))
    return _aula_call(aula_groups, size=None if count else (size or 4), count=count)


@socketio.on("aula_mark")
def handle_aula_mark(data):
    d = data or {}
    res = _aula_call(aula.mark, d.get("name"), bool(d.get("present")))
    aula_ui["attendance_until"] = time.time() + 3 * 3600
    return res


@socketio.on("aula_export")
def handle_aula_export(data=None):
    return _aula_call(aula_export_attendance)


@socketio.on("aula_material")
def handle_aula_material(data):
    d = data or {}
    kind = d.get("kind") if d.get("kind") in aula.KINDS else "quiz"
    tema = str(d.get("tema") or "").strip()[:200]
    if not tema:
        return {"ok": False, "error": "Escribe el tema."}
    grado = str(d.get("grado") or "").strip()[:40]
    cantidad = aula.to_int(str(d.get("cantidad") or "")) or None
    extra = str(d.get("extra") or "").strip()[:600]
    request_text = f"{aula.KINDS[kind][0]} sobre {tema}" + (f" para grado {grado}" if grado else "") \
        + (f". Indicaciones: {extra}" if extra else "")
    generate_material(request_text, kind, cantidad, grado, tema)
    return {"ok": True}


@socketio.on("review_capture")
def handle_review_capture(data):
    src = (data or {}).get("source")
    try:
        path = capture_camera() if src == "camara" else capture_screen_for_review()
        _set_review_image(path, src)
        return {"ok": True, "preview": _preview_b64(path)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"No pude capturar: {e}"}


@socketio.on("review_upload")
def handle_review_upload(data):
    try:
        path = load_uploaded_image((data or {}).get("data", ""))
        _set_review_image(path, "imagen")
        return {"ok": True, "preview": _preview_b64(path)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"No pude abrir la imagen: {e}"}


@socketio.on("review_run")
def handle_review_run(data):
    d = data or {}
    if not review_state["path"]:
        return {"ok": False, "error": "Primero toma una foto, captura la pantalla o sube una imagen."}
    start_review("actual", estudiante=str(d.get("estudiante") or "")[:80], que=str(d.get("que") or "")[:200],
                 clave=str(d.get("clave") or "")[:3000], grado=str(d.get("grado") or "")[:40])
    return {"ok": True}


@socketio.on("aula_teacher")
def handle_aula_teacher(data):
    d = data or {}
    errs = apply_settings({k: d[k] for k in ("aula_docente", "aula_institucion", "aula_open_docs",
                                             "aula_auto_open", "camera_index") if k in d})
    return {"ok": not errs, "error": "; ".join(errs)}


@socketio.on("aula_open")
def handle_aula_open(data):
    path = str((data or {}).get("path", ""))
    if path in generated_files and os.path.exists(path) and IS_WIN:   # solo lo que generó Jarvis
        os.startfile(path)


@socketio.on("aula_open_folder")
def handle_aula_open_folder(data=None):
    folder = os.path.join(settings["output_dir"], "Material de clase")
    os.makedirs(folder, exist_ok=True)
    if IS_WIN:
        os.startfile(folder)
    else:
        webbrowser.open(f"file://{folder}")


@socketio.on("aula_fullscreen")
def handle_aula_fullscreen(data=None):
    w = hud.get("aula_win")
    if w is not None:
        try:
            w.toggle_fullscreen()
        except Exception:
            pass


@app.route("/ajustes")
def settings_page():
    return render_template("settings.html", version=VERSION, providers=PROVIDERS)


@app.route("/api/ping")
def api_ping():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403)
    return f"jarvis {VERSION}"


@app.route("/api/show")
def api_show():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403)
    hud_show()
    return "ok"


@socketio.on("connect")
def handle_connect():
    emit("bootstrap", {
        "logs": list(log_buffer),
        "chat": list(chat_buffer),
        "state": dict(state),
        "settings": public_settings(),
        "size": hud["size"],
        "native": hud["window"] is not None,
        "dictation": dictation_on.is_set(),
        "timers": _timers_snapshot(),
    })


def _bak_list():
    return {"folder": backup_folder(), "items": respaldo.listing(backup_folder())[:30]}


@socketio.on("backup_list")
def handle_backup_list(data=None):
    return {"ok": True, **_bak_list()}


@socketio.on("backup_create")
def handle_backup_create(data=None):
    try:
        res = make_backup("manual")
        return {"ok": True, "name": res["name"], "summary": _backup_summary(res),
                "with_secrets": res["with_secrets"], **_bak_list()}
    except Exception as e:
        return {"ok": False, "error": f"No se pudo guardar la copia: {e}"}


@socketio.on("backup_import")
def handle_backup_import(data=None):
    """Copia elegida desde otro lugar (USB, correo…): se valida y se guarda en la carpeta de copias."""
    import base64
    data = data or {}
    try:
        raw = base64.b64decode(str(data.get("b64", "")), validate=True)
    except Exception:
        return {"ok": False, "error": "No se pudo leer el archivo."}
    if len(raw) > respaldo.MAX_BYTES:
        return {"ok": False, "error": "Ese archivo es demasiado grande para ser una copia de Jarvis."}
    folder = backup_folder()
    os.makedirs(folder, exist_ok=True)
    name = f"Jarvis respaldo importado {datetime.datetime.now():%Y-%m-%d %H%M%S}.zip"
    path = os.path.join(folder, name)
    with open(path, "wb") as f:
        f.write(raw)
    try:
        info = respaldo.inspect(path)
    except respaldo.BackupError as e:
        os.remove(path)
        return {"ok": False, "error": str(e)}
    return {"ok": True, "info": info, **_bak_list()}


@socketio.on("backup_restore")
def handle_backup_restore(data=None):
    data = data or {}
    try:
        res = restore_backup(data.get("name"), list(data.get("parts") or []))
        return {**res, **_bak_list()}
    except respaldo.BackupError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        log_terminal(f"Restaurar copia: {e}", "ERROR")
        return {"ok": False, "error": f"No se pudo restaurar: {e}"}


@socketio.on("backup_open_folder")
def handle_backup_open_folder(data=None):
    folder = backup_folder()
    os.makedirs(folder, exist_ok=True)
    if IS_WIN:
        os.startfile(folder)
    else:
        webbrowser.open(f"file://{folder}")


@socketio.on("update_check")
def handle_update_check(data=None):
    try:
        info = check_updates()
        return {"ok": True, "info": info, "status": update_status()}
    except actualizar.UpdateError as e:
        return {"ok": False, "error": str(e), "status": update_status()}
    except Exception as e:
        return {"ok": False, "error": f"No pude consultar GitHub: {e}", "status": update_status()}


@socketio.on("update_apply")
def handle_update_apply(data=None):
    if upd["busy"]:
        return {"ok": False, "error": "Ya se está actualizando."}
    threading.Thread(target=install_update, daemon=True).start()
    return {"ok": True}


@socketio.on("update_rollback")
def handle_update_rollback(data=None):
    return rollback_update()


@socketio.on("get_settings")
def handle_get_settings():
    return {
        "settings": public_settings(),
        "voices": SPANISH_VOICES,
        "themes": [(k, v[0]) for k, v in THEMES.items()],
        "positions": list(HUD_POSITIONS.items()),
        "autostart_supported": autostart_supported(),
        "config_path": CONFIG_PATH,
        "log_path": LOG_PATH,
        "portable": PORTABLE,
        "env_path": ENV_PATH if env_overrides else "",
        "alarm_found": resolve_alarm_sound() or "",
        "piper_installed": PiperVoice is not None,
        "piper_found": find_piper_voice() or "",
        "whisper_installed": _whisper_installed(),
        "stt_refine_mode": stt_refine_mode(),
        "whisper_models": WHISPER_SIZES,
        "gemini_tts_voices": GEMINI_TTS_VOICES,
        "gemini_tts_models": GEMINI_TTS_MODELS,
        "gemini_key_set": bool(_gemini_for_stt()),
        "update": update_status(),
        "offline_info": {"offline": net["offline"], "local_model": local_ai_model(refresh=True),
                         "piper": bool(PiperVoice is not None and find_piper_voice())},
        "default_system_prompt": DEFAULT_SYSTEM_PROMPT,
        "providers": {k: {"short": v["short"], "kind": v["kind"], "default_model": v.get("model", "")}
                      for k, v in PROVIDERS.items()},
        "capabilities": CAPABILITIES,
        "app_count": skills.app_count(),
        "apps_ready": skills.apps_ready(),
        "skills": [{"name": s.name, "desc": s.desc, "dangerous": s.dangerous}
                   for s in skills.REGISTRY.values()],
        "version": VERSION,
    }


@socketio.on("save_settings")
def handle_save_settings(data):
    errors = apply_settings(data)
    pub = public_settings()
    socketio.emit("settings_updated", pub)
    return {"ok": not errors, "errors": errors, "settings": pub}


@socketio.on("list_models")
def handle_list_models(data):
    data = dict(data or {})
    test = bool(data.pop("test", False))
    try:
        if test:                                      # botón «Probar»: prueba una respuesta real
            return {"ok": True, **ai_test(data)}
        cfg = _ai_cfg(data)
        models = ai_list_models(cfg)
        return {"ok": True, "models": models,
                "recommended": _recommend_model(cfg["ai_provider"], models) if models else ""}
    except AIError as e:
        return {"ok": False, "error": e.why if e.kind != "bad" else str(e), "models": []}


@socketio.on("open_url")
def handle_open_url(data):
    """Abre en el navegador la página para crear la clave (solo las de los proveedores)."""
    url = str((data or {}).get("url", ""))
    if url in {p.get("key_url") for p in PROVIDERS.values()}:
        webbrowser.open(url)


@socketio.on("list_voices")
def handle_list_voices():
    if edge_tts is None:
        return {"ok": False, "error": "Edge-TTS no está instalado.", "voices": SPANISH_VOICES}
    try:
        return {"ok": True, "voices": list_edge_voices()}
    except Exception as e:
        return {"ok": False, "error": f"Sin conexión con el servicio de voces: {e}", "voices": SPANISH_VOICES}


@socketio.on("preview_voice")
def handle_preview_voice(data):
    data = data or {}
    if not audio_ready:
        return {"ok": False, "error": "El audio de salida no está disponible."}
    backend = data.get("backend") or settings["tts_backend"]
    gem = {}
    if backend == "gemini":
        if not _gemini_for_stt():
            return {"ok": False, "error": "Para la voz de Gemini guarda primero tu clave de Gemini (Ajustes › IA)."}
        _gtts["pause_until"] = 0.0                       # probar = reintentar aunque estuviera en pausa
        for k in ("gemini_tts_voice", "gemini_tts_model", "gemini_tts_style"):
            if data.get(k) is not None:
                try:
                    gem[k] = _validate(k, data[k])       # se prueba con lo elegido, sin guardarlo
                except Exception:
                    return {"ok": False, "error": "Opción de voz de Gemini no válida."}
    if backend == "piper":
        if PiperVoice is None:
            return {"ok": False, "error": "Piper no está instalado (pip install piper-tts)."}
        if not find_piper_voice():
            return {"ok": False, "error": "No hay voz de Piper. Ejecuta descargar_voz.py."}
    try:
        voice = _validate("tts_voice", data.get("voice", settings["tts_voice"]))
        rate, volume, pitch = (_validate(k, data.get(k, settings[k]))
                               for k in ("tts_rate", "tts_volume", "tts_pitch"))
    except Exception as e:
        return {"ok": False, "error": str(e)}
    stop_speech()
    speak("Hola, soy Jarvis. Así sonará mi voz con esta configuración.",
          voice=voice, rate=rate, volume=volume, pitch=pitch, force=True, backend=backend, gemini=gem)
    return {"ok": True}


@socketio.on("list_mics")
def handle_list_mics():
    try:
        return {"ok": True, "devices": list_mics()}
    except Exception as e:
        return {"ok": False, "error": str(e), "devices": []}


@socketio.on("reindex_apps")
def handle_reindex_apps():
    try:
        return {"ok": True, "count": skills.index_apps()}
    except Exception as e:
        return {"ok": False, "error": str(e), "count": skills.app_count()}


@socketio.on("test_alarm")
def handle_test_alarm(data):
    path = resolve_alarm_sound((data or {}).get("path", ""))
    if not path:
        return {"ok": False, "error": "No encontré el sonido. Pon sirena.mp3 en la carpeta «recursos» o indica la ruta."}
    if not audio_ready:
        return {"ok": False, "error": "El audio de salida no está disponible."}
    stop_speech()
    play_sound(path, max_seconds=5)
    return {"ok": True, "path": path}


@socketio.on("toggle_mic")
def handle_toggle_mic():
    toggle_mic()
    return {"mic_enabled": settings["mic_enabled"]}


@socketio.on("open_output")
def handle_open_output():
    path = settings["output_dir"]
    os.makedirs(path, exist_ok=True)
    if hasattr(os, "startfile"):
        os.startfile(path)
        return {"ok": True}
    return {"ok": False, "error": f"Abre manualmente: {path}"}


@socketio.on("clear_history")
def handle_clear_history():
    clear_memory()
    chat_buffer.clear()
    log_terminal("Conversación reiniciada.", "SISTEMA")
    return {"ok": True}


@socketio.on("manual_command")
def handle_manual_command(data):
    cmd = str((data or {}).get("command", "")).strip()[:1000]
    if not cmd:
        return
    log_terminal(cmd, "USUARIO")
    m = re.match(r"^\s*whatsapp\s+(\+\d{8,15})\s+(.+)$", cmd, re.I | re.S)
    if m:
        push_chat("user", cmd, "texto")
        threading.Thread(target=send_whatsapp_message, args=m.groups(), daemon=True).start()
        return
    submit_command(cmd, "texto")


@socketio.on("stop_voice")
def handle_stop_voice():
    stop_speech()


@socketio.on("hud_set_size")
def handle_hud_set_size(data):
    hud_set_size(str((data or {}).get("size", "compacto")))


_drag = {"lock": threading.Lock(), "n": 0}


def _hud_hwnd():
    if not IS_WIN:
        return 0
    import ctypes
    return ctypes.windll.user32.FindWindowW(None, HUD_TITLE)


@socketio.on("hud_drag")
def handle_hud_drag(data):
    """Arrastre del HUD (ver hud.js). En Windows se mueve con SetWindowPos desde este hilo,
    fuera del evento de ratón de WebView2, que es donde Windows rechazaba el movimiento."""
    win = hud["window"]
    if win is None:
        return
    try:
        phase = str(data.get("phase"))
        x, y = float(data.get("x", 0)), float(data.get("y", 0))
        dpr = float(data.get("dpr") or 1) or 1
        n = int(data.get("n", 0))
    except (TypeError, ValueError, AttributeError):
        return
    with _drag["lock"]:
        if phase == "start":
            pos = None
            if IS_WIN:
                import ctypes
                from ctypes import wintypes
                r = wintypes.RECT()
                hwnd = _hud_hwnd()
                if hwnd and ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r)):
                    pos = (r.left, r.top)
                _drag.update(hwnd=hwnd, scale=dpr)       # Windows: píxeles físicos
            if pos is None:
                pos = (hud["x"], hud["y"])
                _drag.update(hwnd=0, scale=1)            # pywebview: píxeles lógicos
            _drag.update(sx=x, sy=y, pos=pos, n=n, active=True)
            hud["ignore_moves_until"] = 0
            return
        if not _drag.get("active") or n <= _drag["n"]:  # mensaje viejo o desordenado
            return
        _drag["n"] = n
        nx = int(_drag["pos"][0] + round((x - _drag["sx"]) * _drag["scale"]))
        ny = int(_drag["pos"][1] + round((y - _drag["sy"]) * _drag["scale"]))
        if phase == "end":
            _drag["active"] = False
    try:
        if _drag.get("hwnd"):
            import ctypes
            # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
            ctypes.windll.user32.SetWindowPos(_drag["hwnd"], 0, nx, ny, 0, 0, 0x0001 | 0x0004 | 0x0010)
        else:
            win.move(nx, ny)
    except Exception as e:
        log_terminal(f"No se pudo mover el HUD: {e}", "AVISO")


@socketio.on("hud_hide")
def handle_hud_hide():
    hud_hide()


@socketio.on("open_settings")
def handle_open_settings():
    open_settings_window()


@socketio.on("close_settings")
def handle_close_settings():
    close_settings_window()


@socketio.on("shutdown")
def handle_shutdown():
    quit_app()


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
    load_settings()
    start_hidden = ("--tray" in sys.argv or "--sigilo" in sys.argv
                    or settings["hud_start_hidden"]) and "--mostrar" not in sys.argv

    if SAME_JARVIS_RUNNING:            # ya hay un Jarvis igual abierto: mostrar su HUD y salir
        _boot("Ya hay un Jarvis abierto: muestro su panel (si estaba oculto, pulsa Ctrl+Alt+J).")
        _http_text(f"{URL}/api/show", timeout=3)
        return

    _fix_autostart_path()
    load_memory()
    skills.configure(output_dir=lambda: settings["output_dir"], hide_hud=_temp_hide,
                     custom=lambda: settings["custom_commands"],
                     talleres_dir=lambda: settings["talleres_dir"],
                     contacts=lambda: settings["contacts"],
                     setting=lambda key: settings.get(key, ""),
                     log=lambda m: log_terminal(m, "PC"))
    skills.start()
    _init_audio()
    if audio_ready:
        threading.Thread(target=_tts_worker, daemon=True).start()
    reschedule()
    set_state(copilot=settings["copilot_enabled"])
    for target in (_command_worker, _voice_worker, schedule_worker, audio_loop, _ai_monitor,
                   hotkey_loop, _timers_worker, _copilot_worker, _notes_worker, _cal_worker,
                   _net_worker, _update_worker, _backup_worker):
        threading.Thread(target=target, daemon=True).start()
    threading.Thread(target=check_ai, args=(True,), daemon=True).start()
    threading.Thread(target=warm_ai, daemon=True).start()

    threading.Thread(target=_run_server, daemon=True, name="servidor").start()
    server_ready = _wait_server()
    log_terminal(f"Jarvis {VERSION} en línea{' · modo USB portable' if PORTABLE else ''}.", "SISTEMA")
    if "onedrive" in APP_DIR.lower():
        log_terminal("Jarvis está dentro de OneDrive: la sincronización lo vuelve lento al instalar "
                     "y al arrancar. Te recomiendo moverlo a C:\\Jarvis (instalar.bat lo hace por ti).",
                     "AVISO")
    if env_overrides:
        log_terminal(f"Valores tomados de .env: {', '.join(sorted(env_overrides))}.", "SISTEMA")

    start_tray()
    announce_startup(start_hidden)      # confirma por voz que el núcleo se cargó
    threading.Timer(4.0, notes_today_summary).start()   # 📌 pendientes de hoy en el HUD
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
