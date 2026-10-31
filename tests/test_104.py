"""Pruebas de la 10.4: áreas y asignaturas (Matemáticas y Tecnología en el mismo grupo) y revisión según el área."""
import json
import os
import threading
import time

import pytest

import asignaturas
import horario
import seguimiento


def _wait_approvals():
    for _ in range(150):
        if not any(t.name.startswith("aprobacion") and t.is_alive() for t in threading.enumerate()):
            return
        time.sleep(0.02)


def test_asignaturas_puras():
    txt = asignaturas.DEFAULT
    ch = asignaturas.choices(txt)
    assert ch[0] == "Matemáticas" and "Tecnología e Informática" in ch and "Trigonometría" in ch
    opts = ["Matemáticas", "Tecnología e Informática"]
    assert asignaturas.find("ponle 4 en el taller de tecnologia de 7a", opts, txt) == "Tecnología e Informática"
    assert asignaturas.find("en sistemas", opts, txt) == "Tecnología e Informática"
    assert asignaturas.find("el quiz de mate", opts, txt) == "Matemáticas"
    assert asignaturas.find("en matematicas", ["Trigonometría"], txt) == "Trigonometría"         # el área → la asignatura del curso
    assert asignaturas.find("el quiz de fracciones", opts, txt) is None
    assert asignaturas.parse_course_subjects("7A: Matemáticas, Tecnología e Informática") == {"7A": ["Matemáticas", "Tecnología e Informática"]}


@pytest.fixture
def prof(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Juan Pérez", "Ana Gómez"], "10A": ["Eva Díaz"]})
    monkeypatch.setitem(jv.aula.data, "activo", "7A")
    monkeypatch.setitem(jv.aula.data, "asistencia", {"7A": {"2026-10-01": ["Juan Pérez"]}})
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "n.json"))
    monkeypatch.setattr(seguimiento, "data", {})
    monkeypatch.setattr(horario, "items", [{"dia": 0, "inicio": "07:00", "fin": "07:55", "curso": "7A", "materia": "Matemáticas"},
                                           {"dia": 1, "inicio": "07:00", "fin": "07:55", "curso": "7A", "materia": "Tecnología e Informática"},
                                           {"dia": 2, "inicio": "07:00", "fin": "07:55", "curso": "10A", "materia": "Trigonometría"}])
    monkeypatch.setattr(horario, "now_class", lambda at=None: None)
    monkeypatch.setitem(jv.settings, "subject_current", "")
    monkeypatch.setitem(jv.settings, "course_subjects", "")
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "out"))
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    return tmp_path


def test_notas_aparte_por_asignatura(jv, prof):
    assert jv.subjects_for("7A") == ["Matemáticas", "Tecnología e Informática"] and jv.subjects_for("10A") == ["Trigonometría"]
    jv._rec.clear()
    jv.process_command("ponle 4,5 a juan pérez en el taller de tecnología de 7A")
    assert "7A · Tecnología e Informática" in jv._rec.said()
    jv.process_command("ponle 3 a juan pérez en el quiz de matemáticas de 7A")
    assert seguimiento.data["7A · Tecnología e Informática"]["Juan Pérez"][0]["nota"] == 4.5
    assert seguimiento.data["7A · Matemáticas"]["Juan Pérez"][0]["nota"] == 3.0
    jv._rec.clear()
    jv.process_command("ponle 4 a ana gómez en el quiz de 7A")                     # no dijo cuál: pregunta
    assert "Matemáticas y Tecnología e Informática" in jv._rec.said() and "Ana Gómez" not in str(seguimiento.data)
    jv.process_command("estamos en tecnología")
    assert jv.settings["subject_current"] in ("Tecnología", "Tecnología e Informática")
    jv.process_command("ponle 4 a ana gómez en el quiz de 7A")
    assert seguimiento.data["7A · Tecnología e Informática"]["Ana Gómez"][0]["nota"] == 4.0
    jv.process_command("ponle 4 a eva díaz en el quiz de 10A")                      # una sola asignatura: el curso
    assert "Eva Díaz" in seguimiento.data["10A"]
    assert jv._absences("7A · Matemáticas") == {"Juan Pérez": 1}                     # la asistencia es del grupo
    assert jv._resolve_course("7a tecnologia") == "7A · Tecnología e Informática"
    jv._rec.clear()
    jv.process_command("exporta las notas de 7A para Zeti")                         # una planilla por asignatura
    assert "7A en Matemáticas" in jv._rec.said() and "7A en Tecnología e Informática" in jv._rec.said()
    files = [f for _, _, fs in os.walk(jv.settings["output_dir"]) for f in fs]
    assert len([f for f in files if f.startswith("Zeti 7A")]) == 2


def test_revision_segun_el_area_y_anota_la_nota(jv, prof, monkeypatch):
    prompts = []
    monkeypatch.setattr(jv, "_vision_cfg", lambda: ({"kind": "cloud"}, ""))
    monkeypatch.setattr(jv, "_need_key", lambda c: None)
    monkeypatch.setattr(jv, "_with_fallback", lambda cfg, fn: prompts.append(1) or json.dumps(
        {"legible": True, "resumen": "Bien", "aciertos": ["a"], "errores": [], "nota": 4.2, "justificacion_nota": "x",
         "retroalimentacion": "Muy bien"}))
    monkeypatch.setattr(jv, "Document", None)
    seen = {}
    real = jv.review_work

    def spy(path, estudiante="", que="", clave="", grado="", asignatura=""):
        seen.update(asignatura=asignatura, grado=grado)
        return real(path, estudiante, que, clave, grado, asignatura)
    monkeypatch.setattr(jv, "review_work", spy)
    img = prof / "t.png"
    from PIL import Image
    Image.new("RGB", (20, 20)).save(img)
    jv.review_state["path"] = str(img)
    jv.review_state["busy"] = False
    from nucleo.clase import start_review                                         # la de verdad (conftest la reemplaza)
    start_review("actual", estudiante="Juan Pérez", que="taller de algoritmos", asignatura="Tecnología e Informática")
    for _ in range(200):
        if jv.aprobaciones.latest() and "Juan Pérez" in jv.aprobaciones.latest()["titulo"]:
            break
        time.sleep(0.02)
    assert seen == {"asignatura": "Tecnología e Informática", "grado": "7°"}, jv._rec.said()
    assert "Tecnología e Informática" in jv.area_hint("Tecnología e Informática") and "procedimiento" in jv.area_hint("Matemáticas")
    a = jv.aprobaciones.latest()
    assert a["titulo"] == "Anotar 4,2 a Juan Pérez en «taller de algoritmos» (7A, Tecnología e Informática)"
    jv.process_command("sí")
    _wait_approvals()
    assert seguimiento.data["7A · Tecnología e Informática"]["Juan Pérez"][-1]["nota"] == 4.2
