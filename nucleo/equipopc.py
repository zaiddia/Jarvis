"""12.9: el PC, con órdenes del sistema (sin mover el mouse ni teclear por ti). Lo delicado pide tu «sí».

- Programas (winget): «instala VLC», «¿qué programas tienen actualización?», «actualiza todos mis programas»,
  «desinstala Zoom».
- Mantenimiento: «¿qué está poniendo lento el PC?», «cierra el que más consume», «limpia los temporales»,
  «¿cuánto espacio tengo?», «¿qué programas arrancan con Windows?», «quita Spotify del inicio».
- Energía y conexiones: «plan de energía alto rendimiento», «activa el ahorro de batería», «apaga el bluetooth»,
  «activa el wifi», «modo avión», «¿a qué wifi estoy conectado?», «conéctate al wifi Casa», «luz nocturna»,
  «cambia la salida de audio».
- Concentración: «modo concentración 25 minutos» (No molestar, minimiza lo que distrae y avisa al terminar).
La lógica pura está en equipo.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import ctypes
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time

import equipo
import skills
from nucleo import J

_NOWIN = 0x08000000
_JARVIS_PARTS = r"(?:ollama|kokoro|piper|whisper|la ia|ia\b|la inteligencia|inteligencia|la voz|voz|vision|visión|el motor|motor|modelo|componente|jarvis|la habilidad|habilidad|el conector|conector|extension|plugin"
pc_state = {"focus_until": 0.0, "focus_timer": None, "minimized": []}


def _pc_run(args, timeout=60):
    """Un comando del sistema sin ventana. → (código, salida)."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=_NOWIN if J.IS_WIN else 0,
                           encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return 127, "no está instalado"
    except subprocess.TimeoutExpired:
        return 124, "tardó demasiado"


def _pc_ps(script, timeout=40):
    return _pc_run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script], timeout)


def _need_win(origin="PC"):
    if not J.IS_WIN:
        J.reply("Eso solo lo puedo hacer en Windows.", origin)
        return False
    return True


def _winget_ok():
    return bool(shutil.which("winget"))


# ============================================================================ PROGRAMAS (winget)
_INSTALL = re.compile(r"^(?:jarvis\s+)?(?:instala(?:me)?|instalame|descarga e instala|baja e instala)\s+(?:el programa\s+|la aplicacion\s+|la app\s+|el\s+|la\s+)?(.+)$")
_UNINSTALL = re.compile(r"^(?:jarvis\s+)?(?:desinstala(?:me)?|quita el programa|borra el programa|elimina el programa)\s+(?:el programa\s+|la aplicacion\s+|el\s+|la\s+)?(.+)$")
_UPG_ASK = re.compile(r"\b(?:que|cuales) (?:programas|aplicaciones) (?:tienen|necesitan|hay para) (?:actualizacion|actualizar|actualizaciones)\b|"
                      r"\bhay actualizaciones de (?:programas|aplicaciones|mis programas)\b|\bprogramas (?:desactualizados|por actualizar)\b")
_UPG_ALL = re.compile(r"\bactualiza(?:me)? (?:todos )?(?:mis|los|todas las|mis aplicaciones|las aplicaciones|todos los) ?(?:programas|aplicaciones|apps)\b")
_UPG_ONE = re.compile(r"^(?:jarvis\s+)?actualiza(?:me)?\s+(?:el programa|la aplicacion|la app)\s+(.+)$")


