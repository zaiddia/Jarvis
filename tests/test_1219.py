"""12.19: escoger entre las IA descargadas y Ollama sin abrirlo."""
import json
import os


def _ollama_disk(tmp_path, models):
    for name, tag, size in models:
        d = tmp_path / "manifests" / "registry.ollama.ai" / "library" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / tag).write_text(json.dumps({"layers": [{"size": size}]}), encoding="utf-8")
    return str(tmp_path)


def _motor_disk(jv, files):
    md = os.path.join(jv.CONFIG_DIR, "motor", "modelos")
    os.makedirs(md, exist_ok=True)
    for f in os.listdir(md):
        os.remove(os.path.join(md, f))
    for f in files:
        open(os.path.join(md, f), "wb").write(b"0" * 10)
    return md


def test_lee_ollama_del_disco_sin_abrirlo(jv, tmp_path):
    root = _ollama_disk(tmp_path, [("llama3.2", "latest", 2_000_000_000), ("qwen3", "4b", 2_600_000_000), ("nomic-embed-text", "latest", 1)])
    got = dict(jv.ollama_on_disk(root))
    assert got == {"llama3.2:latest": 2_000_000_000, "qwen3:4b": 2_600_000_000}      # sin los de «embed»


def test_lista_y_escoger(jv, tmp_path, monkeypatch):
    root = _ollama_disk(tmp_path, [("llama3.2", "latest", 2_000_000_000), ("qwen3", "4b", 2_600_000_000)])
    monkeypatch.setenv("OLLAMA_MODELS", root)
    _motor_disk(jv, ["Qwen3-4B-Q4_K_M.gguf"])
    monkeypatch.setattr(jv, "_exe_for", lambda b: "/x/llama-server" if b == "cpu" else "")
    import nucleo
    monkeypatch.setattr(nucleo.J, "_exe_for", jv._exe_for, raising=False)
    for k, v in {"gemini_api_key": "k", "gemini_model": "gemini-x", "ai_provider": "gemini", "offline_model": "", "motor_model": "", "ollama_model": "llama3.2"}.items():
        monkeypatch.setitem(jv.settings, k, v)
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setattr(jv, "check_ai", lambda *a, **k: None)
    monkeypatch.setattr(jv, "_warm", lambda it: None)
    c = jv.ai_choices()
    ids = [i["id"] for i in c["items"]]
    assert "nube:gemini" in ids and "motor:Qwen3-4B-Q4_K_M.gguf" in ids and "ollama:llama3.2:latest" in ids and "ollama:qwen3:4b" in ids
    assert c["actual"] == "nube:gemini" and c["respaldo"] == "motor:Qwen3-4B-Q4_K_M.gguf"      # automático: la integrada primero
    r = jv.ai_pick("ollama:qwen3:4b", backup_only=True)                  # solo para cuando no hay internet
    assert r["ok"] and jv.settings["ai_provider"] == "gemini" and jv.settings["offline_model"] == "ollama:qwen3:4b"
    assert jv.ai_backup_id() == "ollama:qwen3:4b"
    r = jv.ai_pick("ollama:llama3.2:latest")                              # usarla ya
    assert r["ok"] and jv.settings["ai_provider"] == "ollama" and jv.settings["ollama_model"] == "llama3.2:latest"
    assert jv.ai_current_id() == "ollama:llama3.2:latest"
    r = jv.ai_pick("motor:Qwen3-4B-Q4_K_M.gguf")
    assert r["ok"] and jv.settings["ai_provider"] == "motor" and jv.settings["motor_model"] == "Qwen3-4B-Q4_K_M.gguf"
    assert jv.ai_pick("nube:gemini")["ok"] and jv.settings["ai_provider"] == "gemini"
    assert not jv.ai_pick("ollama:no-existe")["ok"]
    assert not jv.ai_pick("nube:gemini", backup_only=True)["ok"]


def test_sin_internet_usa_la_que_escogiste_aunque_haya_integrada(jv, tmp_path, monkeypatch):
    root = _ollama_disk(tmp_path, [("qwen3", "4b", 1)])
    monkeypatch.setenv("OLLAMA_MODELS", root)
    _motor_disk(jv, ["Otro.gguf"])
    monkeypatch.setattr(jv, "motor_ready", lambda: True)
    monkeypatch.setattr(jv, "motor_name", lambda: "Otro")
    monkeypatch.setattr(jv, "ollama", object())
    monkeypatch.setattr(jv, "ai_list_models", lambda cfg: ["qwen3:4b", "llama3.2:latest"])
    monkeypatch.setitem(jv.settings, "offline_model", "ollama:qwen3:4b")
    assert jv.local_pick() == "qwen3:4b"                                   # antes ganaba siempre la integrada
    monkeypatch.setitem(jv.settings, "offline_model", "motor:Otro.gguf")
    assert jv.local_pick() == "motor:Otro"
    monkeypatch.setitem(jv.settings, "offline_model", "qwen3:4b")         # como lo guardaban las versiones viejas
    assert jv.local_pick() == "qwen3:4b"
    assert jv.local_label("motor:Otro") == "Otro" and jv.local_label("llama3.2:latest") == "llama3.2"


