"""Pruebas de la 10.0: kit para colegas y reuniones de área (agenda y acta)."""
import json
import os
import time

import pytest

import banco
import clasevivo
import compromisos
import habilidades
import kit
import lecciones
import reunion
import rutinas


@pytest.fixture
def mio(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "out"))
    monkeypatch.setitem(jv.settings, "aula_docente", "Profe Diana")
    monkeypatch.setattr(rutinas, "_path", str(tmp_path / "rutinas.json"))
    monkeypatch.setattr(rutinas, "routines", [dict(r) for r in rutinas.DEFAULTS] +
                        [{"nombre": "Inicio del día", "frases": ["inicio del día"], "pasos": ["abre el correo", "dime el clima"], "cuando": "07:00"}])
    monkeypatch.setattr(lecciones, "_path", str(tmp_path / "lecciones.json"))
    monkeypatch.setattr(lecciones, "items", [{"id": "a1", "texto": "Los quices siempre con 5 preguntas", "origen": "tú", "fecha": "2026-10-01"}])
    monkeypatch.setattr(clasevivo, "_path", str(tmp_path / "clases.json"))
    monkeypatch.setattr(clasevivo, "data", {"planes": [{"tema": "Fracciones", "titulo": "Plan", "objetivo": "x", "curso": "7A",
                                                        "momentos": [{"nombre": "Inicio", "duracion": "10 min", "actividades": "Pizza"}]}],
                                            "actividades": [{"tema": "Fracciones", "curso": "7A", "actividad": "Tiras de papel", "resultado": 90,
                                                             "fecha": "2026-10-02"},
                                                            {"tema": "Decimales", "curso": "7A", "actividad": "Mal", "resultado": 30, "fecha": "2026-10-03"}]})
    monkeypatch.setattr(banco, "_path", str(tmp_path / "banco.json"))
    monkeypatch.setattr(banco, "items", [{"enunciado": "¿1/2 + 1/2?", "opciones": ["1", "2"], "respuesta": "a", "explicacion": "",
                                          "tema": "fracciones", "grado": "7", "usos": 0}])
    (tmp_path / "hab").mkdir()
    monkeypatch.setattr(habilidades, "_dir", str(tmp_path / "hab"))
    monkeypatch.setattr(habilidades, "skills", [])
    monkeypatch.setattr(compromisos, "_path", str(tmp_path / "c.json"))
    monkeypatch.setattr(compromisos, "data", {"items": [], "respondidos": [], "descartados": []})
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    jv.meeting.update(st=None, agenda=[], agenda_nombre="")
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    return tmp_path


def test_kit_exporta_sin_datos_de_estudiantes(jv, mio):
    jv._rec.clear()
    jv.process_command("exporta mi kit para colegas")
    s = jv._rec.said()
    assert "1 rutina" in s and "1 lección" in s and "1 actividad que funcionó" in s and "1 pregunta del banco" in s
    path = [os.path.join(r, f) for r, _, fs in os.walk(jv.settings["output_dir"]) for f in fs][0]
    raw = open(path, encoding="utf-8").read()
    k = json.loads(raw)
    assert k["autor"] == "Profe Diana" and [r["nombre"] for r in k["rutinas"]] == ["Inicio del día"]
    assert "cuando" not in k["rutinas"][0] and "curso" not in json.dumps(k["planes"]) and "Mal" not in raw
    assert kit.parse(raw)["autor"] == "Profe Diana"


def test_kit_rechaza_lo_que_no_es_kit():
    with pytest.raises(ValueError):
        kit.parse("no es json")
    with pytest.raises(ValueError):
        kit.parse(json.dumps({"tipo": "otra cosa"}))
    with pytest.raises(ValueError, match="estudiantes"):
        kit.parse(json.dumps({"tipo": kit.KIND, "lecciones": [], "asistencia": {"7A": {}}}))