def _install(name, origin="PROGRAMAS"):
    if not _winget_ok():
        J.reply("Para instalar programas necesito winget («Instalador de aplicaciones» de la Microsoft Store). Te abro la tienda para "
                "instalarlo.", origin)
        try:
            os.startfile("ms-windows-store://pdp/?productid=9NBLGGH4NNS1")
        except OSError:
            pass
        return
    J.reply(f"Busco «{name}» en el catálogo de Windows…", origin)

    def work():
        _c, out = _pc_run(equipo.winget_search(name), 60)
        rows = equipo.parse_table(out)
        pkg = equipo.best_package(rows, name)
        if not pkg:
            sug = ", ".join(r["name"] for r in rows[:4])
            J.notify(f"No encontré «{name}»." + (f" Hay: {sug}. Dime el nombre exacto." if sug else ""), origin)
            return

        def go():
            def inst():
                code, out2 = _pc_run(equipo.winget_install(pkg["id"]), 1800)
                ok = code == 0 or re.search(r"(?:instalado correctamente|successfully installed|ya est[aá] instalado|already installed)", out2, re.I)
                J.notify(f"Listo: instalé {pkg['name']}." if ok else f"No se pudo instalar {pkg['name']} ({out2.strip().splitlines()[-1][:120] if out2.strip() else code}).",
                         origin)
            J.start_job(f"Instalando {pkg['name']}", inst, "winget")
        J.request_approval("instalar", f"Instalar {pkg['name']}", f"{pkg['id']} {pkg['version']} · del catálogo oficial de Windows (winget).",
                           on_ok=go, on_no=lambda: None, ttl=900, say=f"Encontré {pkg['name']}. ¿Lo instalo? Di «sí» o «no».")
    J.start_job(f"Buscando {name}", work, "winget-buscar")


def _upgrades():
    _c, out = _pc_run(equipo.winget_upgrades(), 90)
    return [r for r in equipo.parse_table(out) if r["available"]]


def _ask_upgrades(origin="PROGRAMAS", do_all=False):
    if not _winget_ok():
        J.reply("Para actualizar programas necesito winget («Instalador de aplicaciones» de la Microsoft Store).", origin)
        return
    J.reply("Reviso qué programas tienen versión nueva…", origin)

    def work():
        rows = _upgrades()
        if not rows:
            J.notify("Todos tus programas están al día.", origin)
            return
        names = ", ".join(f"{r['name']} ({r['version']} → {r['available']})" for r in rows[:12])
        if not do_all:
            J.notify(f"{len(rows)} programa{'s tienen' if len(rows) != 1 else ' tiene'} versión nueva: {names}. Di «actualiza todos mis programas».",
                     origin)
            return

        def go():
            def upd():
                code, out = _pc_run(equipo.winget_upgrade_all(), 3600)
                left = _upgrades()
                J.notify(f"Actualicé {len(rows) - len(left)} de {len(rows)} programas." + (f" Quedaron pendientes: {', '.join(r['name'] for r in left[:6])} "
                                                                                            "(algunos se actualizan solos al cerrarlos)." if left else ""), origin)
            J.start_job("Actualizando programas", upd, "winget")
        J.request_approval("instalar", f"Actualizar {len(rows)} programa{'s' if len(rows) != 1 else ''}", names, on_ok=go, on_no=lambda: None,
                           ttl=900, say=f"Hay {len(rows)} programas con versión nueva. ¿Los actualizo? Di «sí» o «no».")
    J.start_job("Buscando actualizaciones", work, "winget-buscar")


def _uninstall(name, origin="PROGRAMAS"):
    if not _winget_ok():
        J.reply("Para desinstalar necesito winget. Mientras tanto te abro Aplicaciones instaladas.", origin)
        try:
            os.startfile("ms-settings:appsfeatures")
        except OSError:
            pass
        return

    def work():
        _c, out = _pc_run(equipo.winget_list(name), 60)
        pkg = equipo.best_package(equipo.parse_table(out), name)
        if not pkg:
            J.notify(f"No encontré «{name}» entre tus programas instalados.", origin)
            return

        def go():
            def un():
                code, out2 = _pc_run(equipo.winget_uninstall(pkg["id"]), 900)
                J.notify(f"Desinstalé {pkg['name']}." if code == 0 else f"No pude desinstalar {pkg['name']}: {out2.strip()[-120:]}", origin)
            J.start_job(f"Desinstalando {pkg['name']}", un, "winget")
        J.request_approval("instalar", f"Desinstalar {pkg['name']}", f"{pkg['id']} {pkg['version']}. Tus archivos no se borran.", on_ok=go,
                           on_no=lambda: None, ttl=600, say=f"¿Desinstalo {pkg['name']}? Di «sí» o «no».")
    J.start_job(f"Buscando {name}", work, "winget-buscar")


