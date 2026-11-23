"""Pruebas de la 12.49: «¿por qué tardas?» cuenta cada consulta a la IA, y un parámetro rechazado no se vuelve a mandar."""
import rapidez


def test_parametro_rechazado_se_recuerda(jv, monkeypatch):
    jv._rejected.clear()
    sent = []

    def http(method, url, headers, payload, timeout, stream=False):
        sent.append(dict(payload))
        if "reasoning_effort" in payload:
            raise jv.AIError("bad", kind="bad", code=400, raw='{"error":"unknown field reasoning_effort"}')
        return {"ok": 1}
    monkeypatch.setattr(jv, "_http", http)
    opt = (("reasoning_effort", ("reasoning_effort",)), ("max_tokens", ("max_tokens",)))
    body = {"model": "qwen/qwen3.8-27b", "reasoning_effort": "low", "max_tokens": 100}
    assert jv._post("https://api.x.com/v1/chat/completions", {}, body, opt) == {"ok": 1} and len(sent) == 2
    assert jv._post("https://api.x.com/v1/chat/completions", {}, body, opt) == {"ok": 1} and len(sent) == 3   # ya no lo intenta
    assert "reasoning_effort" not in sent[-1] and sent[-1]["max_tokens"] == 100
    jv._rejected.clear()


def test_por_que_tardas_cuenta_la_ia():
    rapidez.begin("voz", now=100.0)
    rapidez.mark("orden", now=100.1)
    rapidez.ai_note("entender la orden", {"model": "qwen/qwen3.8-27b", "label": "IteraCompute"}, 1.24, [{"content": "x" * 600}])
    rapidez.ai_note("responder", {"model": "qwen/qwen3.8-27b", "label": "IteraCompute"}, 6.3, [{"content": "x" * 30000}])
    rapidez.mark("respuesta", now=108.0)
    r = rapidez.finish_without_voice()
    assert [c["que"] for c in r["ia"]] == ["entender la orden", "responder"]
    txt = rapidez.spoken(rapidez.summary(1))
    assert "2 veces" in txt and "responder 6.3 s con qwen3.8-27b (IteraCompute)" in txt and "5000 palabras" in txt
