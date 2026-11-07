"""12.10: acciones de la ventana. Lo que haces a mano con el teclado, como orden: «cierra la pestaña del explorador»,
«cierra la pestaña de Chrome», «sube una carpeta», «nueva carpeta», «guarda el archivo», «pon la ventana a la izquierda»,
«pasa la ventana al otro monitor», «nuevo escritorio virtual», «historial del portapapeles», «recorte de pantalla»…

Cada orden es un atajo de teclado FIJO sobre la ventana que nombras (o la que tienes delante): Jarvis no teclea texto ni
mueve el mouse por su cuenta. La lista está en atajos.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import time

import atajos
import skills
from nucleo import J

BROWSERS = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"}


def _front():
    """(hwnd, proceso, clase) de la ventana sobre la que actuar (la última que usaste, no el HUD)."""
    h = skills.target_window()
    proc = ""
    try:
        proc = str(skills._proc_name(skills._pid_of(h)) or "").lower()
    except Exception:
        pass
    return h, proc, skills._class_of(h)


def _send(hwnd, keys):
    if skills.pyautogui is None:
        raise skills.SkillError("Falta la librería pyautogui para mandar el atajo.")
    if hwnd:
        skills.focus_window(hwnd)
        time.sleep(0.25)
    skills.pyautogui.hotkey(*keys)


def _tab(p, origin="PC"):
    wins = skills.list_windows()
    if p["app"]:
        w = atajos.pick_window(wins, atajos.app_procs(p["app"]))
        if not w:
            J.reply(f"No tienes abierto {p['app']}.", origin)
            return
        h, title = w["hwnd"], w["title"]
    else:
        h, proc, _cls = _front()
        title = skills._title_of(h)
        if proc not in atajos.TABBED:                  # Word, Excel…: Ctrl+W cerraría el documento. Mejor tu navegador.
            w = atajos.pick_window(wins, tuple(BROWSERS))
            if not w:
                J.reply(f"«{title[:40]}» no tiene pestañas y no veo ningún navegador abierto.", origin)
                return
            h, title = w["hwnd"], w["title"]
    _send(h, atajos.TAB_KEYS[p["accion"]])
    J.reply(f"{atajos.TAB_SAID[p['accion']]} en «{title[:50]}».", origin)


def _action(aid, keys, scope, said, origin="PC"):
    if scope == "sistema":
        _send(0, keys)
        J.reply(said, origin)
        return
    if scope == "explorer":
        h, proc, cls = _front()
        if not (proc == "explorer.exe" and cls == atajos.EXPLORER_CLASS):
            w = atajos.pick_window(skills.list_windows(), ("explorer.exe",))
            if not w:
                J.reply("No hay ninguna carpeta abierta en el Explorador. Di «abre el explorador».", origin)
                return
            h = w["hwnd"]
        _send(h, keys)
        J.reply(said, origin)
        return
    h, _proc, _cls = _front()
    _send(h, keys)
    J.reply(f"{said[:-1]} en «{skills._title_of(h)[:50]}».", origin)


def window_voice(text, t):
    """Pestañas con programa nombrado (o en Explorador, terminal…) y el catálogo de atajos."""
    p = atajos.parse_tab(text)
    act = None if p else atajos.parse_action(text)
    if not p and not act:
        return False
    if not J.IS_WIN:
        if p and not p["app"]:
            return False                               # que lo atienda la orden de siempre
        J.reply("Eso solo lo puedo hacer en Windows.", "PC")
        return True
    try:
        if p:
            if not p["app"]:
                _h, proc, _c = _front()
                if proc in BROWSERS:
                    return False                       # en el navegador ya lo hace la orden de siempre (también «pestaña 3»)
            _tab(p)
        else:
            _action(*act)
    except skills.SkillError as e:
        J.reply(str(e), "PC")
    return True


__all__ = ['BROWSERS', 'window_voice']
