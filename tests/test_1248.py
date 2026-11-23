"""Pruebas de la 12.48: IteraCompute (Qwen3.8 27B gratis), IA de respaldo entre las gratis y la comparación con todas."""


def test_proveedor_iteracompute(jv, monkeypatch):
    p = jv.PROVIDERS["iteracompute"]
    assert p["base"] == "https://api.iteracompute.com/v1" and p["model"] == "qwen/qwen3.8-27b"
    assert jv.ENV_ALIASES["ITERACOMPUTE_API_KEY"] == "iteracompute_api_key"
    monkeypatch.setitem(jv.settings, "iteracompute_api_key", "ic-prueba")
    cfg = jv._ai_cfg({"ai_provider": "iteracompute"})
    short, _ = jv._oa_body(cfg, [{"role": "user", "content": "x"}], 220, json_mode=True)
    assert short["chat_template_kwargs"] == {"enable_thinking": False} and short["max_tokens"] == 2048     # lo corto: sin pensar
    long_, _ = jv._oa_body(cfg, [{"role": "user", "content": "x"}], 9000)
    assert "chat_template_kwargs" not in long_ and long_["max_tokens"] == 8192 and long_["reasoning_effort"] == "low"


def _keys(jv, monkeypatch, **k):
    for pid in ("gemini", "nvidia", "iteracompute"):
        monkeypatch.setitem(jv.settings, f"{pid}_api_key", k.get(pid, ""))
    monkeypatch.setitem(jv.settings, "ai_backup_provider", "auto")
    monkeypatch.setitem(jv.net, "offline", False)


def test_respaldo_entre_las_gratis(jv, monkeypatch):
    _keys(jv, monkeypatch, gemini="AIza-x", iteracompute="ic-x")
    g = jv._ai_cfg({"ai_provider": "gemini"})
    assert jv.backup_cfg(g)["ai_provider"] == "iteracompute"
    assert jv.backup_cfg(jv._ai_cfg({"ai_provider": "iteracompute"}))["ai_provider"] == "gemini"
    monkeypatch.setitem(jv.settings, "ai_backup_provider", "off")
    assert jv.backup_cfg(g) is None
    monkeypatch.setitem(jv.settings, "ai_backup_provider", "auto")
    assert jv.backup_cfg(dict(g, heavy=True)) is None and jv.backup_cfg(dict(g, backup=True)) is None
    # Gemini sin cuota (y sin otro modelo que sirva): responde IteraCompute
    monkeypatch.setattr(jv, "_ensure_model", lambda c: c)
    monkeypatch.setattr(jv, "_try_other_models", lambda c, fn, e, tries=2: (_ for _ in ()).throw(e))
    calls = []

    def fn(c):
        calls.append(c["ai_provider"])
        if c["ai_provider"] == "gemini":
            raise jv.AIError("cuota", kind="quota", why="sin cuota")
        return "hola desde " + c["ai_provider"]
    assert jv._with_fallback(g, fn) == "hola desde iteracompute" and calls == ["gemini", "iteracompute"]


def test_pesados_auto_usa_iteracompute_si_no_hay_nvidia(jv, monkeypatch):
    _keys(jv, monkeypatch, gemini="AIza-x", iteracompute="ic-x")
    monkeypatch.setitem(jv.settings, "ai_provider", "gemini")
    monkeypatch.setitem(jv.settings, "ai_heavy_provider", "auto")
    monkeypatch.setitem(jv.settings, "ai_heavy_model", "")
    monkeypatch.setitem(jv.heavy, "pause_until", 0.0)
    jv._tl.in_job = True
    try:
        hc = jv.heavy_pick(6000, jv._ai_cfg())
        assert hc["ai_provider"] == "iteracompute" and hc["model"] == "qwen/qwen3.8-27b"
    finally:
        jv._tl.in_job, jv._tl.heavy_said = False, False


def test_comparar_incluye_iteracompute(jv, monkeypatch):
    _keys(jv, monkeypatch, nvidia="nvapi-x", iteracompute="ic-x")
    monkeypatch.setattr(jv, "ai_list_models", lambda cfg: ["moonshotai/kimi-k3.1-pro"])
    monkeypatch.setattr(jv, "_cloud_chat", lambda cfg, m, j=False, max_tokens=None, image_path=None: "Una parte de un todo, profe.")
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setattr(jv, "check_ai", lambda *a, **k: True)
    res = jv.nv_bench_run(pause=0)
    assert {(r["proveedor"], r["modelo"]) for r in res} == {("nvidia", "moonshotai/kimi-k3.1-pro"), ("iteracompute", "qwen/qwen3.8-27b")}
    monkeypatch.setitem(jv.nv, "results", res)
    for k in ("ai_provider", "iteracompute_model", "ai_heavy_provider", "ai_heavy_model"):
        monkeypatch.setitem(jv.settings, k, jv.settings.get(k))
    assert "de IteraCompute" in jv.nv_use("qwen/qwen3.8-27b", "conversar")
    assert jv.settings["ai_provider"] == "iteracompute" and jv.settings["iteracompute_model"] == "qwen/qwen3.8-27b"
