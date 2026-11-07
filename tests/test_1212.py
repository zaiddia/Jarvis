"""Pruebas de la 12.12: recuperaciones con seguimiento, calendario escolar, asistencia con QR que cambia, modo examen,
coevaluación, detector de copia, juegos para imprimir, laboratorio de Python y dificultad de las preguntas."""
import datetime as dt
import os

import pytest

import banco
import copia
import festivos
import juegos
import salon

D = dt.date


# ============================================================================ LÓGICA PURA
def test_festivos_de_colombia():
    h = festivos.holidays(2026)
    for d, name in ((D(2026, 1, 12), "Reyes Magos"), (D(2026, 3, 23), "San José"), (D(2026, 4, 2), "Jueves Santo"), (D(2026, 5, 18), "Ascensión del Señor"),
                    (D(2026, 6, 8), "Corpus Christi"), (D(2026, 6, 15), "Sagrado Corazón"), (D(2026, 8, 17), "Asunción de la Virgen"),
                    (D(2026, 11, 16), "Independencia de Cartagena"), (D(2026, 12, 8), "Inmaculada Concepción")):
        assert h[d] == name, d
    assert len(h) == 18 and festivos.easter(2027) == D(2027, 3, 28)
    today = D(2026, 11, 7)
    assert festivos.parse_date("el 20 de noviembre", today) == D(2026, 11, 20) and festivos.parse_date("mañana", today) == D(2026, 11, 8)
    assert festivos.parse_date("el lunes", today) == D(2026, 11, 9)
    assert festivos.parse_range("receso del 28 de septiembre al 2 de octubre", today) is not None
    assert festivos.no_class(D(2026, 11, 16)).startswith("es festivo") and festivos.no_class(D(2026, 11, 14)) == "es fin de semana"
    assert festivos.no_class(D(2026, 11, 17)) == ""


def test_calendario_del_colegio(tmp_path):
    festivos.configure(str(tmp_path))
    today = D(2026, 11, 7)
    festivos.add_event("Semana de receso", D(2026, 11, 23), D(2026, 11, 27))
    festivos.add_event("Entrega de notas a coordinación", D(2026, 11, 10))
    assert festivos.events_between(D(2026, 11, 24), D(2026, 11, 24))[0]["tipo"] == "receso"
    assert "receso" in festivos.no_class(D(2026, 11, 24)).lower()
    assert festivos.to_warn(today) == ["En 3 días: Entrega de notas a coordinación."] and festivos.to_warn(today) == []
    assert festivos.to_warn(D(2026, 11, 15)) == ["Mañana no hay clase: es festivo (Independencia de Cartagena)."]
    assert festivos.remove_event("entrega")["titulo"].startswith("Entrega") and len(festivos.data["eventos"]) == 1
    festivos.configure(str(tmp_path / "limpio"))


def test_detector_de_copia():
    a = "n = int(input('numero'))\nif n % 2 == 0:\n    print('par')\nelse:\n    print('impar')\nfor i in range(n):\n    print(i * 2)"
    b = "# mio\nx = int(input('dame'))\nif x % 2 == 0:\n    print('es par')\nelse:\n    print('es impar')\nfor j in range(x):\n    print(j * 2)"
    c = "edad = 15\nwhile edad < 18:\n    edad += 1\nprint('mayor', edad)\nnombres = ['ana']\nfor nm in nombres: print(nm.upper())"
    r = copia.compare({"Ana": a, "Luis": b, "Sara": c}, code=True)
    assert len(r) == 1 and {r[0]["a"], r[0]["b"]} == {"Ana", "Luis"} and r[0]["nivel"] == "muy parecidos" and r[0]["partes"]
    assert copia.groups(r) == [["Ana", "Luis"]] and "Muy parecidos: Ana y Luis" in copia.spoken(r, 3)
    t1 = "La fotosintesis es el proceso por el cual las plantas convierten la luz del sol en energia quimica usando agua y dioxido de carbono"
    t3 = "Las celulas son la unidad basica de la vida y todos los seres vivos estan formados por una o mas celulas con funciones"
    assert copia.compare({"A": t1, "B": "Segun vimos " + t1, "C": t3})[0]["parecido"] >= 90
    assert copia.compare({"A": t1, "C": t3}) == [] and copia.spoken([], 1).startswith("Necesito")