# ============================================================================ MANTENIMIENTO
def heavy_processes(n=5):
    if J.psutil is None:
        return []
    procs = list(J.psutil.process_iter(["name", "memory_info"]))
    for p in procs:
        try:
            p.cpu_percent(None)
        except Exception:
            pass
    time.sleep(0.6)
    rows = []
    for p in procs:
        try:
            rows.append({"name": p.info["name"], "rss": p.info["memory_info"].rss if p.info["memory_info"] else 0, "cpu": p.cpu_percent(None)})
        except Exception:
            pass
    ncpu = J.psutil.cpu_count() or 1
    for r in rows:
        r["cpu"] = r["cpu"] / ncpu
    return [r for r in equipo.top_processes(rows, n + 4) if equipo.can_close(r["name"])][:n]


def _slow_report(origin="PC"):
    rows = heavy_processes(4)
    if not rows:
        J.reply("No pude leer los procesos del equipo.", origin)
        return
    vm = J.psutil.virtual_memory()
    parts = [f"{equipo.friendly(r['name'])}: {equipo.gb(r['rss'])} de memoria" + (f" y {r['cpu']:.0f} % del procesador" if r["cpu"] >= 2 else "")
             for r in rows]
    J.reply(f"Memoria usada: {vm.percent:.0f} %. Lo que más consume: " + "; ".join(parts) + ". Si quieres, di «cierra el que más consume».", origin)
    J.card("equipo", "Lo que más consume", "\n".join(parts), "⚙", secs=14)


def _kill(name, origin="PC"):
    if J.psutil is None:
        return
    procs = [p for p in J.psutil.process_iter(["name"]) if str(p.info["name"]).lower() == name.lower()]
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    J.reply(f"Cerré {equipo.friendly(name)}." if procs else f"{equipo.friendly(name)} ya no estaba abierto.", origin)


def _kill_heaviest(origin="PC"):
    rows = heavy_processes(1)
    if not rows:
        J.reply("No encontré nada que valga la pena cerrar.", origin)
        return
    r = rows[0]
    J.request_approval("sistema", f"Cerrar {equipo.friendly(r['name'])}", f"Usa {equipo.gb(r['rss'])} de memoria. Si tiene algo sin guardar, se pierde.",
                       on_ok=lambda: _kill(r["name"], origin), on_no=lambda: None, ttl=300,
                       say=f"Lo que más consume es {equipo.friendly(r['name'])}. ¿Lo cierro? Si tiene algo sin guardar se pierde. Di «sí» o «no».")


def _temp_dirs():
    dirs = [tempfile.gettempdir()]
    win = os.environ.get("WINDIR")
    if win:
        dirs.append(os.path.join(win, "Temp"))
    return [d for d in dict.fromkeys(dirs) if os.path.isdir(d)]


def _clean_temp(origin="PC"):
    files, total = equipo.temp_candidates(_temp_dirs())
    if total < 20e6:
        J.reply(f"Los temporales ocupan poco ({equipo.gb(total)}): no hace falta limpiar.", origin)
        return

    def go():
        def work():
            freed = 0
            for p in files:
                try:
                    sz = os.path.getsize(p)
                    os.remove(p)
                    freed += sz
                except OSError:
                    pass
            J.notify(f"Liberé {equipo.gb(freed)} de archivos temporales." + (" Algunos estaban en uso y los dejé." if freed < total * 0.9 else ""),
                     origin)
        J.start_job("Limpiando temporales", work, "temporales")
    J.request_approval("sistema", f"Borrar temporales ({equipo.gb(total)})", f"{len(files)} archivos temporales de más de un día. Tus documentos no se tocan.",
                       on_ok=go, on_no=lambda: None, ttl=600, say=f"Puedo liberar {equipo.gb(total)} de temporales. ¿Los borro? Di «sí» o «no».")


