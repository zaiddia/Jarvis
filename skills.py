"""
Habilidades de control del PC para Jarvis (Windows 10/11).

Cada habilidad es una función registrada con @skill. Jarvis las ejecuta de dos formas:
  1. Órdenes directas reconocidas por parse()  -> «abre Spotify», «cierra Chrome»
  2. La IA interpreta una petición libre y elige una habilidad del registro.

Por seguridad ninguna habilidad ejecuta comandos arbitrarios: solo acciones concretas,
y las que pueden hacer perder trabajo (apagar, forzar cierre...) piden confirmación.
"""

import os
import re
import json
import time
import ctypes
import difflib
import inspect
import datetime
import threading
import subprocess
import unicodedata
import webbrowser
import urllib.parse
import urllib.request

IS_WIN = os.name == "nt"
CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0
OWN_PID = os.getpid()

try:
    import psutil
except Exception:
    psutil = None
try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.02
except Exception:
    pyautogui = None
try:
    import pyperclip
except Exception:
    pyperclip = None


# =============================================================================
# REGISTRO
# =============================================================================
class SkillError(Exception):
    """Error con mensaje apto para decírselo al usuario.
    need = nombre del dato que falta: la siguiente frase del usuario se toma como ese dato."""

    def __init__(self, msg, need=None):
        super().__init__(msg)
        self.need = need


class Skill:
    def __init__(self, name, desc, args, fn, dangerous, confirm, windows_only):
        self.name, self.desc, self.args, self.fn = name, desc, args, fn
        self.dangerous, self.confirm, self.windows_only = dangerous, confirm, windows_only

    def describe(self):
        return f"- {self.name}({self.args}): {self.desc}"

    def confirm_text(self, args):
        if callable(self.confirm):
            return self.confirm(args or {})
        return self.confirm or f"¿Confirmas: {self.desc.lower()}?"

    def run(self, args):
        if self.windows_only and not IS_WIN:
            raise SkillError("Esta acción solo está disponible en Windows.")
        params = inspect.signature(self.fn).parameters
        clean = {k: v for k, v in (args or {}).items() if k in params}   # ignora argumentos inventados
        missing = [p.name for p in params.values()
                   if p.default is inspect.Parameter.empty and p.name not in clean]
        if missing:
            raise SkillError(f"Me falta saber: {', '.join(missing)}.", need=missing[0])
        return self.fn(**clean)


REGISTRY = {}


def skill(name, desc, args="", dangerous=False, confirm=None, windows_only=True):
    def deco(fn):
        REGISTRY[name] = Skill(name, desc, args, fn, dangerous, confirm, windows_only)
        return fn
    return deco


def describe_all():
    return "\n".join(s.describe() for s in REGISTRY.values())


_ctx = {
    "output_dir": lambda: os.path.join(os.path.expanduser("~"), "Documents", "Jarvis"),
    "hide_hud": lambda hidden: None,
    "custom": lambda: "",
    "talleres_dir": lambda: "",
    "contacts": lambda: "",
    "setting": lambda key: "",
    "log": print,
}


def configure(**kwargs):
    _ctx.update(kwargs)


def _log(msg):
    try:
        _ctx["log"](msg)
    except Exception:
        pass


# =============================================================================
# TEXTO
# =============================================================================
def normalize(text):
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s/+:.\-]", " ", t)
    return re.sub(r"\s+", " ", t).strip(" .")


def clean_target(text):
    q = normalize(text)
    q = re.sub(r"\b(?:por favor|porfa|porfavor|ahora|ya)\b", "", q).strip()
    prev = None
    while prev != q:
        prev = q
        q = re.sub(r"^(?:el|la|los|las|un|una|mi|mis|al|del|de|a|aplicacion|app|programa)\s+", "", q)
    return q.replace(" punto ", ".").strip()


_UNITS = {"cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
          "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
          "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17,
          "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veinticinco": 25}
_TENS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70,
         "ochenta": 80, "noventa": 90, "cien": 100, "ciento": 100}
NUM_RE = r"(\d{1,3}|(?:" + "|".join(sorted(list(_UNITS) + list(_TENS), key=len, reverse=True)) + r")(?: y \w+)?)"


def to_int(s):
    s = normalize(s)
    if s.isdigit():
        return int(s)
    parts = s.split(" y ")
    total = _TENS.get(parts[0], _UNITS.get(parts[0]))
    if total is None:
        return None
    if len(parts) > 1:
        total += _UNITS.get(parts[1], 0)
    return total


def _best_match(q, names, cutoff=0.78):
    """Coincidencia exacta > empieza por > contiene todas las palabras > parecida."""
    if not q:
        return None
    names = list(names)
    if q in names:
        return q
    if len(q) < 3:
        return None
    starts = [n for n in names if n.startswith(q + " ")]
    if starts:
        return min(starts, key=len)
    words = q.split()
    contains = [n for n in names if all(re.search(rf"(?:^|\s){re.escape(w)}", n) for w in words)]
    if contains:
        return min(contains, key=len)
    close = difflib.get_close_matches(q, names, n=1, cutoff=cutoff)
    return close[0] if close else None


# =============================================================================
# WINDOWS: VENTANAS
# =============================================================================
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                 "Windows.UI.Core.CoreWindow", "NotifyIconOverflowWindow"}
PROTECTED = {"explorer.exe", "csrss.exe", "winlogon.exe", "svchost.exe", "lsass.exe",
             "services.exe", "smss.exe", "wininit.exe", "dwm.exe", "system", "jarvis.exe",
             "msedgewebview2.exe", "searchhost.exe", "startmenuexperiencehost.exe"}
WM_CLOSE = 0x0010

if IS_WIN:
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    try:
        dwmapi = ctypes.windll.dwmapi
    except Exception:
        dwmapi = None
    _EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]


def _pid_of(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _title_of(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _class_of(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


_proc_cache = {}


def _proc_name(pid):
    if pid in _proc_cache:
        return _proc_cache[pid]
    name = ""
    if psutil:
        try:
            name = psutil.Process(pid).name().lower()
        except Exception:
            pass
    if len(_proc_cache) > 500:
        _proc_cache.clear()
    _proc_cache[pid] = name
    return name


def list_windows():
    """Ventanas de aplicación visibles (sin la del propio Jarvis)."""
    if not IS_WIN:
        return []
    out = []

    def cb(hwnd, _):
        try:
            if not user32.IsWindowVisible(hwnd) or user32.GetWindowTextLengthW(hwnd) == 0:
                return True
            if user32.GetWindowLongW(hwnd, -20) & 0x80:          # WS_EX_TOOLWINDOW
                return True
            if dwmapi:
                cloaked = ctypes.c_int(0)
                dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 14, ctypes.byref(cloaked), 4)
                if cloaked.value:
                    return True
            cls = _class_of(hwnd)
            pid = _pid_of(hwnd)
            if cls in SHELL_CLASSES or pid == OWN_PID:
                return True
            out.append({"hwnd": hwnd, "title": _title_of(hwnd), "pid": pid,
                        "cls": cls, "proc": _proc_name(pid)})
        except Exception:
            pass
        return True

    user32.EnumWindows(_EnumProc(cb), 0)
    return out


_last_ext = {"hwnd": None}

# Ventanas que nunca son «la ventana sobre la que actuar»: menús, Alt+Tab, vistas de tareas, miniaturas de la barra y
# las ventanas del propio Jarvis que viven en otros procesos (el reactor del Explorador y su cuadro de órdenes).
# Sin esto, al escribir una orden en el reactor, «cambia de pestaña», «baja» o «escribe…» iban al cuadro del reactor
# y no a tu navegador.
TRANSIENT_CLASSES = {"#32768", "XamlExplorerHostIslandWindow", "TopLevelWindowForOverflowXamlIsland",
                     "MultitaskingViewFrame", "TaskSwitcherWnd", "TaskListThumbnailWnd", "ForegroundStaging",
                     "Windows.UI.Input.InputSite.WindowClass", "tooltips_class32"}
WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80, 0x08000000


def is_action_target(cls, pid, exstyle):
    """¿Es una ventana de aplicación sobre la que el usuario quiere que Jarvis actúe?"""
    if pid == OWN_PID or cls in SHELL_CLASSES or cls in TRANSIENT_CLASSES:
        return False
    if cls.startswith("Jarvis"):                       # el reactor de Windhawk y sus ventanas
        return False
    return not (exstyle & (WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE))


def _foreground_loop():
    """Recuerda la última ventana externa activa, para «cierra esta ventana», «escribe: …»."""
    while True:
        try:
            h = user32.GetForegroundWindow()
            if h and is_action_target(_class_of(h), _pid_of(h), user32.GetWindowLongW(h, -20)):
                _last_ext["hwnd"] = h
        except Exception:
            pass
        time.sleep(0.35)


def target_window():
    h = _last_ext["hwnd"]
    if IS_WIN and h and user32.IsWindow(h) and user32.IsWindowVisible(h):
        return h
    if IS_WIN:                                         # se cerró: la ventana de aplicación que esté más arriba
        for w in list_windows():
            if is_action_target(w["cls"], w["pid"], 0):
                _last_ext["hwnd"] = w["hwnd"]
                return w["hwnd"]
    raise SkillError("No sé sobre qué ventana actuar. Haz clic en ella y repite la orden.")


def focus_window(hwnd):
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)                    # SW_RESTORE
    user32.keybd_event(0x12, 0, 0, 0)                 # truco ALT para permitir el foco
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)


