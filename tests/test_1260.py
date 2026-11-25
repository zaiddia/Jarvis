"""Pruebas de la 12.60: SenseNova (SenseTime) como proveedor de IA."""
import json


def test_proveedor(jv):
    sp = jv.PROVIDERS["sensenova"]
    assert sp["base"] == "https://token.sensenova.ai/v1" and sp["kind"] == "openai" and sp["model"] == "sensenova-6.8-flash"
    assert "sensenova_api_key" in jv.settings and "China" in sp["note"]
    assert "sensenova" not in jv.BACKUP_ORDER                      # datos en China: nunca de respaldo sin que lo escojas
    assert "sensenova" in jv.FREE_PROVIDERS


def test_cuerpo_de_la_peticion(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "sensenova_api_key", "sk-x")
    cfg = jv._ai_cfg({"ai_provider": "sensenova"})
    sent = []

    def fake(url, headers, payload, optional=(), timeout=180, stream=False):
        sent.append((url, headers, payload))
        return {"choices": [{"message": {"content": "Hola, profesor."}}]}
    monkeypatch.setattr(jv, "_post", fake)
    out = jv._cloud_chat(cfg, [{"role": "user", "content": "hola"}], max_tokens=300)
    url, headers, body = sent[-1]
    assert "Hola" in out and url == "https://token.sensenova.ai/v1/chat/completions"
    assert "sk-x" in str(headers.get("Authorization"))
    assert body["model"] == "sensenova-6.8-flash" and body["reasoning_effort"] == "none" and body["max_tokens"] >= 2048
    jv._cloud_chat(cfg, [{"role": "user", "content": "un informe largo"}], max_tokens=5000)
    assert sent[-1][2]["reasoning_effort"] == "low"


def test_clave_por_variable(jv):
    assert jv.ENV_ALIASES["SENSENOVA_API_KEY"] == "sensenova_api_key"
