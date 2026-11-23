"""Pruebas de la 12.47: comparar los modelos gratis de NVIDIA y dejar uno para conversar o para los trabajos pesados."""


def test_candidatos_y_orden(jv):
    models = ["moonshotai/kimi-k3.1-pro", "moonshotai/kimi-k3", "qwen/qwen3-coder-480b-a35b-instruct", "qwen/qwen3-next-80b-a3b-instruct",
              "meta/llama-3.3-70b-instruct", "meta/llama-3.1-8b-instruct", "nvidia/llama-3.1-nemotron-safety-guard-8b-v3", "z-ai/glm-4.7",
              "bigcode/starcoder2"]
    c = jv.nv_candidates(models)
    assert c[:2] == ["moonshotai/kimi-k3", "moonshotai/kimi-k3.1-pro"] and c[2] == "qwen/qwen3-next-80b-a3b-instruct"   # el «coder» después
    assert "z-ai/glm-4.7" in c and "bigcode/starcoder2" not in c and len(c) <= jv.NV_MAX
    r = jv.nv_rank([{"modelo": "a", "s": 30.0, "ok": True}, {"modelo": "b", "s": 2.0, "ok": False}, {"modelo": "c", "s": 1.5, "ok": True}])
    assert [x["modelo"] for x in r] == ["c", "a", "b"]
    assert "c (1.5 s)" in jv.nv_report(r) and "1 no respondieron" in jv.nv_report(r)


def test_probar_y_usar(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "nvidia_api_key", "nvapi-prueba")
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setattr(jv, "check_ai", lambda *a, **k: True)
    monkeypatch.setattr(jv, "ai_list_models", lambda cfg: ["moonshotai/kimi-k3.1-pro", "qwen/qwen3-next-80b-a3b-instruct"])
    sent = []

    def chat(cfg, m, j=False, max_tokens=None, image_path=None):
        sent.append(cfg["model"])
        if "qwen" not in cfg["model"]:
            import time
            time.sleep(0.05)
        return "Una fracción es una parte de un todo."
    monkeypatch.setattr(jv, "_cloud_chat", chat)
    res = jv.nv_bench_run(pause=0)
    assert [r["modelo"] for r in res] == ["qwen/qwen3-next-80b-a3b-instruct", "moonshotai/kimi-k3.1-pro"] and all(r["ok"] for r in res)
    monkeypatch.setitem(jv.nv, "results", res)
    for k in ("ai_provider", "nvidia_model", "ai_heavy_provider", "ai_heavy_model"):
        monkeypatch.setitem(jv.settings, k, jv.settings.get(k))
    assert "converso con qwen3-next" in jv.nv_use("qwen/qwen3-next-80b-a3b-instruct", "conversar")
    assert jv.settings["ai_provider"] == "nvidia" and jv.settings["nvidia_model"] == "qwen/qwen3-next-80b-a3b-instruct"
    jv.nv_use("moonshotai/kimi-k3.1-pro", "pesados")
    assert jv.settings["ai_heavy_model"] == "moonshotai/kimi-k3.1-pro"
    assert "no está en la última prueba" in jv.nv_use("otro/modelo", "conversar")
    # conversa con Qwen y los trabajos pesados los hace Kimi (mismo proveedor, otro modelo)
    jv._tl.in_job = True
    try:
        hc = jv.heavy_pick(6000, jv._ai_cfg())
        assert hc and hc["model"] == "moonshotai/kimi-k3.1-pro"
    finally:
        jv._tl.in_job, jv._tl.heavy_said = False, False
    # Qwen no recibe «reasoning_effort» (es de Kimi): no hay que reintentar cada vez
    body, _ = jv._oa_body(jv._ai_cfg(), [{"role": "user", "content": "x"}], 100)
    assert "reasoning_effort" not in body
    body, _ = jv._oa_body(jv._ai_cfg({"ai_provider": "nvidia", "nvidia_model": "moonshotai/kimi-k3.1-pro"}), [{"role": "user", "content": "x"}], 100)
    assert body["reasoning_effort"] == "low"


def test_por_voz(jv, monkeypatch):
    jobs = []
    monkeypatch.setitem(jv.settings, "nvidia_api_key", "nvapi-prueba")
    monkeypatch.setattr(jv, "nv_bench_job", lambda: jobs.append(1) or True)
    import nucleo.nvmodelos as nm
    monkeypatch.setattr(nm, "nv_bench_job", lambda: jobs.append(1) or True)
    for p in ("compara los modelos de NVIDIA", "¿cuál modelo de NVIDIA es más rápido?", "prueba la velocidad de los modelos de nvidia", "compara las IA gratis"):
        jv._rec.clear()
        jv.process_command(p)
    assert len(jobs) == 4
