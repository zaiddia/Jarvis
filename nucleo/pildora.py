"""El HUD como píldora (12.13): se esconde solo en el borde derecho de la pantalla y se abre al pasar el ratón.

- La página del HUD (static/js/pildora.js) decide cuándo: se esconde tras unos segundos sin usarlo,
  salvo con el ratón encima, mientras escribes o mientras Jarvis te escucha, piensa o habla.
- Aquí se cambia la ventana: queda una píldora delgada pegada al borde derecho y, al abrirse,
  el HUD vuelve a su tamaño junto a la píldora, a la misma altura.
- Antes de esconderse se comprueba en Windows que el ratón no esté sobre el HUD (solo se lee
  dónde está el puntero; Jarvis no lo mueve).
"""
import queue
import re
import threading
import time

from nucleo import J

PILL_W, PILL_H = 22, 104          # píxeles lógicos
_EDGE_GAP = 8                     # separación del HUD abierto con el borde derecho
pill = {"docked": False, "lock": threading.Lock(), "cy": None, "queue": queue.Queue(), "thread": None, "sync": False}


def pill_enabled():
    return bool(J.settings.get("hud_auto_hide", True)) and J.hud.get("window") is not None


def _pill_xy(cy):
    ax, ay, aw, ah = J._work_area()
    y = int(cy - PILL_H / 2)
    y = max(int(ay) + 6, min(y, int(ay + ah) - PILL_H - 6))
    return int(ax + aw - PILL_W), y


def _open_xy(w, h, cy):
    ax, ay, aw, ah = J._work_area()
    return J._clamp(int(ax + aw - w - _EDGE_GAP), int(cy - h / 2), w, h)


def _win_rect():
    """Rectángulo de la ventana del HUD en píxeles de Windows, o None."""
    if not J.IS_WIN:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = J._hud_hwnd()
        r = wintypes.RECT()
        if hwnd and ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return hwnd, r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    return None


def cursor_over_hud():
    """¿El puntero está sobre el HUD? (solo Windows; en otros sistemas responde la página)."""
    rect = _win_rect()
    if not rect:
        return False
    try:
        import ctypes
        from ctypes import wintypes
        p = wintypes.POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(p)):
            return False
        _, l, t, r, b = rect
        return l <= p.x < r and t <= p.y < b
    except Exception:
        return False


def _shape():
    """En Windows recorta la ventana con forma de píldora (con fondo sólido se vería un rectángulo).
    Mira el estado al aplicarse, así un abrir/cerrar rápido no deja el HUD recortado."""
    def go():
        rect = _win_rect()
        if not rect:
            return
        try:
            import ctypes
            hwnd, l, t, r, b = rect
            gdi, user32 = ctypes.windll.gdi32, ctypes.windll.user32
            w, h = r - l, b - t
            if pill["docked"] and w < 80:
                rgn = gdi.CreateRoundRectRgn(0, 0, w + 1, h + 1, w, w)
                user32.SetWindowRgn(hwnd, rgn, True)       # Windows se queda con la región
            else:
                user32.SetWindowRgn(hwnd, 0, True)
        except Exception as e:
            J.log_terminal(f"No se pudo dar forma a la píldora: {e}", "AVISO")
    threading.Timer(0.15, go).start()


def _dock_now(on, force=False):
    """Hace el cambio de ventana (en el hilo de la píldora). → True si cambió."""
    win = J.hud.get("window")
    if win is None:
        return False
    with pill["lock"]:
        if bool(on) == pill["docked"]:
            return False
        if on and not force and cursor_over_hud():
            J.socketio.emit("hud_pill", {"on": False, "refused": True})
            return False
        try:
            if on:
                cy = J.hud["y"] + (J.hud["h"] or J.hud_dims(J.hud["size"])[1]) / 2
                x, y = _pill_xy(cy)
                pill.update(docked=True, cy=y + PILL_H / 2)
                J.hud.update(x=x, y=y, ignore_moves_until=time.time() + 2.0)
                J.socketio.emit("hud_pill", {"on": True})
                win.resize(PILL_W, PILL_H)
                win.move(x, y)
            else:
                w, h = J.hud_dims(J.hud["size"])
                x, y = _open_xy(w, h, pill["cy"] if pill["cy"] is not None else J.hud["y"] + PILL_H / 2)
                pill["docked"] = False
                J.hud.update(x=x, y=y, w=w, h=h, ignore_moves_until=time.time() + 2.0)
                J.socketio.emit("hud_pill", {"on": False})
                win.resize(w, h)
                win.move(x, y)
            _shape()
        except Exception as e:
            J.log_terminal(f"No se pudo cambiar la píldora del HUD: {e}", "AVISO")
            return False
    return True


