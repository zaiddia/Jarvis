"""Síntesis de voz: Edge, Piper y Gemini, caché de frases y cola de reproducción.

Parte de Jarvis (antes dentro de jarvis.py). Los nombres globales de Jarvis se usan como J.<nombre>.
"""
from collections import deque
import asyncio
import json
import os
import queue
import rapidez
import re
import tempfile
import threading
import time
import uuid

from nucleo import J


# =============================================================================
# SÍNTESIS DE VOZ
# =============================================================================
tts_queue = queue.Queue()
tts_playing = threading.Event()
tts_stop = threading.Event()
tts_prompt = threading.Event()           # suena un «¿Sí?»: el micrófono sigue escuchando
tts_gen = {"n": 0}                       # sube al interrumpir: lo que estaba en cola se descarta
tts_now = {"text": ""}                   # frase que suena ahora
tts_recent = deque(maxlen=6)             # (hora, frase) de lo último dicho: filtro de eco al interrumpir
audio_ready = False
from concurrent.futures import ThreadPoolExecutor
_synth_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="voz")


def _init_audio():
    if not J.pygame:
        J.log_terminal("Pygame no instalado: las respuestas solo se mostrarán en texto.", "AVISO")
        J.set_state(tts="error")
        return
    if not (J.edge_tts or J.PIPER_INSTALLED or J._gemini_for_stt()):
        J.log_terminal("Ni Edge-TTS ni Piper instalados: las respuestas solo se mostrarán en texto.", "AVISO")
        J.set_state(tts="error")
        return
    try:
        J.pygame.mixer.init()
        J.audio_ready = True
        J.set_state(tts="ok" if J.settings["tts_enabled"] else "off")
    except Exception as e:
        J.set_state(tts="error")
        J.log_terminal(f"No se pudo iniciar el audio de salida: {e}", "ERROR")


# ---- Piper (voz offline) --------------------------------------------------
_piper_cache = {}
_piper_lock = threading.Lock()


def find_piper_voice():
    """Ruta del modelo .onnx de Piper: el elegido en Ajustes o el primero de recursos\\piper."""
    v = J.settings["piper_voice"].strip().strip('"')
    if v:
        p = v if os.path.isabs(v) else os.path.join(J.APP_DIR, v)
        return p if os.path.isfile(p) else None
    for folder in (os.path.join(J.APP_DIR, "recursos", "piper"),
                   J.get_resource_path(os.path.join("recursos", "piper"))):
        if os.path.isdir(folder):
            for f in sorted(os.listdir(folder)):
                if f.endswith(".onnx"):
                    return os.path.join(folder, f)
    return None


def _get_piper(model_path):
    with J._piper_lock:
        voice = J._piper_cache.get(model_path)
        if voice is None:
            voice = J.PiperVoice.load(model_path)
            J._piper_cache.clear()                 # solo un modelo cargado a la vez (memoria)
            J._piper_cache[model_path] = voice
        return voice


def _piper_synth(text, path, rate, volume):
    J._ensure_piper()
    model = J.find_piper_voice()
    if not model:
        raise RuntimeError("No hay voz de Piper. Ejecuta descargar_voz.py o indícala en Ajustes › Voz.")
    voice = J._get_piper(model)
    # rate -50..+50 % -> length_scale (más alto = más lento); volume -50..+50 -> 0.5..1.5
    cfg = J.SynthesisConfig(length_scale=max(0.5, min(2.0, 1.0 - rate / 100.0)),
                          volume=max(0.1, min(1.5, 1.0 + volume / 100.0)))
    import wave
    with wave.open(path, "wb") as wav:
        voice.synthesize_wav(text, wav, syn_config=cfg)


# ---- Whisper (reconocimiento offline alternativo a Vosk) ------------------
WHISPER_SIZES = [("tiny", "Muy rápido · menos preciso"),
                 ("base", "Equilibrado (recomendado)"),
                 ("small", "Más preciso · más lento")]


def _whisper_installed():
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def _clean_for_speech(text):
    text = text.split("\n")[0]                                   # solo la primera línea
    text = re.sub(r"[A-Za-z]:\\\S+|/\S+/\S+", "", text)          # no leer rutas en voz alta
    return re.sub(r"[*#`_>|«»]", "", text).strip()


