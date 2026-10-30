"""Conector de IA (Ollama, Gemini, Claude, OpenAI y compatibles) y modo sin internet.

Parte de Jarvis (antes dentro de jarvis.py). Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import json
import os
import re
import skills
import socket
import threading
import time
import urllib.request

from nucleo import J


# =============================================================================
# CONECTOR DE IA: Ollama, Gemini, Claude y cualquier API compatible con OpenAI
# (ChatGPT, DeepSeek, Kimi, Grok, Mistral, Groq, OpenRouter, LM Studio...)
# =============================================================================
class AIError(Exception):
    """Error de IA con explicación en español.
    why  = motivo corto y claro (se dice en voz alta)
    kind = key | quota | balance | model | region | perm | server | bad | net | config"""

    def __init__(self, msg, code=None, raw="", kind="bad", why=None):
        super().__init__(msg)
        self.code, self.raw, self.kind = code, raw or msg, kind
        self.why = why or msg


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
_SHORT_REASON = {"key": "clave inválida", "quota": "sin cuota", "balance": "sin saldo",
                 "model": "modelo no disponible", "region": "región no admitida",
                 "perm": "sin permiso", "server": "servicio caído", "net": "sin conexión",
                 "config": "falta configurar", "bad": "error"}


def _api_message(body):
    """Saca el mensaje legible de un error JSON de cualquier proveedor."""
    try:
        d = json.loads(body)
    except ValueError:
        return re.sub(r"\s+", " ", body).strip()[:220]
    if isinstance(d, list) and d:
        d = d[0]
    err = d.get("error", d) if isinstance(d, dict) else d
    if isinstance(err, dict):
        return str(err.get("message") or err.get("type") or err)[:300]
    return str(err)[:300]


def _classify(code, body):
    msg = J._api_message(body)
    low = f"{msg} {body[:600]}".lower()
    if "location is not supported" in low or ("region" in low and "not supported" in low):
        kind, why = "region", "el servicio no está disponible en tu país o región"
    elif (code == 401 or "api key not valid" in low or "invalid api key" in low
          or "invalid x-api-key" in low or "incorrect api key" in low or "api_key_invalid" in low
          or "invalid_api_key" in low or "authentication" in low or "unauthorized" in low):
        kind, why = "key", "la clave de API no es válida. Revísala o crea una nueva"
    elif (code == 402 or "insufficient balance" in low or "credit balance" in low
          or "insufficient_quota" in low or "billing" in low or "payment" in low):
        kind, why = "balance", "tu cuenta no tiene saldo o crédito disponible"
    elif code == 429 or "quota" in low or "resource_exhausted" in low or "rate limit" in low:
        kind, why = "quota", "se agotó la cuota o hay demasiadas peticiones. Espera un minuto o revisa tu plan"
    elif (code == 404 or "model_not_found" in low or "no longer available" in low
          or ("model" in low and ("not found" in low or "does not exist" in low
                                  or "not available" in low or "not supported" in low
                                  or "no access" in low or "not have access" in low))):
        kind, why = "model", "el modelo elegido no existe o tu cuenta no tiene acceso a él"
    elif code == 403 or "permission" in low:
        kind, why = "perm", "tu clave no tiene permiso. Activa la API en tu cuenta del proveedor"
    elif (code or 0) >= 500 or "overloaded" in low:
        kind, why = "server", "el servicio está caído o saturado en este momento"
    else:
        kind, why = "bad", "el servicio rechazó la petición"
    return kind, why, msg


def _host(url):
    return urllib.parse.urlsplit(url).netloc or url


def _http(method, url, headers=None, payload=None, timeout=120, stream=False):
    """Petición HTTP con errores traducidos. Nunca incluye la URL completa en los mensajes
    (podría llevar una clave)."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    h = {"Content-Type": "application/json", "User-Agent": f"Jarvis/{J.VERSION}"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        kind, why, msg = J._classify(e.code, body)
        raise J.AIError(f"{why}. (HTTP {e.code}: {msg})", code=e.code, raw=body[:800], kind=kind, why=why)
    except urllib.error.URLError as e:
        raise J.AIError(f"Sin conexión con {J._host(url)}: {e.reason}. Revisa tu internet.",
                      code=0, kind="net", why=f"no hay conexión con {J._host(url)}. Revisa tu internet")
    except (TimeoutError, socket.timeout):
        raise J.AIError(f"{J._host(url)} tardó demasiado en responder.", code=0, kind="net",
                      why="el servicio tardó demasiado en responder")
    if stream:
        return r
    with r:
        txt = r.read().decode("utf-8", "replace")
    try:
        return json.loads(txt)
    except ValueError:
        raise J.AIError(f"Respuesta no válida de {J._host(url)}: {txt[:150]}")


def _http_json(method, url, api_key="", payload=None, timeout=120):
    """Compatibilidad con código antiguo."""
    return J._http(method, url, {"Authorization": f"Bearer {api_key}"} if api_key else None,
                 payload, timeout)


def _drop_path(obj, path):
    obj = json.loads(json.dumps(obj))
    cur, parts = obj, path.split(".")
    for p in parts[:-1]:
        cur = cur.get(p) if isinstance(cur, dict) else None
        if cur is None:
            return obj
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)
    return obj


def _post(url, headers, payload, optional=(), timeout=180, stream=False):
    """POST que se adapta: si el proveedor rechaza un parámetro opcional (temperatura,
    modo JSON, «pensamiento»...), lo quita y reintenta una vez."""
    try:
        return J._http("POST", url, headers, payload, timeout, stream)
    except J.AIError as e:
        if e.code != 400 or e.kind != "bad":
            raise
        low = e.raw.lower()
        drop = [p for p, words in optional if any(w in low for w in words)]
        if not drop and any(w in low for w in ("unsupported", "not supported", "unknown",
                                                "unrecognized", "invalid", "extra", "not allowed")):
            drop = [p for p, _ in optional]
        if not drop:
            raise
        for p in drop:
            payload = J._drop_path(payload, p)
        J.log_terminal(f"{J._host(url)} no acepta {', '.join(p.split('.')[-1] for p in drop)}; "
                     "reintento sin ello.", "IA")
        return J._http("POST", url, headers, payload, timeout, stream)


