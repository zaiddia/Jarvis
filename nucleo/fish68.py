"""12.68: la voz de Fish Audio como motor de voz (Ajustes › Voz › Fish Audio).

Fish Audio ofrece su modelo S2.1 Pro gratis por la API («s2.1-pro-free», uso justo, sin garantía); Fish anunció ese acceso
gratis hasta el 30 de noviembre de 2026 y ya lo ha extendido varias veces. Si se acaba, Jarvis vuelve solo a la voz de Edge
y avisa una vez; si activas «usar el modelo de pago» («s2.1-pro», unos 15 dólares por millón de letras), sigue con Fish.

  «usa la voz de Fish Audio» · «vuelve a la voz normal» · «la voz de Fish es 9a9cf47702da476aa4629e2506d4a857» (el código
  de la voz que escogiste en fish.audio; sale en la dirección de la página de la voz).
La clave va en Ajustes › Voz (no se dice en voz alta ni se escribe en el chat).
"""
import re
import time

from nucleo import J

FISH_URL = "https://api.fish.audio/v1/tts"
FISH_FREE = "s2.1-pro-free"
FISH_PAID = "s2.1-pro"
_ftts = {"pause_until": 0.0, "warned": 0.0, "free_over": False}


def fish_ready():
    return bool(J.settings.get("fish_api_key", "").strip())


def _fish_tts(text, path):
    """Pide la voz a Fish Audio y deja un MP3 en path. Lanza AIError si no se puede (la cola de voz pasa a Edge)."""
    key = J.settings.get("fish_api_key", "").strip()
    if not key:
        raise J.AIError("Falta la clave de Fish Audio.", kind="config", why="falta la clave de Fish Audio")
    if time.time() < J._ftts["pause_until"]:
        raise J.AIError("La voz de Fish Audio está en pausa.", kind="quota", why="en pausa")
    models = ([] if J._ftts["free_over"] else [FISH_FREE]) + ([FISH_PAID] if J.settings.get("fish_paid") else [])
    if not models:
        raise J.AIError("Se acabó el acceso gratis de Fish Audio.", kind="balance", why="se acabó el acceso gratis de Fish Audio")
    body = {"text": text, "format": "mp3", "latency": "balanced", "normalize": True,
            "prosody": {"speed": round(max(0.5, min(2.0, 1 + int(J.settings.get("tts_rate", 0)) / 100)), 2), "volume": 0}}
    voice = J.settings.get("fish_voice", "").strip()
    if voice:
        body["reference_id"] = voice
    last = None
    for model in models:
        try:
            r = J._http("POST", FISH_URL, {"Authorization": f"Bearer {key}", "model": model}, body, timeout=30, stream=True)
            with r:
                data = r.read()
        except J.AIError as e:
            last = e
            if model == FISH_FREE and e.code in (400, 402, 403, 404) and not re.search(r"reference|voice|model id", getattr(e, "raw", "") or "", re.I):
                J._ftts["free_over"] = True                 # el modelo gratis ya no responde: no se vuelve a intentar hoy
                J._ftts["pause_until"] = 0.0
                continue
            raise
        if len(data) < 200 or data[:1] in (b"{", b"<"):
            raise J.AIError("Fish Audio no devolvió audio.", kind="bad", why="no devolvió audio")
        with open(path, "wb") as f:
            f.write(data)
        return path
    if last is not None and J._ftts["free_over"]:
        raise J.AIError("Se acabó el acceso gratis de Fish Audio.", kind="balance", why="se acabó el acceso gratis de Fish Audio",
                        code=last.code)
    raise last or J.AIError("Fish Audio no respondió.", kind="net", why="no respondió")


def fish_failed(e):
    """La cola de voz no pudo con Fish: pausa un rato y avisa una sola vez (con lo que puedes hacer)."""
    if e.why == "en pausa":
        return
    J._ftts["pause_until"] = time.time() + (900 if e.kind in ("quota", "balance", "key", "perm", "model", "config") else 60)
    if time.time() - J._ftts["warned"] < 3 * 3600:
        return
    J._ftts["warned"] = time.time()
    if e.kind == "balance":
        J.notify("La voz de Fish Audio dejó de ser gratis, así que mientras tanto hablo con la voz de Edge. Si quieres seguir con "
                 "Fish (cuesta unos 15 dólares por millón de letras), activa «Usar el modelo de pago» en Ajustes › Voz.", "VOZ")
    elif e.kind in ("key", "perm", "config"):
        J.notify("Fish Audio no aceptó la clave; revisa la clave en Ajustes › Voz. Mientras tanto hablo con la voz de Edge.", "VOZ")
    else:
        J.log_terminal(f"La voz de Fish Audio no está disponible ({e.why}); mientras tanto uso la de Edge.", "AVISO")


_F68_ON = re.compile(r"^(?:jarvis )?(?:usa|pon|activa|quiero|cambia a|cambiate a) (?:la )?voz (?:de )?fish(?: audio)?$")
_F68_ID = re.compile(r"^(?:jarvis )?(?:la voz de fish(?: audio)? es|usa la voz de fish(?: audio)?|voz de fish(?: audio)?)\s*:?\s*([0-9a-f]{32})$")


def fish68_voice(text, t):
    m = _F68_ID.match(t)
    if m:
        J.settings["fish_voice"] = m.group(1)
        J.save_settings_file()
        J.reply("Listo, uso esa voz de Fish Audio." + ("" if J.settings["tts_backend"] == "fish" else
                                                       " Para activarla di «usa la voz de Fish Audio»."), "VOZ")
        return True
    if not _F68_ON.match(t):
        return False
    if not fish_ready():
        J.reply("Para hablar con la voz de Fish Audio necesito tu clave: créala gratis en fish.audio (sección API) y pégala en "
                "Ajustes › Voz › Fish Audio. Mientras tanto sigo con la voz de siempre.", "VOZ")
        return True
    J.settings["tts_backend"] = "fish"
    J._ftts.update(pause_until=0.0, free_over=False)
    J.save_settings_file()
    J.reply("Listo, ahora hablo con la voz de Fish Audio." + ("" if J.settings.get("fish_voice") else
            " Uso su voz por defecto: si quieres otra, escoge una en fish.audio y pon su código en Ajustes › Voz.")
            + " Si falla o se acaba lo gratis, vuelvo solo a la voz de siempre.", "VOZ")
    return True


__all__ = ['FISH_FREE', 'FISH_PAID', 'FISH_URL', '_F68_ID', '_F68_ON', '_fish_tts', '_ftts', 'fish68_voice', 'fish_failed', 'fish_ready']