def test_kit_importa_y_suma(jv, mio):
    ajeno = {"tipo": kit.KIND, "autor": "Profe Luis", "fecha": "2026-10-20",
             "rutinas": [{"nombre": "Cierre del día", "frases": ["cierre del día"], "pasos": ["silencia las notificaciones"], "cuando": "17:00"},
                         {"nombre": "Inicio del día", "frases": [], "pasos": ["x"]}],
             "habilidades": [{"nombre": "Wikipedia", "frases": ["busca {tema} en wikipedia"], "accion": "abrir",
                              "url": "https://es.wikipedia.org/wiki/{tema}"}],
             "lecciones": ["Nunca uses la palabra alumnos", "Los quices siempre con 5 preguntas"],
             "actividades": [{"tema": "Ecosistemas", "actividad": "Salida al patio con lupas", "resultado": 88}],
             "planes": [{"tema": "Ecosistemas", "titulo": "Plan ecosistemas", "momentos": []}],
             "banco": [{"enunciado": "¿Qué es un productor?", "opciones": ["Planta", "León"], "respuesta": "a", "tema": "ecosistemas", "grado": "6"}]}
    r = jv.handle_kit({"preview": json.dumps(ajeno)})
    assert r["ok"] and "Profe Luis" in r["summary"] and "2 rutinas" in r["summary"]
    r = jv.handle_kit({"import": json.dumps(ajeno)})
    assert r["ok"] and "1 rutina," in r["summary"] and "1 lección" in r["summary"]
    nueva = [x for x in rutinas.routines if x["nombre"] == "Cierre del día"][0]
    assert nueva["cuando"] == ""                                        # nunca se lanza sola
    assert [h["nombre"] for h in habilidades.skills] == ["Wikipedia"]
    assert lecciones.items[-1]["origen"] == "kit de Profe Luis"
    assert clasevivo.worked("ecosistemas")[0]["actividad"].startswith("Salida al patio")
    assert any(q["enunciado"] == "¿Qué es un productor?" for q in banco.items)
    assert "no trae nada" in jv.handle_kit({"import": json.dumps(ajeno)})["summary"]


def test_acta_puro():
    st = reunion.new("Reunión de área")
    reunion.add(st, "Asistentes: Ana Pérez, Luis Gómez y Marta")
    reunion.add(st, "Se revisaron los resultados del periodo")
    reunion.add(st, "Acuerdo: la salida pedagógica será el 20 de noviembre")
    reunion.add(st, "yo me encargo de consolidar el informe para el lunes")
    assert st["asistentes"] == ["Ana Pérez", "Luis Gómez", "Marta"] and len(st["puntos"]) == 1
    assert st["acuerdos"] == ["La salida pedagógica será el 20 de noviembre"]
    assert st["tareas"][0] == {"quien": "Yo", "que": "Consolidar el informe para el lunes", "cuando": "lunes"}


def test_reunion_de_area_por_voz(jv, mio, monkeypatch):
    monkeypatch.setitem(jv.state, "ai", "ok")
    calls = []

    def fake(msgs, **k):
        calls.append(msgs[0]["content"])
        if "agenda" in msgs[0]["content"].lower() and "orden del día" in msgs[0]["content"].lower() and "Notas:" not in msgs[0]["content"]:
            return json.dumps({"agenda": ["Verificación de asistencia (5 min)", "Informe de notas (20 min)", "Salida pedagógica (15 min)", "Varios"]})
        return json.dumps({"desarrollo": ["Se revisaron los resultados del periodo y se acordó la salida."]})
    monkeypatch.setattr(jv, "ai_chat", fake)
    jv._rec.clear()
    jv.process_command("prepara la agenda de la reunión de área sobre informe de notas y salida pedagógica")
    assert "Informe de notas" in jv._rec.said() and len(jv.meeting["agenda"]) == 4
    jv.process_command("empieza el acta de la reunión de área")
    assert jv.meeting["st"] and jv.meeting["st"]["agenda"][1].startswith("Informe")
    assert os.path.exists(os.path.join(mio, "reunion.json"))
    jv.process_command("asistentes: Ana Pérez, Luis Gómez y Marta")
    jv.process_command("anota en el acta que se revisaron los resultados del periodo")
    jv.process_command("acuerdo: la salida pedagógica será el 20 de noviembre")
    jv.process_command("Luis se encarga de la circular para padres")
    jv.process_command("yo me encargo de consolidar el informe para el lunes")
    jv._rec.clear()
    jv.process_command("¿qué llevo en el acta?")
    assert "3 asistentes, 1 notas, 1 acuerdos y 2 compromisos" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("termina el acta")
    for _ in range(200):
        if "Listo el acta" in jv._rec.said():
            break
        time.sleep(0.02)
    assert "Listo el acta" in jv._rec.said() and "1 tuyos" in jv._rec.said()
    files = [f for _, _, fs in os.walk(jv.settings["output_dir"]) for f in fs]
    assert any(f.startswith("Acta Reunión de área") for f in files) and any(f.startswith("Agenda") for f in files)
    assert compromisos.pending()[-1]["texto"].startswith("Consolidar el informe")
    assert jv.meeting["st"] is None
    assert jv.meeting_voice("anota en el acta que algo", "anota en el acta que algo") is False      # ya no hay acta abierta
