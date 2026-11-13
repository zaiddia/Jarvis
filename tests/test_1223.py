"""12.23: audios y videos subidos → texto y acta; cambiar el tamaño de una imagen."""
import base64
import os
import subprocess
import time

import pytest

import adjuntos
import conversiones

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTES = ("RESUMEN\nSe habló de la feria de ciencias. Se definió la fecha.\n\nACUERDOS\n- La feria será el 20 de noviembre\n- Cada curso lleva dos proyectos\n\n"
         "TAREAS\n- Reservar el coliseo — Marta — viernes\n\nPENDIENTES\n- Ninguno")


@pytest.fixture
def store(jv, tmp_path, monkeypatch):
    adjuntos.configure(str(tmp_path / "cfg"))
    monkeypatch.setattr(adjuntos, "items", [])
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "out"))
    monkeypatch.setitem(jv._batch, "ids", [])
    return tmp_path


def _ffmpeg(jv):
    exe = jv._ffmpeg()
    if not exe:
        pytest.skip("sin ffmpeg en este equipo")
    return exe


def _media(jv, tmp_path, name, secs=4, video=False):
    exe = _ffmpeg(jv)
    dst = str(tmp_path / name)
    src = ["-f", "lavfi", "-i", f"sine=frequency=330:duration={secs}"]
    if video:
        src = ["-f", "lavfi", "-i", f"testsrc=duration={secs}:size=160x120:rate=5"] + src
    subprocess.run([exe, "-loglevel", "quiet", "-y"] + src + [dst], check=True)
    return dst


# ---------------------------------------------------------------- subir por partes
def test_audio_grande_sube_por_partes(jv, store):
    raw = os.urandom(70_000)
    cut = [raw[:30_000], raw[30_000:60_000], raw[60_000:]]
    r = None
    for i, part in enumerate(cut):
        r = jv.handle_attach_part({"uid": "u1", "name": "Reunión de área.m4a", "i": i, "n": 3,
                                   "data": "data:application/octet-stream;base64," + base64.b64encode(part).decode()})
        assert r["ok"] and bool(r.get("sigue")) == (i < 2)
    it = adjuntos.get(r["ids"][0])
    assert it["tipo"] == "audio" and it["bytes"] == 70_000 and open(it["ruta"], "rb").read() == raw
    assert [a["a"] for a in r["acciones"]] == ["acta", "transcribir", "subtitulos"]
    assert not jv.handle_attach_part({"uid": "u2", "name": "virus.exe", "i": 0, "n": 1, "data": "data:;base64,AAAA"})["ok"]
    assert not jv.handle_attach_part({"uid": "u3", "name": "a.mp3", "i": 1, "n": 2, "data": "data:;base64,AAAA"})["ok"]      # sin el comienzo
    assert adjuntos.kind_of("clase.MP4") == "video" and adjuntos.kind_of("nota.opus") == "audio"


# ---------------------------------------------------------------- del audio al texto (ffmpeg de verdad)
@pytest.mark.parametrize("name,video", [("nota.wav", False), ("clase.mp4", True)])
def test_saca_el_sonido_y_lo_parte(jv, store, name, video):
    src = _media(jv, store, name, secs=5, video=video)
    tmp = store / "trozos"
    tmp.mkdir()
    parts = jv.media_chunks(src, str(tmp), secs=2)
    assert len(parts) >= 2 and all(p.endswith(".mp3") and os.path.getsize(p) > 600 for p in parts)


