"""12.38: lo automático del modo docente, para varios grados y varios cursos."""
import datetime
import json
import os
import time

import pytest

import adjuntos
import aula
import diarioclase
import horario
import semana
import seguimiento

CURSOS = {"7A": ["Ana Gómez", "Luis Rojas"], "7B": ["Eva Díaz", "Juan Ruiz"], "7C": ["Sara Paz"], "9A": ["Leo Mora", "Ivo Gil"],
          "11A": ["Mar Sol"]}
HOR = [{"dia": 0, "inicio": "07:00", "fin": "07:55", "curso": "7A", "materia": "Matemáticas"},
       {"dia": 0, "inicio": "08:00", "fin": "08:55", "curso": "7B", "materia": "Matemáticas"},
       {"dia": 0, "inicio": "09:00", "fin": "09:55", "curso": "9A", "materia": "Matemáticas"},
       {"dia": 0, "inicio": "10:00", "fin": "10:55", "curso": "7C", "materia": "Tecnología"},
       {"dia": 2, "inicio": "07:00", "fin": "07:55", "curso": "7A", "materia": "Matemáticas"},
       {"dia": 3, "inicio": "07:00", "fin": "07:55", "curso": "11A", "materia": "Física"}]


@pytest.fixture
def cole(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setitem(aula.data, "cursos", {k: list(v) for k, v in CURSOS.items()})
    monkeypatch.setitem(aula.data, "asistencia", {"7A": {"2026-11-09": ["Luis Rojas"], "2026-11-10": ["Luis Rojas"]}})
    monkeypatch.setattr(horario, "items", list(HOR))
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "n.json"))
    monkeypatch.setattr(seguimiento, "data", {
        "7A": {"Ana Gómez": [{"actividad": "Quiz 1", "nota": 4.5, "fecha": "2026-11-10", "origen": "voz"}],
               "Luis Rojas": [{"actividad": "Quiz 1", "nota": 2.0, "fecha": "2026-11-10", "origen": "voz"},
                              {"actividad": "Taller", "nota": 2.5, "fecha": "2026-11-11", "origen": "voz"}]},
        "9A": {"Leo Mora": [{"actividad": "Taller", "nota": 3.8, "fecha": "2026-11-11", "origen": "voz"}]}})
    monkeypatch.setattr(diarioclase, "_path", str(tmp_path / "d.json"))
    monkeypatch.setattr(diarioclase, "data", {"registro": {"7A": [{"fecha": "2026-11-10", "tema": "Fracciones", "nota": ""}],
                                                           "7B": [{"fecha": "2026-11-10", "tema": "Fracciones", "nota": ""}],
                                                           "9A": [{"fecha": "2026-11-11", "tema": "Ecuaciones", "nota": ""}]},
                                              "mallas": {}})
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "out"))
    monkeypatch.setitem(jv.settings, "assistant_mode", "docente")
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setattr(jv, "gdrive_ready", lambda: False)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="", *a, **k: fn())
    monkeypatch.setitem(jv._dd, "last", "")
    return tmp_path


# ---------------------------------------------------------------- varios grados y cursos
def test_grados_y_agrupacion():
    assert [semana.grade_key(c) for c in ("7A", "7-2", "Séptimo B", "11 Física", "Delfines")] == [7, 7, 7, 11, None]
    rows = [{"curso": "7A", "materia": "Matemáticas", "tema": "Fracciones"}, {"curso": "7B", "materia": "matemáticas", "tema": "fracciones"},
            {"curso": "7C", "materia": "Tecnología", "tema": "Fracciones"}, {"curso": "9A", "materia": "Matemáticas", "tema": "Fracciones"}]
    g = semana.group_courses(rows)
    assert [x["cursos"] for x in g] == [["7A", "7B"], ["7C"], ["9A"]]
    assert semana.courses_label(["7A", "7B", "7C"]) == "7A, 7B y 7C"


