"""Jarvis integrado en Windows (7.2): menú del clic derecho, enlaces jarvis://, Win+R «jarvis», lista de saltos,
notificaciones nativas y la conexión del orbe de la barra de tareas (mod de Windhawk).

La parte que toca Windows está en windows_shell.py. Aquí: qué hace Jarvis con cada enlace, el archivo de enlace
local (dirección + código secreto, para el orbe y para un segundo Jarvis que solo trae un enlace) y los ajustes.
Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import hmac
import json
import os
import sys
import threading
import time
import uuid

from flask import abort, request

import windows_shell
from nucleo import J

LINK_FILE = os.path.join(J.CONFIG_DIR, "enlace.json")
link_token = {"value": ""}
WINDHAWK_MOD = os.path.join(J.APP_DIR, "windhawk", "jarvis-orbe.wh.cpp")
TOAST_ORIGINS = {"NOTAS", "ALARMA", "CALENDARIO", "TIMER", "VIGILANTE", "SISMO"}
_toast_last = {"t": 0.0, "text": ""}


def write_link_file():
    """Dirección y código secreto de este Jarvis, solo legibles para tu usuario de Windows."""
    link_token["value"] = uuid.uuid4().hex + uuid.uuid4().hex
    try:
        os.makedirs(J.CONFIG_DIR, exist_ok=True)
        tmp = LINK_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"url": J.URL, "port": J.PORT, "token": link_token["value"], "pid": os.getpid(),
                       "version": J.VERSION}, f)
        os.replace(tmp, LINK_FILE)
    except OSError as e:
        J.log_terminal(f"No pude escribir el enlace local: {e}", "AVISO")


def _token_ok():
    if request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403)
    tok = request.headers.get("X-Jarvis-Token", "")
    if not link_token["value"] or not hmac.compare_digest(str(tok), link_token["value"]):
        abort(403)


# ----------------------------------------------------------------------------- qué hace cada enlace
def link_order(text):
    """Una orden que llega por un enlace (menú, lista de saltos, orbe, notificación). Se atiende como si la
    escribieras, pero con las reglas del celular: nada de apagar, cerrar programas, escribir en ventanas ni
    borrar datos (un enlace también podría venir de una página web)."""
    def _run():
        J.push_chat("user", text, "enlace")
        J.pending.update(skill=None, args=None, expires=0)
        J._tl.remote, J._tl.via = True, "enlace"
        try:
            J.process_command(text)
        except Exception as e:
            J.log_terminal(f"Error con la orden del enlace «{text}»: {e}", "ERROR")
        finally:
            J._tl.remote, J._tl.via = False, None
    threading.Thread(target=_run, daemon=True, name="enlace").start()


def focus_input():
    J.hud_show()
    if J.hud.get("size") == "orbe":
        J.hud_set_size("compacto")
    J.socketio.emit("focus_input", {})


def run_link(url, source="enlace"):
    """Ejecuta un enlace jarvis://. Devuelve True si se entendió."""
    p = windows_shell.parse_link(url)
    if not p:
        J.log_terminal(f"Enlace no válido: {str(url)[:120]}", "AVISO")
        return False
    action, arg = p
    J.log_terminal(f"Enlace ({source}): {action}{' · ' + arg if arg else ''}", "SISTEMA")
    if action == "mostrar":
        J.hud_show()
    elif action == "ocultar":
        J.hud_hide()
    elif action == "alternar":
        J.hud_toggle()
    elif action == "escribir":
        focus_input()
    elif action == "escuchar":
        J.activate_listening()
    elif action == "microfono":
        J.toggle_mic()
    elif action == "ajustes":
        J.open_settings_window()
    elif action == "bienvenida":
        J.open_welcome_window()
    elif action == "prueba":
        threading.Thread(target=J.run_system_check, daemon=True).start()
    elif action == "temporizador":
        mins = int(arg)
        J.add_timer(mins * 60, "")
        J.reply(f"Temporizador de {J._spoken_duration(mins * 60)} en marcha.", "TIMER")
    elif action == "posponer":
        mins, label = arg.split("/", 1)
        J.trigger_alarm(int(mins) * 60, label)
        J.reply(f"Vale, te lo recuerdo en {mins} minutos.", "ALARMA")
    elif action in ("orden", "rutina"):
        link_order(arg)
    elif action in ("volumen", "multimedia"):
        quick_skill(action, arg)
    return True


def quick_skill(name, accion):
    """Volumen y música desde el orbe (rueda del ratón, clic central): al instante y sin hablar."""
    sk = J.skills.REGISTRY.get(name)
    if sk is None:
        return

    def _run():
        try:
            sk.run({"accion": accion})
        except Exception as e:
            J.log_terminal(f"Orbe: {name} {accion}: {e}", "AVISO")
    threading.Thread(target=_run, daemon=True, name="orbe-" + name).start()


