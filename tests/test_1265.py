"""Pruebas de la 12.65: estafas, contratos, exposiciones, diagnóstico, diplomas, renta, salidas, proyectos y cronograma."""
import datetime
import json
import os

import clausura as CL
import diagnostico as DG
import estafas as EF
import exposicion as EX
import renta as RT


# ---------------------------------------------------------------- 1. estafas (puro)
def test_senales_de_estafa():
    msg = ("Bancolombia: su cuenta será bloqueada en las próximas 24 horas. Ingrese aquí bit.ly/xx y escriba la clave "
           "dinámica que le llegó.")
    keys = {k for k, _w, _y in EF.signals(msg)}
    assert {"claves", "urgencia", "enlace", "entidad"} <= keys and EF.local_verdict(EF.signals(msg)) == "estafa"
    fam = "Hola ma, este es mi nuevo número, préstame 300 mil por Nequi que te devuelvo mañana"
    assert EF.local_verdict(EF.signals(fam)) == "estafa"
    assert EF.local_verdict(EF.signals("Recuerda la reunión de padres el viernes a las 7")) == "sin señales"
    assert "caivirtual" in EF.local_text(EF.signals(msg))


def test_estafa_por_voz(jv, monkeypatch):
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    monkeypatch.setitem(jv.state, "ai", "ok")
    seen = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: (seen.append(msgs), "ESTAFA: pide la clave.")[1])
    jv._rec.clear()
    jv.process_command("¿Esto es una estafa? Bancolombia: su cuenta será bloqueada, ingrese a bit.ly/abc con su clave")
    assert "ESTAFA" in jv._rec.said()
    assert "bit.ly/abc" in seen[-1][1]["content"] and "pide claves" in seen[-1][0]["content"]
    monkeypatch.setitem(jv.state, "ai", "off")                                  # sin IA, igual responde con las señales
    jv._rec.clear()
    jv.process_command("es una estafa? Hola ma, este es mi nuevo número, consigna 200 mil por Nequi")
    assert "pinta de estafa" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("¿esto es una estafa?")
    assert "Pégame el mensaje" in jv._rec.said()


def test_contrato_y_botones(jv, monkeypatch):
    its = [{"tipo": "pdf", "nombre": "contrato arriendo.pdf", "id": "x"}]
    assert {a["a"] for a in jv.d65_card_actions(its)} == {"contrato"}
    assert {a["a"] for a in jv.d65_card_actions([{"tipo": "imagen", "nombre": "captura.png"}])} == {"estafa"}
    assert {a["a"] for a in jv.d65_card_actions([{"tipo": "pdf", "nombre": "Certificado ingresos 2025.pdf"}])} == {"contrato", "renta"}
    assert {a["a"] for a in jv.d65_card_actions([{"tipo": "video", "nombre": "expo.mp4"}])} == {"exposicion"}
    asked = []
    monkeypatch.setattr(jv, "ask_files", lambda its, q: (asked.append(q), "QUÉ ES: arriendo")[1])
    jv._rec.clear()
    jv.d65_attach(its, "contrato")
    assert "Ley 820 de 2003" in asked[-1] and "arriendo" in jv._rec.said()


# ---------------------------------------------------------------- 2. exposiciones
def test_exposicion_puro():
    raw = json.dumps({"criterios": [{"nombre": "Dominio del tema", "nota": 4.5, "evidencia": "min 1", "mejorar": "x"},
                                    {"nombre": "Claridad y organización", "nota": "4,0"}, {"nombre": "Expresión oral", "nota": 3.0},
                                    {"nombre": "Lenguaje corporal", "nota": 2.5}, {"nombre": "Apoyo visual y tiempo", "nota": 4.0}],
                      "fortalezas": ["seguro"], "comentario_estudiante": "Muy bien."})
    d = EX.parse("```json\n" + raw + "\n```")
    assert d["nota"] == round((4.5 * 30 + 4 * 20 + 3 * 20 + 2.5 * 15 + 4 * 15) / 100, 1)
    assert "lenguaje corporal" in EX.spoken(d, "Ana") and "La nota final la pones tú" in EX.spoken(d)
    assert "RÚBRICA" in EX.prompt("Ana", "fotosíntesis") and "Contacto visual" not in EX.prompt(rubric_custom="Contacto visual: x")[:10]


