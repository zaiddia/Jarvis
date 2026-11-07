"""12.8: panel de salud de Jarvis. En una sola pantalla: qué funciona, qué falta y cómo arreglarlo (con botón), las
copias de seguridad, la IA local, los errores recientes, el equipo y las actualizaciones. Se actualiza solo.

«Jarvis, abre el panel de salud» · «¿cómo está tu salud?». La prueba completa (diagnostico.py) se lanza desde el panel.
Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import os
import re
import shutil
import threading
import time

import errores
import rapidez
import respaldo
from nucleo import J

_HEALTH_RE = re.compile(r"\b(?:panel|tablero|pantalla) de (?:salud|estado)\b|\bsalud de jarvis\b|\bcomo esta tu salud\b|"
                        r"\b(?:abre|muestra|muestrame|ensename)\s+(?:tu|la)\s+salud\b")
_HP_START = time.time()


def _hp_ago(iso):
    """«hace 3 h», «hace 2 días»… a partir de una fecha ISO."""
    try:
        d = datetime.datetime.fromisoformat(str(iso)[:19])
    except ValueError:
        return ""
    s = (datetime.datetime.now() - d).total_seconds()
    if s < 90:
        return "hace un momento"
    if s < 3600:
        return f"hace {int(s // 60)} min"
    if s < 86400 * 2:
        return f"hace {int(s // 3600)} h"
    return f"hace {int(s // 86400)} días"


def _hp_hours(iso):
    try:
        return (datetime.datetime.now() - datetime.datetime.fromisoformat(str(iso)[:19])).total_seconds() / 3600
    except ValueError:
        return None


def _hp_score(cards):
    """0–100: cada tarjeta suma según su estado (las informativas no cuentan)."""
    pts = {"ok": 1.0, "aviso": 0.55, "fallo": 0.0}
    rated = [c for c in cards if c["estado"] in pts]
    return round(100 * sum(pts[c["estado"]] for c in rated) / len(rated)) if rated else 100


def health_snapshot():
    """Las tarjetas del panel (rápido: no prueba la IA ni internet; eso lo hace la prueba completa)."""
    cards = []

    def card(cid, titulo, estado, valor, detalle="", accion=None):
        cards.append({"id": cid, "titulo": titulo, "estado": estado, "valor": valor, "detalle": detalle, "accion": accion})

    # --- IA
    try:
        a = J.ai_now()
    except Exception:
        a = {"donde": "ninguna", "texto": "Sin IA"}
    card("ia", "Inteligencia artificial", {"nube": "ok", "local": "ok"}.get(a["donde"], "fallo"), a["texto"],
         ("Sin internet: responde la IA de tu equipo." if a.get("sin_internet") and a["donde"] == "local" else
          "Está en tu equipo: funciona sin internet." if a["donde"] == "local" else
          "Sin internet, responde la IA local." if a.get("respaldo") else "Si se cae el internet no hay IA de respaldo."),
         {"label": "Ajustes de IA", "socket": "open_settings"} if a["donde"] == "ninguna" else None)
    # --- IA local integrada
    try:
        m = J.motor_status()
    except Exception:
        m = {}
    if m.get("modelo"):
        bits = ["encendida" if m.get("corriendo") else "lista (se enciende sola)", "tarjeta gráfica" if m.get("gpu") else "procesador",
                "ve imágenes" if m.get("ve") else "solo texto"]
        card("local", "IA local integrada", "ok", m["modelo"].replace(".gguf", ""), " · ".join(bits),
             None if m.get("ve") else {"label": "Darle visión", "socket": "motor", "data": {"action": "vision"}})
    elif m.get("instalando"):
        card("local", "IA local integrada", "aviso", "Instalando…", m.get("msg", ""))
    else:
        card("local", "IA local integrada", "aviso", "No instalada", "Sin ella, sin internet no hay IA. "
             + (f"Para tu equipo: {m['recomendado'].replace(' (recomendado)', '')} ({m['recomendado_gb']} GB)." if m.get("recomendado") else ""),
             {"label": "Instalar", "socket": "motor", "data": {"action": "instalar"}} if m.get("recomendado") else None)
    # --- voz y micrófono
    mic = J.state.get("mic", "off")
    piper = False
    try:
        piper = bool(J.find_piper_voice())
    except Exception:
        pass
    tts = {"edge": "Voz de Microsoft (con internet)", "piper": "Piper (sin internet)", "gemini": "Voz de Gemini",
           "kokoro": "Kokoro (sin internet)"}.get(J.settings.get("tts_backend"), J.settings.get("tts_backend", ""))
    card("voz", "Voz y micrófono", "ok" if mic == "on" and J.audio_ready else ("fallo" if mic == "error" or not J.audio_ready else "aviso"),
         "No puedo hablar: falló el audio de salida" if not J.audio_ready else
         {"on": "Escuchando", "off": "Micrófono en pausa", "error": "El micrófono falló"}.get(mic, mic), tts
         + (" · Piper listo para sin internet" if piper else " · sin voz de respaldo sin internet"))
    # --- internet y Google
    off = bool(J.net.get("offline"))
    card("red", "Internet", "aviso" if off else "ok", "Sin conexión" if off else "Conectado",
         "Funciono con lo instalado en tu equipo mientras vuelve." if off else "")
    g = False
    try:
        g = bool(J.gdrive_ready())
    except Exception:
        pass
    card("google", "Cuenta de Google", "ok" if g else "info", "Conectada" if g else "No conectada",
         "Drive, Calendar, Classroom y Forms." if g else "Opcional: copias en Drive, Calendar y Classroom.",
         None if g else {"label": "Conectar", "socket": "open_settings"})
    # --- copias de seguridad
    local = []
    try:
        local = respaldo.listing(J.backup_folder())
    except Exception:
        pass
    last_local = local[0]["date"] if local else ""
    ci = J.cloud_info()
    h_cloud = _hp_hours(ci["ultima"]) if ci["ultima"] else None
    if ci["lista"] and h_cloud is not None and h_cloud < 40:
        st, val = "ok", f"En tu Drive, cifrada, {_hp_ago(ci['ultima'])}"
    elif ci["lista"]:
        st, val = "aviso", "La copia de la noche aún no ha subido" if not ci["error"] else "La última copia a Drive falló"
    elif last_local and (_hp_hours(last_local) or 999) < 24 * 8:
        st, val = "aviso", f"Solo en este equipo ({_hp_ago(last_local)})"
    else:
        st, val = "fallo", "Sin copias recientes"
    det = (f"Local: {_hp_ago(last_local)}" if last_local else "Local: ninguna") + " · " + (
        f"Nube: {ci['falta']}" if not ci["lista"] else f"Nube: cada noche desde las {ci['hora']}:00")
    if ci["error"] and st != "ok":
        det += f" · {ci['error']}"
    card("copias", "Copias de seguridad", st, val, det,
         {"label": "Subir copia ahora", "socket": "cloud_backup", "data": {"action": "ahora"}} if ci["lista"] else
         {"label": "Configurar", "socket": "open_settings"})
    # --- datos de estudiantes
    try:
        si = J.students_info()
    except Exception:
        si = {"on": False, "locked": []}
    if si.get("locked"):
        card("datos", "Datos de estudiantes", "fallo", "Bloqueados", "Hay archivos cifrados con otra clave: pega la clave de recuperación.",
             {"label": "Abrir Ajustes", "socket": "open_settings"})
    else:
        card("datos", "Datos de estudiantes", "ok" if si.get("on") else "aviso", "Cifrados" if si.get("on") else "Sin cifrar",
             "Notas, observador y asistencia protegidos (Ley 1581)." if si.get("on") else "Son datos de menores: conviene protegerlos.",
             None if si.get("on") else {"label": "Protegerlos", "socket": "students_protect", "data": {"on": True}})
    # --- errores
    errs = []
    try:
        errs = [e for e in errores.recent(80) if (_hp_hours(e.get("t", "")) or 999) < 24 * 7]
    except Exception:
        pass
    card("errores", "Errores (7 días)", "ok" if not errs else ("aviso" if len(errs) < 5 else "fallo"),
         "Ninguno" if not errs else f"{len(errs)} error{'es' if len(errs) != 1 else ''}",
         (f"Último {_hp_ago(errs[-1]['t'])}: {errs[-1].get('origen', '')} · {errs[-1].get('error', '')[:120]}" if errs else "Todo ha ido bien."),
         {"label": "Ver la lista", "socket": "open_settings"} if errs else None)
    # --- equipo
    try:
        free = shutil.disk_usage(J.CONFIG_DIR).free / 1e9
    except OSError:
        free = 0.0
    ram = cpu = None
    if J.psutil is not None:
        try:
            vm = J.psutil.virtual_memory()
            ram = (vm.percent, vm.total / 1e9)
            cpu = J.psutil.cpu_percent(interval=None)
        except Exception:
            pass
    st = "fallo" if free < 1 else ("aviso" if free < 4 or (ram and ram[0] > 92) else "ok")
    card("equipo", "Equipo", st, f"{free:.0f} GB libres" if free >= 1 else f"{free * 1000:.0f} MB libres",
         " · ".join(x for x in [f"Memoria {ram[0]:.0f} % de {ram[1]:.0f} GB" if ram else "", f"Procesador {cpu:.0f} %" if cpu is not None else "",
                                f"Jarvis encendido hace {_hp_ago(datetime.datetime.fromtimestamp(_HP_START).isoformat()).replace('hace ', '')}"] if x))
    # --- rapidez
    rs = None
    try:
        rs = rapidez.summary()
    except Exception:
        pass
    if rs:
        card("rapidez", "Rapidez", "ok" if rs["total"] <= rapidez.SLOW_TOTAL else "aviso", f"{rs['total']:.1f} s por respuesta",
             f"Media de las últimas {rs['turnos']}" + ("" if rs["total"] <= rapidez.SLOW_TOTAL else
                                                       f" · lo más lento: {rapidez.NAMES.get(rs['lenta'], '?')}"))
    # --- versión
    info = J.upd.get("info") or {}
    newer = bool(info.get("newer"))
    try:
        b = J.update_status().get("backup") or {}
    except Exception:
        b = {}
    card("version", "Versión", "aviso" if newer else "ok", f"Jarvis {J.VERSION}",
         (f"Hay una nueva: la {info.get('version')}." if newer else "Al día.")
         + (f" Última actualización: de la {b.get('from')} a la {b.get('to')}, {str(b.get('date', ''))[:10]}." if b.get("to") else ""),
         {"label": "Actualizar", "socket": "open_settings"} if newer else None)
    return {"cards": cards, "score": _hp_score(cards), "at": datetime.datetime.now().strftime("%H:%M:%S"), "version": J.VERSION,
            "check": {"items": J.check_state.get("items") or [], "at": J.check_state.get("at", ""), "busy": J.check_state.get("busy", False)}}


@J.app.route("/salud")
def health_page():
    from flask import render_template
    return render_template("salud.html", version=J.VERSION, asset_v=getattr(J, "ASSET_V", ""))


@J.socketio.on("health_snapshot")
def handle_health_snapshot(data=None):
    return health_snapshot()


@J.socketio.on("health_full")
def handle_health_full(data=None):
    """La prueba completa (prueba la IA, internet y si hay versión nueva); el resultado llega con «system_check»."""
    if not J.check_state["busy"]:
        threading.Thread(target=J.run_system_check, kwargs={"speak_it": False}, daemon=True, name="prueba-panel").start()
    return {"ok": True}


@J.socketio.on("health_fix")
def handle_health_fix(data=None):
    """Arreglos de la prueba completa: una sección de Ajustes o una página de configuración de Windows."""
    target = str((data or {}).get("arreglo") or "")
    if target.startswith("ms-settings:") and J.IS_WIN and re.fullmatch(r"ms-settings:[a-z\-]+", target):
        try:
            os.startfile(target)
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "error": str(e)}
    J.open_settings_window()
    return {"ok": True}


def open_health_panel():
    J.open_window("/salud", "Salud de Jarvis")


@J.socketio.on("open_health")
def handle_open_health(data=None):
    open_health_panel()
    return {"ok": True}


def health_panel_voice(text, t):
    if not _HEALTH_RE.search(t):
        return False
    open_health_panel()
    snap = health_snapshot()
    bad = [c for c in snap["cards"] if c["estado"] == "fallo"]
    warn = [c for c in snap["cards"] if c["estado"] == "aviso"]
    J.reply(f"Te abrí el panel de salud: {snap['score']} de 100. "
            + (f"Lo urgente: {bad[0]['titulo'].lower()}, {bad[0]['valor'].lower()}." if bad else
               f"Todo funciona; {'un aviso' if len(warn) == 1 else f'{len(warn)} avisos'}: {warn[0]['titulo'].lower()}." if warn else
               "Todo en orden."), "SALUD")
    return True


__all__ = ['_HEALTH_RE', 'handle_health_fix', 'handle_open_health', 'handle_health_full', 'handle_health_snapshot', 'health_page', 'health_panel_voice',
           'health_snapshot', 'open_health_panel']
