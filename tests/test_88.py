"""Pruebas de la 8.8: planes de recuperación, diario de clase y quiz en vivo en el proyector."""
import datetime
import json
import time

import pytest

import diarioclase
import horario
import informes
import recuperacion
import seguimiento

QUIZ = {"titulo": "Repaso", "preguntas": [{"enunciado": "¿2+2?", "opciones": ["3", "4", "5", "6"], "respuesta": "b", "explicacion": "Suma."},
                                          {"enunciado": "¿3·3?", "opciones": ["6", "9", "12", "3"], "respuesta": "b", "explicacion": ""}]}


@pytest.fixture
def curso(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Juan Pérez", "Ana Gómez"]})
    monkeypatch.setitem(jv.aula.data, "activo", "7A")
    monkeypatch.setitem(jv.aula.data, "asistencia", {})
    monkeypatch.setattr(seguimiento, "data", {"7A": {"Juan Pérez": [{"actividad": "Quiz fracciones", "nota": 2.0, "fecha": "2026-10-01"},
                                                                     {"actividad": "Taller decimales", "nota": 2.6, "fecha": "2026-10-08"}],
                                                      "Ana Gómez": [{"actividad": "Quiz fracciones", "nota": 4.5, "fecha": "2026-10-01"}]}})
    monkeypatch.setattr(informes, "data", {})
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    monkeypatch.setattr(diarioclase, "_path", str(tmp_path / "registro.json"))
    monkeypatch.setattr(diarioclase, "data", {"registro": {}, "mallas": {}})
    monkeypatch.setattr(horario, "items", [])
    return tmp_path


def test_plan_de_recuperacion(jv, curso, monkeypatch):
    if jv.Document is None:
        pytest.skip("sin python-docx")
    seen = []

    def ai(msgs, **k):
        seen.append(msgs[0]["content"])
        return json.dumps({"planes": [{"id": 0, "temas": ["Fracciones"], "actividades": [
            {"titulo": "Guía de fracciones", "descripcion": "Resuelve 10 ejercicios", "entrega": "La guía resuelta"}],
            "valoracion": "Cada ejercicio vale…", "familia": "Revise el cuaderno."}]})
    monkeypatch.setattr(jv, "ai_chat", ai)
    said = []
    monkeypatch.setattr(jv, "notify", lambda text, origin="JARVIS": said.append(text))
    jv._tl.capture = []
    try:
        jv.process_command("haz los planes de recuperación de 7A")
    finally:
        jv._tl.capture = None
    assert "Juan Pérez" in seen[0] and "Ana Gómez" not in seen[0] and "Quiz fracciones (2.0)" in seen[0]   # solo los que están en riesgo
    assert "1 plan de recuperación" in said[-1]
    path = next((curso / "Planes de recuperación").iterdir())
    text = " ".join(p.text for p in jv.Document(str(path)).paragraphs)
    assert "Plan de recuperación · Juan Pérez" in text and "Señor(a) acudiente" in text and "Firma del acudiente" in text


def test_recuperacion_valida():
    assert recuperacion.validate({"planes": [{"id": 0, "actividades": [{"titulo": "A"}]}, {"id": 3, "actividades": [{"titulo": "B"}]},
                                             {"id": 1, "actividades": []}]}, 2) == \
        {0: {"temas": [], "actividades": [{"titulo": "A", "descripcion": "", "entrega": ""}], "valoracion": "", "familia": ""}}


def test_diario_de_clase_y_malla(jv, curso):
    diarioclase.set_malla("7A", {"titulo": "Malla", "semanas": [{"semana": 1, "tema": "Fracciones equivalentes"},
                                                               {"semana": 2, "tema": "Suma de fracciones heterogéneas"},
                                                               {"semana": 3, "tema": "Números decimales"}]})
    rec = jv._rec
    rec.clear()
    jv.process_command("hoy en 7A vimos fracciones equivalentes con material concreto")
    assert "Anotado en el diario de 7A" in rec.said() and "van 1 de 3" in rec.said()
    assert diarioclase.entries("7A")[0]["tema"].startswith("Fracciones equivalentes")
    rec.clear()
    jv.process_command("¿qué temas me faltan del periodo en 7A?")
    assert "Faltan: semana 2, Suma de fracciones heterogéneas; semana 3, Números decimales" in rec.said()
    rec.clear()
    jv.process_command("¿qué vimos en 7A?")
    assert "Fracciones equivalentes" in rec.said()
    rec.clear()
    jv.process_command("exporta el registro de clase de 7A")
    assert list((curso / "Exportaciones").glob("Registro de clase 7A*.xlsx"))


def test_diario_usa_la_clase_de_ahora(jv, curso, monkeypatch):
    now = datetime.datetime.now()
    monkeypatch.setattr(horario, "now_class", lambda at=None: {"dia": now.weekday(), "inicio": "00:00", "fin": "23:59", "curso": "7A", "materia": "M"})
    jv._rec.clear()
    jv.process_command("hoy vimos los números decimales")
    assert "diario de 7A" in jv._rec.said()


def test_quiz_en_vivo(jv, monkeypatch):
    opened, events = [], []
    monkeypatch.setattr(jv, "_open_projector", lambda: opened.append(1))
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: events.append((ev, data)))
    jv.remember_quiz(QUIZ)
    jv._rec.clear()
    jv.process_command("quiz en vivo")
    assert opened and jv.live_quiz["on"] and "2 preguntas" in jv._rec.said()
    ev = [d for e, d in events if e == "live_quiz"][-1]
    assert ev["n"] == 1 and ev["correcta"] == -1 and ev["opciones"] == ["3", "4", "5", "6"]        # sin revelar la respuesta
    jv.process_command("siguiente")                                     # primero muestra la respuesta
    ev = [d for e, d in events if e == "live_quiz"][-1]
    assert ev["phase"] == "respuesta" and ev["correcta"] == 1 and ev["explicacion"] == "Suma."
    jv.process_command("siguiente")
    assert [d for e, d in events if e == "live_quiz"][-1]["n"] == 2
    jv.live_quiz["until"] = time.time() - 1                             # se acabó el tiempo: respuesta sola
    jv.live_step("answer")
    jv._rec.clear()
    jv.process_command("siguiente")
    assert not jv.live_quiz["on"] and "Terminamos" in jv._rec.said()
    assert jv.dashboard()["sugerencias"][0]["cmd"] != "respuesta"


def test_siguiente_sin_quiz_no_se_confunde(jv):
    jv.live_quiz["on"] = False
    assert jv.live_quiz_voice("siguiente", "siguiente") is False
