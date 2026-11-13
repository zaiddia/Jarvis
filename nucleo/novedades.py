"""12.22: video dentro del HUD, búsqueda por modos, pulsar para hablar y el reporte de la mañana aunque abras tarde.

- «pon el video de las fracciones equivalentes», «pon el video https://youtu.be/…», «quita el video».
  Se ve dentro del HUD. Mientras suena, el micrófono no escucha (para que el video no dé órdenes).
- «busca el precio de un portátil Lenovo IdeaPad», «compara el iPhone 16 con el Galaxy S25».
- Pulsar para hablar: el botón del HUD escucha solo mientras lo mantienes (sin decir «Jarvis»).
- Si abres Jarvis después de la hora del reporte de la mañana, te lo da al abrir (una vez al día, hasta el mediodía).
  «dame el resumen de la mañana» lo repite cuando quieras.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import re
import threading
import time
import urllib.parse
import urllib.request

import buscar
from nucleo import J

# ============================================================================ VIDEO EN EL HUD
video = {"id": "", "title": "", "ping": 0.0}
_VID_URL = re.compile(r"(?:youtube\.com/(?:watch\?[^\s]*?v=|shorts/|live/|embed/)|youtu\.be/)([\w-]{11})", re.I)
_VID_ON = re.compile(r"^(?:jarvis\s+)?(?:pon|ponme|ponnos|reproduce|reproduceme|muestra|muestrame|muestranos|proyecta|quiero ver)\s+(?:el\s+|un\s+|este\s+|ese\s+)?video\b\s*"
                     r"(?:de\s+|del\s+|sobre\s+|acerca de\s+|que explica\s+|:)?\s*(.*)$")
_VID_OFF = re.compile(r"\b(?:quita|cierra|para|deten|apaga|termina)\s+(?:el\s+|ese\s+)?video\b")


def video_find(query):
    """Primer video de YouTube para esa búsqueda. → (id, título) o ("", "")."""
    req = urllib.request.Request("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query),
                                 headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "es"})
    with urllib.request.urlopen(req, timeout=8) as r:
        page = r.read().decode("utf-8", "ignore")
    m = re.search(r'"videoRenderer":\{"videoId":"([\w-]{11})".{0,1500}?"title":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"', page, re.S)
    if m:
        title = m.group(2).encode("utf-8").decode("unicode_escape", "ignore") if "\\u" in m.group(2) else m.group(2).replace('\\"', '"')
        return m.group(1), title[:120]
    m = re.search(r'"videoId":"([\w-]{11})"', page)
    return (m.group(1), "") if m else ("", "")


def video_show(vid, title=""):
    video.update(id=vid, title=title, ping=time.time())
    J.hud_show()
    J.socketio.emit("hud_video", {"id": vid, "title": title, "mute": bool(J.settings.get("video_mute_mic", True))})


def video_close(tell=True):
    was = bool(video["id"])
    video.update(id="", title="", ping=0.0)
    if tell:
        J.socketio.emit("hud_video", {"id": ""})
    return was


def video_mic_muted():
    """¿El micrófono está en silencio por el video? Solo mientras el HUD confirma que sigue abierto (si el HUD se
    cierra o se cuelga, a los 40 s el micrófono vuelve solo)."""
    return bool(video["id"]) and J.settings.get("video_mute_mic", True) and time.time() - video["ping"] < 40


@J.socketio.on("video_ping")
def handle_video_ping(data=None):
    if video["id"]:
        video["ping"] = time.time()
    return {"on": bool(video["id"])}


@J.socketio.on("video_closed")
def handle_video_closed(data=None):
    if J.video_close(tell=False):
        J.log_terminal("Video cerrado: el micrófono vuelve a escuchar.", "VIDEO")
    return {"ok": True}


def hudvideo_voice(text, t):
    if _VID_OFF.search(t) and (video["id"] or len(t.split()) <= 5):
        J.reply("Listo, quité el video." if J.video_close() else "No hay ningún video puesto.", "VIDEO")
        return True
    m = _VID_ON.match(t)
    if not m:
        return False
    if re.search(r"\b(?:en youtube|en el navegador|en la pestana|resume|resumen)\b", t):
        return False                                   # «pon X en YouTube» sigue abriendo el navegador
    u = _VID_URL.search(text)
    if u:
        J.video_show(u.group(1))
        J.reply("Ahí está el video, en el HUD." + (" El micrófono queda en pausa mientras suena; ciérralo con la ✕ o Esc." if J.settings.get("video_mute_mic", True) else ""), "VIDEO")
        return True
    q = (m.group(1) or "").strip(" .")
    if not q:
        J.reply("¿Qué video pongo? Di, por ejemplo, «pon el video de fracciones equivalentes» o pega el enlace.", "VIDEO")
        return True
    if J.is_offline():
        J.reply("Para poner un video necesito internet, y ahora no hay.", "VIDEO")
        return True
    raw = re.search(r"\bvideo\b\s*(?:de\s+|del\s+|sobre\s+|acerca de\s+|que explica\s+|:)?\s*(.+)$", text.strip().rstrip(".?!"), re.I)
    query = raw.group(1).strip() if raw else q

    def go():
        try:
            vid, title = J.video_find(query)
        except Exception as e:
            J.log_terminal(f"Video: {e}", "AVISO")
            vid, title = "", ""
        if not vid:
            J.reply(f"No encontré un video de «{query}». Prueba con otras palabras o pega el enlace.", "VIDEO")
            return
        J.video_show(vid, title)
        J.reply((f"Puse «{title}»." if title else f"Puse un video de {query}.") +
                (" El micrófono queda en pausa mientras suena; ciérralo con la ✕ o Esc." if J.settings.get("video_mute_mic", True) else ""), "VIDEO")
    J.reply(f"Busco un video de {query}…", "VIDEO")
    if J.net["watch"]:
        J.start_job("Buscando el video", go, name="video-hud")
    return True


# ============================================================================ BÚSQUEDA POR MODOS
_NOT_WEB = re.compile(r"\b(?:notas?|cursos?|grados?|estudiantes?|periodos?|grupos?|asistencia|archivos?|documentos?|pdfs?|hojas?|listas?|"
                      r"clases?|examen(?:es)?|quiz|tareas?|planeacion(?:es)?|dolar|euro|bitcoin|\d{1,2}\s?[a-d])\b")
_PRICE = re.compile(r"^(?:jarvis\s+)?(?:busca(?:me)?|averigua(?:me)?|consulta(?:me)?|dime|investiga)\s+(?:el\s+|los\s+)?precios?\s+(?:de\s+|del\s+)(?:un\s+|una\s+|el\s+|la\s+|los\s+|las\s+)?(.+?)\s*$|"
                    r"^(?:jarvis\s+)?(?:cuanto (?:cuesta|vale|cuestan|valen)|que precio tiene|en cuanto (?:esta|sale))\s+(?:un\s+|una\s+|el\s+|la\s+|los\s+|las\s+)?(.+?)\s*$")
_COMPARE = re.compile(r"^(?:jarvis\s+)?compara(?:me)?\s+(?:el\s+|la\s+|los\s+|las\s+|un\s+|una\s+)?(.+?)\s+(?:con|contra|vs|versus|frente a)\s+(?:el\s+|la\s+|los\s+|las\s+|un\s+|una\s+)?(.+?)\s*$")


def _raw_tail(text, n_words):
    """Las últimas n palabras del texto original (con tildes y mayúsculas)."""
    words = text.strip().rstrip(".?!").split()
    return " ".join(words[-n_words:]) if 0 < n_words <= len(words) else ""


def _web_results(query):
    results = []
    for lite in (False, True):
        try:
            results = buscar.parse_results(J._get_text(buscar.search_url(query, lite=lite), timeout=12))
        except Exception as e:
            J.log_terminal(f"Búsqueda web: {e}", "AVISO")
        if results:
            break
    return results


def _mode_answer(origin, results, prompt, plain):
    if not results:
        J.reply("No pude buscar en internet en este momento. Inténtalo de nuevo en un momento.", origin)
        return
    try:
        ans = J.ai_chat([{"role": "user", "content": prompt}], max_tokens=600).strip()
    except Exception:
        ans = ""
    J.reply(ans or plain, origin)
    fuentes = buscar.sources(results)
    if fuentes:
        J.log_terminal("Fuentes: " + " · ".join(f"{s['titulo']} ({s['fuente']})" for s in fuentes), origin)


def price_search(item):
    results = J._web_results(buscar.price_query(item))
    J._mode_answer("PRECIOS", results, buscar.price_prompt(item, results), buscar.spoken_fallback(f"el precio de {item}", results))


def compare_search(a, b):
    results = J._web_results(buscar.compare_query(a, b))
    if len(results) < 3:
        results += [r for r in J._web_results(f"{a} o {b} cuál es mejor") if r["url"] not in {x["url"] for x in results}]
    J._mode_answer("COMPARAR", results[:8], buscar.compare_prompt(a, b, results[:8]), buscar.spoken_fallback(f"{a} frente a {b}", results))


def search_modes_voice(text, t):
    m = _PRICE.match(t)
    if m and not _NOT_WEB.search(t):
        item_n = (m.group(1) or m.group(2)).strip()
        item = _raw_tail(text, len(item_n.split())) or item_n
        if len(item_n) < 3 or len(item_n.split()) > 12:
            return False
        if J.is_offline():
            J.reply("Para buscar precios necesito internet, y ahora no hay.", "PRECIOS")
            return True
        J.reply(f"Busco precios de {item}…", "PRECIOS")
        if J.net["watch"]:
            J.start_job("Buscando precios", lambda: J.price_search(item), name="precios")
        return True
    m = _COMPARE.match(t)
    if m and not _NOT_WEB.search(t):
        a, b = m.group(1).strip(), m.group(2).strip()
        if min(len(a), len(b)) < 2 or len(t.split()) > 18:
            return False
        if J.is_offline():
            J.reply("Para comparar necesito buscar en internet, y ahora no hay.", "COMPARAR")
            return True
        J.reply(f"Comparo {a} con {b}; busco en internet…", "COMPARAR")
        if J.net["watch"]:
            J.start_job("Comparando", lambda: J.compare_search(a, b), name="comparar")
        return True
    return False


# ============================================================================ PULSAR PARA HABLAR
ptt = {"on": False}
PTT_HOLD = 30          # mientras lo mantienes, el HUD renueva la escucha cada pocos segundos
PTT_GRACE = 2.5        # al soltar: margen para que termine de reconocer lo último que dijiste


def ptt_set(down):
    """Botón «mantén para hablar» del HUD. Usa la escucha de siempre: solo abre y cierra la ventana en la que lo que
    digas cuenta como orden, sin tener que decir «Jarvis»."""
    if not J.settings["mic_enabled"]:
        return {"ok": False, "msg": "El micrófono está en pausa: actívalo primero."}
    if J.video_mic_muted():
        return {"ok": False, "msg": "El micrófono está en pausa por el video: ciérralo primero."}
    if down:
        first = not ptt["on"]
        ptt["on"] = True
        J.wake_until = time.time() + PTT_HOLD
        J.convo["kind"] = "wake"
        if first:
            try:
                J.stop_speech(log=False)               # si Jarvis estaba hablando, se calla para oírte
            except Exception:
                pass
        J.refresh_mode()
    else:
        ptt["on"] = False
        J.wake_until = min(J.wake_until, time.time() + PTT_GRACE)
        threading.Timer(PTT_GRACE + 0.1, J.refresh_mode).start()
    return {"ok": True}


@J.socketio.on("ptt")
def handle_ptt(data=None):
    return J.ptt_set(bool((data or {}).get("down")))


# ============================================================================ REPORTE DE LA MAÑANA AUNQUE ABRAS TARDE
def brief_catchup_due(now, enabled, morning_time, done):
    """¿Toca dar el reporte al abrir? Sí cuando ya pasó su hora, aún es de mañana y hoy no se ha dado.
    done: fechas (AAAA-MM-DD) en que ya hubo reporte o saludo."""
    if not enabled or now.date().isoformat() in done:
        return False
    m = re.match(r"^(\d{1,2}):(\d{2})$", str(morning_time or "").strip())
    if not m:
        return False
    at = now.replace(hour=min(int(m.group(1)), 23), minute=min(int(m.group(2)), 59), second=0, microsecond=0)
    return at <= now and now.hour < 12


def _brief_catchup():
    time.sleep(40)                                     # deja que carguen la voz, la red y la agenda
    try:
        st = J._upd_load()
        now = datetime.datetime.now()
        if not J.brief_catchup_due(now, J.settings["morning_enabled"] and J.settings.get("morning_catchup", True),
                                   J.settings["morning_time"], (st.get("reporte"), st.get("saludo"))):
            return
        J._upd_save(reporte=now.date().isoformat(), saludo=now.date().isoformat())
        J.log_terminal("Abriste después de la hora del reporte: te lo doy ahora.", "RUTINA")
        J.morning_report()
    except Exception as e:
        J.log_terminal(f"Reporte de la mañana: {e}", "AVISO")


_BRIEF = re.compile(r"^(?:jarvis\s+)?(?:dame|dime|repite(?:me)?|cual es|quiero)\s+(?:el\s+|mi\s+)?(?:resumen|reporte|informe)\s+(?:de la manana|matutino|del dia|de hoy)\s*$|"
                    r"^(?:jarvis\s+)?(?:resumen|reporte|informe) (?:de la manana|matutino)\s*$")


def brief_voice(text, t):
    if not _BRIEF.search(t):
        return False
    J.reply(J.morning_brief_text(), "RESUMEN")
    return True


def novedades_start():
    threading.Thread(target=_brief_catchup, daemon=True, name="reporte-al-abrir").start()


__all__ = ['PTT_GRACE', 'PTT_HOLD', '_BRIEF', '_COMPARE', '_NOT_WEB', '_PRICE', '_VID_OFF', '_VID_ON', '_VID_URL', '_brief_catchup', '_mode_answer', '_raw_tail',
           '_web_results', 'brief_catchup_due', 'brief_voice', 'compare_search', 'handle_ptt', 'handle_video_closed', 'handle_video_ping',
           'novedades_start', 'price_search', 'ptt', 'ptt_set', 'search_modes_voice', 'video', 'video_close', 'video_find', 'video_mic_muted',
           'video_show', 'hudvideo_voice']
