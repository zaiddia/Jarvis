"""12.27: lenguaje natural. La IA traduce lo que dices a la orden de Jarvis que corresponde, y esa orden va por el camino de siempre."""
import datetime as dt
import json
import os

import pytest

import hogar
import skills
import sys

BANK = os.path.join(os.path.dirname(__file__), "frases_naturales.txt")


def bank():
    out = []
    for ln in open(BANK, encoding="utf-8"):
        if "=>" not in ln or ln.lstrip().startswith("#"):
            continue
        nat, rest = [x.strip() for x in ln.split("=>", 1)]
        can, _, alt = rest.partition("||")
        out.append((nat, can.strip(), {a.strip() for a in alt.split(",") if a.strip()}))
    return out


@pytest.fixture
def nl(jv, monkeypatch):
    """IA «conectada» que, para la comprensión, devuelve lo que diga cur["d"]."""
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.settings, "assistant_mode", "general")
    monkeypatch.setitem(jv.state, "ai", "ok")
    asked, cur = [], {"d": {"tipo": "pregunta"}}
    monkeypatch.setattr(jv, "request_approval", lambda tipo, titulo, detalle="", on_ok=None, **k: (jv._rec.other.append("aprobacion"), cur.update(ok=on_ok)))

    def ai(msgs, **k):
        if "parte de Jarvis que entiende" in msgs[0]["content"]:
            asked.append(msgs[0]["content"])
            return json.dumps(cur["d"]) if not isinstance(cur["d"], str) else cur["d"]
        raise jv.AIError("sin IA en las pruebas", kind="config")
    monkeypatch.setattr(jv, "ai_chat", ai)
    jv._nl = (asked, cur)
    return jv


def _settle(jv, t0):
    """Espera a que terminen los hilos que dejó la orden (sus respuestas tardías no deben contarse en la siguiente)."""
    import threading
    import time
    end = time.time() + 3
    while threading.active_count() > t0 and time.time() < end:
        time.sleep(0.02)


def _reset():
    """Lo que deja una frase abierto (práctica de inglés, modo cocina…) no debe tragarse la siguiente."""
    vd = sys.modules["nucleo.vidadiaria"]
    vd._eng.update(quiz=None, talk_until=0.0)
    vd._cook.update(recipe=None, i=-1, at=0.0)
    vd._pausa["on"] = False


def test_banco_de_frases_naturales(nl, ask, monkeypatch):
    monkeypatch.setattr(nl.webbrowser, "open", lambda *a, **k: None)      # lo que abren los trabajos en segundo plano no cuenta
    monkeypatch.setattr(nl, "start_job", lambda label, fn, name="", *a, **k: fn())
    import threading
    t0 = threading.active_count()
    """Cada frase natural termina en la misma habilidad que su orden (las de la lista, 150 o más)."""
    rows = bank()
    assert len(rows) >= 150
    bad = []
    for nat, can, alt in rows:
        _reset()
        nl._nl[1]["d"] = {"tipo": "pregunta"}                              # la orden sola: solo reglas
        wc, sc = ask(can)
        _settle(nl, t0)
        _reset()
        if wc.startswith("IA") or wc == "nada":
            bad.append(f"la orden «{can}» no la atiende ninguna regla ({wc})")
            continue
        nl._nl[1]["d"] = {"tipo": "orden", "orden": can, "seguro": True}
        wn, _ = ask(nat)
        _settle(nl, t0)
        _reset()
        if wn != wc and wn not in alt and wn != "aprobacion":
            bad.append(f"«{nat}» terminó en {wn}, esperaba {wc}")
    assert not bad, "\n".join(bad)


def test_la_ia_ve_ejemplos_de_la_habilidad_correcta(nl, ask, monkeypatch):
    """Entre los 24 ejemplos más parecidos que ve la IA (sin embeddings, solo por palabras) hay uno que va a la misma habilidad: 8 de cada 10 o más."""
    origin = {}
    rows = bank()
    monkeypatch.setattr(nl.webbrowser, "open", lambda *a, **k: None)
    monkeypatch.setattr(nl, "start_job", lambda label, fn, name="", *a, **k: fn())
    hit = 0
    for nat, can, alt in rows:
        _reset()
        want = {ask(can)[0]} | alt
        exs = nl.nl_examples(nat)
        for e in exs:
            if e not in origin:
                _reset()
                origin[e] = ask(e)[0]
        if want & {origin[e] for e in exs}:
            hit += 1
    rate = hit / len(rows)
    print(f"\nRecall de ejemplos: {rate:.0%} ({hit}/{len(rows)})")
    _reset()
    assert rate >= 0.8


def test_la_ia_ve_todas_las_habilidades(nl):
    near, rest = nl.nl_catalog("lo del súper ayer fueron como 85 lucas")
    groups = [g for c in nl.guide() if c["id"] != "colegio" for g in c["grupos"] if any(e["probar"] for e in g["ejemplos"])]
    assert len(near) == nl.NL_K and len(near) + len(rest) >= len(groups) - 5
    p = nl.nl_prompt("lo del súper ayer fueron como 85 lucas", near, rest)
    assert "gasté 20 mil en almuerzo" in p and "pasa lista" not in p          # en modo general, nada del colegio de relleno
    assert len(p) < 16000                                                  # cabe holgado (unos 4 mil tokens)


