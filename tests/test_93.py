"""Pruebas de la 9.3: ¿qué necesita mi atención? y su pulso, compromisos, correos por responder, lectura nivelada y
material desde un enlace o un texto pegado."""
import datetime

import pytest

import atencion
import aula
import compromisos
import horario
import notas


@pytest.fixture
def limpio(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(compromisos, "_path", str(tmp_path / "c.json"))
    monkeypatch.setattr(compromisos, "data", {"items": [], "respondidos": [], "descartados": []})
    monkeypatch.setattr(notas, "pending", lambda: [])
    monkeypatch.setattr(horario, "items", [])
    monkeypatch.setitem(jv.mail_cache, "msgs", [])
    monkeypatch.setitem(jv.aula.data, "cursos", {})
    monkeypatch.setattr(jv.seguimiento, "data", {})
    monkeypatch.setattr(jv.errores, "recent", lambda n=50: [])
    for a in jv.aprobaciones.pending():
        jv.resolve_approval(a["id"], False, "prueba")
    return tmp_path


def test_compromisos_por_voz(jv, limpio):
    rec = jv._rec
    rec.clear()
    jv.process_command("quedé en enviarle el taller a la coordinadora mañana")
    assert "Anotado el compromiso para el" in rec.said()
    x = compromisos.pending()[0]
    assert x["texto"].startswith("Enviarle el taller") and x["fecha"] == (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    rec.clear()
    jv.process_command("¿qué compromisos tengo?")
    assert "1 compromiso" in rec.said() and "(mañana)" in rec.said()
    rec.clear()
    jv.process_command("ya le envié el taller a la coordinadora")
    assert "cumplido" in rec.said() and not compromisos.pending()


def test_recordatorio_de_compromisos(jv, limpio, monkeypatch):
    alerts = []
    monkeypatch.setattr(jv, "alert", lambda text, origin="JARVIS": alerts.append(text))
    compromisos.add("llamar a la mamá de Juan mañana", now=datetime.datetime(2026, 11, 2, 9, 0))
    jv._co_warned.clear()
    assert jv.commitments_tick(datetime.datetime(2026, 11, 2, 12, 0)) == []        # el día antes, antes de las 5 p. m.
    assert len(jv.commitments_tick(datetime.datetime(2026, 11, 2, 17, 30))) == 1
    assert jv.commitments_tick(datetime.datetime(2026, 11, 2, 18, 0)) == []        # una sola vez
    assert len(jv.commitments_tick(datetime.datetime(2026, 11, 3, 7, 5))) == 1     # y el mismo día
    assert alerts[0].startswith("Mañana tienes")


def test_correos_por_responder(jv, limpio):
    msgs = [{"msgid": "<a>", "de": "coord@c.co", "de_nombre": "Coordinadora", "asunto": "Planillas", "texto": "Quedo atenta a su respuesta.", "masivo": False},
            {"msgid": "<b>", "de": "news@x.co", "de_nombre": "Boletín", "asunto": "Ofertas", "texto": "¿Ya viste?", "masivo": True},
            {"msgid": "<c>", "de": "ana@c.co", "de_nombre": "Ana", "asunto": "Gracias", "texto": "Gracias por todo.", "masivo": False}]
    jv.mail_cache["msgs"] = msgs
    assert [m["msgid"] for m in compromisos.to_answer(msgs)] == ["<a>"]
    jv._rec.clear()
    jv.process_command("¿qué correos debo responder?")
    assert "Coordinadora" in jv._rec.said()
    jv.process_command("ese correo de coordinadora no necesita respuesta")
    assert compromisos.to_answer(msgs) == []


def test_que_necesita_mi_atencion(jv, limpio, monkeypatch):
    now = datetime.datetime.now().replace(second=0, microsecond=0)
    compromisos.add("entregar planillas hoy")
    monkeypatch.setattr(notas, "pending", lambda: [{"id": "n1", "texto": "comprar marcadores", "fecha": "2020-01-01", "hora": ""}])
    jv.request_approval("x", "Publicar el anuncio", "d", on_ok=lambda: None, ttl=60)
    items = jv.attention_items(now)
    keys = [x["k"].split(":")[0] for x in items]
    assert {"ap", "co", "no"} <= set(keys) and all(x["p"] == 1 for x in items if x["k"].startswith(("ap", "co", "no")))
    jv._rec.clear()
    jv.process_command("¿qué necesita mi atención?")
    assert "para ya" in jv._rec.said() and "Publicar el anuncio" in jv._rec.said()
    for a in jv.aprobaciones.pending():
        jv.resolve_approval(a["id"], False, "prueba")


def test_pulso_solo_avisa_lo_nuevo(jv, limpio, monkeypatch):
    sent = []
    monkeypatch.setattr(jv, "notice_add", lambda text, kind="aviso", origin="": sent.append(text))
    monkeypatch.setattr(jv, "push_chat", lambda *a, **k: None)
    monkeypatch.setitem(jv.settings, "attention_pulse", True)
    monkeypatch.setitem(jv.settings, "attention_from", 7)
    monkeypatch.setitem(jv.settings, "attention_to", 19)
    monkeypatch.setitem(jv.settings, "attention_phone", False)
    jv._pulse.update(seen=set(), last=0.0)
    compromisos.add("entregar planillas hoy")
    t = datetime.datetime.combine(datetime.date.today(), datetime.time(10, 0))
    if t.weekday() >= 5:
        monkeypatch.setitem(jv.settings, "attention_weekend", True)
    assert len(jv.attention_tick(t)) == 1 and "Entregar planillas" in sent[-1]
    assert jv.attention_tick(t + datetime.timedelta(hours=2)) == []                # ya avisado
    assert jv.attention_tick(datetime.datetime.combine(t.date(), datetime.time(22, 0))) == []   # fuera del horario
    assert atencion.spoken([]).startswith("Nada urgente")


def test_lectura_nivelada():
    assert aula.detect_kind("haz una lectura nivelada sobre los volcanes para sexto") == "lectura"
    m = aula.validate("lectura", {"titulo": "Volcanes", "niveles": [
        {"nivel": "Básico", "texto": "Un volcán es…", "vocabulario": [{"palabra": "magma", "significado": "roca fundida"}],
         "resumen": "…", "preguntas": ["¿Qué es un volcán?"]},
        {"texto": "Los volcanes…"}, {"texto": "La vulcanología…"}, {"texto": "sobra"}]})
    assert [x["nivel"] for x in m["niveles"]] == ["Básico", "Intermedio", "Avanzado"]
    assert "tres niveles" in aula.build_prompt("lectura", "x")


def test_lectura_en_word(jv, tmp_path):
    if jv.Document is None:
        pytest.skip("sin python-docx")
    m = aula.validate("lectura", {"titulo": "Volcanes", "niveles": [{"nivel": "Básico", "texto": "Uno.\nDos.", "preguntas": ["¿A?"]},
                                                                    {"texto": "B"}, {"texto": "C"}]})
    path = aula.build_docx("lectura", m, str(tmp_path), jv.Document)
    text = " ".join(p.text for p in jv.Document(path).paragraphs)
    assert "Nivel Básico" in text and "Nivel Avanzado" in text and "Resúmenes" in text


def test_material_desde_enlace_y_texto(jv, monkeypatch):
    made = []
    monkeypatch.setattr(jv, "generate_material", lambda req, kind=None, count=None, grade="", topic="": made.append((kind, req)))
    monkeypatch.setattr(jv, "_get_text", lambda url, timeout=12: "<html><body><p>" + "El ciclo del agua tiene evaporación y condensación. " * 20 + "</p></body></html>")
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="x": fn())
    jv.process_command("haz un quiz con este artículo https://es.wikipedia.org/wiki/Ciclo_del_agua")
    assert made[-1][0] == "quiz" and "evaporación" in made[-1][1] and "es.wikipedia.org" in made[-1][1]
    jv.process_command("nivela este texto: " + "Los volcanes son aberturas de la tierra por donde sale magma. " * 6)
    assert made[-1][0] == "lectura" and "Basado en este texto" in made[-1][1]


