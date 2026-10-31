"""Pruebas de la 11.7: estudio de imágenes (estilos, formatos, varias opciones, editar e imprimir)."""
import base64
import io
import os
import time

import pytest
from PIL import Image

import adjuntos
import imagenes


def _png_b64(color="red", size=(64, 48)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_reglas_del_estudio(tmp_path):
    t = "crea tres opciones de un afiche del día del idioma en acuarela"
    assert imagenes.is_image(imagenes._norm(t)) and imagenes.detect_count(t) == 3
    assert imagenes.detect_style(t) == "acuarela" and imagenes.detect_aspect(t) == "3:4"
    assert imagenes.clean_subject(t) == "afiche del día del idioma"
    assert imagenes.is_image("dibujame un triangulo rectangulo para colorear") and imagenes.detect_style("para colorear") == "colorear"
    assert imagenes.clean_subject("genera una imagen horizontal de una célula animal en estilo 3D") == "una célula animal"
    assert imagenes.detect_aspect("una imagen de la célula para proyectar") == "16:9"
    assert imagenes.clean_subject("hazme un logo para el club de matemáticas") == "logo para el club de matemáticas"
    assert not imagenes.is_image("dibuja la grafica de y = 2x + 1")
    p = imagenes.build_prompt("la célula", "colorear", "3:4")
    assert "coloree" in p and "vertical" in p and "la célula" in p
    b = imagenes.gemini_body("x", "16:9", "QUJD")
    assert b["generationConfig"]["imageConfig"] == {"aspectRatio": "16:9"} and b["contents"][0]["parts"][1]["inlineData"]["data"] == "QUJD"
    assert "imageConfig" not in imagenes.gemini_body("x")["generationConfig"]
    assert imagenes.pick_openai_model(["gpt-4o", "gpt-image-1", "gpt-image-2", "gpt-image-2-mini"]) == "gpt-image-2"
    assert imagenes.pick_openai_model([]) == "gpt-image-1" and imagenes.pick_openai_model([], "mio") == "mio"
    assert imagenes.openai_payload("m", "p", "16:9")["size"] == "1536x1024"
    raw, ext = imagenes.openai_extract({"data": [{"b64_json": _png_b64()}]})
    assert raw[:4] == b"\x89PNG" and ext == ".png"
    with pytest.raises(ValueError):
        imagenes.openai_extract({"data": []})
    body, ctype = imagenes.multipart({"prompt": "hola"}, {"image": ("a.png", b"PNG", "image/png")})
    assert ctype.startswith("multipart/form-data; boundary=") and b'name="prompt"\r\n\r\nhola' in body and b'filename="a.png"' in body
    src = tmp_path / "ancha.png"
    Image.new("RGB", (800, 400), "blue").save(src)
    pdf = imagenes.letter_pdf(str(src), str(tmp_path / "carta.pdf"), "Mi imagen")
    import pypdf
    pg = pypdf.PdfReader(pdf).pages[0]
    assert float(pg.mediabox.width) > float(pg.mediabox.height)               # horizontal: la imagen es ancha


@pytest.fixture
def gem(jv, monkeypatch, tmp_path):
    """Gemini falso que devuelve una imagen (y guarda lo que se le pidió)."""
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.settings, "image_provider", "auto")
    monkeypatch.setattr(jv, "_gemini_for_stt", lambda: {"key": "AIza-falsa", "kind": "gemini"})
    monkeypatch.setattr(jv, "image_model", lambda: "gemini-x-image")
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    calls = []

    def fake(method, url, headers=None, payload=None, timeout=120, stream=False):
        calls.append({"url": url, "payload": payload})
        return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": _png_b64()}}]}}]}
    monkeypatch.setattr(jv, "_http", fake)
    jv.studio["items"].clear()
    adjuntos.items.clear()
    adjuntos.configure(str(tmp_path / "cfg"))
    yield calls
    jv.studio["items"].clear()
    adjuntos.items.clear()


def _wait(jv, text):
    for _ in range(400):
        if text in jv._rec.said():
            return
        time.sleep(0.02)


def test_quien_crea_las_imagenes(jv, monkeypatch):
    monkeypatch.setattr(jv, "_gemini_for_stt", lambda: None)
    monkeypatch.setitem(jv.settings, "chatgpt_api_key", "")
    assert jv.image_backend()[0] is None and "Gemini o de ChatGPT" in jv.image_backend()[1]
    monkeypatch.setitem(jv.settings, "chatgpt_api_key", "sk-falsa")
    assert jv.image_backend()[0] == "chatgpt"
    monkeypatch.setattr(jv, "_gemini_for_stt", lambda: {"key": "AIza"})
    monkeypatch.setattr(jv, "image_model", lambda: "gemini-x-image")
    assert jv.image_backend()[0] == "gemini"
    monkeypatch.setattr(jv, "image_model", lambda: "")                  # Gemini sin modelo de imágenes → ChatGPT
    assert jv.image_backend()[0] == "chatgpt"
    monkeypatch.setitem(jv.settings, "image_provider", "gemini")
    assert jv.image_backend()[0] == "gemini"


