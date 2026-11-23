"""Pruebas de la 12.44: NVIDIA Build como proveedor (Kimi K3.1 Pro gratis con clave nvapi-)."""


def test_proveedor_nvidia(jv, monkeypatch):
    p = jv.PROVIDERS["nvidia"]
    assert p["base"] == "https://integrate.api.nvidia.com/v1" and p["model"] == "moonshotai/kimi-k3.1-pro" and p["key_hint"].startswith("nvapi")
    assert jv.ENV_ALIASES["NVIDIA_API_KEY"] == "nvidia_api_key" and "nvidia_api_key" in jv.API_KEY_FIELDS
    monkeypatch.setitem(jv.settings, "nvidia_api_key", "nvapi-prueba")
    cfg = jv._ai_cfg({"ai_provider": "nvidia"})
    assert cfg["model"] == "moonshotai/kimi-k3.1-pro" and cfg["key"] == "nvapi-prueba"
    body, opt = jv._oa_body(cfg, [{"role": "user", "content": "hola"}], 220, json_mode=True)
    assert body["max_tokens"] == 4096 and body["reasoning_effort"] == "low" and "temperature" not in body     # piensa: más espacio
    assert any(k == "reasoning_effort" for k, _ in opt)                         # si NVIDIA no lo acepta, se quita solo
    sent = {}
    monkeypatch.setattr(jv, "_http", lambda m, url, h, payload, timeout, stream=False: sent.update(url=url, h=h) or
                        {"choices": [{"message": {"content": "<think>pienso</think>Hola, profe."}}]})
    assert jv._cloud_chat(cfg, [{"role": "user", "content": "hola"}]) == "Hola, profe."
    assert sent["url"].endswith("/chat/completions") and sent["h"]["Authorization"] == "Bearer nvapi-prueba"


def test_la_voz_no_lee_el_razonamiento(jv):
    parts = ["Ho", "la <thi", "nk>esto no", " se dice</th", "ink> profe", ", ¿qué tal?"]
    assert "".join(jv.skip_think(iter(parts))) == "Hola  profe, ¿qué tal?"
    assert "".join(jv.skip_think(iter(["2 < 3 y", " listo"]))) == "2 < 3 y listo"
