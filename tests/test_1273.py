"""Pruebas de la 12.73: Z.ai (GLM) como proveedor de IA, con sus modelos gratis."""
import pytest


def _fake_post(sent, reply="Hola, profesor."):
    def fake(url, headers, payload, optional=(), timeout=180, stream=False):
        sent.append((url, headers, payload, optional))
        return {"choices": [{"message": {"content": reply}}]}
    return fake


def test_proveedor(jv):
    sp = jv.PROVIDERS["zai"]
    assert sp["base"] == "https://api.z.ai/api/paas/v4" and sp["kind"] == "openai" and sp["group"] == "cloud"
    assert sp["model"] == "glm-4.7-flash" and sp["model"] in sp["free_models"]
    assert sp["models"][:3] == sp["free_models"]                    # los gratis primero
    assert "zai_api_key" in jv.settings and jv.settings["zai_model"] == "glm-4.7-flash"
    assert "zai" not in jv.BACKUP_ORDER and "zai" in jv.FREE_PROVIDERS
    assert "estudiantes" in sp["note"]
    assert jv.ENV_ALIASES["ZAI_API_KEY"] == "zai_api_key"


def test_cuerpo_sin_pensar_en_lo_corto(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "zai_api_key", "k-zai")
    cfg = jv._ai_cfg({"ai_provider": "zai"})
    sent = []
    monkeypatch.setattr(jv, "_post", _fake_post(sent))
    out = jv._cloud_chat(cfg, [{"role": "user", "content": "hola"}], max_tokens=300)
    url, headers, body, optional = sent[-1]
    assert "Hola" in out and url == "https://api.z.ai/api/paas/v4/chat/completions"
    assert headers["Authorization"] == "Bearer k-zai"
    assert body["model"] == "glm-4.7-flash" and body["thinking"] == {"type": "disabled"}
    assert any(p == "thinking" for p, _ in optional)              # si no lo acepta, se quita solo
    jv._cloud_chat(cfg, [{"role": "user", "content": "un informe largo"}], max_tokens=5000)
    assert sent[-1][2]["thinking"] == {"type": "enabled"}


def test_foto_va_al_modelo_que_ve(jv, monkeypatch, tmp_path):
    from PIL import Image
    img = tmp_path / "p.png"
    Image.new("RGB", (8, 8), "white").save(img)
    monkeypatch.setitem(jv.settings, "zai_api_key", "k-zai")
    sent = []
    monkeypatch.setattr(jv, "_post", _fake_post(sent))
    cfg = jv._ai_cfg({"ai_provider": "zai"})
    jv._cloud_chat(cfg, [{"role": "user", "content": "¿qué ves?"}], image_path=str(img))
    assert sent[-1][2]["model"] == "glm-4.6v-flash"
    jv._cloud_chat(dict(cfg, model="glm-5.3-flash"), [{"role": "user", "content": "¿qué ves?"}], image_path=str(img))
    assert sent[-1][2]["model"] == "glm-5.3-flash"               # ese ya ve imágenes
    jv._cloud_chat(cfg, [{"role": "user", "content": "hola"}])
    assert sent[-1][2]["model"] == "glm-4.7-flash"               # sin foto, el de siempre


def test_lista_fija_si_no_hay_lista(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "zai_api_key", "k-zai")
    cfg = jv._ai_cfg({"ai_provider": "zai"})

    def no_list(*a, **k):
        raise jv.AIError("not found", kind="model", code=404)
    monkeypatch.setattr(jv, "_http", no_list)
    assert jv.ai_list_models(cfg) == jv.PROVIDERS["zai"]["models"]

    def bad_key(*a, **k):
        raise jv.AIError("unauthorized", kind="key", code=401)
    monkeypatch.setattr(jv, "_http", bad_key)
    with pytest.raises(jv.AIError):
        jv.ai_list_models(cfg)                                     # una clave mala se dice, no se esconde

    monkeypatch.setattr(jv, "_http", lambda *a, **k: {"data": [{"id": "glm-9"}, {"id": "glm-4.7-flash"}]})
    got = jv.ai_list_models(cfg)
    assert got[:6] == jv.PROVIDERS["zai"]["models"] and got[-1] == "glm-9"


def test_si_se_llena_pasa_a_otro_gratis(jv, monkeypatch):
    sp = jv.PROVIDERS["zai"]
    assert jv._recommend_model("zai", sp["models"], exclude=("glm-4.7-flash",)) == "glm-4.5-flash"
    assert jv._recommend_model("zai", sp["models"], exclude=("glm-4.7-flash", "glm-4.5-flash")) == "glm-4.6v-flash"


def test_sin_saldo_es_saldo(jv):
    kind = jv._classify(429, '{"error":{"code":"1113","message":"Insufficient balance or no resource package. Please recharge."}}')
    kind = kind[0] if isinstance(kind, tuple) else getattr(kind, "kind", kind)
    assert kind == "balance"


def test_plan_de_programacion(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "zai_api_key", "k-zai")
    assert jv._ai_cfg({"ai_provider": "zai"})["base"] == "https://api.z.ai/api/paas/v4"
    monkeypatch.setitem(jv.settings, "zai_coding", True)
    assert jv._ai_cfg({"ai_provider": "zai"})["base"] == "https://api.z.ai/api/coding/paas/v4"
    assert "zai_coding" in jv.AI_SETTING_KEYS


def test_comparar_incluye_glm_gratis(jv, monkeypatch):
    for p in jv.FREE_PROVIDERS:
        monkeypatch.setitem(jv.settings, f"{p}_api_key", "")
    monkeypatch.setitem(jv.settings, "zai_api_key", "k-zai")
    models = [m for _, m in jv.nv_pairs()]
    assert models == ["glm-4.7-flash", "glm-4.5-flash"]


def test_por_voz(jv, monkeypatch):
    picked = []
    monkeypatch.setattr(jv, "ai_choices", lambda: {"items": [
        {"id": "nube:gemini", "tipo": "nube", "nombre": "Gemini", "detalle": "", "gb": 0},
        {"id": "nube:zai", "tipo": "nube", "nombre": "Z.ai GLM", "detalle": "", "gb": 0}], "actual": "nube:gemini"})
    monkeypatch.setattr(jv, "ai_pick", lambda i: picked.append(i) or {"msg": "Listo."})
    for frase in ("usa glm", "cambia a la ia z.ai", "usa zeta ai"):
        t = jv.normalize(frase)
        assert jv.ai_pick_voice(frase, t), frase
    assert picked == ["nube:zai"] * 3


def test_ajustes_muestra_el_plan(jv):
    import os
    html = open(os.path.join(os.path.dirname(jv.__file__), "templates", "settings.html"), encoding="utf-8").read()
    assert 'data-key="zai_coding"' in html and "p.coding_base" in html