def test_semana_lista_un_plan_por_grupo():
    topics = {"7A": "Fracciones", "7B": "Fracciones", "9A": "Ecuaciones", "7C": "Fracciones", "11A": ""}
    plan, sin = semana.week_plan(HOR, lambda c: topics.get(c, ""), datetime.date(2026, 11, 16))
    titles = [p["titulo"] for p in plan["pasos"] if p["tipo"] == "plan"]
    assert titles == ["Plan de clase 7A y 7B: Fracciones", "Plan de clase 9A: Ecuaciones", "Plan de clase 7C: Fracciones"]
    assert "el mismo material para todos" in plan["pasos"][0]["pedido"] and plan["pasos"][0]["cursos"] == ["7A", "7B"]
    assert sin == ["11A"]


def test_cursos_en_frases_y_archivos(jv, cole):
    assert jv.courses_in("crea un quiz para 7A sobre fracciones") == ["7A"]
    assert jv.courses_in("Quiz fracciones 7-B") == ["7B"] and jv.courses_in("boletines de 7 a y 9a") == ["7A", "9A"]
    assert jv.courses_in("haz los boletines de 11A") == ["11A"] and jv.courses_in("examen de cultura") == []
    assert jv.course_folder(["7A"]) == "7A" and jv.course_folder(["7A", "7B"]) == "Grado 7°" and jv.course_folder(["7A", "9A"]) == ""


def test_drive_subcarpeta_por_curso(jv, cole, tmp_path, monkeypatch):
    from test_1237 import FakeDrive
    fake = FakeDrive()
    fake.files["JARVIS"] = {"name": "Jarvis", "kind": "folder"}
    monkeypatch.setattr(jv, "classroom_client", lambda: fake)
    monkeypatch.setattr(jv, "gdrive_ready", lambda: True)
    monkeypatch.setitem(jv.settings, "drive_folder_id", "JARVIS")
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="", *a, **k: fn())
    f = tmp_path / "Boletines 9A.pdf"
    f.write_bytes(b"x")
    jv.note_skill("boletin_voice", "haz los boletines de 9A")
    assert jv._dd["cursos"] == ["9A"]
    assert jv.docente_file(str(f))
    up = next(v for v in fake.files.values() if v["kind"] == "file" and v["name"].startswith("Boletines"))
    sub = fake.files[up["parents"]]
    assert sub["name"] == "9A" and fake.files[sub["parents"][0]]["name"] == "04 Boletines del periodo"


# ---------------------------------------------------------------- 1. formatos del colegio
def _upload(tmp_path, monkeypatch, name="Formato planes.docx"):
    from docx import Document
    d = Document()
    d.sections[0].header.paragraphs[0].text = "IE SAN JOSÉ · Formato institucional"
    d.add_paragraph("Texto de ejemplo que no debe quedar")
    p = tmp_path / name
    d.save(p)
    it = {"id": "a1", "nombre": name, "tipo": "word", "ruta": str(p), "ext": ".docx", "t": time.time(), "bytes": 1, "paginas": 1}
    monkeypatch.setattr(adjuntos, "items", [it])
    return it


def test_formato_por_grado_y_por_curso(jv, ask, cole, tmp_path, monkeypatch):
    who, said = ask("usa este formato para los planes de clase")
    assert "Súbeme el formato" in said
    _upload(tmp_path, monkeypatch)
    who, said = ask("usa este formato para los planes de clase de séptimo")
    assert who == "FORMATOS" and "«Plan de clase»" in said and "grado 7°" in said
    _upload(tmp_path, monkeypatch, "Formato 9A.docx")
    assert "para 9A" in ask("usa este formato para los planes de clase de 9A")[1]
    _upload(tmp_path, monkeypatch, "General.docx")
    assert "todos los cursos" in ask("usa este formato para las rúbricas")[1]
    fs = jv.formats_list()
    assert {(f["sid"], f["scope"]) for f in fs} == {("plan_clase", "g7"), ("plan_clase", "c:9A"), ("rubrica", "todos")}
    assert jv.template_for("plan_clase", ["7B"]).endswith("g7.docx")
    assert jv.template_for("plan_clase", ["9A"]).endswith("c_9A.docx")
    assert jv.template_for("plan_clase", ["11A"]) == "" and jv.template_for("rubrica", ["11A"]).endswith("todos.docx")
    assert "3 formatos" in ask("¿qué formatos tengo?")[1]
    assert "Quité" in ask("quita el formato de los planes de clase de 9A")[1]
    assert len(jv.formats_list()) == 2


