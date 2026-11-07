"""12.1: voz local Kokoro (opcional) y medición de las voces en tu equipo.

«Instala la voz Kokoro» baja el modelo liviano (~90 MB) y el paquete; «mide las voces» compara en TU computador cuánto
tarda cada voz en generar una frase y te dice cuál conviene; «usa la voz Kokoro» la deja como voz. Sin internet,
si Kokoro está instalada, Jarvis la usa antes que Piper. La lógica está en kokoro_voz.py.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import asyncio
import os
import re
import subprocess
import sys
import tempfile
import uuid

import kokoro_voz
from nucleo import J

kokoro_job = {"busy": False}


def kokoro_ready():
    return kokoro_voz.ready(J.APP_DIR)


def kokoro_synth(text, path, rate=0):
    return kokoro_voz.synth(text, path, J.APP_DIR, J.settings.get("kokoro_voice", "dora"), rate)


def _kokoro_fetch(url, dst):
    import urllib.request
    with urllib.request.urlopen(url, timeout=60) as r, open(dst, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)


def install_kokoro():
    """Instala el paquete y baja el modelo. → mensaje."""
    if not kokoro_voz.package_ready():
        if getattr(sys, "frozen", False):
            return ("En la versión .exe no puedo instalar componentes nuevos. Usa la versión de Python (instalar.bat) "
                    "para tener la voz Kokoro.")
        r = subprocess.run([J._python_console(), "-m", "pip", "install", "-q", "kokoro-onnx"], capture_output=True, text=True, timeout=1200,
                           creationflags=0x08000000 if J.IS_WIN else 0)
        if r.returncode != 0 or not kokoro_voz.package_ready():
            return "No pude instalar el paquete de Kokoro: " + ((r.stderr or "").strip().splitlines() or ["sin detalle"])[-1][:160]
    kokoro_voz.download(J.APP_DIR, _kokoro_fetch)
    return ""


def _engines():
    out = {"Piper": lambda tx: J._piper_synth(tx, os.path.join(tempfile.gettempdir(), f"jarvis_m_{uuid.uuid4().hex}.wav"), 0, 0)}
    if kokoro_ready():
        out["Kokoro"] = lambda tx: kokoro_synth(tx, os.path.join(tempfile.gettempdir(), f"jarvis_m_{uuid.uuid4().hex}.wav"))
    if J.edge_tts is not None and not J.is_offline():
        out["Edge (internet)"] = lambda tx: asyncio.run(J.edge_tts.Communicate(tx, J.settings["tts_voice"]).save(
            os.path.join(tempfile.gettempdir(), f"jarvis_m_{uuid.uuid4().hex}.mp3")))
    return out


def measure_voices():
    eng = _engines()
    for fn in eng.values():                              # la primera vez carga el modelo: no cuenta
        try:
            fn("Hola.")
        except Exception:
            pass
    return kokoro_voz.benchmark(eng)


def _set(key, value):
    J.settings[key] = value
    try:
        J.save_settings_file()
    except OSError:
        pass
    J.socketio.emit("settings_updated", J.public_settings())


_KO_INSTALL = re.compile(r"\b(?:instala|descarga|baja)\s+(?:la\s+)?voz\s+kokoro\b")
_KO_USE = re.compile(r"\b(?:usa|pon|ponte|cambia a)\s+(?:la\s+)?voz\s+kokoro\b|\bhabla con kokoro\b")
_KO_MEASURE = re.compile(r"\b(?:mide|compara|prueba)\s+(?:las\s+)?voces\b|\bque voz es (?:mas rapida|mejor)\b")


def local_voice_voice(text, t):
    if _KO_INSTALL.search(t):
        if kokoro_ready():
            J.reply("La voz Kokoro ya está instalada. «Usa la voz Kokoro» para escucharla, o «mide las voces».", "VOZ")
            return True
        if kokoro_job["busy"]:
            J.reply("Ya la estoy instalando.", "VOZ")
            return True

        def work():
            try:
                err = install_kokoro()
            except Exception as e:
                err = f"No pude bajar el modelo de Kokoro: {e}"
            finally:
                kokoro_job["busy"] = False
            if err:
                J.notify(err, "VOZ")
                return
            res = measure_voices()
            J.notify("Lista la voz Kokoro. " + kokoro_voz.verdict(res) + " «Usa la voz Kokoro» para dejarla.", "VOZ")
        def go():
            if kokoro_job["busy"]:
                return
            kokoro_job["busy"] = True
            J.reply("Instalo la voz Kokoro. Tarda unos minutos; te aviso.", "VOZ")
            J.start_job("Instalando la voz Kokoro", work, "kokoro")
        J.request_approval("instalar", "Instalar la voz Kokoro (unos 90 MB)", "Baja el componente kokoro-onnx y el modelo de voz.", on_ok=go,
                           on_no=lambda: J.reply("Vale, no la instalo.", "VOZ"), ttl=1800,
                           say="¿Instalo la voz Kokoro? Son unos 90 MB. Di «sí» o «no».")       # 12.4: con tu «sí»
        return True
    if _KO_USE.search(t):
        if not kokoro_ready():
            J.reply("Primero hay que instalarla: «instala la voz Kokoro».", "VOZ")
            return True
        if re.search(r"\b(?:alex|hombre|masculina)\b", t):
            _set("kokoro_voice", "alex")
        elif re.search(r"\b(?:dora|mujer|femenina)\b", t):
            _set("kokoro_voice", "dora")
        _set("tts_backend", "kokoro")
        J.reply("Listo, ahora hablo con la voz Kokoro, sin internet.", "VOZ")
        return True
    if _KO_MEASURE.search(t):
        J.reply("Mido las voces en tu equipo…", "VOZ")
        J.start_job("Midiendo las voces", lambda: J.notify(kokoro_voz.verdict(measure_voices()), "VOZ"), "voces")
        return True
    return False


__all__ = ['_KO_INSTALL', '_KO_MEASURE', '_KO_USE', '_engines', '_kokoro_fetch', '_set', 'install_kokoro', 'kokoro_job', 'kokoro_ready', 'kokoro_synth',
           'kokoro_voz', 'local_voice_voice', 'measure_voices']
