"""Conversación en vivo con Gemini Live (audio en tiempo real por WebSocket).

En vez de «reconocer → texto → IA → texto → voz» por pasos, el audio del micrófono va
directo a Gemini, que lo oye tal cual (acentos, ruido, pausas), detecta solo cuándo
terminaste de hablar, responde con voz natural y se deja interrumpir. Para hacer cosas
en el computador, Gemini llama a las funciones que Jarvis le ofrece.

Este módulo solo habla el protocolo (sin nada de Jarvis): jarvis.py lo usa.
  · entrada:  PCM 16 bits, 16 kHz, mono   («audio/pcm;rate=16000»)
  · salida:   PCM 16 bits, 24 kHz, mono
"""
import base64
import json
import threading
import time

LIVE_URL = ("wss://generativelanguage.googleapis.com/ws/"
            "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent")
IN_RATE = 16000
OUT_RATE = 24000
MODELS = ["gemini-3.8-live", "gemini-3.1-flash-live-preview"]


class LiveError(Exception):
    def __init__(self, msg, kind="bad"):
        super().__init__(msg)
        self.kind = kind


def _classify_close(code, reason):
    r = (reason or "").lower()
    if ("api key" in r or "api_key" in r or "permission" in r or "unauthenticated" in r or "credentials" in r
            or code in (1008,) and "key" in r):
        return "key"
    if "quota" in r or "exhausted" in r or "rate" in r and "limit" in r:
        return "quota"
    if ("not found" in r or "not supported" in r or "is not available" in r or "does not exist" in r
            or "model_not_found" in r) and "model" in r:
        return "model"
    if "unknown name" in r or "invalid json" in r or "cannot find field" in r or "invalid argument" in r:
        return "schema"
    if "tool" in r or "google_search" in r or "googlesearch" in r:
        return "tools"
    return "bad"


