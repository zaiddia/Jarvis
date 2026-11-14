"""12.34: «hay tres Jarvis»: por voz en vivo (Gemini Live) decía «no puedo» lo que escrito sí hacía."""
import json

import pytest


@pytest.fixture
def live(jv, monkeypatch):
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.state, "ai", "ok")
    answers = []

    def ai(msgs, **k):
        if "parte de Jarvis que entiende" in msgs[0]["content"]:
            return json.dumps(answers.pop(0) if answers else {"tipo": "pregunta"})
        raise jv.AIError("x", kind="config")
    monkeypatch.setattr(jv, "ai_chat", ai)
    return answers


def test_en_vivo_traduce_antes_de_rendirse(jv, live, monkeypatch):
    ran = []
    monkeypatch.setattr(jv, "run_skill", lambda name, args, confirmed=False: ran.append((name, args)) or True)
    live.append({"tipo": "orden", "orden": "brillo al 90", "seguro": True})
    r = jv.live_run_order("ponle más luz a la pantalla que no veo nada")
    assert ran and ran[-1][0] == "brillo" and "respóndela tú" not in r.get("result", "")
    live.append({"tipo": "charla"})
    r = jv.live_run_order("me siento un poco cansado hoy la verdad")
    assert r["result"] == "Eso no es una orden del computador: respóndela tú."            # de verdad no era orden


def test_en_vivo_lo_delicado_pide_permiso_sin_hablar_encima(jv, live, monkeypatch):
    asked = []
    jv._rec.clear()
    monkeypatch.setattr(jv, "request_approval", lambda tipo, titulo, detalle="", on_ok=None, quiet=False, **k: asked.append((titulo, quiet)))
    live.append({"tipo": "orden", "orden": "vacía la lista del mercado", "seguro": True})
    r = jv.live_run_order("listo, el mercado ya quedó hecho")
    assert asked == [("¿Hago «vacía la lista del mercado»?", True)]
    said = " ".join(t for t, _o in jv._rec.replies)                          # (en la app va en la respuesta que lee Gemini)
    assert "necesito su permiso" in said and "«sí»" in said


def test_instrucciones_de_la_voz_en_vivo(jv):
    rule = jv.LIVE_RULE
    assert "NUNCA digas que no puedes hacer algo sin haber llamado antes a ejecutar_orden" in rule
    for w in ("gastos", "noticias", "correos", "documentos", "proyectos"):
        assert w in rule
    d = next(f for f in jv.LIVE_FUNCS if f["name"] == "ejecutar_orden")["description"]
    assert "SIEMPRE antes de decir que algo no se puede" in d


def test_con_la_ia_local_menos_ejemplos(jv, monkeypatch):
    monkeypatch.setattr(jv, "_is_local_ai", lambda cfg=None: True)
    near, rest = jv.nl_catalog("lo del súper fueron 85 lucas")
    assert len(near) == 18 and rest == []