def test_juegos():
    for topic in juegos.TOPICS:
        p = juegos.generate(topic, 30, seed=7)
        assert len({a for _q, a in p}) == len(p) >= 24, topic                  # respuestas todas distintas (para el bingo)
        assert juegos.check_pairs(p, topic), topic
    assert juegos.topic_of("bingo de fracciones") == "fracciones" and juegos.game_of("haz un dominó") == "domino" and juegos.game_of("memoria") == "parejas"
    pairs = juegos.generate("multiplicacion", 30, seed=1)
    cards = juegos.bingo_cards(pairs, 5, seed=2)
    assert all(len(c) == 25 and c[12] == "LIBRE" and len(set(c)) == 25 for c in cards)
    tiles = juegos.domino_tiles(pairs[:6])
    assert tiles[0] == (pairs[5][1], pairs[0][0]) and tiles[1] == (pairs[0][1], pairs[1][0])      # cadena cerrada
    with pytest.raises(ValueError):
        juegos.bingo_cards(pairs[:10], 2)
    assert juegos.ai_validate({"parejas": [{"pregunta": "Capital de Francia", "respuesta": "París"}, {"pregunta": "x", "respuesta": "parís"}]}, 5) == \
        [("Capital de Francia", "París")]


@pytest.mark.skipif(not __import__("boletin").available(), reason="sin fpdf2")
def test_juegos_en_pdf(tmp_path):
    import pypdf
    for game, n in (("bingo", 30), ("domino", 24), ("parejas", 18)):
        path = juegos.build_pdf(game, juegos.generate("enteros", n, seed=3), str(tmp_path / f"{game}.pdf"), "", "7A", n_cards=4, seed=1)
        r = pypdf.PdfReader(path)
        assert len(r.pages) >= 2 and "7A" in r.pages[0].extract_text(), game


def test_salon_logica(tmp_path):
    salon.configure(str(tmp_path))
    assert salon.at_risk({"Ana": 2.4, "Luis": 3.8, "Sara": 2.9, "Leo": None}) == [("Ana", 2.4), ("Sara", 2.9)]
    salon.recup_open("7A", "Ana", 2.4, D(2026, 11, 20))
    assert salon.recup_open("7A", "Ana", 2.0, D(2026, 12, 1))["fecha_limite"] == "2026-11-20"       # no se duplica
    assert salon.recup_summary(today=D(2026, 11, 21))["7A"]["vencidas"] == ["Ana"]
    assert salon.recup_to_warn(D(2026, 11, 18)) == [("7A", "Ana", 2)] and salon.recup_to_warn(D(2026, 11, 18)) == []
    salon.recup_delivered("7A", "Ana")
    assert salon.recup_result("7A", "Ana", 3.4)["estado"] == "aprobada" and salon.recup_result("7A", "Leo", 4) is None
    # QR que cambia cada 30 s
    tok = salon.qr_token("s3cr3t", 1000)
    assert salon.qr_valid("s3cr3t", tok, 1000) and salon.qr_valid("s3cr3t", tok, 1035) and not salon.qr_valid("s3cr3t", tok, 1100)
    assert not salon.qr_valid("otro", tok, 1000)
    assert salon.attend("7A", "Ana", "2026-11-07", "07:01", device="cel1")[0]
    ok, msg = salon.attend("7A", "Luis", "2026-11-07", "07:02", device="cel1")
    assert not ok and "otro estudiante" in msg                                  # un celular, un estudiante
    assert salon.attend("7A", "Luis", "2026-11-07", "07:20", tarde=True, device="cel2") == (True, "Llegada marcada, pero tarde.")
    # coevaluación
    s = salon.coev_new("c1", "7A", [["Ana", "Luis", "Sara"]])
    assert salon.coev_peers(s, "Ana") == ["Luis", "Sara"]
    assert not salon.coev_submit(s, "Ana", "Ana", [5, 5, 5, 5])[0] and not salon.coev_submit(s, "Ana", "Pepe", [5, 5, 5, 5])[0]
    salon.coev_submit(s, "Ana", "Luis", [5, 4, 5, 4])
    salon.coev_submit(s, "Sara", "Luis", [3, 4, 3, 4])
    salon.coev_submit(s, "Luis", "Ana", [5, 5, 5, 5])
    res = salon.coev_results(s)
    assert res["Luis"]["nota"] == 4.0 and res["Luis"]["votos"] == 2 and res["Ana"]["nota"] is None            # con 1 voto no se califica
    # laboratorio
    lab = salon.lab_new("l1", "7A", "Suma", "5")
    assert salon.same_output("5", "5\n") and not salon.same_output("", "5")
    assert not salon.lab_record(lab, "Ana", "print(2+2)", "4\n")["ok"] and salon.lab_record(lab, "Ana", "print(2+3)", "5\n")["ok"]
    salon.lab_record(lab, "Luis", "print(", "", "SyntaxError")
    x = salon.lab_summary(lab, ["Ana", "Luis", "Sara"])
    assert x["listos"] == ["Ana"] and x["trabajando"] == ["Luis"] and x["sin_empezar"] == ["Sara"]
    salon.configure(str(tmp_path / "limpio"))