def close_foreground():
    """Cierra la ventana activa con el atajo de teclado Alt+F4 (cierre inmediato
    del sistema operativo). Es el método de «cierra esto»."""
    h = target_window()                               # última ventana externa en primer plano
    title = _title_of(h)
    if pyautogui is not None:
        focus_window(h)                               # asegura que el atajo llegue a ESA ventana
        time.sleep(0.12)
        pyautogui.hotkey("alt", "f4")
    else:                                             # sin pyautogui: cierre ordenado equivalente
        user32.PostMessageW(h, WM_CLOSE, 0, 0)
    return f"Cerrando «{title}»."


# =============================================================================
# ÍNDICE DE APLICACIONES (menú Inicio)
# =============================================================================
_apps = {}
_apps_lock = threading.Lock()
_apps_ready = threading.Event()
JUNK = re.compile(r"\b(?:uninstall\w*|desinstal\w*|readme|leame|help|manual|website|sitio web|"
                  r"documentation|documentacion|release notes|license|licencia|eula)\b")


def index_apps():
    found = {}
    if IS_WIN:
        ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
              "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress")
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                                "Bypass", "-Command", ps], capture_output=True, timeout=45,
                               creationflags=CREATE_NO_WINDOW)
            out = r.stdout.decode("utf-8", "replace").strip().lstrip("\ufeff")
            data = json.loads(out) if out else []
            for d in ([data] if isinstance(data, dict) else data):
                name, appid = (d.get("Name") or "").strip(), d.get("AppID")
                if name and appid:
                    found.setdefault(normalize(name), (name, "appid", appid))
        except Exception as e:
            _log(f"No se pudo leer el menú Inicio con PowerShell: {e}")
        roots = [
            os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        ]
        for root in roots:
            for dirpath, _, files in os.walk(root):
                for f in files:
                    if f.lower().endswith(".lnk"):
                        name = f[:-4]
                        found.setdefault(normalize(name), (name, "path", os.path.join(dirpath, f)))
    found = {k: v for k, v in found.items() if k and not JUNK.search(k)}
    with _apps_lock:
        _apps.clear()
        _apps.update(found)
    _apps_ready.set()
    _log(f"Aplicaciones indexadas: {len(found)}.")
    return len(found)


def app_count():
    return len(_apps)


def apps_ready():
    return _apps_ready.is_set()


def _launch(target):
    target = target.strip().strip('"')
    if re.match(r"^https?://", target, re.I):
        webbrowser.open(target)
    elif not IS_WIN:
        raise SkillError("Abrir programas solo está disponible en Windows.")
    elif target.lower().startswith("shell:"):
        subprocess.Popen(["explorer.exe", target], creationflags=CREATE_NO_WINDOW)
    else:
        os.startfile(target)


def _launch_app(kind, target):
    if kind == "appid":
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{target}"], creationflags=CREATE_NO_WINDOW)
    else:
        _launch(target)


def _custom_commands():
    out = {}
    for line in str(_ctx["custom"]() or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            if normalize(k) and v.strip():
                out[clean_target(k)] = v.strip()
    return out


BUILTIN_APPS = {
    "bloc de notas": ("Bloc de notas", "notepad.exe"), "notepad": ("Bloc de notas", "notepad.exe"),
    "calculadora": ("Calculadora", "calc.exe"),
    "paint": ("Paint", "mspaint.exe"),
    "explorador": ("Explorador de archivos", "explorer.exe"),
    "explorador de archivos": ("Explorador de archivos", "explorer.exe"),
    "simbolo del sistema": ("Símbolo del sistema", "cmd.exe"), "cmd": ("Símbolo del sistema", "cmd.exe"),
    "powershell": ("PowerShell", "powershell.exe"),
    "terminal": ("Terminal", "wt.exe"),
    "administrador de tareas": ("Administrador de tareas", "taskmgr.exe"),
    "panel de control": ("Panel de control", "control.exe"),
    "word": ("Word", "winword.exe"), "excel": ("Excel", "excel.exe"),
    "powerpoint": ("PowerPoint", "powerpnt.exe"), "outlook": ("Outlook", "outlook.exe"),
    "chrome": ("Chrome", "chrome.exe"), "google chrome": ("Chrome", "chrome.exe"),
    "edge": ("Edge", "msedge.exe"), "microsoft edge": ("Edge", "msedge.exe"),
    "firefox": ("Firefox", "firefox.exe"),
    "navegador": ("el navegador", "https://www.google.com"),
    "recortes": ("Recortes", "snippingtool.exe"), "herramienta de recortes": ("Recortes", "snippingtool.exe"),
    "camara": ("Cámara", "microsoft.windows.camera:"),
    "tienda": ("Microsoft Store", "ms-windows-store:"), "microsoft store": ("Microsoft Store", "ms-windows-store:"),
    "reloj": ("Reloj", "ms-clock:"), "alarmas": ("Reloj", "ms-clock:"),
    "configuracion": ("Configuración", "ms-settings:"),
}

SETTINGS_PAGES = {
    "wifi": "ms-settings:network-wifi", "red": "ms-settings:network-status",
    "internet": "ms-settings:network-status", "bluetooth": "ms-settings:bluetooth",
    "pantalla": "ms-settings:display", "sonido": "ms-settings:sound",
    "actualizaciones": "ms-settings:windowsupdate", "windows update": "ms-settings:windowsupdate",
    "aplicaciones": "ms-settings:appsfeatures", "fondo de pantalla": "ms-settings:personalization-background",
    "personalizacion": "ms-settings:personalization", "bateria": "ms-settings:batterysaver",
    "energia": "ms-settings:powersleep", "impresoras": "ms-settings:printers",
    "privacidad": "ms-settings:privacy", "almacenamiento": "ms-settings:storagesense",
    "notificaciones": "ms-settings:notifications", "fecha y hora": "ms-settings:dateandtime",
    "idioma": "ms-settings:regionlanguage", "mouse": "ms-settings:mousetouchpad",
    "raton": "ms-settings:mousetouchpad", "cuentas": "ms-settings:yourinfo",
    "microfono": "ms-settings:privacy-microphone", "camara": "ms-settings:privacy-webcam",
}

FOLDERS = {
    "descargas": "shell:Downloads", "documentos": "shell:Personal", "escritorio": "shell:Desktop",
    "imagenes": "shell:My Pictures", "fotos": "shell:My Pictures", "musica": "shell:My Music",
    "videos": "shell:My Video", "este equipo": "shell:MyComputerFolder", "mi pc": "shell:MyComputerFolder",
    "papelera": "shell:RecycleBinFolder", "papelera de reciclaje": "shell:RecycleBinFolder",
}

SITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com",
    "gmail": "https://mail.google.com", "correo": "https://mail.google.com",
    "whatsapp web": "https://web.whatsapp.com", "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com", "twitter": "https://x.com", "x": "https://x.com",
    "netflix": "https://www.netflix.com", "wikipedia": "https://es.wikipedia.org",
    "google maps": "https://maps.google.com", "mapas": "https://maps.google.com",
    "drive": "https://drive.google.com", "google drive": "https://drive.google.com",
    "classroom": "https://classroom.google.com", "github": "https://github.com",
    "linkedin": "https://www.linkedin.com", "tiktok": "https://www.tiktok.com",
    "amazon": "https://www.amazon.com", "mercado libre": "https://www.mercadolibre.com.co",
    "traductor": "https://translate.google.com", "chatgpt": "https://chatgpt.com",
    "spotify web": "https://open.spotify.com", "outlook web": "https://outlook.live.com",
}


# =============================================================================
# HABILIDADES: APLICACIONES
# =============================================================================
@skill("abrir_app", "Abre una aplicación instalada, una carpeta (descargas, documentos…), "
                    "un apartado de la configuración de Windows o un sitio web, por su nombre",
       "nombre", windows_only=False)