def _dock_worker():
    while True:
        on, force = pill["queue"].get()
        while not pill["queue"].empty():               # solo cuenta lo último que se pidió
            on, force = pill["queue"].get()
        try:
            _dock_now(on, force)
        except Exception as e:
            J.log_terminal(f"Píldora del HUD: {e}", "AVISO")


def hud_dock(on, force=False):
    """on=True: esconde el HUD como píldora en el borde derecho. on=False: lo abre junto a la píldora.
    Nunca hace esperar a quien lo pide: mover la ventana puede tardar, y si lo pide la escucha
    (al decir «Jarvis») no debe frenar el micrófono. → True si quedó pedido."""
    if J.hud.get("window") is None:
        return False
    if pill.get("sync"):                               # pruebas
        return _dock_now(on, force)
    with pill["lock"]:
        if pill["thread"] is None:
            pill["thread"] = threading.Thread(target=_dock_worker, daemon=True, name="pildora")
            pill["thread"].start()
    pill["queue"].put((bool(on), bool(force)))
    return True


def pill_on_mode(mode):
    """Lo llama set_state: al decir «Jarvis», mientras piensa o al responder, la píldora se abre."""
    if mode in ("awaiting", "thinking", "speaking") and pill["docked"] and pill_enabled() and J.hud.get("visible"):
        J.hud_dock(False)


def pill_docked():
    return pill["docked"]


@J.socketio.on("hud_dock")
def handle_hud_dock(data):
    on = bool((data or {}).get("on"))
    if on and not pill_enabled():
        return
    J.hud_dock(on)


@J.socketio.on("hud_pill_state")
def handle_hud_pill_state(_data=None):
    return {"on": pill["docked"], "enabled": pill_enabled()}


# ------------------------------------------------------------------ por voz
_PL_NOW = re.compile(r"\b(?:escondete|ocultate|hazte a un lado|retirate|quitate)\s+(?:a un lado|al lado|a la derecha|al borde|en el borde)\b"
                     r"|\b(?:modo|vuelvete|hazte|convierte(?:te)? en)\s+(?:una\s+)?pildora\b|\bminimizate\b")
_PL_ON = re.compile(r"\b(?:escondete|ocultate)\s+(?:solo|sola|automaticamente|cuando no te use)\b"
                    r"|\b(?:activa|enciende|pon)\s+(?:la\s+)?(?:pildora|escondida automatica|ocultacion automatica)\b")
_PL_OFF = re.compile(r"\b(?:no te escondas|no te ocultes|quedate (?:fijo|quieto|visible|abierto)|deja (?:el |la )?(?:hud|panel|interfaz) (?:fijo|quieto|abierto|visible))\b"
                     r"|\b(?:quita|desactiva|apaga)\s+(?:la\s+)?(?:pildora|escondida automatica|ocultacion automatica)\b")


def _pill_setting(on):
    with J.settings_lock:
        J.settings["hud_auto_hide"] = bool(on)
        try:
            J.save_settings_file()
        except Exception:
            pass
    J.socketio.emit("settings_updated", J.public_settings())


def pill_voice(text, t):
    if _PL_OFF.search(t):
        _pill_setting(False)
        J.hud_show()
        J.reply("Listo: el panel se queda abierto. Di «escóndete solo» para volver a la píldora.", "SISTEMA")
        return True
    if _PL_ON.search(t):
        _pill_setting(True)
        J.reply(f"Listo: me escondo en el borde derecho tras {J.settings.get('hud_hide_secs', 5)} segundos sin usarme. "
                "Pasa el ratón por la píldora para abrirme.", "SISTEMA")
        return True
    if _PL_NOW.search(t):
        if J.hud.get("window") is None:
            J.reply("El panel está abierto en el navegador; no lo puedo volver píldora.", "SISTEMA")
            return True
        J.hud_show(expand=False)
        J.reply("Me escondo a la derecha. Pasa el ratón por la píldora para abrirme.", "SISTEMA")
        threading.Timer(2.2, lambda: J.hud_dock(True, force=True)).start()   # deja que termine de hablar
        return True
    return False


__all__ = [
    'PILL_H',
    'PILL_W',
    '_EDGE_GAP',
    '_dock_now',
    '_dock_worker',
    '_PL_NOW',
    '_PL_OFF',
    '_PL_ON',
    '_open_xy',
    '_pill_setting',
    '_pill_xy',
    '_shape',
    '_win_rect',
    'cursor_over_hud',
    'handle_hud_dock',
    'handle_hud_pill_state',
    'hud_dock',
    'pill',
    'pill_docked',
    'pill_enabled',
    'pill_on_mode',
    'pill_voice',
]
