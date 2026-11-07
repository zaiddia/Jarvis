"""12.10: acciones de la ventana. Lo que haces a mano con el teclado, como orden: «cierra la pestaña del explorador»,
«cierra la pestaña de Chrome», «sube una carpeta», «nueva carpeta», «guarda el archivo», «pon la ventana a la izquierda»,
«pasa la ventana al otro monitor», «nuevo escritorio virtual», «historial del portapapeles», «recorte de pantalla»…

Cada orden es un atajo de teclado FIJO sobre la ventana que nombras (o la que tienes delante): Jarvis no teclea texto ni
mueve el mouse por su cuenta. La lista está en atajos.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import os
import re
import subprocess
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


# ============================================================================ 12.10.1: Acceso por voz de Windows
# Windows 11 trae «Acceso por voz»: tú diriges el mouse con la voz («mostrar números», «clic en 5», «doble clic en 5»,
# «cuadrícula del mouse», «desplazar hacia abajo»). Jarvis lo abre y lo cierra; no hace clic por su cuenta.
_VA_ON = re.compile(r"\b(?:activa|abre|enciende|prende|inicia|pon|arranca)(?:me)?\s+(?:el\s+)?(?:control\s+(?:del\s+(?:mouse|raton)\s+)?por\s+voz|"
                    r"acceso\s+por\s+voz|mouse\s+por\s+voz|raton\s+por\s+voz)\b")
_VA_OFF = re.compile(r"\b(?:desactiva|cierra|apaga|quita|deten)\s+(?:el\s+)?(?:control\s+(?:del\s+(?:mouse|raton)\s+)?por\s+voz|acceso\s+por\s+voz|"
                     r"mouse\s+por\s+voz|raton\s+por\s+voz)\b")
VA_HELP = ("Ya puedes manejar el mouse con tu voz. Di «mostrar números» y luego «clic en 5» o «doble clic en 5»; «cuadrícula del mouse» "
           "para llegar a cualquier punto; «desplazar hacia abajo» para bajar. Para dejarlo, di «Jarvis, desactiva el control por voz».")


def _va_running():
    if J.psutil is None:
        return False
    for p in J.psutil.process_iter(["name"]):
        try:
            if str(p.info["name"] or "").lower() == "voiceaccess.exe":
                return True
        except Exception:
            pass
    return False


def voice_access_on(origin="PC"):
    if _va_running():
        J.reply("El control por voz ya está activo. " + VA_HELP, origin)
        return
    exe = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "voiceaccess.exe")
    try:
        if os.path.exists(exe):
            subprocess.Popen([exe], creationflags=0x08000000)
        else:
            _send(0, ("win", "ctrl", "s"))             # el atajo de Windows para Acceso por voz
    except Exception:
        try:
            os.startfile("ms-settings:easeofaccess-speechrecognition")
        except OSError:
            pass
        J.reply("No pude abrir el control por voz; te abrí su ajuste de Windows (Accesibilidad › Voz › Acceso por voz). Si no aparece, "
                "actualiza Windows 11.", origin)
        return
    J.reply("Abrí el control por voz de Windows. La primera vez descarga el idioma y te enseña lo básico. " + VA_HELP, origin)


def voice_access_off(origin="PC"):
    if J.psutil is None or not _va_running():
        J.reply("El control por voz no estaba activo.", origin)
        return
    for p in J.psutil.process_iter(["name"]):
        try:
            if str(p.info["name"] or "").lower() == "voiceaccess.exe":
                p.terminate()
        except Exception:
            pass
    J.reply("Listo, cerré el control por voz.", origin)


def window_voice(text, t):
    """Pestañas con programa nombrado (o en Explorador, terminal…) y el catálogo de atajos."""
    if _VA_ON.search(t) or _VA_OFF.search(t):
        if not J.IS_WIN:
            J.reply("El control por voz es de Windows 11.", "PC")
        elif _VA_OFF.search(t):
            voice_access_off()
        else:
            voice_access_on()
        return True
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


__all__ = ['BROWSERS', 'VA_HELP', '_VA_OFF', '_VA_ON', '_va_running', 'voice_access_off', 'voice_access_on', 'window_voice']