def _sse_lines(resp):
    """Recorre las líneas «data: ...» de una respuesta en streaming (SSE)."""
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk and chunk != "[DONE]":
                    yield chunk


def _png_b64(path):
    import base64
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _model_name(m):
    for key in ("model", "name"):
        v = m.get(key) if isinstance(m, dict) else getattr(m, key, None)
        if v:
            return str(v)
    return ""


def _ai_cfg(override=None):
    """Configuración efectiva del proveedor (los valores de «override» vienen de la página
    de Ajustes al pulsar «Probar»; los vacíos se toman de lo guardado)."""
    o = {k: v for k, v in (override or {}).items() if v not in (None, "")}
    pid = str(o.get("ai_provider") or J.settings["ai_provider"])
    if pid not in J.PROVIDERS:
        pid = "ollama"
    sp = J.PROVIDERS[pid]

    def get(k):
        return str(o.get(k, J.settings.get(k, "")) or "").strip()

    base = get("openai_base_url") if sp.get("custom") else sp.get("base", "")
    if override is None and pid != "ollama" and J.is_offline() and J.net["local_model"]:
        # sin internet: la IA de tu equipo (Ollama) responde mientras vuelve la conexión
        return dict(J._ai_cfg({"ai_provider": "ollama", "ollama_model": J.net["local_model"]}),
                    label="Ollama (sin internet)", offline=True)
    return {"ai_provider": pid, "kind": sp["kind"], "spec": sp, "label": sp["short"],
            "model": get(f"{pid}_model"), "key": "" if pid == "ollama" else get(f"{pid}_api_key"),
            "base": base.rstrip("/"),
            "ollama_host": get("ollama_host").rstrip("/") or J.DEFAULT_SETTINGS["ollama_host"]}


def _need_key(cfg):
    if cfg["kind"] != "ollama" and not cfg["spec"].get("custom") and not cfg["key"]:
        raise J.AIError(f"Falta la clave de API de {cfg['label']} (Ajustes › IA).", kind="config",
                      why=f"falta poner la clave de {cfg['label']} en Ajustes, sección IA")


# ---- Gemini (Google) --------------------------------------------------------
def _gemini_headers(cfg):
    return {"x-goog-api-key": cfg["key"]}          # la clave va en cabecera, no en la URL


