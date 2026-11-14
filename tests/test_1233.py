"""12.33: lo que salió de la prueba de comprensión real (58 %): cuota mal clasificada, frases devueltas sin traducir, y la nota."""
import json

import frasesnl


def test_429_de_gemini_es_cuota_no_saldo(jv):
    body = json.dumps({"error": {"code": 429, "message": "You exceeded your current quota, please check your plan and billing details.",
                                 "status": "RESOURCE_EXHAUSTED"}})
    assert jv._classify(429, body)[0] == "quota"                          # así también prueba otro modelo de tu cuenta
    assert jv._classify(402, json.dumps({"error": {"message": "Your credit balance is too low"}}))[0] == "balance"
    assert jv._classify(429, json.dumps({"error": {"message": "Your credit balance is too low"}}))[0] == "balance"


def test_nota_con_lo_que_paso_de_verdad():
    g = frasesnl.grade
    o = lambda x: {"tipo": "orden", "orden": x}
    assert g(o("libera espacio en el disco"), "limpia los temporales", "libera espacio en el disco") == "mal"     # sin traducir
    assert g(o("limpia los temporales"), "limpia los temporales", "libera espacio en el disco") == "bien"
    assert g(o("pausa Spotify"), "pausa la música", "pausa la música") == "bien"                                  # otra forma válida
    assert g(o("modo casa"), "modo asistente general", "quiero que estés en modo casa") == "bien"
    assert g(o("registré 3500 de café"), "gasté 3500 en tinto", "me tomé un tinto de 3500") == "mal"
    assert g(o("cuánto queda"), "cuánto espacio tengo", "cuánto disco me queda") == "mal"
    assert g({"tipo": "pregunta"}, "qué medicamentos tengo", "qué medicinas tomo") == "mal"
    assert frasesnl.orders_of("pausa la música") == ["pausa la música", "pausa Spotify"]


def test_las_formas_alternativas_tambien_las_hace_una_regla(jv, ask, monkeypatch):
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.settings, "assistant_mode", "general")
    for nat, _c, _a in frasesnl.rows():
        for alt in frasesnl.orders_of(nat)[1:]:
            assert not ask(alt)[0].startswith("IA"), alt


def test_el_prompt_pide_la_forma_de_la_lista(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "assistant_mode", "general")
    near, rest = jv.nl_catalog("cuánto disco me queda")
    p = jv.nl_prompt("cuánto disco me queda", near, rest)
    assert "Nunca devuelvas la frase de la persona tal cual" in p and "«qué medicinas tomo» → «qué medicamentos tengo»" in p
    assert "cuánto espacio tengo" in p or "¿cuánto espacio tengo?" in p
    assert len(near) == jv.NL_K == 30


def test_si_la_devuelve_sin_traducir_lo_intenta_otra_vez(jv, ask, monkeypatch):
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.state, "ai", "ok")
    answers = [{"tipo": "orden", "orden": "oye la pantalla está como muy oscura"}, {"tipo": "orden", "orden": "brillo al 90"}]
    calls = []

    def ai(msgs, **k):
        if "parte de Jarvis que entiende" in msgs[0]["content"]:
            calls.append(msgs)
            return json.dumps(answers.pop(0))
        raise jv.AIError("x", kind="config")
    monkeypatch.setattr(jv, "ai_chat", ai)
    who, _ = ask("oye la pantalla está como muy oscura")
    assert len(calls) == 2 and "no la reconoce Jarvis" in calls[1][-1]["content"] and who == "skill:brillo"
