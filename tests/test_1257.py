"""Pruebas de la 12.57: frases reales que antes iban al lugar equivocado o a la IA sin necesidad."""
import datetime

import aula
import comprador
import skills


def _who(jv, monkeypatch, phrase):
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": jv._rec.other.append("job:" + label))
    jv._rec.clear()
    jv.process_command(phrase)
    return jv._rec.who(), jv._rec.said()


def test_alarma_para_manana(jv):
    ten_am = datetime.datetime(2026, 11, 24, 10, 0)
    secs, label = jv.parse_clock_reminder("ponme una alarma para manana a las 6", now=ten_am)
    assert ten_am + datetime.timedelta(seconds=secs) == datetime.datetime(2026, 11, 25, 6, 0) and label == "Alarma"
    secs, label = jv.parse_clock_reminder("recuerdame pasado manana a las 3 de la tarde llamar a mama", now=ten_am)
    assert ten_am + datetime.timedelta(seconds=secs) == datetime.datetime(2026, 11, 26, 15, 0) and label == "llamar a mama"
    secs, label = jv.parse_clock_reminder("recuerdame a las 3 de la tarde llamar a mama", now=ten_am)
    assert ten_am + datetime.timedelta(seconds=secs) == datetime.datetime(2026, 11, 24, 15, 0)
    _, label = jv.parse_clock_reminder("despiertame a las 5 de la manana", now=ten_am)
    assert label == "Despertar"


def test_cuanto_falta_no_es_temporizador(jv, monkeypatch):
    who, said = _who(jv, monkeypatch, "cuánto falta para el puente festivo")
    assert who == "CALENDARIO" and "festivo" in said.lower()
    who, _ = _who(jv, monkeypatch, "cuánto falta")
    assert who == "TIMER"


def test_recomendar_no_es_comprar():
    assert comprador.parse_request("qué me recomiendas ver en netflix") is None
    assert comprador.parse_request("qué celular me recomiendas de 800 mil")["producto"]


def test_queja_no_es_memoria(jv, monkeypatch):
    who, _ = _who(jv, monkeypatch, "eso no era lo que te pedí")
    assert who.startswith("IA")
    who, _ = _who(jv, monkeypatch, "qué te pedí ayer sobre el examen")
    assert who == "MEMORIA"


def test_skills_nuevas():
    assert skills.parse("sube el volumen al máximo") == ("volumen", {"accion": "fijar", "nivel": 100})
    assert skills.parse("volumen al mínimo") == ("volumen", {"accion": "fijar", "nivel": 10})
    assert skills.parse("sube el volumen") == ("volumen", {"accion": "subir"})
    assert skills.parse("cuánta memoria ram estoy usando") == ("estado_sistema", {})
    assert skills.parse("pon el modo oscuro") == ("tema_windows", {"modo": "oscuro"})
    assert skills.parse("activa el modo claro") == ("tema_windows", {"modo": "claro"})
    assert skills.parse("modo clase") is None


def test_tema_windows(monkeypatch):
    calls = []

    class R:
        returncode = 0
    monkeypatch.setattr(skills.os, "name", "nt")
    monkeypatch.setattr(skills.subprocess, "run", lambda args, **k: (calls.append(args), R())[1])
    assert skills.REGISTRY["tema_windows"].fn(modo="oscuro") == "Listo, Windows en modo oscuro."
    assert all(c[-2] == "0" for c in calls) and len(calls) == 2


def test_gastos_y_lectura(jv, monkeypatch):
    who, said = _who(jv, monkeypatch, "anota que gasté 15 mil en almuerzo")
    assert who == "GASTOS"
    who, said = _who(jv, monkeypatch, "cuánto gasté este mes")
    assert who == "GASTOS" and "Este mes llevas" in said
    who, _ = _who(jv, monkeypatch, "léeme este texto")
    assert who == "read_selection_aloud"


def test_clase(jv, monkeypatch):
    monkeypatch.setitem(jv.material_job, "busy", False)          # el trabajo no corre aquí: que no quede «ocupado»
    assert aula.detect_kind("preparame la clase de ecuaciones para noveno") == "plan"
    assert aula.detect_kind("que clase tengo ahora") is None
    who, _ = _who(jv, monkeypatch, "prepárame la clase de ecuaciones para noveno")
    assert who == "job:Preparando material de clase"
    who, _ = _who(jv, monkeypatch, "cuántas horas de clase tengo hoy")
    assert who == "HORARIO"


def test_foto(jv, monkeypatch, tmp_path):
    src = tmp_path / "cam.png"
    src.write_bytes(b"png")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "out"))
    monkeypatch.setattr(jv, "capture_camera", lambda wait=0.0: str(src))
    monkeypatch.setattr(jv, "card", lambda *a, **k: None)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    jv._rec.clear()
    jv.process_command("tómame una foto")
    assert "Lista" in jv._rec.said() and len(list((tmp_path / "out" / "Fotos").iterdir())) == 1
    monkeypatch.setattr(jv, "capture_camera", lambda wait=0.0: (_ for _ in ()).throw(ValueError("No pude abrir la cámara.")))
    jv._rec.clear()
    jv.process_command("toma una foto con la cámara")
    assert "No pude abrir" in jv._rec.said()


def test_charla_sin_enrutador(jv):
    for t in ("te quiero jarvis", "eres muy lento", "estoy aburrido", "buenos dias jarvis", "no entendiste"):
        assert jv.p57_chatty(t), t
    for t in ("abre word", "estoy aburrido pon musica", "dime el clima", "hola abre youtube"):
        assert not jv.p57_chatty(t), t
    jv._rec.clear()
    jv.process_command("te quiero jarvis")
    assert jv._rec.ai and not any(route for _, route in jv._rec.ai)        # respuesta directa, sin enrutador
