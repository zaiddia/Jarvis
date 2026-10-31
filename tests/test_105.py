"""Pruebas de la 10.5: hojas de respuesta que se califican con una foto, análisis de la evaluación y refuerzo."""
import base64
import json
import os
import threading
import time

import pytest

import examenes
import omr
import seguimiento

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


def _wait_approvals():
    for _ in range(150):
        if not any(t.name.startswith("aprobacion") and t.is_alive() for t in threading.enumerate()):
            return
        time.sleep(0.02)


def photo(code, student, n_q, n_opt, fill, rot=None):
    """Una «foto» de la hoja: en perspectiva, sobre una mesa, con sombra, ruido y JPEG."""
    a = np.array(omr.draw_sheet(code, student, n_q, n_opt, "Quiz", "7A", "x", fill=fill))
    bg = (np.full((2400, 1900), 110) + np.random.rand(2400, 1900) * 40).astype(np.uint8)
    src = np.float32([[0, 0], [omr.W, 0], [omr.W, omr.H], [0, omr.H]])
    dst = np.float32([[260, 230], [1560, 300], [1660, 2200], [190, 2120]])
    m = cv2.getPerspectiveTransform(src, dst)
    w = cv2.warpPerspective(a, m, (1900, 2400), borderValue=0)
    mask = cv2.warpPerspective(np.full_like(a, 255), m, (1900, 2400))
    p = np.where(mask > 0, w, bg).astype(np.float32) * np.linspace(0.7, 1.05, 1900)[None, :]
    p = np.clip(p + np.random.randn(*p.shape) * 5, 0, 255).astype(np.uint8)
    if rot is not None:
        p = cv2.rotate(p, rot)
    return cv2.imencode(".jpg", p, [cv2.IMWRITE_JPEG_QUALITY, 82])[1].tobytes()


def test_codigo_de_la_hoja():
    for code, st in ((1, 0), (12345, 7), (16383, 127)):
        assert omr.decode_bits(omr.id_bits(code, st)) == (code, st)
    bits = omr.id_bits(500, 3)
    bits[2] ^= 1
    assert omr.decode_bits(bits) is None and omr.decode_bits([0] * 24) is None


def test_lee_la_foto_aunque_este_torcida_o_de_lado():
    fill = {q: (q * 7) % 4 for q in range(30) if q != 5}
    exp = [fill.get(q) for q in range(30)]
    for rot in (None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180):
        r = omr.read_image(photo(4321, 12, 30, 4, fill, rot), 30, 4)
        assert (r["code"], r["student"]) == (4321, 12) and r["answers"] == exp
    with pytest.raises(omr.ReadError):
        omr.read_image(cv2.imencode(".jpg", np.full((800, 600), 200, np.uint8))[1].tobytes())


def test_calificar_y_analizar():
    key = [0, 1, 2, 3]
    g = omr.grade([0, 1, None, 0], key)
    assert g["aciertos"] == 2 and g["nota"] == 3.0 and g["detalle"] == [True, True, None, False]
    items = omr.item_analysis([{"answers": [0, 1, 1, 0]}, {"answers": [0, 2, 1, 3]}], key, 4)
    assert items[2]["acierto"] == 0 and items[2]["distractor"] == 1 and items[0]["acierto"] == 100
    assert examenes.parse_key("a, c, b, d") == [0, 2, 1, 3] and examenes.parse_key("1a 2c 3b") == [0, 2, 1]


QUIZ = {"titulo": "Quiz de fracciones", "tema": "fracciones", "preguntas": [
    {"enunciado": f"Pregunta {i}", "opciones": ["1/2", "1/3", "1/4", "2/3"], "respuesta": "abcd"[i % 4], "explicacion": ""} for i in range(8)]}


@pytest.fixture
def aula7a(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(examenes, "_path", str(tmp_path / "ex.json"))
    monkeypatch.setattr(examenes, "data", {"examenes": {}})
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "n.json"))
    monkeypatch.setattr(seguimiento, "data", {})
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Ana Gómez", "Juan Pérez", "Luis Rojas"]})
    monkeypatch.setitem(jv.aula.data, "activo", "7A")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "out"))
    monkeypatch.setitem(jv.settings, "course_subjects", "")
    monkeypatch.setattr(jv.horario, "items", [])
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    monkeypatch.setitem(jv.last_quiz, "m", QUIZ)
    jv.sess.update(code=None, token="")
    return tmp_path


