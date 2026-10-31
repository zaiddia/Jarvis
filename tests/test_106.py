"""Pruebas de la 10.6: programa Saber 11 y Saber 9."""
import json
import os
import threading
import time

import pytest

import examenes
import saber
import seguimiento
import ticket


def _wait_approvals():
    for _ in range(150):
        if not any(t.name.startswith("aprobacion") and t.is_alive() for t in threading.enumerate()):
            return
        time.sleep(0.02)


def test_competencias_y_perfil(tmp_path, monkeypatch):
    monkeypatch.setattr(saber, "_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(saber, "data", {"cursos": {}})
    assert saber.level_of(11) == 11 and saber.level_of(10) == 11 and saber.level_of(7) == 9
    assert saber.canonical("formulación", 11) == "Formulación y ejecución"
    assert saber.canonical("razonamiento", 9) == "Razonamiento y argumentación"
    comps = ["interpretación", "formulación", "argumentación", "interpretación"]
    saber.add_session("11A", 11, "S1", "hoja", comps, {"Ana": [True, False, False, True], "Luis": [False, False, True, True]})
    saber.add_session("11A", 11, "S2", "celular", comps, {"Ana": [True, True, False, True], "Luis": [True, True, True, True]})
    evo = saber.evolution("11A")
    assert evo[0]["comp"]["Formulación y ejecución"] == 0 and evo[1]["comp"]["Formulación y ejecución"] == 100
    p = saber.profile("11A")
    assert p["Ana"]["Argumentación"] == 0 and saber.weakest(p["Ana"]) == "Argumentación"
    s = saber.spoken("11A")
    assert "Formulación y ejecución: 100 % (+100 desde el primero)" in s and "Argumentación" in s
    svg, legend = saber.chart_svg(evo, 11)
    assert svg.startswith("<svg") and "polyline" in svg and "Argumentación" in legend


SIM = {"titulo": "Simulacro Saber 11", "tema": "mixto", "instrucciones": "x", "preguntas": [
    {"contexto": "Una tienda…", "enunciado": f"P{i}", "opciones": ["1", "2", "3", "4"], "respuesta": "abcd"[i % 4],
     "competencia": ["interpretación y representación", "formulación", "argumentación"][i % 3], "explicacion": "e"} for i in range(6)]}


@pytest.fixture
def once(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(saber, "_path", str(tmp_path / "s.json"))
    monkeypatch.setattr(saber, "data", {"cursos": {}})
    monkeypatch.setattr(examenes, "_path", str(tmp_path / "e.json"))
    monkeypatch.setattr(examenes, "data", {"examenes": {}})
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "n.json"))
    monkeypatch.setattr(seguimiento, "data", {})
    monkeypatch.setitem(jv.aula.data, "cursos", {"11A": ["Ana Gómez", "Luis Rojas"]})
    monkeypatch.setitem(jv.aula.data, "activo", "11A")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "out"))
    monkeypatch.setitem(jv.settings, "course_subjects", "")
    monkeypatch.setattr(jv.horario, "items", [])
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    monkeypatch.setattr(jv, "_open_projector", lambda: None)
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv.banco, "add_quiz", lambda m: 0)
    jv.sess.update(code=None, token="")
    return tmp_path


def test_simulacro_con_hoja_y_al_programa(jv, once, monkeypatch):
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps(SIM))
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    jv._rec.clear()
    jv.process_command("haz un simulacro saber de 6 preguntas para 11A")
    s = jv._rec.said()
    assert "Saber 11" in s and "hojas de respuesta de 11A" in s
    ex = examenes.latest()
    assert ex["tipo"] == "saber" and ex["preguntas"][1]["competencia"] == "Formulación y ejecución"
    files = [f for _, _, fs in os.walk(jv.settings["output_dir"]) for f in fs]
    assert any(f.endswith(".pdf") for f in files) and any(f.endswith(".docx") for f in files)
    import omr
    g = omr.grade([0, 1, 2, 3, 0, 1], ex["clave"])
    examenes.add_result(ex["code"], 1, [0, 1, 2, 3, 0, 1], g)
    examenes.add_result(ex["code"], 2, [0, 0, 0, 0, 0, 0], omr.grade([0, 0, 0, 0, 0, 0], ex["clave"]))
    jv.sess["code"] = ex["code"]
    jv.close_grading()
    jv.process_command("no")                                                    # no anota las notas (deja limpia la lista)
    _wait_approvals()
    assert saber.evolution("11A")[0]["comp"]["Interpretación y representación"] == 75
    jv._rec.clear()
    monkeypatch.setattr(jv.webbrowser if hasattr(jv, "webbrowser") else __import__("webbrowser"), "open", lambda *a, **k: None)
    jv.process_command("¿cómo va 11A en el saber?")
    assert "Saber 11, 1 simulacro" in jv._rec.said()
    page = jv.app.test_client().get("/saber/11A").get_data(as_text=True)
    assert "Preparación Saber 11" in page and "Luis Rojas" in page
    jv.process_command("haz el informe saber de 11A")
    assert any(f.startswith("Informe Saber 11") for _, _, fs in os.walk(jv.settings["output_dir"]) for f in fs)
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps({"competencias": [
        {"nombre": c, "que_evalua": "q", "estrategias": ["s"], "practica": [{"contexto": "c", "enunciado": "e", "opciones": ["1", "2", "3", "4"], "respuesta": "a"}]}
        for c in saber.COMP[11]]}))
    path = jv.saber_plans("11A")
    from docx import Document
    txt = "\n".join(p.text for p in Document(path).paragraphs)
    assert "Para: Luis Rojas" in txt and "Formulación y ejecución" in txt


def test_mini_simulacro_en_el_celular(jv, once, monkeypatch):
    monkeypatch.setitem(jv.mobile, "server", object())
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps(SIM))
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    if ticket.state["open"]:
        ticket.close()
    jv.process_command("lanza el mini simulacro de 11A")
    assert ticket.state["open"] and ticket.state["tipo"] == "saber" and len(ticket.state["preguntas"]) == 5
    code = ticket.state["code"]
    ok, _ = ticket.submit(code, "ana gomez", [q["respuesta"] for q in ticket.state["preguntas"]], "1")
    assert ok
    jv.process_command("cierra el ticket")
    evo = saber.evolution("11A")
    assert evo and evo[0]["fuente"] == "celular" and "Ana Gómez" in saber.profile("11A")
