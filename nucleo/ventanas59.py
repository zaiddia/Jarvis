"""12.59: que el panel y los Ajustes no se abran y se cierren solos.

Causa (visto en un registro real tras actualizar a la 12.57): al reiniciarse para actualizar, el Jarvis viejo se cierra,
pero su motor de ventanas (Microsoft Edge WebView2) sigue vivo unos segundos con la carpeta de datos de las ventanas
tomada. Si el Jarvis nuevo crea sus ventanas en ese momento, cada ventana que abre se cierra al instante.

  · Antes de crear las ventanas, Jarvis espera a que esos procesos sueltos terminen (y, si se quedan colgados,
    los cierra: son del Jarvis viejo, de su misma carpeta).
  · Si aun así una ventana se cierra sola en cuanto se abre, Jarvis la abre en el navegador y, si es el panel, se
    reinicia una vez (no más de una vez cada 10 minutos) para recuperar las ventanas.
  · «reiníciate» · «abre los ajustes en el navegador» · «abre el panel en el navegador».
  · En la conversación en vivo: el «sí» a la actualización de Jarvis ahora cuenta, y un «sí / confirmar» suelto ya no
    se traduce como otra orden (antes se volvía «actualiza todos mis programas»).

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import os
import re
import time
import webbrowser

from nucleo import J

VW59_RESTART_GAP = 600            # segundos entre reinicios automáticos por ventanas caídas
VW59_QUICK_CLOSE = 3.0            # una ventana que se cierra antes de esto, sin que nadie la cerrara, «se cayó»


def _vw59_stamp_path():
    return os.path.join(J.CONFIG_DIR, "reinicio_ventanas.txt")


def vw59_webview_procs(storage):
    """Procesos de WebView2 que usan la carpeta de datos de las ventanas de Jarvis (los del Jarvis viejo)."""
    if not J.IS_WIN:
        return []
    try:
        import psutil
    except ImportError:
        return []
    want = os.path.normcase(os.path.abspath(storage))
    me = os.getpid()
    out = []
    for p in psutil.process_iter(["name", "cmdline", "ppid"]):
        try:
            if (p.info.get("name") or "").lower() != "msedgewebview2.exe":
                continue
            cmd = os.path.normcase(" ".join(p.info.get("cmdline") or []))
            if want in cmd and p.info.get("ppid") != me:
                out.append(p)
        except Exception:
            continue
    return out


def vw59_wait_webview(storage, timeout=20.0, sleep=time.sleep):
    """Espera a que el motor de ventanas del Jarvis viejo suelte la carpeta; si se queda colgado, lo cierra.
    → cuántos procesos tuvo que cerrar."""
    t0 = time.time()
    procs = J.vw59_webview_procs(storage)
    if not procs:
        return 0
    J.log_terminal(f"Espero a que se cierren {len(procs)} procesos de ventanas del Jarvis anterior…", "ARRANQUE")
    while procs and time.time() - t0 < timeout:
        sleep(0.5)
        procs = J.vw59_webview_procs(storage)
    killed = 0
    for p in procs:
        try:
            p.kill()
            killed += 1
        except Exception:
            pass
    if killed:
        J.log_terminal(f"Cerré {killed} procesos de ventanas que el Jarvis anterior dejó colgados.", "ARRANQUE")
        sleep(1.0)
    return killed


def vw59_can_restart(now=None):
    now = now or time.time()
    try:
        with open(J._vw59_stamp_path(), encoding="utf-8") as f:
            last = float(f.read().strip() or 0)
    except (OSError, ValueError):
        last = 0.0
    return now - last >= VW59_RESTART_GAP


def vw59_mark_restart(now=None):
    try:
        os.makedirs(J.CONFIG_DIR, exist_ok=True)
        with open(J._vw59_stamp_path(), "w", encoding="utf-8") as f:
            f.write(str(now or time.time()))
    except OSError:
        pass


def vw59_hud_died():
    """El panel se cerró solo (no pediste salir). → True si Jarvis se va a reiniciar para recuperarlo."""
    J.note_error("HUD", "la ventana del HUD se cerró sin pedir salir")
    if J.vw59_can_restart():
        J.vw59_mark_restart()
        J.log_terminal("La ventana del panel se cerró sola. Me reinicio una vez para recuperarla.", "AVISO")
        J.restart_jarvis(delay=1.5)
        return True
    J.log_terminal("La ventana del panel se volvió a cerrar sola. Sigo funcionando: abro el panel en el navegador "
                   "(o di «reiníciate»).", "AVISO")
    J._open_browser_hud()
    return False


def vw59_settings_closed(opened_at, by_us, now=None):
    """Se cerró la ventana de Ajustes. Si fue sola y enseguida, se abren en el navegador. → True si los abrió allí."""
    now = now or time.time()
    if by_us or now - opened_at > VW59_QUICK_CLOSE:
        return False
    J.log_terminal("La ventana de Ajustes se cerró sola al abrirse: te los abro en el navegador.", "AVISO")
    J.note_error("Ajustes", "la ventana de Ajustes se cerró sola al abrirse")
    webbrowser.open(f"{J.URL}/ajustes")
    return True


# ============================================================================ POR VOZ
_VW59_RESTART = re.compile(r"^(?:jarvis )?(?:reiniciate|reinicia(?:te)?(?: jarvis| el asistente| a jarvis)?|vuelve a (?:arrancar|iniciar)(?:te)?|"
                           r"reinicia (?:el programa|la aplicacion))$")
_VW59_SETTINGS_WEB = re.compile(r"^(?:jarvis )?abre (?:los |la )?(?:ajustes|configuracion|opciones) en el navegador$")
_VW59_HUD_WEB = re.compile(r"^(?:jarvis )?abre (?:el )?(?:panel|hud|tablero) en el navegador$")


def ventanas59_voice(text, t):
    if _VW59_RESTART.match(t):
        J.reply("Me reinicio. Vuelvo en unos segundos.", "SISTEMA")
        J.restart_jarvis(delay=2.0)
        return True
    if _VW59_SETTINGS_WEB.match(t):
        webbrowser.open(f"{J.URL}/ajustes")
        J.reply("Te abrí los ajustes en el navegador.", "SISTEMA")
        return True
    if _VW59_HUD_WEB.match(t):
        J._open_browser_hud()
        J.reply("Te abrí el panel en el navegador.", "SISTEMA")
        return True
    return False


# ============================================================================ CONFIRMACIONES EN VIVO
_VW59_CONFIRM = re.compile(r"^(?:si|sí|confirmar|confirmo|confirma|confirmado|hazlo|adelante|dale|de acuerdo|ok|okay|claro|procede|instalala|instalalo|instala(?:r)? la (?:version|actualizacion))\b")
_VW59_DENY = re.compile(r"^(?:no|cancela(?:r)?|cancelado|olvidalo|mejor no|no lo hagas)\b")
VW59_LIVE_OK = {"instalar_actualizacion"}     # lo único peligroso que se puede confirmar en vivo (tiene copia y vuelta atrás)


def vw59_live_confirm(order, now=None):
    """En vivo: si es la respuesta a una confirmación pendiente, la resuelve. → resultado para Gemini, o None si no aplica."""
    t = J.skills.normalize(order)
    is_yes, is_no = bool(_VW59_CONFIRM.match(t)), bool(_VW59_DENY.match(t))
    if not (is_yes or is_no):
        return None
    now = now or time.time()
    p = J.pending
    live = p.get("skill") and now < p.get("expires", 0)
    if is_no:
        if live:
            p.update(skill=None, args=None, expires=0)
            return {"result": "Cancelado."}
        return {"result": "No había nada pendiente por confirmar."}
    if live and p["skill"] in VW59_LIVE_OK:
        name, args = p["skill"], p.get("args") or {}
        p.update(skill=None, args=None, expires=0)
        J.log_terminal(f"Confirmado en vivo: {name}", "EN VIVO")
        J._tl.capture, J._tl.live = [], True
        try:
            J.run_skill(name, args, confirmed=True)
            said = list(J._tl.capture)
        finally:
            J._tl.capture, J._tl.live = None, False
        return {"result": " ".join(said) or "Hecho."}
    if live:
        return {"result": "Por seguridad, eso no se confirma en la conversación en vivo: dile al usuario que lo escriba "
                          "en el panel o que diga «confirmar» después de terminar la conversación en vivo."}
    return {"result": "No había nada pendiente por confirmar. Pregúntale al usuario qué quiere hacer."}


__all__ = ['VW59_LIVE_OK', 'VW59_QUICK_CLOSE', 'VW59_RESTART_GAP', '_VW59_CONFIRM', '_VW59_DENY', '_VW59_HUD_WEB', '_VW59_RESTART',
           '_VW59_SETTINGS_WEB', '_vw59_stamp_path', 'ventanas59_voice', 'vw59_can_restart', 'vw59_hud_died', 'vw59_live_confirm',
           'vw59_mark_restart', 'vw59_settings_closed', 'vw59_wait_webview', 'vw59_webview_procs']
