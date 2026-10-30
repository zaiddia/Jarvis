"""Ventana HUD, ajustes, bienvenida, bandeja y atajos de teclado.

Parte de Jarvis (antes dentro de jarvis.py). Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import os
import re
import subprocess
import threading
import time
import webbrowser

from nucleo import J


# =============================================================================
# VENTANA HUD (pywebview), VENTANA DE AJUSTES, BANDEJA Y ATAJOS
# =============================================================================
hud = {"window": None, "size": J.settings["hud_start_size"], "visible": False,
       "x": 0, "y": 0, "w": 0, "h": 0, "ignore_moves_until": 0.0,
       "settings_win": None, "quitting": False, "tray": None, "temp_hidden": False}
_save_pos_timer = None


def _work_area():
    """Área útil de la pantalla principal (sin la barra de tareas), en píxeles lógicos."""
    if J.IS_WIN:
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
        s = J.webview.screens[0]
        return s.x, s.y, s.width, s.height - 48
    except Exception:
        return 0, 0, 1366, 720


def _corner_xy(size, corner):
    w, h = J.HUD_SIZES[size]
    ax, ay, aw, ah = J._work_area()
    m = 14
    x = ax + aw - w - m if corner.endswith("der") else ax + m
    y = ay + ah - h - m if corner.startswith("inf") else ay + m
    return int(x), int(y)


def _initial_xy(size):
    if J.settings["hud_position"] == "libre" and J.settings["hud_x"] >= 0 and J.settings["hud_y"] >= 0:
        return J.settings["hud_x"], J.settings["hud_y"]
    return J._corner_xy(size, J.settings["hud_position"] if J.settings["hud_position"] != "libre" else "inf-der")


def _clamp(x, y, w, h):
    ax, ay, aw, ah = J._work_area()
    x = max(ax, min(x, ax + aw - w))
    y = max(ay, min(y, ay + ah - h))
    return int(x), int(y)


def _on_hud_moved(x, y):
    J.hud["x"], J.hud["y"] = x, y
    if time.time() < J.hud["ignore_moves_until"]:
        return
    if J._save_pos_timer:
        J._save_pos_timer.cancel()

    def _save():
        with J.settings_lock:
            J.settings.update(hud_position="libre", hud_x=max(0, int(x)), hud_y=max(0, int(y)))
            try:
                J.save_settings_file()
            except Exception:
                pass
    J._save_pos_timer = threading.Timer(0.8, _save)
    J._save_pos_timer.start()


def _apply_tool_window():
    """Quita el HUD de la barra de tareas y de Alt+Tab (sigue en la bandeja)."""
    if not (J.IS_WIN and J.settings["hud_hide_taskbar"]):
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, J.HUD_TITLE)
        if not hwnd:
            return
        ex = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, (ex | 0x80) & ~0x40000)     # TOOLWINDOW, sin APPWINDOW
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
    except Exception as e:
        J.log_terminal(f"No se pudo ocultar de la barra de tareas: {e}", "AVISO")


HUD_SOLID_BG = "#04090f"


def hud_transparency_supported():
    """¿Puede el HUD tener fondo transparente y seguir respondiendo al ratón?
    En Windows, pywebview 6 ya no hace transparente la ventana (sale un rectángulo negro o
    blanco), y forzarla con trucos de Windows deja pasar los clics a través del HUD. Así que
    con pywebview 6 en Windows se usa el fondo sólido, que funciona siempre."""
    if not J.IS_WIN:
        return True
    try:
        from importlib.metadata import version
        return int(version("pywebview").split(".")[0]) < 6
    except Exception:
        return False


def _on_hud_shown():
    J.hud["visible"] = True
    J._apply_tool_window()


def _on_hud_closing():
    if J.hud["quitting"]:
        return True
    J.hud_hide()
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
    size = J.settings["hud_start_size"]
    w, h = J.HUD_SIZES[size]
    x, y = J._clamp(*J._initial_xy(size), w, h)
    J.hud.update(size=size, x=x, y=y, w=w, h=h, ignore_moves_until=time.time() + 2)
    solid = not (J.settings["hud_transparent"] and J.hud_transparency_supported())
    target = f"{J.URL}/?size={size}{'&solid=1' if solid else ''}"
    page = dict(url=target)
    if loader:
        page = dict(html=J.HUD_LOADER.replace("__TARGET__", target).replace("__PING__", f"{J.URL}/api/ping")
                    .replace("__BG__", J.HUD_SOLID_BG if solid else "transparent"))
    win = J.webview.create_window(
        J.HUD_TITLE, width=w, height=h, x=x, y=y, **page,
        frameless=True, easy_drag=False, transparent=not solid, resizable=False,
        on_top=J.settings["hud_on_top"], hidden=start_hidden, shadow=False,
        background_color=J.HUD_SOLID_BG if solid else "#000000", min_size=(80, 80))
    win.events.moved += J._on_hud_moved
    win.events.shown += J._on_hud_shown
    win.events.closing += J._on_hud_closing
    J.hud["window"] = win
    J.hud["visible"] = not start_hidden
    return win


def _open_browser_hud():
    """Sin pywebview: abre el HUD como ventana de aplicación de Edge (sin barra de direcciones)."""
    w, h = J.HUD_SIZES["expandido"]
    if J.IS_WIN:
        try:
            subprocess.Popen(f'start "" msedge --app={J.URL}/?size=expandido --window-size={w},{h}',
                             shell=True, creationflags=J.CREATE_NO_WINDOW)
            return
        except Exception:
            pass
    webbrowser.open(f"{J.URL}/?size=expandido")


def hud_show():
    win = J.hud["window"]
    if win is None:
        if not J.hud.get("browser_opened"):
            J.hud["browser_opened"] = True
            J._open_browser_hud()
        return
    win.show()
    J.hud["visible"] = True
    J.socketio.emit("hud_visible", {"visible": True})


def hud_hide():
    win = J.hud["window"]
    if win is not None:
        win.hide()
        J.hud["visible"] = False


def hud_toggle():
    if J.hud["window"] is None or not J.hud["visible"]:
        J.hud_show()
    else:
        J.hud_hide()


def _temp_hide(hidden):
    """Para las capturas de pantalla: esconde el HUD un momento."""
    if hidden:
        J.hud["temp_hidden"] = J.hud["visible"]
        if J.hud["temp_hidden"]:
            J.hud_hide()
    elif J.hud["temp_hidden"]:
        J.hud["temp_hidden"] = False
        J.hud_show()


def hud_set_size(size):
    if size not in J.HUD_SIZES:
        return
    win = J.hud["window"]
    J.hud["size"] = size
    J.socketio.emit("hud_size", {"size": size})
    if win is None:
        return
    nw, nh = J.HUD_SIZES[size]
    ax, ay, aw, ah = J._work_area()
    x, y, w, h = J.hud["x"], J.hud["y"], J.hud["w"] or nw, J.hud["h"] or nh
    # Crece hacia el centro de la pantalla: si está a la derecha, crece hacia la izquierda, etc.
    nx = x + w - nw if x + w / 2 > ax + aw / 2 else x
    ny = y + h - nh if y + h / 2 > ay + ah / 2 else y
    nx, ny = J._clamp(nx, ny, nw, nh)
    J.hud.update(x=nx, y=ny, w=nw, h=nh, ignore_moves_until=time.time() + 1.0)
    win.resize(nw, nh)
    win.move(nx, ny)


def hud_reposition():
    win = J.hud["window"]
    if win is None or J.settings["hud_position"] == "libre":
        return
    w, h = J.HUD_SIZES[J.hud["size"]]
    x, y = J._corner_xy(J.hud["size"], J.settings["hud_position"])
    J.hud.update(x=x, y=y, w=w, h=h, ignore_moves_until=time.time() + 1.0)
    win.move(x, y)


def open_settings_window():
    if J.webview is None or J.hud["window"] is None:
        webbrowser.open(f"{J.URL}/ajustes")
        return
    sw = J.hud["settings_win"]
    if sw is not None:
        try:
            sw.show()
            sw.restore()
            return
        except Exception:
            J.hud["settings_win"] = None
    sw = J.webview.create_window("Ajustes · Jarvis", f"{J.URL}/ajustes", width=640, height=760,
                               min_size=(420, 520), background_color="#03060c")

    def _closed():
        J.hud["settings_win"] = None
    sw.events.closed += _closed
    J.hud["settings_win"] = sw


def open_welcome_window():
    """La bienvenida (7.1): cinco pasos para dejar a Jarvis listo la primera vez."""
    if J.webview is None or J.hud["window"] is None:
        webbrowser.open(f"{J.URL}/bienvenida")
        return
    w = J.hud.get("welcome_win")
    if w is not None:
        try:
            w.show()
            w.restore()
            return
        except Exception:
            J.hud["welcome_win"] = None
    w = J.webview.create_window("Bienvenida · Jarvis", f"{J.URL}/bienvenida", width=720, height=640,
                              min_size=(460, 520), background_color="#03060c")

    def _closed():
        J.hud["welcome_win"] = None
    w.events.closed += _closed
    J.hud["welcome_win"] = w


def close_welcome_window():
    w = J.hud.get("welcome_win")
    J.hud["welcome_win"] = None
    if w is not None:
        try:
            w.destroy()
        except Exception:
            pass


WELCOME_TRY = ["¿qué hora es?", "pon un temporizador de 1 minuto", "sube el volumen", "¿qué tengo pendiente?",
               "recuérdame en 5 minutos tomar agua", "¿cuánto es 15 por 8?", "qué puedes hacer"]


def welcome_status():
    """Todo lo que la bienvenida necesita mostrar, en una sola llamada."""
    ai_ok = J.state.get("ai") == "ok"
    try:
        mics = J.list_mics()
    except Exception:
        mics = []
    return {"name": J.settings["address_name"], "theme": J.settings["theme"],
            "themes": [(k, v[0]) for k, v in J.THEMES.items()],
            "mic": J.state.get("mic", "off"), "mics": mics, "mic_device": J.settings["mic_device"],
            "wake": J.get_wake_words()[:1] or ["jarvis"],
            "voices": J.SPANISH_VOICES, "voice": J.settings["tts_voice"], "audio": bool(J.audio_ready),
            "tts_backend": J.settings["tts_backend"], "piper": bool(J.PIPER_INSTALLED and J.find_piper_voice()),
            "ai": J.state.get("ai", "unknown"), "ai_label": J.state.get("ai_label", ""), "ai_ok": ai_ok,
            "ai_provider": J.settings["ai_provider"],
            "local_model": J.local_ai_model(), "providers": {
                k: {"label": v["label"], "short": v["short"], "key_url": v.get("key_url", ""),
                    "key_hint": v.get("key_hint", ""), "note": v.get("note", ""),
                    "key_set": bool(str(J.settings.get(f"{k}_api_key", "")).strip())}
                for k, v in J.PROVIDERS.items() if not v.get("custom")},
            "try": J.WELCOME_TRY, "done": J.settings["onboarding_done"], "version": J.VERSION}


@J.socketio.on("welcome_status")
def handle_welcome_status():
    return J.welcome_status()


@J.socketio.on("open_welcome")
def handle_open_welcome():
    J.open_welcome_window()


@J.socketio.on("welcome_done")
def handle_welcome_done(data=None):
    J.apply_settings({"onboarding_done": True})
    name = J.settings["address_name"]
    J.speak(f"Todo listo{', ' + name if name else ''}. Cuando me necesites, di «{J.get_wake_words()[0] if J.get_wake_words() else 'Jarvis'}».",
          force=True)
    if not (data or {}).get("keep"):
        threading.Timer(0.8, J.close_welcome_window).start()
    return {"ok": True}


def welcome_at_start():
    """La primera vez que se abre Jarvis, la bienvenida aparece sola."""
    if not J.settings["onboarding_done"]:
        J.open_welcome_window()


def welcome_voice(text, t):
    if re.search(r"\b(?:bienvenida|primeros pasos|tutorial|ensename a usarte|como te uso|como se usa jarvis|"
                 r"configuracion inicial|asistente de inicio)\b", t) and not re.search(r"\b(?:dale la|da la|di la)\b", t):
        J.open_welcome_window()
        J.reply("Te abro la bienvenida: en cinco pasos me dejas a tu gusto.", "SISTEMA")
        return True
    return False


def close_settings_window():
    sw = J.hud["settings_win"]
    if sw is not None:
        try:
            sw.destroy()
        except Exception:
            pass
        J.hud["settings_win"] = None


def quit_app():
    J.hud["quitting"] = True
    J.log_terminal("Apagando Jarvis...", "SISTEMA")
    try:
        if J.hud["tray"]:
            J.hud["tray"].stop()
    except Exception:
        pass
    threading.Timer(0.4, lambda: os._exit(0)).start()


def toggle_mic():
    J.apply_settings({"mic_enabled": not J.settings["mic_enabled"]})
    J.socketio.emit("settings_updated", J.public_settings())


def _tray_icon_path():
    """Icono real para la bandeja/ejecutable: recursos\\icono.ico (tuyo) o static\\jarvis.ico."""
    for name in ("recursos/icono.ico", "recursos/icono.png", "jarvis.ico", "static/jarvis.ico"):
        p = J.get_resource_path(name)
        if os.path.isfile(p):
            return p
    return None


def start_tray():
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception:
        J.log_terminal("pystray/Pillow no instalados: no habrá icono en la bandeja.", "AVISO")
        return
    img = None
    icon_path = J._tray_icon_path()
    if icon_path:
        try:
            img = Image.open(icon_path)      # usa tu icono.ico real si existe
        except Exception as e:
            J.log_terminal(f"No pude abrir el icono {icon_path}: {e}. Uso el generado.", "AVISO")
    if img is None:                          # respaldo: círculo dibujado con el color del tema
        r, g, b = J.THEMES[J.settings["theme"]][1]
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((3, 3, 61, 61), outline=(r, g, b, 255), width=5)
        d.ellipse((15, 15, 49, 49), outline=(r, g, b, 160), width=3)
        d.ellipse((24, 24, 40, 40), fill=(255, 255, 255, 255))
    item = pystray.MenuItem
    menu = pystray.Menu(
        item("Mostrar u ocultar HUD", lambda: J.hud_toggle(), default=True),
        item("Tamaño: orbe", lambda: (J.hud_show(), J.hud_set_size("orbe"))),
        item("Tamaño: compacto", lambda: (J.hud_show(), J.hud_set_size("compacto"))),
        item("Tamaño: expandido", lambda: (J.hud_show(), J.hud_set_size("expandido"))),
        pystray.Menu.SEPARATOR,
        item("Pausar micrófono", lambda: J.toggle_mic(), checked=lambda i: not J.settings["mic_enabled"]),
        item("Tablero del aula…", lambda: J.open_aula_window()),
        item("Ajustes…", lambda: J.open_settings_window()),
        item("Bienvenida y primeros pasos…", lambda: J.open_welcome_window()),
        item("Ver registro", lambda: os.startfile(J.LOG_PATH) if J.IS_WIN and os.path.exists(J.LOG_PATH) else None),
        pystray.Menu.SEPARATOR,
        item("Salir de Jarvis", lambda: J.quit_app()),
    )
    icon = pystray.Icon("jarvis", img, "Jarvis · Ctrl+Alt+J", menu)
    J.hud["tray"] = icon
    threading.Thread(target=icon.run, daemon=True).start()


def hotkey_loop():
    """Atajos globales: Ctrl+Alt+J (mostrar/ocultar) y Ctrl+Alt+Espacio (hablar)."""
    if not J.IS_WIN:
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
        J.log_terminal(f"Atajo ocupado por otro programa: {', '.join(ocupados)}. "
                     "Lo demás funciona; puedes usar la palabra de activación.", "AVISO")
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == 0x0312:              # WM_HOTKEY
            try:
                if msg.wParam == 1:
                    J.hud_toggle()
                elif msg.wParam == 2:
                    J.hud_show()
                    J.activate_listening()
            except Exception as e:
                J.log_terminal(f"Error en atajo: {e}", "ERROR")


__all__ = [
    'HUD_LOADER',
    'HUD_SOLID_BG',
    'WELCOME_TRY',
    '_apply_tool_window',
    '_clamp',
    '_corner_xy',
    '_initial_xy',
    '_on_hud_closing',
    '_on_hud_moved',
    '_on_hud_shown',
    '_open_browser_hud',
    '_save_pos_timer',
    '_temp_hide',
    '_tray_icon_path',
    '_work_area',
    'close_settings_window',
    'close_welcome_window',
    'create_hud',
    'handle_open_welcome',
    'handle_welcome_done',
    'handle_welcome_status',
    'hotkey_loop',
    'hud',
    'hud_hide',
    'hud_reposition',
    'hud_set_size',
    'hud_show',
    'hud_toggle',
    'hud_transparency_supported',
    'open_settings_window',
    'open_welcome_window',
    'quit_app',
    'start_tray',
    'toggle_mic',
    'welcome_at_start',
    'welcome_status',
    'welcome_voice',
]
