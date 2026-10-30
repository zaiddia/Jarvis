"""Escucha continua (Vosk), palabra de activación y reconocimiento en dos etapas.

Parte de Jarvis (antes dentro de jarvis.py). Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import array
import importlib.util
import json
import os
import queue
import rapidez
import re
import skills
import threading
import time

from nucleo import J


# =============================================================================
# ESCUCHA CONTINUA (VOSK)
# =============================================================================
mic_restart = threading.Event()
_pa = None
_pa_lock = threading.Lock()


def _get_pa():
    with J._pa_lock:
        if J._pa is None:
            J._pa = J.pyaudio.PyAudio()
        return J._pa


def list_mics():
    if J.pyaudio is None:
        return []
    pa = J._get_pa()
    devices = []
    for i in range(pa.get_device_count()):
        try:
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                api = pa.get_host_api_info_by_index(info["hostApi"])["name"]
                devices.append({"index": i, "name": f"{info['name']} · {api}"})
        except Exception:
            continue
    return devices


convo = {"armed": False, "chain": 0, "kind": ""}
FOLLOWUP_MAX_CHAIN = 8                     # como mucho 8 órdenes seguidas sin decir «Jarvis»
_CMD_START = re.compile(
    r"^(?:y |ahora |tambien |luego |despues |ya |oye |porfa |por favor )*"
    r"(?:abr|cierr|cerr|pon|quit|sub|baj|busc|mand|envi|escrib|cre|hac|haz|dim|di |dec|cuent|"
    r"explic|recuerd|apag|encend|activ|desactiv|muestr|mostr|le[ea]|reproduc|paus|para|deten|"
    r"silenci|guard|copi|peg|selecciona|minimiz|maximiz|cambi|ve |ir |vamos|llam|program|agend|"
    r"marc|borr|elimin|tom|captur|traduc|calcul|resum|revis|compart|inici|empez|termin|fin|"
    r"que |cual|cuant|como |cuando |donde |quien|por que|sabes|puedes|me |necesito|quiero)")


def _looks_like_command(text):
    """Para lo que llega SIN decir «Jarvis»: ¿suena a una orden o pregunta para él?
    (evita que una conversación o un video de fondo se tome como orden)."""
    t = J.normalize(text)
    if not t:
        return False
    try:
        if skills.parse(text):
            return True
    except Exception:
        pass
    return bool(J._CMD_START.match(t)) or text.strip().endswith("?")


def open_followup():
    """Después de contestar una orden hablada, escucha unos segundos más: puedes seguir
    («y ahora ciérralo», «súbele el volumen») sin repetir «Jarvis»."""
    secs = J.settings["followup_listen"]
    if not J.convo["armed"] or not secs or J.convo["chain"] >= J.FOLLOWUP_MAX_CHAIN or J.dictation_on.is_set():
        return
    if J.thinking > 0:
        return                                         # aún está generando la respuesta
    J.convo["armed"] = False
    J.wake_until = time.time() + secs
    J.convo["kind"] = "followup"
    J.refresh_mode()
    threading.Timer(secs + 0.1, J.refresh_mode).start()


def activate_listening(allow_live=True):
    """Como decir «Jarvis»: la siguiente frase se toma como orden."""
    if allow_live and J.live_mode() == "vivo" and J.live_start():
        J.play_sound(J._beep_path(), 1)
        return
    J.wake_until = time.time() + J.settings["wake_window"]
    J.refresh_mode()
    J.convo["kind"] = "wake"
    threading.Timer(J.settings["wake_window"] + 0.1, J.refresh_mode).start()
    J.speak("¿Sí?", prompt=True)                     # mientras suena, ya te está escuchando


# -----------------------------------------------------------------------------
# ESCUCHA EN DOS ETAPAS
# 1) Vosk escucha todo en el PC (gratis, sin enviar nada) solo para saber si le hablas a Jarvis.
# 2) Si la frase es para Jarvis, ese mismo audio se transcribe con un reconocedor preciso
#    (Gemini con tu clave, o Whisper en local) y se le dan las palabras que suelen aparecer
#    (contactos, apps, órdenes). Lo que se habla en el ambiente nunca sale del PC.
# -----------------------------------------------------------------------------
voice_queue = queue.Queue()
_WAKE_FILLERS = {"hola", "oye", "oiga", "ey", "hey", "eh", "ya", "la", "el", "a", "bueno",
                 "ok", "okay", "vale", "ahora", "y", "pues", "mira"}
_STT_WORDS = ("WhatsApp, Telegram, Spotify, YouTube, Google, Chrome, Edge, Word, Excel, PowerPoint, "
              "Gemini, temporizador, recordatorio, volumen, brillo, captura de pantalla, diapositiva, "
              "videobeam, dictado, modo sigilo, mostrar panel, calculadora, explorador de archivos, pestaña, navegador")


def _match_wake(text):
    """¿La frase va dirigida a Jarvis? Tolera cómo suele transcribirse la palabra de
    activación («yarvis», «jarvi»...) y muletillas delante («hola jarvis», «ya jarvis»).
    Devuelve el resto de la frase (puede ser "") o None si no va dirigida a Jarvis."""
    import difflib
    orig = text.split()
    words = J.normalize(text).split()
    for w in J.get_wake_words():
        ww = J.normalize(w).split()
        n = len(ww)
        for start in range(0, min(3, len(words))):
            cand = " ".join(words[start:start + n])
            if not cand:
                continue
            ok = cand == " ".join(ww) or (len(cand) >= 4 and len(" ".join(ww)) >= 5 and
                                          difflib.SequenceMatcher(None, cand, " ".join(ww)).ratio() >= 0.8)
            if ok and all(x in J._WAKE_FILLERS for x in words[:start]):
                rest = orig[start + n:] if len(orig) == len(words) else words[start + n:]
                return " ".join(rest).strip(" ,.:;")
    # «abre Word, Jarvis» / «oye, abre Word Jarvis»: el nombre exacto en cualquier lugar
    for w in J.get_wake_words():
        ww = J.normalize(w).split()
        n = len(ww)
        if n != 1 or len(ww[0]) < 5:
            continue
        for i in range(len(words)):
            if words[i] == ww[0]:
                src = orig if len(orig) == len(words) else words
                rest = [x for j, x in enumerate(src) if j != i]
                return " ".join(rest).strip(" ,.:;¿?¡!")
    return None


def _stt_vocab_sentence():
    contacts = list(skills._parse_contacts().keys())[:25] if hasattr(skills, "_parse_contacts") else []
    wake = ", ".join(J.get_wake_words()) or "Jarvis"
    extra = f" Contactos: {', '.join(c.title() for c in contacts)}." if contacts else ""
    return f"Órdenes para el asistente {wake.title()}: {J._STT_WORDS}.{extra}"


def _wav_bytes(raw, rate=16000):
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(raw)
    return buf.getvalue()


def _gemini_for_stt():
    """Configuración de Gemini para transcribir (sirve aunque la IA elegida sea otra)."""
    cfg = J._ai_cfg({"ai_provider": "gemini"})
    return cfg if cfg["key"] else None


_whisper_refiner = {"model": None, "size": None, "failed": False}


def _whisper_transcribe(raw):
    if J._whisper_refiner["failed"]:
        return None
    try:
        size = J.settings["whisper_model"]
        if J._whisper_refiner["model"] is None or J._whisper_refiner["size"] != size:
            from faster_whisper import WhisperModel
            J._whisper_refiner.update(model=WhisperModel(size, device="cpu", compute_type="int8"), size=size)
        import numpy as np
        audio = np.frombuffer(raw, dtype=np.int16).astype("float32") / 32768.0
        segs, _ = J._whisper_refiner["model"].transcribe(
            audio, language="es", beam_size=1, vad_filter=False, initial_prompt=J._stt_vocab_sentence())
        return " ".join(sg.text for sg in segs).strip()
    except ImportError:
        J._whisper_refiner["failed"] = True
        return None
    except Exception as e:
        J.log_terminal(f"Whisper no pudo transcribir: {e}", "AVISO")
        return None


def _gemini_transcribe(raw):
    cfg = J._gemini_for_stt()
    if not cfg:
        return None
    prompt = ("Transcribe exactamente lo que dice la persona en este audio, en español de Colombia. "
              "Le está hablando a su asistente de voz en un computador con Windows. "
              f"Palabras que pueden aparecer: {J._stt_vocab_sentence()} "
              "Devuelve SOLO la transcripción, sin comillas ni comentarios. "
              "Si no hay ninguna voz clara, devuelve exactamente: (nada)")
    body_msgs = [{"role": "user", "content": prompt}]

    def call(c):
        url = f"{J.GEMINI_BASE}/models/{c['model']}:generateContent"
        data = J._post(url, J._gemini_headers(c),
                     J._gemini_body(c, body_msgs, 300, audio_wav=J._wav_bytes(raw), temperature=0),
                     J._GEMINI_OPTIONAL, timeout=12)
        return J._gemini_text(data)
    try:
        out = J._with_fallback(cfg, call)
    except J.AIError as e:
        J.log_terminal(f"Gemini no pudo transcribir ({e.why}); uso el reconocimiento local.", "AVISO")
        return None
    out = re.sub(r"^\s*(transcripci[oó]n|texto)\s*:\s*", "", out or "", flags=re.I).strip().strip('"«»“”')
    return "" if out.lower().strip(" .") == "(nada)" else out


def stt_refine_mode():
    """Qué 2ª etapa se usará ahora: 'gemini', 'whisper' u 'off'."""
    want = J.settings["stt_refine"]
    if want == "off":
        return "off"
    if want in ("auto", "gemini") and J._gemini_for_stt() and not J.is_offline():
        return "gemini"
    if want in ("auto", "whisper") and J.settings["stt_backend"] != "whisper":
        try:
            import importlib.util
            if importlib.util.find_spec("faster_whisper"):
                return "whisper"
        except Exception:
            pass
    return "off"


def refine_speech(raw, fallback):
    """Transcribe bien una frase dirigida a Jarvis. Si no se puede, devuelve la de Vosk."""
    if not raw or len(raw) < 16000 * 2 * 0.4:            # menos de 0,4 s: nada que mejorar
        return fallback
    mode = J.stt_refine_mode()
    if mode == "off":
        return fallback
    t0 = time.time()
    out = J._gemini_transcribe(raw) if mode == "gemini" else J._whisper_transcribe(raw)
    if out is None or out == "":
        return fallback
    if J.normalize(out) != J.normalize(fallback):
        J.log_terminal(f"Entendido con {mode.title()} en {time.time() - t0:.1f} s "
                     f"(el reconocimiento local había oído: «{fallback}»)", "AUDIO")
    return out


def _voice_worker():
    while True:
        item = J.voice_queue.get()
        try:
            J.handle_voice(*item)
        except Exception as e:
            J.log_terminal(f"Error procesando la voz: {e}", "ERROR")


def handle_voice(text, raw=None, started=None):
    J.socketio.emit("heard", {"text": text})
    # En dictado, todo lo que se oye se escribe sin necesidad de decir «Jarvis».
    if J.dictation_on.is_set():
        text = J.refine_speech(raw, text)
        J.log_terminal(f'"{text}"', "VOZ")
        J.command_queue.put(text)
        return
    # Descarta transcripciones demasiado cortas (ruidos, sílabas sueltas del ambiente).
    if len(J.normalize(text)) < J.settings["min_command_chars"]:
        J.log_terminal(f'"{text}"', "VOZ")
        return

    # La ventana cuenta desde que EMPEZASTE a hablar: una orden larga que termina un poco
    # después de que se cerró la ventana sigue valiendo.
    t0 = min(time.time(), started) if started else time.time()
    in_wake = t0 < J.wake_until
    asked = ((J.pending["skill"] and t0 < J.pending["expires"])
             or (J.followup["skill"] and t0 < J.followup["expires"]))
    window_open = in_wake or asked
    via_followup = in_wake and J.convo["kind"] == "followup" and not asked
    wake_rest = None
    if J.settings["require_hotkey"]:                     # solo tras Ctrl+Alt+Espacio
        if time.time() >= J.wake_until:
            J.log_terminal(f'"{text}"', "VOZ")
            return
    elif J.settings["wake_word_enabled"]:
        wake_rest = J._match_wake(text)
        if wake_rest is None and J.normalize(text) in ("mostrar panel", "muestra el panel", "muestra panel",
                                                     "mostrar el panel", "abre el panel"):
            J.log_terminal(f'"{text}"', "VOZ")             # inofensivo: funciona sin decir «Jarvis»
            J.submit_command("mostrar panel", "voz")
            return
        if wake_rest is None and not window_open:      # conversación del ambiente: no sale del PC
            late = 0 < t0 - J.wake_until < 8
            J.log_terminal(f'"{text}"' + ("  (llegó después de que dejé de escucharte: di «Jarvis» y la orden "
                                        "seguidas, o sube «Tiempo de espera» en Ajustes › Escucha)" if late else ""), "VOZ")
            return
        if wake_rest is not None and not asked and J.live_mode() == "vivo":
            J.log_terminal(f'"{text}"', "VOZ")
            # con orden incluida («Jarvis, abre Word»), Gemini oye esa misma grabación
            if J.live_start(initial_audio=raw if wake_rest else None):
                if not wake_rest:
                    J.play_sound(J._beep_path(), 1)
                return
        if wake_rest == "":                            # solo dijo «Jarvis»
            J.log_terminal(f'"{text}"', "VOZ")
            J.activate_listening()
            return

    # La frase es para Jarvis: 2ª etapa con el reconocedor preciso.
    rapidez.begin("voz")
    final = J.refine_speech(raw, text)
    rapidez.mark("transcripcion")
    if J.settings["wake_word_enabled"]:                  # quita «Jarvis» de la versión precisa
        rest = J._match_wake(final)
        if rest:
            final = rest
        elif rest == "":
            final = wake_rest or ""
    final = final.strip().rstrip(".").strip()
    if wake_rest is None and in_wake and not asked:
        # el «¿Sí?» de Jarvis puede colarse al principio de la grabación
        final = re.sub(r"^\s*[¿¡]?\s*s[ií]\s*[?!,.]*\s+(?=\S)", "", final, flags=re.I)
        if J.normalize(final) in ("si", "si si", "aja"):
            return                                     # solo se oyó su propio «¿Sí?»: sigue esperando
    J.log_terminal(f'"{final}"', "VOZ")
    if not final.strip():
        if via_followup:
            return                                     # ruido mientras esperaba: no insiste
        J.activate_listening()
        return
    if via_followup and wake_rest is None and (len(J.normalize(final).split()) < 2 or not J._looks_like_command(final)):
        J.log_terminal("(no parece una orden para mí; si lo era, empieza con «Jarvis»)", "VOZ")
        return
    J.convo["chain"] = J.convo["chain"] + 1 if (via_followup and wake_rest is None) else 0
    J.convo["armed"] = True
    J.wake_until = 0.0
    J.convo["kind"] = ""
    J.refresh_mode()
    J.submit_command(final, "voz")


def _passes_gate(text, peak):
    gate = J.settings["mic_sensitivity"] / 100
    if gate and peak < gate and J.settings["wake_word_enabled"] and J._match_wake(text) is not None:
        return True                                    # te llamó por su nombre: siempre cuenta
    if gate and peak < gate:
        J.log_terminal(f"Ignorado (sonido lejano/flojo): «{text}»", "AUDIO")
        return False
    return True


class VoskEngine:
    """Reconocimiento en streaming con Vosk (ligero, siempre disponible)."""
    label = "VOSK"

    def __init__(self):
        model_path = J.get_resource_path("model_es")
        if J.Model is None:
            raise RuntimeError("Vosk no está instalado.")
        if not os.path.isdir(model_path):
            raise RuntimeError(f"Modelo Vosk no encontrado en {model_path}. Ejecuta descargar_modelo.py.")
        J.SetLogLevel(-1)
        self.rec = J.KaldiRecognizer(J.Model(model_path), 16000)
        self.utt_peak = 0.0
        self.audio = bytearray()          # audio de la frase en curso (para la 2ª etapa)
        self.last_audio = b""
        self.speech_start = None          # cuándo empezaste a hablar en esta frase
        self.last_start = None

    MAX_AUDIO = 16000 * 2 * 20            # guarda como mucho 20 s

    def feed(self, data, peak):
        self.utt_peak = max(self.utt_peak, peak)
        self.audio += data
        if len(self.audio) > self.MAX_AUDIO:
            del self.audio[:len(self.audio) - self.MAX_AUDIO]
        if self.rec.AcceptWaveform(data):
            text = json.loads(self.rec.Result()).get("text", "").strip()
            up, self.utt_peak = self.utt_peak, 0.0
            self.last_audio, self.audio = bytes(self.audio), bytearray()
            self.last_start, self.speech_start = self.speech_start or time.time(), None
            if text and J._passes_gate(text, up):
                return text
        elif self.speech_start is None:
            try:
                if json.loads(self.rec.PartialResult()).get("partial", "").strip():
                    self.speech_start = time.time() - 0.3
            except ValueError:
                pass
        return None

    def reset(self):
        self.rec.Reset()
        self.utt_peak = 0.0
        self.audio = bytearray()
        self.speech_start = None


class WhisperEngine:
    """Reconocimiento con faster-whisper (más preciso). Trocea por silencios (endpointing)."""
    label = "WHISPER"
    CHUNK_SEC = 0.25          # cada lectura son 4000 muestras a 16 kHz

    def __init__(self):
        from faster_whisper import WhisperModel
        import numpy as np
        self.np = np
        size = J.settings["whisper_model"]
        self.model = WhisperModel(size, device="cpu", compute_type="int8")
        self.buf = bytearray()
        self.speaking = False
        self.silence = 0
        self.speech_chunks = 0
        self.utt_peak = 0.0
        self.last_audio = b""

    def feed(self, data, peak):
        thr = max(0.02, J.settings["mic_sensitivity"] / 100)     # umbral de habla
        if peak >= thr:
            if not self.speaking:
                self.speech_start = time.time() - self.CHUNK_SEC
            self.speaking = True
            self.silence = 0
            self.speech_chunks += 1
            self.buf += data
            self.utt_peak = max(self.utt_peak, peak)
        elif self.speaking:
            self.buf += data
            self.silence += 1
            if self.silence >= 3:                               # ~0.75 s de silencio -> fin de frase
                return self._finish()
        if len(self.buf) > 16000 * 2 * 15:                      # tope de 15 s
            return self._finish()
        return None

    def _finish(self):
        raw = bytes(self.buf)
        self.last_audio = raw
        self.last_start = getattr(self, "speech_start", None) or time.time()
        up = self.utt_peak
        speech = self.speech_chunks
        self.reset()
        if speech < 2:                                          # menos de ~0,5 s de voz real: ruido
            return None
        audio = self.np.frombuffer(raw, dtype=self.np.int16).astype("float32") / 32768.0
        try:
            segs, _ = self.model.transcribe(audio, language="es", beam_size=1, vad_filter=False,
                                            initial_prompt=J._stt_vocab_sentence())
            text = " ".join(s.text for s in segs).strip()
        except Exception as e:
            J.log_terminal(f"Fallo de Whisper: {e}", "ERROR")
            return None
        if text and J._passes_gate(text, up):
            return text
        return None

    def reset(self):
        self.buf = bytearray()
        self.speaking = False
        self.silence = 0
        self.speech_chunks = 0
        self.utt_peak = 0.0


def make_stt_engine():
    if J.settings["stt_backend"] == "whisper":
        try:
            eng = J.WhisperEngine()
            J.log_terminal(f"Reconocimiento con Whisper ({J.settings['whisper_model']}).", "SISTEMA")
            return eng
        except Exception as e:
            J.log_terminal(f"No se pudo iniciar Whisper ({e}). Uso Vosk.", "AVISO")
    return J.VoskEngine()


_STOP_ALONE = {"basta", "callate", "silencio", "detente", "deja de hablar", "para de hablar",
               "ya basta", "ya callate", "para ya", "para para"}


def _is_echo(t):
    """¿Lo que oyó el micrófono es su propia voz saliendo por los parlantes?"""
    import difflib
    words = t.split()
    if not words:
        return True
    now = time.time()
    for ts, said in list(J.tts_recent):
        if now - ts > 25:
            continue
        if t in said:
            return True
        sw = said.split()
        n = len(words)
        for i in range(0, max(1, len(sw) - n + 1)):
            if difflib.SequenceMatcher(None, " ".join(sw[i:i + n]), t).ratio() >= 0.78:
                return True
    return False


def _barge_in(text, raw):
    """Oyó algo mientras Jarvis hablaba. Lo interrumpe solo si va dirigido a él."""
    t = J.normalize(text)
    if J._is_echo(t):
        return False
    rest = J._match_wake(text) if J.settings["wake_word_enabled"] else None
    stop_alone = t in J._STOP_ALONE
    if rest is None and not stop_alone:
        return False                                   # ruido o conversación del salón
    J.stop_speech(log=False)
    J.log_terminal(f'Interrumpido: «{text}»', "VOZ")
    rest_n = J.normalize(rest or "")
    if stop_alone or J.is_stop_command(rest_n) or rest_n in J._STOP_ALONE or rest_n in ("ya", "ok", "gracias", "listo"):
        return True                                    # solo quería que se callara
    J.voice_queue.put((text, raw))                       # una pregunta nueva: se atiende ya
    return True


def audio_loop():
    if J.pyaudio is None:
        J.set_state(mic="error")
        J.log_terminal("Falta sounddevice (o PyAudio): solo funcionarán los comandos escritos.", "AVISO")
        return
    try:
        engine = J.make_stt_engine()
    except Exception as e:
        J.set_state(mic="error")
        J.log_terminal(f"No se pudo iniciar el reconocimiento de voz: {e}", "ERROR")
        return

    while True:
        J.mic_restart.clear()
        if not J.settings["mic_enabled"]:
            J.set_state(mic="off")
            J.socketio.emit("mic_level", {"v": 0})
            J.mic_restart.wait()
            try:
                engine = J.make_stt_engine()          # recarga por si cambió el motor en Ajustes
            except Exception:
                pass
            continue

        device = J.settings["mic_device"]
        try:
            engine.reset()
            kwargs = dict(format=J.pyaudio.paInt16, channels=1, rate=16000,
                          input=True, frames_per_buffer=4000)
            if device >= 0:
                kwargs["input_device_index"] = device
            stream = J._get_pa().open(**kwargs)
        except Exception as e:
            J.set_state(mic="error")
            J.log_terminal(f"No se pudo abrir el micrófono: {e}. Elige otro en Ajustes › Escucha.", "ERROR")
            J.mic_restart.wait(timeout=30)
            continue

        J.set_state(mic="on")
        J.log_terminal(f"Micrófono activo ({engine.label}).", "AUDIO")
        was_speaking = False
        last_level = 0.0
        try:
            while not J.mic_restart.is_set():
                data = stream.read(4000, exception_on_overflow=False)
                samples = array.array("h", data)
                peak = max(max(samples), -min(samples)) / 32768 if samples else 0
                now = time.time()
                if now - last_level > 0.12:
                    J.socketio.emit("mic_level", {"v": round(min(1.0, peak * 1.6), 3)})
                    J.orb_feed["level"] = round(min(1.0, peak * 1.6), 3)
                    last_level = now
                if J.live["active"] or J.live["connecting"]:
                    J.live_feed(data, peak)               # conversación en vivo: el audio va a Gemini
                    was_speaking = True
                    continue
                if J.tts_playing.is_set() and not J.tts_prompt.is_set():
                    was_speaking = True
                    if not J.settings["barge_in"] or J.dictation_on.is_set():
                        continue
                    # Sigue escuchando mientras habla, pero solo le hace caso si lo llamas
                    # («Jarvis, para», «Jarvis, ¿y mañana?») o le pides que se calle.
                    text = engine.feed(data, peak)
                    if text:
                        J._barge_in(text, getattr(engine, "last_audio", b""))
                    continue
                if was_speaking:
                    engine.reset()                  # descarta el eco de su propia voz
                    was_speaking = False
                text = engine.feed(data, peak)
                if text:
                    # La 2ª etapa (Gemini/Whisper) tarda ~1 s: se hace en otro hilo para no
                    # dejar de leer el micrófono mientras tanto.
                    J.voice_queue.put((text, getattr(engine, "last_audio", b""), getattr(engine, "last_start", None)))
        except Exception as e:
            J.set_state(mic="error")
            J.log_terminal(f"Lectura de micrófono interrumpida: {e}", "ERROR")
            time.sleep(2)
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        # Al reiniciar el micrófono (p. ej. cambio de motor en Ajustes), reconstruye el reconocedor.
        want_whisper = J.settings["stt_backend"] == "whisper"
        if want_whisper != isinstance(engine, J.WhisperEngine):
            try:
                engine = J.make_stt_engine()
            except Exception:
                pass


__all__ = [
    'FOLLOWUP_MAX_CHAIN',
    'VoskEngine',
    'WhisperEngine',
    '_CMD_START',
    '_STOP_ALONE',
    '_STT_WORDS',
    '_WAKE_FILLERS',
    '_barge_in',
    '_gemini_for_stt',
    '_gemini_transcribe',
    '_get_pa',
    '_is_echo',
    '_looks_like_command',
    '_match_wake',
    '_pa',
    '_pa_lock',
    '_passes_gate',
    '_stt_vocab_sentence',
    '_voice_worker',
    '_wav_bytes',
    '_whisper_refiner',
    '_whisper_transcribe',
    'activate_listening',
    'audio_loop',
    'convo',
    'handle_voice',
    'list_mics',
    'make_stt_engine',
    'mic_restart',
    'open_followup',
    'refine_speech',
    'stt_refine_mode',
    'voice_queue',
]