def speak(text, voice=None, rate=None, volume=None, pitch=None, force=False, backend=None, gemini=None,
          prompt=False):
    if not text or not J.audio_ready:
        return
    if not (J.settings["tts_enabled"] or force):
        return
    if getattr(J._tl, "capture", None) is not None:
        return
    if not prompt:
        rapidez.mark("respuesta")
    item = {"text": text, "voice": voice, "rate": rate, "volume": volume, "pitch": pitch,
            "backend": backend, "gemini": gemini or {}, "gen": J.tts_gen["n"], "prompt": prompt}
    # La voz se genera YA, en paralelo, mientras suena la frase anterior: así no hay
    # pausas entre frases aunque el motor (p. ej. Gemini) tarde un segundo en responder.
    item["future"] = J._synth_pool.submit(J._synthesize, item)
    J.tts_queue.put(item)


def _play_file(path, max_seconds=None):
    J.pygame.mixer.music.load(path)
    J.pygame.mixer.music.play()
    t0 = time.time()
    while J.pygame.mixer.music.get_busy() and not J.tts_stop.is_set():
        if max_seconds and time.time() - t0 > max_seconds:
            break
        time.sleep(0.03)
    J.pygame.mixer.music.stop()


def play_sound(path, max_seconds=10):
    """Pone un sonido (p. ej. la sirena de alarma) en la misma cola que la voz."""
    if J.audio_ready and path:
        J.tts_queue.put({"sound": path, "max": max_seconds, "gen": J.tts_gen["n"]})


# ---- Voz de Gemini (muy natural; usa tu clave de Gemini) -------------------
GEMINI_TTS_MODELS = [("gemini-3.8-flash-lite-tts", "Rápida (recomendada)"),
                     ("gemini-3.8-flash-tts", "Máxima calidad, algo más lenta")]
GEMINI_TTS_VOICES = [("Charon", "Informativa"), ("Orus", "Firme"), ("Kore", "Firme"), ("Puck", "Animada"),
                     ("Zephyr", "Brillante"), ("Fenrir", "Entusiasta"), ("Leda", "Juvenil"), ("Aoede", "Ligera"),
                     ("Callirrhoe", "Relajada"), ("Autonoe", "Brillante"), ("Enceladus", "Susurrante"),
                     ("Iapetus", "Clara"), ("Umbriel", "Relajada"), ("Algieba", "Suave"), ("Despina", "Suave"),
                     ("Erinome", "Clara"), ("Algenib", "Grave"), ("Rasalgethi", "Informativa"),
                     ("Laomedeia", "Animada"), ("Achernar", "Suave"), ("Alnilam", "Firme"), ("Schedar", "Pareja"),
                     ("Gacrux", "Madura"), ("Pulcherrima", "Directa"), ("Achird", "Amigable"),
                     ("Zubenelgenubi", "Casual"), ("Vindemiatrix", "Gentil"), ("Sadachbia", "Vivaz"),
                     ("Sadaltager", "Experta"), ("Sulafat", "Cálida")]
VOICE_CACHE_DIR = os.path.join(J.CONFIG_DIR, "voz_cache")
_gtts = {"pause_until": 0.0, "warned": 0.0}