def test_exposicion_con_video(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    vid = tmp_path / "expo.mp4"
    vid.write_bytes(b"v" * 100)
    monkeypatch.setattr(jv, "_gemini_for_stt", lambda: {"key": "g", "model": "gemini-x"})
    monkeypatch.setattr(jv, "_d65_small_video", lambda src: str(vid))
    sent = []
    resp = json.dumps({"criterios": [{"nombre": n, "nota": 4.0} for n, _w, _d in EX.RUBRIC], "comentario_estudiante": "Bien."})
    monkeypatch.setattr(jv, "_post", lambda url, h, body, opt=(), timeout=0: (sent.append((url, body)), {"x": 1})[1])
    monkeypatch.setattr(jv, "_gemini_text", lambda data, strip=True: resp)
    monkeypatch.setattr(jv, "_with_fallback", lambda cfg, fn: fn(cfg))
    d, path = jv.expo_evaluate({"ruta": str(vid), "nombre": "expo.mp4"}, "Ana Ruiz", "la célula")
    assert d["nota"] == 4.0 and os.path.exists(path)
    assert sent[-1][1]["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "video/mp4"
    assert ":generateContent" in sent[-1][0]


def test_exposicion_por_voz_sin_video(jv, monkeypatch):
    monkeypatch.setattr(jv.adjuntos, "recent", lambda s=1800, n=6: [])
    jv._rec.clear()
    jv.process_command("evalúa esta exposición de Juan")
    assert "Súbeme el video" in jv._rec.said()


# ---------------------------------------------------------------- 3. diagnóstico
QS = [{"competencia": c, "enunciado": f"p{i}", "opciones": ["a", "b", "c", "d"], "correcta": i % 4, "dba": ""}
      for i, c in enumerate(["Números"] * 4 + ["Geometría"] * 4)]


def test_diagnostico_puro():
    assert len(DG.parse(json.dumps({"preguntas": QS + [{"enunciado": "mala", "opciones": ["a"], "correcta": 0}]}))) == 8
    sc = DG.score(QS, [q["correcta"] for q in QS[:4]] + [None] * 4)
    assert sc["aciertos"] == 4 and sc["por_comp"]["Números"] == (4, 4) and sc["por_comp"]["Geometría"] == (0, 4)
    res = {f"E{i}": DG.score(QS, [q["correcta"] if j < i else None for j, q in enumerate(QS)]) for i in range(9)}
    sm = DG.course_summary(res)
    assert sm["comp"]["Números"] > sm["comp"]["Geometría"] and "E0" in sm["refuerzo"]["Geometría"]
    assert sorted(sum(sm["grupos"], [])) == sorted(res) and "Geometría".lower() in DG.spoken(sm, "7A")


def test_diagnostico_flujo(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps({"preguntas": QS}))
    key, qs, path = jv.diag_create("Matemáticas", 7)
    assert key == "matemáticas|7" and len(qs) == 8 and os.path.exists(path)
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Ana Ruiz", "Luis Gómez"]})
    monkeypatch.setattr(jv, "_need_lan", lambda: False)
    monkeypatch.setattr(jv, "_open_projector", lambda: None)
    monkeypatch.setattr(jv, "_resolve_course", lambda s: "7A" if s else "")
    jv._rec.clear()
    jv.process_command("abre el diagnóstico de matemáticas para 7A")
    assert "proyector" in jv._rec.said()
    code = jv.diag["last"]
    c = jv.mobile_app.test_client()
    assert c.get(f"/diag/{code}").status_code == 200
    r = c.post(f"/diag/{code}/enviar", json={"nombre": "ana ruiz", "respuestas": [q["correcta"] for q in QS]}).get_json()
    assert r["ok"] and "8 de 8" in r["texto"]
    assert not c.post(f"/diag/{code}/enviar", json={"nombre": "Pepito", "respuestas": [0] * 8}).get_json()["ok"]
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    jv._rec.clear()
    jv.process_command("cierra el diagnóstico")
    assert "En 7A" in jv._rec.said()


# ---------------------------------------------------------------- 5. diplomas
def test_diplomas(jv, monkeypatch, tmp_path):
    assert CL.top_students({"A": 4.8, "B": 4.5, "C": 4.5, "D": 4.2, "E": 3.0}, 2) == [("A", 4.8), ("B", 4.5), ("C", 4.5)]
    assert CL.motivo_of("por su liderazgo") == CL.MOTIVOS["liderazgo"] and CL.motivo_of("") == CL.MOTIVOS["excelencia"]
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    monkeypatch.setattr(jv.seguimiento, "data", {"7A": {"Ana Ruiz": [], "Luis Gómez": [], "Pedro Paz": []}})
    monkeypatch.setattr(jv.seguimiento, "average", lambda c, e: {"Ana Ruiz": 4.7, "Luis Gómez": 4.2, "Pedro Paz": 3.1}[e])
    jv._rec.clear()
    jv.process_command("haz los diplomas de los mejores de cada curso")
    assert "2 diplomas" in jv._rec.said()
    files = list((tmp_path / "Diplomas").iterdir())
    assert len(files) == 1
    from docx import Document
    text = "\n".join(p.text for p in Document(str(files[0])).paragraphs)
    assert "Ana Ruiz" in text and "Primer puesto".upper() in text and "Pedro Paz" not in text
    jv._rec.clear()
    jv.process_command("haz un diploma para Sofía Gómez de 9A por su liderazgo")
    assert "Sofía Gómez" in jv._rec.said() and "liderazgo" in jv._rec.said()


# ---------------------------------------------------------------- 6. renta
def test_renta_puro():
    assert RT.topes(2025)[0][1] == 1400 * 49799 and RT.topes(2026)[1][1] == 4500 * 52374 and RT.topes(2019) is None
    r = RT.check(2026, {"ingresos": 80_000_000})
    assert r["obliga"] is True and "debes declarar renta en 2027" in RT.spoken(2026, r)
    r = RT.check(2026, {"ingresos": 50_000_000})
    assert r["obliga"] is None and "me falta saber" in RT.spoken(2026, r)
    r = RT.check(2025, {k: 0 for k, *_ in RT.TOPES})
    assert r["obliga"] is False and "no estás obligado" in RT.spoken(2025, r)
    assert RT.check(2025, {"ingresos": 1400 * 49799})["obliga"] is True                # ingresos: igual o superior
    assert RT.check(2025, {"patrimonio": 4500 * 49799})["obliga"] is None              # patrimonio: superior


def test_renta_por_voz(jv, monkeypatch):
    assert jv.renta_parse("gano 4,5 millones al mes") == {"ingresos": 4_500_000 * 13}
    assert jv.renta_parse("tengo una casa de 200 millones")["patrimonio"] == 200_000_000
    monkeypatch.setattr(jv.adjuntos, "recent", lambda s=1800, n=6: [])
    monkeypatch.setattr(jv, "card", lambda *a, **k: None)
    jv._rec.clear()
    jv.process_command("¿debo declarar renta? gano 6 millones al mes")
    assert "Sí:" in jv._rec.said() and "contador" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("debo declarar renta")
    assert "73.323.600" in jv._rec.said() or "69.718.600" in jv._rec.said()


# ---------------------------------------------------------------- 7. salidas
def test_salida(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: "OBJETIVO PEDAGÓGICO: observar plantas.\nDURANTE: recorrido.")
    monkeypatch.setitem(jv.aula.data, "cursos", {"9A": ["Ana Ruiz", "Luis Gómez"]})
    monkeypatch.setattr(jv, "_resolve_course", lambda s: "9A")
    jv._rec.clear()
    jv.process_command("planea una salida pedagógica al Jardín Botánico con 9A el 15 de marzo")
    assert "2 autorizaciones" in jv._rec.said()
    from docx import Document
    f = next((tmp_path / "Salidas pedagógicas").iterdir())
    txt = "\n".join(p.text for p in Document(str(f)).paragraphs)
    assert "Jardín Botánico" in txt and "Directiva Ministerial 55" in txt and "estudiante Ana Ruiz" in txt
    jv._rec.clear()
    jv.process_command("Ana Ruiz entregó la autorización")
    assert "Faltan 1" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("¿quién no ha entregado la autorización?")
    assert "Luis Gómez" in jv._rec.said()


# ---------------------------------------------------------------- 8. proyectos transversales
def test_proyectos(jv, monkeypatch, tmp_path):
    assert CL.proyecto_of("el PRAE") == "ambiental" and CL.proyecto_of("educación sexual") == "sexualidad"
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    prompts = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: (prompts.append(msgs[-1]["content"]), "TÍTULO: Reciclemos\nJUSTIFICACIÓN: …")[1])
    jv._rec.clear()
    jv.process_command("formula el proyecto ambiental")
    assert "Decreto 1743 de 1994" in prompts[-1] and (tmp_path / "Proyectos transversales").exists()
    jv.process_command("evidencia del PRAE: jornada de reciclaje con sexto")
    assert "1 en total" in jv._rec.said()
    jv.process_command("informe final del proyecto ambiental")
    assert "jornada de reciclaje con sexto" in prompts[-1]


# ---------------------------------------------------------------- 9. cronograma
def test_cronograma_puro():
    slots = [("7A", "Mat", 0), ("7A", "Mat", 2), ("7A", "Tec", 0), ("8B", "Mat", 0), ("9A", "Mat", 0)]
    start = datetime.date(2027, 2, 1)                     # lunes
    plan, missing = CL.schedule(slots, start, weeks=2, per_day_max=2)
    assert not missing and len(plan) == 4
    days = {}
    for x in plan:
        days.setdefault(x["fecha"], []).append(x["curso"])
    assert all(len(v) <= 2 for v in days.values()) and all(len(v) == len(set(v)) for v in days.values())
    plan2, miss2 = CL.schedule([("7A", "Mat", 0)], start, 1, 2, holidays={start})
    assert not plan2 and miss2 == [("7A", "Mat")]


def test_cronograma_por_voz_y_aviso(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    monkeypatch.setattr(jv.horario, "items", [{"dia": d, "inicio": "07:00", "fin": "07:55", "curso": c, "materia": "Matemáticas"}
                                              for d, c in ((0, "7A"), (0, "8B"), (0, "9A"), (2, "7A"))])
    jv._rec.clear()
    jv.process_command("organiza los exámenes de las próximas dos semanas")
    assert "Repartí 3 evaluaciones" in jv._rec.said()
    first = jv.d65_data()["cronograma"][0]
    eve = datetime.datetime.fromisoformat(first["fecha"]) - datetime.timedelta(hours=8)
    jv._rec.clear()
    jv.docente65_tick(eve)
    assert "Mañana evalúas" in jv._rec.said()
    jv._rec.clear()
    jv.docente65_tick(eve)
    assert not jv._rec.said()                                                   # una sola vez