def test_dificultad_del_banco(monkeypatch):
    qs = [{"enunciado": f"P{i}", "opciones": ["a", "b"], "respuesta": "a", "tema": "fracciones", "grado": "7", "usos": 0} for i in range(12)]
    monkeypatch.setattr(banco, "items", qs)
    monkeypatch.setattr(banco, "save", lambda: None)
    res = {str(k): {"detalle": [True, k < 5, k < 2] + [None] * 9} for k in range(10)}
    exams = [{"preguntas": [{"enunciado": "P0"}, {"enunciado": "P1"}, {"enunciado": "P2"}], "resultados": res}]
    assert banco.refresh_stats(exams) == 3 and banco.refresh_stats(exams) == 3                            # no cuenta dos veces
    assert [banco.level(q) for q in qs[:4]] == ["fácil", "media", "difícil", ""]
    assert banco.difficulty_counts("fracciones") == {"fácil": 1, "media": 1, "difícil": 1, "sin datos": 9}
    quiz = banco.build_balanced("fracciones", 10)
    assert len(quiz["preguntas"]) == 10 and quiz["niveles"] == {"fácil": 1, "media": 1, "difícil": 1}
    assert banco.build_balanced("fracciones", 20) is None


# ============================================================================ JARVIS
@pytest.fixture
def curso(jv, monkeypatch, tmp_path):
    import aula
    import practica
    monkeypatch.setitem(aula.data, "cursos", {"7A": ["Ana Gómez", "Luis Rojas", "Sara Díaz"]})
    monkeypatch.setitem(aula.data, "asistencia", {})
    monkeypatch.setattr(aula, "save", lambda: None)
    monkeypatch.setattr(practica, "check_pin", lambda c, e, p: (str(p) == "1234", "" if str(p) == "1234" else "Ese no es tu PIN."))
    monkeypatch.setattr(jv, "_need_lan", lambda: False)
    monkeypatch.setattr(jv, "_open_projector", lambda: None)
    monkeypatch.setattr(jv, "_resolve_course", lambda c: "7A" if "7" in str(c) else "")
    monkeypatch.setattr(jv, "request_approval", lambda *a, **k: None)          # sin permisos reales pendientes
    salon.configure(str(tmp_path))
    yield jv.mobile_app.test_client()
    salon.configure(str(tmp_path / "limpio"))


