"""Pruebas de la 10.3: varios grados, de sexto a undécimo (cursos, orden, grado del material y todo de una vez)."""
import json
import os

import pytest

import aula
import periodos
import seguimiento

CURSOS = {"6A": ["Ana"], "7 Tecnología": ["Luis"], "10 Trigonometría": ["Eva"], "11-1": ["Sara"], "11-2": ["Iván"], "Décimo B": ["Pía"]}


@pytest.fixture
def carga(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.aula.data, "cursos", {k: list(v) for k, v in CURSOS.items()})
    monkeypatch.setitem(jv.aula.data, "activo", "7 Tecnología")
    monkeypatch.setitem(jv.aula.data, "asistencia", {})
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "n.json"))
    monkeypatch.setattr(seguimiento, "data", {})
    monkeypatch.setattr(periodos, "_path", str(tmp_path / "p.json"))
    monkeypatch.setattr(periodos, "data", {})
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "out"))
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    return tmp_path


def test_reconoce_los_cursos(carga):
    assert aula.find_course("undécimo 1") == "11-1" and aula.find_course("11 2") == "11-2"
    assert aula.find_course("sexto a") == "6A" and aula.find_course("7") == "7 Tecnología"
    assert aula.find_course("11") is None and aula.find_course("10") is None                # varios del mismo grado
    assert sorted(CURSOS, key=aula.course_sort_key) == ["6A", "7 Tecnología", "Décimo B", "10 Trigonometría", "11-1", "11-2"]
    assert [aula.grade_of(c) for c in ("6A", "Séptimo", "11-2", "Décimo B")] == [6, 7, 11, 10]


def test_grado_ambiguo_pregunta(jv, carga):
    assert jv._resolve_course("11") == ""                                                   # no adivina con 11-1 y 11-2
    assert jv._resolve_course("undécimo 2") == "11-2"
    jv._rec.clear()
    jv.process_command("ponle 4 a sara en el quiz de 11")
    assert "curso" in jv._rec.said().lower()


def test_material_con_el_grado_del_curso(jv, carga, monkeypatch):
    prompts = []
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: prompts.append(msgs[0]["content"]) or (_ for _ in ()).throw(ValueError("x")))
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    jv.generate_material("haz un taller de algoritmos", "taller")
    jv.generate_material("haz un quiz de funciones para undécimo", "quiz")
    assert any("7° (curso 7 Tecnología)" in p and "unos 12 a 13 años" in p for p in prompts)
    assert not any("curso 7 Tecnología" in p for p in prompts if "undécimo" in p)


def test_zeti_de_todos_los_cursos(jv, carga):
    for c, n in (("6A", "Ana"), ("11-1", "Sara"), ("10 Trigonometría", "Eva")):
        seguimiento.data[c] = {n: [{"actividad": "Quiz", "nota": 4.0, "fecha": "2026-10-01"}]}
    jv._rec.clear()
    jv.process_command("exporta las notas de todos mis cursos para Zeti")
    s = jv._rec.said()
    assert "3 planillas" in s and s.index("6A") < s.index("10 Trigonometría") < s.index("11-1")
    files = [f for _, _, fs in os.walk(jv.settings["output_dir"]) for f in fs]
    assert len([f for f in files if f.startswith("Zeti")]) == 3


def test_quien_pierde_en_todos(jv, carga, monkeypatch):
    monkeypatch.setitem(jv.settings, "period_current", 3)
    periodos.set_val("6A", "Ana", 1, 2.0)
    periodos.set_val("6A", "Ana", 2, 2.0)
    periodos.set_val("11-1", "Sara", 1, 4.5)
    periodos.set_val("11-1", "Sara", 2, 4.5)
    seguimiento.data["6A"] = {"Ana": [{"actividad": "Quiz", "nota": 2.0, "fecha": "2026-10-01"}]}
    jv._rec.clear()
    jv.process_command("¿quiénes pueden perder el año?")
    assert "6A: 1 (Ana)" in jv._rec.said() and "11-1" not in jv._rec.said()
