"""12.29: la comprensión primero en lo conversacional, segundo intento, botones para aclarar y prueba de comprensión real."""
import json
import os

import pytest

import frasesnl


@pytest.fixture
def nl(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.settings, "assistant_mode", "general")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="", *a, **k: fn())
    calls, answers = [], []

    def ai(msgs, **k):
        if "parte de Jarvis que entiende" in msgs[0]["content"]:
            calls.append(msgs)
            a = answers.pop(0) if answers else {"tipo": "pregunta"}
            if isinstance(a, Exception):
                raise a
            return json.dumps(a)
        raise jv.AIError("sin IA en las pruebas", kind="config")
    monkeypatch.setattr(jv, "ai_chat", ai)
    emitted = []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: emitted.append((ev, data)))
    jv.nl_pending.update(ops=[], until=0.0)
    return calls, answers, emitted


def test_que_suena_a_conversacion(jv):
    c = jv.nl_conversational
    for f in ("oye pon algo de musica que estoy aburrido", "es que mañana tengo que llevar el carro al taller",
              "mira se me acabo la leche y el pan", "resulta que el viernes viene mi mama a visitarme y quiero tener todo listo",
              "jarvis el computador esta como pegado desde esta mañana"):
        assert c(jv.normalize(f)), f
    for f in ("sube el volumen", "pon salsa en spotify", "recuerdame mañana a las 7 llevar el carro al taller de la 80",
              "que es la fotosintesis y por que es importante para las plantas", "hola jarvis como estas", "abre excel",
              "escribe una historia de un dragon que vive en una montaña"):
        assert not c(jv.normalize(f)), f


def test_conversacional_entra_antes_que_las_reglas(nl, jv, ask):
    calls, answers, _ = nl
    answers.append({"tipo": "orden", "orden": "pon salsa en Spotify", "seguro": True})
    assert ask("oye pon algo de música que estoy aburrido")[0] == "skill:spotify" and len(calls) == 1
    answers.append({"tipo": "pregunta"})                                  # no es orden: siguen las reglas, como siempre
    who_with = ask("oye pon algo de música que estoy aburrido")[0]
    calls.clear()
    jv.settings["nl_understand"] = False
    try:
        assert ask("oye pon algo de música que estoy aburrido")[0] == who_with and not calls
    finally:
        jv.settings["nl_understand"] = True
    assert ask("sube el volumen")[0] == "skill:volumen" and not calls    # lo corto y claro: directo, sin IA


def test_una_sola_pasada_por_frase(nl, ask):
    calls, answers, _ = nl
    answers.extend([{"tipo": "pregunta"}])
    ask("mira se me acabó la paciencia con este computador tan lento")
    assert len(calls) == 1                                                # la de antes no se repite al final


def test_segundo_intento(nl, ask):
    calls, answers, _ = nl
    answers.extend([{"tipo": "orden", "orden": "registra un gasto mercado 85000", "seguro": True},
                    {"tipo": "orden", "orden": "gasté 85 mil en mercado", "seguro": True}])
    who, said = ask("oye lo del súper ayer fueron como 85 lucas")
    assert who == "GASTOS" and len(calls) == 2
    assert "no la reconoce Jarvis" in calls[1][-1]["content"] and "registra un gasto mercado 85000" in calls[1][-2]["content"]


def test_botones_y_la_primera(nl, jv, ask):
    calls, answers, emitted = nl
    answers.append({"tipo": "aclarar", "opciones": ["gasté 85 mil en mercado", "mi presupuesto de comida es de 85 mil"]})
    who, said = ask("oye lo de la comida son 85 lucas")
    assert who == "COMPRENSIÓN" and "«la primera»" in said
    assert ("nl_options", {"opciones": ["gasté 85 mil en mercado", "mi presupuesto de comida es de 85 mil"]}) in emitted
    assert ask("la segunda")[0] == "PRESUPUESTO" and not jv.nl_pending["ops"]
    jv.nl_offer(["gasté 85 mil en mercado", "mi presupuesto de comida es de 85 mil"])
    ask("qué hora es")                                                    # otra cosa: la aclaración pasó
    assert not jv.nl_pending["ops"] and ask("la primera")[0] != "GASTOS"
    jv.nl_offer(["gasté 85 mil en mercado"])
    assert "Solo te di 1" in ask("la tercera")[1]
    js = open(os.path.join(os.path.dirname(__file__), "..", "static", "js", "hud.js"), encoding="utf-8").read()
    assert js.index('socket.on("nl_options"') > js.index("const socket = io()") and "run(o)" in js


def test_cada_habilidad_tiene_un_ejemplo(jv):
    bad = [g["nombre"] for c in jv.guide() for g in c["grupos"] if not any(e["probar"] for e in g["ejemplos"])]
    assert not bad


def test_nota_de_la_prueba():
    assert frasesnl.similar("recuérdame mañana a las 7 llevar el carro al taller", "recuérdame mañana a las 7 llevar el carro al taller")
    assert frasesnl.grade({"tipo": "orden", "orden": "gasté 85 mil en mercado"}, "gasté 85 mil en mercado") == "bien"
    assert frasesnl.grade({"tipo": "orden", "orden": "pon salsa"}, "gasté 85 mil en mercado") == "mal"
    assert frasesnl.grade({"tipo": "aclarar", "opciones": ["pon salsa", "gasté 85 mil en mercado"]}, "gasté 85 mil en mercado") == "aclaró"
    assert len(frasesnl.rows()) >= 150


def test_prueba_de_comprension(nl, jv, ask, monkeypatch):
    calls, answers, _ = nl
    rows = frasesnl.rows()
    sample = __import__("random").Random(7).sample(rows, 10)
    answers.extend([{"tipo": "orden", "orden": can} if i % 2 == 0 else {"tipo": "charla"} for i, (_n, can, _a) in enumerate(sample)])
    res = jv.nl_test_run(10, pause=0, seed=7)
    assert (res["n"], res["bien"], res["mal"]) == (10, 5, 5)
    path, pct = jv.nl_test_report(res)
    body = open(path, encoding="utf-8").read()
    assert pct == 50 and "Acierto: 50 %" in body and body.index("✗") < body.index("✓") and "Nada de esto se ejecutó" in body
    answers.clear()
    answers.extend([{"tipo": "orden", "orden": can} for _n, can, _a in rows[:3]] + [jv.AIError("cuota", kind="quota")])
    res = jv.nl_test_run(0, pause=0)
    assert res["n"] == 3 and res["corte"] == "cuota"
    said = []
    monkeypatch.setattr(jv, "notify", lambda text, origin="": said.append(text))
    answers.clear()
    who, msg = ask("haz la prueba de comprensión")
    assert who == "COMPRENSIÓN" and "40 frases" in msg and "sin ejecutar nada" in msg
    assert "de 40 frases" in said[-1] and "%" in said[-1]
    assert not jv._rec.skills                                             # no ejecutó ninguna orden