def open_app(nombre):
    q = clean_target(nombre)
    if not q:
        raise SkillError("¿Qué quieres que abra?", need="nombre")

    custom = _custom_commands()
    key = _best_match(q, custom, 0.85)
    if key:
        _launch(custom[key])
        return f"Abriendo {key}."

    m = re.match(r"^(?:la )?(?:configuracion|ajustes)(?: de(?:l)?(?: la| el| los)?)?\s*(.*)$", q)
    sub = m.group(1).strip() if m else (q if q in SETTINGS_PAGES else "")
    if m or sub:
        page_key = _best_match(sub, SETTINGS_PAGES, 0.8) if sub else None
        _launch(SETTINGS_PAGES[page_key] if page_key else "ms-settings:")
        return f"Abriendo la configuración de {page_key}." if page_key else "Abriendo la configuración de Windows."

    fq = re.sub(r"^carpeta(?: de)?\s+", "", q)
    fk = _best_match(fq, FOLDERS, 0.86)
    if fk:
        _launch(FOLDERS[fk])
        return f"Abriendo {fk}."

    if re.fullmatch(r"[a-z0-9\-]+(\.[a-z0-9\-]+)+(/\S*)?", q):
        webbrowser.open("https://" + q)
        return f"Abriendo {q}."

    bk = _best_match(q, BUILTIN_APPS, 0.86)
    if bk and IS_WIN:
        display, target = BUILTIN_APPS[bk]
        try:
            _launch(target)
            return f"Abriendo {display}."
        except OSError:
            q = normalize(display)          # no está en el PATH: buscar en el menú Inicio

    if IS_WIN:
        _apps_ready.wait(timeout=10)
        with _apps_lock:
            ak = _best_match(q, _apps, 0.74)
            hit = _apps.get(ak) if ak else None
        if hit:
            display, kind, target = hit
            _launch_app(kind, target)
            return f"Abriendo {display}."

    sk = _best_match(q, SITES, 0.8)
    if sk:
        webbrowser.open(SITES[sk])
        return f"Abriendo {sk} en el navegador."

    raise SkillError(f"No encontré «{nombre}» entre tus aplicaciones. Prueba con el nombre "
                     "que aparece en el menú Inicio o añádelo como atajo en Ajustes › Control del PC.")


PROC_ALIASES = {
    "navegador": ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe"],
    "chrome": ["chrome.exe"], "google chrome": ["chrome.exe"], "edge": ["msedge.exe"],
    "firefox": ["firefox.exe"], "brave": ["brave.exe"], "opera": ["opera.exe"],
    "word": ["winword.exe"], "excel": ["excel.exe"], "powerpoint": ["powerpnt.exe"],
    "outlook": ["outlook.exe", "olk.exe"], "bloc de notas": ["notepad.exe"], "notepad": ["notepad.exe"],
    "calculadora": ["calculatorapp.exe", "calculator.exe"], "paint": ["mspaint.exe"],
    "spotify": ["spotify.exe"], "whatsapp": ["whatsapp.exe", "whatsapp.root.exe"],
    "discord": ["discord.exe"], "teams": ["ms-teams.exe", "teams.exe"], "zoom": ["zoom.exe"],
    "vlc": ["vlc.exe"], "steam": ["steam.exe"], "obs": ["obs64.exe"], "telegram": ["telegram.exe"],
    "visual studio code": ["code.exe"], "vs code": ["code.exe"], "code": ["code.exe"],
    "administrador de tareas": ["taskmgr.exe"], "cmd": ["cmd.exe"], "simbolo del sistema": ["cmd.exe"],
    "powershell": ["powershell.exe"], "terminal": ["windowsterminal.exe"],
}
EXPLORER_WORDS = {"explorador", "explorador de archivos", "carpetas", "las carpetas", "archivos"}
THIS_WINDOW = {"esta ventana", "la ventana", "ventana", "ventana actual", "esto", "eso", "esta"}


def _find_windows(q, wins):
    pk = _best_match(q, PROC_ALIASES, 0.86)
    if pk:
        procs = PROC_ALIASES[pk]
        return [w for w in wins if w["proc"] in procs], procs, pk
    compact = q.replace(" ", "")
    hits = [w for w in wins if q in normalize(w["title"]) or normalize(w["proc"]).startswith(compact)]
    if not hits:
        stems = {normalize(w["proc"].rsplit(".", 1)[0]): w["proc"] for w in wins if w["proc"]}
        close = difflib.get_close_matches(compact, stems, n=1, cutoff=0.75)
        if close:
            hits = [w for w in wins if w["proc"] == stems[close[0]]]
    procs = sorted({w["proc"] for w in hits if w["proc"]})
    return hits, procs, q


def _close(nombre, force):
    q = clean_target(nombre)
    if not q:
        raise SkillError("¿Qué quieres que cierre?", need="nombre")
    if q in THIS_WINDOW:
        return close_foreground()

    wins = list_windows()
    if q in EXPLORER_WORDS:
        targets = [w for w in wins if w["cls"] == "CabinetWClass"]
        if not targets:
            raise SkillError("No hay ventanas del explorador abiertas.")
        for w in targets:
            user32.PostMessageW(w["hwnd"], WM_CLOSE, 0, 0)
        return f"Cerrando {len(targets)} ventana(s) del explorador."

    targets, procs, label = _find_windows(q, wins)
    procs = [p for p in procs if p not in PROTECTED]

    if force:
        if not psutil:
            raise SkillError("Falta la librería psutil.")
        killed = 0
        for p in psutil.process_iter(["name"]):
            try:
                if p.pid != OWN_PID and (p.info["name"] or "").lower() in procs:
                    p.terminate()
                    killed += 1
            except Exception:
                continue
        if not killed:
            raise SkillError(f"No encontré procesos de «{nombre}».")
        return f"Cerré a la fuerza {label} ({killed} proceso(s))."

    targets = [w for w in targets if w["proc"] not in PROTECTED]
    if not targets:
        if procs and psutil and any((p.info["name"] or "").lower() in procs
                                    for p in psutil.process_iter(["name"])):
            raise SkillError(f"{label.capitalize()} está en segundo plano sin ventana. "
                             f"Di «cierra {label} a la fuerza» si quieres terminarlo.")
        raise SkillError(f"No encontré ninguna ventana abierta de «{nombre}».")
    for w in targets:
        user32.PostMessageW(w["hwnd"], WM_CLOSE, 0, 0)
    n = len(targets)
    return f"Cerrando {label}." if n == 1 else f"Cerrando {n} ventanas de {label}."


@skill("cerrar_app", "Cierra una aplicación o ventana abierta por su nombre, de forma normal "
                     "(permite guardar). Usa nombre='esta ventana' para la ventana activa", "nombre")
def close_app(nombre):
    return _close(nombre, force=False)


@skill("forzar_cierre", "Termina a la fuerza una aplicación que no responde", "nombre", dangerous=True,
       confirm=lambda a: f"¿Cierro a la fuerza {a.get('nombre', 'esa aplicación')}? Se perderá lo que no esté guardado.")
def force_close(nombre):
    return _close(nombre, force=True)


@skill("cerrar_todo", "Cierra todas las ventanas abiertas", dangerous=True,
       confirm="¿Cierro todas las ventanas abiertas? Cada programa te pedirá guardar si hace falta.")
def close_all():
    wins = [w for w in list_windows() if w["proc"] not in PROTECTED or w["cls"] == "CabinetWClass"]
    for w in wins:
        user32.PostMessageW(w["hwnd"], WM_CLOSE, 0, 0)
    return f"Cerrando {len(wins)} ventanas."


@skill("enfocar", "Trae al frente una ventana que ya está abierta (si no lo está, la abre)", "nombre")
def focus_app(nombre):
    q = clean_target(nombre)
    targets, _, label = _find_windows(q, list_windows())
    if not targets:
        return open_app(nombre)
    focus_window(targets[0]["hwnd"])
    return f"Mostrando {label}."


@skill("ventanas_abiertas", "Dice qué ventanas y aplicaciones están abiertas")
def open_windows():
    wins = list_windows()
    if not wins:
        return "No hay ventanas abiertas."
    names = []
    for w in wins:
        t = w["title"] if len(w["title"]) <= 50 else w["title"][:47] + "…"
        if t not in names:
            names.append(t)
    return f"Tienes {len(names)} ventanas abiertas: " + "; ".join(names[:12]) + ("…" if len(names) > 12 else ".")


@skill("ventana", "Controla la ventana activa o el escritorio",
       "accion: minimizar|maximizar|restaurar|cerrar|escritorio|cambiar")
def window_action(accion):
    a = normalize(accion)
    if a in ("escritorio", "mostrar escritorio", "minimizar todo", "minimizar todas"):
        _hotkey("win", "d")
        return "Mostrando el escritorio."
    if a in ("cambiar", "siguiente"):
        _hotkey("alt", "tab")
        return "Cambiando de ventana."
    h = target_window()
    title = _title_of(h)
    if a.startswith("minim"):
        user32.ShowWindow(h, 6)
        return f"Minimizando «{title}»."
    if a.startswith("maxim"):
        user32.ShowWindow(h, 3)
        return f"Maximizando «{title}»."
    if a.startswith("restaur"):
        user32.ShowWindow(h, 9)
        return f"Restaurando «{title}»."
    if a.startswith("cerr"):
        user32.PostMessageW(h, WM_CLOSE, 0, 0)
        return f"Cerrando «{title}»."
    if "pantalla completa" in a or a.startswith("completa"):
        _need_gui()
        focus_window(h)
        time.sleep(0.1)
        pyautogui.press("f11")
        return f"Pantalla completa en «{title}»."
    raise SkillError(f"No conozco la acción de ventana «{accion}».")


# =============================================================================
# HABILIDADES: AUDIO, MULTIMEDIA, PANTALLA
# =============================================================================
def _need_gui():
    if pyautogui is None:
        raise SkillError("Falta la librería pyautogui.")


