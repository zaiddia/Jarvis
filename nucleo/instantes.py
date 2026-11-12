"""12.20: respuestas al instante y habilidades nuevas del asistente general.

Sin IA (milisegundos, con o sin internet), en instante.py: hora en otra ciudad, días que faltan, qué día cae, edad,
conversor de unidades, dados y sorteos, deletrear, repetir, chistes, datos curiosos, frases y contraseñas.

Con red o IA (en segundo plano, avisando al terminar):
- «mide la velocidad de internet»   → bajada, subida y latencia, y para qué alcanza.
- «¿cuál es mi IP?»                  → la de este equipo en la red y la pública.
- «resume este video https://youtu…» → Gemini ve el video y lo resume (necesita la clave de Gemini).
- «¿cómo se dice buenos días en inglés?» → lo traduce con un pedido corto a la IA y lo dice con voz de ese idioma.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import re
import socket
import time
import urllib.request

import instante
from nucleo import J

_inst = {"speed": False, "speed_last": None}


# ============================================================================ SIN IA
def instant_voice(text, t):
    if not J.settings.get("instant_answers", True):
        return False
    t2 = instante.norm(text)
    pw = instante.password(t2)
    if pw:
        # La contraseña va SOLO a la pantalla: no pasa por la voz, ni por el registro, ni por el historial guardado.
        J.socketio.emit("chat", {"role": "jarvis", "source": "CONTRASEÑA", "time": time.strftime("%H:%M"), "date": time.strftime("%Y-%m-%d"),
                                 "text": f"Contraseña nueva ({pw[1]} caracteres):\n\n`{pw[0]}`\n\nCópiala ya: no queda guardada en ninguna parte."})
        J.reply(f"Te dejé en el chat una contraseña nueva de {pw[1]} caracteres. No la digo en voz alta ni la guardo.", "CONTRASEÑA")
        return True
    r = instante.answer(t2, text)
    if r:
        J.reply(r[1], r[0])
        return True
    return net_skills_voice(text, t, t2)


# ============================================================================ VELOCIDAD DE INTERNET
SPEED_DOWN = "https://speed.cloudflare.com/__down?bytes={n}"
SPEED_UP = "https://speed.cloudflare.com/__up"
_SPEED = re.compile(r"\b(?:mide|medir|prueba|test|revisa|como esta|que tal(?: esta)?|cual es)\s+(?:de\s+)?(?:la\s+|el\s+|mi\s+)?(?:velocidad\s+(?:de(?:l)?\s+)?)?(?:mi\s+)?(?:internet|wifi|conexion)\b|"
                    r"\b(?:test|prueba) de velocidad\b|\bvelocidad (?:de(?:l)? )?(?:mi )?(?:internet|wifi)\b|\b(?:esta|anda) lento el internet\b")


def _speed_get(url, limit_s, data=None):
    """Baja (o sube) midiendo. → (bytes, segundos)."""
    req = urllib.request.Request(url, data=data, headers={"User-Agent": f"Jarvis/{J.VERSION}"}, method="POST" if data is not None else "GET")
    t0 = time.perf_counter()
    n = 0
    with urllib.request.urlopen(req, timeout=10) as r:
        if data is not None:
            r.read()
            return len(data), time.perf_counter() - t0
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            n += len(chunk)
            if time.perf_counter() - t0 > limit_s:
                break
    return n, time.perf_counter() - t0


def speed_rating(down, up, ping):
    if down >= 50:
        txt = "Muy buena: alcanza para videollamadas, video en 4K y varias personas a la vez."
    elif down >= 15:
        txt = "Buena: alcanza para videollamadas y video en alta definición."
    elif down >= 5:
        txt = "Regular: sirve para una videollamada y navegar, pero se nota con varios equipos."
    elif down >= 1:
        txt = "Lenta: navegar y mensajes sí; las videollamadas se van a cortar."
    else:
        txt = "Muy lenta: apenas para mensajes de texto."
    if up < 1 and down >= 5:
        txt += " La subida es baja: tu video en las llamadas se verá mal."
    if ping > 150:
        txt += " La respuesta es lenta (latencia alta): se nota en llamadas y juegos."
    return txt


def speed_test():
    """→ {"ok", "bajada", "subida", "ping", "msg"} (megabits por segundo y milisegundos)."""
    try:
        pings = []
        for _ in range(3):
            t0 = time.perf_counter()
            with socket.create_connection(("1.1.1.1", 443), timeout=3):
                pings.append((time.perf_counter() - t0) * 1000)
        ping = min(pings)
    except OSError:
        ping = 0.0
    try:
        n, secs = J._speed_get(SPEED_DOWN.format(n=1_000_000), 6)          # calienta y estima
        down = n * 8 / max(secs, 0.001) / 1e6
        big = 25_000_000 if down > 20 else 8_000_000 if down > 4 else 0
        if big:
            n, secs = J._speed_get(SPEED_DOWN.format(n=big), 8)
            down = n * 8 / max(secs, 0.001) / 1e6
        up_n = 4_000_000 if down > 20 else 1_000_000 if down > 2 else 250_000
        n, secs = J._speed_get(SPEED_UP, 8, data=b"0" * up_n)
        up = n * 8 / max(secs, 0.001) / 1e6
    except Exception as e:
        return {"ok": False, "bajada": 0, "subida": 0, "ping": ping, "msg": f"No pude medir la velocidad: {'no hay internet' if J.net['offline'] else e}."}

    def f(v):
        return (f"{v:.0f}" if v >= 10 else f"{v:.1f}").replace(".", ",")
    msg = (f"Tu internet: {f(down)} megas de bajada, {f(up)} de subida" + (f" y {ping:.0f} milisegundos de respuesta" if ping else "") + ". "
           + speed_rating(down, up, ping))
    return {"ok": True, "bajada": round(down, 1), "subida": round(up, 1), "ping": round(ping), "msg": msg}


def _speed_job():
    try:
        r = J.speed_test()
        _inst["speed_last"] = dict(r, t=time.time())
        J.notify(r["msg"], "INTERNET")
    finally:
        _inst["speed"] = False


# ============================================================================ MI IP
_IP = re.compile(r"\b(?:cual es|dime|que|muestrame)\s+(?:mi\s+)?(?:direccion\s+)?ip(?:\s+(?:tengo|publica|local|es))?\b|\bmi (?:direccion )?ip\b")


def my_ip():
    local = ""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))            # no envía nada: solo averigua por cuál tarjeta saldría
            local = s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        pass
    public = ""
    if not J.net["offline"]:
        try:
            with urllib.request.urlopen("https://api.ipify.org", timeout=4) as r:
                public = r.read().decode("ascii", "replace").strip()[:45]
        except Exception:
            pass
    return local, public


# ============================================================================ RESUMIR UN VIDEO DE YOUTUBE
_YT = re.compile(r"(https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?[^\s]*v=|shorts/|live/)|youtu\.be/)[\w-]{6,}[^\s]*)", re.I)
_YT_ASK = re.compile(r"\b(?:resume|resumeme|resumen|resumir|de que (?:trata|habla)|que dice|explica|explicame|puntos clave|ideas principales|saca (?:las )?(?:ideas|notas|apuntes)|hazme (?:un )?(?:resumen|apuntes|quiz|cuestionario))\b")


def youtube_summary(url, ask=""):
    """Gemini ve el video y responde. → texto. Lanza AIError si no se puede."""
    g = J._gemini_for_stt()
    if not g:
        raise J.AIError("Falta la clave de Gemini.", kind="config", why="para resumir videos necesito la clave de Gemini (Ajustes › Inteligencia artificial)")
    prompt = (ask.strip() or "Resume este video.") + (
        " Responde en español, para leer en voz alta: primero de qué trata en 2 frases, luego de 3 a 6 ideas clave en frases cortas "
        "y al final para quién sirve. Sin asteriscos ni títulos.")
    body = {"contents": [{"role": "user", "parts": [{"file_data": {"file_uri": url}}, {"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 900, "temperature": 0.3}}
    data = J._post(f"{J.GEMINI_BASE}/models/{g['model']}:generateContent", J._gemini_headers(g), body, (), timeout=240)
    out = J._gemini_text(data)
    if not out:
        raise J.AIError("Gemini no devolvió el resumen.", why="Gemini no pudo ver ese video (puede ser privado, muy largo o con restricción de edad)")
    return out


def _yt_job(url, ask):
    try:
        out = J.youtube_summary(url, ask)
    except J.AIError as e:
        J.notify(f"No pude resumir el video: {e.why or e}.", "VIDEO")
        return
    except Exception as e:
        J.notify(f"No pude resumir el video: {e}.", "VIDEO")
        return
    J.reply(out, "VIDEO")


# ============================================================================ TRADUCTOR HABLADO
LANGS = {  # idioma → (nombre para la IA, voz de Edge)
    "ingles": ("inglés", "en-US-GuyNeural"), "frances": ("francés", "fr-FR-HenriNeural"), "portugues": ("portugués", "pt-BR-AntonioNeural"),
    "italiano": ("italiano", "it-IT-DiegoNeural"), "aleman": ("alemán", "de-DE-ConradNeural"), "japones": ("japonés", "ja-JP-KeitaNeural"),
    "chino": ("chino mandarín", "zh-CN-YunxiNeural"), "coreano": ("coreano", "ko-KR-InJoonNeural"), "ruso": ("ruso", "ru-RU-DmitryNeural"),
    "arabe": ("árabe", "ar-SA-HamedNeural"), "holandes": ("neerlandés", "nl-NL-MaartenNeural"), "espanol": ("español", ""),
    "latin": ("latín", "it-IT-DiegoNeural"), "catalan": ("catalán", "ca-ES-EnricNeural"),
}
_LANG_ALT = "|".join(LANGS)
_TR1 = re.compile(rf"\bcomo (?:se dice|se escribe|digo|dirias|se diria)\s+(.+?)\s+en\s+({_LANG_ALT})\b")
_TR2 = re.compile(rf"\b(?:traduce|traduceme|traducir|traduzca|pasa|pon)\s+(?:al?|en)\s+({_LANG_ALT})\s*:?\s+(.+)$")
_TR3 = re.compile(rf"\b(?:traduce|traduceme|traducir|traduzca)\s+(.+?)\s+(?:al?|en)\s+({_LANG_ALT})\s*$")
_TR4 = re.compile(r"\bque (?:significa|quiere decir)\s+(.+?)\s+en (?:espanol|castellano)\b")


def _tr_parse(text, t2):
    """→ (frase, idioma) o None. La frase sale del texto original (con tildes y mayúsculas)."""
    for rx, order in ((_TR1, (1, 2)), (_TR2, (2, 1)), (_TR3, (1, 2))):
        m = rx.search(t2)
        if m:
            phrase, lang = m.group(order[0]), m.group(order[1])
            words = text.strip().strip("¿?¡!.").split()
            nw = t2.split()
            try:                                        # mismas palabras, en su forma original
                i = next(k for k in range(len(nw)) if nw[k:k + len(phrase.split())] == phrase.split())
                if len(words) == len(nw):
                    phrase = " ".join(words[i:i + len(phrase.split())])
            except StopIteration:
                pass
            return phrase.strip(" :\"«»"), lang
    m = _TR4.search(t2)
    if m:
        return m.group(1).strip(), "espanol"
    return None


def translate(phrase, lang):
    """Pedido corto a la IA (sin tu contexto ni la conversación: por eso es rápido). → traducción."""
    name = LANGS[lang][0]
    sys_msg = (f"Eres un traductor. Traduce al {name} lo que te dan. Responde SOLO con la traducción, sin comillas, sin explicar y sin "
               "repetir el original.")
    out = J.ai_chat([{"role": "system", "content": sys_msg}, {"role": "user", "content": phrase}], max_tokens=120)
    return out.strip().strip('"«»').split("\n")[0].strip()


def _tr_job(phrase, lang):
    try:
        out = J.translate(phrase, lang)
    except J.AIError as e:
        J.reply(J.ai_error_reply(e), "TRADUCTOR")
        return
    if not out:
        J.reply("No pude traducir eso.", "TRADUCTOR")
        return
    name, voice = LANGS[lang]
    J.log_terminal(f"«{phrase}» en {name}: {out}", "TRADUCTOR")
    J.push_chat("jarvis", f"«{phrase}» en {name}:\n\n**{out}**", "TRADUCTOR")
    if getattr(J._tl, "quiet", False):
        return
    if lang == "espanol" or not voice or J.is_offline() or J.edge_tts is None:
        J.speak(f"En {name} se dice: {out}" if lang != "espanol" else f"Significa: {out}")
    else:
        J.speak(f"En {name} se dice:")
        J.speak(out, voice=voice, backend="edge")       # con voz nativa de ese idioma


# ============================================================================ ENRUTADO
def net_skills_voice(text, t, t2=None):
    t2 = t2 or instante.norm(text)
    m = _YT.search(text)
    if m and (_YT_ASK.search(t) or len(t.split()) <= 3):
        url = m.group(1).rstrip(".,)")
        ask = _YT.sub("", text).strip(" :.,")
        if J.is_offline():
            J.reply("Para ver el video necesito internet. Vuelve a pedírmelo cuando regrese.", "VIDEO")
            return True
        J.reply("Voy a ver el video; te cuento en un momento.", "VIDEO")
        J.start_job("Viendo el video", lambda: _yt_job(url, ask), name="video")
        return True
    if _SPEED.search(t):
        if J.net["offline"]:
            J.reply("Ahora mismo no hay internet, así que no hay nada que medir. Estoy funcionando con la IA de tu equipo.", "INTERNET")
            return True
        if _inst["speed"]:
            J.reply("Ya la estoy midiendo.", "INTERNET")
            return True
        _inst["speed"] = True
        J.reply("Midiendo tu internet; tarda unos 15 segundos.", "INTERNET")
        if J.net["watch"]:
            J.start_job("Midiendo la velocidad de internet", J._speed_job, name="velocidad")
        else:                                          # sin vigilancia de red (pruebas automáticas): no sale a internet
            _inst["speed"] = False
        return True
    if _IP.search(t):
        local, public = J.my_ip()
        if not local and not public:
            J.reply("Este equipo no está conectado a ninguna red.", "RED")
            return True
        msg = (f"En tu red, este equipo es {local}." if local else "") + (f" Hacia internet sales con la {public}." if public else
                                                                           " No pude ver la IP pública (sin internet)." if local else "")
        J.reply(msg.strip(), "RED")
        return True
    tr = _tr_parse(text, t2)
    if tr and len(tr[0]) <= 300:
        J._tr_job(*tr)
        return True
    return False


__all__ = ['LANGS', 'SPEED_DOWN', 'SPEED_UP', '_IP', '_SPEED', '_TR1', '_TR2', '_TR3', '_TR4', '_YT', '_YT_ASK', '_inst', '_speed_get', '_speed_job',
           '_tr_job', '_tr_parse', '_yt_job', 'instant_voice', 'my_ip', 'net_skills_voice', 'speed_rating', 'speed_test', 'translate',
           'youtube_summary']
