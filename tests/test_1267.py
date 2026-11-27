"""Pruebas de la 12.67: juegos de repaso, mapas, fluidez lectora, cartas de recomendación y pico y placa."""
import datetime
import json
import time

import adjuntos
import cole67 as C

PAIRS = [{"termino": w, "pista": f"Pista de {w}"} for w in
         ["fotosíntesis", "clorofila", "raíz", "tallo", "hoja", "sol", "agua", "oxígeno", "savia", "estoma"]]


# ---------------------------------------------------------------- juegos (puro)
def test_sopa_de_letras():
    ws = C.wordsearch([p["termino"] for p in PAIRS], seed=3)
    assert not ws["faltan"] and len(ws["grid"]) == ws["size"]
    for p in PAIRS:
        assert C.find_in_grid(ws["grid"], p["termino"])
    assert all(len(c) == 1 for row in ws["grid"] for c in row)
    easy = C.wordsearch(["casa", "perro", "gato"], seed=1, hard=False)
    assert all(p["dr"] >= -1 and (p["dr"], p["dc"]) in C.DIRS_EASY for p in easy["placed"])
    assert C.letters("Ñandú") == "ÑANDU"


def test_crucigrama_valido():
    for seed in range(5):
        cw = C.crossword(PAIRS, seed=seed)
        assert len(cw["palabras"]) >= 8
        for p in cw["palabras"]:
            dr, dc = (0, 1) if p["dir"] == "H" else (1, 0)
            assert "".join(cw["cells"][(p["fila"] + dr * i, p["col"] + dc * i)] for i in range(len(p["palabra"]))) == p["palabra"]
            assert (p["fila"] - dr, p["col"] - dc) not in cw["cells"]                  # nada pegado antes
            assert (p["fila"] + dr * len(p["palabra"]), p["col"] + dc * len(p["palabra"])) not in cw["cells"]
        nums = sorted({p["num"] for p in cw["palabras"]})
        assert nums == list(range(1, len(nums) + 1))


def test_emparejar():
    mt = C.matching(PAIRS[:5], seed=2)
    der = dict(mt["der"])
    for n, term in mt["izq"]:
        assert der[mt["clave"][n]] == f"Pista de {term}"


def test_juegos_por_voz(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    prompts = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: (prompts.append(msgs[-1]["content"]),
                                                          json.dumps({"titulo": "Las plantas", "pares": PAIRS}))[1])
    jv._rec.clear()
    jv.process_command("hazme unos juegos de repaso de las plantas para sexto")
    files = sorted(p.name for p in (tmp_path / "Juegos de repaso").iterdir())
    assert len(files) == 2 and any("(respuestas)" in f for f in files)
    assert "las plantas" in prompts[-1] and "hoja de respuestas" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("haz una sopa de letras del sistema solar")
    assert "sopa de letras" in jv._rec.said().lower()


# ---------------------------------------------------------------- mapas
def test_mapas(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    mp = {"titulo": "La célula", "centro": "Célula", "ramas": [
        {"texto": "Partes", "conector": "tiene", "hijos": [{"texto": "núcleo", "conector": "como"}, {"texto": "membrana", "conector": "y"}]},
        {"texto": "Tipos", "conector": "puede ser", "hijos": [{"texto": "animal", "conector": ""}, {"texto": "vegetal", "conector": ""}]},
        {"texto": "Funciones", "conector": "cumple", "hijos": ["nutrición", "relación"]}]}
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps(mp))
    jv._rec.clear()
    jv.process_command("haz un mapa conceptual de la célula para séptimo")
    files = {p.name for p in (tmp_path / "Mapas").iterdir()}
    assert len(files) == 4 and any("en blanco" in f and f.endswith(".png") for f in files)
    assert "versión en blanco" in jv._rec.said()
    m = C.clean_map(mp, "mental")
    assert m["ramas"][2]["hijos"][0]["texto"] == "nutrición"
    assert [a["a"] for a in jv.a67_card_actions([{"tipo": "pdf", "nombre": "guía.pdf"}])] == ["mapa67"]


# ---------------------------------------------------------------- fluidez lectora
REF = "El perro corre por el parque y salta la cerca muy alto todos los días de la semana"


def test_fluidez_puro():
    r = C.fluency(REF, "el perro corre corre por el palque y salta la cerca muy alto todos los días", 15, 3)
    assert r["correctas"] == 14 and r["cambiadas"] == [("parque", "palque")] and r["repetidas"] == ["corre"]
    assert r["no_leidas"] == 3 and not r["omitidas"]                     # lo que no alcanzó a leer no es omisión
    assert r["ppm"] == 60 and r["pcm"] == 56 and r["nivel"] == "se acerca al estándar"
    r2 = C.fluency(REF, "el perro corre por el y salta la cerca alto todos los dias de la semana", 10, 5)
    assert r2["omitidas"] == ["parque", "muy"]
    assert C.level_of(120, 5)[0] == "estándar" and "MEN" in C.level_of(120, 5)[1]
    assert C.level_of(130, 9)[0] == "estándar" and "no hay tabla oficial" in C.level_of(130, 9)[1]
    assert C.level_of(50, None) == ("", "")
    assert "repitió 1" in C.fluency_text("Juan", r)


