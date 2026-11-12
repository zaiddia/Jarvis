"""12.21: habilidades para el día a día.

- Pausas activas y respiración guiadas por voz («hazme una pausa activa», «respiración de 2 minutos», «termina la pausa»).
- Códigos QR de lo que quieras («crea un QR de https://…», «un QR del wifi Casa con clave …»).
- Radio en vivo dentro de Jarvis («pon Caracol Radio», «pon una emisora de salsa», «apaga la radio»).
- Modo cocina: receta paso a paso («modo cocina arroz con pollo», «siguiente paso», «repite», «los ingredientes»).
- Inglés: palabra del día y quiz sin internet; práctica de conversación con la IA («practiquemos inglés»).
- Cuentos narrados («cuéntame un cuento de dragones para un niño de 6 años»).

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import array
import json
import os
import random
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request

import instante
from nucleo import J

def show(text, origin):
    """Lo deja en el chat y en el registro SIN decirlo (lo que se dice va aparte, más corto o con otra voz)."""
    was = getattr(J._tl, "quiet", False)
    J._tl.quiet = True
    try:
        J.reply(text, origin)
    finally:
        J._tl.quiet = was


# ============================================================================ PAUSA ACTIVA Y RESPIRACIÓN
PAUSAS = [
    ("Cuello", [("Siéntate derecho y relaja los hombros.", 4), ("Lleva la oreja derecha hacia el hombro derecho y sostén.", 12),
                ("Ahora hacia el lado izquierdo.", 12), ("Baja el mentón al pecho, despacio.", 10), ("Gira la cabeza a la derecha… y a la izquierda.", 10)]),
    ("Hombros y espalda", [("Sube los hombros hacia las orejas… y suéltalos. Tres veces.", 12), ("Haz círculos grandes con los hombros hacia atrás.", 12),
                           ("Entrelaza las manos y estira los brazos al frente, redondeando la espalda.", 12),
                           ("Ahora estíralos hacia arriba, bien alto.", 12)]),
    ("Manos y vista", [("Abre y cierra las manos con fuerza, diez veces.", 12), ("Gira las muñecas hacia un lado y hacia el otro.", 10),
                       ("Mira por la ventana, o al punto más lejano que puedas, y descansa la vista.", 20),
                       ("Parpadea despacio varias veces.", 8)]),
    ("Piernas", [("Ponte de pie.", 4), ("Párate en la punta de los pies y baja. Diez veces.", 15), ("Camina en el puesto, levantando las rodillas.", 20),
                 ("Sacude brazos y piernas, y vuelve a sentarte cuando quieras.", 8)]),
]
_pausa = {"on": False, "stop": threading.Event()}
_PAUSA = re.compile(r"\b(?:hazme|hagamos|haz|dame|necesito|guiame|iniciar?|empieza|empecemos)\s+(?:una\s+|en una\s+)?pausa activa\b|^(?:jarvis\s+)?pausa activa\b|"
                    r"\b(?:estiramientos?|estirar(?:me)?) (?:guiados?|ahora|un momento)\b|\bestiremos\b")
_RESP = re.compile(r"\b(?:respiracion|respirar|respiremos|ejercicio de respiracion)\b(?:.*?\b(\d{1,2})\s+minutos?)?")
_PAUSA_STOP = re.compile(r"\b(?:termina|para|deten|cancela|corta|ya)\s+(?:la\s+)?(?:pausa(?: activa)?|respiracion|los estiramientos)\b|\bya no mas pausa\b")


def _say_wait(text, secs):
    """Dice una frase y espera (se corta si piden parar). → False si se pidió parar."""
    J.speak(text)
    return not _pausa["stop"].wait(secs)


def _pausa_run(kind, minutes):
    try:
        if kind == "resp":
            cycles = max(3, int(minutes * 60 / 16))
            J.speak(f"Respiración guiada, {minutes} minutos. Siéntate cómodo y afloja los hombros.")
            if _pausa["stop"].wait(5):
                return
            for i in range(cycles):
                if not (_say_wait("Inhala por la nariz.", 4.5) and _say_wait("Sostén.", 4) and _say_wait("Exhala despacio por la boca.", 7)):
                    return
            J.reply("Listo. Vuelve a lo tuyo con calma.", "PAUSA")
            return
        J.speak("Pausa activa de unos cuatro minutos. Si quieres parar, di: termina la pausa.")
        if _pausa["stop"].wait(5):
            return
        for name, steps in PAUSAS:
            if not _say_wait(name + ".", 1.5):
                return
            for text, secs in steps:
                if not _say_wait(text, secs + 3):
                    return
        J.reply("Terminamos la pausa activa. ¡Buen trabajo!", "PAUSA")
    finally:
        _pausa["on"] = False


def pausa_voice(text, t):
    if _pausa["on"] and _PAUSA_STOP.search(t):
        _pausa["stop"].set()
        J.stop_speech(log=False)
        J.reply("Listo, paro la pausa.", "PAUSA")
        return True
    m = _RESP.search(t)
    is_resp = bool(m) and bool(re.search(r"\b(?:guiada|ejercicio|hagamos|hazme|haz|minutos?|respiremos|necesito|ayudame)\b|^(?:jarvis )?respiracion\b", t))
    if not (_PAUSA.search(t) or is_resp):
        return False
    if _pausa["on"]:
        J.reply("Ya estamos en una pausa. Para cortarla di «termina la pausa».", "PAUSA")
        return True
    _pausa["on"] = True
    _pausa["stop"].clear()
    if is_resp and not _PAUSA.search(t):
        mins = min(max(int(m.group(1) or 2), 1), 10)
        J.show(f"Respiración guiada · {mins} min: inhala 4 s, sostén 4 s, exhala 6 s. Para cortar: «termina la respiración».", "PAUSA")
        args = ("resp", mins)
    else:
        lines = "\n".join(f"**{n}**: " + " ".join(s for s, _ in steps) for n, steps in PAUSAS)
        J.show("Pausa activa (4 min). Para cortar: «termina la pausa».\n\n" + lines, "PAUSA")
        args = ("pausa", 4)
    if J.net["watch"]:
        threading.Thread(target=J._pausa_run, args=args, daemon=True, name="pausa-activa").start()
    else:                                              # pruebas automáticas: no se queda hablando varios minutos
        _pausa["on"] = False
    return True


# ============================================================================ CÓDIGOS QR
_QR = re.compile(r"\b(?:crea|creame|genera|generame|haz|hazme|saca|necesito|dame)\s+(?:un\s+|el\s+)?(?:codigo\s+)?qr\b\s*(.*)$")
_QR_WIFI = re.compile(r"\b(?:del?|para(?: el)?|con el)\s+wi-?fi\s+(?:de\s+|llamad[oa]\s+)?(.+?)\s+(?:con\s+(?:la\s+)?|y\s+)?(?:clave|contrasena|password)\s+(.+)$", re.I)


def qr_payload(raw):
    """Texto original de la orden → (contenido del QR, descripción para decir) o None si no dijo de qué."""
    m = re.search(r"\bqr\b\s*(.*)$", raw, re.I)
    rest = (m.group(1) if m else "").strip()
    w = re.search(r"\b(?:del?|para(?:\s+el)?|con\s+el)\s+wi-?fi\s+(?:de\s+|llamad[oa]\s+)?(.+?)\s+(?:con\s+(?:la\s+)?|y\s+)?(?:clave|contraseña|contrasena|password)\s+(\S+)\s*$", rest, re.I)
    if w:
        name, key = w.group(1).strip(" \"«»"), w.group(2).strip(" \"«».")

        def esc(x):
            return re.sub(r'([\\;,:"])', r"\\\1", x)
        return f"WIFI:T:WPA;S:{esc(name)};P:{esc(key)};;", f"el wifi «{name}»"
    rest = re.sub(r"^(?:de|del|para|con|a|que diga|que lleve a|que abra|hacia)\s+(?:este\s+|esta\s+|el\s+|la\s+)?(?:enlace|link|pagina|direccion|texto|numero|telefono)?\s*:?\s*", "", rest, flags=re.I).strip(" \"«».")
    if not rest:
        return None
    if re.fullmatch(r"(?:www\.)?[\w-]+(?:\.[\w-]+)+(?:/\S*)?", rest):
        rest = "https://" + rest
    return rest, (rest if len(rest) <= 60 else rest[:57] + "…")


def make_qr(content, name="qr"):
    import qrcode
    folder = os.path.join(J.settings["output_dir"], "QR")
    os.makedirs(folder, exist_ok=True)
    slug = re.sub(r"[^\w-]+", "_", J.normalize(name))[:40].strip("_") or "qr"
    path = os.path.join(folder, f"{slug}_{time.strftime('%H%M%S')}.png")
    qrcode.make(content, box_size=12, border=3).save(path)
    return path


def qr_voice(text, t):
    if not _QR.search(t) or re.search(r"\b(?:asistencia|quiz|examen|salon|clase|estudiantes?|coevaluacion|laboratorio|ticket|taller|celular|panel|juego|"
                                      r"calificar|practica|guia|tablero|aventura)\b", t):
        return False                                   # los QR del salón y del celular tienen sus propias órdenes
    got = qr_payload(text)
    if not got:
        J.reply("Dime de qué: «crea un QR de https://mi-pagina.com» o «un QR del wifi Casa con clave 12345678».", "QR")
        return True
    content, label = got
    try:
        path = J.make_qr(content, "wifi" if content.startswith("WIFI:") else label)
    except Exception as e:
        J.reply(f"No pude crear el QR: {e}", "QR")
        return True
    if J.IS_WIN and J.net["watch"]:
        try:
            os.startfile(path)
        except OSError:
            pass
    J.reply(f"Listo el QR de {label}. Lo guardé en {path}" + (" y te lo abrí." if J.IS_WIN else "."), "QR")
    return True


# ============================================================================ RADIO EN VIVO
RADIO_HOSTS = ("de1.api.radio-browser.info", "nl1.api.radio-browser.info", "at1.api.radio-browser.info")
GENEROS = {"salsa": "salsa", "vallenato": "vallenato", "clasica": "classical", "musica clasica": "classical", "rock": "rock", "pop": "pop",
           "jazz": "jazz", "reggaeton": "reggaeton", "tropical": "tropical", "noticias": "news", "baladas": "ballads", "romantica": "romantic",
           "electronica": "electronic", "cristiana": "christian", "infantil": "children", "instrumental": "instrumental", "relajante": "chillout",
           "deportes": "sports", "merengue": "merengue", "cumbia": "cumbia", "ranchera": "ranchera", "popular": "popular", "anos 80": "80s"}
_radio = {"proc": None, "name": "", "vol": 0.6, "stop": threading.Event(), "thread": None}
_RADIO_ON = re.compile(r"\b(?:pon|ponme|coloca|sintoniza|quiero (?:oir|escuchar)|reproduce|escuchemos)\s+(?:la\s+|una\s+|el\s+)?(?:(?:emisora|radio)\s+(?:de\s+|del?\s+)?(.+)|(.+?)\s+(?:radio|fm|estereo|stereo))\s*$")
_RADIO_OFF = re.compile(r"\b(?:apaga|para|quita|deten|cierra|silencia)\s+(?:la\s+)?(?:radio|emisora)\b")
_RADIO_VOL = re.compile(r"\b(sube|subele|baja|bajale)(?:le)?\s+(?:el volumen )?(?:a |de )?(?:la )?(?:radio|emisora)\b")
_RADIO_WHAT = re.compile(r"\bque (?:emisora|radio) (?:suena|es|esta sonando|tienes puesta)\b")


def radio_find(query, genre=""):
    """Busca emisoras en Radio Browser (directorio abierto). → [{"name", "url"}] (primero las de Colombia)."""
    out = []
    for cc in ("CO", ""):                              # primero las de Colombia; si no hay, de cualquier país
        params = {"hidebroken": "true", "order": "clickcount", "reverse": "true", "limit": "6"}
        params["tag" if genre else "name"] = genre or query
        if cc:
            params["countrycode"] = cc
        elif genre:
            params["language"] = "spanish"
        for host in RADIO_HOSTS:
            try:
                req = urllib.request.Request(f"https://{host}/json/stations/search?" + urllib.parse.urlencode(params),
                                             headers={"User-Agent": f"Jarvis/{J.VERSION}"})
                with urllib.request.urlopen(req, timeout=6) as r:
                    data = json.loads(r.read().decode("utf-8", "replace"))
                out += [{"name": (s.get("name") or "").strip()[:60], "url": s.get("url_resolved") or s.get("url")} for s in data
                        if (s.get("url_resolved") or s.get("url"))]
                break
            except Exception:
                continue
        if out:
            break
    return out


def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""


def _radio_loop(url, name):
    """ffmpeg decodifica la emisora y el sonido sale por el parlante. Mientras Jarvis habla, la radio baja sola."""
    import sounddevice as sd
    proc = subprocess.Popen([J._ffmpeg(), "-loglevel", "quiet", "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
                             "-i", url, "-vn", "-f", "s16le", "-ar", "44100", "-ac", "2", "-"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                            creationflags=0x08000000 if J.IS_WIN else 0)
    _radio.update(proc=proc, name=name)
    got = False
    try:
        with sd.RawOutputStream(samplerate=44100, channels=2, dtype="int16", blocksize=0) as out:
            while not _radio["stop"].is_set():
                data = proc.stdout.read(8192)
                if not data:
                    break
                got = True
                vol = _radio["vol"] * (0.15 if (J.tts_playing.is_set() or J.state.get("mode") == "awaiting") else 1.0)
                if vol < 0.99:
                    a = array.array("h")
                    a.frombytes(data[:len(data) // 2 * 2])
                    data = array.array("h", [int(x * vol) for x in a]).tobytes()
                out.write(data)
    except Exception as e:
        J.log_terminal(f"Radio: {e}", "AVISO")
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        ended = not _radio["stop"].is_set()
        if _radio["proc"] is proc:
            _radio.update(proc=None, name="")
        if ended:
            J.notify(f"La emisora {name} dejó de transmitir." if got else f"No pude conectar con la emisora {name}. Prueba con otra.", "RADIO")


def radio_stop():
    if _radio["proc"] is None:
        return False
    _radio["stop"].set()
    try:
        _radio["proc"].kill()
    except Exception:
        pass
    th = _radio["thread"]
    if th is not None and th is not threading.current_thread():
        th.join(2)
    _radio.update(proc=None, name="")
    return True


def radio_play(query, genre=""):
    stations = J.radio_find(query, genre)
    if not stations:
        return ""
    J.radio_stop()
    st = stations[0]
    _radio["stop"] = threading.Event()
    if not J._ffmpeg():
        import webbrowser
        webbrowser.open(st["url"])                     # sin reproductor propio: la abre en el navegador
        return st["name"] + " (en el navegador)"
    th = threading.Thread(target=J._radio_loop, args=(st["url"], st["name"]), daemon=True, name="radio")
    _radio["thread"] = th
    th.start()
    return st["name"]


def radio_voice(text, t):
    if _RADIO_OFF.search(t):
        J.reply("Radio apagada." if J.radio_stop() else "No hay ninguna emisora sonando.", "RADIO")
        return True
    if _RADIO_WHAT.search(t):
        J.reply(f"Suena {_radio['name']}." if _radio["proc"] is not None else "No hay ninguna emisora sonando.", "RADIO")
        return True
    m = _RADIO_VOL.search(t)
    if m and _radio["proc"] is not None:
        up = m.group(1).startswith("sub")
        _radio["vol"] = min(1.0, _radio["vol"] + 0.2) if up else max(0.1, _radio["vol"] - 0.2)
        J.reply(f"Radio al {round(_radio['vol'] * 100)} por ciento.", "RADIO")
        return True
    m = _RADIO_ON.search(t)
    if not m:
        return False
    q = (m.group(1) or m.group(2) or "").strip()
    q = re.sub(r"^(?:musica|la musica)\s+", "", q).strip()
    if not q or re.search(r"\b(?:en spotify|en youtube|cancion|album|playlist|video)\b", t):
        return False
    if J.is_offline():
        J.reply("La radio en vivo necesita internet, y ahora no hay.", "RADIO")
        return True
    genre = GENEROS.get(q) or GENEROS.get(re.sub(r"^de ", "", q), "")

    def go():
        name = J.radio_play(q, genre)
        J.reply(f"Sonando {name}. Para quitarla di «apaga la radio»." if name else
                f"No encontré una emisora de «{q}». Prueba con el nombre exacto, por ejemplo «pon la emisora Caracol».", "RADIO")
    J.reply(f"Buscando {'una emisora de ' + q if genre else 'la emisora ' + q}…", "RADIO")
    if J.net["watch"]:
        J.start_job("Sintonizando la radio", go, name="radio-buscar")
    return True


# ============================================================================ MODO COCINA
_cook = {"recipe": None, "i": -1, "at": 0.0}
_COOK_ON = re.compile(r"\b(?:modo cocina|receta paso a paso|cocinemos|ayudame a cocinar|ensename a cocinar|guiame para cocinar)\b\s*(?:con|de|para|:)?\s*(.*)$|"
                      r"\b(?:receta de|como (?:se prepara|se hace|preparo|hago|cocino))\s+(.+?)\s+paso a paso\s*$")
_COOK_NEXT = re.compile(r"\b(?:siguiente paso|paso siguiente|que sigue|que mas sigue|continua(?:r)?(?: con)? la receta|ya lo hice|ya esta listo eso|listo el paso)\b|^(?:jarvis )?(?:siguiente|continua|listo)$")
_COOK_PREV = re.compile(r"\b(?:paso anterior|vuelve al paso anterior|devuelvete un paso|anterior)\b")
_COOK_REP = re.compile(r"\b(?:repite(?:me)?(?: el paso)?|otra vez|como era|que dijiste)\b")
_COOK_ING = re.compile(r"\b(?:ingredientes|que necesito|que lleva)\b")
_COOK_OFF = re.compile(r"\b(?:termina|cancela|sal de|salir de|cierra|deja|quita)\s+(?:la\s+|el\s+)?(?:receta|modo cocina|cocina)\b|\bya termine de cocinar\b")


def cook_fetch(dish):
    """La IA arma la receta en pasos cortos. → {"titulo", "porciones", "ingredientes": [...], "pasos": [{"texto", "minutos"}]}"""
    sys_msg = ("Eres un cocinero que guía por voz. Devuelve SOLO un JSON con esta forma: "
               '{"titulo": "...", "porciones": 4, "ingredientes": ["2 tazas de arroz", "..."], '
               '"pasos": [{"texto": "una sola acción, en una o dos frases cortas", "minutos": 0}]}. '
               "Entre 5 y 10 pasos. «minutos» es el tiempo de espera o cocción de ese paso (0 si no hay que esperar). "
               "Ingredientes que se consiguen en Colombia, con cantidades. En español.")
    raw = J.ai_chat([{"role": "system", "content": sys_msg}, {"role": "user", "content": f"Receta: {dish}"}], json_mode=True, max_tokens=1100)
    data = J._extract_json(raw)
    steps = [{"texto": str(p.get("texto", "")).strip(), "minutos": int(float(p.get("minutos") or 0))} for p in data.get("pasos", [])
             if isinstance(p, dict) and str(p.get("texto", "")).strip()]
    if len(steps) < 2:
        raise ValueError("la receta llegó incompleta")
    return {"titulo": str(data.get("titulo") or dish).strip()[:80], "porciones": data.get("porciones") or "",
            "ingredientes": [str(x).strip() for x in data.get("ingredientes", []) if str(x).strip()][:25], "pasos": steps[:14]}


def _cook_say(i):
    r = _cook["recipe"]
    step = r["pasos"][i]
    _cook.update(i=i, at=time.time())
    tail = ""
    if step["minutos"] > 0:
        try:
            J.add_timer(step["minutos"] * 60, f"{r['titulo']}: paso {i + 1}")
            tail = f" Te puse un temporizador de {step['minutos']} minutos."
        except Exception:
            tail = f" Son unos {step['minutos']} minutos."
    last = i == len(r["pasos"]) - 1
    J.reply(f"Paso {i + 1} de {len(r['pasos'])}: {step['texto']}{tail}" + (" Es el último paso. ¡Buen provecho!" if last else ""), "COCINA")
    if last:
        _cook.update(recipe=None, i=-1)


def cook_active():
    return _cook["recipe"] is not None and time.time() - _cook["at"] < 3 * 3600


def cook_voice(text, t):
    if cook_active():
        if _COOK_OFF.search(t):
            _cook.update(recipe=None, i=-1)
            J.reply("Listo, cierro la receta.", "COCINA")
            return True
        r = _cook["recipe"]
        if _COOK_ING.search(t) and len(t.split()) <= 6:
            J.reply("Ingredientes: " + "; ".join(r["ingredientes"]) + ".", "COCINA")
            return True
        if _COOK_PREV.search(t) and len(t.split()) <= 6:
            _cook_say(max(0, _cook["i"] - 1))
            return True
        if _COOK_REP.search(t) and len(t.split()) <= 5:
            _cook_say(max(0, _cook["i"]))
            return True
        if _COOK_NEXT.search(t) and len(t.split()) <= 6:
            _cook_say(min(len(r["pasos"]) - 1, _cook["i"] + 1))
            return True
    m = _COOK_ON.search(t)
    if not m:
        return False
    dish = (m.group(1) or m.group(2) or "").strip(" .")
    dish = re.sub(r"^(?:un|una|unos|unas|el|la|los|las)\s+", "", dish)
    if not dish:
        J.reply("¿Qué vamos a preparar? Di, por ejemplo, «modo cocina arroz con pollo».", "COCINA")
        return True
    J.reply(f"Busco la receta de {dish}; un momento.", "COCINA")
    try:
        r = J.cook_fetch(dish)
    except J.AIError as e:
        J.reply(J.ai_error_reply(e), "COCINA")
        return True
    except Exception as e:
        J.reply(f"No pude armar esa receta ({e}). Pídemela otra vez.", "COCINA")
        return True
    _cook.update(recipe=r, i=-1, at=time.time())
    por = f" para {r['porciones']} porciones" if r["porciones"] else ""
    J.show(f"**{r['titulo']}**{por}\n\nIngredientes:\n" + "\n".join("- " + x for x in r["ingredientes"]) + "\n\nPasos:\n"
                + "\n".join(f"{n}. {p['texto']}" + (f" ({p['minutos']} min)" if p["minutos"] else "") for n, p in enumerate(r["pasos"], 1)), "COCINA")
    J.speak(f"{r['titulo']}{por}. Necesitas {len(r['ingredientes'])} ingredientes; están en la pantalla. Son {len(r['pasos'])} pasos. "
            "Di «siguiente paso» para empezar, «repite» o «los ingredientes».")
    return True


# ============================================================================ INGLÉS
EN_VOICE = "en-US-GuyNeural"
_eng = {"quiz": None, "talk_until": 0.0}
_ENG_QUIZ = re.compile(r"^(?:jarvis )?(?:hazme |hagamos |quiero |juguemos )?(?:un |al )?(?:quiz|juego) de (?:vocabulario (?:de|en) |palabras (?:de|en) )?ingles$|"
                       r"\bpreguntame (?:palabras|vocabulario) (?:de|en) ingles\b")
_ENG_TALK = re.compile(r"\b(?:practiquemos|quiero practicar|hablemos|conversemos|ayudame a practicar)\s+(?:(?:mi|el|en)\s+)?ingles\b")
_ENG_OFF = re.compile(r"\b(?:termin(?:a|emos|ar)|para|deja|salir de|sal de|stop|fin de|acaba|acabemos)\s+(?:con\s+)?(?:la\s+|el\s+)?(?:practica|clase|ingles|quiz|conversacion)\b|\bya no mas ingles\b|\bvolvamos al espanol\b|^(?:that s all|bye|goodbye|stop)$")


def _say_en(text):
    if J.is_offline() or J.edge_tts is None:
        J.speak(text)
    else:
        J.speak(text, voice=EN_VOICE, backend="edge")


def _quiz_ask():
    q = _eng["quiz"]
    en, es, _ex = q["items"][q["i"]]
    J.show(f"Pregunta {q['i'] + 1} de {len(q['items'])}: ¿qué significa **{en}**?", "INGLÉS")
    if not getattr(J._tl, "quiet", False):
        J.speak(f"Pregunta {q['i'] + 1}. ¿Qué significa…")
        _say_en(en)


def _quiz_check(answer, es):
    a = J.normalize(answer)
    a = re.sub(r"^(?:significa|es|quiere decir|creo que(?: es)?|seria)\s+", "", a).strip()
    for opt in re.split(r"\s*,\s*", es):
        o = J.normalize(re.sub(r"\(.*?\)", "", opt)).strip()
        if o and (a == o or (len(a) >= 4 and (a in o or o in a))):
            return True
    return False


def english_voice(text, t):
    q = _eng["quiz"]
    if q is not None or time.time() < _eng["talk_until"]:
        if _ENG_OFF.search(t):
            had = q
            _eng.update(quiz=None, talk_until=0.0)
            J.reply(f"Listo. Acertaste {had['ok']} de {had['i']}." if had else "Listo, volvemos al español. ¡Buen trabajo!", "INGLÉS")
            return True
    if q is not None:
        en, es, ex = q["items"][q["i"]]
        ok = _quiz_check(text, es)
        q["ok"] += ok
        q["i"] += 1
        fin = q["i"] >= len(q["items"])
        msg = ("¡Correcto! " if ok else f"Casi: «{en}» significa {es}. ") + f"Ejemplo: {ex}"
        if fin:
            _eng["quiz"] = None
            J.reply(msg + f" Terminamos: {q['ok']} de {len(q['items'])}." + (" ¡Excelente!" if q["ok"] >= 4 else " Sigue practicando: mañana hay otra palabra del día."), "INGLÉS")
        else:
            J.reply(msg, "INGLÉS")
            _quiz_ask()
        return True
    if time.time() < _eng["talk_until"]:
        return _talk_turn(text)
    w = instante.word_of_day(instante.norm(text), rng=random)
    if w:
        en, es, ex = w
        J.show(f"Palabra del día: **{en}** — {es}.\n\n_{ex}_", "INGLÉS")
        if not getattr(J._tl, "quiet", False):
            J.speak("La palabra del día es…")
            _say_en(en)
            J.speak(f"Significa {es}. Por ejemplo:")
            _say_en(ex)
        return True
    if _ENG_QUIZ.search(t):
        items = random.sample(instante.WORDS, 5)
        _eng["quiz"] = {"items": items, "i": 0, "ok": 0}
        J.reply("Quiz de inglés: cinco palabras. Te digo la palabra y me dices qué significa. Para salir di «termina el quiz».", "INGLÉS")
        _quiz_ask()
        return True
    if _ENG_TALK.search(t):
        _eng["talk_until"] = time.time() + 600
        J.show("Práctica de inglés: escríbeme o háblame en inglés y te respondo en inglés, con la corrección en español. "
               "Para salir: «terminemos la práctica». Si hablas por voz y no te entiendo bien, escribe: el oído de Jarvis está ajustado al español.", "INGLÉS")
        if not getattr(J._tl, "quiet", False):
            J.speak("Empecemos. Para terminar di: terminemos la práctica.")
            _say_en("Hi! How was your day today?")
        return True
    return False


def _talk_turn(text):
    _eng["talk_until"] = time.time() + 600
    sys_msg = ('You are a friendly English tutor for a Spanish speaker (level A2-B1). Reply ONLY with JSON: '
               '{"reply": "your short answer in simple English, ending with one question", '
               '"fix": "si el estudiante cometió un error, la frase corregida y una explicación de una línea EN ESPAÑOL; si no hubo error, cadena vacía"}')
    try:
        data = J._extract_json(J.ai_chat([{"role": "system", "content": sys_msg}, {"role": "user", "content": text}], json_mode=True, max_tokens=220))
    except J.AIError as e:
        J.reply(J.ai_error_reply(e), "INGLÉS")
        return True
    except Exception:
        J.reply("No te entendí; dímelo otra vez.", "INGLÉS")
        return True
    reply, fix = str(data.get("reply") or "").strip(), str(data.get("fix") or "").strip()
    J.show(reply + (f"\n\n✎ {fix}" if fix else ""), "INGLÉS")
    if not getattr(J._tl, "quiet", False):
        if fix:
            J.speak("Una corrección: " + fix)
        _say_en(reply)
    return True


# ============================================================================ CUENTOS
_STORY = re.compile(r"\b(?:cuentame|cuentanos|narrame|narra|leeme|inventa(?:me)?|dime|quiero)\s+(?:un|otro|una)\s+(?:cuento|historia|fabula)\b\s*(.*)$|^(?:jarvis\s+)?(?:un\s+)?cuento para dormir\b\s*(.*)$")


def story_text(topic, age):
    who = f"para un niño o niña de {age} años" if age else "para toda la familia"
    sys_msg = (f"Eres un narrador de cuentos en español. Escribe un cuento original {who}, para leer en voz alta en unos 2 minutos: "
               "entre 220 y 300 palabras, frases cortas, un personaje con nombre, un pequeño problema y un final tranquilo con una enseñanza suave. "
               "Sin violencia ni sustos. Empieza con el título en la primera línea. Sin asteriscos ni listas.")
    return J.ai_chat([{"role": "system", "content": sys_msg}, {"role": "user", "content": f"Tema: {topic or 'el que quieras'}"}], max_tokens=700)


def story_voice(text, t):
    m = _STORY.search(t)
    if not m:
        return False
    rest = (m.group(1) or m.group(2) or "").strip()
    age = None
    ma = re.search(r"\bde (\d{1,2}) anos?\b", rest)
    if ma:
        age = max(2, min(int(ma.group(1)), 15))
    topic = re.sub(r"\bpara (?:un|una|mi|el|la|los|las)?\s*(?:nin[oa]s?|hij[oa]s?|bebe|sobrin[oa]s?|niet[oa]s?|estudiantes?)?\s*(?:de \d{1,2} anos?)?\b|\bpara dormir\b|\bcorto\b", " ", rest)
    topic = re.sub(r"^(?:de|del|sobre|acerca de|con)\s+", "", topic.strip()).strip(" .")
    J.reply("Voy a pensar un cuento…" if not topic else f"Un cuento de {topic}; ya te lo cuento…", "CUENTO")
    try:
        out = J.story_text(topic, age).strip()
    except J.AIError as e:
        J.reply(J.ai_error_reply(e), "CUENTO")
        return True
    if not out:
        J.reply("No se me ocurrió ninguno; pídemelo otra vez.", "CUENTO")
        return True
    J.show(out, "CUENTO")
    if not getattr(J._tl, "quiet", False):
        for para in [p.strip() for p in re.split(r"\n+", out) if p.strip()]:
            for chunk in re.findall(r".{1,380}(?:[.!?…]|$)\s*", para, flags=re.S):      # trozos cortos: la voz no los recorta
                if chunk.strip():
                    J.speak(chunk.strip(), rate=-8)
    return True


# ============================================================================ TODO JUNTO
def daily_voice(text, t):
    """Lo de 12.21 que no necesita ir antes que nada. → True si la atendió."""
    return (pausa_voice(text, t) or english_voice(text, t) or cook_voice(text, t) or qr_voice(text, t) or radio_voice(text, t)
            or story_voice(text, t))


def daily_state_active():
    """¿Hay un quiz, una práctica o una receta en curso? (lo que digas es para eso, antes que para otra orden)."""
    return _eng["quiz"] is not None or time.time() < _eng["talk_until"]


__all__ = ['EN_VOICE', 'GENEROS', 'PAUSAS', 'RADIO_HOSTS', '_COOK_ING', '_COOK_NEXT', '_COOK_OFF', '_COOK_ON', '_COOK_PREV', '_COOK_REP', '_ENG_OFF', '_ENG_QUIZ',
           '_ENG_TALK', '_PAUSA', '_PAUSA_STOP', '_QR', '_QR_WIFI', '_RADIO_OFF', '_RADIO_ON', '_RADIO_VOL', '_RADIO_WHAT', '_RESP', '_STORY', '_cook',
           '_cook_say', '_eng', '_ffmpeg', '_pausa', '_pausa_run', '_quiz_ask', '_quiz_check', '_radio', '_radio_loop', '_say_en', '_say_wait',
           '_talk_turn', 'cook_active', 'cook_fetch', 'cook_voice', 'daily_state_active', 'daily_voice', 'english_voice', 'make_qr', 'pausa_voice',
           'qr_payload', 'qr_voice', 'radio_find', 'radio_play', 'radio_stop', 'radio_voice', 'show', 'story_text', 'story_voice']
