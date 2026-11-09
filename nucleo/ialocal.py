"""12.19: escoger la IA y Ollama sin abrirlo.

- Todas las IA que tienes, en una lista: las de la nube con clave puesta, la IA integrada (cada modelo .gguf
  descargado) y cada modelo de Ollama descargado (se leen del disco: no hace falta que Ollama esté abierto).
- Escoges una desde el botón de IA del HUD, desde Ajustes o por voz («cambia a la IA qwen», «usa Gemini»). La que
  escojas de tu equipo queda también como la que se usa cuando se cae el internet.
- Ollama ya no hay que abrirlo: si está instalado y hace falta, Jarvis lo enciende escondido (sin ventana).

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import json
import os
import re
import subprocess
import threading
import time
import urllib.request

from nucleo import J

_il = {"lock": threading.Lock(), "tried": 0.0, "proc": None, "alive_at": 0.0}


# ============================================================================ OLLAMA SIN ABRIRLO
def _ollama_ping(host, timeout=0.8):
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/api/version", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def ollama_ensure(host=None, wait=25):
    """Si Ollama está instalado pero cerrado, lo enciende escondido (``ollama serve``, sin ventana) y espera a que
    responda. → True si responde. No hace nada si la dirección no es de este equipo."""
    host = (host or J.settings.get("ollama_host") or J.DEFAULT_SETTINGS["ollama_host"]).rstrip("/")
    if time.time() - _il["alive_at"] < 20:
        return True
    if J._ollama_ping(host):
        _il["alive_at"] = time.time()
        return True
    if not re.match(r"^https?://(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?$", host):
        return False                                   # otro equipo: no se puede encender desde aquí
    with _il["lock"]:
        if J._ollama_ping(host):
            _il["alive_at"] = time.time()
            return True
        if time.time() - _il["tried"] < 60:            # ya se intentó hace poco y no sirvió
            return False
        _il["tried"] = time.time()
        exe = J._ollama_exe()
        if not exe:
            return False
        env = dict(os.environ)
        m = re.search(r":(\d+)$", host)
        if m and m.group(1) != "11434":
            env["OLLAMA_HOST"] = "127.0.0.1:" + m.group(1)
        try:
            _il["proc"] = subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           stdin=subprocess.DEVNULL, env=env,
                                           creationflags=0x08000000 if J.IS_WIN else 0)   # sin ventana
        except OSError as e:
            J.log_terminal(f"No pude encender Ollama: {e}", "IA LOCAL")
            return False
        J.log_terminal("Encendí Ollama en segundo plano (no hace falta abrirlo).", "IA LOCAL")
        t0 = time.time()
        while time.time() - t0 < wait:
            if J._ollama_ping(host):
                _il["alive_at"] = time.time()
                _il["tried"] = 0.0
                return True
            if _il["proc"].poll() is not None:
                break
            time.sleep(0.5)
        J.log_terminal("Ollama no arrancó.", "IA LOCAL")
        return False


# ============================================================================ LAS IA QUE HAY
def _ollama_dir():
    d = os.environ.get("OLLAMA_MODELS", "").strip()
    return d or os.path.join(os.path.expanduser("~"), ".ollama", "models")


def ollama_on_disk(root=None):
    """Modelos de Ollama descargados, leídos del disco (sin abrir Ollama). → [(nombre, bytes)]."""
    base = os.path.join(root or J._ollama_dir(), "manifests")
    out = []
    if not os.path.isdir(base):
        return out
    for dirpath, _dirs, files in os.walk(base):
        for tag in files:
            path = os.path.join(dirpath, tag)
            rel = os.path.relpath(path, base).replace("\\", "/").split("/")
            if len(rel) < 3:
                continue
            host, parts = rel[0], rel[1:]
            ns, model = (parts[0], parts[1]) if len(parts) >= 3 else ("library", parts[0])
            name = (model if ns == "library" else f"{ns}/{model}") + ":" + parts[-1]
            if host != "registry.ollama.ai":
                name = f"{host}/{ns}/{model}:{parts[-1]}"
            size = 0
            try:
                with open(path, encoding="utf-8") as f:
                    man = json.load(f)
                size = sum(int(x.get("size") or 0) for x in man.get("layers", []))
            except Exception:
                pass
            if "embed" not in name.lower():
                out.append((name, size))
    return sorted(out)


def _motor_files():
    mdir = os.path.join(J.CONFIG_DIR, "motor", "modelos")
    if not os.path.isdir(mdir):
        return []
    return sorted((f, os.path.getsize(os.path.join(mdir, f))) for f in os.listdir(mdir) if f.lower().endswith(".gguf"))


def _gb(n):
    return round(n / 1e9, 1) if n else 0


def _pretty(name):
    n = re.sub(r"\.gguf$", "", name, flags=re.I)
    n = re.sub(r":latest$", "", n)
    return n


def ai_choices():
    """Todo lo que se puede escoger. → {"items": [...], "actual": id, "respaldo": id}.
    Cada item: {"id", "tipo": "nube"|"integrada"|"ollama", "nombre", "detalle", "gb"}."""
    items = []
    for pid, sp in J.PROVIDERS.items():
        if sp.get("group") != "cloud":
            continue
        if not str(J.settings.get(f"{pid}_api_key", "") or "").strip():
            continue
        model = str(J.settings.get(f"{pid}_model", "") or "")
        items.append({"id": f"nube:{pid}", "tipo": "nube", "nombre": sp["short"], "detalle": model or "en la nube", "gb": 0})
    engine_ok = bool(J._exe_for("gpu") or J._exe_for("cpu"))
    for f, size in J._motor_files():
        items.append({"id": f"motor:{f}", "tipo": "integrada", "nombre": _pretty(f), "gb": _gb(size),
                      "detalle": "IA integrada · sin Ollama" if engine_ok else "falta el motor (Ajustes › IA)"})
    seen = set()
    for name, size in J.ollama_on_disk():
        seen.add(name)
        items.append({"id": f"ollama:{name}", "tipo": "ollama", "nombre": _pretty(name), "detalle": "Ollama", "gb": _gb(size)})
    if J.ollama is not None and time.time() - _il["alive_at"] < 60:      # Ollama abierto: lo que diga (p. ej. otra carpeta)
        try:
            for name in J.ai_list_models(J._ai_cfg({"ai_provider": "ollama"})):
                full = name if ":" in name else name + ":latest"
                if full not in seen and "embed" not in name.lower():
                    items.append({"id": f"ollama:{full}", "tipo": "ollama", "nombre": _pretty(name), "detalle": "Ollama", "gb": 0})
        except Exception:
            pass
    return {"items": items, "actual": J.ai_current_id(), "respaldo": J.ai_backup_id(items)}


def ai_current_id():
    pid = J.settings.get("ai_provider", "")
    if pid == "motor":
        _exe, model = J.motor_paths()
        return "motor:" + os.path.basename(model) if model else "motor:"
    if pid == "ollama":
        m = J.settings.get("ollama_model", "").strip()
        return "ollama:" + (m if ":" in m else m + ":latest")
    return f"nube:{pid}"


def ai_backup_id(items=None):
    """La IA de tu equipo que se usa si se cae el internet."""
    want = J.settings.get("offline_model", "").strip()
    if want:
        if want.startswith(("motor:", "ollama:")):
            return want
        return "ollama:" + (want if ":" in want else want + ":latest")      # versiones viejas: solo el nombre de Ollama
    items = items if items is not None else J.ai_choices()["items"]
    loc = [i for i in items if i["tipo"] in ("integrada", "ollama")]
    return loc[0]["id"] if loc else ""


def _same_ollama(a, b):
    def norm(x):
        return x if ":" in x else x + ":latest"
    return norm(a) == norm(b)


def local_pick():
    """La IA de tu equipo para cuando no hay internet, según lo que escogiste. → "motor:<nombre>", el modelo de
    Ollama o "" (lo usa local_ai_model)."""
    want = J.settings.get("offline_model", "").strip()
    files = [f for f, _s in J._motor_files()]
    if want.startswith("motor:"):
        f = want[6:]
        if f in files and J.motor_ready():
            if J.settings.get("motor_model") != f:
                J.settings["motor_model"] = f
            return "motor:" + J.motor_name()
    elif want:
        name = want[7:] if want.startswith("ollama:") else want
        hit = next((n for n in J._il_ollama_names() if J._same_ollama(name, n) or n.startswith(name + ":")), "")
        if hit:
            return hit
    # automático (o lo escogido ya no está): la integrada primero; si no, Ollama
    if J.motor_ready():
        return "motor:" + J.motor_name()
    names = J._il_ollama_names()
    pref = J.settings.get("ollama_model", "").strip()
    return next((n for n in names if pref and (n == pref or n.startswith(pref + ":"))), names[0] if names else "")


def _il_ollama_names():
    """Modelos de Ollama que responden (lo enciende solo si hace falta, dentro de ai_list_models)."""
    if J.ollama is None:
        return []
    try:
        return [n for n in J.ai_list_models(J._ai_cfg({"ai_provider": "ollama"})) if "embed" not in n.lower()]
    except Exception:
        return []


def local_label(model):
    """Nombre para decir en voz alta: «motor:qwen…» → «qwen…», «llama3.2:latest» → «llama3.2»."""
    return _pretty(model[6:] if model.startswith("motor:") else model)


# ============================================================================ ESCOGER
def ai_pick(cid, backup_only=False):
    """Cambia la IA. cid = "nube:<proveedor>" | "motor:<archivo.gguf>" | "ollama:<modelo>".
    backup_only: solo la deja para cuando no haya internet. → {"ok", "msg"}."""
    cid = str(cid or "").strip()
    ch = {i["id"]: i for i in J.ai_choices()["items"]}
    it = ch.get(cid)
    if it is None:
        return {"ok": False, "msg": "Esa IA ya no está en este equipo."}
    if it["tipo"] == "integrada" and it["detalle"].startswith("falta"):
        return {"ok": False, "msg": "A la IA integrada le falta el motor: en Ajustes › Inteligencia artificial pulsa «Instalar la IA integrada».",
                **J.ai_choices()}
    data = {}
    if it["tipo"] == "nube":
        if backup_only:
            return {"ok": False, "msg": "Para cuando no hay internet solo sirve una IA de tu equipo."}
        data["ai_provider"] = cid[5:]
        msg = f"Listo: ahora respondo con {it['nombre']} ({it['detalle']})."
    else:
        data["offline_model"] = cid
        if it["tipo"] == "integrada":
            if J.settings.get("motor_model") != cid[6:]:
                data["motor_model"] = cid[6:]
                if J._mt_alive():
                    J.motor_stop()                     # se vuelve a encender con el modelo nuevo al preguntarle
        if not backup_only:
            if it["tipo"] == "integrada":
                data["ai_provider"] = "motor"
            else:
                data["ai_provider"] = "ollama"
                data["ollama_model"] = cid[7:]
        msg = (f"Listo: si se cae el internet, uso {it['nombre']}." if backup_only else
               f"Listo: ahora respondo con {it['nombre']}, de tu equipo (sin internet). También es la que uso si se cae el internet.")
    errs = J.apply_settings(data) or []
    J.net["local_at"] = 0.0                            # vuelve a calcular la de respaldo
    if not backup_only and it["tipo"] != "nube":
        threading.Thread(target=J._warm, args=(it,), daemon=True, name="ia-escogida").start()
    try:
        J.socketio.emit("ai_now", J.ai_now())
    except Exception:
        pass
    J.log_terminal(msg, "IA")
    return {"ok": not errs, "msg": msg if not errs else "; ".join(map(str, errs)), **J.ai_choices()}


def _warm(it):
    """La deja cargada para que la primera respuesta no espere."""
    try:
        if it["tipo"] == "integrada":
            J.motor_start()
        elif J.ollama_ensure() and J.ollama is not None:
            J.ollama.Client(host=J._ai_cfg({"ai_provider": "ollama"})["ollama_host"], timeout=180).chat(
                model=it["id"][7:], messages=[{"role": "user", "content": "hola"}], options={"num_predict": 1}, keep_alive="30m")
    except Exception as e:
        J.log_terminal(f"No pude dejar lista {it['nombre']}: {e}", "IA LOCAL")


@J.socketio.on("ai_choices")
def handle_ai_choices(data=None):
    return {**J.ai_choices(), "ahora": J.ai_now()}


@J.socketio.on("ai_pick")
def handle_ai_pick(data=None):
    d = data or {}
    return J.ai_pick(d.get("id"), bool(d.get("respaldo")))


# ============================================================================ COMPROBAR LA IA LOCAL
_il_check = {"busy": False, "last": None}


def local_check(cid=None):
    """12.19.1: comprueba de verdad la IA de tu equipo: que esté todo y que responda a una pregunta corta.
    cid: la que se quiere probar (vacío = la que responde ahora si es local; si no, la de «sin internet»).
    → {"ok", "id", "nombre", "pasos": [{"ok", "texto"}], "msg", "segundos"}."""
    items = {i["id"]: i for i in J.ai_choices()["items"]}
    cur = J.ai_current_id()
    cid = str(cid or "").strip() or (cur if cur in items and not cur.startswith("nube:") else J.ai_backup_id())
    pasos = []

    def paso(ok, texto):
        pasos.append({"ok": bool(ok), "texto": texto})
        return ok

    def done(ok, msg, secs=0.0):
        r = {"ok": ok, "id": cid, "nombre": items.get(cid, {}).get("nombre", J.local_label(cid.split(":", 1)[-1]) if cid else ""),
             "pasos": pasos, "msg": msg, "segundos": round(secs, 1), "hora": time.strftime("%H:%M")}
        _il_check["last"] = r
        return r

    if not cid or cid not in items:
        paso(False, "No hay ninguna IA descargada en tu equipo.")
        return done(False, "No tengo IA local para comprobar: di «instala la IA integrada» o descarga un modelo de Ollama.")
    it = items[cid]
    ask = [{"role": "system", "content": "Responde en español con una sola palabra."},
           {"role": "user", "content": "Di «listo»."}]
    if it["tipo"] == "integrada":
        f = cid[6:]
        if not paso(J._exe_for("gpu") or J._exe_for("cpu"), "Motor de la IA integrada instalado." if (J._exe_for("gpu") or J._exe_for("cpu"))
                    else "Falta el motor de la IA integrada (Ajustes › Inteligencia artificial › Instalar)."):
            return done(False, "A la IA integrada le falta el motor.")
        paso(True, f"Modelo descargado: {it['nombre']}" + (f" ({it['gb']} GB)." if it["gb"] else "."))
        if J.settings.get("motor_model") != f:
            J.settings["motor_model"] = f
            if J._mt_alive():
                J.motor_stop()
        t0 = time.time()
        if not paso(J.motor_start(), "La IA integrada encendió."):
            pasos[-1]["texto"] = "La IA integrada no encendió (puede faltar memoria: cierra programas pesados)."
            return done(False, f"{it['nombre']} no pudo encender.")
        try:
            ans = J.motor_ask(ask, max_tokens=8)
        except Exception as e:
            paso(False, f"No respondió: {e}")
            return done(False, f"{it['nombre']} encendió pero no respondió.")
    else:
        name = cid[7:]
        if not paso(J.ollama is not None, "Componente de Ollama en Jarvis." if J.ollama is not None else
                    "Falta el componente de Ollama en Jarvis (Ajustes › Inteligencia artificial › Si se cae el internet)."):
            return done(False, "Falta el componente de Ollama en Jarvis.")
        host = J._ai_cfg({"ai_provider": "ollama"})["ollama_host"]
        local = bool(re.match(r"^https?://(?:127\.0\.0\.1|localhost|\[::1\])", host))
        exe = J._ollama_exe()
        if local and not exe and not J._ollama_ping(host):
            paso(False, "Ollama no está instalado en este equipo.")
            return done(False, "Ollama no está instalado: di «instala Ollama».")
        was_on = J._ollama_ping(host)
        if not paso(was_on or J.ollama_ensure(host), "Ollama está encendido." if was_on else "Encendí Ollama en segundo plano (no hizo falta abrirlo)."):
            pasos[-1]["texto"] = f"Ollama no responde en {host}" + (" y no pude encenderlo." if local else " (es otro equipo: enciéndelo allá).")
            return done(False, "Ollama no responde.")
        names = J._il_ollama_names()
        hit = next((n for n in names if J._same_ollama(name, n)), "")
        if not paso(hit, f"Modelo descargado en Ollama: {it['nombre']}." if hit else f"Ollama no tiene el modelo {it['nombre']}."):
            return done(False, f"Ollama no encuentra {it['nombre']}: vuelve a descargarlo con internet.")
        t0 = time.time()
        try:
            r = J.ollama.Client(host=host, timeout=240).chat(model=hit, messages=ask, options={"num_predict": 8, "temperature": 0}, keep_alive="30m")
            ans = (r["message"]["content"] or "").strip()
        except Exception as e:
            paso(False, f"No respondió: {e}")
            return done(False, f"{it['nombre']} no respondió (¿poca memoria?).")
    secs = time.time() - t0
    ans = re.sub(r"<think>.*?</think>", "", str(ans), flags=re.S).strip()
    if not paso(ans, f"Respondió en {secs:.1f} s: «{ans[:40]}»." if ans else "Respondió vacío."):
        return done(False, f"{it['nombre']} respondió vacío.", secs)
    lento = " Va lenta: la primera respuesta carga el modelo; las siguientes son más rápidas." if secs > 20 else ""
    return done(True, f"La IA local funciona: {it['nombre']} respondió en {secs:.1f} segundos.{lento}", secs)


def _il_check_run(cid, say):
    try:
        r = J.local_check(cid)
    except Exception as e:
        r = {"ok": False, "id": cid or "", "nombre": "", "pasos": [{"ok": False, "texto": str(e)}], "msg": f"No pude comprobarla: {e}", "segundos": 0}
    finally:
        _il_check["busy"] = False
    J.log_terminal(r["msg"], "IA LOCAL")
    J.socketio.emit("ai_check", r)
    if say:
        J.reply(r["msg"] if r["ok"] else r["msg"] + " " + " ".join(p["texto"] for p in r["pasos"] if not p["ok"])[:200], "IA LOCAL")


@J.socketio.on("ai_check")
def handle_ai_check(data=None):
    d = data or {}
    if _il_check["busy"]:
        return {"ok": True, "busy": True, "msg": "Ya la estoy comprobando…"}
    _il_check["busy"] = True
    threading.Thread(target=J._il_check_run, args=(str(d.get("id") or ""), False), daemon=True, name="ia-comprobar").start()
    return {"ok": True, "busy": True, "msg": "Comprobando la IA local… (la primera vez puede tardar mientras carga el modelo)"}


_IL_CHECK = re.compile(r"\b(?:comprueba|prueba|revisa|verifica|chequea)\s+(?:si\s+)?(?:la\s+)?(?:ia|inteligencia artificial|cerebro)\s+(?:local|sin internet|de mi (?:equipo|pc|computador))\b|"
                       r"\b(?:la\s+)?(?:ia|inteligencia artificial)\s+(?:local|sin internet)\s+(?:esta\s+)?(?:conectada|funciona|funcionando|responde)\b")


# ============================================================================ POR VOZ
_IL_PICK = re.compile(r"\b(?:cambia(?:te)?|pasa(?:te)?|usa|utiliza|pon|activa)\s+(?:a\s+|la\s+)?(?:ia|inteligencia artificial|modelo|cerebro)?\s*"
                      r"(?:a\s+|de\s+)?(?:la\s+)?(.+?)\s*$")
_IL_LIST = re.compile(r"\b(?:que|cuales)\s+(?:ia|ias|inteligencias artificiales|modelos)\s+(?:tengo|hay|tienes)(?:\s+(?:descargad[oa]s|instalad[oa]s|en mi (?:equipo|pc|computador)))?\b|"
                      r"\b(?:lista|muestrame|ensename)\s+(?:las\s+|los\s+)?(?:ia|ias|modelos)\b")


def ai_pick_voice(text, t):
    if _IL_CHECK.search(t):
        if _il_check["busy"]:
            J.reply("Ya la estoy comprobando.", "IA LOCAL")
            return True
        _il_check["busy"] = True
        J.reply("Voy a comprobar la IA de tu equipo; te digo en un momento.", "IA LOCAL")
        threading.Thread(target=J._il_check_run, args=("", True), daemon=True, name="ia-comprobar").start()
        return True
    if _IL_LIST.search(t):
        c = J.ai_choices()
        if not c["items"]:
            J.reply("No tengo ninguna IA lista: pon una clave de la nube o instala una IA en tu equipo (Ajustes › Inteligencia artificial).", "IA")
            return True
        names = [i["nombre"] + ("" if i["tipo"] == "nube" else " (en tu equipo)") for i in c["items"]]
        cur = next((i["nombre"] for i in c["items"] if i["id"] == c["actual"]), "")
        J.reply("Tengo " + ", ".join(names) + "." + (f" Ahora uso {cur}." if cur else "") +
                " Para cambiar di «cambia a la IA …» o toca el botón de IA del HUD.", "IA")
        return True
    if not re.search(r"\b(?:ia|inteligencia artificial|modelo|cerebro)\b", t) and not re.search(r"\b(?:usa|cambia a|pasate a)\s+(?:gemini|claude|chatgpt|gpt|deepseek|grok|mistral|groq|ollama|llama|qwen|gemma|phi)\b", t):
        return False
    m = _IL_PICK.search(t)
    if not m:
        return False
    want = J.normalize(m.group(1))
    want = re.sub(r"^(?:ia|inteligencia artificial|modelo)\s+(?:de\s+)?", "", want).strip()
    if not want or len(want) < 3 or len(want.split()) > 4 or re.search(r"\b(?:para|que|y luego|con el|con la)\b", want):
        return False                                   # «usa Gemini para resumir esto» no es cambiar de IA
    items = J.ai_choices()["items"]
    local = re.search(r"\b(?:local|de mi (?:equipo|pc|computador)|sin internet)\b", want)
    if local:
        loc = [i for i in items if i["tipo"] != "nube"]
        want2 = re.sub(r"\b(?:local|de mi (?:equipo|pc|computador)|sin internet)\b", "", want).strip()
        if not want2:
            if not loc:
                J.reply("No tienes una IA descargada en tu equipo. Di «instala la IA integrada» para bajar una.", "IA")
                return True
            J.reply(J.ai_pick(J.ai_backup_id(items) or loc[0]["id"])["msg"], "IA")
            return True
        want = want2

    def key(s):
        return re.sub(r"[^a-z0-9]", "", J.normalize(s))
    w = key(want)
    hits = [i for i in items if w and (w in key(i["nombre"]) or w in key(i["id"]) or (i["tipo"] == "nube" and key(i["nombre"]) in w))]
    if not hits:
        return False
    J.reply(J.ai_pick(hits[0]["id"])["msg"], "IA")
    return True


def ialocal_start():
    """Al abrir Jarvis: si tu IA (o la de respaldo) es de Ollama, lo deja encendido."""
    def go():
        time.sleep(4)
        uses = J.settings.get("ai_provider") == "ollama" or J.ai_backup_id().startswith("ollama:")
        if uses and J._ollama_exe() and J.ollama is not None:
            J.ollama_ensure()
    threading.Thread(target=go, daemon=True, name="ollama-encender").start()


__all__ = ['_IL_CHECK', '_IL_LIST', '_IL_PICK', '_il', '_il_check', '_il_check_run', 'handle_ai_check', 'local_check', '_il_ollama_names', '_motor_files', '_ollama_dir', '_ollama_ping', '_same_ollama', '_warm', 'ai_backup_id', 'ai_choices',
           'ai_current_id', 'ai_pick', 'ai_pick_voice', 'handle_ai_choices', 'handle_ai_pick', 'ialocal_start', 'local_label', 'local_pick',
           'ollama_ensure', 'ollama_on_disk']