def _disk_report(origin="PC"):
    if J.psutil is None:
        return
    parts = []
    for d in J.psutil.disk_partitions(all=False):
        if "cdrom" in d.opts or not d.fstype:
            continue
        try:
            u = J.psutil.disk_usage(d.mountpoint)
        except OSError:
            continue
        parts.append(f"{d.mountpoint.rstrip(chr(92))}: {equipo.gb(u.free)} libres de {equipo.gb(u.total)}")
    J.reply(("Espacio en disco: " + "; ".join(parts) + ".") if parts else "No pude leer los discos.", origin)


def startup_items():
    """[{"nombre","donde","activo","puede"}] de lo que arranca con Windows (de tu usuario y del equipo)."""
    if not J.IS_WIN:
        return []
    import winreg
    out = []

    def approved(hive, key, name):
        try:
            with winreg.OpenKey(hive, key) as k:
                return equipo.approved_enabled(winreg.QueryValueEx(k, name)[0])
        except OSError:
            return True
    for hive, scope in ((winreg.HKEY_CURRENT_USER, "usuario"), (winreg.HKEY_LOCAL_MACHINE, "equipo")):
        try:
            with winreg.OpenKey(hive, equipo.RUN_KEY) as k:
                i = 0
                while True:
                    try:
                        name, _v, _t = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    out.append({"nombre": name, "donde": scope, "activo": approved(hive, equipo.APPROVED_RUN, name), "puede": scope == "usuario"})
                    i += 1
        except OSError:
            pass
    folder = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
    try:
        for f in os.listdir(folder):
            if f.lower() != "desktop.ini":
                out.append({"nombre": f, "donde": "carpeta", "activo": approved(winreg.HKEY_CURRENT_USER, equipo.APPROVED_FOLDER, f), "puede": True})
    except OSError:
        pass
    return out


def set_startup(item, enabled):
    import winreg
    key = equipo.APPROVED_FOLDER if item["donde"] == "carpeta" else equipo.APPROVED_RUN
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
        winreg.SetValueEx(k, item["nombre"], 0, winreg.REG_BINARY, equipo.approved_value(enabled, 0 if enabled else equipo.filetime_now()))


def _startup_find(name):
    n = equipo.norm(name)
    items = startup_items()
    return next((x for x in items if equipo.norm(x["nombre"]) == n), None) or next((x for x in items if n in equipo.norm(x["nombre"])), None)


# ============================================================================ ENERGÍA Y CONEXIONES
def _power_plan(want, origin="PC"):
    _c, out = _pc_run(["powercfg", "/list"], 15)
    plans = equipo.parse_plans(out)
    p = equipo.pick_plan(plans, want)
    if not p:
        J.reply("Tu equipo no tiene ese plan de energía. Tiene: " + ", ".join(x["name"] for x in plans) + "." if plans else
                "No pude leer los planes de energía.", origin)
        return
    code, _o = _pc_run(["powercfg", "/setactive", p["guid"]], 15)
    J.reply(f"Plan de energía: {p['name']}." if code == 0 else "Windows no me dejó cambiar el plan de energía.", origin)


def _battery_saver(on, origin="PC"):
    val = "100" if on else "20"                       # el umbral: al 100 % se activa siempre que estés con batería
    c1, _ = _pc_run(["powercfg", "/setdcvalueindex", "SCHEME_CURRENT", "SUB_ENERGYSAVER", "ESBATTTHRESHOLD", val], 15)
    _pc_run(["powercfg", "/setactive", "SCHEME_CURRENT"], 15)
    if c1 == 0:
        J.reply("Ahorro de batería activado: se aplica mientras estés sin cargador." if on else
                "Ahorro de batería desactivado (vuelve a encenderse solo al 20 %).", origin)
    else:
        J.reply("No pude cambiarlo desde aquí; te abro la configuración de energía.", origin)
        try:
            os.startfile("ms-settings:batterysaver")
        except OSError:
            pass


