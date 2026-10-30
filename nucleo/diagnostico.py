"""Prueba completa: revisa todo y dice qué falla y cómo arreglarlo.

Parte de Jarvis (antes dentro de jarvis.py). Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import os
import platform
import rapidez
import re
import threading
import time

from nucleo import J


# =============================================================================
# PRUEBA COMPLETA (6.8): revisa todo lo que necesita Jarvis y dice qué falla y cómo arreglarlo
# =============================================================================
_CHECK_RE = re.compile(r"\b(?:prueba completa|haz (?:una|la) prueba completa|revisa(?:lo)? todo|diagnostico completo|"
                       r"haz un diagnostico|diagnosticate|autodiagnostico|chequeo completo|revisa (?:el sistema|tus sistemas)|"
                       r"comprueba todo|como estan tus sistemas|estado de tus sistemas|revisa que todo funcione|prueba todo)\b")
check_state = {"busy": False, "items": [], "at": ""}


def system_check():
    """Lista de comprobaciones: {"grupo", "estado": ok|aviso|fallo|info, "texto", "arreglo"}."""
    out = []

    def add(grupo, estado, texto, arreglo=""):
        out.append({"grupo": grupo, "estado": estado, "texto": texto, "arreglo": arreglo})

    def ok(grupo, cond, bien, mal, arreglo="", aviso=False):
        add(grupo, "ok" if cond else ("aviso" if aviso else "fallo"), bien if cond else mal, "" if cond else arreglo)

    # --- micrófono y escucha
    G = "Micrófono y escucha"
    mics = []
    try:
        mics = J.list_mics()
    except Exception:
        pass
    ok(G, J.pyaudio is not None, "Hay librería de micrófono (sounddevice o PyAudio).",
       "Falta sounddevice: solo funcionan las órdenes escritas. Vuelve a ejecutar instalar.bat.")
    ok(G, bool(mics), f"Micrófonos encontrados: {len(mics)}.", "No encuentro ningún micrófono conectado.", "ms-settings:sound")
    mic = J.state.get("mic", "off")
    ok(G, mic == "on", "El micrófono está escuchando.",
       "El micrófono está en pausa (bandeja › reanudar, o el botón del HUD)." if mic == "off" else
       "El micrófono dio error al abrirse: ¿lo usa otra aplicación? ¿Windows le da permiso?", "ms-settings:privacy-microphone",
       aviso=(mic == "off"))
    model = J.get_resource_path("model_es")
    ok(G, os.path.isdir(model) or J.settings.get("stt_backend") == "whisper", "El modelo de voz de Vosk está instalado.",
       "Falta el modelo de voz (model_es): ejecuta descargar_modelo.py o instalar.bat.")
    ok(G, bool(J.settings.get("wake_word_enabled", True)), "Responde a «" + ", ".join(J.get_wake_words()[:3]) + "».",
       "La palabra de activación está apagada: tienes que usar Ctrl+Alt+Espacio para hablarle.", aviso=True)

    # --- voz
    G = "Voz"
    ok(G, J.audio_ready, "El audio de salida funciona.", "No pude iniciar el audio de salida (pygame): no podré hablar.")
    backend = J.settings["tts_backend"]
    add(G, "info", {"edge": "Hablo con la voz de Microsoft (Edge, necesita internet).",
                    "piper": "Hablo con Piper (sin internet).",
                    "gemini": "Hablo con la voz de Gemini (necesita internet y tu clave)."}.get(backend, backend))
    piper_ok = bool(J.find_piper_voice())
    ok(G, piper_ok, "Piper está instalado: sin internet también puedo hablar.",
       "Piper no está instalado: sin internet no podré hablar (python descargar_voz.py).", aviso=True)
    rs = rapidez.summary()
    if rs:
        ok(G, rs["total"] <= rapidez.SLOW_TOTAL, f"Respondo en {rs['total']:.1f} s de media (últimas {rs['turnos']}).",
           f"Tardo {rs['total']:.1f} s de media en responder; lo más lento: {rapidez.NAMES.get(rs['lenta'], '?')}.",
           rapidez.TIPS.get(rs["lenta"], ""), aviso=True)

    # --- internet
    G = "Internet"
    t0 = time.time()
    online = J._internet_ok()
    ok(G, online, f"Conectado ({(time.time() - t0) * 1000:.0f} ms).",
       "Sin internet: uso la IA local y Piper si están instalados.", "ms-settings:network", aviso=True)

    # --- inteligencia artificial
    G = "Inteligencia artificial"
    try:
        r = J.ai_test()
        ok(G, r.get("test_ok"), f"{J._ai_cfg()['label']}: {r.get('test_msg', '')}",
           f"{J._ai_cfg()['label']}: {r.get('test_msg', 'no responde')}", "ajustes:ia")
    except Exception as e:
        add(G, "fallo", f"La IA no responde: {getattr(e, 'why', e)}", "ajustes:ia")
    lm = ""
    try:
        lm = J.local_ai_model()
    except Exception:
        pass
    ok(G, bool(lm), f"IA local lista para cuando no haya internet ({lm}).",
       "Sin IA local: si se cae el internet solo funcionarán las órdenes (instala Ollama y «ollama pull llama3.2»).", aviso=True)

    # --- integraciones (solo las configuradas)
    G = "Integraciones"
    if J.settings["telegram_remote"]:
        ok(G, J.tg["ok"], "Telegram conectado: puedes darme órdenes desde el celular.",
           f"Telegram no conecta: {J.tg['error'] or 'revisa el token y el chat id'}.", "ajustes:integraciones")
    if J._cal_urls():
        ok(G, not J.cal_state.get("missing_lib"), "Calendario conectado.",
           "Falta la librería del calendario (icalendar): vuelve a ejecutar instalar.bat.")
    if not J.settings["telegram_remote"] and not J._cal_urls():
        add(G, "info", "Ni Telegram ni calendario configurados (son opcionales).")

    # --- versión
    G = "Versión"
    try:
        info = J.check_updates()
        ok(G, not info.get("newer"), f"Tienes la versión más reciente ({J.VERSION}).",
           f"Hay una versión nueva: la {info.get('version')} (tienes la {J.VERSION}). Di «actualízate».", "actualizar", aviso=True)
    except Exception as e:
        add(G, "info", f"Versión {J.VERSION}. No pude consultar si hay una nueva: {e}")

    # --- equipo
    G = "Equipo"
    ok(G, "onedrive" not in J.APP_DIR.lower(), "Jarvis no está dentro de OneDrive.",
       "Jarvis está dentro de OneDrive: la sincronización lo vuelve lento. Muévelo a C:\\Jarvis.", aviso=True)
    if J.autostart_supported():
        add(G, "info", "Arranca con Windows." if J.autostart_enabled() else "No arranca con Windows (Ajustes › General).")
    add(G, "info", f"Jarvis {J.VERSION} · Python {platform.python_version()} · registro en {J.LOG_PATH}")
    return out


def check_summary(items):
    bad = [i for i in items if i["estado"] == "fallo"]
    warn = [i for i in items if i["estado"] == "aviso"]
    if not bad and not warn:
        return "Prueba completa: todo en orden."
    if bad:
        return (f"Encontré {'un problema' if len(bad) == 1 else f'{len(bad)} problemas'}. {bad[0]['texto']}"
                + (" Los demás están en Ajustes, sección Acerca de." if len(bad) > 1 else ""))
    return f"Todo funciona, con {'un aviso' if len(warn) == 1 else f'{len(warn)} avisos'}: {warn[0]['texto']}"


def check_report(items):
    marks = {"ok": "✅", "aviso": "⚠️", "fallo": "❌", "info": "•"}
    lines, g = [f"Prueba completa de Jarvis {J.VERSION} — {datetime.datetime.now():%Y-%m-%d %H:%M}"], ""
    for i in items:
        if i["grupo"] != g:
            g = i["grupo"]
            lines.append(f"\n{g}")
        lines.append(f"{marks.get(i['estado'], '•')} {i['texto']}")
    return "\n".join(lines)


def run_system_check(speak_it=True):
    if J.check_state["busy"]:
        return J.check_state["items"]
    J.check_state["busy"] = True
    try:
        items = J.system_check()
        J.check_state.update(items=items, at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        for i in items:
            if i["estado"] in ("fallo", "aviso"):
                J.log_terminal(i["texto"], "PRUEBA")
        J.socketio.emit("system_check", {"items": items, "at": J.check_state["at"]})
        if speak_it:
            J.reply(J.check_summary(items), "PRUEBA")
        return items
    finally:
        J.check_state["busy"] = False


def show_system_check():
    J.reply("Hago una prueba completa de mis sistemas. Tarda unos segundos.", "PRUEBA")
    threading.Thread(target=J.run_system_check, daemon=True, name="prueba-completa").start()


# Peticiones con forma de pregunta: «¿puedes subir el volumen?», «¿me abres la calculadora?», «¿me pones música?».
# Antes, por el signo de interrogación, iban a la IA como pregunta: contestaba, pero no hacía nada.


__all__ = [
    '_CHECK_RE',
    'check_report',
    'check_state',
    'check_summary',
    'run_system_check',
    'show_system_check',
    'system_check',
]