def build_setup(model, voice, system, tools, variant="nested", vad=None, handle=None):
    """Mensaje de configuración. variant: 'nested' (generationConfig, el formato clásico)
    o 'flat' (campos directamente en setup, como en la guía nueva)."""
    gen = {"responseModalities": ["AUDIO"],
           "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}
    setup = {"model": model if model.startswith("models/") else f"models/{model}"}
    if variant == "nested":
        setup["generationConfig"] = gen
    else:
        setup.update(gen)
    setup["systemInstruction"] = {"parts": [{"text": system}]}
    if tools:
        setup["tools"] = tools
    setup["inputAudioTranscription"] = {}
    setup["outputAudioTranscription"] = {}
    setup["realtimeInputConfig"] = {"automaticActivityDetection": vad or {
        "silenceDurationMs": 700, "prefixPaddingMs": 200}}
    setup["contextWindowCompression"] = {"slidingWindow": {}}
    if handle:
        setup["sessionResumption"] = {"handle": handle}
    return {"setup": setup}


class LiveSession:                       # Gemini Live
    """Una conversación. Los eventos llegan a los callbacks desde un hilo propio:
        on_audio(pcm24k)  on_input_text(txt)  on_output_text(txt)  on_interrupted()
        on_turn_complete()  on_tool_calls(calls) -> [responses]  on_closed(reason)
        on_resume_handle(handle)
    """

    def __init__(self, api_key, connect=None, url=LIVE_URL, **callbacks):
        self.api_key = api_key
        self.url = url
        self._connect = connect
        self.cb = callbacks
        self.ws = None
        self.closed = threading.Event()
        self._send_lock = threading.Lock()
        self.model = ""
        self.variant = ""
        self.last_server = 0.0

    # ---- conexión ---------------------------------------------------------
    def _open(self):
        connect = self._connect
        if connect is None:
            from websockets.sync.client import connect
        sep = "&" if "?" in self.url else "?"
        return connect(f"{self.url}{sep}key={self.api_key}", open_timeout=10, close_timeout=2,
                       max_size=None, compression=None)

    def start(self, attempts, wait=8.0):
        """attempts: lista de (modelo, variante, mensaje_setup). Prueba en orden hasta que uno
        funcione. Devuelve (modelo, variante). Lanza LiveError con el motivo si ninguno sirve."""
        last = None
        bad_models = set()
        for model, variant, setup in attempts:
            if model in bad_models:
                continue
            try:
                ws = self._open()
            except Exception as e:
                raise LiveError(f"No pude conectar con Gemini Live: {e}", "net")
            try:
                try:
                    ws.send(json.dumps(setup))
                except Exception as e:                     # cerró antes de recibir (p. ej. clave mala)
                    rc = getattr(e, "rcvd", None)
                    reason = getattr(rc, "reason", "") if rc else str(e)
                    raise LiveError(f"Gemini Live cerró la conexión: {reason}",
                                    _classify_close(getattr(rc, "code", None), reason))
                first = self._first_message(ws, wait)
            except LiveError as e:
                last = e
                try:
                    ws.close()
                except Exception:
                    pass
                if e.kind in ("key", "quota", "net"):
                    raise
                if e.kind == "model":
                    bad_models.add(model)              # ese modelo no está: no probar sus variantes
                continue                                   # modelo/formato no aceptado: el siguiente
            self.ws, self.model, self.variant = ws, model, variant
            threading.Thread(target=self._recv_loop, args=(first,), daemon=True, name="envivo").start()
            return model, variant
        raise last or LiveError("Gemini Live no aceptó ninguna configuración.")

    def _first_message(self, ws, wait):
        from websockets.exceptions import ConnectionClosed
        try:
            raw = ws.recv(timeout=wait)
        except TimeoutError:
            return None                                    # abierto y sin quejas: se da por bueno
        except ConnectionClosed as e:
            code = getattr(e.rcvd, "code", None) if getattr(e, "rcvd", None) else None
            reason = getattr(e.rcvd, "reason", "") if getattr(e, "rcvd", None) else str(e)
            raise LiveError(f"Gemini Live cerró la conexión: {reason or code}", _classify_close(code, reason))
        msg = _parse(raw)
        if msg and "error" in msg:
            err = msg["error"]
            reason = err.get("message", "") if isinstance(err, dict) else str(err)
            raise LiveError(f"Gemini Live: {reason}", _classify_close(None, reason))
        return msg

    # ---- envío ---------------------------------------------------------------
    def _send(self, obj):
        if self.closed.is_set() or self.ws is None:
            return False
        try:
            with self._send_lock:
                self.ws.send(json.dumps(obj))
            return True
        except Exception as e:
            self._finish(f"envío fallido: {e}")
            return False

    def send_audio(self, pcm16k):
        return self._send({"realtimeInput": {"audio": {
            "data": base64.b64encode(pcm16k).decode("ascii"), "mimeType": f"audio/pcm;rate={IN_RATE}"}}})

    def send_text(self, text):
        return self._send({"realtimeInput": {"text": text}})

    def send_image(self, jpeg):
        """Una imagen de la cámara o la pantalla (Gemini la toma como video: máx. 1 por segundo)."""
        return self._send({"realtimeInput": {"video": {
            "data": base64.b64encode(jpeg).decode("ascii"), "mimeType": "image/jpeg"}}})

    def send_tool_responses(self, responses):
        return self._send({"toolResponse": {"functionResponses": responses}})

    def close(self, reason="cerrada"):
        self._finish(reason)

    # ---- recepción ---------------------------------------------------------------
    def _recv_loop(self, first):
        from websockets.exceptions import ConnectionClosed
        if first:
            self._dispatch(first)
        reason = "fin"
        try:
            while not self.closed.is_set():
                try:
                    raw = self.ws.recv(timeout=1.0)
                except TimeoutError:
                    continue
                self.last_server = time.time()
                self._handle_raw(raw)
        except ConnectionClosed as e:
            rc = getattr(e, "rcvd", None)
            reason = (getattr(rc, "reason", "") or f"código {getattr(rc, 'code', '?')}") if rc else "conexión cerrada"
        except Exception as e:
            reason = str(e)
        self._finish(reason)

    def _handle_raw(self, raw):
        msg = _parse(raw)
        if msg:
            self._dispatch(msg)

    def _dispatch(self, msg):
        cb = self.cb
        sc = msg.get("serverContent")
        if sc:
            if sc.get("interrupted"):
                _call(cb, "on_interrupted")
            it = (sc.get("inputTranscription") or {}).get("text")
            if it:
                _call(cb, "on_input_text", it)
            ot = (sc.get("outputTranscription") or {}).get("text")
            if ot:
                _call(cb, "on_output_text", ot)
            for part in ((sc.get("modelTurn") or {}).get("parts") or []):
                data = (part.get("inlineData") or {}).get("data")
                if data:
                    _call(cb, "on_audio", base64.b64decode(data))
                elif part.get("text") and not part.get("thought"):
                    _call(cb, "on_output_text", part["text"])
            if sc.get("turnComplete"):
                _call(cb, "on_turn_complete")
        tc = msg.get("toolCall")
        if tc and tc.get("functionCalls"):
            calls = tc["functionCalls"]
            # se atiende en otro hilo: una orden lenta no detiene la recepción de audio
            threading.Thread(target=self._run_tools, args=(calls,), daemon=True).start()
        ru = msg.get("sessionResumptionUpdate")
        if ru and ru.get("resumable") and ru.get("newHandle"):
            _call(cb, "on_resume_handle", ru["newHandle"])
        if "goAway" in msg:
            _call(cb, "on_go_away", msg["goAway"])

    def _run_tools(self, calls):
        fn = self.cb.get("on_tool_calls")
        if not fn:
            return
        try:
            responses = fn(calls)
        except Exception as e:
            responses = [{"id": c.get("id"), "name": c.get("name"), "response": {"error": str(e)}} for c in calls]
        if responses:
            self.send_tool_responses(responses)

    def _finish(self, reason):
        if self.closed.is_set():
            return
        self.closed.set()
        try:
            if self.ws is not None:
                self.ws.close()
        except Exception:
            pass
        _call(self.cb, "on_closed", reason)


def _parse(raw):
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    try:
        m = json.loads(raw)
        return m if isinstance(m, dict) else None
    except ValueError:
        return None


def _call(cb, name, *args):
    f = cb.get(name)
    if f:
        try:
            f(*args)
        except Exception:
            pass


class Player:
    """Reproduce el PCM de 24 kHz que llega en trozos, sin cortes, y se puede vaciar al
    instante cuando lo interrumpes."""

    def __init__(self, device=None):
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._stream = None
        self.rate = OUT_RATE
        self.until = 0.0                 # hasta cuándo se oye (para no mandar su eco al micrófono)
        self.device = device

    def _ensure(self):
        if self._stream is not None:
            return
        import sounddevice as sd
        last = None
        for rate in (OUT_RATE, 48000, 44100):
            try:
                st = sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16", blocksize=0,
                                        device=self.device, callback=self._fill, latency="low")
                st.start()
                self._stream, self.rate = st, rate
                return
            except Exception as e:
                last = e
        raise last

    def _fill(self, outdata, frames, time_info, status):
        n = frames * 2
        with self._lock:
            chunk = bytes(self._buf[:n])
            del self._buf[:n]
        if len(chunk) < n:
            chunk += b"\x00" * (n - len(chunk))
        outdata[:] = chunk

    def write(self, pcm24k):
        self._ensure()
        data = pcm24k if self.rate == OUT_RATE else _resample(pcm24k, OUT_RATE, self.rate)
        with self._lock:
            self._buf += data
            pending = len(self._buf) / 2 / self.rate
        self.until = time.time() + pending + 0.25

    def clear(self):
        with self._lock:
            self._buf.clear()
        self.until = time.time() + 0.1

    def playing(self):
        return time.time() < self.until

    def close(self):
        self.clear()
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None


