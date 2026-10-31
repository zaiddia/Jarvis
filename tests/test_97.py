"""Pruebas de la 9.7: alertas tempranas por tendencia, ficha del estudiante en el HUD y celebraciones."""
import datetime
import threading
import time

import pytest

import compromisos
import informes
import seguimiento
import tendencias

HOY = datetime.date(2026, 10, 28)                      # miércoles


def _n(nota, dia):
    return {"actividad": f"act {dia}", "nota": nota, "fecha": f"2026-10-{dia:02d}", "origen": "voz"}


def _wait_approvals():
    for _ in range(100):
        if not any(t.name.startswith("aprobacion") and t.is_alive() for t in threading.enumerate()):
            return
        time.sleep(0.02)


@pytest.fixture
def curso(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "notas.json"))
    monkeypatch.setattr(seguimiento, "data", {"7A": {
        "Ana Gómez": [_n(4.5, 1), _n(4.2, 5), _n(4.4, 9), _n(3.0, 20), _n(2.8, 26)],      # viene bajando
        "Luis Rojas": [_n(2.8, 1), _n(3.0, 5), _n(3.1, 9), _n(4.2, 20), _n(4.4, 26)],     # mejoró
        "Eva Díaz": [_n(4.0, 1), _n(4.1, 5), _n(3.9, 9), _n(4.0, 20)]}})                   # estable
    monkeypatch.setattr(informes, "_path", str(tmp_path / "obs.json"))
    monkeypatch.setattr(informes, "data", {})
    monkeypatch.setattr(compromisos, "_path", str(tmp_path / "c.json"))
    monkeypatch.setattr(compromisos, "data", {"items": [], "respondidos": [], "descartados": []})
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Ana Gómez", "Luis Rojas", "Eva Díaz"]})
    monkeypatch.setitem(jv.aula.data, "asistencia", {"7A": {"2026-10-26": ["Eva Díaz"], "2026-10-27": ["Eva Díaz"]}})
    jv._seen["keys"].clear()
    return tmp_path


def test_tendencias_puras():
    assert tendencias.grade_trend([_n(4.5, 1), _n(4.2, 5), _n(4.4, 9), _n(3.0, 20), _n(2.8, 26)])[0] == "baja"
    assert tendencias.grade_trend([_n(2.8, 1), _n(3.0, 5), _n(3.1, 9), _n(4.2, 20), _n(4.4, 26)])[0] == "mejora"
    assert tendencias.grade_trend([_n(4.0, 1), _n(4.1, 5), _n(3.9, 9)]) is None          # pocas notas
    assert "última semana" in tendencias.absence_trend(["2026-10-26", "2026-10-27"], HOY)[1]
    lunes = ["2026-09-07", "2026-09-21", "2026-10-05"]
    assert "lunes" in tendencias.absence_trend(lunes, HOY)[1]
    assert tendencias.absence_trend(["2026-10-01"], HOY) is None


def test_alertas_por_voz(jv, curso, monkeypatch):
    orig = jv.early_alerts
    monkeypatch.setattr(jv, "early_alerts", lambda today=None: orig(HOY))
    jv._rec.clear()
    jv.process_command("¿quién viene bajando?")
    s = jv._rec.said()
    assert "Ana Gómez" in s and "Eva Díaz" in s and "Para felicitar" in s and "Luis Rojas" in s
    jv._rec.clear()
    jv.process_command("¿a quién debo felicitar?")
    s = jv._rec.said()
    assert "Luis Rojas" in s and "Ana Gómez" not in s


def test_aviso_diario_y_felicitacion(jv, curso, monkeypatch):
    monkeypatch.setitem(jv.settings, "early_last", "")
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    notices = []
    monkeypatch.setattr(jv, "notice_add", lambda text, kind="info", origin="": notices.append(text))
    tarde = datetime.datetime(2026, 10, 28, 15, 30)
    new = jv.early_tick(tarde)
    assert {a["estudiante"] for a in new} == {"Ana Gómez", "Luis Rojas", "Eva Díaz"}
    assert notices and "Ana Gómez" in notices[0] and "Luis Rojas" not in notices[0]
    a = jv.aprobaciones.latest()
    assert a["titulo"].startswith("Felicitar a Luis Rojas")
    jv.process_command("sí")
    _wait_approvals()
    e = informes.entries("7A", "Luis Rojas")
    assert e and e[-1]["tipo"] == "positiva" and e[-1]["texto"].startswith("Felicitación")
    assert jv.early_tick(tarde) == []                   # una vez al día
    monkeypatch.setitem(jv.settings, "early_last", "")
    assert jv.early_tick(tarde) == []                   # y no repite lo ya avisado


def test_ficha_del_estudiante(jv, curso, monkeypatch):
    events = []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: events.append((ev, data)))
    informes.add("7A", "Ana Gómez", "No entregó el taller")
    compromisos.add("llamar a la mamá de Ana el viernes")
    jv._rec.clear()
    jv.process_command("muéstrame a Ana de 7A")
    c = [d for e, d in events if e == "student_card"][-1]
    assert c["nombre"] == "Ana Gómez" and c["curso"] == "7A" and len(c["notas"]) == 5
    assert c["observador"][-1]["x"].startswith("No entregó") and c["compromisos"]
    assert "promedio" in jv._rec.said() and "HUD" in jv._rec.said()
    jv.process_command("ficha de eva díaz de 7A")
    c = [d for e, d in events if e == "student_card"][-1]
    assert c["nombre"] == "Eva Díaz" and c["fallas"] == 2


def test_muestrame_no_estudiante_sigue_de_largo(jv, curso):
    assert jv.card_voice("muéstrame a qué hora es la reunión", "muestrame a que hora es la reunion") is False
    assert jv.card_voice("muéstrame el calendario", "muestrame el calendario") is False


def test_atencion_incluye_tendencias(jv, curso, monkeypatch):
    monkeypatch.setattr(jv, "early_alerts", lambda today=None: [
        {"k": "baja:7A:Ana Gómez:5", "curso": "7A", "estudiante": "Ana Gómez", "tipo": "baja", "detalle": "venía en 4,4"}])
    items = jv.attention_items(datetime.datetime(2026, 10, 28, 10, 0))
    assert any(x["k"].startswith("ea:") and "Ana Gómez" in x["t"] for x in items)
