"""Pruebas de la 12.7: vuelve el estilo clásico, la IA local más rápida (tarjeta gráfica, reusar lo ya leído, menos texto)."""
import motorlocal


def test_estilo_clasico_por_defecto(jv, monkeypatch):
    assert jv.DEFAULT_SETTINGS["look"] == "clasico"
    monkeypatch.setitem(jv.settings, "look", "aurora")
    monkeypatch.setitem(jv.settings, "look_chosen", False)
    applied = {}
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    # la 12.6 lo puso sin preguntar: al cargar vuelve el clásico
    import json
    import os
    cfg = json.load(open(jv.CONFIG_PATH, encoding="utf-8")) if os.path.exists(jv.CONFIG_PATH) else {}
    monkeypatch.setattr(jv, "_read_env", lambda: {})
    real_open = open

    def fake_open(path, *a, **k):
        if path == jv.CONFIG_PATH and "r" in (a[0] if a else k.get("mode", "r")):
            import io
            return io.StringIO(json.dumps({**cfg, "look": "aurora"}))
        return real_open(path, *a, **k)
    monkeypatch.setattr("builtins.open", fake_open)
    jv.load_settings()
    monkeypatch.setattr("builtins.open", real_open)
    assert jv.settings["look"] == "clasico"
    # si lo escoges tú en Ajustes, se respeta
    jv.apply_settings({"look": "aurora"})
    assert jv.settings["look"] == "aurora" and jv.settings["look_chosen"] is True
    applied.clear()


def test_motor_mas_rapido():
    a = motorlocal.server_args("srv", "m.gguf", threads=4, threads_batch=8, gpu=True)
    for flag in ("-np", "--cache-reuse", "-fa", "-ngl", "-tb"):
        assert flag in a, flag
    assert a[a.index("-ngl") + 1] == "99" and motorlocal.server_args("srv", "m.gguf")[motorlocal.server_args("srv", "m.gguf").index("-ngl") + 1] == "0"
    rel = [{"tag_name": "b1", "assets": [{"name": "llama-b1-bin-win-cpu-x64.zip", "browser_download_url": "https://x/c.zip"},
                                         {"name": "llama-b1-bin-win-vulkan-x64.zip", "browser_download_url": "https://x/v.zip"}]}]
    assert motorlocal.pick_release(rel, True, gpu=True)[0] == "https://x/v.zip" and motorlocal.pick_release(rel, True)[0] == "https://x/c.zip"
    assert motorlocal.tokens_per_second({"timings": {"predicted_per_second": 14.5}}) == 14.5 and motorlocal.tokens_per_second({}) == 0
    assert len(motorlocal.trim_context("palabra " * 1000, 300)) <= 302


def test_escoge_la_mas_rapida(jv, monkeypatch):
    import nucleo.motor as mt
    monkeypatch.setattr(mt, "_exe_for", lambda be: "/x/" + be)
    started = []

    def start(wait=120):
        started.append(jv.settings["motor_backend"])
        return True
    monkeypatch.setattr(jv, "motor_start", start)
    monkeypatch.setattr(jv, "motor_stop", lambda: None)
    monkeypatch.setattr(mt, "motor_stop", lambda: None)
    monkeypatch.setattr(jv, "motor_bench", lambda: {"gpu": 31.0, "cpu": 9.0}[jv.settings["motor_backend"]])
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.settings, "motor_backend", "auto")
    assert jv.motor_pick_backend() == 31.0 and jv.settings["motor_backend"] == "gpu" and started == ["gpu", "cpu"]


def test_ia_local_lee_menos(jv, monkeypatch):
    from nucleo.ia import ask_ai
    sent = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: sent.append(msgs) or "ok")
    monkeypatch.setattr(jv, "_user_ctx", lambda p: " CONTEXTO " * 900)
    monkeypatch.setattr(jv, "chat_history", [{"role": "user", "content": str(i)} for i in range(20)])
    monkeypatch.setitem(jv.settings, "history_turns", 10)
    monkeypatch.setattr(jv, "save_memory", lambda: None)
    monkeypatch.setattr(jv, "_is_local_ai", lambda cfg=None: True)
    ask_ai("hola")
    sys_local, n_local = sent[-1][0]["content"], len(sent[-1])
    assert sys_local.startswith(jv.system_static()) and len(sys_local) < len(jv.system_static()) + 1600 and n_local == 1 + 6 + 1
    monkeypatch.setattr(jv, "_is_local_ai", lambda cfg=None: False)
    monkeypatch.setattr(jv, "chat_history", [{"role": "user", "content": str(i)} for i in range(20)])
    ask_ai("hola")
    assert sent[-1][0]["content"].startswith(jv.system_static()) and len(sent[-1][0]["content"]) > 5000 and len(sent[-1]) == 1 + 20 + 1