def test_fluidez_por_voz(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.aula.data, "cursos", {"3A": ["Juan Pérez", "Ana Ruiz"]})
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    monkeypatch.setattr(adjuntos, "items", [{"id": "a1", "nombre": "lectura.m4a", "tipo": "audio", "ruta": "x.m4a", "t": time.time()}])
    jv._rec.clear()
    jv.process_command("evalúa la lectura de Juan de 3A")
    assert "texto que leyó" in jv._rec.said()
    monkeypatch.setattr(jv, "a67_duration", lambda p: 15)
    monkeypatch.setattr(jv, "a67_transcribe", lambda it: "el perro corre por el parque y salta la cerca muy alto todos los días")
    jv._rec.clear()
    jv.process_command(f"evalúa la lectura de Juan de 3A con este texto: {REF}")
    said = jv._rec.said()
    assert "Juan Pérez" in said and "palabras por minuto" in said
    rec = jv.a67_data()["fluidez"]["3A"]["Juan Pérez"]
    assert len(rec) == 1 and rec[0]["ppm"] == 60
    jv._rec.clear()
    jv.process_command("¿cómo va la fluidez de 3A?")
    assert "3A: 1 estudiante" in jv._rec.said() and list((tmp_path / "Fluidez lectora").iterdir())
    assert [a["a"] for a in jv.a67_card_actions([{"tipo": "audio", "nombre": "Juan.m4a"}])] == ["fluidez"]


# ---------------------------------------------------------------- carta de recomendación
def test_carta(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.settings, "aula_docente", "Profe Prueba")
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setitem(jv.aula.data, "cursos", {"11A": ["Ana Ruiz", "Luis Gómez"]})
    monkeypatch.setitem(jv.seguimiento.data, "11A", {"Ana Ruiz": [{"actividad": "Proyecto robótica", "nota": 4.9, "fecha": "2026-05-01",
                                                                    "origen": "voz"}]})
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    prompts = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: (prompts.append(msgs[-1]["content"]), "Ana es una estudiante destacada.")[1])
    jv._rec.clear()
    jv.process_command("hazme una carta de recomendación para Ana de 11A para la beca de la Universidad del Valle, destaca que lidera el club de robótica")
    p = prompts[-1]
    assert "Ana Ruiz" in p and "Proyecto robótica (4,9)" in p and "beca de la Universidad del Valle" in p and "club de robótica" in p
    files = list((tmp_path / "Cartas").iterdir())
    assert len(files) == 1
    import docx
    txt = "\n".join(x.text for x in docx.Document(str(files[0])).paragraphs)
    assert "Profe Prueba" in txt and "Ana es una estudiante destacada." in txt and "Atentamente" in txt


# ---------------------------------------------------------------- pico y placa
def test_pico_y_placa_puro():
    rot, ok = C.rotation((2026, 2))
    assert ok and rot == {0: (9, 0), 1: (1, 2), 2: (3, 4), 3: (5, 6), 4: (7, 8)}
    assert C.rotation((2026, 1))[0][0] == (1, 2) and C.rotation((2026, 1))[0][2] == (5, 6)
    assert not C.rotation((2027, 1))[1]                                      # estimada hasta verificarla
    thu = datetime.date(2026, 11, 26)
    assert C.restricted(thu, 5) == (True, (5, 6), True) and not C.restricted(thu, 7)[0]
    assert not C.restricted(datetime.date(2026, 11, 28), 9)[0]               # sábado
    assert not C.restricted(datetime.date(2026, 12, 8), 1, {datetime.date(2026, 12, 8)})[0]
    assert C.plate_digit("abc-125") == 5 and C.plate_digit("ABC12D") is None and C.is_moto("abc 12d")
    assert C.parse_table({"lunes": [9, 0], "martes": [1, 2], "miercoles": [3, 4], "jueves": [5, 6], "viernes": [7, 8]})["0"] == [9, 0]
    assert C.parse_table({"lunes": [9, 0], "martes": [9, 2]}) is None


def test_pico_y_placa_voz_y_aviso(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    jv._rec.clear()
    jv.process_command("mi placa es ABC 125")
    assert "termina en 5" in jv._rec.said() and jv.a67_data()["pyp"]["placa"] == "ABC125"
    jv._rec.clear()
    jv.process_command("¿cuándo tengo pico y placa?")
    assert "lunes 9 y 0" in jv._rec.said() or "lunes" in jv._rec.said()
    monkeypatch.setattr(jv, "_web_results", lambda q: [])
    jv._rec.clear()
    jv.aula67_tick(datetime.datetime(2026, 11, 26, 6, 30))                    # jueves: 5 y 6
    assert "Hoy tienes pico y placa" in jv._rec.said()
    jv._rec.clear()
    jv.aula67_tick(datetime.datetime(2026, 11, 26, 7, 30))
    assert not jv._rec.said()                                                  # una vez al día
    jv.aula67_tick(datetime.datetime(2026, 11, 27, 6, 30))                    # viernes: 7 y 8
    assert not jv._rec.said()
    jv.process_command("mi placa es ABC12D")
    assert "moto" in jv._rec.said()


def test_pico_y_placa_verifica(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(jv, "_web_results", lambda q: [{"titulo": "Rotación 2027", "resumen": "lunes 7 y 8…", "fuente": "cali.gov.co",
                                                        "url": "https://www.cali.gov.co/x"}])
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps({"lunes": [1, 2], "martes": [3, 4], "miercoles": [5, 6],
                                                                     "jueves": [7, 8], "viernes": [9, 0], "fuente": "cali.gov.co"}))
    assert jv.a67_pyp_verify((2027, 1))
    d = jv.a67_data()
    d["pyp"]["placa"] = "XYZ121"
    jv.a67_save(d)
    assert jv.a67_pyp_check(datetime.date(2027, 2, 1)) == (True, (1, 2), True)   # lunes, con la tabla verificada
