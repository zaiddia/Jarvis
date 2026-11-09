"""Pruebas de la 12.5: qué IA responde (nube o local) y qué falta para funcionar sin internet."""


def test_que_ia_responde(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "ai_provider", "gemini")
    monkeypatch.setitem(jv.settings, "gemini_api_key", "AIza-prueba")
    monkeypatch.setitem(jv.settings, "gemini_model", "gemini-x")
    monkeypatch.setitem(jv.net, "offline", False)
    monkeypatch.setitem(jv.net, "local_model", "")
    monkeypatch.setitem(jv.state, "ai", "ok")
    a = jv.ai_now()
    assert a["donde"] == "nube" and a["proveedor"] and a["modelo"] == "gemini-x" and a["ok"]
    # sin internet y con Ollama de respaldo: responde la de tu equipo
    monkeypatch.setitem(jv.net, "offline", True)
    monkeypatch.setitem(jv.net, "local_model", "llama3.2:latest")
    monkeypatch.setitem(jv.settings, "offline_auto", True)
    a = jv.ai_now()
    assert a["donde"] == "local" and a["modelo"] == "llama3.2" and a["sin_internet"]      # 12.19: sin «:latest»
    # sin internet y sin respaldo
    monkeypatch.setitem(jv.net, "local_model", "")
    assert jv.ai_now()["donde"] == "ninguna"
    monkeypatch.setitem(jv.net, "offline", False)
    jv._rec.clear()
    monkeypatch.setattr(jv, "offline_detail", lambda: {"local_model": "", "ia": "Ollama no está instalado en este equipo."})
    jv.process_command("¿qué IA estás usando?")
    s = jv._rec.said()
    assert "IA en la nube" in s and "no tengo IA de respaldo" in s


def test_que_falta_sin_internet(jv, monkeypatch):
    monkeypatch.setattr(jv, "ollama", object())
    monkeypatch.setattr(jv, "PIPER_INSTALLED", False)
    monkeypatch.setattr(jv, "find_piper_voice", lambda: None)
    monkeypatch.setattr(jv, "_ollama_exe", lambda: "")

    def down(cfg):
        raise ConnectionError("no responde")
    monkeypatch.setattr(jv, "ai_list_models", down)
    d = jv.offline_detail()
    assert d["ia_paso"] == "instalar" and d["voz_paso"] == "voz" and "no está instalado" in d["ia"]
    monkeypatch.setattr(jv, "_ollama_exe", lambda: r"C:\\Ollama\\ollama.exe")
    assert jv.offline_detail()["ia_paso"] == "abrir"                     # instalado pero cerrado
    monkeypatch.setattr(jv, "ai_list_models", lambda cfg: [])
    assert jv.offline_detail()["ia_paso"] == "modelo"                    # abierto sin modelo
    monkeypatch.setattr(jv, "ai_list_models", lambda cfg: ["qwen3:4b"])
    monkeypatch.setitem(jv.net, "local_at", 0)
    d = jv.offline_detail()
    assert d["ia_paso"] == "" and d["local_model"] == "qwen3:4b" and "lista" in d["ia"]
    monkeypatch.setattr(jv, "PIPER_INSTALLED", True)
    monkeypatch.setattr(jv, "find_piper_voice", lambda: "voz.onnx")
    assert jv.offline_detail()["piper"] is True
    jv.net.update(local_model="", local_at=0)


def test_botones_piden_permiso(jv, monkeypatch):
    asked, sent = [], []
    monkeypatch.setattr(jv, "request_approval", lambda tipo, titulo, detalle="", on_ok=None, on_no=None, **k: asked.append((tipo, titulo)))
    monkeypatch.setattr(jv, "submit_command", lambda t, s="texto": sent.append(t))
    jv.piper_job["busy"] = False
    assert jv.handle_offline_setup({"what": "voz"})["ok"] and asked[-1][0] == "instalar" and "Piper" in asked[-1][1]
    jv.handle_offline_setup({"what": "instalar"})
    jv.handle_offline_setup({"what": "modelo"})
    assert sent == ["instala ollama", "prepara la IA sin internet"]
