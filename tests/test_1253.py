"""Pruebas de la 12.53: documentos del colegio, convivencia (Ley 1620), portafolio de evidencias y reglas automáticas."""
import datetime
import json
import os

import convivencia as CV
import libro
import portafolio as PF
import reglas as RG


def _inline(jv, monkeypatch):
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    said = []
    monkeypatch.setattr(jv, "notify", lambda m, o="": said.append(m))
    return said


# ---------------------------------------------------------------- 4. documentos del colegio
def test_documentos_del_colegio(jv, monkeypatch, tmp_path):
    libro.configure(str(tmp_path))
    f = tmp_path / "SIEE 2026.txt"
    f.write_text("Capítulo de recuperaciones. " * 3 + "Las actividades de recuperación se presentan en la semana 10 del periodo y la "
                 "nota máxima de recuperación es 3,0. " * 4, encoding="utf-8")
    it = {"id": "x1", "nombre": "SIEE 2026.txt", "tipo": "texto", "ruta": str(f), "t": 9e18}
    monkeypatch.setattr(jv, "_upload_batch", lambda limit=40: [it])
    jv._rec.clear()
    jv.process_command("guárdalo como documento del colegio")
    assert "Guardé «SIEE 2026»" in jv._rec.said() and jv.inst_docs()
    assert libro.search("recuperacion", "Matemáticas") == [] and libro.search("recuperacion", "")  == []   # no se mezcla con clase
    monkeypatch.setitem(jv.state, "ai", "ok")
    seen = {}
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: seen.update(m=msgs[0]["content"]) or "Se presentan en la semana 10 (SIEE 2026, pág. 1).")
    jv._rec.clear()
    jv.process_command("¿qué dice el SIEE sobre las recuperaciones?")
    assert "semana 10" in jv._rec.said() and "pág. 1" in seen["m"] and "<<<INICIO" in seen["m"]
    jv.process_command("¿qué documentos del colegio tienes?")
    assert "SIEE 2026" in jv._rec.said()
    for bid in list(jv.inst_docs()):
        libro.remove(bid)


# ---------------------------------------------------------------- 1. convivencia
def test_convivencia(jv, monkeypatch, tmp_path):
    a = CV.clean({"tipo": "Tipo II", "por_que": "Agresión repetida que causó un golpe.", "pasos": ["Atención en salud", "Informar a acudientes"],
                  "informar_a": ["Coordinación", "Acudientes"], "registro": {"hechos": "Empujón en el descanso"},
                  "citacion_acudiente": "Señor acudiente…"}, "Juan empujó a Pedro")
    assert a["tipo"] == "II" and not a["urgente"] and "tipo II" in CV.spoken(a)
    assert CV.clean({"tipo": "I", "pasos": ["x"]}, "dijo que se quiere morir")["urgente"]
    assert "Decreto 1965" in CV.prompt("x") and "123" in CV.URGENT_TEXT
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.state, "ai", "ok")
    said = _inline(jv, monkeypatch)
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps({"tipo": "II", "por_que": "Agresión repetida.", "urgente": False,
                                                                      "pasos": ["Atención en salud", "Informar a los acudientes"],
                                                                      "informar_a": ["Coordinación"], "registro": {"hechos": "Empujón"},
                                                                      "citacion_acudiente": "Respetado acudiente…", "fuentes": ["Decreto 1965, art. 43"]}))
    jv._rec.clear()
    jv.process_command("situación de convivencia: en el descanso Juan empujó a Pedro y se golpeó la rodilla; es la tercera vez esta semana")
    assert said and "tipo II" in said[-1] and "comité" in said[-1]
    docs = [p for p in os.listdir(tmp_path / "Convivencia") if p.endswith(".docx")]
    import docx
    txt = "\n".join(p.text for p in docx.Document(str(tmp_path / "Convivencia" / docs[0])).paragraphs)
    assert "Pasos del protocolo" in txt and "Respetado acudiente" in txt and "confidencial" in txt
    jv._rec.clear()
    jv.process_command("situación de convivencia: pelea")
    assert "Cuéntame qué pasó" in jv._rec.said()


