"""Pruebas de la 11.0: evaluaciones en versiones A, B, C, D y material con gráficas y figuras."""
import os

import pytest

import aula
import examenes
import graficas
import omr
import seguimiento
import versiones
from test_105 import QUIZ, photo  # noqa: F401  (la «foto» de una hoja)

cv2 = pytest.importorskip("cv2")


def test_versiones_puras():
    vs = versiones.make([4] * 6, 4, seed=7)
    assert [v["v"] for v in vs] == ["A", "B", "C", "D"] and vs[0]["orden"] == list(range(6))
    assert vs[1]["orden"] != list(range(6)) and sorted(vs[1]["orden"]) == list(range(6))
    base_key = [0, 1, 2, 3, 0, 1]
    for v in vs:
        kv = versiones.key_for(v, base_key)
        assert versiones.to_base(kv, v) == base_key                        # la clave de la versión, al orden original, es la clave
    assert versiones.assign([1, 2, 3, 4, 5], 4) == {"1": "A", "2": "B", "3": "C", "4": "D", "5": "A"}


def test_graficas():
    f = graficas.compile_expr("2x^2 - 3")
    assert f(2.0) == 5.0 and graficas.compile_expr("(x+1)(x-1)")(3.0) == 8.0
    for bad in ("__import__('os')", "x.__class__", "open(x)", "lambda"):
        with pytest.raises(ValueError):
            graficas.compile_expr(bad)
    with pytest.raises(ValueError):
        graficas.compile_expr("9^9^9")                                     # no se cuelga: desborda y avisa
    assert graficas.clean({"tipo": "triángulo", "lados": {"AB": "5 cm"}, "recto": "C"})["tipo"] == "triangulo"
    assert graficas.clean({"tipo": "funcion", "expr": "import os"}) is None and graficas.clean({"tipo": "nada"}) is None
    for spec in ({"tipo": "funcion", "expr": "x^2-4"}, {"tipo": "plano", "puntos": [[1, 2, "A"]]}, {"tipo": "barras", "etiquetas": ["a", "b"],
                 "valores": [1, 2]}, {"tipo": "torta", "etiquetas": ["a"], "valores": [3]}, {"tipo": "circulo", "radio": "3 cm"},
                 {"tipo": "rectangulo"}, {"tipo": "triangulo"}):
        p = graficas.render(spec)
        assert p and os.path.getsize(p) > 1000
        os.remove(p)


def test_material_con_grafica(tmp_path):
    from docx import Document
    m = aula.validate("quiz", {"titulo": "Funciones", "preguntas": [
        {"enunciado": "¿Dónde corta el eje x?", "opciones": ["2", "4", "0", "-4"], "respuesta": "a", "explicacion": "",
         "grafica": {"tipo": "funcion", "expr": "x^2-4"}},
        {"enunciado": "¿2+2?", "opciones": ["4", "5", "6", "7"], "respuesta": "a", "grafica": {"tipo": "funcion", "expr": "os.system()"}}]})
    assert m["preguntas"][0]["grafica"]["expr"] == "x^2-4" and "grafica" not in m["preguntas"][1]
    path = aula.build_docx("quiz", m, str(tmp_path), Document)
    assert len(Document(path).inline_shapes) == 1
    assert "grafica" in aula.build_prompt("quiz", "quiz de funciones")


@pytest.fixture
def aula7a(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(examenes, "_path", str(tmp_path / "e.json"))
    monkeypatch.setattr(examenes, "data", {"examenes": {}})
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "n.json"))
    monkeypatch.setattr(seguimiento, "data", {})
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Ana Gómez", "Juan Pérez", "Luis Rojas", "Eva Díaz", "Sara López"]})
    monkeypatch.setitem(jv.aula.data, "activo", "7A")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "out"))
    monkeypatch.setitem(jv.settings, "course_subjects", "")
    monkeypatch.setattr(jv.horario, "items", [])
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    monkeypatch.setitem(jv.last_quiz, "m", QUIZ)
    jv.sess.update(code=None, token="")
    return tmp_path


def test_hojas_en_cuatro_versiones(jv, aula7a):
    jv._rec.clear()
    jv.process_command("prepara las hojas de respuesta del quiz para 7A en 4 versiones")
    assert "4 versiones (A, B, C, D)" in jv._rec.said()
    ex = examenes.latest()
    assert ex["vmap"]["1"] == "A" and ex["vmap"]["2"] == "B" and ex["vmap"]["5"] == "A" and len(ex["vmap"]) == 9
    files = [f for _, _, fs in os.walk(jv.settings["output_dir"]) for f in fs]
    assert any(f.endswith(".pdf") for f in files) and any("versiones" in f and f.endswith(".docx") for f in files)
    jv.process_command("califica las hojas")
    vb = next(v for v in ex["versiones"] if v["v"] == "B")
    kb = versiones.key_for(vb, ex["clave"])
    r = jv.grade_photo(photo(ex["code"], 2, 8, 4, {i: kb[i] for i in range(8)}))          # Juan (versión B): todo bien con SU clave
    assert r["ok"] and r["version"] == "B" and r["nota"] == 5.0 and "versión B" in r["msg"]
    assert ex["resultados"]["2"]["answers"] == ex["clave"]                                  # guardado en el orden original
    wrong = dict(enumerate(kb))
    wrong[0] = (kb[0] + 1) % 4
    r = jv.grade_photo(photo(ex["code"], 2, 8, 4, wrong))
    assert r["malas"] == [1] and r["aciertos"] == 7                                         # la 1 de SU cuadernillo
    r = jv.grade_photo(photo(ex["code"], 1, 8, 4, {i: ex["clave"][i] for i in range(8)}))  # Ana (versión A = original)
    assert r["version"] == "A" and r["nota"] == 5.0
