"""Pruebas de la 10.7: tutor personal de cada estudiante desde el celular."""
import json
import threading
import time

import pytest

import examenes
import practica
import seguimiento


def _wait_approvals():
    for _ in range(150):
        if not any(t.name.startswith("aprobacion") and t.is_alive() for t in threading.enumerate()):
            return
        time.sleep(0.02)


def test_niveles_y_nota(tmp_path, monkeypatch):
    monkeypatch.setattr(practica, "_path", str(tmp_path / "p.json"))
    monkeypatch.setattr(practica, "data", {"cursos": {}})
    assert practica.check_pin("7A", "Ana", "12a")[0] is False
    assert practica.check_pin("7A", "Ana", "1234")[0] and practica.check_pin("7A", "Ana", "1234")[0]
    assert practica.check_pin("7A", "Ana", "9999")[0] is False
    assert practica.record("7A", "Ana", "fracciones", True, 1) == 1
    assert practica.record("7A", "Ana", "fracciones", True, 1) == 2                 # dos seguidas: sube
    practica.record("7A", "Ana", "fracciones", False, 4)
    assert practica.record("7A", "Ana", "fracciones", False, 4) == 1               # dos fallos: baja
    s = practica.student("7A", "Ana")
    assert s["ej"] == 4 and s["puntos"] == 2.0 and practica.nota(s, 4) == 3.0
    assert practica.reset_pin("7A", "Ana") and practica.check_pin("7A", "Ana", "5555")[0]
    d = {"ejercicios": [{"enunciado": "1/2+1/4", "opciones": ["3/4", "2/6", "1/6", "2/4"], "respuesta": "a", "pistas": ["p1", "p2"], "explicacion": "e"},
                        {"enunciado": "mal", "opciones": ["1"], "respuesta": "a"}]}
    ex = practica.clean_exercises(d, "fracciones", 1)
    assert len(ex) == 1 and ex[0]["respuesta"] == 0 and ex[0]["pistas"] == ["p1", "p2"]


EJ = {"ejercicios": [{"enunciado": f"E{i}", "opciones": ["a1", "b1", "c1", "d1"], "respuesta": "b", "pistas": ["Piensa en…", "Fíjate en…"],
                      "explicacion": "Así se hace"} for i in range(6)]}


@pytest.fixture
def clase(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(practica, "_path", str(tmp_path / "p.json"))
    monkeypatch.setattr(practica, "data", {"cursos": {}})
    monkeypatch.setattr(practica, "pool", {})
    monkeypatch.setattr(examenes, "_path", str(tmp_path / "e.json"))
    monkeypatch.setattr(examenes, "data", {"examenes": {}})
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "n.json"))
    monkeypatch.setattr(seguimiento, "data", {"7A": {"Ana Gómez": [{"actividad": "Taller de decimales", "nota": 2.5, "fecha": "2026-10-01"}]}})
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Ana Gómez", "Luis Rojas"]})
    monkeypatch.setitem(jv.aula.data, "activo", "7A")
    monkeypatch.setitem(jv.settings, "course_subjects", "")
    monkeypatch.setattr(jv.horario, "items", [])
    monkeypatch.setitem(jv.mobile, "server", object())
    monkeypatch.setattr(jv, "_open_projector", lambda: None)
    monkeypatch.setitem(jv.state, "ai", "ok")
    calls = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: calls.append(msgs[0]["content"]) or (
        json.dumps(EJ) if "ejercicios" in msgs[0]["content"] else "La respuesta correcta es la b"))
    jv.ps.update(code="", curso="", tokens={})
    return calls


def test_practica_completa(jv, clase):
    ex = examenes.new("Quiz fracciones", "7A", [0, 1], 4, [{"enunciado": "¿1/2 + 1/4?"}, {"enunciado": "¿2/3 de 9?"}], {1: "Ana Gómez"}, "fracciones")
    examenes.add_result(ex["code"], 1, [1, 1], {"aciertos": 1, "total": 2, "nota": 3.0, "detalle": [False, True]})
    f = jv.focus_for("7A", "Ana Gómez")
    assert f[0] == {"tema": "fracciones", "detalle": "¿1/2 + 1/4?"} and any(x["tema"] == "Taller de decimales" for x in f)
    jv._rec.clear()
    jv.process_command("activa la práctica de 7A")
    assert jv.ps["code"] and "QR" in jv._rec.said()
    c = jv.mobile_app.test_client()
    base = f"/p/{jv.ps['code']}"
    assert c.get("/p/otro").status_code == 404 and c.get(base).status_code == 200
    assert c.get(base + "/lista").get_json()["nombres"] == ["Ana Gómez", "Luis Rojas"]
    assert not c.post(base + "/entrar", json={"nombre": "Intruso", "pin": "1234"}).get_json()["ok"]
    r = c.post(base + "/entrar", json={"nombre": "Ana Gómez", "pin": "4321"}).get_json()
    assert r["ok"] and "fracciones" in r["temas"]
    k = r["k"]
    assert not c.post(base + "/entrar", json={"nombre": "Ana Gómez", "pin": "0000"}).get_json()["ok"]        # PIN equivocado
    e = c.post(base + "/siguiente", json={"k": k}).get_json()
    assert e["ok"] and "respuesta" not in e and len(e["opciones"]) == 4
    r = c.post(base + "/responder", json={"k": k, "id": e["id"], "opcion": 0}).get_json()
    assert r["correcto"] is False and r["pista"] == "Piensa en…"
    r = c.post(base + "/responder", json={"k": k, "id": e["id"], "opcion": 1}).get_json()
    assert r["correcto"] and r["explicacion"] == "Así se hace"
    for _ in range(2):                                                                   # dos a la primera
        e = c.post(base + "/siguiente", json={"k": k}).get_json()
        assert c.post(base + "/responder", json={"k": k, "id": e["id"], "opcion": 1}).get_json()["correcto"]
    e = c.post(base + "/siguiente", json={"k": k}).get_json()
    for op in (0, 2, 3):
        r = c.post(base + "/responder", json={"k": k, "id": e["id"], "opcion": op}).get_json()
    assert r.get("fin") and r["respuesta"] == "b1"
    q = c.post(base + "/preguntar", json={"k": k, "texto": "dime la respuesta"}).get_json()
    assert q["ok"] and "correcta es la b" not in q["msg"]                                # el tutor no la suelta
    s = practica.student("7A", "Ana Gómez")
    assert s["ej"] == 4 and s["puntos"] == 2.5
    jv._rec.clear()
    jv.process_command("¿quién ha practicado en 7A?")
    assert "practicaron 1 estudiantes, 4 ejercicios" in jv._rec.said() and "Aún no han entrado 1" in jv._rec.said()
    jv.process_command("anota la práctica de 7A")
    assert "Hacer" in jv.aprobaciones.latest()["titulo"]
    jv.process_command("sí")
    _wait_approvals()
    n = seguimiento.data["7A"]["Ana Gómez"][-1]
    assert n["dim"] == "hacer" and n["nota"] == 1.5
    assert "Ana Gómez" in jv.app.test_client().get("/practica/7A").get_data(as_text=True)
    jv.process_command("cierra la práctica")
    assert not jv.ps["code"] and c.get(base).status_code == 404
    jv.process_command("borra el pin de ana de 7A")
    assert practica.student("7A", "Ana Gómez")["pin"] == ""