def _gemini_body(cfg, messages, max_tokens, json_mode=False, image_path=None,
                 audio_wav=None, temperature=None):
    system = " ".join(m["content"] for m in messages if m["role"] == "system")
    contents = []
    for m in messages:
        if m["role"] == "system":
            continue
        role = "model" if m["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    if image_path:
        if not contents:
            contents.append({"role": "user", "parts": []})
        contents[-1]["parts"].append({"inlineData": {"mimeType": "image/png", "data": J._png_b64(image_path)}})
    if audio_wav:
        import base64
        if not contents:
            contents.append({"role": "user", "parts": []})
        contents[-1]["parts"].append({"inlineData": {"mimeType": "audio/wav",
                                                     "data": base64.b64encode(audio_wav).decode()}})
    gen = {"temperature": J.settings["ai_temperature"] if temperature is None else temperature,
           "maxOutputTokens": max_tokens}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    # «Pensamiento»: consume tokens de salida y retrasa la respuesta. Para hablar conviene
    # poco: Gemini 2.x flash se apaga (presupuesto 0); Gemini 3 flash en nivel bajo. Los
    # flash-lite ya vienen al mínimo y los pro piensan siempre. Si el modelo no acepta
    # este ajuste, _post lo quita solo.
    ml = cfg["model"].lower()
    if re.match(r"gemini-[12]\.", ml):
        if "flash" in ml:
            gen["thinkingConfig"] = {"thinkingBudget": 0}
    elif "flash" in ml and "lite" not in ml:
        gen["thinkingConfig"] = {"thinkingLevel": "low"}
    body = {"contents": contents, "generationConfig": gen}
    if system.strip():
        body["systemInstruction"] = {"parts": [{"text": system}]}
    return body


_GEMINI_OPTIONAL = (("generationConfig.thinkingConfig", ("thinking",)),
                    ("generationConfig.responseMimeType", ("mime",)),
                    ("generationConfig.temperature", ("temperature",)))


def _gemini_text(data, strip=True):
    if isinstance(data, dict) and data.get("error"):
        kind, why, msg = J._classify(data["error"].get("code"), json.dumps(data))
        raise J.AIError(f"Gemini: {msg}", kind=kind, why=why)
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return ""
    txt = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return txt.strip() if strip else txt


def gemini_chat(cfg, messages, json_mode=False, max_tokens=2048, image_path=None):
    url = f"{J.GEMINI_BASE}/models/{cfg['model']}:generateContent"
    data = J._post(url, J._gemini_headers(cfg),
                 J._gemini_body(cfg, messages, max_tokens, json_mode, image_path), J._GEMINI_OPTIONAL)
    return J._gemini_text(data)


def gemini_stream(cfg, messages, image_path=None):
    url = f"{J.GEMINI_BASE}/models/{cfg['model']}:streamGenerateContent?alt=sse"
    resp = J._post(url, J._gemini_headers(cfg), J._gemini_body(cfg, messages, 2048, image_path=image_path),
                 J._GEMINI_OPTIONAL, stream=True)

    def it():
        for chunk in J._sse_lines(resp):
            try:
                txt = J._gemini_text(json.loads(chunk), strip=False)
            except ValueError:
                continue
            if txt:
                yield txt
    return it()


# ---- Claude (Anthropic) -----------------------------------------------------
def _anthropic_headers(cfg):
    return {"x-api-key": cfg["key"], "anthropic-version": "2023-06-01"}


def _anthropic_body(cfg, messages, max_tokens, image_path=None, stream=False):
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    conv = []
    for m in messages:                       # Claude exige turnos alternos usuario/asistente
        if m["role"] == "system":
            continue
        role = "assistant" if m["role"] == "assistant" else "user"
        if conv and conv[-1]["role"] == role:
            conv[-1]["content"][0]["text"] += "\n" + m["content"]
        else:
            conv.append({"role": role, "content": [{"type": "text", "text": m["content"]}]})
    if conv and conv[0]["role"] == "assistant":
        conv.insert(0, {"role": "user", "content": [{"type": "text", "text": "(continuamos)"}]})
    if image_path and conv:
        conv[-1]["content"].insert(0, {"type": "image", "source": {
            "type": "base64", "media_type": "image/png", "data": J._png_b64(image_path)}})
    # Sin «temperature»: los modelos Claude actuales la rechazan si no es la de fábrica.
    body = {"model": cfg["model"], "max_tokens": max_tokens, "messages": conv}
    if system:
        body["system"] = system
    if stream:
        body["stream"] = True
    return body


def anthropic_chat(cfg, messages, max_tokens=1024, image_path=None):
    data = J._post(cfg["base"] + "/messages", J._anthropic_headers(cfg),
                 J._anthropic_body(cfg, messages, max_tokens, image_path))
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()


def anthropic_stream(cfg, messages, image_path=None):
    resp = J._post(cfg["base"] + "/messages", J._anthropic_headers(cfg),
                 J._anthropic_body(cfg, messages, 1024, image_path, stream=True), stream=True)

    def it():
        for chunk in J._sse_lines(resp):
            try:
                ev = json.loads(chunk)
            except ValueError:
                continue
            if ev.get("type") == "error":
                kind, why, msg = J._classify(None, chunk)
                raise J.AIError(f"Claude: {msg}", kind=kind, why=why)
            d = ev.get("delta") or {}
            if ev.get("type") == "content_block_delta" and d.get("type") == "text_delta" and d.get("text"):
                yield d["text"]
    return it()


# ---- APIs compatibles con OpenAI ----------------------------------------------
def _oa_headers(cfg):
    h = {"Authorization": f"Bearer {cfg['key']}"} if cfg["key"] else {}
    if cfg["ai_provider"] == "openrouter":
        h["X-Title"] = "Jarvis"
    return h


def _oa_body(cfg, messages, max_tokens, json_mode=False, stream=False, image_path=None):
    sp = cfg["spec"]
    msgs = [dict(m) for m in messages]
    if image_path and msgs:
        msgs[-1]["content"] = [{"type": "text", "text": msgs[-1]["content"]},
                               {"type": "image_url",
                                "image_url": {"url": "data:image/png;base64," + J._png_b64(image_path)}}]
    tp = sp.get("tokens_param", "max_tokens")
    body = {"model": cfg["model"], "messages": msgs, tp: max_tokens}
    if not sp.get("no_temp"):
        body["temperature"] = J.settings["ai_temperature"]
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if stream:
        body["stream"] = True
    return body, (("temperature", ("temperature",)), ("response_format", ("response_format", "json")),
                  (tp, (tp,)))


def openai_chat(cfg, messages, json_mode=False, max_tokens=1024, image_path=None):
    body, opt = J._oa_body(cfg, messages, max_tokens, json_mode, image_path=image_path)
    data = J._post(cfg["base"] + "/chat/completions", J._oa_headers(cfg), body, opt)
    try:
        return (data["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError):
        raise J.AIError(f"Respuesta inesperada de {cfg['label']}: {str(data)[:200]}")


def openai_stream(cfg, messages, image_path=None):
    body, opt = J._oa_body(cfg, messages, 1024, stream=True, image_path=image_path)
    resp = J._post(cfg["base"] + "/chat/completions", J._oa_headers(cfg), body, opt, stream=True)

    def it():
        for chunk in J._sse_lines(resp):
            try:
                d = json.loads(chunk)
            except ValueError:
                continue
            if d.get("error"):
                kind, why, msg = J._classify(None, chunk)
                raise J.AIError(f"{cfg['label']}: {msg}", kind=kind, why=why)
            for ch in d.get("choices") or []:
                txt = (ch.get("delta") or {}).get("content")
                if txt:
                    yield txt
    return it()


# ---- Lista de modelos y elección automática -----------------------------------
def ai_list_models(cfg):
    kind = cfg["kind"]
    if kind == "ollama":
        if J.ollama is None:
            raise J.AIError("Falta la librería 'ollama' (pip install ollama).", kind="config")
        try:
            resp = J.ollama.Client(host=cfg["ollama_host"], timeout=8).list()
        except Exception as e:
            raise J.AIError(f"Ollama no responde en {cfg['ollama_host']}: {e}", kind="net",
                          why="Ollama no está abierto en este equipo")
        models = resp.models if hasattr(resp, "models") else resp["models"]
        return sorted(filter(None, (J._model_name(m) for m in models)))
    J._need_key(cfg)
    if kind == "gemini":
        data = J._http("GET", f"{J.GEMINI_BASE}/models?pageSize=200", J._gemini_headers(cfg), timeout=10)
        out = []
        for m in data.get("models", []):
            name = (m.get("name") or "").replace("models/", "")
            if ("generateContent" in (m.get("supportedGenerationMethods") or [])
                    and name.startswith("gemini") and not J.MODEL_EXCLUDE.search(name)):
                out.append(name)
        return sorted(set(out))
    if kind == "anthropic":
        data = J._http("GET", cfg["base"] + "/models?limit=100", J._anthropic_headers(cfg), timeout=10)
        return sorted(m["id"] for m in data.get("data", []) if m.get("id"))
    data = J._http("GET", cfg["base"] + "/models", J._oa_headers(cfg), timeout=10)
    items = data.get("data", data if isinstance(data, list) else [])
    ids = [m.get("id", "") for m in items if isinstance(m, dict)]
    return sorted(i for i in ids if i and not J.MODEL_EXCLUDE.search(i))


def _version_key(name):
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", name)[:3]]
    unstable = bool(re.search(r"preview|exp|beta|alpha|\d{4}-\d{2}|\d{8}", name))
    return (not unstable, nums, -len(name))


def _recommend_model(pid, models, exclude=()):
    """El modelo más adecuado para hablar entre los que tiene tu cuenta."""
    sp = J.PROVIDERS[pid]
    models = [m for m in models if m not in exclude]
    if not models:
        return ""
    if sp.get("model") in models:
        return sp["model"]
    for pat in sp.get("prefer", []):
        cands = [m for m in models if re.search(pat, m)]
        if cands:
            return max(cands, key=J._version_key)
    return "" if sp["kind"] == "ollama" else models[0]


def _switch_model(cfg, new, reason):
    key = f"{cfg['ai_provider']}_model"
    old = J.settings.get(key, "")
    with J.settings_lock:
        J.settings[key] = new
        try:
            J.save_settings_file()
        except Exception:
            pass
    J.log_terminal(f"{cfg['label']}: uso el modelo «{new}» en vez de «{old or 'ninguno'}» ({reason}).", "IA")
    try:
        J.socketio.emit("settings_updated", J.public_settings())
    except Exception:
        pass
    return dict(cfg, model=new)


def _ensure_model(cfg):
    """Si no hay modelo elegido, toma el mejor de la cuenta."""
    if cfg["model"] or cfg["kind"] == "ollama":
        return cfg
    best = J._recommend_model(cfg["ai_provider"], J.ai_list_models(cfg))
    if not best:
        raise J.AIError("No hay modelo seleccionado. Elige uno en Ajustes › IA.", kind="config",
                      why="no hay modelo elegido. Elige uno en Ajustes, sección IA")
    return J._switch_model(cfg, best, "no había ninguno elegido")


def _with_fallback(cfg, fn):
    """Ejecuta fn(cfg). Si el modelo no existe o la cuenta no tiene acceso (p. ej. Gemini 2.5
    con claves nuevas), cambia solo al mejor modelo disponible y reintenta."""
    cfg = J._ensure_model(cfg)
    try:
        return fn(cfg)
    except J.AIError as e:
        if e.kind != "model" or cfg["kind"] == "ollama":
            raise
        try:
            models = J.ai_list_models(cfg)
        except J.AIError:
            raise e
        best = J._recommend_model(cfg["ai_provider"], models, exclude=(cfg["model"],))
        if not best:
            raise
        return fn(J._switch_model(cfg, best, "el anterior no está disponible para tu cuenta"))


def _cloud_chat(cfg, messages, json_mode=False, image_path=None, max_tokens=None):
    tokens = max_tokens or (1024 if json_mode else 2048)
    if cfg["kind"] == "gemini":
        return J.gemini_chat(cfg, messages, json_mode, tokens, image_path)
    if cfg["kind"] == "anthropic":
        return J.anthropic_chat(cfg, messages, tokens, image_path)
    return J.openai_chat(cfg, messages, json_mode, tokens, image_path)


def _cloud_stream(cfg, messages, image_path=None):
    if cfg["kind"] == "gemini":
        return J.gemini_stream(cfg, messages, image_path)
    if cfg["kind"] == "anthropic":
        return J.anthropic_stream(cfg, messages, image_path)
    return J.openai_stream(cfg, messages, image_path)


def _current_model(cfg):
    return cfg["model"]


def ai_chat(messages, json_mode=False, max_tokens=None):
    cfg = J._ai_cfg()
    if cfg["kind"] == "ollama" and not cfg["model"]:
        raise J.AIError("No hay modelo seleccionado. Elige uno en Ajustes › IA.", kind="config",
                      why="no hay modelo elegido. Elige uno en Ajustes, sección IA")
    J.thinking += 1
    J.refresh_mode()
    try:
        if cfg["kind"] == "ollama":
            if J.ollama is None:
                raise J.AIError("Falta la librería 'ollama'.", kind="config")
            kwargs = {"format": "json"} if json_mode else {}
            # keep_alive mantiene el modelo cargado en RAM (no se recarga en cada orden);
            # num_predict limita la longitud -> responde/habla antes.
            opts = {"temperature": J.settings["ai_temperature"],
                    "num_predict": max_tokens or (120 if json_mode else 220)}
            try:
                r = J.ollama.Client(host=cfg["ollama_host"], timeout=180).chat(
                    model=cfg["model"], messages=messages, options=opts, keep_alive="30m", **kwargs)
            except Exception as e:
                raise J.AIError(str(e), kind="net", why="Ollama no responde")
            return r["message"]["content"].strip()
        J._need_key(cfg)
        try:
            return J._with_fallback(cfg, lambda c: J._cloud_chat(c, messages, json_mode, max_tokens=max_tokens))
        except J.AIError as e:
            # Se cayó el internet a mitad de la petición: se repite con la IA del equipo.
            if e.kind == "net" and J.net_recheck() and J._ai_cfg()["kind"] == "ollama":
                J.log_terminal("Sin internet: respondo con la IA de tu equipo.", "RED")
                return J.ai_chat(messages, json_mode, max_tokens)
            raise
    finally:
        J.thinking -= 1
        J.refresh_mode()


def ai_test(override=None):
    """Prueba REAL: lista modelos y además pide una respuesta corta. Así «conectado»
    significa que Jarvis podrá contestar, no solo que la clave abre la lista."""
    cfg = J._ai_cfg(override)
    models = J.ai_list_models(cfg)
    rec = J._recommend_model(cfg["ai_provider"], models) if models else ""
    model = cfg["model"] or rec
    if not model:
        return {"models": models, "recommended": rec, "test_ok": False,
                "test_msg": "No hay modelos disponibles."}
    msgs = [{"role": "user", "content": "Responde solo con la palabra: listo"}]
    t0 = time.time()
    try:
        if cfg["kind"] == "ollama":
            out = J.ollama.Client(host=cfg["ollama_host"], timeout=60).chat(
                model=model, messages=msgs, options={"num_predict": 8})["message"]["content"]
        else:
            out = J._cloud_chat(dict(cfg, model=model), msgs)
        return {"models": models, "recommended": rec, "model": model, "test_ok": True,
                "test_msg": f"responde bien con «{model}» ({time.time() - t0:.1f} s): «{out.strip()[:40]}»"}
    except Exception as e:
        why = getattr(e, "why", str(e))
        res = {"models": models, "recommended": rec, "model": model, "test_ok": False,
               "test_msg": f"la lista abre, pero «{model}» no responde: {why}."}
        if getattr(e, "kind", "") == "model":
            alt = J._recommend_model(cfg["ai_provider"], models, exclude=(model,))
            if alt:
                try:
                    J._cloud_chat(dict(cfg, model=alt), msgs)
                    res.update(suggest=alt, test_msg=res["test_msg"] + f" «{alt}» sí funciona: lo dejo elegido.")
                except Exception:
                    pass
        return res


def check_ai(verbose=False):
    cfg = J._ai_cfg()
    label = cfg["label"]
    try:
        models = J.ai_list_models(cfg)
    except J.AIError as e:
        if e.code == 404 and cfg["kind"] != "ollama":   # el servicio no publica su lista
            J.set_state(ai="ok", ai_label=f"{label} · {cfg['model'] or 'auto'}")
            return True
        J.set_state(ai="error", ai_label=f"{label} · {J._SHORT_REASON.get(e.kind, 'sin conexión')}")
        if verbose:
            J.log_terminal(f"{label}: {e}", "AVISO")
        return False
    model = cfg["model"]
    present = bool(model) and any(m == model or m.startswith(model + ":") for m in models)
    if not present and cfg["kind"] != "ollama" and models:
        best = J._recommend_model(cfg["ai_provider"], models)
        if best and best != model:
            J._switch_model(cfg, best, "el elegido no está en tu cuenta" if model else "no había ninguno elegido")
            model, present = best, True
        elif cfg["ai_provider"] == "openrouter" and model:
            present = True                              # «openrouter/auto» no sale en la lista
    if present:
        J.set_state(ai="ok", ai_label=f"{label} · {model}")
    else:
        J.set_state(ai="warn", ai_label=f"{label} · falta modelo")
        if verbose:
            hint = f" Ejecuta: ollama pull {model}" if cfg["kind"] == "ollama" and model else ""
            J.log_terminal(f"El modelo '{model or '(ninguno)'}' no está disponible.{hint}", "AVISO")
    return present


def _ai_monitor():
    while True:
        time.sleep(60)
        J.check_ai()

# =============================================================================
# SIN INTERNET: Jarvis sigue funcionando solo. Si se cae la conexión, la IA pasa a
# Ollama (en tu equipo), la voz a Piper y la escucha a lo local. Cuando vuelve, regresa.
# =============================================================================
net = {"offline": False, "since": 0.0, "fails": 0, "local_model": "", "local_at": 0.0}
_net_lock = threading.Lock()
NET_PROBES = (("1.1.1.1", 443), ("8.8.8.8", 53), ("208.67.222.222", 443))
NET_HTTP_PROBE = "http://www.msftconnecttest.com/connecttest.txt"   # la misma que usa Windows


def _internet_ok():
    """¿Hay internet? Primero conexiones directas (rápidas); si fallan, una petición web
    normal, que sí pasa por el proxy del colegio si lo hay."""
    for host, port in J.NET_PROBES:
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            pass
    try:
        with urllib.request.urlopen(J.NET_HTTP_PROBE, timeout=4) as r:
            return r.status < 500
    except Exception:
        return False


def local_ai_model(refresh=False):
    """Modelo de Ollama instalado en este equipo para usar sin internet ('' si no hay)."""
    if not refresh and time.time() - J.net["local_at"] < 120:
        return J.net["local_model"]
    model = ""
    try:
        if J.ollama is not None:
            names = J.ai_list_models(J._ai_cfg({"ai_provider": "ollama"}))
            names = [n for n in names if "embed" not in n.lower()]

            def present(m):
                return next((n for n in names if m and (n == m or n.startswith(m + ":"))), "")
            model = (present(J.settings["offline_model"].strip()) or present(J.settings["ollama_model"].strip())
                     or (names[0] if names else ""))
    except Exception:
        model = ""
    J.net.update(local_model=model, local_at=time.time())
    return model


def is_offline():
    return J.net["offline"] and J.settings["offline_auto"]


def _net_set(online):
    with J._net_lock:
        if online:
            J.net["fails"] = 0
            if not J.net["offline"]:
                return False
            mins = (time.time() - J.net["since"]) / 60
            J.net.update(offline=False)
        else:
            J.net["fails"] += 1
            if J.net["offline"] or J.net["fails"] < 2:    # 2 fallos seguidos: evita falsas alarmas
                return False
            J.net.update(offline=True, since=time.time())
    if online:
        J.log_terminal(f"Volvió el internet (estuvo caído {mins:.0f} min).", "RED")
        J.set_state(net="online")
        threading.Thread(target=J.check_ai, daemon=True).start()
        if J.settings["offline_auto"] and J.settings["ai_provider"] != "ollama":
            J.reply(f"Volvió el internet. Vuelvo a usar {J._ai_cfg()['label']}.", "RED")
        return True
    J.set_state(net="offline")
    J.log_terminal("Sin internet.", "RED")
    if not J.settings["offline_auto"]:
        return True
    m = J.local_ai_model(refresh=True)
    threading.Thread(target=J.check_ai, daemon=True).start()
    if J.settings["ai_provider"] == "ollama":
        msg = "Se cayó el internet. Sigo funcionando normal con la IA de tu equipo."
    elif m:
        msg = f"Se cayó el internet. Sigo funcionando sin conexión, con la IA de tu equipo ({m.split(':')[0]})."
    else:
        msg = ("Se cayó el internet. Las órdenes del computador siguen funcionando, pero para "
               "responder preguntas necesito internet o una IA local con Ollama.")
    J.reply(msg, "RED")
    return True


def net_recheck():
    """Tras un error de red en una petición: comprueba ya. True si estamos sin internet."""
    if not J.settings["offline_auto"]:
        return False
    if J._internet_ok():
        J._net_set(True)
        return False
    J.net["fails"] = max(J.net["fails"], 1)               # el error de la petición cuenta como un fallo
    J._net_set(False)
    return J.net["offline"]


def _net_worker():
    while True:
        time.sleep(10 if J.net["offline"] else 20)
        try:
            J._net_set(J._internet_ok())
        except Exception as e:
            J.log_terminal(f"Comprobación de red: {e}", "AVISO")



def warm_ai():
    """Carga el modelo en memoria al arrancar para que la primera orden sea rápida."""
    cfg = J._ai_cfg()
    if cfg["kind"] != "ollama" or J.ollama is None or not cfg["model"]:
        return
    try:
        J.ollama.Client(host=cfg["ollama_host"], timeout=120).chat(
            model=cfg["model"], messages=[{"role": "user", "content": "hola"}],
            options={"num_predict": 1}, keep_alive="30m")
        J.log_terminal("Modelo de IA precargado y listo.", "SISTEMA")
    except Exception:
        pass


def ai_error_reply(e):
    """Frase hablada cuando la IA falla: dice el motivo real, no un genérico."""
    cfg = J._ai_cfg()
    why = getattr(e, "why", "") or "no respondió"
    return f"No pude usar {cfg['label']}: {why}."


chat_history = []
MEMORY_PATH = os.path.join(J.CONFIG_DIR, "memoria.json")


def load_memory():
    try:
        with open(J.MEMORY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            J.chat_history[:] = [m for m in data if isinstance(m, dict) and "role" in m and "content" in m][-40:]
    except (FileNotFoundError, ValueError, OSError):
        pass


def save_memory():
    try:
        os.makedirs(J.CONFIG_DIR, exist_ok=True)
        tmp = J.MEMORY_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(J.chat_history[-40:], f, ensure_ascii=False)
        os.replace(tmp, J.MEMORY_PATH)
    except OSError:
        pass


def clear_memory():
    J.chat_history.clear()
    try:
        os.remove(J.MEMORY_PATH)
    except OSError:
        pass


# Resumen de todo lo que Jarvis sabe hacer (para mostrarlo en Ajustes › Acerca de).
CAPABILITIES = [
    ("Control del PC", ["abre Spotify", "cierra esto", "cambia a Excel", "minimiza todo", "pantalla completa", "¿qué ventanas hay?"]),
    ("Leer en voz alta", ["selecciona un texto y di: lee esto", "léeme la selección"]),
    ("Audio y música", ["sube el volumen", "volumen al 30", "silencio", "pausa", "siguiente canción"]),
    ("Clase y presentaciones", ["siguiente diapositiva", "inicia la presentación", "activa el videobeam", "abre el taller de estadística"]),
    ("Dictado por voz", ["inicia el dictado", "modo matemáticas", "marca la casilla", "siguiente campo", "terminar dictado"]),
    ("Matemáticas", ["cuánto es el 15% de 240", "resuelve 2x+3=7", "deriva x al cuadrado", "factoriza x al cuadrado menos 4"]),
    ("Temporizadores", ["pon un temporizador de 15 minutos para el examen", "cuánto queda", "cancela el temporizador"]),
    ("Recordatorios y rutinas", ["recuérdame en 10 minutos sacar la ropa", "reporte matutino"]),
    ("Documentos", ["crear documento STEAM sobre energía solar", "numerología 15/08/1990"]),
    ("Web y búsquedas", ["busca recetas de arepas", "pon Despacito en YouTube", "abre youtube"]),
    ("Visión de pantalla", ["¿qué hay en la pantalla?", "describe la pantalla", "qué ves"]),
    ("Rutinas", ["modo clase", "fin de clase", "modo planeación", "¿qué rutinas tengo?",
                 "silencia las notificaciones", "activa las notificaciones",
                 "crea una rutina buenos días a las 7 de lunes a viernes que diga el clima y mis pendientes"]),
    ("Prueba completa", ["prueba completa", "revisa todo", "(en Telegram) /prueba"]),
    ("Avísame cuando termine", ["avísame cuando termine la descarga", "avísame cuando se cierre Zoom",
                                "avísame cuando termine de instalar", "¿qué estás vigilando?"]),
    ("Diario", ["¿qué hice ayer?", "¿qué hice hoy?", "resume mi semana", "borra mi diario"]),
    ("Habilidades", ["busca la fotosíntesis en wikipedia", "cómo se dice buenos días en inglés", "modo concentración",
                     "dame un dato curioso de los volcanes", "¿qué habilidades tengo?"]),
    ("Leer el tablero", ["lee lo que hay en el tablero", "pasa esta hoja a Word", "haz un quiz con lo que hay en el tablero"]),
    ("Conectores (MCP)", ["lo que ofrezcan los conectores que añadas en Ajustes › Integraciones"]),
    ("Lo que sabe de ti", ["mi hermana se llama Ana", "me gusta el vallenato", "¿cómo se llama mi hermana?",
                           "¿qué sabes de mí?", "olvida que me gusta el vallenato"]),
    ("Calendario", ["¿qué tengo hoy?", "¿cuál es mi próxima clase?", "¿qué sigue?", "¿qué tengo esta semana?",
                    "actualiza el calendario"]),
    ("Memoria", ["recuerda que la reunión de padres es el jueves a las 3", "anota que debo comprar marcadores",
                 "¿qué tengo pendiente?", "¿qué tengo mañana?", "ya hice lo de los marcadores",
                 "borra la nota de la reunión", "¿cuándo era la reunión de padres?"]),
    ("Aula", ["escoge un estudiante", "¿quién pasa al tablero?", "haz grupos de 4", "haz parejas",
              "llama a lista", "falta Juan", "guarda la asistencia", "usa el curso 7A",
              "activa el semáforo de ruido", "abre el tablero"]),
    ("Revisar trabajos", ["revisa el taller de Juan (muéstralo a la cámara)",
                          "califica este examen en la pantalla", "corrige la tarea de Sofía"]),
    ("Material de clase (Word)", ["crea un quiz de 10 preguntas sobre fracciones para séptimo",
                                  "hazme un taller de ecuaciones para grado 8",
                                  "prepara una rúbrica para exposiciones orales",
                                  "haz un plan de clase sobre el ciclo del agua"]),
    ("Ayuda con tu pantalla", ["ayúdame con esto", "¿qué me sugieres?", "revisa lo que estoy haciendo",
                               "activa el copiloto", "copiloto cada 10 minutos", "desactiva el copiloto"]),
    ("Música (Spotify)", ["reproduce Despacito en Spotify", "pausa Spotify", "siguiente en Spotify"]),
    ("Presentaciones y Excel", ["haz una presentación de 8 diapositivas sobre el ciclo del agua para quinto",
                                "crea la planilla de notas de 7A con 4 notas",
                                "crea una tabla en Excel de los planetas con su distancia al sol"]),
    ("En vivo: ver", ["(en la conversación en vivo) mira esto", "mira mi pantalla y ayúdame", "deja de mirar"]),
    ("Clima y noticias", ["¿cómo está el clima?", "¿va a llover mañana?", "clima en Cali", "noticias", "noticias de educación"]),
    ("Buscar en internet", ["busca en internet qué pasó con la reforma educativa", "averigua cuándo es el día del maestro", "busca la biografía de Policarpa y resúmemela"]),
    ("Manejar el navegador", ["busca el ciclo del agua en una pestaña nueva", "cambia de pestaña", "busca la palabra fotosíntesis en la página", "baja la página", "ve atrás", "recarga la página"]),
    ("Desde el celular (Telegram)", ["escríbele a tu bot: ¿qué tengo hoy?", "abre la presentación", "recuérdame a las 3 llamar a la coordinadora"]),
    ("Sismos y correo", ["avísame de los sismos (actívalo en Ajustes)", "escríbele un correo a la coordinadora diciendo que mañana llego a las 7"]),
    ("Personal", ["llámame profe", "trabajo en el colegio San José", "apaga el pc a las 6", "Jarvis, descansa"]),
    ("Mensajería", ["manda un whatsapp a Juan que llego tarde", "manda un telegram diciendo reunión a las 3"]),
    ("Pantalla y archivos", ["toma una captura de pantalla", "busca el archivo informe", "brillo al 70"]),
    ("Modo sigilo", ["modo sigilo", "mostrar panel"]),
    ("Sistema (piden confirmación)", ["bloquea el equipo", "apaga el equipo", "vacía la papelera", "actualízate"]),
    ("Inteligencia artificial", ["cualquier pregunta: ¿cuál es la capital de Francia?", "escríbeme un poema"]),
]


ROUTER_PROMPT = """

Además controlas este PC con Windows mediante estas acciones:
{skills}

Responde SIEMPRE con un único objeto JSON con este formato:
{{"accion": "nombre_de_la_accion o chat", "args": {{...}}, "respuesta": "texto"}}
- Si el usuario pide hacer algo en el PC que corresponde a una acción, pon su nombre en "accion" y sus datos en "args".
- Si es una pregunta o una conversación, usa "accion": "chat" y escribe tu respuesta en "respuesta".
- No inventes acciones que no estén en la lista.
- Interpreta la intención aunque no la digan como orden: «está muy oscuro aquí» → subir el brillo
  (brillo con nivel 80); «hay demasiada luz en la pantalla» → bajar el brillo; «esto suena muy duro» → bajar el
  volumen; «quiero escuchar algo alegre» → poner música alegre en YouTube; «no oigo nada» → subir el volumen.
- Si la frase es una pregunta o una conversación (no pide hacer nada), es "chat"."""


def _extract_json(text):
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def ask_ai(prompt, route=False):
    """Devuelve ('chat', respuesta) o ('skill', nombre, args)."""
    system = J.settings["system_prompt"] + J.ACTION_RULE + J.VOICE_RULE + f" Hoy es {J.fecha_hablada(datetime.date.today())}." + J._notes_ctx() + J._user_ctx(prompt)
    if route:
        # Seguridad: la IA solo ve acciones NO destructivas. Apagar, reiniciar, vaciar la
        # papelera, etc. nunca se activan por interpretación: solo con la orden directa exacta.
        # 7.5: solo las acciones y conectores que tienen que ver con la orden (por significado).
        system += J.ROUTER_PROMPT.format(skills=J.router_catalog(prompt))
    user_msg = {"role": "user", "content": prompt}
    keep = J.settings["history_turns"] * 2
    history = J.chat_history[-keep:] if keep else []
    try:
        raw = J.ai_chat([{"role": "system", "content": system}, *history, user_msg], json_mode=route)
    except J.AIError as e:
        J.log_terminal(f"Error de IA: {e}", "ERROR")
        threading.Thread(target=J.check_ai, daemon=True).start()
        return ("chat", J.ai_error_reply(e))

    answer = raw
    if route:
        try:
            data = J._extract_json(raw)
        except Exception:
            data = {"accion": "chat", "respuesta": raw}
        if not isinstance(data, dict):
            data = {"accion": "chat", "respuesta": str(data)}
        action = str(data.get("accion") or "chat").strip()
        args = data.get("args") if isinstance(data.get("args"), dict) else {}
        if J.mcp_hub.find(action):
            J.chat_history.extend([user_msg, {"role": "assistant", "content": f"(usé el conector {action})"}])
            del J.chat_history[:-max(keep, 2)]
            J.save_memory()
            return ("mcp", action, args)
        sk = skills.REGISTRY.get(action)
        if sk and sk.dangerous:
            # Blindaje: nunca ejecutar acciones destructivas elegidas por la IA.
            J.log_terminal(f"IA propuso una acción peligrosa ({action}); la ignoro por seguridad.", "AVISO")
            sk = None
            action = "chat"
        if sk:
            J.chat_history.extend([user_msg, {"role": "assistant", "content": f"(ejecuté la acción {action})"}])
            del J.chat_history[:-max(keep, 2)]
            J.save_memory()
            return ("skill", action, args)
        answer = str(data.get("respuesta") or "").strip() or "No estoy seguro de cómo ayudarte con eso."

    J.chat_history.extend([user_msg, {"role": "assistant", "content": answer}])
    del J.chat_history[:-max(keep, 2)]
    J.save_memory()
    return ("chat", answer)


# Preguntas claras: se responden en streaming (Jarvis habla la 1ª frase mientras genera el resto).
QUESTION_RE = re.compile(
    r"\b(?:que|quien|quienes|cual|cuales|como|cuando|donde|por que|para que|cuanto|cuanta|cuantos|"
    r"explica|explicame|define|definicion|dime|cuentame|hablame|resume|resumen|traduce|significa|"
    r"sabes|conoces|describe|diferencia)\b")
_SENT_END = re.compile(r"[.!?…:](\s|$)")


def _stream_chunks(cfg, msgs):
    """Fragmentos de texto del proveedor actual, a medida que se generan.
    La conexión se abre ya (así, si el modelo no existe, se cambia por otro antes de hablar)."""
    if cfg["kind"] != "ollama":
        J._need_key(cfg)
        return J._with_fallback(cfg, lambda c: J._cloud_stream(c, msgs))

    def oll():
        stream = J.ollama.Client(host=cfg["ollama_host"], timeout=180).chat(
            model=cfg["model"], messages=msgs, stream=True, keep_alive="30m",
            options={"temperature": J.settings["ai_temperature"], "num_predict": 240})
        for part in stream:
            chunk = (part.get("message") or {}).get("content", "")
            if chunk:
                yield chunk
    return oll()


def answer_question_streaming(prompt):
    """Responde una pregunta hablando por frases a medida que el modelo las genera."""
    cfg = J._ai_cfg()
    if cfg["kind"] == "ollama" and (J.ollama is None or not cfg["model"]):
        J.reply(J.ask_ai(prompt, route=False)[1])
        return
    system = J.settings["system_prompt"] + J.ACTION_RULE + J.VOICE_RULE + f" Hoy es {J.fecha_hablada(datetime.date.today())}." + J._notes_ctx() + J._user_ctx(prompt)
    user_msg = {"role": "user", "content": prompt}
    keep = J.settings["history_turns"] * 2
    history = J.chat_history[-keep:] if keep else []
    msgs = [{"role": "system", "content": system}, *history, user_msg]

    J.thinking += 1
    J.refresh_mode()
    full, buf = "", ""
    try:
        for chunk in J._stream_chunks(cfg, msgs):
            full += chunk
            buf += chunk
            m = J._SENT_END.search(buf)
            while m:                                  # habla cada frase completa al instante
                sent = buf[:m.end()].strip()
                buf = buf[m.end():]
                if len(sent) > 1:
                    J.speak(J._clean_for_speech(sent))
                m = J._SENT_END.search(buf)
    except Exception as e:
        J.log_terminal(f"Error de IA (streaming): {e}", "ERROR")
        if (not full.strip() and getattr(e, "kind", "") == "net" and cfg["kind"] != "ollama"
                and J.net_recheck() and J._ai_cfg()["kind"] == "ollama"):
            J.reply(J.ask_ai(prompt, route=False)[1])     # sin internet: responde la IA del equipo
            return
        threading.Thread(target=J.check_ai, daemon=True).start()
        if full.strip():                              # ya había dicho parte: se queda ahí
            J.push_chat("jarvis", full.strip(), "JARVIS")
        else:
            J.reply(J.ai_error_reply(e))
        return
    finally:
        J.thinking -= 1
        J.refresh_mode()

    if buf.strip():
        J.speak(J._clean_for_speech(buf))
    full = full.strip() or "No estoy seguro de cómo responder."
    J.log_terminal(full, "JARVIS")
    J.push_chat("jarvis", full, "JARVIS")
    J.chat_history.extend([user_msg, {"role": "assistant", "content": full}])
    del J.chat_history[:-max(keep, 2)]
    J.save_memory()


__all__ = [
    'AIError',
    'CAPABILITIES',
    'GEMINI_BASE',
    'MEMORY_PATH',
    'NET_HTTP_PROBE',
    'NET_PROBES',
    'QUESTION_RE',
    'ROUTER_PROMPT',
    '_GEMINI_OPTIONAL',
    '_SENT_END',
    '_SHORT_REASON',
    '_ai_cfg',
    '_ai_monitor',
    '_anthropic_body',
    '_anthropic_headers',
    '_api_message',
    '_classify',
    '_cloud_chat',
    '_cloud_stream',
    '_current_model',
    '_drop_path',
    '_ensure_model',
    '_extract_json',
    '_gemini_body',
    '_gemini_headers',
    '_gemini_text',
    '_host',
    '_http',
    '_http_json',
    '_internet_ok',
    '_model_name',
    '_need_key',
    '_net_lock',
    '_net_set',
    '_net_worker',
    '_oa_body',
    '_oa_headers',
    '_png_b64',
    '_post',
    '_recommend_model',
    '_sse_lines',
    '_stream_chunks',
    '_switch_model',
    '_version_key',
    '_with_fallback',
    'ai_chat',
    'ai_error_reply',
    'ai_list_models',
    'ai_test',
    'answer_question_streaming',
    'anthropic_chat',
    'anthropic_stream',
    'ask_ai',
    'chat_history',
    'check_ai',
    'clear_memory',
    'gemini_chat',
    'gemini_stream',
    'is_offline',
    'load_memory',
    'local_ai_model',
    'net',
    'net_recheck',
    'openai_chat',
    'openai_stream',
    'save_memory',
    'warm_ai',
]
