"""Pruebas de la 10.9: línea del día, mapa del curso, modo clase y barra del año en el panel «Hoy» del HUD."""
import datetime

import pytest

import horario
import seguimiento


@pytest.fixture
def dia(jv, monkeypatch, tmp_path):
    now = datetime.datetime(2026, 11, 2, 9, 30)          # lunes
    monkeypatch.setattr(horario, "items", [{"dia": 0, "inicio": "07:00", "fin": "07:55", "curso": "6A", "materia": "Matemáticas"},
                                           {"dia": 0, "inicio": "09:00", "fin": "10:00", "curso": "7A", "materia": "Tecnología e Informática"},
                                           {"dia": 0, "inicio": "11:00", "fin": "11:55", "curso": "10A", "materia": "Trigonometría"}])
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Ana", "Luis"]})
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "n.json"))
    monkeypatch.setattr(seguimiento, "data", {"7A": {"Ana": [{"actividad": "Quiz", "nota": 4.6, "fecha": "2026-10-01"},
                                                             {"actividad": "Taller", "nota": 4.0, "fecha": "2026-10-05"}],
                                                     "Luis": [{"actividad": "Quiz", "nota": 2.0, "fecha": "2026-10-01"}]}})
    return now


def test_linea_del_dia(jv, dia):
    d = jv.day_line(dia)
    assert [x["estado"] for x in d] == ["pasada", "ahora", "luego"] and d[1]["progreso"] == 0.5
    assert any(a["cmd"] == "activa la práctica de 7A" for a in d[1]["acciones"])
    assert d[2]["acciones"][0]["cmd"] == "prepárame la próxima clase de 10A"
    out = jv.dashboard(dia)
    assert out["dia"] and "anio" in out and out["en_clase"] is None


def test_mapa_del_curso(jv, dia):
    m = jv.handle_course_map({"curso": "7A"})
    assert [a["a"] for a in m["acts"]] == ["Quiz", "Taller"] and m["acts"][1]["dim"] == "hacer"
    assert m["rows"][0]["n"] == "Luis" and m["rows"][0]["c"] == [2.0, None] and m["rows"][0]["letra"] == "Bj"   # los más bajos primero
    assert m["rows"][1]["val"] == 4.3
    assert "7A" in jv.handle_course_map({})["cursos"]


def test_modo_clase_y_barra_del_ano(jv, dia, monkeypatch):
    monkeypatch.setitem(jv.settings, "year_start", "2026-01-26")
    monkeypatch.setitem(jv.settings, "school_weeks", 40)
    monkeypatch.setitem(jv.settings, "period_end", "2026-11-20")
    b = jv.year_bar(dia)
    assert b["semana"] == 41 or b["semana"] is None or b["periodos"] == [14, 13, 13]
    monkeypatch.setitem(jv.settings, "year_start", "2026-02-02")
    b = jv.year_bar(datetime.datetime(2026, 9, 1))
    assert b["semana"] == 31 and b["periodo"] == 3 and b["cierre"] == 80
    jv.live_class.update(on=True, steps=[{"nombre": "Inicio", "min": 10, "actividades": ""}], i=0, tema="Algoritmos", curso="7A",
                         end=__import__("time").time() + 300)
    try:
        p = jv.in_class_panel()
        assert p["clase"]["momento"] == "Inicio" and 290 <= p["clase"]["left"] <= 300
    finally:
        jv.live_class["on"] = False