def _radios(kinds, state, origin="PC"):
    code, out = _pc_ps(equipo.radio_script(kinds, state))
    res = equipo.parse_radios(out)
    if code != 0 or not res:
        J.reply("Windows no me dejó cambiar la conexión; te abro la configuración.", origin)
        try:
            os.startfile("ms-settings:network-airplanemode")
        except OSError:
            pass
        return res
    names = {"WiFi": "Wi-Fi", "Bluetooth": "Bluetooth", "MobileBroadband": "datos móviles"}
    word = {"On": "encendido", "Off": "apagado"}
    J.reply(" · ".join(f"{names.get(k, k)} {word.get(v, v)}" for k, v in res.items()) + ".", origin)
    return res


def _wifi_connect(name, origin="PC"):
    _c, out = _pc_run(["netsh", "wlan", "show", "profiles"], 15)
    profs = equipo.parse_profiles(out)
    hit = next((p for p in profs if equipo.norm(p) == equipo.norm(name)), None) or next((p for p in profs if equipo.norm(name) in equipo.norm(p)), None)
    if not hit:
        J.reply(f"No tengo guardada la red «{name}». Conéctate una vez desde Windows y después lo hago yo." +
                (f" Guardadas: {', '.join(profs[:6])}." if profs else ""), origin)
        return
    code, out = _pc_run(["netsh", "wlan", "connect", f"name={hit}"], 20)
    J.reply(f"Conectándome a «{hit}»…" if code == 0 else f"No pude conectarme a «{hit}».", origin)


# ============================================================================ CONCENTRACIÓN
_DISTRACT_DEFAULT = "youtube, facebook, instagram, tiktok, whatsapp, twitter, netflix, x.com, telegram"


def focus_start(minutes=25, origin="CONCENTRACIÓN"):
    minutes = max(5, min(180, int(minutes)))
    try:
        skills.notifications("silenciar")
    except Exception:
        pass
    words = [w.strip().lower() for w in str(J.settings.get("focus_distractions") or _DISTRACT_DEFAULT).split(",") if w.strip()]
    hidden = []
    if J.IS_WIN:
        for w in skills.list_windows():
            title = (w["title"] + " " + w["proc"]).lower()
            if any(x in title for x in words):
                try:
                    ctypes.windll.user32.ShowWindow(w["hwnd"], 6)       # minimizar (no se cierra nada)
                    hidden.append(w["title"][:40])
                except Exception:
                    pass
    pc_state.update(focus_until=time.time() + minutes * 60, minimized=hidden)
    if pc_state["focus_timer"]:
        pc_state["focus_timer"].cancel()
    t = threading.Timer(minutes * 60, focus_end, kwargs={"done": True})
    t.daemon = True
    t.start()
    pc_state["focus_timer"] = t
    try:
        J.add_timer(minutes * 60, "Concentración")
    except Exception:
        pass
    J.reply(f"Modo concentración por {minutes} minutos: silencié las notificaciones" + (f" y minimicé {len(hidden)} ventana{'s' if len(hidden) != 1 else ''} "
                                                                                        "que distraen" if hidden else "") + ". Te aviso al terminar.", origin)


def focus_end(done=False, origin="CONCENTRACIÓN"):
    if not pc_state["focus_until"]:
        if not done:
            J.reply("No estabas en modo concentración.", origin)
        return
    if pc_state["focus_timer"] and not done:
        pc_state["focus_timer"].cancel()
    pc_state.update(focus_until=0.0, focus_timer=None)
    try:
        skills.notifications("activar")
    except Exception:
        pass
    (J.notify if done else J.reply)("Terminó tu bloque de concentración. ¡Buen trabajo! Descansa 5 minutos; las notificaciones ya volvieron."
                                     if done else "Listo, salí del modo concentración y volví a activar las notificaciones.", origin)


