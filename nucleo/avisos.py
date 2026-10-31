"""Clima y noticias, Telegram y tonos de aviso.

Parte de Jarvis (antes dentro de jarvis.py). Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import buscar
import infodia
import json
import os
import re
import skills
import tempfile
import threading
import time
import urllib.request

from nucleo import J


# =============================================================================
# CLIMA Y NOTICIAS (lógica en infodia.py)
# =============================================================================
GEO_URL = infodia.GEO_URL
FORECAST_URL = infodia.FORECAST_URL
_geo_cache = {}


def _get_text(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": f"Mozilla/5.0 (Jarvis/{J.VERSION})",
                                               "Accept-Language": "es-CO,es;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _geo(city):
    key = J.normalize(city)
    if key not in J._geo_cache:
        url = infodia.geo_url(city).replace(infodia.GEO_URL, J.GEO_URL)
        J._geo_cache[key] = infodia.parse_geo(json.loads(J._get_text(url)))
    return J._geo_cache[key]


def weather_text(city="", day=0):
    city = (city or J.settings["weather_city"]).strip()
    if not city:
        return ("Para darte el clima dime de qué ciudad, por ejemplo «clima en Medellín», o escribe tu ciudad "
                "en Ajustes, sección Integraciones.")
    if J.is_offline():
        return "Ahora no hay internet, así que no puedo consultar el clima."
    try:
        g = J._geo(city)
        if not g:
            return f"No encontré la ciudad «{city}». Prueba con otro nombre."
        url = infodia.forecast_url(g["lat"], g["lon"]).replace(infodia.FORECAST_URL, J.FORECAST_URL)
        return infodia.describe(json.loads(J._get_text(url)), g["name"], day)
    except Exception as e:
        J.log_terminal(f"Clima: {e}", "AVISO")
        return "No pude consultar el clima en este momento."


def _news_items(topic=""):
    feeds = [infodia.topic_feed(topic)] if topic else (
        [u.strip() for u in J.settings["news_feeds"].splitlines() if u.strip().startswith("http")] or infodia.DEFAULT_FEEDS)
    lists = []
    for u in feeds[:5]:
        try:
            lists.append(infodia.parse_rss(J._get_text(u)))
        except Exception as e:
            J.log_terminal(f"Noticias ({urllib.parse.urlsplit(u).netloc}): {e}", "AVISO")
    return infodia.merge(lists, limit=10)


def news_text(topic=""):
    if J.is_offline():
        return "Ahora no hay internet, así que no puedo traer las noticias."
    items = J._news_items(topic)
    if not items:
        return "No pude traer las noticias en este momento."
    try:
        return J.ai_chat([{"role": "user", "content": infodia.news_prompt(items, topic)}], max_tokens=900).strip()
    except Exception:
        return infodia.headlines_spoken(items)          # sin IA: los titulares tal cual


_WEATHER_RE = re.compile(r"\b(?:clima|tiempo (?:que hace|hace|va a hacer)|temperatura|pronostico|va a llover|"
                         r"llovera|esta lloviendo|hace (?:frio|calor)|que tal el dia)\b")
_NEWS_RE = re.compile(r"\b(?:noticias|titulares|que (?:hay de nuevo|esta pasando)|que paso hoy|resumen de noticias)\b")


def info_voice(text, t):
    """«¿cómo está el clima?», «¿va a llover mañana?», «clima en Cali», «noticias», «noticias de educación»."""
    if J._WEATHER_RE.search(t) and not re.search(r"\b(?:temperatura del? (?:pc|cpu|procesador|equipo))\b", t):
        day = 1 if re.search(r"\bmanana\b", t) else 0
        m = re.search(r"\b(?:en|de|para)\s+([a-zñ ]{3,40}?)\s*(?:hoy|manana|ahora)?$", t)
        city = ""
        if m and m.group(1).strip() not in ("hoy", "manana", "la manana", "la tarde", "la noche", "el dia"):
            city = m.group(1).strip().title()
        J.reply(J.weather_text(city, day), "CLIMA")
        return True
    if J._NEWS_RE.search(t):
        m = re.search(r"\bnoticias\s+(?:de|del|sobre|acerca de)\s+(?:la |el |los |las )?(.{3,60})$", t)
        topic = m.group(1).strip() if m and m.group(1).strip() not in ("hoy", "el dia", "colombia hoy") else ""
        J.reply("Buscando las noticias" + (f" de {topic}" if topic else "") + "…", "NOTICIAS")
        J.reply(J.news_text(topic), "NOTICIAS")
        return True
    return False


_SEARCH_RE = re.compile(
    r"\b(?:busca|buscame|averigua|averiguame|investiga|consulta|resumeme)\b.{0,40}\b(?:en internet|en la web|en linea|en google|en la red)\b"
    r"|^(?:oye |jarvis )?(?:averigua|averiguame|investiga)\b"
    r"|\bbusca(?:me)?\b.{0,60}\by (?:res[uú]m\w*|cu[eé]nta\w*|me cu[eé]nta\w*)\b")
_SEARCH_NOT = re.compile(r"\b(?:archivo|carpeta|documento|youtube|you tube|spotify|cancion|video|musica|"
                         r"aplicacion|programa|en mi (?:pc|equipo|computador))\b")


def search_voice(text, t):
    """«busca en internet qué pasó con…», «averigua…», «busca y resúmeme…»."""
    if J._SEARCH_NOT.search(t) or not J._SEARCH_RE.search(t):
        return False
    q = re.sub(r"^(?:oye |jarvis )?(?:busca(?:me)?|averigua(?:me)?|investiga|consulta|resumeme)\s+", "", text.strip(), flags=re.I)
    q = re.sub(r"\b(?:en internet|en la web|en linea|en l[ií]nea|en google|en la red)\b", "", q, flags=re.I)
    q = re.sub(r"\s+y (?:res[uú]m\w*|cu[eé]nta\w*|me cu[eé]nta\w*)\b.*$", "", q, flags=re.I)
    q = re.sub(r"^(?:sobre|acerca de|que|qu[eé]|lo de|por)\s+", "", q.strip(" ,.:"), flags=re.I).strip(" ,.:¿?")
    if len(q) < 3:
        J.reply("¿Qué quieres que busque en internet?", "INTERNET")
        return True
    J.web_search(q)
    return True


def web_search(query):
    if J.is_offline():
        J.reply("Ahora no hay internet, así que no puedo buscar.", "INTERNET")
        return
    J.reply(f"Busco en internet sobre {query}…", "INTERNET")

    def work():
        results = []
        for lite in (False, True):
            try:
                results = buscar.parse_results(J._get_text(buscar.search_url(query, lite=lite), timeout=12))
            except Exception as e:
                J.log_terminal(f"Búsqueda web: {e}", "AVISO")
            if results:
                break
        if not results:
            J.reply("No pude buscar en internet en este momento. Inténtalo de nuevo en un momento.", "INTERNET")
            return
        try:
            ans = J.ai_chat([{"role": "user", "content": buscar.prompt(query, results)}], max_tokens=600).strip()
        except J.AIError:
            ans = buscar.spoken_fallback(query, results)
        except Exception:
            ans = buscar.spoken_fallback(query, results)
        J.reply(ans or buscar.spoken_fallback(query, results), "INTERNET")
        fuentes = buscar.sources(results)
        if fuentes:
            J.log_terminal("Fuentes: " + " · ".join(f"{s['titulo']} ({s['fuente']})" for s in fuentes), "INTERNET")
    J.start_job("Buscando en la web", work, "buscar")


# =============================================================================
# TELEGRAM: controla Jarvis desde tu celular y recibe ahí tus avisos
# =============================================================================
TELEGRAM_API = "https://api.telegram.org"
tg = {"offset": None, "last_cmd": 0.0, "unknown_warned": set(), "ok": False, "error": ""}


def _tg_call(method, params=None, timeout=35, files=None):
    token = J.settings["telegram_token"].strip()
    url = f"{J.TELEGRAM_API}/bot{token}/{method}"
    if files:                                          # multipart para la captura de pantalla
        import uuid as _u
        bnd = "----jarvis" + _u.uuid4().hex
        body = bytearray()
        for k, v in (params or {}).items():
            body += f"--{bnd}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        for k, (fname, data, ctype) in files.items():
            body += (f"--{bnd}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fname}\"\r\n"
                     f"Content-Type: {ctype}\r\n\r\n").encode() + data + b"\r\n"
        body += f"--{bnd}--\r\n".encode()
        req = urllib.request.Request(url, data=bytes(body), method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={bnd}"})
    else:
        req = urllib.request.Request(url, data=json.dumps(params or {}).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    if not d.get("ok"):
        raise RuntimeError(d.get("description") or "Telegram rechazó la petición")
    return d.get("result")


def telegram_send(text, chat=None):
    chat = chat or J.settings["telegram_chat"].strip()
    if not (J.settings["telegram_token"].strip() and chat):
        return False
    try:
        for i in range(0, len(text), 3800):
            J._tg_call("sendMessage", {"chat_id": chat, "text": text[i:i + 3800]}, timeout=15)
        return True
    except Exception as e:
        J.log_terminal(f"Telegram: {e}", "AVISO")
        return False


def alert(text, origin="JARVIS"):
    """Un aviso (recordatorio, calendario, temporizador): en el PC y, si lo activaste, en tu celular."""
    J.reply(text, origin)
    J.orb_feed.update(alert_seq=J.orb_feed["alert_seq"] + 1, alert=str(text)[:300])   # el orbe destella
    J.whatsapp_alert(text)                             # 7.9: también al WhatsApp, si lo configuraste
    J.windows_toast(text, origin)                      # 7.2: también como notificación de Windows
    if J.settings["telegram_alerts"] and J.settings["telegram_remote"]:
        threading.Thread(target=J.telegram_send, args=(f"🔔 {text}",), daemon=True).start()


_TG_HELP = ("Soy Jarvis, en tu computador. Escríbeme como me hablarías, por ejemplo:\n"
            "• ¿qué tengo hoy?\n• abre la presentación de ciencias\n• recuérdame a las 3 llamar a la coordinadora\n"
            "• volumen al 30\n• ¿cómo está el clima?\n• noticias\n\n"
            "/captura – foto de la pantalla\n/estado – cómo está el PC\n/prueba – prueba completa de Jarvis\n/informe – informe de errores (sin claves)\n/ayuda – esta ayuda\n\n"
            "Por seguridad, desde aquí no apago ni reinicio el equipo, no cierro programas, no escribo en ventanas "
            "y no borro datos.")


def telegram_run(text):
    """Ejecuta un mensaje de Telegram como una orden escrita y devuelve la respuesta en texto."""
    t = J.normalize(text)
    J.pending.update(skill=None, args=None, expires=0)   # nada peligroso se confirma desde el celular
    direct = skills.parse(text)
    sk = skills.REGISTRY.get(direct[0]) if direct else None
    if sk is not None and sk.dangerous:
        J.log_terminal(f"Orden peligrosa pedida por Telegram, no ejecutada: {text}", "AVISO")
        return "Por seguridad, eso (apagar, reiniciar, cerrar sesión, borrar…) no lo hago desde Telegram."
    if re.search(J.DICTATION_START_RE, t):
        return "El dictado solo funciona hablando frente al computador."
    if J._REMOTE_DELETE_RE.search(t):
        J.log_terminal(f"Desde el celular no se borran datos: {text}", "AVISO")
        return "Por seguridad, desde el celular no borro ni restauro datos (notas, memoria, rutinas, copias). Hazlo en el equipo."
    J._tl.capture, J._tl.remote = [], True
    try:
        J.process_command(text)
        said = list(J._tl.capture)
    except Exception as e:
        return f"No pude hacerlo: {e}"
    finally:
        J._tl.capture, J._tl.remote = None, False
    return "\n".join(said) or "Hecho."


def _tg_screenshot(chat):
    if skills.pyautogui is None:
        return "No puedo capturar la pantalla (falta pyautogui)."
    title = J._foreground_title()
    if title and J.SENSITIVE_TITLES.search(title):
        return "La ventana abierta parece privada (contraseñas, banco o pagos): no la capturo."
    import io
    img = skills.pyautogui.screenshot()
    if img.width > 1600:
        img = img.resize((1600, round(img.height * 1600 / img.width)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=75)
    J._tg_call("sendPhoto", {"chat_id": chat, "caption": title or "Pantalla"},
             files={"photo": ("pantalla.jpg", buf.getvalue(), "image/jpeg")}, timeout=30)
    return None


def _tg_handle(msg):
    chat = str((msg.get("chat") or {}).get("id", ""))
    text = (msg.get("text") or "").strip()
    who = (msg.get("from") or {}).get("first_name", "alguien")
    allowed = J.settings["telegram_chat"].strip()
    if not allowed:
        # aún no hay chat configurado: le dice su número para que lo pongas en Ajustes
        J.log_terminal(f"Telegram: escribió {who} (chat id {chat}). Si eres tú, pon {chat} en Ajustes › "
                     "Integraciones › Chat id.", "TELEGRAM")
        J.telegram_send(f"Hola {who}. Tu chat id es {chat}. Escríbelo en Jarvis (Ajustes › Integraciones › Chat id) "
                      "para que pueda obedecerte desde aquí.", chat)
        return
    if chat != allowed:
        if chat not in J.tg["unknown_warned"]:
            J.tg["unknown_warned"].add(chat)
            J.log_terminal(f"Telegram: ignoré un mensaje de un chat desconocido ({who}, {chat}).", "AVISO")
        return
    if not text and (msg.get("voice") or msg.get("audio")):
        J.tg_voice(msg)                                # 7.9: notas de voz
        return
    if not text:
        J.telegram_send("Por ahora entiendo mensajes de texto y notas de voz.")
        return
    J.tg["last_cmd"] = time.time()
    J.log_terminal(f"Desde el celular: {text}", "TELEGRAM")
    J.push_chat("user", text, "telegram")
    low = J.normalize(text.lstrip("/"))
    if low in ("start", "ayuda", "help"):
        out = J._TG_HELP
    elif low in ("captura", "pantalla", "screenshot"):
        try:
            out = J._tg_screenshot(chat)
        except Exception as e:
            out = f"No pude enviar la captura: {e}"
    elif low in ("estado", "status"):
        out = J.telegram_run("estado del sistema")
    elif low in ("informe", "informe de errores"):
        J.telegram_send("Preparo el informe… (hago la prueba completa)")
        _, path = J.make_report()
        try:
            with open(path, "rb") as f:
                J._tg_call("sendDocument", {"chat_id": chat}, files={"document": (os.path.basename(path), f.read(), "text/plain")},
                           timeout=60)
            out = "Ahí va el informe. No lleva tus claves."
        except Exception as e:
            out = f"No pude enviar el informe: {e}"
    elif low in ("prueba", "prueba completa", "diagnostico"):
        J.telegram_send("Haciendo la prueba completa… (tarda unos segundos)")
        out = J.check_report(J.run_system_check(speak_it=False))
    else:
        out = J.telegram_run(text)
    if out:
        J.telegram_send(out)


def _telegram_worker():
    """Recibe los mensajes del bot (long polling). Solo obedece a tu chat."""
    while True:
        if not (J.settings["telegram_remote"] and J.settings["telegram_token"].strip()) or J.is_offline():
            J.tg["ok"] = False
            time.sleep(5)
            continue
        try:
            if J.tg["offset"] is None:                    # al arrancar no se ejecutan mensajes viejos
                old = J._tg_call("getUpdates", {"timeout": 0, "offset": -1}, timeout=15) or []
                J.tg["offset"] = (old[-1]["update_id"] + 1) if old else 0
            ups = J._tg_call("getUpdates", {"timeout": 25, "offset": J.tg["offset"],
                                          "allowed_updates": ["message"]}, timeout=35) or []
            if not J.tg["ok"]:
                J.tg.update(ok=True, error="")
                J.log_terminal("Telegram conectado: puedes escribirle a tu bot desde el celular.", "TELEGRAM")
            for u in ups:
                J.tg["offset"] = u["update_id"] + 1
                if u.get("message"):
                    try:
                        J._tg_handle(u["message"])
                    except Exception as e:
                        J.log_terminal(f"Telegram: {e}", "ERROR")
        except Exception as e:
            if str(e) != J.tg["error"]:
                J.tg["error"] = str(e)
                J.log_terminal(f"Telegram: {e}", "AVISO")
            J.tg["ok"] = False
            time.sleep(15)


def telegram_test():
    if not J.settings["telegram_token"].strip():
        return {"ok": False, "msg": "Primero pega el token del bot y guarda."}
    try:
        me = J._tg_call("getMe", timeout=10)
    except Exception as e:
        return {"ok": False, "msg": f"El token no funciona: {e}"}
    name = me.get("username", "")
    if not J.settings["telegram_chat"].strip():
        return {"ok": True, "msg": f"Bot @{name} listo. Escríbele «hola» desde tu Telegram y te responderá con tu "
                                   "chat id; pégalo aquí y guarda."}
    ok = J.telegram_send(f"✅ Jarvis conectado. Escríbeme aquí tus órdenes. /ayuda para ver ejemplos.")
    return {"ok": ok, "msg": f"Bot @{name}: " + ("te envié un mensaje de prueba." if ok else "no pude escribirte; revisa el chat id.")}



# =============================================================================
# TONOS (avisos cortos sintetizados): descanso, despertar, sismo
# =============================================================================
_TONES = {}


def _tone(name, notes, vol=9000):
    """notes = [(frecuencia_hz, duración_s), …]. Devuelve la ruta a un WAV cacheado."""
    if name in J._TONES and os.path.exists(J._TONES[name]):
        return J._TONES[name]
    import math
    import wave
    rate = 22050
    frames = bytearray()
    for freq, dur in notes:
        n = int(rate * dur)
        for i in range(n):
            env = min(1.0, i / 300) * min(1.0, (n - i) / 500)
            s = vol * env * math.sin(2 * math.pi * freq * i / rate)
            frames += int(max(-32767, min(32767, s))).to_bytes(2, "little", signed=True)
    path = os.path.join(tempfile.gettempdir(), f"jarvis_tono_{name}.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    J._TONES[name] = path
    return path


def tono_descanso():
    return J._tone("descanso", [(660, 0.14), (520, 0.14), (392, 0.2)])     # desciende


def tono_despertar():
    return J._tone("despertar", [(392, 0.12), (523, 0.12), (660, 0.18)])   # asciende


def tono_sismo_aviso():
    return J._tone("sismo1", [(700, 0.18), (0, 0.08), (700, 0.18)])


def tono_sismo_alerta():
    return J._tone("sismo2", [(880, 0.16), (0, 0.06), (880, 0.16), (0, 0.06), (880, 0.16),
                            (0, 0.06), (1100, 0.3)], vol=12000)


__all__ = [
    'FORECAST_URL',
    'GEO_URL',
    'TELEGRAM_API',
    '_NEWS_RE',
    '_SEARCH_NOT',
    '_SEARCH_RE',
    '_TG_HELP',
    '_TONES',
    '_WEATHER_RE',
    '_geo',
    '_geo_cache',
    '_get_text',
    '_news_items',
    '_telegram_worker',
    '_tg_call',
    '_tg_handle',
    '_tg_screenshot',
    '_tone',
    'alert',
    'info_voice',
    'news_text',
    'search_voice',
    'telegram_run',
    'telegram_send',
    'telegram_test',
    'tg',
    'tono_descanso',
    'tono_despertar',
    'tono_sismo_alerta',
    'tono_sismo_aviso',
    'weather_text',
    'web_search',
]
