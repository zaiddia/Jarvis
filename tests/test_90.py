"""Pruebas de la 9.0: HUD expandido, segunda vuelta (trabajos en segundo plano, panel «Hoy» más útil y la página)."""
import datetime
import os
import threading

import horario
import notas


def test_trabajos_en_segundo_plano(jv, monkeypatch):
    events = []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: events.append((ev, data)))
    monkeypatch.setitem(jv.project_run, "busy", False)
    go = threading.Event()
    t = jv.start_job("Preparando material de clase", lambda: go.wait(5), "x")
    assert any(j["t"] == "Preparando material de clase" for j in jv.jobs_list())
    assert events[-1][0] == "jobs" and events[-1][1]["jobs"][0]["t"] == "Preparando material de clase"
    go.set()
    t.join(2)
    assert not any(j["t"] == "Preparando material de clase" for j in jv.jobs_list())
    assert events[-1][1]["jobs"] == [] or all(j["t"] != "Preparando material de clase" for j in events[-1][1]["jobs"])


def test_trabajo_que_falla_no_queda_colgado(jv):
    def boom():
        raise RuntimeError("x")
    t = jv.start_job("Algo que falla", boom, "y")
    t.join(2)
    assert not any(j["t"] == "Algo que falla" for j in jv.jobs_list())


def test_panel_hoy_mas_util(jv, monkeypatch):
    monkeypatch.setattr(horario, "items", [{"dia": 4, "inicio": "07:00", "fin": "08:00", "curso": "7A", "materia": "M"}])
    monkeypatch.setattr(jv, "_weather_short", lambda: "")
    monkeypatch.setattr(notas, "pending", lambda: [{"id": "n1", "texto": "calificar talleres", "fecha": "", "hora": ""}])
    d = jv.dashboard(datetime.datetime(2026, 10, 30, 7, 15))
    assert d["clase"]["progreso"] == 0.25
    assert d["pendientes"] == [{"id": "n1", "t": "calificar talleres"}]
    assert "trabajos" in d


def test_las_tareas_lentas_se_ven_en_el_hud():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for f in ("clase.py", "aulaconecta.py", "familia.py", "aulavivo.py", "alcance.py", "gintegra.py", "herramientas.py"):
        src = open(os.path.join(here, "nucleo", f), encoding="utf-8").read()
        assert "J.start_job(" in src, f


def test_pagina_del_hud():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html = open(os.path.join(here, "templates", "hud.html"), encoding="utf-8").read()
    js = open(os.path.join(here, "static", "js", "hud.js"), encoding="utf-8").read()
    assert 'id="jobs"' in html and 'id="btn-dash"' in html and 'id="log-q"' in html
    for name in ("function md(", "showTyping", "renderJobs", "remember(", "applyLogFilter", "review_upload", "addReviewCard", "hud-collapsed"):
        assert name in js, name
    assert "innerHTML = md(" in js and "function esc(" in js          # el formato se aplica sobre texto escapado