# ============================================================================ ÓRDENES
_SLOW = re.compile(r"\bque (?:esta|me esta|lo esta|anda) (?:poniendo|haciendo) lento\b|\bpor que (?:esta|anda|va) (?:tan )?lento (?:el|mi) "
                   r"(?:pc|computador|portatil|equipo|computadora)\b|\bque (?:programa |proceso )?(?:esta )?consum(?:e|iendo) (?:mas|tanta) "
                   r"(?:memoria|ram|procesador|cpu|bateria)\b|\bque es lo que mas consume\b|\bque (?:programa |proceso )?(?:esta|me esta) "
                   r"(?:consumiendo|gastando|usando) (?:la |el |tanta |tanto |mucha |mucho )?(?:memoria|ram|procesador|cpu|bateria)\b|"
                   r"\bque (?:programa|proceso) (?:consume|gasta|usa) mas\b|\b(?:el|mi) (?:pc|computador|portatil|equipo) (?:esta|anda|va) (?:muy |super )?lento\b")
_KILL_TOP = re.compile(r"\bcierra (?:el|lo) que mas (?:consume|gasta|pesa)\b")
_TEMP = re.compile(r"\b(?:limpia|borra|elimina)(?:me)? (?:los |las )?(?:archivos )?temporales\b|\blibera(?:me)? (?:espacio|memoria del disco)\b|"
                   r"\blimpia (?:el|mi) (?:pc|computador|equipo|disco|portatil)\b")
_DISK = re.compile(r"\bcuanto espacio (?:libre )?(?:tengo|hay|me queda|queda)\b|\bespacio (?:libre )?en (?:el |mi )?disco\b")
_START_ASK = re.compile(r"\bque (?:programas|aplicaciones) (?:arrancan|inician|se abren|se inician|abren) (?:solos? )?(?:con windows|al (?:encender|iniciar|prender))\b|"
                        r"\bprogramas (?:de|del) inicio\b")
_START_OFF = re.compile(r"^(?:jarvis\s+)?(?:quita|saca|desactiva)\s+(?:a\s+)?(.+?)\s+(?:del|al)\s+inicio(?:\s+de windows)?$|^(?:jarvis\s+)?que\s+(.+?)\s+no\s+"
                        r"(?:arranque|inicie|se abra)\s+(?:solo|con windows|al encender)")
_START_ON = re.compile(r"^(?:jarvis\s+)?(?:activa|pon)\s+(?:a\s+)?(.+?)\s+(?:al|en el)\s+inicio(?:\s+de windows)?$|^(?:jarvis\s+)?que\s+(.+?)\s+(?:arranque|inicie)\s+con windows$")
_PLAN = re.compile(r"\b(?:plan de energia|modo|pon el (?:pc|computador|portatil|equipo) en(?: modo)?|pon(?:me)? el plan)\s+(?:de\s+)?(alto rendimiento|maximo rendimiento|"
                   r"rendimiento|equilibrado|balanceado|economizador|ahorro de energia)\b")
_SAVER = re.compile(r"^(?:jarvis\s+)?(activa|enciende|prende|pon|desactiva|apaga|quita)\s+(?:el\s+)?(?:modo\s+)?ahorro de (?:bateria|energia)$")
_RADIO = re.compile(r"^(?:jarvis\s+)?(activa|enciende|prende|conecta|desactiva|apaga|desconecta)\s+(?:el\s+|la\s+)?(wifi|wi fi|bluetooth|datos moviles)$")
_AIRPLANE = re.compile(r"^(?:jarvis\s+)?(?:(activa|pon|enciende|desactiva|quita|apaga)\s+(?:el\s+)?)?modo avion$")
_SSID_ASK = re.compile(r"\b(?:a que|en que|cual) (?:red|wifi|wi fi)\b.*\b(?:conectad[oa]|estoy|estamos)\b|\bque wifi (?:tengo|es este)\b")
_WIFI_JOIN = re.compile(r"^(?:jarvis\s+)?conecta(?:te|me)?\s+(?:a\s+la\s+red|al\s+wifi|al\s+wi\s?fi|a\s+la\s+wifi)\s+(?:de\s+|del\s+)?(.+)$")
_NIGHT = re.compile(r"\b(?:activa|desactiva|enciende|apaga|pon|quita)\s+(?:la\s+)?luz nocturna\b")
_AUDIO_OUT = re.compile(r"\b(?:cambia|pasa(?:lo)?|pon)\s+(?:la\s+)?(?:salida de (?:audio|sonido)|el (?:audio|sonido)\s+(?:a|en)\s+(?:los\s+)?(?:audifonos|parlantes|bafles|"
                        r"bocinas|altavoces|diadema|cascos))\b|\bpasalo a los (?:audifonos|parlantes)\b")