def _gemini_tts(text, path, over=None):
    """Pide la voz a Gemini (Interactions API) y deja un WAV en path.
    Devuelve la ruta a reproducir (puede ser la de la caché, que no se borra)."""
    import base64
    import hashlib
    cfg = J._gemini_for_stt()
    if not cfg:
        raise J.AIError("Falta la clave de Gemini.", kind="config", why="falta la clave de Gemini")
    if time.time() < J._gtts["pause_until"]:
        raise J.AIError("La voz de Gemini está en pausa.", kind="quota", why="en pausa")
    over = over or {}                                    # valores de «Probar voz» (sin guardar)
    voice = over.get("gemini_tts_voice") or J.settings["gemini_tts_voice"]
    model = over.get("gemini_tts_model") or J.settings["gemini_tts_model"]
    style = (over.get("gemini_tts_style", J.settings["gemini_tts_style"]) or "").strip()
    cacheable = len(text) <= 80                       # frases cortas y repetidas: «¿Sí?», «Hecho.»
    key = hashlib.sha1(f"{model}|{voice}|{style}|{text}".encode("utf-8")).hexdigest()
    cached = os.path.join(J.VOICE_CACHE_DIR, key + ".wav")
    if cacheable and os.path.exists(cached):
        return cached
    content = {"type": "text", "text": text}
    if style:
        content["annotations"] = [{"type": "speech_metadata", "style": style}]
    body = {"model": model, "input": [{"type": "user_input", "content": [content]}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": voice}]}}
    data = J._http("POST", f"{J.GEMINI_BASE}/interactions", J._gemini_headers(cfg), body, timeout=30)
    audio = None
    for step in data.get("steps") or []:
        for c in step.get("content") or []:
            if isinstance(c, dict) and c.get("type") == "audio" and c.get("data"):
                audio = c                                  # el último bloque de audio
    if not audio:
        raise J.AIError("Gemini no devolvió audio.", kind="bad", why="no devolvió audio")
    raw = base64.b64decode(audio["data"])
    if raw[:4] != b"RIFF":                                 # PCM sin cabecera: se envuelve en WAV
        raw = J._wav_bytes(raw, int(audio.get("sample_rate") or 24000))
    with open(path, "wb") as f:
        f.write(raw)
    if cacheable:
        try:
            os.makedirs(J.VOICE_CACHE_DIR, exist_ok=True)
            files = sorted(os.scandir(J.VOICE_CACHE_DIR), key=lambda e: e.stat().st_mtime)
            for old in files[:-300]:                       # como mucho 300 frases guardadas
                os.remove(old.path)
            with open(cached, "wb") as f:
                f.write(raw)
        except OSError:
            pass
    return path


# Caché de voz (7.1): las frases cortas que se repiten («¿Sí?», «Hecho», «Listo», saludos…) se guardan ya
# generadas y suenan al instante, sin volver a pedirlas a internet ni a Piper.
VOICE_CACHE = os.path.join(J.CONFIG_DIR, "cache_voz")
VOICE_CACHE_MAX_CHARS = 90
VOICE_CACHE_FILES = 400


def _voice_cache_key(backend, item, text, rate, volume, pitch):
    import hashlib
    if backend == "edge":
        who = item.get("voice") or J.settings["tts_voice"]
    elif backend == "piper":
        who = J.find_piper_voice() or "piper"
    else:
        g = item.get("gemini") or {}
        who = f"{J.settings['gemini_tts_voice']}|{J.settings['gemini_tts_style']}|{json.dumps(g, sort_keys=True)}"
    raw = f"{backend}|{who}|{rate}|{volume}|{pitch}|{text}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest() + (".mp3" if backend == "edge" else ".wav")


def _voice_cache_get(backend, item, text, rate, volume, pitch):
    if len(text) > J.VOICE_CACHE_MAX_CHARS:
        return None
    try:
        p = os.path.join(J.VOICE_CACHE, J._voice_cache_key(backend, item, text, rate, volume, pitch))
        if os.path.isfile(p) and os.path.getsize(p) > 0:
            os.utime(p)                                    # el más usado se queda
            return p
    except Exception:
        pass
    return None


def _voice_cache_put(backend, item, text, rate, volume, pitch, path):
    if len(text) > J.VOICE_CACHE_MAX_CHARS:
        return
    try:
        import shutil
        os.makedirs(J.VOICE_CACHE, exist_ok=True)
        shutil.copyfile(path, os.path.join(J.VOICE_CACHE, J._voice_cache_key(backend, item, text, rate, volume, pitch)))
        files = sorted((e for e in os.scandir(J.VOICE_CACHE) if e.is_file()), key=lambda e: e.stat().st_mtime)
        for e in files[:-J.VOICE_CACHE_FILES]:
            os.remove(e.path)
    except Exception:
        pass


PREWARM_PHRASES = ["¿Sí?", "Hecho.", "Listo.", "Cancelado.", "Vale, lo dejo.", "Te escucho.", "Lo tendré en cuenta."]


def prewarm_voice():
    """Al arrancar deja listas en la caché las frases que más se repiten (no con la voz de Gemini:
    gastaría tu cuota)."""
    if not J.audio_ready or J.settings["tts_backend"] == "gemini" or J.is_offline():
        return
    for ph in J.PREWARM_PHRASES:
        try:
            J._synthesize({"text": ph, "voice": None, "rate": None, "volume": None, "pitch": None, "backend": None,
                         "gemini": {}, "gen": J.tts_gen["n"]})
        except Exception:
            return
        time.sleep(0.3)


def _synthesize(item):
    """Genera el audio de una frase. Devuelve (ruta, borrar_después) o (None, False).
    Si el motor elegido falla, prueba el siguiente: Gemini → Edge → Piper."""
    if item.get("gen") != J.tts_gen["n"]:
        return None, False                                 # se canceló (interrupción) antes de empezar
    text = J._clean_for_speech(item["text"])
    if not text:
        return None, False
    rate = J.settings["tts_rate"] if item["rate"] is None else int(item["rate"])
    volume = J.settings["tts_volume"] if item["volume"] is None else int(item["volume"])
    pitch = J.settings["tts_pitch"] if item["pitch"] is None else int(item["pitch"])
    first = item.get("backend") or J.settings["tts_backend"]
    order = {"gemini": ["gemini", "edge", "piper"], "edge": ["edge", "piper"], "piper": ["piper", "edge"]}.get(first, ["edge", "piper"])
    if J.is_offline():
        order = ["piper", "edge"]                          # sin internet: directo a la voz del equipo
    last_err = None
    for b in order:
        cached = J._voice_cache_get(b, item, text, rate, volume, pitch)
        if cached:
            return cached, False
        try:
            if b == "gemini":
                path = os.path.join(tempfile.gettempdir(), f"jarvis_{uuid.uuid4().hex}.wav")
                out = J._gemini_tts(text, path, item.get("gemini"))
                if out == path:
                    J._voice_cache_put(b, item, text, rate, volume, pitch, path)
                return out, out == path
            if b == "piper":
                if not J._ensure_piper():
                    continue
                path = os.path.join(tempfile.gettempdir(), f"jarvis_{uuid.uuid4().hex}.wav")
                J._piper_synth(text, path, rate, volume)
                J._voice_cache_put(b, item, text, rate, volume, pitch, path)
                return path, True
            if J.edge_tts is None:
                continue
            path = os.path.join(tempfile.gettempdir(), f"jarvis_{uuid.uuid4().hex}.mp3")
            voice = item["voice"] or J.settings["tts_voice"]
            communicate = J.edge_tts.Communicate(text, voice, rate=f"{rate:+d}%", volume=f"{volume:+d}%",
                                               pitch=f"{pitch:+d}Hz")
            asyncio.run(communicate.save(path))
            J._voice_cache_put(b, item, text, rate, volume, pitch, path)
            return path, True
        except J.AIError as e:
            last_err = e
            if b == "gemini" and e.why != "en pausa":
                # cuota agotada, sin saldo, clave… : pausa 15 min y avisa una sola vez
                J._gtts["pause_until"] = time.time() + (900 if e.kind in ("quota", "balance", "key", "perm", "model", "config") else 60)
                if time.time() - J._gtts["warned"] > 900:
                    J._gtts["warned"] = time.time()
                    J.log_terminal(f"La voz de Gemini no está disponible ({e.why}); mientras tanto uso la de Edge.", "AVISO")
        except Exception as e:
            last_err = e
    raise last_err or RuntimeError("no hay motor de voz disponible")


def _tts_worker():
    while True:
        item = J.tts_queue.get()
        if item.get("gen") != J.tts_gen["n"]:               # cancelado por una interrupción
            continue
        J.tts_stop.clear()
        J.tts_playing.set()
        if item.get("prompt"):
            J.tts_prompt.set()
        else:
            J.tts_prompt.clear()
        J.refresh_mode()
        path, delete = None, False
        try:
            if item.get("sound"):
                J._play_file(item["sound"], item.get("max"))
            else:
                path, delete = item["future"].result(timeout=60)
                if path and item.get("gen") == J.tts_gen["n"]:
                    if J.settings["tts_enabled"]:
                        J.set_state(tts="ok")
                    J.tts_now["text"] = J.normalize(item["text"])
                    J.tts_recent.append((time.time(), J.tts_now["text"]))
                    if not J.tts_stop.is_set():
                        if not item.get("prompt"):
                            rapidez.mark("voz_lista")
                            r = rapidez.mark("sonando")
                            if r:
                                J.log_terminal(rapidez.line(r), "TIEMPOS")
                        J._play_file(path)
        except Exception as e:
            if item.get("sound"):
                J.log_terminal(f"No se pudo reproducir el sonido {item['sound']}: {e}", "ERROR")
            else:
                J.set_state(tts="error")
                J.log_terminal(f"Fallo en síntesis de voz (revisa la conexión o la voz elegida en Ajustes): {e}", "ERROR")
        finally:
            J.tts_now["text"] = ""
            try:
                J.pygame.mixer.music.unload()
            except Exception:
                pass
            if path and delete:
                try:
                    os.remove(path)
                except OSError:
                    pass
            if J.tts_queue.empty():
                was_prompt = bool(item.get("prompt"))
                time.sleep(0.05 if was_prompt else 0.4)
                J.tts_playing.clear()
                J.tts_prompt.clear()
                J.refresh_mode()
                if not was_prompt:
                    J.open_followup()


def stop_speech(log=True):
    J.tts_gen["n"] += 1                                    # invalida lo que estaba en cola o generándose
    while not J.tts_queue.empty():
        try:
            J.tts_queue.get_nowait()
        except queue.Empty:
            break
    J.tts_stop.set()
    if log:
        J.log_terminal("Reproducción de audio detenida.", "SISTEMA")


_tl = threading.local()                 # _tl.quiet: este hilo ejecuta una rutina (no hablar cada paso)


def reply(text, origin="JARVIS"):
    J.log_terminal(text, origin)
    cap = getattr(J._tl, "capture", None)
    if cap is not None:                     # orden pedida en la conversación en vivo: la dice Gemini
        cap.append(str(text))
        return
    J.push_chat("jarvis", text, origin)
    J._auto_card(text, origin)
    if not getattr(J._tl, "quiet", False):
        J.speak(text)


def list_edge_voices():
    async def _fetch():
        return await asyncio.wait_for(J.edge_tts.list_voices(), timeout=10)

    out = []
    for v in asyncio.run(_fetch()):
        if str(v.get("Locale", "")).startswith("es-"):
            name = v.get("ShortName")
            gender = "femenina" if v.get("Gender") == "Female" else "masculina"
            friendly = name.split("-")[-1].replace("Neural", "").replace("Multilingual", " multilingüe")
            out.append((name, f"{friendly} · {v.get('Locale')} · {gender}"))
    return sorted(out, key=lambda x: (x[0][:5] != "es-CO", x[0]))


__all__ = [
    'GEMINI_TTS_MODELS',
    'GEMINI_TTS_VOICES',
    'PREWARM_PHRASES',
    'ThreadPoolExecutor',
    'VOICE_CACHE',
    'VOICE_CACHE_DIR',
    'VOICE_CACHE_FILES',
    'VOICE_CACHE_MAX_CHARS',
    'WHISPER_SIZES',
    '_clean_for_speech',
    '_gemini_tts',
    '_get_piper',
    '_gtts',
    '_init_audio',
    '_piper_cache',
    '_piper_lock',
    '_piper_synth',
    '_play_file',
    '_synth_pool',
    '_synthesize',
    '_tl',
    '_tts_worker',
    '_voice_cache_get',
    '_voice_cache_key',
    '_voice_cache_put',
    '_whisper_installed',
    'audio_ready',
    'find_piper_voice',
    'list_edge_voices',
    'play_sound',
    'prewarm_voice',
    'reply',
    'speak',
    'stop_speech',
    'tts_gen',
    'tts_now',
    'tts_playing',
    'tts_prompt',
    'tts_queue',
    'tts_recent',
    'tts_stop',
]
