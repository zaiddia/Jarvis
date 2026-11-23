"""Pruebas de la 12.46: Gemini para conversar, Kimi (NVIDIA) para los trabajos pesados en segundo plano."""


def _setup(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "ai_provider", "gemini")
    monkeypatch.setitem(jv.settings, "gemini_api_key", "AIza-prueba")
    monkeypatch.setitem(jv.settings, "nvidia_api_key", "nvapi-prueba")
    monkeypatch.setitem(jv.settings, "ai_heavy_provider", "auto")
    monkeypatch.setitem(jv.net, "offline", False)
    monkeypatch.setattr(jv, "net_preflight", lambda: False)
    monkeypatch.setitem(jv.heavy, "pause_until", 0.0)
    from nucleo.ia import ai_chat
    monkeypatch.setattr(jv, "ai_chat", ai_chat)                              # la de verdad (las pruebas la apagan)
    monkeypatch.setattr(jv, "usage_add", lambda *a, **k: None)
    used = []
    monkeypatch.setattr(jv, "_with_fallback", lambda cfg, fn: used.append(cfg["ai_provider"]) or fn(cfg))
    return used


def test_trabajo_pesado_va_a_kimi_y_lo_de_siempre_a_gemini(jv, monkeypatch):
    used = _setup(jv, monkeypatch)
    monkeypatch.setattr(jv, "_cloud_chat", lambda cfg, m, j=False, max_tokens=None, image_path=None: f"de {cfg['ai_provider']}")
    msgs = [{"role": "user", "content": "x"}]
    jv._tl.in_job, jv._tl.heavy_said = False, False
    try:
        assert jv.ai_chat(msgs, max_tokens=8000) == "de gemini"          # en la conversación: la rápida, aunque sea largo
        jv._tl.in_job = True
        assert jv.ai_chat(msgs, max_tokens=300) == "de gemini"           # en un trabajo, pero corto: la rápida
        assert jv.ai_chat(msgs, json_mode=True, max_tokens=8000) == "de nvidia"
        assert jv._tl.heavy_said
        monkeypatch.setitem(jv.settings, "ai_heavy_provider", "off")
        assert jv.ai_chat(msgs, max_tokens=8000) == "de gemini"
        monkeypatch.setitem(jv.settings, "ai_heavy_provider", "auto")
        monkeypatch.setitem(jv.settings, "nvidia_api_key", "")
        assert jv.ai_chat(msgs, max_tokens=8000) == "de gemini"          # sin clave de NVIDIA: nada cambia
    finally:
        jv._tl.in_job, jv._tl.heavy_said = False, False
    assert used.count("nvidia") == 1


def test_si_kimi_falla_lo_termina_gemini(jv, monkeypatch):
    _setup(jv, monkeypatch)

    def chat(cfg, m, j=False, max_tokens=None, image_path=None):
        if cfg["ai_provider"] == "nvidia":
            raise jv.AIError("límite", kind="quota", why="se llenó el límite")
        return "de gemini"
    monkeypatch.setattr(jv, "_cloud_chat", chat)
    jv._tl.in_job = True
    try:
        assert jv.ai_chat([{"role": "user", "content": "x"}], max_tokens=6000) == "de gemini"
        assert jv.heavy["pause_until"] > 0 and not getattr(jv._tl, "no_heavy", False)
        assert jv.heavy_pick(6000, jv._ai_cfg()) is None                  # descansa unos minutos
    finally:
        jv._tl.in_job, jv._tl.heavy_said = False, False


def test_trabajos_marcan_su_hilo(jv):
    import threading
    seen = []
    ev = threading.Event()
    from nucleo.tablero import start_job
    start_job("prueba", lambda: (seen.append(getattr(jv._tl, "in_job", False)), ev.set()), "prueba").join(5)
    assert seen == [True]