def test_flujo_completo(jv, aula7a, monkeypatch):
    jv._rec.clear()
    jv.process_command("prepara las hojas de respuesta del quiz para 7A")
    assert "3 con nombre" in jv._rec.said() and "8 preguntas" in jv._rec.said()
    ex = examenes.latest()
    pdf = [f for _, _, fs in os.walk(jv.settings["output_dir"]) for f in fs if f.endswith(".pdf")]
    assert pdf and ex["clave"] == [0, 1, 2, 3, 0, 1, 2, 3] and ex["estudiantes"]["2"] == "Juan Pérez"
    jv.process_command("califica las hojas")
    assert jv.sess["code"] == ex["code"] and jv.sess["token"]
    r = jv.grade_photo(photo(ex["code"], 2, 8, 4, {i: ex["clave"][i] for i in range(8)}))                    # Juan: todas bien
    assert r["ok"] and r["nombre"] == "Juan Pérez" and r["nota"] == 5.0
    wrong = {i: (ex["clave"][i] if i not in (3, 5) else (ex["clave"][i] + 1) % 4) for i in range(8)}
    b64 = "data:image/jpeg;base64," + base64.b64encode(photo(ex["code"], 1, 8, 4, wrong)).decode()
    r = jv.handle_grade_upload({"data": b64})                                                              # Ana, desde el HUD
    assert r["ok"] and r["nombre"] == "Ana Gómez" and r["malas"] == [4, 6] and r["nota"] == 4.0
    r = jv.grade_photo(photo(ex["code"], 3, 8, 4, {0: 0, 1: 1, 3: 0, 5: 0}))                              # Luis
    assert r["nombre"] == "Luis Rojas" and r["aciertos"] == 2
    jv._rec.clear()
    jv.process_command("terminé de calificar")
    for _ in range(200):
        if "hojas" in jv._rec.said() and jv.aprobaciones.latest() and "Anotar" in jv.aprobaciones.latest()["titulo"]:
            break
        time.sleep(0.02)
    s = jv._rec.said()
    assert "3 hojas" in s and "la 4" in s and "la 6" in s
    assert any(f.startswith("Análisis") for _, _, fs in os.walk(jv.settings["output_dir"]) for f in fs)
    jv.process_command("sí")
    _wait_approvals()
    assert seguimiento.data["7A"]["Juan Pérez"][0]["nota"] == 5.0 and seguimiento.data["7A"]["Juan Pérez"][0]["dim"] == "conocer"
    # refuerzo a la medida
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps({"diagnostico": "Confunden fracciones", "clase": {"objetivo": "x", "actividades": ["a"]},
                                                                      "preguntas": [{"numero": n, "error": "e", "explicacion": "exp", "ejercicios": [{"enunciado": "1/2+1/2", "respuesta": "1"}]}
                                                                                    for n in (3, 4, 5, 6, 7, 8)]}))
    path = jv.reinforcement()
    assert path and os.path.exists(path)
    from docx import Document
    text = "\n".join(p.text for p in Document(path).paragraphs)
    assert "Para: Luis Rojas" in text and "Para: Juan Pérez" not in text                                  # Juan no falló nada


def test_clave_externa_y_paginas_protegidas(jv, aula7a):
    jv.process_command("prepara las hojas de respuesta del simulacro para 7A, la clave es a, c, b, d, a")
    ex = examenes.latest()
    assert ex["clave"] == [0, 2, 1, 3, 0] and ex["preguntas"] == []
    client = jv.mobile_app.test_client()
    assert client.get("/h/inventado").status_code == 404
    jv.process_command("califica las hojas")
    assert client.get(f"/h/{jv.sess['token']}").status_code == 200
    d = client.get(f"/h/{jv.sess['token']}/datos").get_json()
    assert d["ok"] and d["preguntas"] == 5
    r = client.post(f"/h/{jv.sess['token']}/foto", data=photo(ex["code"], 1, 5, 4, {0: 0, 1: 2, 2: 1, 3: 3, 4: 0})).get_json()
    assert r["ok"] and r["nota"] == 5.0
    jv.process_command("la clave es a, a, b, d, a")                                                       # corrige la clave: recalifica
    assert ex["resultados"]["1"]["aciertos"] == 4