def test_asistencia_con_qr(jv, curso, monkeypatch):
    import time
    import aula
    import nucleo.salonplus as sp
    jv._rec.clear()
    jv.process_command("toma asistencia con QR de 7A")
    assert sp.asis["code"] and "cambia cada 30 segundos" in jv._rec.said()
    tok = salon.qr_token(sp.asis["secret"], time.time())
    page = curso.get(f"/as/{sp.asis['code']}?k={tok}").get_data(as_text=True)
    assert "Marcar mi llegada" in page and "Luis Rojas" in page
    r = curso.post(f"/as/{sp.asis['code']}/marcar", json={"nombre": "Ana Gómez", "pin": "1234", "k": tok, "dev": "a"}).get_json()
    assert r["ok"] and "marcada" in r["msg"]
    r = curso.post(f"/as/{sp.asis['code']}/marcar", json={"nombre": "Luis Rojas", "pin": "1234", "k": "viejo", "dev": "b"}).get_json()
    assert not r["ok"] and "ya cambió" in r["msg"]                              # el código que mandaron por chat ya no sirve
    assert "ya cambió" in curso.get(f"/as/{sp.asis['code']}?k=viejo").get_data(as_text=True)
    jv._rec.clear()
    jv.process_command("cierra la asistencia")
    today = dt.date.today().isoformat()
    assert aula.data["asistencia"]["7A"][today] == ["Luis Rojas", "Sara Díaz"] and "faltan 2" in jv._rec.said() and not sp.asis["code"]


def test_modo_examen(jv, curso):
    import nucleo.salonplus as sp
    jv._rec.clear()
    jv.process_command("modo examen 40 minutos")
    assert sp.exam["on"] and sp.exam_state()["left"] > 2390 and "40 minutos" in jv._rec.said()
    assert curso.get("/p/abc").status_code == 423 and "Modo examen" in curso.get("/r/abc").get_data(as_text=True)
    assert curso.get("/as/x").status_code == 404                               # la asistencia no se bloquea
    jv.process_command("termina el examen")
    assert not sp.exam["on"] and curso.get("/p/abc").status_code == 404


def test_coevaluacion(jv, curso):
    import seguimiento
    import nucleo.salonplus as sp
    jv.last_groups.update(curso="7A", groups=[["Ana Gómez", "Luis Rojas", "Sara Díaz"]], t=__import__("time").time())
    jv.process_command("abre la coevaluación de 7A")
    code = sp.coev["code"]
    ks = {}
    for n in ("Ana Gómez", "Luis Rojas", "Sara Díaz"):
        r = curso.post(f"/co/{code}/entrar", json={"nombre": n, "pin": "1234"}).get_json()
        assert r["ok"] and n not in r["companeros"] and len(r["companeros"]) == 2 and not r["libre"]
        ks[n] = r["k"]
    for ev, who, notas in (("Ana Gómez", "Luis Rojas", [5, 5, 4, 4]), ("Sara Díaz", "Luis Rojas", [4, 4, 4, 4]), ("Luis Rojas", "Ana Gómez", [5, 5, 5, 5])):
        assert curso.post(f"/co/{code}/enviar", json={"k": ks[ev], "evaluado": who, "notas": notas}).get_json()["ok"]
    jv._rec.clear()
    jv.process_command("cierra la coevaluación")
    luis = [n for n in seguimiento.data["7A"]["Luis Rojas"] if n["actividad"] == "Coevaluación"]
    assert luis and luis[-1]["nota"] == 4.3 and luis[-1]["dim"] == "ser"
    assert "Ana Gómez" not in seguimiento.data["7A"] or not [n for n in seguimiento.data["7A"]["Ana Gómez"] if n["actividad"] == "Coevaluación"]
    assert "menos de 2 evaluaciones" in jv._rec.said()


def test_laboratorio_de_python(jv, curso):
    import nucleo.salonplus as sp
    jv.process_command("abre el laboratorio de Python para 7A, el reto es: suma 2 y 3, la salida debe ser: 5")
    s = sp._pylab_s()
    assert s["reto"].startswith("suma 2 y 3") and s["esperada"] == "5"
    code = sp.pylab["code"]
    page = curso.get(f"/py/{code}").get_data(as_text=True)
    assert "pyodide" in page and "suma 2 y 3" in page
    k = curso.post(f"/py/{code}/entrar", json={"nombre": "Ana Gómez", "pin": "1234"}).get_json()["k"]
    assert not curso.post(f"/py/{code}/corrida", json={"k": k, "codigo": "print(2+2)", "salida": "4\n"}).get_json()["listo"]
    assert curso.post(f"/py/{code}/corrida", json={"k": k, "codigo": "print(2+3)", "salida": "5\n"}).get_json()["listo"]
    jv._rec.clear()
    jv.process_command("¿cómo va el laboratorio?")
    assert "1 lo resolvieron" in jv._rec.said() and "2 sin empezar" in jv._rec.said()
    jv.process_command("cierra el laboratorio")
    assert not sp.pylab["code"]