# ---------------------------------------------------------------- 2. portafolio
def test_portafolio(jv, monkeypatch, tmp_path):
    assert PF.area_of("/d/Planeaciones/Plan de clase fracciones.docx").startswith("Académica · Planeación")
    assert PF.area_of("/d/Boletines/Boletín 7A.pdf").startswith("Administrativa")
    assert PF.area_of("/d/Convivencia/Situación 2026.docx").startswith("Comunitaria")
    for rel in ("Planeaciones/Plan de clase fracciones.docx", "Quices/Quiz de ecuaciones.docx", "Boletines/Boletín 7A.pdf",
                "Respaldo/notas.xlsx"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "ai_chat", lambda *a, **k: json.dumps({"presentacion": "Este año trabajé…",
                                                                    "reflexiones": {"Académica · Planeación y organización": "Planeé con…"}}))
    r = jv.make_portfolio(datetime.date.today() - datetime.timedelta(days=5))
    assert r["n"] == 3 and os.path.exists(r["docx"]) and os.path.exists(r["zip"])        # el respaldo no entra
    import zipfile
    assert len(zipfile.ZipFile(r["zip"]).namelist()) == 3
    said = _inline(jv, monkeypatch)
    jv._rec.clear()
    jv.process_command("arma mi portafolio de evidencias")
    assert said and "Listo tu portafolio" in said[-1]


# ---------------------------------------------------------------- 5. reglas
def test_reglas(jv, monkeypatch, tmp_path):
    r = RG.parse("si alguien saca menos de 3 en un quiz, preparale un refuerzo y avisame")
    assert r == {"evento": "nota_baja", "umbral": 3.0, "filtro": "quiz", "acciones": ["refuerzo", "avisar"]}
    r2 = RG.parse("si un estudiante falta 3 veces seguidas, recuerdame llamar al acudiente")
    assert r2["evento"] == "fallas" and r2["filtro"] == "seguidas" and "acudiente" in r2["acciones"]
    assert RG.parse("cuando alguien saque 5, felicitalo")["acciones"] == ["felicitar"]
    assert RG.parse("si llueve, avisame") is None
    assert RG.grade_matches(r, 2.5, "Quiz 1") and not RG.grade_matches(r, 2.5, "Taller 1") and not RG.grade_matches(r, 3.2, "quiz")
    assert RG.streak({"d3", "d4"}, ["d1", "d2", "d3", "d4"]) == 2 and RG.streak({"d1"}, ["d1", "d2"]) == 0
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    said = _inline(jv, monkeypatch)
    monkeypatch.setattr(jv, "notice_add", lambda *a, **k: None)
    made = []
    monkeypatch.setattr(jv, "generate_material", lambda req, kind=None, **k: made.append(req))
    jv._rec.clear()
    jv.process_command("si alguien saca menos de 3 en un quiz, prepárale un refuerzo y avísame")
    assert "Regla guardada" in jv._rec.said()
    jv.process_command("si un estudiante falta 3 veces seguidas, recuérdame llamar al acudiente")
    jv._rec.clear()
    jv.process_command("¿qué reglas tengo?")
    assert "1) si alguien saca menos de 3 en un quiz" in jv._rec.said() and "2) si alguien falta 3 veces seguidas" in jv._rec.said()
    # las notas que entran se juntan en un solo aviso
    jv.rules_on_grade("7A", "Ana", "Quiz 2", 2.0)
    jv.rules_on_grade("7A", "Luis", "Quiz 2", 2.8)
    jv.rules_on_grade("7A", "Sara", "Quiz 2", 4.5)
    jv._rg["timer"].cancel()
    jv.rules_flush()
    assert len(said) == 1 and "2 estudiante(s)" in said[0] and "Ana (2)" in said[0] and made == ["taller de refuerzo sobre Quiz 2 para 7A"]
    # faltas seguidas
    import aula
    monkeypatch.setitem(aula.data, "asistencia", {"7A": {"2026-11-18": ["Ana"], "2026-11-19": ["Ana", "Luis"], "2026-11-20": ["Ana"],
                                                         "2026-11-21": []}})
    assert jv.rules_absence_tick() == 0                                  # el último día vino
    aula.data["asistencia"]["7A"]["2026-11-21"] = ["Ana"]
    said.clear()
    assert jv.rules_absence_tick() == 1 and "Ana (7A) lleva 4 faltas seguidas" in said[0] and "Mensaje sugerido" in said[0]
    assert jv.rules_absence_tick() == 0                                  # no repite el mismo aviso
    jv.process_command("borra todas las reglas")
    assert jv.rules_list()["reglas"] == []


def test_las_notas_pasan_por_las_reglas(jv, monkeypatch):
    import seguimiento
    got = []
    monkeypatch.setattr(jv, "rules_on_grade", lambda *a, **k: got.append(a))
    monkeypatch.setattr(seguimiento, "save", lambda: None)
    seguimiento.add("7A", "Ana", "Quiz 9", 2.0, origen="hoja")
    assert got and got[-1][:4] == ("7A", "Ana", "Quiz 9", 2.0)
    seguimiento.data["7A"]["Ana"] = [x for x in seguimiento.data["7A"]["Ana"] if x["actividad"] != "Quiz 9"]
