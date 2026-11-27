"""12.69: reconocimiento de voz local Parakeet (NVIDIA, por sherpa-onnx), opcional.

«Instala el reconocimiento Parakeet» (con tu «sí»: unos 490 MB) · «usa Parakeet para entenderme».
Sirve en dos lugares, siempre con audio que ya existe: (1) la segunda pasada que entiende mejor la frase que le dijiste a
Jarvis (Ajustes › Voz › «Entender mejor lo que le dices»), y (2) transcribir audios y videos que subes cuando no hay Gemini.
No abre el micrófono ni graba: el oído de Jarvis sigue siendo el mismo (Vosk o Whisper).
"""
import os
import re
import subprocess
import sys
import tempfile
import time

import parakeet_stt as PK
from nucleo import J

parakeet_job = {"busy": False}


def parakeet_ready():
    return PK.ready(J.APP_DIR)


def _parakeet_transcribe(raw):
    """PCM 16 kHz mono → texto, o None si Parakeet no está instalado o falla."""
    if not parakeet_ready():
        return None
    try:
        return PK.transcribe_pcm(raw, J.APP_DIR)
    except Exception as e:
        J.log_terminal(f"Parakeet no pudo transcribir: {e}", "AVISO")
        return None


def install_parakeet():
    """Instala sherpa-onnx y baja el modelo. → "" si quedó, o el mensaje de error."""
    if not PK.package_ready():
        if getattr(sys, "frozen", False):
            return ("En la versión .exe no puedo instalar componentes nuevos. Usa la versión de Python (instalar.bat) para tener "
                    "el reconocimiento Parakeet.")
        r = subprocess.run([J._python_console(), "-m", "pip", "install", "-q", "sherpa-onnx"], capture_output=True, text=True, timeout=1800,
                           creationflags=0x08000000 if J.IS_WIN else 0)
        if r.returncode != 0 or not PK.package_ready():
            return "No pude instalar sherpa-onnx: " + ((r.stderr or "").strip().splitlines() or ["sin detalle"])[-1][:160]
    tmp = os.path.join(tempfile.gettempdir(), f"jarvis_{PK.MODEL_NAME}.tar.bz2")
    try:
        J._kokoro_fetch(PK.MODEL_URL, tmp)
        if not PK.extract(tmp, J.APP_DIR):
            return "El modelo llegó incompleto; vuelve a intentarlo."
    except Exception as e:
        return f"No pude bajar el modelo de Parakeet: {e}"
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return ""


def parakeet_speed():
    """Cuánto tarda en tu equipo con 3 s de silencio (para saber si conviene). → segundos o None."""
    if not parakeet_ready():
        return None
    t0 = time.time()
    _parakeet_transcribe(b"\0\0" * 16000 * 3)                 # la primera vez carga el modelo
    t1 = time.time()
    _parakeet_transcribe(b"\0\0" * 16000 * 3)
    return round(time.time() - t1, 2), round(t1 - t0, 1)


_PK_INSTALL = re.compile(r"^(?:jarvis\s+)?(?:instala|descarga|baja)(?:me)?\s+(?:el\s+)?(?:reconocimiento(?:\s+de\s+voz)?\s+)?parakeet$")
_PK_USE = re.compile(r"^(?:jarvis\s+)?(?:usa|activa|pon)\s+parakeet(?:\s+para\s+(?:entenderme|escucharme|transcribir))?$")


def parakeet69_voice(text, t):
    if _PK_INSTALL.match(t):
        if parakeet_ready():
            J.reply("Parakeet ya está instalado. «Usa Parakeet para entenderme» para dejarlo como segunda pasada.", "VOZ")
            return True
        if parakeet_job["busy"]:
            J.reply("Ya lo estoy instalando.", "VOZ")
            return True

        def work():
            try:
                err = J.install_parakeet()
            finally:
                parakeet_job["busy"] = False
            if err:
                J.notify(err, "VOZ")
                return
            sp = parakeet_speed()
            J.notify("Listo el reconocimiento Parakeet, sin internet." + (f" En tu equipo tarda {sp[0]} s por frase." if sp else "") +
                     " Di «usa Parakeet para entenderme» para usarlo cuando no hay Gemini.", "VOZ")

        def go():
            if parakeet_job["busy"]:
                return
            parakeet_job["busy"] = True
            J.reply("Instalo Parakeet. Son unos 490 MB: tarda unos minutos; te aviso.", "VOZ")
            J.start_job("Instalando Parakeet", work, "parakeet")
        J.request_approval("instalar", "Instalar el reconocimiento de voz Parakeet (unos 490 MB)",
                           "Baja el componente sherpa-onnx y el modelo Parakeet TDT 0.6B v3 de NVIDIA.", on_ok=go,
                           on_no=lambda: J.reply("Vale, no lo instalo.", "VOZ"), ttl=1800,
                           say="¿Instalo el reconocimiento Parakeet? Son unos 490 megas. Di «sí» o «no».")
        return True
    if _PK_USE.match(t):
        if not parakeet_ready():
            J.reply("Primero hay que instalarlo: «instala el reconocimiento Parakeet».", "VOZ")
            return True
        J._set("stt_refine", "parakeet")
        J.reply("Listo: lo que me digas lo vuelvo a entender con Parakeet, en tu equipo y sin internet.", "VOZ")
        return True
    return False


__all__ = ['_PK_INSTALL', '_PK_USE', '_parakeet_transcribe', 'install_parakeet', 'parakeet69_voice', 'parakeet_job', 'parakeet_ready',
           'parakeet_speed']
