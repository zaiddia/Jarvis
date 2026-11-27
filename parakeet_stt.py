"""12.69: reconocimiento de voz local con NVIDIA Parakeet TDT 0.6B v3 (sherpa-onnx, int8). Sin internet y en el procesador.

Solo convierte en texto audio que ya existe (lo que Jarvis ya oyó para una orden, o un archivo que subiste): no abre el
micrófono ni graba nada. Modelo: https://github.com/k2-fsa/sherpa-onnx/releases (asr-models), unos 490 MB.
"""
import os
import tarfile
import threading

MODEL_NAME = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
MODEL_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{MODEL_NAME}.tar.bz2"
FILES = ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")
_state = {"rec": None, "dir": "", "lock": threading.Lock()}


def model_dir(app_dir):
    return os.path.join(app_dir, "modelos", MODEL_NAME)


def package_ready():
    try:
        import importlib.util
        return importlib.util.find_spec("sherpa_onnx") is not None
    except Exception:
        return False


def ready(app_dir):
    d = model_dir(app_dir)
    return package_ready() and all(os.path.isfile(os.path.join(d, f)) for f in FILES)


def extract(archive, app_dir):
    """Descomprime el modelo (solo los archivos que hacen falta, sin rutas raras)."""
    dest = os.path.join(app_dir, "modelos")
    os.makedirs(dest, exist_ok=True)
    with tarfile.open(archive, "r:bz2") as tf:
        for m in tf.getmembers():
            name = m.name.replace("\\", "/")
            parts = name.split("/")
            if len(parts) == 2 and parts[0] == MODEL_NAME and parts[1] in FILES and m.isfile():
                m.name = name
                if hasattr(tarfile, "data_filter"):
                    tf.extract(m, dest, filter="data")
                else:
                    tf.extract(m, dest)
    return ready(app_dir)


def recognizer(app_dir, threads=2):
    with _state["lock"]:
        d = model_dir(app_dir)
        if _state["rec"] is None or _state["dir"] != d:
            import sherpa_onnx
            _state["rec"] = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=os.path.join(d, "encoder.int8.onnx"), decoder=os.path.join(d, "decoder.int8.onnx"),
                joiner=os.path.join(d, "joiner.int8.onnx"), tokens=os.path.join(d, "tokens.txt"),
                num_threads=threads, model_type="nemo_transducer", decoding_method="greedy_search")
            _state["dir"] = d
        return _state["rec"]


def transcribe_pcm(raw, app_dir, rate=16000, threads=2):
    """PCM de 16 bits mono → texto."""
    import numpy as np
    audio = np.frombuffer(raw, dtype=np.int16).astype("float32") / 32768.0
    rec = recognizer(app_dir, threads)
    st = rec.create_stream()
    st.accept_waveform(rate, audio)
    rec.decode_stream(st)
    return (st.result.text or "").strip()


__all__ = ["MODEL_NAME", "MODEL_URL", "FILES", "model_dir", "package_ready", "ready", "extract", "recognizer", "transcribe_pcm"]