_FOCUS = re.compile(r"^(?:jarvis\s+)?(?:activa\s+(?:el\s+)?)?(?:modo concentracion|quiero concentrarme|bloque de concentracion|modo enfoque|necesito concentrarme)"
                    r"(?:\s+(?:por|de|durante)?\s*(\d{1,3})\s*(?:minutos?|min)?|\s+(?:por|de|durante)?\s*(una|media|1)\s+hora)?$")
_FOCUS_END = re.compile(r"\b(?:termina|terminar|sal del|salir del|sal de la|desactiva|quita|acaba|para|deten)\s+(?:el\s+|la\s+)?(?:modo\s+)?(?:concentracion|enfoque)\b")


def pc_voice(text, t):
    m = _INSTALL.match(t)
    if m and not re.match(_JARVIS_PARTS + r")", m.group(1)) and not re.search(r"\b(?:actualizacion|la nueva version)\b", m.group(1)):
        if _need_win("PROGRAMAS"):
            _install(m.group(1).strip())
        return True
    m = _UNINSTALL.match(t)
    if m:
        if _need_win("PROGRAMAS"):
            _uninstall(m.group(1).strip())
        return True
    if _UPG_ALL.search(t):
        if _need_win("PROGRAMAS"):
            _ask_upgrades(do_all=True)
        return True
    if _UPG_ASK.search(t):
        if _need_win("PROGRAMAS"):
            _ask_upgrades(do_all=False)
        return True
    m = _UPG_ONE.match(t)
    if m:
        if _need_win("PROGRAMAS"):
            name = m.group(1).strip()

            def work():
                pkg = equipo.best_package(_upgrades(), name)
                if not pkg:
                    J.notify(f"{name} ya está al día (o no lo encontré).", "PROGRAMAS")
                    return
                code, _o = _pc_run(equipo.winget_upgrade_one(pkg["id"]), 1800)
                J.notify(f"Actualicé {pkg['name']} a la {pkg['available']}." if code == 0 else f"No pude actualizar {pkg['name']}.", "PROGRAMAS")
            J.start_job(f"Actualizando {name}", work, "winget")
            J.reply(f"Actualizo {name} si tiene versión nueva…", "PROGRAMAS")
        return True
    if _SLOW.search(t):
        _slow_report()
        return True
    if _KILL_TOP.search(t):
        _kill_heaviest()
        return True
    if _TEMP.search(t):
        _clean_temp()
        return True
    if _DISK.search(t):
        _disk_report()
        return True
    if _START_ASK.search(t):
        if _need_win():
            items = startup_items()
            on = [x["nombre"] for x in items if x["activo"]]
            off = [x["nombre"] for x in items if not x["activo"]]
            J.reply((f"Arrancan con Windows: {', '.join(on)}." if on else "Nada arranca solo con Windows.") +
                    (f" Desactivados: {', '.join(off)}." if off else "") + " Para quitar uno: «quita Spotify del inicio».", "PC")
        return True
    m = _START_OFF.match(t) or _START_ON.match(t)
    if m:
        if not _need_win():
            return True
        enable = bool(_START_ON.match(t))
        name = next(g for g in m.groups() if g)
        x = _startup_find(name)
        if not x:
            J.reply(f"«{name}» no está entre los programas que arrancan con Windows.", "PC")
        elif not x["puede"]:
            J.reply(f"{x['nombre']} lo instaló el equipo para todos los usuarios: te abro el Administrador de tareas, pestaña Inicio.", "PC")
            _pc_run(["taskmgr", "/0", "/startup"], 5)
        elif enable:
            set_startup(x, True)
            J.reply(f"Listo: {x['nombre']} volverá a arrancar con Windows.", "PC")
        else:
            J.request_approval("sistema", f"Que {x['nombre']} no arranque con Windows", "Se puede volver a activar cuando quieras.",
                               on_ok=lambda: (set_startup(x, False), J.reply(f"Listo: {x['nombre']} ya no arranca con Windows.", "PC")),
                               on_no=lambda: None, ttl=300, say=f"¿Quito {x['nombre']} del inicio de Windows? Di «sí» o «no».")
        return True
    m = _PLAN.search(t)
    if m and _need_win():
        w = m.group(1)
        _power_plan("alto" if "rendimiento" in w else "ahorro" if w in ("economizador", "ahorro de energia") else "equilibrado")
        return True
    m = _SAVER.match(t)
    if m:
        if _need_win():
            _battery_saver(m.group(1) in ("activa", "enciende", "prende", "pon"))
        return True
    m = _RADIO.match(t)
    if m:
        if _need_win():
            kind = {"wifi": "WiFi", "wi fi": "WiFi", "bluetooth": "Bluetooth", "datos moviles": "MobileBroadband"}[m.group(2)]
            on = m.group(1) in ("activa", "enciende", "prende", "conecta")
            if kind == "WiFi" and not on:
                J.reply("Apago el Wi-Fi: sin internet usaré la IA de tu equipo.", "PC")
            _radios([kind], "On" if on else "Off")
        return True
    m = _AIRPLANE.match(t)
    if m:
        if _need_win():
            on = m.group(1) in (None, "activa", "pon", "enciende")
            _radios(["WiFi", "Bluetooth", "MobileBroadband"], "Off" if on else "On")
        return True
    if _SSID_ASK.search(t):
        if _need_win():
            from nucleo.modos import wifi_now
            s = wifi_now(max_age=0)
            J.reply(f"Estás conectado a «{s}»." if s else "No estás conectado a ninguna red Wi-Fi.", "PC")
        return True
    m = _WIFI_JOIN.match(t)
    if m:
        if _need_win():
            _wifi_connect(m.group(1).strip())
        return True
    if _NIGHT.search(t):
        if _need_win():
            J.reply("Windows no deja cambiar la luz nocturna desde fuera: te abro su ajuste, es un solo clic.", "PC")
            try:
                os.startfile("ms-settings:nightlight")
            except OSError:
                pass
        return True
    if _AUDIO_OUT.search(t):
        if _need_win():
            J.reply("Te abro la salida de sonido de Windows: elige ahí los audífonos o los parlantes.", "PC")
            try:
                os.startfile("ms-settings:sound")
            except OSError:
                pass
        return True
    m = _FOCUS.match(t)
    if m and (m.group(1) or m.group(2) or not (J.rutinas.find(t) or J.habilidades.match(text))):   # sin minutos y con tu rutina o habilidad: manda la tuya
        mins = int(m.group(1)) if m.group(1) else (30 if m.group(2) == "media" else 60 if m.group(2) else 25)
        focus_start(mins)
        return True
    if _FOCUS_END.search(t):
        focus_end()
        return True
    return False


__all__ = ['_AIRPLANE', '_AUDIO_OUT', '_DISK', '_FOCUS', '_FOCUS_END', '_INSTALL', '_KILL_TOP', '_NIGHT', '_PLAN', '_RADIO', '_SAVER', '_SLOW',
           '_SSID_ASK', '_START_ASK', '_START_OFF', '_START_ON', '_TEMP', '_UNINSTALL', '_UPG_ALL', '_UPG_ASK', '_UPG_ONE', '_WIFI_JOIN',
           '_clean_temp', '_kill_heaviest', '_pc_ps', '_pc_run',
           'focus_end', 'focus_start', 'heavy_processes', 'pc_state', 'pc_voice', 'set_startup', 'startup_items']