def test_acta_completa(jv, store, monkeypatch):
    src = _media(jv, store, "Reunión feria.wav", secs=5)
    it = adjuntos.add("Reunión feria.wav", open(src, "rb").read())
    sent, said = [], []
    monkeypatch.setattr(jv, "is_offline", lambda: False)
    monkeypatch.setattr(jv, "_gemini_for_stt", lambda: {"model": "gemini-x", "key": "k", "kind": "gemini", "ai_provider": "gemini", "label": "Gemini"})
    monkeypatch.setattr(jv, "_with_fallback", lambda cfg, fn: fn(cfg))
    monkeypatch.setattr(jv, "_gemini_headers", lambda c: {})
    monkeypatch.setattr(jv, "CHUNK_SECS", 2, raising=False)
    import nucleo.transcribir as tr
    monkeypatch.setattr(tr, "CHUNK_SECS", 2)
    real = jv.media_chunks
    monkeypatch.setattr(jv, "media_chunks", lambda s, t, secs=2: real(s, t, 2))

    def post(url, headers, body, optional=(), timeout=180, stream=False):
        sent.append(body)
        n = len(sent)
        return {"candidates": [{"content": {"parts": [{"text": f"Persona 1: parte {n} de la reunión."}]}}]}
    monkeypatch.setattr(jv, "_post", post)
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, json_mode=False, max_tokens=None: NOTES)
    monkeypatch.setattr(jv, "notify", lambda text, origin="JARVIS": said.append((origin, text)))
    dst = jv.media_run(it, with_minutes=True)
    assert len(sent) >= 2 and sent[0]["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "audio/mp3"
    assert "parte 1 de la reunión" in sent[1]["contents"][0]["parts"][1]["text"]        # cada trozo sabe en qué iba el anterior
    assert dst.endswith("(acta).docx") and os.path.dirname(dst).endswith("Transcripciones")
    from docx import Document
    body = "\n".join(p.text for p in Document(dst).paragraphs)
    assert "La feria será el 20 de noviembre" in body and "Reservar el coliseo" in body and "parte 2 de la reunión" in body
    origin, msg = said[-1]
    assert origin == "TRANSCRIPCIÓN" and "feria de ciencias" in msg and "Anoté 2 acuerdos" in msg
    dst2 = jv.media_run(it, with_minutes=False)                                         # solo transcribir
    assert dst2.endswith("(transcripción).docx")


def test_sin_gemini_ni_whisper_lo_dice(jv, store, monkeypatch):
    src = _media(jv, store, "nota.wav", secs=2)
    it = adjuntos.add("nota.wav", open(src, "rb").read())
    monkeypatch.setattr(jv, "is_offline", lambda: True)
    monkeypatch.setattr(jv, "_whisper_transcribe", lambda raw: None)
    said = []
    monkeypatch.setattr(jv, "notify", lambda text, origin="JARVIS": said.append(text))
    jv.attach_run([it], "acta")
    assert "necesito la clave de Gemini" in said[-1] and "Whisper" in said[-1]
    monkeypatch.setattr(jv, "_whisper_transcribe", lambda raw: "hola desde whisper" if len(raw) > 1000 else "")
    text, how, _m = jv.transcribe_media(it)
    assert text == "hola desde whisper" and how == "Whisper en tu equipo"                # sin internet: en tu equipo


def test_por_voz(jv, ask, store, monkeypatch):
    went = []
    monkeypatch.setattr(jv, "_attach_go", lambda its, action, pregunta: went.append((its[0]["nombre"], action)))
    assert ask("transcribe este audio")[0] != "TRANSCRIPCIÓN"                           # sin nada subido no hace nada
    adjuntos.add("reunion.mp3", b"x" * 2000)
    assert ask("transcríbelo")[0] == "TRANSCRIPCIÓN" and went[-1] == ("reunion.mp3", "transcribir")
    assert ask("saca el acta de la reunión")[0] == "TRANSCRIPCIÓN" and went[-1][1] == "acta"
    assert ask("¿qué acordaron?")[0] == "TRANSCRIPCIÓN" and went[-1][1] == "acta"
    assert ask("resume este video")[0] == "TRANSCRIPCIÓN" and went[-1][1] == "acta"


# ---------------------------------------------------------------- tamaño de imágenes
def _img(store, w=1600, h=1200, name="foto.jpg"):
    from PIL import Image
    p = str(store / name)
    Image.new("RGB", (w, h), (30, 120, 200)).save(p)
    return adjuntos.add(name, open(p, "rb").read())


def test_entiende_el_tamano():
    rs = conversiones.resize_spec
    assert rs("dejala de 800 de ancho") == {"w": 800} and rs("ponla de 600 de alto") == {"h": 600}
    assert rs("redimensiona a 800x600") == {"w": 800, "h": 600} and rs("cambiale el tamano a 1024 por 768") == {"w": 1024, "h": 768}
    assert rs("dejala tamano carne") == {"preset": "carne"} and rs("recortala 3x4") == {"preset": "carne"} and rs("hazla cuadrada") == {"preset": "cuadrada"}
    assert rs("reducela a la mitad") == {"pct": 50} and rs("escalala al 25 por ciento") == {"pct": 25}
    for no in ["que dice esta imagen", "pasala a pdf", "800 de ancho", "ponla en word", "reduce el peso"]:
        assert rs(no) is None, no


def test_cambia_el_tamano_sin_deformar(jv, store):
    from PIL import Image
    it = _img(store)
    out = str(store / "o")
    dst, before, after, note = conversiones.image_resize(it, out, {"w": 800})
    assert before == (1600, 1200) and after == (800, 600) and Image.open(dst).size == (800, 600) and note == ""
    _d, _b, after, note = conversiones.image_resize(it, out, {"w": 800, "h": 800})
    assert after == (800, 600) and "no deformarla" in note                               # cabe en la caja, no se estira
    dst, _b, after, note = conversiones.image_resize(it, out, {"preset": "carne"})
    assert after == (354, 472) and "recortada" in note and Image.open(dst).size == (354, 472)
    assert conversiones.image_resize(it, out, {"pct": 50})[2] == (800, 600)
    assert "borrosa" in conversiones.image_resize(it, out, {"pct": 200})[3]
    with pytest.raises(conversiones.ConvertError):
        conversiones.image_resize(it, out, {"w": 50000})
    png = _img(store, 400, 300, "logo.png")
    assert conversiones.image_resize(png, out, {"h": 150})[0].endswith("(200x150).png")   # conserva el formato


def test_tamano_por_voz_y_tarjeta(jv, ask, store, monkeypatch):
    it = _img(store)
    said = []
    monkeypatch.setattr(jv, "notify", lambda text, origin="JARVIS": said.append(text))
    card = jv.card_of([it])
    assert {"a": "redim:carne", "t": "↔ Tamaño carné"} in card["acciones"]
    jv.attach_run([it], "redim:w800")
    assert "de 1600×1200 a 800×600" in said[-1]
    monkeypatch.setattr(jv, "_attach_go", lambda its, action, pregunta: jv.attach_run(its, action, pregunta))
    who, _ = ask("déjala de 400 de ancho")
    assert who == "ADJUNTOS" and "a 400×300" in said[-1]
    ask("redúcela a la mitad")
    assert "a 800×600" in said[-1]
    n = len(said)
    ask("comprímela")                                                                   # lo de antes sigue igual
    assert len(said) == n + 1 and "liviana" in said[-1]


def test_hud_acepta_audio_y_video():
    js = open(os.path.join(ROOT, "static", "js", "hud.js"), encoding="utf-8").read()
    html = open(os.path.join(ROOT, "templates", "hud.html"), encoding="utf-8").read()
    assert 'socket.emit("attach_part"' in js and "MEDIA_EXT" in js and "audio/*,video/*" in html
