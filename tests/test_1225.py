"""12.25: audios de Telegram a texto, subtítulos .srt y modelo saturado en videos e imágenes."""
import os
import subprocess

import pytest

import adjuntos
import imagenes
import subtitulos


@pytest.fixture
def store(jv, tmp_path, monkeypatch):
    adjuntos.configure(str(tmp_path / "cfg"))
    monkeypatch.setattr(adjuntos, "items", [])
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "out"))
    monkeypatch.setitem(jv._batch, "ids", [])
    return tmp_path


def _wav(jv, tmp_path, name="clase.wav", secs=5):
    exe = jv._ffmpeg()
    if not exe:
        pytest.skip("sin ffmpeg en este equipo")
    dst = str(tmp_path / name)
    subprocess.run([exe, "-loglevel", "quiet", "-y", "-f", "lavfi", "-i", f"sine=frequency=330:duration={secs}", dst], check=True)
    return dst


# ---------------------------------------------------------------- subtítulos (lógica)
def test_lee_las_marcas_de_tiempo():
    raw = "[00:02] Buenos días a todos.\n[00:05] Hoy vamos a ver fracciones\nequivalentes.\n00:11 - ¿Alguien recuerda qué es?\n[09:59] fuera del trozo\n[00:08] retrocede"
    got = subtitulos.parse_stamped(raw, offset=300, limit=300)
    assert got == [(302, "Buenos días a todos."), (305, "Hoy vamos a ver fracciones equivalentes."), (311, "¿Alguien recuerda qué es?"), (311, "retrocede")]
    assert subtitulos.parse_stamped("(nada)") == [] and subtitulos.parse_stamped("[1:02:03] una hora después")[0][0] == 3723


def test_arma_el_srt():
    cs = subtitulos.cues([(2, "Buenos días a todos."), (5, "Hoy vamos a ver fracciones equivalentes, que son las que valen lo mismo aunque se escriban distinto, como un medio y dos cuartos."),
                          (40, "Persona 1: Listo.")], total=60)
    assert cs[0] == (2, 5, ["Buenos días a todos."])                       # dura hasta el siguiente
    assert all(len(line) <= 42 and len(c[2]) <= 2 for c in cs for line in c[2])  # máximo 2 líneas de 42 letras
    assert cs[1][0] == 5 and cs[-2][1] <= 12.001                           # el largo se parte y no pasa de 7 s en total
    assert cs[-1] == (40, 47, ["Listo."])                                  # sin «Persona 1:»
    srt = subtitulos.to_srt(cs)
    assert srt.startswith("1\n00:00:02,000 --> 00:00:05,000\nBuenos días a todos.\n\n2\n00:00:05,000 --> ")
    assert subtitulos._ts(3723.5) == "01:02:03,500"
    sp = subtitulos.spread("Una frase. Otra frase más larga que la primera.", 300, 60)
    assert sp[0][0] == 300 and 300 < sp[1][0] < 360


def test_subtitulos_de_un_audio(jv, store, monkeypatch):
    src = _wav(jv, store)
    it = adjuntos.add("clase.wav", open(src, "rb").read())
    said, asked = [], []
    monkeypatch.setattr(jv, "is_offline", lambda: False)
    monkeypatch.setattr(jv, "_gemini_for_stt", lambda: {"model": "g", "key": "k", "kind": "gemini", "ai_provider": "gemini", "label": "Gemini"})
    monkeypatch.setattr(jv, "_tr_gemini", lambda cfg, p, hint="", stamped=False: asked.append(stamped) or "[00:01] Hola a todos.\n[00:03] Empezamos la clase.")
    monkeypatch.setattr(jv, "notify", lambda text, origin="JARVIS": said.append((origin, text)))
    dst = jv.attach_run([it], "subtitulos")
    assert asked == [True] and dst.endswith("clase.srt")
    body = open(dst, encoding="utf-8-sig").read()
    assert "00:00:01,000 --> 00:00:03,000\nHola a todos." in body and "2\n00:00:03,000 --> " in body
    assert said[-1][0] == "SUBTÍTULOS" and "2 líneas" in said[-1][1] and "pueden correrse" in said[-1][1]
    monkeypatch.setattr(jv, "is_offline", lambda: True)                    # sin internet: Whisper, con tiempos exactos
    monkeypatch.setattr(jv, "_whisper_segments", lambda p: [(0.5, 2.25, "Hola a todos."), (2.5, 4.0, "Empezamos.")])
    srt, n, how, exact, _r = jv.subtitle_media(it)
    assert n == 2 and exact and how == "Whisper en tu equipo" and "00:00:00,500 --> 00:00:02,250" in srt
    monkeypatch.setattr(jv, "_whisper_segments", lambda p: None)
    jv.attach_run([it], "subtitulos")
    assert "necesito la clave de Gemini" in said[-1][1]


def test_subtitulos_por_voz(jv, ask, store, monkeypatch):
    went = []
    monkeypatch.setattr(jv, "_attach_go", lambda its, action, pregunta: went.append(action))
    adjuntos.add("clase.mp4", b"x" * 2000)
    assert ask("hazle subtítulos")[0] == "SUBTÍTULOS" and went == ["subtitulos"]
    assert {"a": "subtitulos", "t": "Subtítulos (.srt)"} in jv.card_of([adjuntos.items[-1]])["acciones"]