def _hotkey(*keys):
    _need_gui()
    pyautogui.hotkey(*keys)


@skill("volumen", "Sube, baja, silencia o fija el volumen del sistema",
       "accion: subir|bajar|silenciar|fijar, nivel: 0-100 (solo con fijar)")
def volume(accion="fijar", nivel=None):
    _need_gui()
    a = normalize(accion)
    if a.startswith("sub"):
        pyautogui.press("volumeup", presses=5)
        return "Subiendo volumen."
    if a.startswith("baj"):
        pyautogui.press("volumedown", presses=5)
        return "Bajando volumen."
    if a.startswith(("silen", "mute", "quitar")):
        pyautogui.press("volumemute")
        return "Silencio activado o desactivado."
    n = to_int(str(nivel)) if nivel is not None else None
    if n is None:
        raise SkillError("¿A qué nivel pongo el volumen? Por ejemplo: volumen al 40.", need="nivel")
    n = max(0, min(100, n))
    pyautogui.press("volumedown", presses=50, interval=0.005)    # cada tecla = 2 %
    pyautogui.press("volumeup", presses=round(n / 2), interval=0.005)
    return f"Volumen al {n} %."


@skill("multimedia", "Controla la música o el video que se esté reproduciendo",
       "accion: pausar|siguiente|anterior|detener")
def media(accion):
    _need_gui()
    a = normalize(accion)
    key = ("nexttrack" if a.startswith("sig") else "prevtrack" if a.startswith("ant")
           else "stop" if a.startswith("det") else "playpause")
    pyautogui.press(key)
    return {"nexttrack": "Siguiente.", "prevtrack": "Anterior.", "stop": "Detenido."}.get(key, "Hecho.")


@skill("brillo", "Ajusta el brillo de la pantalla (portátiles)", "nivel: 0-100")
def brightness(nivel):
    n = to_int(str(nivel))
    if n is None:
        raise SkillError("¿A qué nivel pongo el brillo?", need="nivel")
    n = max(5, min(100, n))
    ps = f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{n})"
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, timeout=15, creationflags=CREATE_NO_WINDOW)
    if r.returncode != 0:
        raise SkillError("Esta pantalla no permite cambiar el brillo desde Windows.")
    return f"Brillo al {n} %."


@skill("captura", "Toma una captura de pantalla y la guarda")
def screenshot():
    _need_gui()
    folder = os.path.join(_ctx["output_dir"](), "Capturas")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"captura_{datetime.datetime.now():%Y%m%d_%H%M%S}.png")
    _ctx["hide_hud"](True)
    try:
        time.sleep(0.35)
        pyautogui.screenshot(path)
    finally:
        _ctx["hide_hud"](False)
    return f"Captura guardada en {path}"


@skill("escribir", "Escribe un texto en la ventana activa (como si lo tecleara el usuario)", "texto")
def type_text(texto):
    _need_gui()
    if not texto:
        raise SkillError("¿Qué quieres que escriba?", need="texto")
    h = target_window()
    focus_window(h)
    time.sleep(0.25)
    if pyperclip:
        try:
            old = pyperclip.paste()
        except Exception:
            old = None
        pyperclip.copy(texto)
        pyautogui.hotkey("ctrl", "v")
        if old is not None:
            threading.Timer(0.8, lambda: pyperclip.copy(old)).start()
    else:
        pyautogui.write(texto, interval=0.01)
    return f"Escrito en «{_title_of(h)}»."


def _focus_browser():
    """Pone al frente la última ventana que usabas (tu navegador) antes de mandar teclas."""
    try:
        h = target_window()
        focus_window(h)
        time.sleep(0.25)
        return _title_of(h)
    except SkillError:
        return ""


def _paste_type(texto):
    """Escribe texto de forma fiable (con tildes) pegándolo desde el portapapeles."""
    if pyperclip:
        try:
            old = pyperclip.paste()
        except Exception:
            old = None
        pyperclip.copy(texto)
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        if old is not None:
            threading.Timer(1.0, lambda: pyperclip.copy(old)).start()
    else:
        pyautogui.write(texto, interval=0.01)


@skill("navegador_buscar", "Abre una pestaña nueva del navegador y busca algo", "consulta", windows_only=False)
def browser_search(consulta):
    if not consulta:
        raise SkillError("¿Qué quieres que busque?", need="consulta")
    # Abrir la pestaña con la búsqueda ya hecha es lo más fiable (no depende del foco ni del teclado).
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote_plus(consulta))
    return f"Abrí una pestaña nueva buscando «{consulta}»."


@skill("pestana", "Cambia, abre o cierra pestañas del navegador",
       "accion: siguiente|anterior|cerrar|reabrir|nueva|numero, numero: 1-9")
def tab(accion="siguiente", numero=None):
    _need_gui()
    _focus_browser()
    a = normalize(accion)
    n = to_int(str(numero)) if numero is not None else to_int(a)
    if n and 1 <= n <= 9:
        pyautogui.hotkey("ctrl", str(min(n, 9)))
        return f"Pestaña {n}."
    if a.startswith("sig") or "derecha" in a or "adelante" in a:
        pyautogui.hotkey("ctrl", "tab"); return "Pestaña siguiente."
    if a.startswith("ant") or "izquierda" in a or "atras" in a:
        pyautogui.hotkey("ctrl", "shift", "tab"); return "Pestaña anterior."
    if a.startswith("cerr") or "cierra" in a:
        pyautogui.hotkey("ctrl", "w"); return "Pestaña cerrada."
    if a.startswith("reabr") or "recuper" in a or "vuelve" in a:
        pyautogui.hotkey("ctrl", "shift", "t"); return "Reabrí la última pestaña."
    if a.startswith("nuev") or "abre" in a:
        pyautogui.hotkey("ctrl", "t"); return "Pestaña nueva."
    pyautogui.hotkey("ctrl", "tab"); return "Pestaña siguiente."


@skill("buscar_en_pagina", "Busca una palabra dentro de la página abierta (Ctrl+F)", "texto", windows_only=False)
def find_in_page(texto):
    _need_gui()
    if not texto:
        raise SkillError("¿Qué palabra busco en la página?", need="texto")
    _focus_browser()
    pyautogui.hotkey("ctrl", "f")
    time.sleep(0.3)
    _paste_type(texto)
    time.sleep(0.1)
    pyautogui.press("enter")
    return f"Buscando «{texto}» en la página."


@skill("navegar", "Controla la página: atrás, adelante, recargar, subir, bajar, arriba o al final",
       "accion", windows_only=False)
def navigate(accion="abajo"):
    _need_gui()
    _focus_browser()
    a = normalize(accion)
    if "atras" in a or "anterior" in a or "regresa" in a or "vuelve" in a:
        pyautogui.hotkey("alt", "left"); return "Atrás."
    if "adelante" in a or "siguiente" in a:
        pyautogui.hotkey("alt", "right"); return "Adelante."
    if "recarg" in a or "actualiz" in a or "refresc" in a:
        pyautogui.press("f5"); return "Recargando."
    if "inicio" in a or "arriba del todo" in a or "principio" in a:
        pyautogui.press("home"); return "Al principio."
    if "final" in a or "fondo" in a or "abajo del todo" in a:
        pyautogui.press("end"); return "Al final."
    if "sube" in a or "arriba" in a:
        pyautogui.scroll(600); return "Subiendo."
    pyautogui.scroll(-600); return "Bajando."


# =============================================================================
# HABILIDADES: AULA (presentaciones, proyector, dictado matemático)
# =============================================================================
# Diccionario para dictar ecuaciones por voz: palabra -> símbolo.
MATH_WORDS = {
    "cero": "0", "uno": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5",
    "seis": "6", "siete": "7", "ocho": "8", "nueve": "9", "diez": "10",
    "mas": "+", "menos": "-", "por": "*", "entre": "/", "dividido": "/",
    "igual": "=", "igual a": "=", "mayor que": ">", "menor que": "<",
    "abre parentesis": "(", "cierra parentesis": ")", "abre corchete": "[", "cierra corchete": "]",
    "coma": ",", "punto": ".", "punto y coma": ";",
    "al cuadrado": "^2", "al cubo": "^3", "elevado a": "^", "raiz de": "sqrt(",
    "equis": "x", "ye": "y", "zeta": "z", "pi": "pi", "por ciento": "%",
}
_MATH_ALT = "|".join(sorted(map(re.escape, MATH_WORDS), key=len, reverse=True))
_MATH_RE = re.compile(rf"\b(?:{_MATH_ALT})\b")


def transcribe_math(text):
    """'dos equis mas tres igual siete' -> '2x+3=7'. Une los símbolos sin espacios."""
    out = _MATH_RE.sub(lambda m: f"\0{MATH_WORDS[normalize(m.group(0))]}\0", normalize(text))
    out = re.sub(r"\s*\0\s*", "", out)        # pega los símbolos a lo que tengan al lado
    return out


