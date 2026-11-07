"""12.9: dos modos, Docente y Asistente general, y las reglas «cuando pase esto, haz aquello».

- «modo docente», «modo general», «modo automático», «¿en qué modo estás?». En automático, Jarvis es docente durante
  tu jornada (según tu horario) o conectado al Wi-Fi del colegio, y asistente general el resto del tiempo.
- Disparadores: «cuando conecte el cargador, modo general», «cuando me conecte al wifi Colegio, modo docente»,
  «cuando abra Excel, silencia las notificaciones», «cuando la batería esté baja, activa el ahorro de batería»,
  «cuando encienda el PC, dame el resumen de la mañana». «¿Qué disparadores tengo?», «borra el disparador 2».
- Avisos de batería: baja (20 %) y muy baja (8 %).
La lógica está en vidadiaria.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import re
import subprocess
import threading
import time

import equipo
import horario
import skills
import vidadiaria
from nucleo import J

mode_state = {"mode": "", "since": 0.0, "ssid": "", "ssid_t": 0.0, "plugged": None, "pct": None, "low_fired": set(), "procs": set(),
              "warned": {"low": False, "critical": False}, "started": time.time()}
MODE_LABEL = {"docente": "Docente", "general": "Asistente general"}

_MODE_SET = re.compile(r"^(?:jarvis\s+)?(?:pasa(?:te)?\s+(?:a|al)\s+|cambia(?:te)?\s+(?:a|al)\s+|activa\s+(?:el\s+)?|pon(?:te)?\s+(?:en\s+)?(?:el\s+)?)?"
                       r"modo\s+(docente|profe|profesor|colegio|escolar|general|asistente(?:\s+general)?|personal|casa|automatico|auto)$")
_MODE_ASK = re.compile(r"\b(?:estas|estamos|andas) en (?:el )?modo (?:docente|general|asistente)(?: o (?:en )?(?:el )?(?:modo )?(?:docente|general|asistente))?\b|"
                       r"\b(?:docente o general|general o docente)\b")
_TRIG_LIST = re.compile(r"\b(?:que|cuales|mis) (?:disparadores|automatizaciones|reglas automaticas)\b|\b(?:muestrame|dime|lee(?:me)?) "
                        r"(?:mis |los )?(?:disparadores|automatizaciones)\b|^(?:disparadores|automatizaciones)$")
_TRIG_DEL = re.compile(r"^(?:jarvis\s+)?(?:borra|elimina|quita|cancela)\s+(?:el|la)\s+(?:disparador|automatizacion|regla)\s+(?:numero\s+)?(?:del?\s+|de la\s+)?(.+)$")


# ----------------------------------------------------------------------------- modo
def wifi_now(max_age=60):
    """La red Wi-Fi conectada (cada minuto como mucho, es una consulta al sistema)."""
    if not J.IS_WIN:
        return ""
    if time.time() - mode_state["ssid_t"] < max_age:
        return mode_state["ssid"]
    mode_state["ssid_t"] = time.time()
    try:
        out = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, timeout=8,
                             creationflags=0x08000000, encoding="utf-8", errors="replace").stdout
        mode_state["ssid"] = equipo.parse_ssid(out)
    except Exception:
        mode_state["ssid"] = ""
    return mode_state["ssid"]


def current_mode(now=None):
    now = now or datetime.datetime.now()
    setting = J.settings.get("assistant_mode", "auto")
    if setting in vidadiaria.MODES:
        return setting
    return vidadiaria.resolve_mode("auto", bool(horario.now_class(now)), wifi_now(), J.settings.get("school_wifi", ""),
                                   bool(horario.items), vidadiaria.school_hours(horario.items, now))


def mode_rule():
    """Lo que cambia en las instrucciones de la IA según el modo (va en la parte fija: cambia pocas veces al día)."""
    if current_mode() == "general":
        return (" MODO ASISTENTE GENERAL: ahora no estás en el colegio. Ayuda como asistente personal y del computador "
                "(tareas, correo, compras, gastos, programas, el PC, la casa, ocio); no supongas que hablan de cursos, "
                "estudiantes o notas salvo que lo digan.")
    return (" MODO DOCENTE: ahora es la jornada escolar. Da prioridad a la clase, los cursos, los estudiantes y el material; "
            "«notas» suele significar calificaciones.")


def mode_info():
    m = current_mode()
    s = J.settings.get("assistant_mode", "auto")
    return {"mode": m, "label": MODE_LABEL[m], "auto": s not in vidadiaria.MODES, "ssid": mode_state["ssid"]}


def set_mode(value):
    v = {"profe": "docente", "profesor": "docente", "colegio": "docente", "escolar": "docente", "asistente": "general",
         "asistente general": "general", "personal": "general", "casa": "general", "automatico": "auto", "auto": "auto"}.get(value, value)
    J.apply_settings({"assistant_mode": v})
    _mode_changed(force=True)
    return v


def _mode_changed(force=False):
    m = current_mode()
    if m != mode_state["mode"] or force:
        old = mode_state["mode"]
        mode_state.update(mode=m, since=time.time())
        J.socketio.emit("assistant_mode", mode_info())
        if old and old != m:
            J.log_terminal(f"Cambio a modo {MODE_LABEL[m]}" + (" (automático)" if not force else ""), "MODO")


def mode_voice(text, t):
    m = _MODE_SET.match(t)
    if m:
        v = set_mode(m.group(1))
        info = mode_info()
        if v == "auto":
            J.reply(f"Modo automático: en tu jornada o en el Wi-Fi del colegio seré docente; el resto del tiempo, asistente general. "
                    f"Ahora: {info['label']}.", "MODO")
        elif v == "docente":
            J.reply("Modo docente: me concentro en tus clases, cursos y estudiantes. Para volver a lo automático, di «modo automático».", "MODO")
        else:
            J.reply("Modo asistente general: te ayudo con el PC, tus programas, gastos, listas, la casa y lo personal. Para volver a "
                    "lo automático, di «modo automático».", "MODO")
        return True
    if _MODE_ASK.search(t):
        i = mode_info()
        J.reply(f"Estoy en modo {i['label']}" + (", en automático" if i["auto"] else ", elegido por ti") + ".", "MODO")
        return True
    return False


@J.socketio.on("assistant_mode")
def handle_assistant_mode(data=None):
    v = str((data or {}).get("set") or "")
    if v in ("docente", "general", "auto"):
        set_mode(v)
    elif v == "toggle":
        set_mode("general" if current_mode() == "docente" else "docente")
    return mode_info()


# ----------------------------------------------------------------------------- disparadores
def trigger_voice(text, t):
    tr = vidadiaria.parse_trigger(text)
    if tr:
        x = vidadiaria.add_trigger(tr)
        if not x:
            J.reply("Esa acción no la puedo programar así. Prueba, por ejemplo: «cuando conecte el cargador, modo general».", "DISPARADOR")
        else:
            J.reply(f"Listo, {vidadiaria.describe(x)[0].lower() + vidadiaria.describe(x)[1:]}. Para verlos: «¿qué disparadores tengo?».",
                    "DISPARADOR")
        return True
    if t.startswith("cuando ") and re.search(r"\b(?:cargador|wifi|wi fi|bateria|abra|abro|encienda|prenda)\b", t):
        J.reply("No entendí la regla. Ejemplos: «cuando conecte el cargador, modo general», «cuando me conecte al wifi Colegio, modo "
                "docente», «cuando abra Excel, silencia las notificaciones».", "DISPARADOR")
        return True
    if _TRIG_LIST.search(t):
        L = vidadiaria.data["disparadores"]
        J.reply("No tienes disparadores. Ejemplo: «cuando conecte el cargador, modo general»." if not L else
                "Tus disparadores: " + "; ".join(f"{i + 1}. {vidadiaria.describe(x)}" for i, x in enumerate(L)) + ".", "DISPARADOR")
        return True
    m = _TRIG_DEL.match(t)
    if m:
        x = vidadiaria.remove_trigger(m.group(1))
        J.reply(f"Borré el disparador: {vidadiaria.describe(x)}." if x else "No encontré ese disparador. Di «¿qué disparadores tengo?».",
                "DISPARADOR")
        return True
    return False


def _run_trigger(x):
    J.log_terminal(f"Disparador: {vidadiaria.describe(x)}", "DISPARADOR")

    def work():
        try:
            J._tl.chained = False
            J.process_command(x["accion"])
        except Exception as e:
            J.note_error("DISPARADOR", e)
    threading.Thread(target=work, daemon=True, name="disparador").start()


def _proc_names():
    if J.psutil is None:
        return set()
    out = set()
    for p in J.psutil.process_iter(["name"]):
        try:
            out.add(str(p.info["name"] or "").lower())
        except Exception:
            pass
    return out


def _tick():
    events = []
    _mode_changed()
    # batería y cargador
    bat = None
    try:
        bat = J.psutil.sensors_battery() if J.psutil is not None else None
    except Exception:
        bat = None
    if bat is not None:
        plugged, pct = bool(bat.power_plugged), int(bat.percent)
        if mode_state["plugged"] is not None and plugged != mode_state["plugged"]:
            events.append(("cargador_on" if plugged else "cargador_off", ""))
        if plugged:
            mode_state["low_fired"].clear()
            mode_state["warned"] = {"low": False, "critical": False}
        else:
            for x in vidadiaria.fire([("bateria_baja", pct)]):
                if x["id"] not in mode_state["low_fired"]:
                    mode_state["low_fired"].add(x["id"])
                    _run_trigger(x)
            if J.settings.get("battery_alerts", True):
                low = int(J.settings.get("battery_low", 20))
                if pct <= 8 and not mode_state["warned"]["critical"]:
                    mode_state["warned"]["critical"] = True
                    J.notify(f"La batería está al {pct} %: conecta el cargador ya, o guarda tu trabajo.", "BATERÍA")
                elif pct <= low and not mode_state["warned"]["low"]:
                    mode_state["warned"]["low"] = True
                    J.notify(f"Batería al {pct} %: conviene conectar el cargador.", "BATERÍA")
        mode_state["plugged"], mode_state["pct"] = plugged, pct
    # Wi-Fi
    if any(x["evento"] == "wifi" for x in vidadiaria.data["disparadores"]) or J.settings.get("school_wifi"):
        old = mode_state["ssid"]
        new = wifi_now(max_age=25)
        if new and new != old:
            events.append(("wifi", new))
    # programas que se acaban de abrir
    if any(x["evento"] == "app" for x in vidadiaria.data["disparadores"]):
        now = _proc_names()
        if mode_state["procs"]:
            for name in now - mode_state["procs"]:
                events.append(("app", equipo.friendly(name) + " " + name))
        mode_state["procs"] = now
    for x in vidadiaria.fire(events):
        _run_trigger(x)


def _mode_worker():
    time.sleep(20)
    for x in vidadiaria.fire([("encender", "")]):
        _run_trigger(x)
    while True:
        try:
            _tick()
        except Exception as e:
            J.note_error("MODO", e)
        time.sleep(20)


def modes_start():
    vidadiaria.configure(J.CONFIG_DIR)
    mode_state["mode"] = current_mode()
    threading.Thread(target=_mode_worker, daemon=True, name="modos").start()


# ----------------------------------------------------------------------------- 12.9.1: que la IA conozca lo nuevo
ASSISTANT_ORDERS = ("instala <programa>", "actualiza todos mis programas", "¿qué programas tienen actualización?", "desinstala <programa>",
                    "¿qué está poniendo lento el PC?", "cierra el que más consume", "limpia los temporales", "¿cuánto espacio tengo?",
                    "¿qué programas arrancan con Windows?", "quita <programa> del inicio", "plan de energía alto rendimiento",
                    "plan de energía equilibrado", "activa el ahorro de batería", "desactiva el ahorro de batería", "apaga el bluetooth",
                    "activa el bluetooth", "apaga el wifi", "activa el wifi", "modo avión", "desactiva el modo avión", "¿a qué wifi estoy conectado?",
                    "conéctate al wifi <red>", "modo concentración <N> minutos", "termina la concentración", "luz nocturna",
                    "cambia la salida de audio", "modo docente", "modo general", "modo automático", "gasté <monto> en <concepto>",
                    "¿cuánto he gastado este mes?", "recuérdame pagar <cosa> el <día> de cada mes", "¿qué pagos tengo?", "ya pagué <cosa>",
                    "agrega <cosas> a la lista de <lista>", "¿qué hay en la lista de <lista>?", "enciende <aparato de la casa>",
                    "apaga <aparato de la casa>", "cuando conecte el cargador, <orden>", "¿qué disparadores tengo?",
                    "cierra la pestaña del <explorador|Chrome|Edge|Firefox|navegador|terminal>", "abre una pestaña nueva en el <programa>",
                    "sube una carpeta", "nueva carpeta", "vista de detalles", "renombra", "guarda el archivo", "selecciona todo", "copia eso",
                    "pega aquí", "imprime esto", "acerca", "aleja", "zoom normal", "pon la ventana a la izquierda", "pon la ventana a la derecha",
                    "pasa la ventana al otro monitor", "nuevo escritorio virtual", "siguiente escritorio", "vista de tareas",
                    "historial del portapapeles", "recorte de pantalla", "abre el explorador",
                    "activa el control por voz", "desactiva el control por voz")


@skills.skill("orden_asistente", "El PC y el día a día con órdenes de Jarvis: instalar, actualizar o desinstalar programas; qué "
                                 "consume más y cerrarlo; temporales; espacio en disco; programas al inicio; planes de energía y ahorro de "
                                 "batería; wifi, bluetooth y modo avión; concentración; modo docente o general; gastos, pagos y listas; luces y "
                                 "aparatos de la casa; disparadores; pestañas de un programa (explorador, Chrome…), carpetas, ventanas, "
                                 "escritorios virtuales, portapapeles y recortes. Úsala cuando pidan algo de esto con otras palabras.",
              "orden: la orden directa, una de: " + " | ".join(ASSISTANT_ORDERS), windows_only=False)
def assistant_order(orden):
    return assistant_direct(orden)


def assistant_direct(orden):
    """Ejecuta una orden del asistente general sin volver a pasar por la IA (así no hay vueltas). → True si alguien la atendió."""
    from nucleo.diaadia import expense_voice, home_voice, list_voice, payment_voice
    from nucleo.equipopc import pc_voice
    from nucleo.ventanaactiva import window_voice
    text = str(orden or "").strip()
    t = J.normalize(text)
    for fn in (mode_voice, trigger_voice, payment_voice, expense_voice, list_voice, pc_voice, window_voice, home_voice):
        if fn(text, t):
            return True
    J.reply(f"No supe cómo hacer «{text}». Prueba con la orden directa, por ejemplo «instala VLC» o «limpia los temporales».", "PC")
    return False


@J.socketio.on("assistant_rules")
def handle_assistant_rules(data=None):
    d = data or {}
    if d.get("action") == "borrar":
        vidadiaria.remove_trigger(str(d.get("n") or ""))
    elif d.get("action") == "crear":
        tr = vidadiaria.parse_trigger(str(d.get("texto") or ""))
        if not tr or not vidadiaria.add_trigger(tr):
            return {"ok": False, "error": "No entendí la regla. Ejemplo: «cuando conecte el cargador, modo general».",
                    "items": [vidadiaria.describe(x) for x in vidadiaria.data["disparadores"]]}
    return {"ok": True, "items": [vidadiaria.describe(x) for x in vidadiaria.data["disparadores"]], **mode_info()}


__all__ = ['MODE_LABEL', '_MODE_ASK', '_MODE_SET', '_TRIG_DEL', '_TRIG_LIST', '_mode_changed', '_mode_worker', '_proc_names', '_run_trigger',
           '_tick', 'ASSISTANT_ORDERS', 'assistant_direct', 'assistant_order', 'current_mode', 'handle_assistant_mode', 'handle_assistant_rules', 'mode_info', 'mode_rule', 'mode_state', 'mode_voice',
           'modes_start', 'set_mode', 'trigger_voice', 'wifi_now']
