"""Pruebas de la 9.4: lecciones de tus correcciones, vigilante de páginas web y modo tutor socrático."""
import json
import threading
import time

import pytest

import lecciones
import paginas


@pytest.fixture
def limpio(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(lecciones, "_path", str(tmp_path / "l.json"))
    monkeypatch.setattr(lecciones, "items", [])
    monkeypatch.setattr(paginas, "_path", str(tmp_path / "p.json"))
    monkeypatch.setattr(paginas, "items", [])
    for a in jv.aprobaciones.pending():
        jv.resolve_approval(a["id"], False, "prueba")
    return tmp_path


def test_reglas_que_dices(jv, limpio):
    jv._rec.clear()
    jv.process_command("de ahora en adelante los quices con 5 preguntas")
    assert "lo tendré en cuenta" in jv._rec.said()
    jv.process_command("cuando digo 7A me refiero a matemáticas de séptimo A")
    assert len(lecciones.items) == 2
    ctx = jv.lessons_ctx()
    assert "quices con 5 preguntas" in ctx and "7A me refiero" in ctx
    jv._rec.clear()
    jv.process_command("¿qué lecciones tienes?")
    assert "2 lecciones" in jv._rec.said()
    jv.process_command("olvida la lección de los quices")
    assert len(lecciones.items) == 1


def test_leccion_va_a_la_ia_y_al_material(jv, limpio, monkeypatch):
    lecciones.add("Nunca uses la palabra alumnos")
    import nucleo.ia as ia
    src = open(ia.__file__, encoding="utf-8").read()
    assert src.count("J.lessons_ctx()") == 2
    assert "Nunca uses la palabra alumnos" in jv.lessons_ctx()


def test_correccion_propone_leccion(jv, limpio, monkeypatch):
    monkeypatch.setattr(jv, "chat_buffer", __import__("collections").deque([
        {"role": "user", "text": "haz un quiz de fracciones"}, {"role": "jarvis", "text": "Listo: quiz de 20 preguntas."},
        {"role": "user", "text": "no, me refería a 5 preguntas"}], maxlen=50))
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps({"leccion": "Haz los quices de 5 preguntas si no te dicen cuántas"}))
    started = []
    real = threading.Thread

    class T(real):
        def start(self):
            started.append(self)
            self.run()
    monkeypatch.setattr(threading, "Thread", T)
    assert jv.lessons_voice("no, me refería a 5 preguntas", "no me referia a 5 preguntas") is False   # la orden se atiende igual
    monkeypatch.setattr(threading, "Thread", real)
    a = jv.aprobaciones.latest()
    assert a and a["titulo"].startswith("Aprender: Haz los quices de 5 preguntas")
    jv.process_command("sí")
    for _ in range(100):
        if lecciones.items and not any(t.name.startswith("aprobacion") and t.is_alive() for t in threading.enumerate()):
            break
        time.sleep(0.02)
    assert lecciones.items and lecciones.items[0]["origen"] == "corrección"


def test_vigilante_de_paginas(jv, limpio, monkeypatch):
    pages = {"v": "<html><body><p>Circular 012: inscripciones abiertas hasta el viernes para docentes.</p>"
                  "<p>Bienvenidos al portal de la Secretaría de Educación del departamento.</p></body></html>"}
    monkeypatch.setattr(jv, "_get_text", lambda url, timeout=12: pages["v"])
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="x": fn())
    alerts = []
    monkeypatch.setattr(jv, "alert", lambda text, origin="JARVIS": alerts.append(text))
    monkeypatch.setitem(jv.state, "ai", "off")
    jv._rec.clear()
    jv.process_command("avísame cuando publiquen algo nuevo en https://sed.ejemplo.gov.co/circulares")
    assert "vigilo" in jv._rec.said() and len(paginas.items) == 1 and paginas.items[0]["lineas"]
    it = paginas.items[0]
    assert jv.watch_check(it) == "" and not alerts                                    # sin cambios
    pages["v"] = pages["v"].replace("</body>", "<p>Circular 013: nueva jornada de capacitación en inteligencia artificial el 20 de noviembre.</p></body>")
    msg = jv.watch_check(it)
    assert "Circular 013" in msg and alerts
    pages["v"] = pages["v"].replace("012", "014")                                       # solo cambian números: no avisa
    alerts.clear()
    assert jv.watch_check(it) == "" and not alerts
    jv._rec.clear()
    jv.process_command("¿qué páginas estás vigilando?")
    assert "1 página" in jv._rec.said()
    jv.process_command("deja de vigilar la página de sed.ejemplo")
    assert paginas.items == []


def test_modo_tutor(jv, monkeypatch):
    events = []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: events.append((ev, data)))
    jv._rec.clear()
    jv.process_command("activa el modo tutor de matemáticas para séptimo")
    assert jv.tutor["on"] and jv.tutor["materia"] == "matematicas" and "septimo" in jv.tutor["grado"]
    assert "NUNCA des la respuesta" in jv.tutor_ctx() and "de matematicas" in jv.tutor_ctx()
    jv.tutor_relay({"role": "user", "text": "¿cuánto es 3/4 + 1/4?"})
    assert events[-1][0] == "tutor_msg"
    jv.process_command("desactiva el modo tutor")
    assert not jv.tutor["on"] and jv.tutor_ctx() == ""