def _resample(pcm, src, dst):
    import array
    a = array.array("h")
    a.frombytes(pcm)
    if not a:
        return b""
    n = int(len(a) * dst / src)
    step = src / dst
    out = array.array("h", (a[min(int(i * step), len(a) - 1)] for i in range(n)))
    return out.tobytes()


GeminiLive = LiveSession


def _closed_reason(e):
    rc = getattr(e, "rcvd", None)
    return (getattr(rc, "code", None), getattr(rc, "reason", "") if rc else str(e))


# =============================================================================
# OpenAI Realtime (voz en vivo de ChatGPT). De pago; usa la clave de ChatGPT.
# =============================================================================
OPENAI_URL = "wss://api.openai.com/v1/realtime"
OPENAI_MODELS = ["gpt-realtime", "gpt-realtime-2.1", "gpt-realtime-2"]
OPENAI_VOICES = [("marin", "Natural (recomendada)"), ("cedar", "Natural, grave"), ("coral", "Cálida"),
                 ("sage", "Serena"), ("alloy", "Neutra"), ("ash", "Clara"), ("ballad", "Suave"),
                 ("echo", "Grave"), ("shimmer", "Brillante"), ("verse", "Expresiva")]


def openai_session(model, voice, instructions, funcs):
    tools = [{"type": "function", "name": f["name"], "description": f.get("description", ""),
              "parameters": _lower_schema(f.get("parameters") or {"type": "OBJECT", "properties": {}})}
             for f in funcs]
    return {"type": "session.update", "session": {
        "type": "realtime", "model": model, "instructions": instructions, "output_modalities": ["audio"],
        "audio": {"input": {"format": {"type": "audio/pcm", "rate": OUT_RATE},
                            "turn_detection": {"type": "server_vad", "create_response": True,
                                               "interrupt_response": True, "silence_duration_ms": 700},
                            "transcription": {"model": "gpt-4o-transcribe", "language": "es"}},
                  "output": {"format": {"type": "audio/pcm", "rate": OUT_RATE}, "voice": voice}},
        "tools": tools, "tool_choice": "auto"}}


