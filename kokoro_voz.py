"""Voz local Kokoro (12.1): más natural que Piper y sin internet. Lógica pura, sin Jarvis.

Kokoro es un modelo de voz pequeño (82 millones de parámetros, licencia Apache 2.0) con voces en español (Dora y Alex).
Es OPCIONAL: necesita el paquete «kokoro-onnx» y dos archivos del modelo en recursos\\kokoro (~90 MB la versión
liviana). Jarvis lo instala con «instala la voz Kokoro» y mide en TU equipo si conviene más que Piper («mide las voces»),
porque la velocidad depende mucho del procesador.
"""
import os
import time
import wave

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
MODEL_FILE, VOICES_FILE = "kokoro-v1.0.int8.onnx", "voices-v1.0.bin"
VOICES = {"dora": "ef_dora", "alex": "em_alex"}
_cache = {"k": None, "dir": None}


def folder(app_dir):
    return os.path.join(app_dir, "recursos", "kokoro")


def files_ready(app_dir):
    d = folder(app_dir)
    return os.path.isfile(os.path.join(d, MODEL_FILE)) and os.path.isfile(os.path.join(d, VOICES_FILE))


def package_ready():
    try:
        import kokoro_onnx  # noqa: F401
        return True
    except Exception:
        return False


def ready(app_dir):
    return files_ready(app_dir) and package_ready()


def _engine(app_dir):
    d = folder(app_dir)
    if _cache["k"] is None or _cache["dir"] != d:
        from kokoro_onnx import Kokoro
        _cache["k"] = Kokoro(os.path.join(d, MODEL_FILE), os.path.join(d, VOICES_FILE))
        _cache["dir"] = d
    return _cache["k"]


def to_wav(samples, sr, path):
    """Muestras float (-1..1) → WAV de 16 bits."""
    try:
        import numpy as np
        raw = (np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0) * 32767).astype("<i2").tobytes()
    except ImportError:
        import array
        raw = array.array("h", (int(max(-1.0, min(1.0, float(s))) * 32767) for s in samples)).tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(raw)
    return path


def synth(text, path, app_dir, voice="dora", rate=0):
    """Genera el WAV. rate −50..+50 % → velocidad 0,5..1,5."""
    k = _engine(app_dir)
    speed = max(0.5, min(1.5, 1.0 + rate / 100.0))
    samples, sr = k.create(text, voice=VOICES.get(voice, voice), speed=speed, lang="es")
    return to_wav(samples, sr, path)


def download(app_dir, fetch, progress=None):
    """Baja los dos archivos del modelo. fetch(url, ruta) descarga (lo pone Jarvis)."""
    d = folder(app_dir)
    os.makedirs(d, exist_ok=True)
    for i, (url, name) in enumerate(((MODEL_URL, MODEL_FILE), (VOICES_URL, VOICES_FILE))):
        dst = os.path.join(d, name)
        if not os.path.isfile(dst):
            tmp = dst + ".parte"
            fetch(url, tmp)
            os.replace(tmp, dst)
        if progress:
            progress(i + 1, 2)
    return d


def benchmark(engines, text="Hola, soy Jarvis. Hoy vamos a repasar las fracciones equivalentes con un ejemplo sencillo."):
    """Mide cada motor: {nombre: segundos para generar la frase} (o el error). engines = {nombre: fn(texto)}."""
    out = {}
    for name, fn in engines.items():
        try:
            t = time.perf_counter()
            fn(text)
            out[name] = round(time.perf_counter() - t, 2)
        except Exception as e:
            out[name] = f"no disponible ({str(e)[:60]})"
    return out


def verdict(res):
    """La frase con el resultado de la medición."""
    ok = {k: v for k, v in res.items() if isinstance(v, (int, float))}
    if not ok:
        return "No pude medir ninguna voz local."
    parts = [f"{k}: {str(v).replace('.', ',')} s" for k, v in sorted(ok.items(), key=lambda x: x[1])]
    best = min(ok, key=ok.get)
    t = "En tu equipo, generar una frase tarda " + "; ".join(parts) + "."
    if "Kokoro" in ok and "Piper" in ok:
        if ok["Kokoro"] <= max(1.2, ok["Piper"] * 2.5):
            t += " Kokoro va bien de velocidad y suena más natural: te recomiendo usarlo sin internet."
        else:
            t += " Kokoro es bastante más lento aquí: mejor deja Piper para no hacerte esperar."
    elif best:
        t += f" La más rápida es {best}."
    return t