@J.app.route("/api/enlace", methods=["POST"])
def api_link():
    J._token_ok()
    d = request.get_json(silent=True) or {}
    url = str(d.get("url") or request.get_data(as_text=True) or "")[:600]
    ok = J.run_link(url, str(d.get("origen") or "enlace")[:20])
    return {"ok": ok}


_agenda_cache = {"t": 0.0, "text": ""}


def _orb_agenda():
    """Lo próximo de hoy (una línea), como mucho una consulta por minuto."""
    if time.time() - _agenda_cache["t"] > 60:
        _agenda_cache["t"] = time.time()
        try:
            items = J.agenda("hoy", with_day=False)
            _agenda_cache["text"] = str(items[0])[:90] if items else ""
        except Exception:
            _agenda_cache["text"] = ""
    return _agenda_cache["text"]


@J.app.route("/api/orbe")
def api_orb():
    """Lo que necesita el orbe de la barra de tareas para pintarse. Solo para tu equipo y con el código."""
    J._token_ok()
    snap = J._timers_snapshot()
    nxt = min(snap, key=lambda x: x["remaining"]) if snap else None
    f = J.orb_feed
    mode = J.state.get("mode", "idle")
    return {"mode": mode, "mic": J.state.get("mic", "off"), "ai": J.state.get("ai", ""),
            "ai_label": J.state.get("ai_label", "")[:60], "net": J.state.get("net", ""),
            "live": bool(J.state.get("live")), "visible": bool(J.hud.get("visible")),
            "resting": bool(J.state.get("resting")), "timers": len(snap),
            "next": int(nxt["remaining"]) if nxt else -1, "total": int(nxt["total"]) if nxt else 0,
            "label": (nxt["label"] or "")[:40] if nxt else "",
            "level": f["level"] if mode in ("awaiting", "idle") and J.state.get("mic") == "on" else 0.0,
            "seq": f["seq"], "role": f["role"], "msg": f["msg"],
            "alert_seq": f["alert_seq"], "alert": f["alert"],
            "agenda": _orb_agenda(), "approvals": len(J.aprobaciones.pending()),
            "approval": (J.aprobaciones.latest() or {}).get("titulo", "")[:120],
            "approval_id": (J.aprobaciones.latest() or {}).get("id", 0), "accent": J.mood_accent(), "mood": J._mood["mood"],
            "version": J.VERSION, **_orb_project()}


def _orb_project():
    """8.4: avance del proyecto en marcha, para el arco verde del reactor."""
    st = J.project_run["st"] if J.project_run["busy"] else None
    if not st:
        return {"project_total": 0, "project_done": 0, "project_name": ""}
    steps = st.get("pasos") or []
    done = sum(1 for p in steps if p.get("estado") in ("hecho", "error", "omitido"))
    return {"project_total": len(steps), "project_done": done, "project_name": str(st.get("nombre", ""))[:60]}


@J.app.route("/api/orden", methods=["POST"])
def api_local_order():
    """Una orden escrita en el cuadro del orbe. Es tuya (llega con el código secreto, que solo puede leer tu
    usuario de Windows), así que se atiende igual que en la barra del HUD."""
    J._token_ok()
    d = request.get_json(silent=True) or {}
    text = str(d.get("texto", "")).strip()[:1000]
    if not text:
        return {"ok": False}
    J.log_terminal(text, "USUARIO")
    J.submit_command(text, "orbe")
    return {"ok": True}


def forward_link(url, link_file=None, timeout=4):
    """Desde un segundo Jarvis que solo trae un enlace: se lo pasa al que ya está abierto. True si llegó."""
    import urllib.request
    try:
        with open(link_file or LINK_FILE, encoding="utf-8") as f:
            d = json.load(f)
        req = urllib.request.Request(d["url"] + "/api/enlace", data=json.dumps({"url": url}).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "X-Jarvis-Token": d["token"]},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return bool(json.loads(r.read().decode("utf-8")).get("ok"))
    except Exception:
        return False


# ----------------------------------------------------------------------------- registrar en Windows
def _launch():
    exe, args = windows_shell.launcher(getattr(sys, "frozen", False), sys.executable,
                                       os.path.join(J.APP_DIR, "jarvis.py"))
    icon = J.get_resource_path(os.path.join("static", "jarvis.ico"))
    custom = os.path.join(J.APP_DIR, "recursos", "icono.ico")
    if os.path.exists(custom):
        icon = custom
    vbs = os.path.join(J.APP_DIR, "Jarvis.vbs")
    target = exe if getattr(sys, "frozen", False) else (vbs if os.path.exists(vbs) else exe)
    return exe, args, icon, target


