"""Pruebas de la 9.9: personalidad según el momento, color del día del reactor y retrospectiva del año."""
import datetime
import os
import threading
import time

import pytest

import animo
import clasevivo
import diarioclase
import horario
import informes
import retro
import seguimiento


def _wait_approvals():
    for _ in range(150):
        if not any(t.name.startswith("aprobacion") and t.is_alive() for t in threading.enumerate()):
            return
        time.sleep(0.02)


def test_personalidad_pura():
    lunes9 = datetime.datetime(2026, 11, 2, 9)
    assert animo.auto_mode(lunes9, True) == "clase"
    assert animo.auto_mode(lunes9, False) == "jornada"
    assert animo.auto_mode(datetime.datetime(2026, 11, 2, 20), False) == "relajado"
    assert animo.auto_mode(datetime.datetime(2026, 11, 7, 9), False) == "relajado"
    assert animo.parse_set("ponte relajado") == "relajado" and animo.parse_set("modo serio") == "jornada"
    assert animo.parse_set("personalidad automatica") == "auto"
    assert animo.parse_set("modo clase") is None and animo.parse_set("modo concentracion") is None    # son rutinas/habilidades


def test_color_del_dia_puro():
    assert animo.day_mood([])[0] == "tranquilo"
    assert animo.day_mood([{"p": 1, "t": "se venció: llamar"}])[0] == "urgente"
    assert animo.day_mood([{"p": 2, "t": "a"}, {"p": 2, "t": "b"}, {"p": 3, "t": "c"}, {"p": 3, "t": "d"}])[0] == "cargado"
    assert animo.day_mood([], "cerraste el periodo") == ("celebracion", "cerraste el periodo")


@pytest.fixture
def base(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "out"))
    monkeypatch.setitem(jv.settings, "retro_year", "")
    jv.persona.update(manual="", until=0, mode="")
    jv._mood.update(t=0.0, mood="tranquilo", why="")
    monkeypatch.setattr(horario, "items", [])
    monkeypatch.setattr(informes, "_path", str(tmp_path / "obs.json"))
    monkeypatch.setattr(informes, "data", {})
    return tmp_path


def test_personalidad_en_el_prompt(jv, base, monkeypatch):
    monkeypatch.setitem(jv.settings, "persona_auto", True)
    now = datetime.datetime.now()
    monkeypatch.setattr(horario, "items", [{"dia": now.weekday(), "inicio": "00:00", "fin": "23:59", "curso": "7A", "materia": "M"}])
    assert "MODO CLASE" in jv.persona_ctx()
    jv.process_command("ponte relajado")
    assert "MODO RELAJADO" in jv.persona_ctx() and "3 horas" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("¿en qué modo estás?")
    assert "relajado" in jv._rec.said() and "lo pusiste tú" in jv._rec.said()
    jv.process_command("personalidad automática")
    assert "MODO CLASE" in jv.persona_ctx()
    jv.tutor["on"] = True
    try:
        assert jv.persona_ctx() == ""                                              # el modo tutor manda
    finally:
        jv.tutor["on"] = False
    monkeypatch.setitem(jv.settings, "persona_auto", False)
    assert jv.persona_ctx() == ""


def test_color_del_dia_y_orbe(jv, base, monkeypatch):
    monkeypatch.setitem(jv.settings, "orb_day_color", True)
    monkeypatch.setattr(jv, "attention_items", lambda now=None: [{"k": "x", "p": 1, "t": "se venció: enviar notas"}])
    events = []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: events.append((ev, data)))
    assert jv.day_mood_now(force=True)[0] == "urgente"
    assert jv.mood_accent() == "ff6b4a" and any(e == "day_mood" for e, _ in events)
    monkeypatch.setattr(jv, "attention_items", lambda now=None: [])
    informes.add("7A", "Ana", "Excelente trabajo", tipo="positiva")
    assert jv.day_mood_now(force=True) == ("celebracion", "1 felicitación hoy")
    jv._rec.clear()
    jv.process_command("¿cómo viene mi día?")
    assert "celebrar" in jv._rec.said()
    monkeypatch.setitem(jv.settings, "orb_day_color", False)
    assert jv.day_mood_now(force=True)[0] == "tranquilo"
    assert jv.mood_accent() == "%02x%02x%02x" % jv.THEMES.get(jv.settings["theme"], jv.THEMES["cyan"])[1]


Y = datetime.date.today().year


def _seg():
    ns = [{"actividad": f"a{i}", "nota": v, "fecha": f"{Y}-0{i + 2}-10", "origen": "voz"} for i, v in enumerate([2.5, 2.8, 3.0, 4.0, 4.2, 4.5])]
    return {"7A": {"Ana Gómez": ns, "Luis": [{"actividad": "q", "nota": 4.0, "fecha": f"{Y}-03-01", "origen": "voz"},
                                              {"actividad": "v", "nota": 3.0, "fecha": f"{Y - 1}-03-01", "origen": "voz"}]}}


def test_retrospectiva_pura():
    obs = {"7A": {"Ana Gómez": [{"fecha": f"{Y}-05-01", "tipo": "positiva", "texto": "x"}]}}
    reg = {"7A": [{"fecha": f"{Y}-02-01", "tema": "Fracciones"}, {"fecha": f"{Y}-03-01", "tema": "Decimales"}], "9B": []}
    acts = [{"tema": "Fracciones", "curso": "7A", "actividad": "Tiras de papel", "resultado": 92, "fecha": f"{Y}-04-01"}]
    s = retro.compute(Y, _seg(), obs, reg, [], acts, [{"estado": "hecho", "creado": f"{Y}-06-01T10:00"}], 3, 5, 40)
    assert s["notas"] == 7 and s["estudiantes"] == 2 and s["n_temas"] == 2 and s["positivas"] == 1 and s["compromisos"] == 1
    assert s["mejoras"][0][:2] == ("Ana Gómez", "7A")
    t = retro.spoken(s)
    assert "diste 2 temas" in t and "Ana Gómez" in t and "Tiras de papel" in t
    assert "Aún no tengo" in retro.spoken(retro.compute(1990, {}, {}, {}, [], [], []))


def test_retrospectiva_por_voz_y_a_fin_de_ano(jv, base, monkeypatch):
    monkeypatch.setattr(seguimiento, "data", _seg())
    monkeypatch.setattr(diarioclase, "data", {"registro": {"7A": [{"fecha": f"{Y}-02-01", "tema": "Fracciones"}]}, "mallas": {}})
    monkeypatch.setattr(clasevivo, "data", {"planes": [], "actividades": []})
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: "Querida profe: qué año.")
    jv._rec.clear()
    jv.process_command("haz mi retrospectiva del año")
    for _ in range(200):
        if "Retrospectiva" in jv._rec.said():
            break
        time.sleep(0.02)
    assert "diste 1 tema" in jv._rec.said() and "Retrospectiva" in jv._rec.said()
    files = [f for _, _, fs in os.walk(jv.settings["output_dir"]) for f in fs]
    assert f"Mi {Y} como docente.docx" in files
    assert jv.retro_tick(datetime.datetime(Y, 10, 30, 10)) is False                 # aún no es fin de año
    d = next(datetime.datetime(Y, 11, x, 10) for x in range(25, 31) if datetime.date(Y, 11, x).weekday() < 5)
    assert jv.retro_tick(d) is True                                                 # fin del año escolar, entre semana
    assert jv.aprobaciones.latest()["titulo"] == f"Tu retrospectiva de {Y}"
    assert jv.retro_tick(datetime.datetime(Y, 12, 1, 10)) is False                  # una vez por año