def dictation_type(text):
    """Escribe en la ventana activa durante el dictado, añadiendo un espacio al final."""
    _need_gui()
    if not text:
        return
    piece = text + " "
    if pyperclip:
        try:
            old = pyperclip.paste()
        except Exception:
            old = None
        pyperclip.copy(piece)
        pyautogui.hotkey("ctrl", "v")
        if old is not None:
            threading.Timer(0.6, lambda: pyperclip.copy(old)).start()
    else:
        pyautogui.write(piece, interval=0.01)


@skill("presentacion", "Controla una presentación de diapositivas (PowerPoint, Google Slides, PDF…)",
       "accion: siguiente|anterior|iniciar|salir|negro")
def presentation(accion):
    _need_gui()
    a = normalize(accion)
    if a.startswith(("sig", "avanz", "pasa")):
        pyautogui.press("right")
        return "Siguiente diapositiva."
    if a.startswith(("ant", "atras", "retroced", "regres")):
        pyautogui.press("left")
        return "Diapositiva anterior."
    if a.startswith(("inici", "empiez", "comienz", "presenta", "proyecta")):
        pyautogui.press("f5")
        return "Iniciando la presentación."
    if a.startswith(("sal", "termin", "deten", "fin")):
        pyautogui.press("esc")
        return "Saliendo de la presentación."
    if a.startswith("negr") or "pantalla en negro" in a:
        pyautogui.press("b")
        return "Pantalla en negro (pulsa de nuevo para volver)."
    raise SkillError(f"No conozco la acción de presentación «{accion}».")


PROJECTOR_MODES = {
    "solo pc": 0, "solo computador": 0, "solo pantalla": 0, "desconectar": 0,
    "duplicar": 1, "clonar": 1, "espejo": 1, "proyectar": 1,
    "extender": 2, "ampliar": 2, "escritorio extendido": 2,
    "solo proyector": 3, "solo videobeam": 3, "solo segunda pantalla": 3,
}


@skill("proyector", "Configura la segunda pantalla o videobeam (duplicar, extender…)",
       "modo: duplicar|extender|solo_proyector|solo_pc")
def projector(modo="duplicar"):
    _need_gui()
    key = _best_match(normalize(modo), PROJECTOR_MODES, 0.8)
    steps = PROJECTOR_MODES.get(key, 1)
    pyautogui.hotkey("win", "p")
    time.sleep(1.0)
    pyautogui.press("home")               # vuelve a la primera opción (Solo PC)
    time.sleep(0.2)
    if steps:
        pyautogui.press("right", presses=steps, interval=0.2)
    time.sleep(0.2)
    pyautogui.press("enter")
    names = {0: "Solo este equipo", 1: "Duplicar en el proyector", 2: "Escritorio extendido", 3: "Solo el proyector"}
    return f"Proyección: {names[steps]}."


@skill("notificaciones", "Silencia o vuelve a activar las notificaciones emergentes de Windows "
                         "(útil al proyectar en clase)", "accion: silenciar|activar")
def notifications(accion="silenciar"):
    """Cambia el mismo ajuste que «Configuración › Sistema › Notificaciones» y avisa a Windows."""
    import winreg
    on = normalize(accion) in ("activar", "activa", "encender", "reactivar", "mostrar")
    key = r"Software\Microsoft\Windows\CurrentVersion\PushNotifications"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
        winreg.SetValueEx(k, "ToastEnabled", 0, winreg.REG_DWORD, 1 if on else 0)
    try:                                  # pide a Windows que relea el ajuste ya mismo
        HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x001A, 0x0002
        res = ctypes.c_ulong()
        user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Notifications",
                                   SMTO_ABORTIFHUNG, 2000, ctypes.byref(res))
    except Exception:
        pass
    return "Notificaciones activadas." if on else "Notificaciones silenciadas: no saldrán avisos encima de tu clase."


def _talleres_dir():
    d = str(_ctx["talleres_dir"]() or "").strip()
    if not d:
        d = os.path.join(_ctx["output_dir"](), "Talleres")
    return d


@skill("abrir_taller", "Abre en el navegador un taller o formulario HTML del profesor "
                       "(busca el archivo en la carpeta de Talleres)", "nombre", windows_only=False)
def open_taller(nombre):
    q = clean_target(nombre)
    folder = _talleres_dir()
    if not os.path.isdir(folder):
        raise SkillError(f"No existe la carpeta de talleres: {folder}. Créala y pon ahí tus archivos HTML, "
                         "o indica la carpeta en Ajustes › Control del PC.")
    htmls = {}
    for root, _, files in os.walk(folder):
        for f in files:
            if f.lower().endswith((".html", ".htm")):
                htmls.setdefault(normalize(os.path.splitext(f)[0]), os.path.join(root, f))
    if not htmls:
        raise SkillError(f"No hay archivos HTML en {folder}.")
    key = _best_match(q, htmls, 0.6) if q else None
    if not key:
        nombres = ", ".join(sorted(htmls)[:8])
        raise SkillError(f"No encontré el taller «{nombre}». Tengo: {nombres}.")
    webbrowser.open("file:///" + htmls[key].replace("\\", "/"))
    return f"Abriendo el taller {key}."


# =============================================================================
# HABILIDADES: WEB
# =============================================================================
@skill("abrir_web", "Abre una dirección web", "url", windows_only=False)
def open_web(url):
    u = url.strip()
    if not re.match(r"^https?://", u):
        u = "https://" + u.replace(" punto ", ".").replace(" ", "")
    webbrowser.open(u)
    return f"Abriendo {u}."


@skill("buscar_web", "Busca algo en Google", "consulta", windows_only=False)
def web_search(consulta):
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote_plus(consulta))
    return f"Buscando «{consulta}» en Google."


@skill("youtube", "Reproduce o busca un video o canción en YouTube", "consulta", windows_only=False)
def youtube(consulta):
    try:                       # abre directamente el primer resultado (sin pywhatkit)
        q = urllib.parse.quote_plus(consulta)
        req = urllib.request.Request("https://www.youtube.com/results?search_query=" + q,
                                     headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "es"})
        html = urllib.request.urlopen(req, timeout=6).read().decode("utf-8", "ignore")
        vid = re.search(r'"videoId":"([\w-]{11})"', html).group(1)
        webbrowser.open(f"https://www.youtube.com/watch?v={vid}")
        return f"Reproduciendo «{consulta}» en YouTube."
    except Exception:
        webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(consulta))
        return f"Buscando «{consulta}» en YouTube."


# =============================================================================
# HABILIDADES: MENSAJERÍA Y MÚSICA
# =============================================================================
def _parse_contacts():
    """Agenda: líneas 'Nombre = +573001112233'."""
    out = {}
    for line in str(_ctx["contacts"]() or "").splitlines():
        if "=" in line:
            name, num = line.split("=", 1)
            num = re.sub(r"[^\d+]", "", num)
            if normalize(name) and num:
                out[normalize(name)] = num
    return out


def resolve_contact(nombre):
    """Devuelve el número de un contacto por nombre, o el propio número si ya lo es."""
    q = normalize(nombre)
    num = re.sub(r"[^\d+]", "", nombre)
    if re.fullmatch(r"\+?\d{8,15}", num):
        return num if num.startswith("+") else "+" + num
    contacts = _parse_contacts()
    key = _best_match(q, contacts, 0.7)
    return contacts.get(key) if key else None


@skill("whatsapp", "Envía un mensaje de WhatsApp a un contacto de la agenda o a un número",
       "contacto, mensaje", windows_only=False)
def whatsapp(contacto, mensaje):
    num = resolve_contact(contacto)
    if not num:
        raise SkillError(f"No tengo a «{contacto}» en la agenda. Añádelo en Ajustes › Integraciones, "
                         "o dime el número con el código de país.")
    if not mensaje.strip():
        raise SkillError("¿Qué mensaje le envío?", need="mensaje")
    try:
        _ctx["log"](f"Enviando WhatsApp a {num}...")
        send_whatsapp(num, mensaje)
        return f"Mensaje de WhatsApp enviado a {contacto}."
    except Exception as e:
        raise SkillError(f"No pude enviar el WhatsApp: {e}. Ten WhatsApp abierto con la sesión iniciada.")


def _whatsapp_desktop_installed():
    if not IS_WIN:
        return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "whatsapp"))
        return True
    except OSError:
        return False


def send_whatsapp(num, mensaje, wait=None):
    """Abre el chat con el texto ya escrito (app de escritorio o WhatsApp Web) y pulsa Enter.
    Sustituye a pywhatkit, que no instala en las versiones nuevas de Python."""
    num = re.sub(r"[^\d]", "", num)              # wa.me exige solo dígitos con código de país
    texto = urllib.parse.quote(mensaje)
    if _whatsapp_desktop_installed():
        os.startfile(f"whatsapp://send?phone={num}&text={texto}")
        time.sleep(wait or 4)
    else:
        webbrowser.open(f"https://web.whatsapp.com/send?phone={num}&text={texto}")
        time.sleep(wait or 15)                   # WhatsApp Web tarda en cargar el chat
    import pyautogui
    pyautogui.press("enter")


@skill("telegram", "Envía un mensaje por Telegram (requiere bot configurado en Ajustes)",
       "mensaje", windows_only=False)
