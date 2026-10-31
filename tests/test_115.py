"""Pruebas de la 11.5: quiz desde un video de YouTube y libro guía del curso."""
import base64
import io
import json
import os
import time

import pytest

import libro
import videos

PAGE = ('<html><title>Teorema de Pitágoras explicado - YouTube</title><script>var x = {"captionTracks":[{"baseUrl":"https://www.youtube.com/api/timedtext?v=abc&lang=en",'
        '"languageCode":"en"},{"baseUrl":"https://www.youtube.com/api/timedtext?v=abc&lang=es","languageCode":"es","kind":"asr"}]};</script></html>')
XML = '<transcript><text start="0" dur="3">Hola a todos</text><text start="65.2" dur="4">el cuadrado de la hipotenusa &amp;amp; los catetos</text></transcript>'
QUIZ = {"titulo": "Pitágoras", "tema": "Pitágoras", "resumen": "Trata del teorema.", "preguntas": [
    {"enunciado": f"¿P{i}?", "opciones": ["a", "b", "c", "d"], "respuesta": "b", "explicacion": "Porque sí", "minuto": "01:05"} for i in range(4)],
    "pausas": [{"minuto": "01:00", "pregunta": "¿Qué es un cateto?"}]}


def test_partes_del_video():
    assert videos.video_id("mira https://youtu.be/dQw4w9WgXcQ?t=3") == "dQw4w9WgXcQ"
    assert videos.video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=x") == "dQw4w9WgXcQ"
    tr = videos.caption_tracks(PAGE)
    assert videos.pick_track(tr)["lang"] == "es" and videos.title_of(PAGE) == "Teorema de Pitágoras explicado"
    segs = videos.parse_timedtext(XML)
    assert segs[1] == (65.2, "el cuadrado de la hipotenusa & los catetos")
    assert "[01:05]" in videos.as_prompt_text(segs)
    pasted = videos.parse_pasted("0:00\nHola a todos\n1:05\nel cuadrado de la hipotenusa\n1:02:03 al final")
    assert pasted[1] == (65, "el cuadrado de la hipotenusa") and pasted[2][0] == 3723


def _wait(jv, text):
    for _ in range(300):
        if text in jv._rec.said():
            return
        time.sleep(0.02)


def test_quiz_del_video(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    monkeypatch.setattr(jv, "_get_text", lambda url, timeout=12: PAGE if "watch" in url else XML)
    prompts = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: prompts.append(msgs[0]["content"]) or json.dumps(QUIZ))
    monkeypatch.setattr(jv.banco, "add_quiz", lambda m: 0)
    jv._rec.clear()
    jv.process_command("haz un quiz de 5 preguntas de este video https://youtu.be/dQw4w9WgXcQ")
    _wait(jv, "Listo «Pitágoras»")
    assert "4 preguntas con el minuto" in jv._rec.said() and "1 pausas" in jv._rec.said()
    assert "[01:05] el cuadrado de la hipotenusa" in prompts[0] and "5 preguntas" in prompts[0]
    assert jv.last_quiz["m"]["preguntas"][0]["respuesta"] == "b"                      # listo para Forms, Kahoot u hojas
    from docx import Document
    path = next(os.path.join(r, f) for r, _, fs in os.walk(tmp_path) for f in fs if f.endswith(".docx"))
    text = "\n".join(p.text for p in Document(path).paragraphs)
    assert "[01:05]" in text and "⏸ 01:00" in text
    # sin subtítulos: pide pegar la transcripción
    monkeypatch.setattr(jv, "_get_text", lambda url, timeout=12: "<html></html>")
    jv._rec.clear()
    jv.process_command("haz un quiz del video https://youtu.be/dQw4w9WgXcQ")
    _wait(jv, "Mostrar transcripción")
    assert "quiz del video:" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("quiz del video: 0:00\nHola a todos, hoy veremos el teorema\n1:05\nel cuadrado de la hipotenusa es igual a la suma")
    _wait(jv, "Listo «Pitágoras»")
    assert "Listo «Pitágoras»" in jv._rec.said()


@pytest.fixture
def lib(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(libro, "_dir", str(tmp_path))
    monkeypatch.setattr(libro, "index", {"libros": {}})
    libro._cache.clear()
    return tmp_path


def test_libro_guia(jv, lib, monkeypatch):
    from docx import Document
    doc = Document()
    for i in range(3):
        doc.add_paragraph(("relleno " * 300) if i != 1 else "El teorema de Pitágoras dice que en un triángulo rectángulo el cuadrado de la hipotenusa es "
                          "igual a la suma de los cuadrados de los catetos. " + "ejemplo " * 400)
    buf = io.BytesIO()
    doc.save(buf)
    r = jv.handle_books({"upload": "data:application/octet-stream;base64," + base64.b64encode(buf.getvalue()).decode(), "filename": "Matemáticas 8.docx",
                         "asignatura": "Matemáticas"})
    assert r["ok"] and r["libros"][0]["nombre"] == "Matemáticas 8" and r["libros"][0]["paginas"] >= 3
    hits = libro.search("teorema de Pitágoras hipotenusa", "Matemáticas")
    assert hits and "hipotenusa" in hits[0]["texto"]
    assert libro.search("hipotenusa", "Tecnología e Informática") == []             # solo los libros de esa asignatura
    ctx = jv.book_ctx("teorema de Pitágoras", "")
    assert "libro guía" in ctx and "p. " in ctx
    # PDF sin texto (escaneado): lo dice
    from PIL import Image
    pdf = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(pdf, "PDF")
    r = jv.handle_books({"upload": base64.b64encode(pdf.getvalue()).decode(), "filename": "escaneado.pdf"})
    assert not r["ok"] and "escaneado" in r["msg"]
    jv._rec.clear()
    jv.process_command("¿qué libros guía tengo?")
    assert "Matemáticas 8" in jv._rec.said()
    monkeypatch.setitem(jv.state, "ai", "off")
    jv._rec.clear()
    jv.process_command("busca en el libro guía: teorema de Pitágoras")
    assert "página" in jv._rec.said()
    assert jv.handle_books({"delete": r["libros"][0]["id"]})["libros"] == []
