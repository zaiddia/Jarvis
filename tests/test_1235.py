"""12.35: «la habilidad de procesar video y transcribir audio no está disponible» — sí lo está."""
import os

import pytest

import adjuntos


@pytest.fixture
def nada(jv, monkeypatch):
    monkeypatch.setattr(adjuntos, "items", [])
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)


@pytest.mark.parametrize("f", ["transcribe este video", "¿puedes transcribir audio?", "procesa este video", "transcríbeme el audio",
                               "sácale el texto a este video", "¿puedes procesar videos?", "hazle subtítulos a mi video"])
def test_sin_nada_subido_explica_como(jv, ask, nada, f):
    who, said = ask(f)
    assert who == "TRANSCRIPCIÓN" and said.startswith("Sí, eso lo hago") and "clip" in said and "Telegram" in said


def test_youtube(jv, ask, nada, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="", *a, **k: fn())
    monkeypatch.setattr(jv, "youtube_transcript", lambda url: "Persona 1: Hola, hoy vemos fracciones.")
    notes = []
    monkeypatch.setattr(jv, "notify", lambda text, origin="": notes.append(text))
    assert ask("transcribe el video https://youtu.be/abcdefghijk")[0] == "TRANSCRIPCIÓN"
    assert "transcribí el video (6 palabras)" in notes[-1] and os.path.exists(jv.tr_last["path"])
    assert ask("resume este video https://youtu.be/abcdefghijk")[0] == "VIDEO"            # resumir sigue como antes
    sent = []
    monkeypatch.setattr(jv, "_gemini_for_stt", lambda: {"model": "g", "key": "k", "kind": "gemini", "ai_provider": "gemini", "label": "Gemini"})
    monkeypatch.setattr(jv, "_gemini_headers", lambda c: {})
    monkeypatch.setattr(jv, "_with_fallback", lambda cfg, fn: fn(cfg))
    monkeypatch.setattr(jv, "_post", lambda url, h, body, opt=(), timeout=0: sent.append(body) or {"candidates": [{"content": {"parts": [{"text": "texto"}]}}]})
    assert jv.sys.modules["nucleo.transcribir"].youtube_transcript("https://www.youtube.com/watch?v=abcdefghijk") == "texto"
    assert sent[0]["contents"][0]["parts"][0]["file_data"]["file_uri"].endswith("abcdefghijk")


def test_la_ia_sabe_que_si_puede(jv):
    assert "transcribe audios y videos" in jv.ACTION_RULE and "nunca digas que eso no está disponible" in jv.ACTION_RULE
    assert "transcripciones de audios y videos" in jv.LIVE_RULE