def telegram(mensaje):
    token = _ctx["setting"]("telegram_token").strip()
    chat = _ctx["setting"]("telegram_chat").strip()
    if not (token and chat):
        raise SkillError("Falta configurar Telegram. Pon el token del bot y el chat en Ajustes › Integraciones.")
    if not mensaje.strip():
        raise SkillError("¿Qué mensaje envío por Telegram?", need="mensaje")
    url = (f"https://api.telegram.org/bot{token}/sendMessage?chat_id={urllib.parse.quote(chat)}"
           f"&text={urllib.parse.quote(mensaje)}")
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            ok = json.loads(r.read().decode()).get("ok")
        return "Mensaje de Telegram enviado." if ok else "Telegram rechazó el mensaje; revisa el chat id."
    except Exception as e:
        raise SkillError(f"No pude enviar el Telegram: {e}")


def _spotify_api():
    """Cliente spotipy si está configurado y disponible, o None."""
    cid = _ctx["setting"]("spotify_client_id").strip()
    secret = _ctx["setting"]("spotify_client_secret").strip()
    if not (cid and secret):
        return None
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
        cache = os.path.join(_ctx["output_dir"](), ".spotify_cache")
        auth = SpotifyOAuth(client_id=cid, client_secret=secret,
                            redirect_uri="http://127.0.0.1:8888/callback",
                            scope="user-read-playback-state user-modify-playback-state",
                            cache_path=cache, open_browser=True)
        return spotipy.Spotify(auth_manager=auth)
    except Exception as e:
        _ctx["log"](f"Spotify API no disponible: {e}")
        return None


@skill("spotify", "Reproduce o controla Spotify. Con acción 'reproducir' y una canción, "
                  "la pone por su nombre", "accion: reproducir|pausa|siguiente|anterior, cancion",
       windows_only=False)
def spotify(accion="reproducir", cancion=""):
    a = normalize(accion)
    sp = _spotify_api()
    if a.startswith(("pausa", "para", "deten")):
        if sp:
            try:
                sp.pause_playback(); return "Spotify en pausa."
            except Exception:
                pass
        if pyautogui:
            pyautogui.press("playpause")
        return "Pausado."
    if a.startswith(("sig", "proxim", "salt")):
        if sp:
            try:
                sp.next_track(); return "Siguiente canción."
            except Exception:
                pass
        if pyautogui:
            pyautogui.press("nexttrack")
        return "Siguiente."
    if a.startswith("ant"):
        if sp:
            try:
                sp.previous_track(); return "Canción anterior."
            except Exception:
                pass
        if pyautogui:
            pyautogui.press("prevtrack")
        return "Anterior."
    # reproducir
    if not cancion.strip():
        if pyautogui:
            pyautogui.press("playpause")
        return "Reproduciendo."
    if sp:
        try:
            res = sp.search(q=cancion, type="track", limit=1)
            items = res["tracks"]["items"]
            if items:
                sp.start_playback(uris=[items[0]["uri"]])
                t = items[0]
                return f"Reproduciendo {t['name']} de {t['artists'][0]['name']} en Spotify."
        except Exception as e:
            _ctx["log"](f"Spotify API falló, abro búsqueda: {e}")
    # sin API: abrir la búsqueda en la app/web de Spotify
    q = urllib.parse.quote(cancion)
    try:
        if IS_WIN:
            os.startfile(f"spotify:search:{q}")
        else:
            webbrowser.open(f"https://open.spotify.com/search/{q}")
    except Exception:
        webbrowser.open(f"https://open.spotify.com/search/{q}")
    return f"Abrí la búsqueda de «{cancion}» en Spotify. Para reproducir automáticamente, configura la API en Ajustes."


# =============================================================================
# HABILIDADES: ARCHIVOS
# =============================================================================
SKIP_DIRS = {"appdata", "node_modules", ".git", "__pycache__", "$recycle.bin", ".venv", "venv"}


def _search_files(q, limit=8, budget=5.0):
    home = os.path.expanduser("~")
    roots = [os.path.join(home, d) for d in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos")]
    roots += [os.path.join(home, "OneDrive", d) for d in ("Desktop", "Documents", "Escritorio", "Documentos")]
    words = clean_target(q).split()
    hits, t0 = [], time.time()
    for root in roots:
        if not os.path.isdir(root):
            continue
        base_depth = root.count(os.sep)
        for dirpath, dirnames, files in os.walk(root):
            if time.time() - t0 > budget:
                break
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith(".")
                           and dirpath.count(os.sep) - base_depth < 5]
            for f in files:
                n = normalize(os.path.splitext(f)[0])
                if all(w in n for w in words):
                    p = os.path.join(dirpath, f)
                    try:
                        hits.append((os.path.getmtime(p), p))
                    except OSError:
                        pass
    hits.sort(reverse=True)
    return [p for _, p in hits[:limit]]


@skill("buscar_archivo", "Busca un archivo por su nombre en Escritorio, Documentos, Descargas, etc. "
                         "y opcionalmente lo abre", "nombre, abrir: true|false")
def find_file(nombre, abrir=False):
    hits = _search_files(nombre)
    if not hits:
        raise SkillError(f"No encontré archivos que se llamen «{nombre}».")
    if str(abrir).lower() in ("true", "1", "si", "sí") or abrir is True:
        os.startfile(hits[0])
        return f"Abriendo {os.path.basename(hits[0])}."
    lista = "\n".join(f"• {p}" for p in hits[:5])
    return f"Encontré {len(hits)} archivo(s). Los más recientes:\n{lista}"


# =============================================================================
# HABILIDADES: SISTEMA
# =============================================================================
def _run_quiet(args):
    return subprocess.run(args, capture_output=True, timeout=15, creationflags=CREATE_NO_WINDOW)


@skill("estado_sistema", "Informa del uso de CPU, memoria, disco y batería")
def system_status():
    if not psutil:
        raise SkillError("Falta la librería psutil.")
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory().percent
    drive = os.environ.get("SystemDrive", "C:") + "\\"
    disk = psutil.disk_usage(drive).percent
    msg = f"Procesador al {cpu:.0f} %, memoria al {ram:.0f} %, disco {drive[0]} al {disk:.0f} %."
    bat = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    if bat:
        msg += f" Batería al {bat.percent:.0f} %" + (", cargando." if bat.power_plugged else ".")
    return msg


@skill("bloquear", "Bloquea el equipo (pantalla de inicio de sesión)")
def lock():
    user32.LockWorkStation()
    return "Equipo bloqueado."


def _shutdown_confirm(a):
    c = a.get("cuando") or "en un minuto"
    return f"¿Apago el equipo {c}? Di «cancela el apagado» para detenerlo."


@skill("apagar", "Apaga el equipo (en un minuto, o a la hora / dentro del tiempo que indiques)",
       "segundos, cuando", dangerous=True, confirm=_shutdown_confirm)
def shutdown(segundos=60, cuando=""):
    try:
        segundos = max(0, min(86400, int(segundos)))
    except (TypeError, ValueError):
        segundos = 60
    _run_quiet(["shutdown", "/s", "/t", str(segundos)])
    return f"El equipo se apagará {cuando or 'en un minuto'}."


@skill("reiniciar", "Reinicia el equipo en un minuto", dangerous=True,
       confirm="¿Reinicio el equipo? Se reiniciará en un minuto.")
def restart():
    _run_quiet(["shutdown", "/r", "/t", "60"])
    return "El equipo se reiniciará en un minuto."


@skill("cancelar_apagado", "Cancela un apagado o reinicio programado")
def cancel_shutdown():
    _run_quiet(["shutdown", "/a"])
    return "Apagado cancelado."


@skill("suspender", "Suspende el equipo", dangerous=True, confirm="¿Suspendo el equipo ahora?")
def suspend():
    ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
    return "Suspendiendo."


@skill("cerrar_sesion", "Cierra la sesión de Windows", dangerous=True,
       confirm="¿Cierro la sesión de Windows? Se cerrarán todos los programas.")
def logoff():
    _run_quiet(["shutdown", "/l"])
    return "Cerrando sesión."


@skill("vaciar_papelera", "Vacía la papelera de reciclaje", dangerous=True,
       confirm="¿Vacío la papelera? Los archivos se borrarán definitivamente.")
def empty_bin():
    ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)
    return "Papelera vaciada."


# =============================================================================
# INTÉRPRETE DE ÓRDENES DIRECTAS
# =============================================================================
_OPEN = r"(?:abre|abrir|abreme|abra|inicia|iniciar|ejecuta|ejecutar|lanza|arranca|entra a|entra en)"
_CLOSE = r"(?:cierra|cerrar|cierre|cierrame|termina|finaliza|mata|quita)"
_PC = r"(?:el |la )?(?:equipo|pc|computador|computadora|ordenador|maquina|portatil)"