def test_crear_varias_y_seguir_trabajando(jv, gem, tmp_path):
    jv._rec.clear()
    jv.process_command("crea tres opciones de un afiche del día del idioma en acuarela")
    _wait(jv, "Listas 3 opciones")
    assert len(gem) == 3 and gem[0]["payload"]["generationConfig"]["imageConfig"]["aspectRatio"] == "3:4"
    assert "acuarela" in gem[0]["payload"]["contents"][0]["parts"][0]["text"] and "afiche del día del idioma" in gem[0]["payload"]["contents"][0]["parts"][0]["text"]
    imgs = [f for f in os.listdir(tmp_path / "Imágenes") if f.endswith(".png")]
    assert len(imgs) == 3
    last = jv.studio["items"][-1]["path"]
    card = jv.file_card(last)
    assert card["estudio"]["estilo"] == "acuarela" and card["estudio"]["formato"] == "vertical"
    # otra versión: el mismo pedido, sin imagen de entrada
    gem.clear(); jv._rec.clear()
    jv.process_command("otra versión")
    _wait(jv, "Lista la imagen")
    assert len(gem) == 1 and len(gem[0]["payload"]["contents"][0]["parts"]) == 1
    # editar: va la imagen anterior con la instrucción
    gem.clear(); jv._rec.clear()
    jv.process_command("cámbiale el fondo a azul")
    _wait(jv, "Lista la imagen")
    parts = gem[0]["payload"]["contents"][0]["parts"]
    assert "cámbiale el fondo a azul" in parts[0]["text"] and parts[1]["inlineData"]["mimeType"] == "image/png"
    # formato
    gem.clear(); jv._rec.clear()
    jv.process_command("hazla horizontal")
    _wait(jv, "Lista la imagen")
    assert gem[0]["payload"]["generationConfig"]["imageConfig"]["aspectRatio"] == "16:9"
    # imprimir en carta
    jv._rec.clear()
    jv.process_command("imprímela")
    _wait(jv, "lista para imprimir")
    assert any(f.endswith("(carta).pdf") for f in os.listdir(tmp_path / "Imágenes"))


def test_formato_que_el_modelo_no_acepta(jv, gem, monkeypatch):
    calls = []

    def fake(method, url, headers=None, payload=None, timeout=120, stream=False):
        calls.append(payload)
        if "imageConfig" in payload["generationConfig"]:
            raise jv.AIError("no", code=400, why="parámetro no válido")
        return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": _png_b64()}}]}}]}
    monkeypatch.setattr(jv, "_http", fake)
    assert len(jv.studio_generate("la célula", "", "16:9")) == 1 and len(calls) == 2


def test_chatgpt_crear_y_editar(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.settings, "image_provider", "chatgpt")
    monkeypatch.setitem(jv.settings, "chatgpt_api_key", "sk-falsa")
    monkeypatch.setitem(jv.settings, "image_model_openai", "")
    jv._oa_model.update(name="", checked=0.0)
    seen = []

    def fake(method, url, headers=None, payload=None, timeout=120, stream=False):
        seen.append((method, url, payload))
        if url.endswith("/models"):
            return {"data": [{"id": "gpt-image-1"}, {"id": "gpt-image-2"}]}
        return {"data": [{"b64_json": _png_b64()}]}
    monkeypatch.setattr(jv, "_http", fake)
    p = jv.studio_generate("una célula", "3d", "16:9")[0]
    gen = seen[-1]
    assert gen[1].endswith("/images/generations") and gen[2]["model"] == "gpt-image-2" and gen[2]["size"] == "1536x1024" and os.path.exists(p)
    sent = []
    monkeypatch.setattr(jv, "_post_multipart", lambda url, key, fields, files, timeout=240: sent.append((url, fields, files)) or
                        {"data": [{"b64_json": _png_b64("blue")}]})
    jv.studio_generate("", "", "", 1, src=p, instruccion="ponle un sombrero")
    assert sent[0][0].endswith("/images/edits") and "ponle un sombrero" in sent[0][1]["prompt"] and sent[0][2]["image"][1][:4] == b"\x89PNG"


def test_editar_una_foto_subida(jv, gem):
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), "green").save(buf, "PNG")
    r = jv.handle_attach({"files": [{"name": "salon.png", "data": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}]})
    assert "editar" in [a["a"] for a in r["acciones"]]
    jv._rec.clear()
    assert jv.handle_studio_action({"attach": r["ids"][0], "action": "editar", "texto": "ponle un tablero verde al fondo"})["ok"]
    _wait(jv, "Lista la imagen")
    assert "tablero verde" in gem[-1]["payload"]["contents"][0]["parts"][0]["text"]
    assert not jv.handle_studio_action({"attach": r["ids"][0], "action": "editar", "texto": ""})["ok"]
    assert not jv.handle_studio_action({"path": "/no/existe.png", "action": "otra"})["ok"]


def test_no_se_roba_otras_ordenes(jv, gem):
    jv.studio_generate("la célula", "", "")
    for t in ("ponle una alarma a las 6", "agrega una tarea para mañana", "que hora es", "hazla en pdf", "abre la calculadora",
              "haz el taller de fracciones para septimo"):
        assert not jv.studio_voice(t, t), t
    jv.studio["items"][-1]["t"] -= 2000                                   # ya pasó un buen rato
    assert not jv.studio_voice("cambiale el fondo", "cambiale el fondo")
