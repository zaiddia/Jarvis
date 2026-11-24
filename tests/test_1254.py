"""Pruebas de la 12.54: acta de la comisión de evaluación y promoción, y test y orientación vocacional."""
import json
import os

import comision as CM
import vocacional as VC


def test_casos_de_la_comision():
    st = {"actual": 2.4, "previos": [3.5, 2.9], "vf_proy": 2.9, "vra": 3.6, "pierde": False}
    c = CM.case_of("7A", "Ana", st, 4, ["Recuperación (3)"])
    assert c and "desempeño bajo en el periodo (2.4)" in c["motivos"] and c["faltas"] == 4
    assert CM.case_of("7A", "Luis", {"actual": 4.2, "previos": [4.0], "vf_proy": 4.1, "pierde": False}) is None
    assert "en riesgo de perder" in CM.case_of("7A", "Sara", {"actual": None, "pierde": True})["motivos"][0]
    p = CM.prompt(7, 4, True, [c], "Se promueve con 3,0 en todas las áreas", {"Ana": "entregar taller"})
    assert "Decreto 1290" in p and "último del año" in p and "entregar taller" in p and "Se promueve" in p
    recs, obs, estr = CM.clean({"casos": [{"estudiante": "Ana", "recomendaciones": ["Tutoría semanal"], "compromisos": ["Taller el 1/12"],
                                           "promocion": "a decisión de la comisión"}], "observaciones_generales": "Grupo estable",
                                "estrategias_grado": ["Refuerzo en fracciones"]}, [c])
    assert recs[0]["compromisos"] == ["Taller el 1/12"] and obs == "Grupo estable" and estr == ["Refuerzo en fracciones"]


def test_acta_completa(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "comision_keys", lambda g: ["7A · Matemáticas"])
    monkeypatch.setattr(jv, "course_year", lambda k: {"Ana": {"actual": 2.4, "previos": [3.5, 2.9], "vf_proy": 2.9, "vra": 3.6, "pierde": False},
                                                      "Luis": {"actual": 4.0, "previos": [4.1, 4.0], "vf_proy": 4.0, "vra": None, "pierde": False}})
    monkeypatch.setattr(jv, "_absences", lambda k: {"Ana": 5})
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "inst_docs", lambda: {})
    monkeypatch.setattr(jv, "ai_chat", lambda *a, **k: json.dumps({"casos": [{"estudiante": "Ana", "recomendaciones": ["Tutoría"],
                                                                              "compromisos": ["Entregar el taller de fracciones el 1/12"]}],
                                                                   "estrategias_grado": ["Repaso de fracciones"]}))
    path, recs = jv.comision_acta(7)
    assert len(recs) == 1 and recs[0]["estudiante"] == "Ana" and os.path.exists(path)
    import docx
    txt = "\n".join(p.text for p in docx.Document(path).paragraphs)
    assert "Comisión de evaluación y promoción" in txt and "Entregar el taller de fracciones" in txt and "Decreto 1290" in txt
    # la próxima acta verifica esos compromisos
    seen = {}
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: seen.update(p=msgs[0]["content"]) or "{}")
    jv.comision_acta(7)
    assert "Entregar el taller de fracciones" in seen["p"]
    # por voz
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    said = []
    monkeypatch.setattr(jv, "notify", lambda m, o="": said.append(m))
    jv._rec.clear()
    jv.process_command("prepara el acta de la comisión de evaluación de séptimo")
    assert said and "grado 7, 1 caso" in said[-1]


def test_test_vocacional_puro():
    assert len(VC.QUESTIONS) == 30 and {k for k, _ in VC.QUESTIONS} == set("RIASEC")
    ans = [4 if k == "S" else 3 if k == "A" else 1 for k, _ in VC.QUESTIONS]
    p = VC.score(ans)
    assert p["S"] == 100 and p["A"] == 75 and VC.code(p).startswith("SA")
    assert "social" in VC.describe(p).lower() and "licenciaturas" in VC.describe(p)
    assert VC.match_student("ana gomez", ["Ana Gómez Ruiz", "Luis Pérez"]) == "Ana Gómez Ruiz"
    assert VC.match_student("Ana", ["Ana Gómez", "Ana Ruiz"]) == ""                  # ambiguo: que escriba el apellido
    assert "SNIES" in VC.report_prompt("Ana", p) and "No inventes" in VC.report_prompt("Ana", p)


def test_test_vocacional_en_el_celular(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "_need_lan", lambda: False)
    monkeypatch.setattr(jv, "_open_projector", lambda: None)
    monkeypatch.setattr(jv, "_resolve_course", lambda s: "11A" if s else "")
    import aula
    monkeypatch.setattr(aula, "students", lambda c: ["Ana Gómez", "Luis Pérez"])
    jv._rec.clear()
    jv.process_command("abre el test vocacional para 11A")
    assert "proyector" in jv._rec.said()
    code = jv.voc["last"]
    c = jv.mobile_app.test_client()
    assert "Test de intereses" in c.get(f"/voc/{code}").get_data(as_text=True)
    bad = c.post(f"/voc/{code}/enviar", json={"nombre": "Pepito", "respuestas": [2] * 30}).get_json()
    assert not bad["ok"] and "lista del curso" in bad["msg"]
    ans = [4 if k == "I" else 1 for k, _ in VC.QUESTIONS]
    ok = c.post(f"/voc/{code}/enviar", json={"nombre": "ana gomez", "respuestas": ans}).get_json()
    assert ok["ok"] and "investigador" in ok["texto"].lower()
    assert jv.voc_data()["11A"]["Ana Gómez"]["codigo"].startswith("I")
    jv._rec.clear()
    jv.process_command("cierra el test vocacional")
    assert "1 estudiantes" in jv._rec.said() and c.get(f"/voc/{code}").status_code == 404
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "ai_chat", lambda *a, **k: json.dumps({"mensaje": "Te interesa investigar.", "carreras": [
        {"nombre": "Biología", "tipo": "profesional", "por_que": "Te gusta experimentar"}], "este_anio": ["Visita un laboratorio"],
        "rutas": ["Universidad pública"]}))
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    said = []
    monkeypatch.setattr(jv, "notify", lambda m, o="": said.append(m))
    jv.process_command("orientación vocacional para Ana")
    assert said and "Ana Gómez" in said[-1]
    assert os.path.exists(tmp_path / "Orientación vocacional" / "11A" / "Ana Gómez.docx")
