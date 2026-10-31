"""Pruebas de la 9.5: resumen de la mañana en nota de voz, tu estilo al escribir y retroalimentación de textos."""
import datetime
import json
import threading
import time

import pytest

import compromisos
import estilo
import horario
import seguimiento

TEXTO = ("El agua es muy importante para la vida porque todos los seres vivos la nesecitan. En mi casa ahorramos agua "
         "cerrando la llave cuando nos cepillamos. Pienso que el colegio deberia tener mas campañas.")


@pytest.fixture
def limpio(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(estilo, "_path", str(tmp_path / "e.json"))
    monkeypatch.setattr(estilo, "data", {"ejemplos": [], "perfil": "", "perfil_n": 0})
    monkeypatch.setattr(compromisos, "data", {"items": [], "respondidos": [], "descartados": []})
    monkeypatch.setattr(compromisos, "_path", str(tmp_path / "c.json"))
    for a in jv.aprobaciones.pending():
        jv.resolve_approval(a["id"], False, "prueba")
    return tmp_path


def test_resumen_de_la_manana(jv, limpio, monkeypatch):
    now = datetime.datetime(2026, 11, 2, 6, 30)                         # lunes
    monkeypatch.setattr(horario, "items", [{"dia": 0, "inicio": "07:00", "fin": "07:55", "curso": "7A", "materia": "Matemáticas"}])
    monkeypatch.setitem(jv.settings, "weather_city", "")
    monkeypatch.setattr(jv, "agenda", lambda scope, with_day=True: ["a las 10, consejo académico"])
    monkeypatch.setattr(jv, "attention_items", lambda now=None: [])
    compromisos.add("entregar las planillas hoy", now=now)
    txt = jv.morning_brief_text(now)
    assert "Buenos días" in txt and "7A Matemáticas" in txt and "consejo académico" in txt and "Entregar las planillas" in txt
    sent, voices = [], []
    monkeypatch.setattr(jv, "telegram_ready", lambda: True)
    monkeypatch.setattr(jv, "telegram_send", lambda t: sent.append(t) or True)
    monkeypatch.setattr(jv, "tg_send_voice", lambda t: voices.append(t) or True)
    monkeypatch.setattr(jv, "morning_brief_text", lambda now=None: "Buenos días. Hoy…")
    assert jv.send_morning_voice() and voices == ["Buenos días. Hoy…"] and sent[0].startswith("☀️")


def test_estilo_al_escribir(jv, limpio, monkeypatch):
    monkeypatch.setitem(jv.settings, "style_learn", True)
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: "- Saluda con «Cordial saludo».\n- Se despide con «Quedo atenta».")
    real = threading.Thread

    class T(real):
        def start(self):
            self.run()
    monkeypatch.setattr(threading, "Thread", T)
    for i in range(3):
        jv.learn_style(f"Cordial saludo, señora Marta. Le escribo para informarle sobre la reunión número {i} del consejo. Quedo atenta.")
    monkeypatch.setattr(threading, "Thread", real)
    assert "Cordial saludo" in estilo.data["perfil"] and "Cordial saludo" in jv.style_ctx()
    jv._rec.clear()
    jv.process_command("¿cómo escribo?")
    assert "Así escribes" in jv._rec.said()
    jv.process_command("olvida mi estilo")
    assert estilo.data["perfil"] == "" and jv.style_ctx() == ""


def test_estilo_va_en_los_correos():
    import nucleo.personal as p
    import nucleo.conecta as c
    import nucleo.familia as f
    for mod in (p, c, f):
        assert "J.style_ctx()" in open(mod.__file__, encoding="utf-8").read(), mod.__name__


def test_retroalimentacion_de_texto(jv, limpio, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Juan Pérez"]})
    monkeypatch.setitem(jv.aula.data, "activo", "7A")
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "n.json"))
    monkeypatch.setattr(seguimiento, "data", {})
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps({
        "fortalezas": ["Idea clara"], "mejorar": ["Argumenta más"], "errores": [{"dice": "nesecitan", "debe_decir": "necesitan"}],
        "nota": "3,8", "comentario": "Buen inicio, Juan."}))
    said = []
    monkeypatch.setattr(jv, "notify", lambda text, origin="JARVIS": said.append(text))
    jv._tl.capture = []
    try:
        jv.process_command("retroalimenta este texto de Juan de 7A: " + TEXTO)
    finally:
        jv._tl.capture = None
    assert "Juan Pérez" in said[-1] and "3,8" in said[-1]
    a = jv.aprobaciones.latest()
    assert a["titulo"].startswith("Guardar 3,8 a Juan Pérez (7A)")
    jv.process_command("sí")
    for _ in range(100):
        if seguimiento.data.get("7A") and not any(t.name.startswith("aprobacion") and t.is_alive() for t in threading.enumerate()):
            break
        time.sleep(0.02)
    assert seguimiento.average("7A", "Juan Pérez") == 3.8
    if jv.Document is not None:
        doc = next((tmp_path / "Retroalimentación").iterdir())
        text = " ".join(p.text for p in jv.Document(str(doc)).paragraphs)
        assert "Fortalezas" in text and "Texto revisado" in text


def test_retro_valida():
    from nucleo import pulido
    with pytest.raises(ValueError):
        pulido.text_fb_validate({"nota": 9})
    assert pulido.text_fb_validate({"fortalezas": ["x"], "nota": 9})["nota"] is None