def test_el_documento_sale_sobre_el_formato(jv, ask, cole, tmp_path, monkeypatch):
    _upload(tmp_path, monkeypatch)
    ask("usa este formato para los planes de clase de séptimo")
    assert getattr(jv.Document, "templated", False)
    jv.note_skill_direct("plan_clase", ["7A"])
    d = jv.Document()
    assert d.sections[0].header.paragraphs[0].text.startswith("IE SAN JOSÉ") and not d.paragraphs
    d.add_paragraph("Plan nuevo")
    assert [p.text for p in d.paragraphs] == ["Plan nuevo"]
    jv.note_skill_direct("plan_clase", ["11A"])                          # otro grado: documento normal
    assert jv.Document().sections[0].header.paragraphs[0].text == ""
    jv._dd["last"] = ""
    assert jv.Document().sections[0].header.paragraphs[0].text == ""


# ---------------------------------------------------------------- 2. respaldo
def test_respaldo_una_hoja_por_curso(jv, ask, cole):
    who, said = ask("haz el respaldo de notas")
    assert who == "RESPALDO" and "5 cursos" in said
    from openpyxl import load_workbook
    folder = os.path.join(jv.settings["output_dir"], "Respaldos docentes")
    path = os.path.join(folder, os.listdir(folder)[0])
    wb = load_workbook(path)
    assert wb.sheetnames == ["Resumen", "7A", "7B", "7C", "9A", "11A"]
    ws = wb["7A"]
    assert [c.value for c in ws[1]] == ["Estudiante", "Quiz 1", "Taller", "Promedio", "Faltas"]
    assert ws["D3"].value == '=IFERROR(AVERAGE(B3:C3),"")' and ws["E3"].value == 2
    res = wb["Resumen"]
    assert [res.cell(r, 1).value for r in range(2, 7)] == ["Grado 7°", "Grado 7°", "Grado 7°", "Grado 9°", "Grado 11°"]
    assert res["D2"].value.startswith("=IFERROR(AVERAGE('7A'!D2:D3)")


# ---------------------------------------------------------------- 3. cierre completo
def test_cierre_propone_boletines_y_recuperaciones(jv, cole, monkeypatch):
    asked, sent = [], []
    monkeypatch.setattr(jv, "request_approval", lambda tipo, titulo, detalle="", on_ok=None, **k: asked.append((tipo, titulo, on_ok)))
    monkeypatch.setattr(jv, "submit_command", lambda text, source="texto": sent.append(text))
    assert jv.close_followups() == ["boletines", "recuperaciones"]
    assert asked[0][1] == "Hacer los boletines de 2 cursos" and asked[1][1] == "Planes de recuperación de 7A"
    asked[0][2]()
    asked[1][2]()
    assert sent == ["haz los boletines de 7A", "haz los boletines de 9A", "haz los planes de recuperación de 7A"]
    monkeypatch.setitem(jv.settings, "close_followups", False)
    assert jv.close_followups() == []


