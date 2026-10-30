"""Pruebas de la 8.2: preguntas tipo Saber, malla del periodo, ajustes PIAR, observador e informes para padres."""
import json
import time

import pytest

import aula
import formularios
import informes
import seguimiento

SABER = {"titulo": "Simulacro", "grado": "11", "tema": "lectura crítica", "instrucciones": "Lee.",
         "preguntas": [{"contexto": "Un texto corto…", "enunciado": "¿Cuál es la idea?", "opciones": ["A) uno", "dos", "tres", "cuatro"],
                        "respuesta": "B", "competencia": "Comprende el sentido global", "explicacion": "Porque…"}]}
MALLA = {"titulo": "Malla de matemáticas", "grado": "7", "tema": "Matemáticas", "periodo": "Tercero", "estandar": "Pensamiento numérico",
         "semanas": [{"semana": 1, "tema": "Fracciones", "dba": "DBA 2", "desempeno": "Suma fracciones", "actividades": "Taller",
                      "evaluacion": "Quiz"}, {"tema": "Decimales"}], "evidencias": ["Resuelve problemas"]}
PIAR = {"titulo": "Ajustes", "grado": "6", "tema": "fracciones", "necesidad": "Baja visión", "barreras": ["Letra pequeña"],
        "ajustes": [{"tipo": "Materiales", "ajuste": "Letra de 18 puntos"}, {"ajuste": ""}], "actividad": "Taller en grande",
        "evaluacion": "Oral", "seguimiento": "Cada mes"}


def test_tipos_nuevos():
    assert aula.detect_kind("crea 10 preguntas tipo saber de lectura critica") == "saber"
    assert aula.detect_kind("haz la malla curricular de sociales del tercer periodo") == "malla"
    assert aula.detect_kind("adapta el taller de fracciones para un estudiante con baja vision") == "piar"
    assert aula.detect_kind("haz un quiz de fracciones") == "quiz"
    for k in ("saber", "malla", "piar"):
        p = aula.build_prompt(k, "x")
        assert "JSON" in p
    assert "Decreto 1421" in aula.build_prompt("piar", "x") and "ICFES" in aula.build_prompt("saber", "x")
    s = aula.validate("saber", SABER)
    q = s["preguntas"][0]
    assert q["opciones"][0] == "uno" and q["respuesta"] == "b" and q["contexto"] and q["competencia"]
    m = aula.validate("malla", MALLA)
    assert [x["semana"] for x in m["semanas"]] == [1, 2] and m["evidencias"]
    p = aula.validate("piar", PIAR)
    assert len(p["ajustes"]) == 1 and p["ajustes"][0]["tipo"] == "Materiales"
    with pytest.raises(ValueError):
        aula.validate("malla", {"semanas": []})
    # el contexto de Saber va como descripción de la pregunta en Forms
    item = [r for r in formularios.batch_requests(s) if "createItem" in r][0]["createItem"]["item"]
    assert item["description"] == "Un texto corto…"


def test_word_de_los_tipos_nuevos(jv, tmp_path):
    if jv.Document is None:
        pytest.skip("sin python-docx")
    for k, d in (("saber", SABER), ("malla", MALLA), ("piar", PIAR)):
        path = aula.build_docx(k, aula.validate(k, d), str(tmp_path), jv.Document, "Prof", "Colegio", "7A")
        text = " ".join(p.text for p in jv.Document(path).paragraphs)
        assert {"saber": "Clave, competencias", "malla": "Evidencias", "piar": "Decreto 1421"}[k] in text


def test_saber_por_voz(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.settings, "aula_open_docs", False)
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps(SABER))
    added = []
    monkeypatch.setattr(jv.banco, "add_quiz", lambda m: added.append(m) or 1)
    jv._rec.clear()
    jv.process_command("crea 8 preguntas tipo saber de lectura crítica para once")
    for _ in range(100):
        if not jv.material_job["busy"]:
            break
        time.sleep(0.02)
    assert added and added[0]["preguntas"][0]["contexto"]
    assert jv.last_quiz["m"] is added[0]
    assert "tipo Saber" in jv._rec.said()


# ----------------------------------------------------------------------------- observador e informes
@pytest.fixture
def curso(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Juan Pérez", "Ana Gómez"]})
    monkeypatch.setitem(jv.aula.data, "activo", "7A")
    monkeypatch.setitem(jv.aula.data, "asistencia", {"7A": {"2026-10-01": ["Juan Pérez"]}})
    monkeypatch.setattr(informes, "_path", str(tmp_path / "obs.json"))
    monkeypatch.setattr(informes, "data", {})
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "notas.json"))
    monkeypatch.setattr(seguimiento, "data", {"7A": {"Juan Pérez": [{"actividad": "quiz", "nota": 2.5, "fecha": "2026-10-01", "origen": "voz"}]}})
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    return tmp_path


def test_observador(jv, curso):
    rec = jv._rec
    rec.clear()
    jv.process_command("anota en el observador de Juan que hoy ayudó a sus compañeros con el taller")
    assert "observador de Juan Pérez (7A), como anotación positiva" in rec.said()
    jv.process_command("anota en el observador de Juan de 7A que llegó tarde y sin uniforme")
    e = informes.entries("7A", "Juan Pérez")
    assert [x["tipo"] for x in e] == ["positiva", "convivencia"] and e[0]["texto"].startswith("Hoy ayudó")
    rec.clear()
    jv.process_command("¿qué tiene Juan en el observador?")
    assert "2 anotaciones" in rec.said()
    if jv.Document is not None:
        rec.clear()
        jv.process_command("genera el observador de Juan")
        assert list((curso / "Observador").iterdir())


def test_informe_para_padres(jv, curso, monkeypatch):
    if jv.Document is None:
        pytest.skip("sin python-docx")
    seen = []

    def ai(msgs, **k):
        seen.append(msgs[0]["content"])
        n = msgs[0]["content"].count("\nid ")
        return json.dumps({"informes": [{"id": i, "parrafos": ["Su hijo es muy amable."], "recomendaciones": ["Leer 20 minutos"]}
                                        for i in range(n)]})
    monkeypatch.setattr(jv, "ai_chat", ai)
    said = []
    monkeypatch.setattr(jv, "notify", lambda text, origin="JARVIS": said.append(text))
    jv._tl.capture = []
    try:
        jv.process_command("haz el informe para los padres de Juan")
        assert '"promedio": 2.5' in seen[0] and '"fallas": 1' in seen[0] and "Bajo" in seen[0]
        jv.process_command("prepara los informes para los padres de todo el curso 7A")
    finally:
        jv._tl.capture = None
    assert "2 informes" in said[-1]
    files = sorted((curso / "Informes para padres").iterdir())
    assert len(files) == 2
    text = " ".join(p.text for p in jv.Document(str(files[0])).paragraphs)
    assert "Estimada familia" in text and "Su hijo es muy amable." in text


def test_desempeno():
    assert [informes.performance(x) for x in (4.8, 4.2, 3.0, 2.9, None)] == ["Superior", "Alto", "Básico", "Bajo", ""]
    assert informes.letter_validate({"informes": [{"id": 0, "parrafos": ["a"]}, {"id": 5, "parrafos": ["b"]}]}, 1) == \
        {0: {"parrafos": ["a"], "recomendaciones": []}}