def _shutdown_delay(t):
    """De «apaga a las 6», «apaga en 30 minutos», «apaga en 2 horas» saca (segundos, texto)."""
    import datetime
    m = re.search(rf"\ben\s+{NUM_RE}\s*(hora|horas|minuto|minutos|min|segundo|segundos)\b", t)
    if m:
        n = to_int(m.group(1)) or 1
        unit = m.group(2)[:3]
        secs = n * (3600 if unit == "hor" else 1 if unit == "seg" else 60)
        nombre = {"hor": "hora", "min": "minuto", "seg": "segundo"}[unit]
        return secs, f"en {n} {nombre}{'s' if n != 1 else ''}"
    m = re.search(r"\ba la[s]?\s+(\d{1,2})(?:[:y ]\s*(\d{2}))?\s*(de la (?:manana|tarde|noche)|a\.?m|p\.?m)?\b", t)
    if m:
        hh = int(m.group(1)); mm = int(m.group(2) or 0)
        suf = (m.group(3) or "").replace(".", "")
        if "tarde" in suf or "noche" in suf or suf == "pm":
            if hh < 12:
                hh += 12
        elif ("manana" in suf or suf == "am") and hh == 12:
            hh = 0
        now = datetime.datetime.now()
        target = now.replace(hour=hh % 24, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        secs = int((target - now).total_seconds())
        return secs, f"a las {target.strftime('%H:%M')}"
    return 60, ""


def parse(text):
    """Devuelve (habilidad, argumentos) para órdenes directas, o None."""
    t = normalize(text)
    t = re.sub(r"\b(?:por favor|porfa|porfavor)\b", "", t).strip(" ,")
    orig = text.strip()

    # Volumen
    m = re.search(rf"\bvolumen (?:al|a|en)\s+{NUM_RE}", t)
    if m:
        return "volumen", {"accion": "fijar", "nivel": m.group(1)}
    if re.search(r"\b(?:sube(?:r|le)?|aumenta(?:r)?) (?:el )?volumen|volumen arriba|mas volumen\b", t):
        return "volumen", {"accion": "subir"}
    if re.search(r"\b(?:baja(?:r|le)?|disminuye|reduce) (?:el )?volumen|volumen abajo|menos volumen\b", t):
        return "volumen", {"accion": "bajar"}
    if re.fullmatch(r"(?:silencio|silencia(?:r)?(?: el (?:audio|sonido|pc|equipo))?|mutea(?:r)?|mute|quita el silencio)", t):
        return "volumen", {"accion": "silenciar"}

    # Multimedia
    if re.fullmatch(r"(?:pausa|pausar|pon pausa|reanuda(?:r)?|continua(?:r)?|play|pausa (?:la musica|el video|la cancion)|"
                    r"reanuda (?:la musica|el video)|reproduce la musica|quita la pausa)", t):
        return "multimedia", {"accion": "pausar"}
    if re.search(r"\b(?:siguiente (?:cancion|pista|tema|video)|salta(?:r)? (?:la |esta )?(?:cancion|pista)|pasa la cancion)\b", t):
        return "multimedia", {"accion": "siguiente"}
    if re.search(r"\b(?:cancion|pista|tema) anterior\b|\banterior (?:cancion|pista)\b", t):
        return "multimedia", {"accion": "anterior"}

    # Brillo
    m = re.search(rf"\bbrillo (?:al|a|en)\s+{NUM_RE}", t)
    if m:
        return "brillo", {"nivel": m.group(1)}
    if re.search(r"\bbrillo (?:al )?maximo\b", t):
        return "brillo", {"nivel": 100}
    if re.search(r"\bbrillo (?:al )?minimo\b", t):
        return "brillo", {"nivel": 10}

    # Sistema y energía
    if re.search(r"\b(?:cancela(?:r)?|deten|anula) (?:el )?(?:apagado|reinicio)\b|\bno (?:apagues|reinicies)\b", t):
        return "cancelar_apagado", {}
    if re.search(rf"\b(?:apaga|apagar|apague|apagate)\b(?:\s+{_PC})?", t) and not re.search(r"\b(?:pantalla|monitor|musica|video|notificacion|alarma|sonido|volumen|luz|linterna)\b", t):
        secs, cuando = _shutdown_delay(t)
        return "apagar", {"segundos": secs, "cuando": cuando}
    if re.search(rf"\b(?:reinicia|reiniciar|reinicie) {_PC}\b", t):
        return "reiniciar", {}
    if re.search(rf"\b(?:suspende|suspender|hiberna|hibernar|pon a dormir) {_PC}\b", t):
        return "suspender", {}
    if re.search(r"\b(?:bloquea|bloquear|bloquee) (?:el |la )?(?:equipo|pc|pantalla|computador|computadora|sesion|ordenador)\b", t):
        return "bloquear", {}
    if re.search(rf"^{_CLOSE} (?:la )?sesion\b", t):
        return "cerrar_sesion", {}
    if re.search(r"\bvacia(?:r)? (?:la )?papelera\b", t):
        return "vaciar_papelera", {}
    if re.search(r"\b(?:captura de pantalla|toma una captura|haz una captura|saca una captura|pantallazo|screenshot)\b", t):
        return "captura", {}
    if re.search(r"\b(?:estado del (?:sistema|equipo|pc)|uso de (?:cpu|memoria|ram|disco|procesador)|"
                 r"como esta (?:el )?(?:pc|equipo|sistema)|nivel de bateria|cuanta bateria)\b", t):
        return "estado_sistema", {}
    if re.search(r"\bque (?:ventanas|aplicaciones|programas|apps) (?:tengo |hay |estan )?abiert[oa]s\b", t):
        return "ventanas_abiertas", {}

    # Aula: presentaciones y proyector
    if re.search(r"\b(?:siguiente|próxima|proxima|avanza(?:r)?(?: a la)?|pasa(?: a la)?) diapositiva\b|\bavanza la presentacion\b", t):
        return "presentacion", {"accion": "siguiente"}
    if re.search(r"\b(?:anterior|previa) diapositiva\b|\bdiapositiva anterior\b|\bretrocede (?:la )?diapositiva\b|\bregresa la diapositiva\b", t):
        return "presentacion", {"accion": "anterior"}
    if re.search(r"\b(?:inicia(?:r)?|empieza|comienza|proyecta) (?:la )?presentacion\b|\bmodo presentacion\b|\bpresentar diapositivas\b", t):
        return "presentacion", {"accion": "iniciar"}
    if re.search(r"\b(?:sal(?:ir)?|termina(?:r)?|cierra) (?:de )?(?:la )?presentacion\b", t):
        return "presentacion", {"accion": "salir"}
    if re.search(r"\bpantalla en negro\b", t):
        return "presentacion", {"accion": "negro"}
    m = re.search(r"\b(?:activa(?:r)?|configura(?:r)?|pon(?:er)?|usa(?:r)?)?\s*(?:el )?(?:videobeam|proyector|segunda pantalla)"
                  r"(?:\s+(?:en|modo|para)?\s*(duplicar|clonar|espejo|extender|ampliar|solo \w+( \w+)?))?\b", t)
    if m:
        return "proyector", {"modo": (m.group(1) or "duplicar").strip()}

    # Notificaciones de Windows
    if re.search(r"\b(?:silencia|desactiva|apaga|quita|bloquea|oculta)(?:r)? (?:las |los )?(?:notificaciones|avisos)\b"
                 r"|\b(?:activa|pon)(?:r)? (?:el )?(?:modo )?no molestar\b", t):
        return "notificaciones", {"accion": "silenciar"}
    if re.search(r"\b(?:activa|enciende|reactiva|muestra|devuelve)(?:r)? (?:las |los )?(?:notificaciones|avisos)\b"
                 r"|\b(?:quita|desactiva)(?:r)? (?:el )?(?:modo )?no molestar\b", t):
        return "notificaciones", {"accion": "activar"}

    # Ventanas
    if re.search(r"\b(?:minimiza(?:r)? (?:todo|todas(?: las ventanas)?)|muestra(?:me)? el escritorio|ve al escritorio|ir al escritorio)\b", t):
        return "ventana", {"accion": "escritorio"}
    m = re.fullmatch(r"(minimiza|maximiza|restaura)(?:r)?(?: (?:esta|la) ventana| la| esta)?", t)
    if m:
        return "ventana", {"accion": m.group(1)}
    if re.fullmatch(r"cambia(?:r)? de ventana|siguiente ventana", t):
        return "ventana", {"accion": "cambiar"}
    if re.search(r"\bpantalla completa\b|\bpon(?:la)? en completa\b|\bmodo pantalla completa\b", t):
        return "ventana", {"accion": "pantalla completa"}

    # Escribir texto literal («escribe: hola», «teclea hola»)
    m = re.match(r"^\s*(?:escribe|escribir|dicta)(?: el texto| esto| lo siguiente)?\s*[:,]\s*(.+)$", orig, re.I | re.S) \
        or re.match(r"^\s*(?:teclea|tipea)\s+(.+)$", orig, re.I | re.S)
    if m:
        return "escribir", {"texto": m.group(1).strip()}

    # Talleres / formularios HTML del profesor
    m = re.match(rf"^{_OPEN} (?:el |un |mi )?(?:taller|formulario|actividad|ejercicio|guia)\s+(?:de\s+|sobre\s+)?(.+)$", t)
    if m:
        return "abrir_taller", {"nombre": m.group(1)}

    # Archivos
    m = re.match(r"^(?:busca|buscar|encuentra|localiza)(?: el| un| mi| los| mis)? archivos?\s+(?:llamados?\s+|de\s+)?(.+)$", t)
    if m:
        return "buscar_archivo", {"nombre": m.group(1), "abrir": False}
    m = re.match(rf"^{_OPEN} (?:el |mi )?archivo\s+(?:llamado\s+)?(.+)$", t)
    if m:
        return "buscar_archivo", {"nombre": m.group(1), "abrir": True}

    _ENVIAR = r"(?:m[aá]nda(?:le)?|env[ií]a(?:le)?|envia(?:le)?|escr[ií]bele?)"
    # WhatsApp por voz: «manda un whatsapp a Juan que llego tarde»
    # (acepta cómo lo transcribe a veces el reconocimiento: whatsap, wasap, guasap, «unwhatsapp»...)
    _WA = r"(?:whats?\s?app?|wh?ats?app?|wh?asap+|guas?ap+|guasa)"
    m = re.match(rf"^\s*{_ENVIAR}\s+(?:un\s*|una\s+)?(?:mensaje\s+)?(?:de\s+|por\s+)?{_WA}\s+a\s+"
                 r"(.+?)\s+(?:que|diciendo|dile que|:)\s+(.+)$", orig, re.I)
    if m:
        return "whatsapp", {"contacto": m.group(1).strip(), "mensaje": m.group(2).strip()}
    # Sin mensaje: «manda un whatsapp a Andrea» -> Jarvis pregunta qué mensaje enviar
    m = re.match(rf"^\s*{_ENVIAR}\s+(?:un\s*|una\s+)?(?:mensaje\s+)?(?:de\s+|por\s+)?{_WA}\s+a\s+"
                 r"([\w\s+]+?)[\s.,!?]*$", orig, re.I)
    if m:
        return "whatsapp", {"contacto": m.group(1).strip(), "mensaje": ""}

    # Telegram por voz
    m = re.match(rf"^\s*{_ENVIAR}\s+(?:un |una )?"
                 r"(?:mensaje )?(?:de |por )?telegram\s+(?:que|diciendo|:)?\s*(.+)$", orig, re.I)
    if m:
        return "telegram", {"mensaje": m.group(1).strip()}

    # Spotify
    if re.search(r"\bspotify\b", t):
        if re.search(r"\b(?:pausa|para|deten)\b", t):
            return "spotify", {"accion": "pausa"}
        if re.search(r"\b(?:siguiente|proxima|salta|pasa)\b", t):
            return "spotify", {"accion": "siguiente"}
        if re.search(r"\banterior\b", t):
            return "spotify", {"accion": "anterior"}
        m = re.match(r"^\s*(?:pon|ponme|reproduce|reproducir|busca|pon la cancion)\s+(.+?)\s+en\s+spotify\s*$", orig, re.I) \
            or re.match(r"^\s*(?:pon|reproduce)\s+(?:en\s+)?spotify\s+(.+)$", orig, re.I)
        if m:
            return "spotify", {"accion": "reproducir", "cancion": m.group(1).strip()}
        return "spotify", {"accion": "reproducir", "cancion": ""}

    # Navegador: pestañas, buscar dentro de la página, moverse (control por teclado)
    m = re.match(r"^\s*(?:busca|buscame|abre|pon)\s+(.+?)\s+en\s+(?:una\s+|otra\s+|la\s+)?(?:pesta[nñ]a(?:\s+nueva)?|nueva\s+pesta[nñ]a)\s*$", orig, re.I)
    if m:
        return "navegador_buscar", {"consulta": m.group(1).strip()}
    m = re.match(r"^\s*(?:busca|buscame|encuentra|resalta)\s+(?:la\s+palabra\s+|el\s+texto\s+)?(.+?)\s+en\s+(?:esta\s+|la\s+)?p[aá]gina\s*$", orig, re.I)
    if m:
        return "buscar_en_pagina", {"texto": m.group(1).strip()}
    if re.search(r"\b(?:cierra|cerrar)\s+(?:la\s+|esta\s+)?pesta[nñ]a\b", t):
        return "pestana", {"accion": "cerrar"}
    if re.search(r"\b(?:reabre|recupera|vuelve a abrir)\b.*\bpesta[nñ]a\b", t):
        return "pestana", {"accion": "reabrir"}
    m = re.search(r"\b(?:pesta[nñ]a|ve(?:te)? a la pesta[nñ]a|abre la pesta[nñ]a)\s+(?:numero\s+)?(\d|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve)\b", t)
    if m:
        return "pestana", {"accion": "numero", "numero": m.group(1)}
    if re.search(r"\bcambia de pesta[nñ]a\b|\b(?:siguiente|otra)\s+pesta[nñ]a\b|\bpesta[nñ]a\s+siguiente\b|\bpasa (?:de|a la siguiente) pesta[nñ]a\b", t):
        return "pestana", {"accion": "siguiente"}
    if re.search(r"\bpesta[nñ]a\s+anterior\b|\banterior pesta[nñ]a\b|\bpesta[nñ]a de la izquierda\b", t):
        return "pestana", {"accion": "anterior"}
    if re.search(r"\b(?:abre|abreme)\s+(?:una\s+)?pesta[nñ]a(?:\s+(?:nueva|en blanco))?\b", t):
        return "pestana", {"accion": "nueva"}
    if re.search(r"\b(?:recarga|refresca|actualiza)\s+(?:la\s+|esta\s+)?(?:p[aá]gina|pesta[nñ]a|web|sitio)\b", t):
        return "navegar", {"accion": "recargar"}
    if re.search(r"\b(?:ve|regresa|vuelve|vete)\s+(?:a la\s+|la\s+)?(?:p[aá]gina\s+)?atras\b|\bp[aá]gina anterior\b|\batras en (?:el navegador|la p[aá]gina|internet)\b", t):
        return "navegar", {"accion": "atras"}
    if re.search(r"\b(?:ve|pasa|avanza)\s+adelante\b|\bp[aá]gina siguiente\b.*navegador|\badelante en (?:el navegador|la p[aá]gina)\b", t):
        return "navegar", {"accion": "adelante"}
    if re.search(r"\b(?:baja|desplaza(?:te)?)\b.*\b(?:la\s+)?(?:p[aá]gina|pantalla)\b", t):
        return "navegar", {"accion": "abajo"}
    if re.search(r"\bsube\b.*\b(?:la\s+)?(?:p[aá]gina|pantalla)\b", t):
        return "navegar", {"accion": "arriba"}
    if re.search(r"\b(?:ve|baja)\s+(?:al|hasta el)\s+(?:final|fondo)\s+de la p[aá]gina\b", t):
        return "navegar", {"accion": "final"}
    if re.search(r"\b(?:ve|sube)\s+(?:al|hasta el)\s+(?:principio|inicio)\s+de la p[aá]gina\b", t):
        return "navegar", {"accion": "inicio"}

    # YouTube y búsquedas web (con el texto original para conservar tildes)
    m = re.match(r"^\s*(?:pon|ponme|reproduce|reproducir|busca|buscar)\s+(.+?)\s+en\s+youtube\s*$", orig, re.I)
    if m:
        return "youtube", {"consulta": m.group(1)}
    m = re.match(r"^\s*(?:reproduce|reproducir|ponme)\s+(.+)$", orig, re.I)
    if m:
        return "youtube", {"consulta": m.group(1)}
    m = re.match(r"^\s*(?:busca|buscar|googlea|investiga)(?:\s+en\s+(?:google|internet|la web))?\s+(.+?)"
                 r"(?:\s+en\s+(?:google|internet|la web))?\s*$", orig, re.I)
    if m:
        return "buscar_web", {"consulta": m.group(1)}

    # Cerrar
    if re.fullmatch(rf"{_CLOSE} (?:todo|todas las ventanas|todos los programas)", t):
        return "cerrar_todo", {}
    m = re.match(rf"^{_CLOSE}\s+(.+?)(\s+(?:a la fuerza|forzad[oa]|de golpe))?$", t)
    if m:
        return ("forzar_cierre" if m.group(2) else "cerrar_app"), {"nombre": m.group(1)}

    # Traer al frente
    m = re.match(r"^(?:cambia a|cambiate a|ve a|pasa a|enfoca|trae(?:me)?|muestra(?:me)?)\s+(?:la ventana de\s+)?(.+)$", t)
    if m and not re.search(r"\b(?:pagina|sitio|web)\b", m.group(1)):
        return "enfocar", {"nombre": m.group(1)}

    # Abrir
    m = re.match(rf"^{_OPEN}\s+(.+)$", t)
    if m:
        return "abrir_app", {"nombre": m.group(1)}
    if t and clean_target(t) in _custom_commands():
        return "abrir_app", {"nombre": t}
    return None


# =============================================================================
# ARRANQUE
# =============================================================================
def start():
    threading.Thread(target=index_apps, daemon=True).start()
    if IS_WIN:
        threading.Thread(target=_foreground_loop, daemon=True).start()
