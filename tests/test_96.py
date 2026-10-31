"""Pruebas de la 9.6: clase en vivo, ticket de salida y semáforo con el celular, y el banco de actividades que aprende."""
import json
import time

import pytest

import clasevivo
import diarioclase
import ticket

PLAN = {"tema": "Fracciones equivalentes", "titulo": "Plan", "objetivo": "Reconocer fracciones equivalentes", "momentos": [
    {"nombre": "Inicio", "duracion": "10 min", "actividades": "Pregunta: ¿Es lo mismo media pizza que dos cuartos? Lluvia de ideas."},
    {"nombre": "Desarrollo", "duracion": "30 minutos", "actividades": "Tiras de papel: construir 1/2, 2/4 y 4/8."},
    {"nombre": "Cierre", "duracion": "10 min", "actividades": "Socialización."}]}


@pytest.fixture
def aula7a(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(clasevivo, "_path", str(tmp_path / "clases.json"))
    monkeypatch.setattr(clasevivo, "data", {"planes": [], "actividades": []})
    monkeypatch.setattr(diarioclase, "_path", str(tmp_path / "r.json"))
    monkeypatch.setattr(diarioclase, "data", {"registro": {}, "mallas": {}})
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Ana Gómez", "Luis Rojas"]})
    monkeypatch.setitem(jv.aula.data, "activo", "7A")
    monkeypatch.setattr(jv, "_open_projector", lambda: None)
    jv.live_class["on"] = False
    if ticket.state["open"]:
        ticket.close()
    return tmp_path


def test_partes_del_plan():
    st = clasevivo.steps(PLAN)
    assert [s["min"] for s in st] == [10, 30, 10]
    assert clasevivo.hook_question(PLAN) == "¿Es lo mismo media pizza que dos cuartos?"
    assert clasevivo.hook_question({"tema": "volcanes"}).startswith("¿Qué sabes sobre volcanes?")


def test_clase_en_vivo(jv, aula7a, monkeypatch):
    events = []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: events.append((ev, data)))
    clasevivo.remember_plan(PLAN, "7A")
    jv._rec.clear()
    jv.process_command("empieza la clase de fracciones equivalentes")
    assert jv.live_class["on"] and "3 momentos" in jv._rec.said()
    ev = [d for e, d in events if e == "live_class"][-1]
    assert ev["nombre"] == "Inicio" and ev["hook"].startswith("¿Es lo mismo") and 590 <= ev["left"] <= 600
    jv.process_command("dame 5 minutos más")
    assert [d for e, d in events if e == "live_class"][-1]["left"] > 850
    jv.process_command("siguiente momento")
    assert [d for e, d in events if e == "live_class"][-1]["nombre"] == "Desarrollo"
    assert any(s["cmd"] == "siguiente momento" for s in jv.dashboard()["sugerencias"])
    jv._rec.clear()
    jv.process_command("termina la clase")
    assert not jv.live_class["on"] and "diario de clase" in jv._rec.said()
    assert diarioclase.entries("7A")[-1]["tema"] == "Fracciones equivalentes"


def test_clase_sin_plan_lo_prepara(jv, aula7a, monkeypatch):
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps(PLAN))
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="x": fn())
    jv.process_command("empieza la clase de volcanes en 7A")
    assert jv.live_class["on"] and clasevivo.data["planes"]
    jv.live_class["on"] = False


def test_ticket_de_salida(jv, aula7a, monkeypatch):
    events = []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: events.append((ev, data)))
    monkeypatch.setitem(jv.mobile, "server", object())                 # el panel del celular está encendido
    monkeypatch.setattr(jv, "lan_ip", lambda: "192.168.1.20")
    jv.remember_quiz({"titulo": "q", "preguntas": [
        {"enunciado": "¿2/4 = 1/2?", "opciones": ["Sí", "No", "A veces", "Nunca"], "respuesta": "a"},
        {"enunciado": "¿1/3 = 2/6?", "opciones": ["No", "Sí", "A veces", "Nunca"], "respuesta": "b"}]})
    jv.live_class.update(on=False, plan=PLAN, steps=clasevivo.steps(PLAN), tema="Fracciones equivalentes", curso="7A")
    jv.process_command("lanza el ticket de salida")
    assert ticket.state["open"] and len(ticket.state["preguntas"]) == 2
    code = ticket.state["code"]
    c = jv.mobile_app.test_client()
    assert c.get(f"/t/{code}").status_code == 200 and c.get("/t/otro").status_code == 404
    pub = c.get(f"/t/{code}/datos").get_json()
    assert "respuesta" not in json.dumps(pub)                          # el estudiante no ve las respuestas
    assert c.post(f"/t/{code}/enviar", json={"nombre": "Ana Gómez", "respuestas": [0, 1]}).get_json()["ok"]
    assert c.post(f"/t/{code}/enviar", json={"nombre": "Luis Rojas", "respuestas": [1, 0]}).get_json()["ok"]
    assert not c.post(f"/t/{code}/enviar", json={"nombre": "X", "respuestas": [0]}).get_json()["ok"]
    if __import__("importlib").util.find_spec("qrcode"):
        assert jv.app.test_client().get("/ticket-qr.png").mimetype == "image/png"
    jv._rec.clear()
    jv.process_command("cierra el ticket")
    said = jv._rec.said()
    assert "Respondieron 2, con 50 % de aciertos" in said and "Necesitan refuerzo: Luis Rojas" in said
    assert clasevivo.data["actividades"][-1]["resultado"] == 50                      # el banco de actividades aprende
    assert c.get(f"/t/{code}/datos").status_code == 404                               # cerrado


def test_semaforo_y_actividades(jv, aula7a, monkeypatch):
    monkeypatch.setitem(jv.mobile, "server", object())
    monkeypatch.setattr(jv, "lan_ip", lambda: "192.168.1.20")
    jv.live_class.update(on=False, plan=PLAN, steps=clasevivo.steps(PLAN), tema="Fracciones equivalentes", curso="7A")
    jv.process_command("semáforo de comprensión")
    code = ticket.state["code"]
    for i, (n, r) in enumerate((("Ana", 0), ("Luis", 0), ("Sara", 0), ("Pedro", 1))):
        ok, _ = ticket.submit(code, n, [r], f"ip{i}")
        assert ok
    jv._rec.clear()
    jv.process_command("cierra el semáforo")
    assert "75 % lo entendió bien" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("¿qué actividades funcionaron en fracciones?")
    assert "Tiras de papel" in jv._rec.said() and "75 %" in jv._rec.said()
    assert "Tiras de papel" in clasevivo.worked_ctx("fracciones equivalentes")


def test_ticket_limites():
    code = ticket.open_ticket([{"enunciado": "¿?", "opciones": ["a", "b"], "respuesta": 0}])
    for i in range(3):
        assert ticket.submit(code, f"Nombre {i}", [0], "1.1.1.1")[0]
    assert not ticket.submit(code, "Otro", [0], "1.1.1.1")[0]                       # máximo 3 por celular
    assert ticket.submit(code, "Nombre 0", [1], "1.1.1.1")[0]                        # puede corregir el suyo
    ticket.close()
    assert not ticket.submit(code, "Tarde", [0], "2.2.2.2")[0]