def _lower_schema(sch):
    """Esquema estilo Gemini («OBJECT», «STRING») -> JSON Schema («object», «string»)."""
    if isinstance(sch, dict):
        return {k: (v.lower() if k == "type" and isinstance(v, str) else _lower_schema(v)) for k, v in sch.items()}
    if isinstance(sch, list):
        return [_lower_schema(x) for x in sch]
    return sch


class OpenAIRealtime(LiveSession):
    name = "OpenAI Realtime"

    def __init__(self, api_key, connect=None, url=OPENAI_URL, **callbacks):
        super().__init__(api_key, connect=connect, url=url, **callbacks)
        self._calls_done = set()

    def _open_model(self, model):
        connect = self._connect
        if connect is None:
            from websockets.sync.client import connect
        sep = "&" if "?" in self.url else "?"
        return connect(f"{self.url}{sep}model={model}", open_timeout=10, close_timeout=2, max_size=None,
                       compression=None, additional_headers={"Authorization": f"Bearer {self.api_key}"})

    def start(self, attempts, wait=8.0):
        """attempts: [(modelo, mensaje session.update)]."""
        from websockets.exceptions import ConnectionClosed, InvalidStatus
        last = None
        for model, sess_msg in attempts:
            try:
                ws = self._open_model(model)
            except InvalidStatus as e:
                code = getattr(getattr(e, "response", None), "status_code", 0)
                kind = "key" if code in (401, 403) else "quota" if code == 429 else "model" if code in (400, 404) else "bad"
                last = LiveError(f"OpenAI Realtime rechazó la conexión (HTTP {code}).", kind)
                if kind in ("key", "quota"):
                    raise last
                continue
            except Exception as e:
                raise LiveError(f"No pude conectar con OpenAI Realtime: {e}", "net")
            try:
                ws.send(json.dumps(sess_msg))
                deadline = time.time() + wait
                ok = False
                while time.time() < deadline:
                    msg = _parse(ws.recv(timeout=max(0.1, deadline - time.time())))
                    if not msg:
                        continue
                    if msg.get("type") == "error":
                        err = msg.get("error") or {}
                        text = f"{err.get('message', '')} {err.get('code', '')}"
                        raise LiveError(f"OpenAI Realtime: {err.get('message', 'error')}", _classify_close(None, text))
                    if msg.get("type") == "session.updated":
                        ok = True
                        break
                if not ok:
                    raise LiveError("OpenAI Realtime no confirmó la configuración.", "bad")
            except TimeoutError:
                last = LiveError("OpenAI Realtime no respondió.", "net")
                _safe_close(ws)
                continue
            except ConnectionClosed as e:
                code, reason = _closed_reason(e)
                last = LiveError(f"OpenAI Realtime cerró la conexión: {reason or code}", _classify_close(code, reason))
                _safe_close(ws)
                if last.kind in ("key", "quota"):
                    raise last
                continue
            except LiveError as e:
                last = e
                _safe_close(ws)
                if e.kind in ("key", "quota"):
                    raise
                continue
            self.ws, self.model, self.variant = ws, model, "openai"
            threading.Thread(target=self._recv_loop, args=(None,), daemon=True, name="envivo-oa").start()
            return model, "openai"
        raise last or LiveError("OpenAI Realtime no aceptó ninguna configuración.")

    def send_audio(self, pcm16k):
        pcm = _resample(pcm16k, IN_RATE, OUT_RATE)
        return self._send({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode("ascii")})

    def send_text(self, text):
        self._send({"type": "conversation.item.create", "item": {
            "type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}})
        return self._send({"type": "response.create"})

    def send_image(self, jpeg):
        return self._send({"type": "conversation.item.create", "item": {
            "type": "message", "role": "user", "content": [{
                "type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")}]}})

    def send_tool_responses(self, responses):
        for r in responses:
            self._send({"type": "conversation.item.create", "item": {
                "type": "function_call_output", "call_id": r["id"],
                "output": json.dumps(r["response"], ensure_ascii=False)}})
        return self._send({"type": "response.create"})

    def _dispatch(self, msg):
        cb, t = self.cb, msg.get("type", "")
        if t == "input_audio_buffer.speech_started":
            _call(cb, "on_interrupted")
        elif t == "conversation.item.input_audio_transcription.completed":
            _call(cb, "on_input_text", (msg.get("transcript") or "") + " ")
        elif t in ("response.output_audio.delta", "response.audio.delta"):
            if msg.get("delta"):
                _call(cb, "on_audio", base64.b64decode(msg["delta"]))
        elif t in ("response.output_audio_transcript.delta", "response.audio_transcript.delta"):
            _call(cb, "on_output_text", msg.get("delta") or "")
        elif t == "response.function_call_arguments.done":
            cid = msg.get("call_id")
            if cid in self._calls_done:
                return
            self._calls_done.add(cid)
            try:
                args = json.loads(msg.get("arguments") or "{}")
            except ValueError:
                args = {}
            threading.Thread(target=self._run_tools, args=([{"id": cid, "name": msg.get("name"), "args": args}],),
                             daemon=True).start()
        elif t == "response.done":
            _call(cb, "on_turn_complete")
        elif t == "error":
            err = msg.get("error") or {}
            if err.get("code") not in ("response_cancel_not_active", "conversation_already_has_active_response"):
                _call(cb, "on_error", err.get("message", "error"))


# =============================================================================
# Deepgram Voice Agent. 200 USD de crédito gratis al registrarse.
# =============================================================================
DEEPGRAM_URL = "wss://agent.deepgram.com/v1/agent/converse"
DEEPGRAM_VOICES = [("aura-2-celeste-es", "Celeste (femenina)"), ("aura-2-estrella-es", "Estrella (femenina)"),
                   ("aura-2-carina-es", "Carina (femenina)"), ("aura-2-diana-es", "Diana (femenina)"),
                   ("aura-2-selena-es", "Selena (femenina)"), ("aura-2-sirio-es", "Sirio (masculina)"),
                   ("aura-2-nestor-es", "Néstor (masculina)"), ("aura-2-alvaro-es", "Álvaro (masculina)"),
                   ("aura-2-javier-es", "Javier (masculina)"), ("aura-2-aquila-es", "Áquila (masculina)")]


def deepgram_settings(voice, think_model, prompt, funcs, greeting=None):
    agent = {
        "listen": {"provider": {"type": "deepgram", "model": "nova-3", "language": "es", "keyterms": ["Jarvis"]}},
        "think": {"provider": {"type": "open_ai", "model": think_model}, "prompt": prompt,
                  "functions": [{"name": f["name"], "description": f.get("description", ""),
                                 "parameters": _lower_schema(f.get("parameters") or {"type": "OBJECT", "properties": {}})}
                                for f in funcs]},
        "speak": {"provider": {"type": "deepgram", "model": voice}},
    }
    if greeting:
        agent["greeting"] = greeting
    return {"type": "Settings",
            "audio": {"input": {"encoding": "linear16", "sample_rate": IN_RATE},
                      "output": {"encoding": "linear16", "sample_rate": OUT_RATE, "container": "none"}},
            "agent": agent}


class DeepgramAgent(LiveSession):
    name = "Deepgram"

    def __init__(self, api_key, connect=None, url=DEEPGRAM_URL, **callbacks):
        super().__init__(api_key, connect=connect, url=url, **callbacks)

    def start(self, attempts, wait=8.0):
        """attempts: [(etiqueta, mensaje Settings)]."""
        from websockets.exceptions import ConnectionClosed, InvalidStatus
        connect = self._connect
        if connect is None:
            from websockets.sync.client import connect
        last = None
        for label, settings_msg in attempts:
            try:
                ws = connect(self.url, open_timeout=10, close_timeout=2, max_size=None, compression=None,
                             additional_headers={"Authorization": f"Token {self.api_key}"})
            except InvalidStatus as e:
                code = getattr(getattr(e, "response", None), "status_code", 0)
                kind = "key" if code in (401, 403) else "quota" if code in (402, 429) else "bad"
                raise LiveError(f"Deepgram rechazó la conexión (HTTP {code}).", kind)
            except Exception as e:
                raise LiveError(f"No pude conectar con Deepgram: {e}", "net")
            try:
                ws.send(json.dumps(settings_msg))
                deadline = time.time() + wait
                ok = False
                while time.time() < deadline:
                    raw = ws.recv(timeout=max(0.1, deadline - time.time()))
                    msg = _parse(raw) if not isinstance(raw, (bytes, bytearray)) else None
                    if not msg:
                        continue
                    if msg.get("type") == "Error":
                        text = f"{msg.get('description', '')} {msg.get('code', '')}"
                        raise LiveError(f"Deepgram: {msg.get('description') or 'error'}", _classify_close(None, text))
                    if msg.get("type") == "SettingsApplied":
                        ok = True
                        break
                if not ok:
                    raise LiveError("Deepgram no confirmó la configuración.", "bad")
            except TimeoutError:
                last = LiveError("Deepgram no respondió.", "net")
                _safe_close(ws)
                continue
            except ConnectionClosed as e:
                code, reason = _closed_reason(e)
                last = LiveError(f"Deepgram cerró la conexión: {reason or code}", _classify_close(code, reason))
                _safe_close(ws)
                continue
            except LiveError as e:
                last = e
                _safe_close(ws)
                if e.kind in ("key", "quota"):
                    raise
                continue
            self.ws, self.model, self.variant = ws, label, "deepgram"
            threading.Thread(target=self._recv_loop, args=(None,), daemon=True, name="envivo-dg").start()
            return label, "deepgram"
        raise last or LiveError("Deepgram no aceptó la configuración.")

    def send_audio(self, pcm16k):
        if self.closed.is_set() or self.ws is None:
            return False
        try:
            with self._send_lock:
                self.ws.send(bytes(pcm16k))
            return True
        except Exception as e:
            self._finish(f"envío fallido: {e}")
            return False

    def send_text(self, text):
        return self._send({"type": "InjectUserMessage", "content": text})

    def send_image(self, jpeg):
        return False                                   # el agente de voz de Deepgram no ve imágenes

    def send_tool_responses(self, responses):
        ok = True
        for r in responses:
            ok = self._send({"type": "FunctionCallResponse", "id": r["id"], "name": r["name"],
                             "content": json.dumps(r["response"], ensure_ascii=False)}) and ok
        return ok

    def _handle_raw(self, raw):
        if isinstance(raw, (bytes, bytearray)):
            _call(self.cb, "on_audio", bytes(raw))
            return
        msg = _parse(raw)
        if msg:
            self._dispatch(msg)

    def _dispatch(self, msg):
        cb, t = self.cb, msg.get("type", "")
        if t == "UserStartedSpeaking":
            _call(cb, "on_interrupted")
        elif t == "ConversationText":
            if msg.get("role") == "user":
                _call(cb, "on_input_text", (msg.get("content") or "") + " ")
            else:
                _call(cb, "on_output_text", (msg.get("content") or "") + " ")
        elif t == "AgentAudioDone":
            _call(cb, "on_turn_complete")
        elif t == "FunctionCallRequest":
            calls = []
            for f in msg.get("functions") or []:
                if f.get("client_side", True) is False:
                    continue
                args = f.get("arguments") or "{}"
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = {}
                calls.append({"id": f.get("id"), "name": f.get("name"), "args": args})
            if calls:
                threading.Thread(target=self._run_tools, args=(calls,), daemon=True).start()
        elif t == "Error":
            _call(cb, "on_error", msg.get("description") or "error")
            self._finish(f"Deepgram: {msg.get('description') or 'error'}")


def _safe_close(ws):
    try:
        ws.close()
    except Exception:
        pass