# ---------------------------------------------------------------- 4. resumen docente
def test_resumen_docente_por_grado(jv, ask, cole, monkeypatch):
    monkeypatch.setattr(jv, "phone_send", lambda text: False)
    data = jv.teacher_week(datetime.date(2026, 11, 13))
    assert [g["grado"] for g in data] == ["Grado 7°", "Grado 9°", "Grado 11°"]
    c7 = {c["curso"]: c for c in data[0]["cursos"]}
    assert c7["7A"]["vistos"] == ["Fracciones"] and c7["7A"]["riesgo"] == ["Luis Rojas"] and c7["7A"]["notas"] == 3
    txt = jv.teacher_week_text(data)
    assert "5 cursos" in txt and "• Grado 7°: 7A: Fracciones; 7B: Fracciones; 7C: sin registro" in txt and "Luis Rojas (7A)" in txt
    who, said = ask("hazme el resumen docente de la semana")
    assert who == "RESUMEN DOCENTE"
    assert os.listdir(os.path.join(jv.settings["output_dir"], "Resúmenes docentes"))


# ---------------------------------------------------------------- 5. clase de mañana
def test_clase_de_manana_agrupa_y_no_repite(jv, ask, cole, monkeypatch):
    monday = datetime.date(2026, 11, 23)                                           # (el 16 es festivo)
    monkeypatch.setitem(jv.state, "ai", "ok")
    runs = []
    monkeypatch.setattr(jv, "run_project", lambda st: runs.append(st))
    plan = jv.prepare_day(monday, say=False)
    assert [p["titulo"] for p in plan["pasos"]] == ["Clase de mañana 7A y 7B: continuación de Fracciones",
                                                    "Clase de mañana 9A: continuación de Ecuaciones"]
    assert jv.prepared()[monday.isoformat()] == ["7A", "7B", "9A"]
    assert jv.prepare_day(monday, say=False) is None and len(runs) == 1           # ya estaba: no repite
    tue = datetime.date(2026, 11, 24)
    assert jv.prepare_day(tue, say=False) is None                                   # martes sin clases
    holiday = datetime.date(2026, 11, 30)
    import festivos
    monkeypatch.setattr(festivos, "no_class", lambda d: "es festivo (prueba)")
    assert jv.prepare_day(holiday, say=False) is None


def test_semana_lista_marca_lo_preparado(jv, cole):
    plan = {"pasos": [{"tipo": "plan", "cursos": ["7A", "7B"]}]}
    jv.mark_week_prepared(plan, datetime.date(2026, 11, 16))
    p = jv.prepared()
    assert p["2026-11-16"] == ["7A", "7B"] and p["2026-11-18"] == ["7A"]


def test_reloj_viernes_y_noche(jv, cole, monkeypatch):
    calls = []
    monkeypatch.setattr(jv, "run_backup", lambda say=True: calls.append("respaldo") or "x")
    monkeypatch.setattr(jv, "run_friday", lambda say=True, send=False: calls.append(("resumen", send)) or "x")
    monkeypatch.setattr(jv, "prepare_day", lambda day, say=True: calls.append(("dia", day)) or {"pasos": []})
    for k in ("auto_backup_last", "docente_friday_last", "night_prep_last"):
        monkeypatch.setitem(jv.settings, k, "")
    monkeypatch.setitem(jv.project_run, "busy", False)
    assert jv.auto_ticks(datetime.datetime(2026, 11, 20, 10)) == []                # viernes temprano
    assert jv.auto_ticks(datetime.datetime(2026, 11, 20, 20)) == ["respaldo", "resumen"]   # viernes noche: mañana es sábado
    assert jv.auto_ticks(datetime.datetime(2026, 11, 20, 21)) == []                # una vez
    assert jv.auto_ticks(datetime.datetime(2026, 11, 22, 19, 5)) == ["clase de mañana"]   # domingo noche → lunes
    assert ("dia", datetime.date(2026, 11, 23)) in calls and ("resumen", True) in calls
    monkeypatch.setitem(jv.settings, "night_prep", False)
    monkeypatch.setitem(jv.settings, "night_prep_last", "")
    assert jv.auto_ticks(datetime.datetime(2026, 11, 23, 19, 5)) == []


def test_nuevas_habilidades_en_el_catalogo():
    import catalogo_docente as C
    ids = {h["id"] for h in C.H}
    assert {"clase_manana", "formatos", "respaldo_notas", "resumen_semana"} <= ids and len(C.H) == 58