def test_ollama_se_enciende_solo(jv, monkeypatch):
    calls = []
    pings = iter([False, False, True])
    monkeypatch.setattr(jv, "_ollama_ping", lambda host, timeout=0.8: next(pings, True))
    monkeypatch.setattr(jv, "_ollama_exe", lambda: "/opt/ollama/ollama")

    class P:
        def poll(self):
            return None
    import nucleo.ialocal as il
    monkeypatch.setattr(il.subprocess, "Popen", lambda args, **k: calls.append((args, k)) or P())
    monkeypatch.setattr(il.time, "sleep", lambda s: None)
    monkeypatch.setitem(jv._il, "alive_at", 0.0)
    monkeypatch.setitem(jv._il, "tried", 0.0)
    assert jv.ollama_ensure("http://127.0.0.1:11434")
    assert calls and calls[0][0] == ["/opt/ollama/ollama", "serve"]        # escondido, sin abrir la app
    calls.clear()
    monkeypatch.setitem(jv._il, "alive_at", 0.0)
    monkeypatch.setattr(jv, "_ollama_ping", lambda host, timeout=0.8: False)
    assert not jv.ollama_ensure("http://192.168.1.20:11434") and not calls  # otro equipo: no se toca


def test_por_voz(jv, ask, monkeypatch):
    picked = []
    monkeypatch.setattr(jv, "ai_choices", lambda: {"items": [
        {"id": "nube:gemini", "tipo": "nube", "nombre": "Gemini", "detalle": "x", "gb": 0},
        {"id": "ollama:qwen3:4b", "tipo": "ollama", "nombre": "qwen3:4b", "detalle": "Ollama", "gb": 2}], "actual": "nube:gemini", "respaldo": ""})
    monkeypatch.setattr(jv, "ai_pick", lambda cid, backup_only=False: picked.append(cid) or {"ok": True, "msg": "Listo."})
    jv.process_command("cambia a la IA qwen")
    assert picked == ["ollama:qwen3:4b"]
    jv.process_command("usa la IA local")
    assert picked[-1] == "ollama:qwen3:4b"
    jv.process_command("cambia a la ia gemini")
    assert picked[-1] == "nube:gemini"
    n = len(picked)
    jv._rec.clear()
    jv.process_command("¿qué IA tengo descargadas?")
    assert "qwen3:4b" in jv._rec.said() and len(picked) == n


def test_hud_boton_y_ajustes():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html = open(os.path.join(root, "templates", "hud.html"), encoding="utf-8").read()
    assert 'id="btn-ai"' in html and 'id="aipick"' in html and 'id="dock-ai"' in html
    js = open(os.path.join(root, "static", "js", "hud.js"), encoding="utf-8").read()
    assert 'socket.emit("ai_pick"' in js and 'socket.emit("ai_choices"' in js
    st = open(os.path.join(root, "templates", "settings.html"), encoding="utf-8").read()
    assert '<select class="inp" id="f-offline-model" data-key="offline_model"' in st


def test_comprobar_ia_local(jv, tmp_path, monkeypatch):
    root = _ollama_disk(tmp_path, [("qwen3", "4b", 2_600_000_000)])
    monkeypatch.setenv("OLLAMA_MODELS", root)
    _motor_disk(jv, [])
    monkeypatch.setitem(jv.settings, "ai_provider", "gemini")
    monkeypatch.setitem(jv.settings, "offline_model", "ollama:qwen3:4b")

    class Cli:
        def __init__(self, host=None, timeout=None):
            pass

        def chat(self, **k):
            return {"message": {"content": "Listo."}}

    class Lib:
        Client = Cli
    monkeypatch.setattr(jv, "ollama", Lib())
    monkeypatch.setattr(jv, "_ollama_exe", lambda: "/opt/ollama")
    monkeypatch.setattr(jv, "_ollama_ping", lambda host, timeout=0.8: False)
    monkeypatch.setattr(jv, "ollama_ensure", lambda *a, **k: True)
    monkeypatch.setattr(jv, "ai_list_models", lambda cfg: ["qwen3:4b"])
    r = jv.local_check()
    assert r["ok"] and r["id"] == "ollama:qwen3:4b" and "respondió" in r["msg"]
    assert any("Encendí Ollama" in p["texto"] for p in r["pasos"]) and all(p["ok"] for p in r["pasos"])
    monkeypatch.setattr(jv, "ai_list_models", lambda cfg: [])                       # Ollama sin ese modelo
    r = jv.local_check()
    assert not r["ok"] and "no tiene el modelo" in r["pasos"][-1]["texto"]
    monkeypatch.setattr(jv, "ollama_ensure", lambda *a, **k: False)                 # no arranca
    r = jv.local_check()
    assert not r["ok"] and r["msg"] == "Ollama no responde."
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "vacio"))
    monkeypatch.setitem(jv.settings, "offline_model", "")
    r = jv.local_check()
    assert not r["ok"] and "No hay ninguna IA" in r["pasos"][0]["texto"]


def test_comprobar_por_voz(jv, monkeypatch):
    ran = []
    monkeypatch.setattr(jv, "_il_check_run", lambda cid, say: ran.append(say))
    import threading

    class T:
        def __init__(self, target=None, args=(), **k):
            self.f, self.a = target, args

        def start(self):
            self.f(*self.a)
    monkeypatch.setattr(threading, "Thread", T)
    for frase in ["comprueba la IA local", "¿la IA local está conectada?", "revisa la inteligencia artificial sin internet"]:
        jv._il_check["busy"] = False
        jv.process_command(frase)
    assert ran == [True, True, True]
    jv._il_check["busy"] = False