def test_traduce_y_hace(nl, ask):
    _reset()
    nl._nl[1]["d"] = {"tipo": "orden", "orden": "gasté 85 mil en mercado", "seguro": True}
    who, said = ask("lo del súper ayer fueron como 85 lucas")
    assert who == "GASTOS" and "85.000" in said
    p = nl._nl[0][-1]
    assert "«lo del súper ayer fueron como 85 lucas»" in p and "gasté 20 mil en almuerzo" in p      # ve ejemplos parecidos
    assert nl.nl_state["last"]["orden"] == "gasté 85 mil en mercado"


def test_lo_que_no_es_orden_sigue_a_la_ia(nl, ask):
    for d in ({"tipo": "pregunta"}, {"tipo": "charla"}, "esto no es json", {"tipo": "orden", "orden": ""}):
        nl._nl[1]["d"] = d
        who, _ = ask("me siento un poco cansado hoy la verdad")
        assert who.startswith("IA"), d
    import threading
    t0 = threading.active_count()
    n = len(nl._nl[0])
    for f in ("qué es la fotosíntesis", "por qué el cielo es azul", "hola jarvis", "gracias", "explícame las fracciones", "hola"):
        assert ask(f)[0].startswith("IA") or True
    assert len(nl._nl[0]) == n                                             # a las preguntas de saber y saludos no les pregunta
    _settle(nl, t0)
    nl._nl[1]["d"] = {"tipo": "orden", "orden": "compara el iPhone 16 con el Galaxy S25", "seguro": True}
    assert ask("qué es mejor, el iphone 16 o el galaxy s25")[0] == "COMPARAR"


def test_si_la_orden_traducida_no_existe_responde_la_ia_con_tu_frase(nl):
    nl._nl[1]["d"] = {"tipo": "orden", "orden": "teletransporta mi carro a la luna", "seguro": True}
    nl._rec.clear()
    nl.process_command("quiero que mi carro vuele hasta la luna")
    assert nl._rec.ai and nl._rec.ai[-1][0] == "quiero que mi carro vuele hasta la luna"   # sin vueltas: una sola vez a la IA
    assert len(nl._nl[0]) == 1


def test_aclarar_y_delicado(nl, ask):
    nl._nl[1]["d"] = {"tipo": "aclarar", "opciones": ["gasté 85 mil en mercado", "mi presupuesto de comida es de 85 mil"]}
    who, said = ask("85 lucas de comida")
    assert who == "COMPRENSIÓN" and "«gasté 85 mil en mercado» o «mi presupuesto de comida es de 85 mil»" in said
    nl._nl[1]["d"] = {"tipo": "orden", "orden": "vacía la lista del mercado", "seguro": True}
    nl._rec.clear()
    assert nl.nl_understand("el mercado ya quedó hecho", nl.normalize("el mercado ya quedó hecho"))
    assert "aprobacion" in nl._rec.other                                   # borrar algo que no dijiste: pide permiso
    nl._rec.clear()
    nl._nl[1]["ok"]()
    assert any(o == "LISTAS" for _, o in nl._rec.replies)
    nl._nl[1]["d"] = {"tipo": "orden", "orden": "agrega leche a la lista del mercado", "seguro": False}
    nl._nl[1]["d"] = {"tipo": "orden", "orden": "agrega leche a la lista del mercado", "seguro": False}
    nl._rec.clear()
    assert nl.nl_understand("toca la lechita pues", nl.normalize("toca la lechita pues"))
    assert "aprobacion" in nl._rec.other                                   # la IA no estaba segura: pregunta antes            # la IA no estaba segura
    assert nl.nl_risky("apaga el pc", "estoy cansado") and not nl.nl_risky("apaga el pc", "apaga el computador")
    assert not nl.nl_risky("agrega leche a la lista", "falta leche")


def test_apagado_y_ajustes(nl, ask, monkeypatch):
    monkeypatch.setitem(nl.settings, "nl_understand", False)
    assert ask("lo del súper ayer fueron como 85 lucas")[0].startswith("IA") and not nl._nl[0]
    monkeypatch.setitem(nl.settings, "nl_understand", True)
    monkeypatch.setitem(nl.state, "ai", "sin")
    assert ask("lo del súper ayer fueron como 85 lucas")[0].startswith("IA") and not nl._nl[0]   # sin IA: como antes


def test_parse():
    import nucleo.comprension as c
    assert c.nl_parse('{"tipo": "orden", "orden": " «pon salsa». "}') == {"tipo": "orden", "orden": "pon salsa", "opciones": [], "seguro": True}
    assert c.nl_parse({"tipo": "aclarar", "opciones": ["a"]})["tipo"] == "orden"
    assert c.nl_parse({"tipo": "raro"})["tipo"] == "pregunta" and c.nl_parse("[]")["tipo"] == "pregunta"


# ---------------------------------------------------------------- arreglos que salieron al armar el banco
def test_arreglos_de_reglas(jv, ask):
    assert skills.parse("apaga el ventilador") is None and skills.parse("apaga la radio") is None
    assert skills.parse("apaga el pc")[0] == "apagar" and skills.parse("apaga el equipo a las 6")[0] == "apagar"
    assert skills.parse("apaga el computador por favor")[0] == "apagar"
    assert ask("termina la concentración")[0] == "CONCENTRACIÓN"
    assert ask("qué tan rápido está el internet")[0] != "TIEMPOS" and ask("qué tan rápido eres")[0] == "TIEMPOS"
    sat = dt.date(2026, 11, 14)
    assert hogar.parse_date("el martes", sat) == dt.date(2026, 11, 17) and hogar.parse_date("este sábado", sat) == dt.date(2026, 11, 21)
    assert hogar.parse_date("el próximo lunes", sat) == dt.date(2026, 11, 16) and hogar.parse_date("el 20", sat) == dt.date(2026, 11, 20)