def test_recuperaciones_por_voz(jv, curso, monkeypatch):
    import seguimiento
    monkeypatch.setitem(seguimiento.data, "7A", {"Ana Gómez": [{"actividad": "Quiz", "nota": 2.0, "fecha": "2026-10-01"}]})
    monkeypatch.setitem(jv.settings, "zeti_since", "")
    monkeypatch.setattr(jv, "_student_or_ask", lambda target, origin="": ("7A", "Ana Gómez"))
    jv._rec.clear()
    jv.process_command("¿quiénes deben recuperar?")
    assert "Ana Gómez (2" in jv._rec.said()
    jv.register_plans("7A", ["Ana Gómez"])
    jv.process_command("Ana Gómez entregó la recuperación")
    assert salon.data["recup"]["7A"]["Ana Gómez"]["estado"] == "entregado"
    jv._rec.clear()
    jv.process_command("Ana Gómez sacó 3,5 en la recuperación")
    assert salon.data["recup"]["7A"]["Ana Gómez"]["estado"] == "aprobada" and "aprobó" in jv._rec.said()
    assert seguimiento.data["7A"]["Ana Gómez"][-1]["actividad"] == "Recuperación"
    jv._rec.clear()
    jv.process_command("¿cómo van las recuperaciones?")
    assert "1 aprobaron" in jv._rec.said()


def test_calendario_por_voz(jv, tmp_path):
    festivos.configure(str(tmp_path))
    for text in ("¿cuándo es el próximo festivo?", "¿mañana hay clase?", "entrega de notas a coordinación el 20 de noviembre"):
        jv._rec.clear()
        jv.process_command(text)
        assert jv._rec.who() == "CALENDARIO", text
    assert festivos.data["eventos"][-1]["titulo"] == "Entrega de notas a coordinación"             # con tus tildes
    assert jv.date_warning(dt.date(2026, 11, 16)).startswith(" Ojo: ese día es festivo")
    festivos.configure(str(tmp_path / "limpio"))


def test_juego_y_copia_por_voz(jv, curso, monkeypatch, tmp_path):
    import entregas
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    told = []
    monkeypatch.setattr(jv, "notify", lambda t, o="": told.append(t))
    jv.process_command("haz un dominó de enteros")
    assert "Listo el dominó de enteros" in told[-1] and os.listdir(tmp_path / "Juegos")
    a = "n = int(input())\nif n % 2 == 0:\n    print('par')\nelse:\n    print('impar')\nfor i in range(n):\n    print(i)"
    import re
    b = re.sub(r"\bn\b", "x", re.sub(r"\bi\b", "k", a))
    monkeypatch.setitem(entregas.data, "tareas", {"t1": {"curso": "7A", "consigna": "par", "creado": "2026-11-07T10:00", "cerrada": False,
                                                          "entregas": {"Ana Gómez": [{"tipo": "codigo", "texto": a}], "Luis Rojas": [{"tipo": "codigo", "texto": b}]}}})
    jv._rec.clear()
    jv.process_command("¿hay copia en las entregas de 7A?")
    assert "Muy parecidos" in jv._rec.said() and os.listdir(tmp_path / "Copia")


def test_python_servido_por_jarvis(jv, curso, monkeypatch, tmp_path):
    import io as _io
    import urllib.request
    import nucleo.salonplus as sp
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    assert not sp.pyodide_ready() and curso.get("/pyodide/pyodide.js").status_code == 404
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: _io.BytesIO(b"paquete alterado"))
    with pytest.raises(ValueError):
        sp.install_pyodide()                                                    # huella distinta: no se instala
    assert not sp.pyodide_ready()
    assert curso.get("/pyodide/../config.json").status_code == 404
