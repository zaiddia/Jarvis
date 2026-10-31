"""Pruebas de la 10.8: la planeación del año completo, alineada a los DBA, que alimenta el diario y avisa si vas atrasado."""
import datetime
import json
import os

import pytest

import anual
import diarioclase
import horario


def test_semanas_y_periodos():
    assert anual.split_weeks(40, (34, 33, 33)) == [14, 13, 13]
    assert anual.week_now("2026-01-26", 40, datetime.date(2026, 2, 9)) == 3
    assert anual.week_now("2026-01-26", 40, datetime.date(2025, 12, 1)) is None
    assert anual.period_of(15, [14, 13, 13]) == (2, 1) and anual.period_of(40, [14, 13, 13]) == (3, 13)


def _fake_year(wpp):
    return json.dumps({"periodos": [{"n": i + 1, "semanas": [{"semana": j + 1, "tema": f"T{i + 1}{j + 1:02d}tema", "dba": "DBA 1",
                                                              "evaluacion": "Quiz"} for j in range(n - 2)]} for i, n in enumerate(wpp)]})


@pytest.fixture
def plan(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(anual, "_path", str(tmp_path / "pa.json"))
    monkeypatch.setattr(anual, "data", {"planes": {}})
    monkeypatch.setattr(diarioclase, "_path", str(tmp_path / "r.json"))
    monkeypatch.setattr(diarioclase, "data", {"registro": {}, "mallas": {}})
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Ana"], "10A": ["Eva"]})
    monkeypatch.setattr(horario, "items", [{"dia": 0, "inicio": "07:00", "fin": "07:55", "curso": "7A", "materia": "Matemáticas"},
                                           {"dia": 1, "inicio": "07:00", "fin": "07:55", "curso": "7A", "materia": "Tecnología e Informática"},
                                           {"dia": 2, "inicio": "07:00", "fin": "07:55", "curso": "10A", "materia": "Trigonometría"}])
    monkeypatch.setitem(jv.settings, "school_weeks", 40)
    monkeypatch.setitem(jv.settings, "zeti_period_weights", "34,33,33")
    monkeypatch.setitem(jv.settings, "period_current", 1)
    monkeypatch.setitem(jv.settings, "year_start", "")
    monkeypatch.setitem(jv.settings, "area_plan", "")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "out"))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    prompts = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: prompts.append(msgs[0]["content"]) or _fake_year(jv.year_weeks()))
    return prompts


def test_planear_el_ano(jv, plan):
    assert [k for k, _, _ in jv.plan_targets()] == ["7A · Matemáticas", "7A · Tecnología e Informática", "10A"]
    done = jv.plan_year()
    assert done == ["7A · Matemáticas", "7A · Tecnología e Informática", "10A"]
    assert "grado 10°" in plan[2] and "Trigonometría" in plan[2] and "14 semanas" in plan[0]
    p = anual.data["planes"]["10A"]["periodos"]
    assert [len(x["semanas"]) for x in p] == [14, 13, 13] and p[0]["semanas"][-1]["tema"] == "Refuerzo y evaluación del periodo"
    assert diarioclase.data["mallas"]["10A"]["semanas"][0]["tema"] == "T101tema"                # la del periodo en curso
    files = [f for _, _, fs in os.walk(jv.settings["output_dir"]) for f in fs]
    assert len([f for f in files if f.startswith("Planeación anual")]) == 3
    assert jv.on_new_period(2) == 3 and diarioclase.data["mallas"]["10A"]["semanas"][0]["tema"] == "T201tema"


def test_como_voy_y_reajuste(jv, plan, monkeypatch):
    jv.plan_year(["10A"])
    jv.settings["year_start"] = (datetime.date.today() - datetime.timedelta(weeks=5)).isoformat()      # semana 6
    diarioclase.add("10A", "T101tema")
    diarioclase.add("10A", "T102tema")
    st = jv.plan_status("10A")
    assert st["semana"] == 6 and st["vistos"] == 2 and st["esperados"] == 5 and st["diferencia"] == -3
    jv._rec.clear()
    jv.process_command("¿cómo voy con la planeación de 10A?")
    assert "vas atrasado 3 temas" in jv._rec.said() and "T106tema" in jv._rec.said()
    assert any("atrasado 3 temas en 10A" in x["t"] for x in jv.attention_items())
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps({"semanas": [{"tema": "Temas 1.3 y 1.4", "nota": ""}] * 9,
                                                                       "autonomo": ["T112tema"]}))
    jv._rec.clear()
    jv.process_command("reajusta la planeación de 10A")
    import time
    for _ in range(200):
        if "Reajusté" in jv._rec.said():
            break
        time.sleep(0.02)
    assert "Reajusté el periodo 1 de 10A" in jv._rec.said() and "T112tema" in jv._rec.said()
    assert anual.data["planes"]["10A"]["periodos"][0]["semanas"][5]["tema"] == "Temas 1.3 y 1.4"


def test_planear_todo_pide_aprobacion(jv, plan):
    jv._rec.clear()
    jv.process_command("planea mi año")
    assert "3 cursos y asignaturas" in jv._rec.said()
    a = jv.aprobaciones.latest()
    assert a["titulo"].startswith("Planear el año")
    jv.resolve_approval(a["id"], False)


def test_fecha_de_inicio(jv):
    assert jv._validate("year_start", "2026-01-26") == "2026-01-26"
    with pytest.raises(Exception):
        jv._validate("year_start", "enero")