def windows_apply():
    """Instala o quita la integración según el ajuste. Devuelve un texto con el resultado."""
    if not J.IS_WIN:
        return "Solo funciona en Windows."
    if J.PORTABLE:
        return "En modo USB no se toca el Windows del equipo prestado."
    exe, args, icon, target = _launch()
    try:
        if J.settings["windows_integration"]:
            windows_shell.apply(windows_shell.registry_plan(exe, args, icon, target))
            msg = "Jarvis está en el clic derecho del escritorio, en Win+R «jarvis» y en los enlaces jarvis://."
            try:
                windows_shell.stamp_shortcuts()
                windows_shell.set_jump_list(exe, args, icon)
                msg += " La lista de saltos del icono estará lista la próxima vez que abras Jarvis."
            except Exception as e:
                J.log_terminal(f"Lista de saltos: {e} (instala pywin32 para tenerla).", "AVISO")
            J.log_terminal(msg, "SISTEMA")
            return msg
        if windows_shell.installed():
            windows_shell.remove()
            try:
                windows_shell.clear_jump_list()
            except Exception:
                pass
            J.log_terminal("Quité a Jarvis del clic derecho, Win+R y los enlaces.", "SISTEMA")
        return "Integración con Windows apagada."
    except OSError as e:
        J.log_terminal(f"Integración con Windows: {e}", "AVISO")
        return f"No pude cambiar el registro de Windows: {e}"


def windows_toast(text, origin):
    """Notificación nativa para los avisos (recordatorios, calendario, temporizadores, vigilante, sismos)."""
    if not (J.IS_WIN and J.settings["windows_integration"] and J.settings["windows_toasts"]):
        return
    if origin not in TOAST_ORIGINS:
        return
    now = time.time()
    if text == _toast_last["text"] and now - _toast_last["t"] < 20:
        return
    _toast_last.update(t=now, text=text)
    title = {"NOTAS": "Recordatorio", "ALARMA": "Recordatorio", "CALENDARIO": "Tu agenda", "TIMER": "Temporizador",
             "VIGILANTE": "Aviso", "SISMO": "Sismo"}.get(origin, "Jarvis")
    if origin == "TIMER":
        buttons = [("Otros 5 minutos", windows_shell.make_link("temporizador", "5"))]
    elif origin in ("NOTAS", "ALARMA", "CALENDARIO"):
        buttons = [("Posponer 5 min", windows_shell.make_link("posponer", "5/" + text[:150])),
                   ("Posponer 15 min", windows_shell.make_link("posponer", "15/" + text[:150]))]
    else:
        buttons = []
    buttons.append(("Abrir Jarvis", "jarvis://mostrar"))
    windows_shell.toast(title, text, buttons)


@J.socketio.on("windows_info")
def handle_windows_info(data=None):
    d = data or {}
    msg = ""
    if d.get("apply"):
        msg = J.windows_apply()
    code = ""
    try:
        with open(J.WINDHAWK_MOD, encoding="utf-8") as f:
            code = f.read()
    except OSError:
        pass
    return {"supported": J.IS_WIN and not J.PORTABLE, "installed": windows_shell.installed(), "msg": msg,
            "mod_path": J.WINDHAWK_MOD, "mod_code": code,
            "orb_connected": time.time() - J.orb_seen["t"] < 10}


orb_seen = {"t": 0.0}


@J.app.after_request
def _orb_mark(resp):
    try:
        if request.path == "/api/orbe" and resp.status_code == 200:
            J.orb_seen["t"] = time.time()
        if request.path.startswith("/static/") or request.path in ("/", "/ajustes", "/aula", "/proyector", "/bienvenida"):
            resp.headers["Cache-Control"] = "no-cache"      # 9.1: tras actualizar, el HUD carga siempre lo nuevo
    except Exception:
        pass
    return resp


@J.app.context_processor
def _asset_version():
    """9.1: ?v=versión en los .css y .js, para que la ventana del HUD no use los de la versión anterior."""
    return {"asset_v": J.VERSION}


@J.socketio.on("open_windhawk_folder")
def handle_open_windhawk_folder():
    if J.IS_WIN and os.path.isdir(os.path.dirname(J.WINDHAWK_MOD)):
        os.startfile(os.path.dirname(J.WINDHAWK_MOD))


def windows_at_start(link=None):
    """Al arrancar: el archivo de enlace, la integración (si está activada) y el enlace con el que se abrió."""
    J.write_link_file()
    if J.IS_WIN and J.settings["windows_integration"]:
        threading.Thread(target=J.windows_apply, daemon=True).start()
    if link:
        threading.Timer(3.0, lambda: J.run_link(link, "inicio")).start()


__all__ = [
    'LINK_FILE', 'TOAST_ORIGINS', 'WINDHAWK_MOD', '_launch', '_orb_mark', '_toast_last', '_token_ok', 'api_link',
    'api_orb', '_orb_project', 'api_local_order', 'quick_skill', '_agenda_cache', '_orb_agenda', 'focus_input', 'forward_link', 'handle_open_windhawk_folder', 'handle_windows_info', 'link_order',
    'link_token', 'orb_seen', 'run_link', 'windows_apply', 'windows_at_start', 'windows_toast', 'write_link_file',
]