# ---------------------------------------------------------------- Telegram
def test_que_audio_es_una_orden_y_cual_es_para_transcribir(jv):
    m = jv.tg_is_material
    assert not m({"voice": {"duration": 6}})                               # nota corta tuya: una orden, como siempre
    assert m({"voice": {"duration": 6}, "forward_origin": {"type": "user"}})  # reenviada: es de otra persona, se transcribe
    assert m({"voice": {"duration": 200}}) and m({"voice": {"duration": 8}, "caption": "transcribe"})
    assert m({"audio": {"duration": 30}, "caption": "acta"}) and m({"video": {"duration": 5}}) and m({"video_note": {}})
    assert not m({"text": "hola"}) and not m({"audio": {"duration": 20}})
    a = jv.tg_media_action_of
    assert a("saca el acta") == "acta" and a("subtítulos porfa") == "subtitulos" and a("transcríbelo") == "transcribir" and a("resume") == "acta" and a("hola") == ""


def test_audio_de_telegram_a_texto(jv, store, monkeypatch):
    sent, docs, ran = [], [], []
    monkeypatch.setattr(jv, "telegram_send", lambda t: sent.append(t))
    monkeypatch.setattr(jv, "_tg_file", lambda fid: b"OggS" + b"x" * 5000)
    monkeypatch.setattr(jv, "tg_send_document", lambda p: docs.append(os.path.basename(p)))
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    out = store / "out"
    out.mkdir(exist_ok=True)

    def run(its, action, pregunta=""):
        ran.append((its[0]["nombre"][-4:], its[0]["tipo"], action))
        jv.tr_last.update(text="Hola profe, mañana no hay clase." if action == "transcribir" else "x" * 5000, notes="", path="p", kind=action)
        p = out / f"r_{action}.docx"
        p.write_bytes(b"d")
        return str(p)
    monkeypatch.setattr(jv, "attach_run", run)
    assert jv.tg_media_in({"voice": {"file_id": "f1", "duration": 12, "file_size": 5004}, "forward_date": 1})
    assert ran[-1] == (".ogg", "audio", "transcribir") and sent[-1] == "📝 Hola profe, mañana no hay clase." and not docs
    assert jv.tg_media_in({"voice": {"file_id": "f2", "duration": 900, "file_size": 5004}})                 # larga → acta, y llega el Word
    assert ran[-1][2] == "acta" and docs == ["r_acta.docx"]
    assert jv.tg_media_in({"video": {"file_id": "f3", "duration": 30, "file_size": 5004}, "caption": "subtítulos"})
    assert ran[-1] == (".mp4", "video", "subtitulos")
    assert jv.tg_pending_answer("acta") and ran[-1][2] == "acta"            # después: «acta» sobre el mismo archivo
    n = len(ran)
    assert jv.tg_media_in({"audio": {"file_id": "f4", "duration": 4000, "file_size": 30_000_000}, "caption": "acta"})
    assert len(ran) == n and "20 MB" in sent[-1]                           # muy grande: lo dice, con la salida
    assert not jv.tg_media_in({"voice": {"file_id": "f5", "duration": 5}})  # orden corta: no la toca
    assert jv.tg_file_in({"document": {"file_id": "f6", "file_name": "reunion.m4a", "file_size": 5004}}) and ran[-1][:2] == (".m4a", "audio")


# ---------------------------------------------------------------- modelo saturado en videos e imágenes
def test_video_usa_otro_modelo_si_esta_saturado(jv, monkeypatch):
    used = []
    monkeypatch.setattr(jv, "_gemini_for_stt", lambda: {"model": "g-a", "key": "k", "kind": "gemini", "ai_provider": "gemini", "label": "Gemini"})
    monkeypatch.setattr(jv, "_gemini_headers", lambda c: {})
    monkeypatch.setattr(jv, "_with_fallback", lambda cfg, fn: fn(dict(cfg, model="g-b")))      # el respaldo escogió otro
    monkeypatch.setattr(jv, "_post", lambda url, h, body, optional=(), timeout=180, stream=False: used.append(url) or
                        {"candidates": [{"content": {"parts": [{"text": "Trata de fracciones."}]}}]})
    assert jv.youtube_summary("https://youtu.be/dQw4w9WgXcQ") == "Trata de fracciones." and "/models/g-b:" in used[0]


def test_imagen_usa_otro_modelo_si_esta_saturado(jv, monkeypatch):
    names = ["models/gemini-2.5-flash-image", "models/gemini-3-pro-image-preview", "models/text-embedding-004", "models/gemini-2.5-flash"]
    cands = imagenes.model_candidates(names)
    assert len(cands) == 2 and set(cands) == {"gemini-2.5-flash-image", "gemini-3-pro-image-preview"}
    tried = []
    monkeypatch.setattr(jv, "image_model", lambda: cands[0])
    monkeypatch.setattr(jv, "image_models_all", lambda: cands)
    monkeypatch.setattr(jv, "_gemini_headers", lambda c: {})

    def http(method, url, headers=None, payload=None, timeout=120, stream=False):
        tried.append(url.split("/models/")[1].split(":")[0])
        if tried[-1] == cands[0]:
            raise jv.AIError("overloaded", code=503, kind="server")
        return {"ok": 1}
    monkeypatch.setattr(jv, "_http", http)
    monkeypatch.setattr(imagenes, "extract", lambda data: (b"png", "png"))
    assert jv._one_image("gemini", {"key": "k"}, "un gato") == (b"png", "png") and tried == cands
    tried.clear()

    def bad(method, url, headers=None, payload=None, timeout=120, stream=False):
        tried.append(1)
        raise jv.AIError("clave", code=403, kind="key")
    monkeypatch.setattr(jv, "_http", bad)
    with pytest.raises(jv.AIError):
        jv._one_image("gemini", {"key": "k"}, "un gato")
    assert tried == [1]                                                    # una clave mala no se arregla cambiando de modelo
