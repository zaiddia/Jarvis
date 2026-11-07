"""Pruebas de la 12.14: Mis aplicaciones (tarjetas, grupos, horario, frases) y el generador de documentos."""
import datetime as dt
import json
import os
import sys

import pytest

import documentos
import misapps

DOC = {"titulo": "Taller de fracciones", "subtitulo": "Grado 7°", "secciones": [
    {"titulo": "Explicación", "parrafos": ["Una fracción representa partes de un todo."], "vinetas": ["Numerador", "Denominador"]},
    {"titulo": "Ejercicios", "pasos": ["Suma 1/2 + 1/4"], "preguntas": [{"enunciado": "¿2/4 simplificado?", "opciones": ["A) 1/2", "B) 2/3"]}]},
    {"titulo": "Rúbrica", "tabla": {"columnas": ["Criterio", "Superior"], "filas": [["Suma", "Siempre correcto"]]}}]}


# ============================================================================ MIS APLICACIONES (lógica)
@pytest.fixture
def apps(tmp_path):
    misapps.configure(str(tmp_path))
    yield misapps
    misapps.data.update(apps=[], grupos=[], importado=False)


def test_tarjetas_y_frases(apps):
    c = apps.upsert({"nombre": "Campus", "destino": "campusvirtual.univalle.edu.co", "tipo": "web", "frases": ["abre el campus", "abre campus", "abre campus"]})
    assert c["destino"] == "https://campusvirtual.univalle.edu.co" or c["tipo"] == "web"
    with pytest.raises(ValueError):
        apps.upsert({"nombre": "Mala", "tipo": "web", "destino": "ftp://x"})
    c = apps.upsert({"id": c["id"], "nombre": "Campus", "destino": "https://campusvirtual.univalle.edu.co", "frases": ["abre el campus", "abre campus", "Abre Campus"]})
    assert c["tipo"] == "web" and c["frases"] == ["abre el campus", "abre campus"]
    m = apps.upsert({"nombre": "Música", "destino": "https://www.youtube.com/watch?v=x", "frases": ["pon música", "música"], "navegador": "brave.exe"})
    n = apps.upsert({"nombre": "Paint", "destino": r"C:\Windows\System32\mspaint.exe", "frases": []})
    assert n["tipo"] == "app" and n["frases"] == ["abre paint"]
    assert apps.guess_tipo(r"C:\Users\ana\Documents\Clases") == "carpeta" and apps.guess_tipo(r"C:\x\horario.pdf") == "archivo"
    assert apps.match_phrase("Jarvis, pon música por favor")["id"] == m["id"]
    assert apps.match_phrase("abre el canpus")["id"] == c["id"]            # una letra mal oída
    assert apps.match_phrase("abre el campo de fútbol") is None
    assert apps.match_name("campus")["id"] == c["id"] and apps.match_name("musica")["id"] == m["id"]
    apps.load()                                                             # quedó guardado
    assert len(apps.data["apps"]) == 3
    warn = apps.conflicts(["abre campus", "yo", "abre paint", "abre el canal"], own_id=m["id"], builtin={"abre paint"})
    assert any("ya abre «Campus»" in w for w in warn) and any("muy corta" in w for w in warn)
    assert not apps.conflicts(["abre el campus"], own_id=c["id"])
    assert apps.remove(m["id"]) and apps.get(m["id"]) is None


def test_grupos_horario_e_importar(apps):
    a = apps.upsert({"nombre": "Campus", "destino": "https://campus.edu.co", "horario": {"hora": "6:50", "dias": [0]}})
    b = apps.upsert({"nombre": "Clases", "destino": r"C:\Clases", "tipo": "carpeta"})
    with pytest.raises(ValueError):
        apps.upsert_group({"nombre": "Solo", "items": [a["id"]]})
    with pytest.raises(ValueError):
        apps.upsert({"nombre": "X", "destino": "https://x.co", "horario": {"hora": "25:00"}})
    g = apps.upsert_group({"nombre": "Modo clase", "items": [a["id"], b["id"], "nada"], "frases": ["modo clase"], "horario": {"hora": "07:00", "dias": [0, 1, 2, 3, 4]}})
    assert g["items"] == [a["id"], b["id"]] and apps.match_phrase("modo clase")["id"] == g["id"]
    assert apps.describe_schedule(g["horario"]) == "entre semana a las 07:00" and a["horario"] == {"hora": "06:50", "dias": [0]}
    fired = {}
    mon = dt.datetime(2026, 11, 9, 6, 51)
    assert [x["id"] for x in apps.due(mon, fired)] == [a["id"]] and apps.due(mon, fired) == []       # una vez al día
    assert apps.due(dt.datetime(2026, 11, 9, 6, 55), {}) == []                                       # muy tarde
    assert [x["id"] for x in apps.due(dt.datetime(2026, 11, 10, 7, 0), {})] == [g["id"]]
    apps.remove(b["id"])
    assert apps.get(g["id"])["items"] == [a["id"]]
    n = apps.import_text("mi proyecto = C:\\Proyecto\nnotas = https://docs.google.com/x\nmalo\n")
    assert n == 2 and apps.match_phrase("abre mi proyecto")["destino"] == "C:\\Proyecto"
    assert apps.import_text("notas = https://docs.google.com/x") == 0
    for _ in range(3):
        apps.used(a["id"])
    assert apps.most_used(1)[0]["id"] == a["id"] and apps.get(a["id"])["usos"] == 3


# ============================================================================ MIS APLICACIONES (con Jarvis)
@pytest.fixture
def jv_apps(jv, tmp_path, monkeypatch):
    misapps.configure(str(tmp_path))
    opened = []
    monkeypatch.setattr(jv.skills, "open_url", lambda url, proc="": (opened.append(("web", url, proc)), "Brave" if proc else "")[1])
    monkeypatch.setattr(jv.skills, "_launch", lambda d: opened.append(("abrir", d)))
    monkeypatch.setattr(jv.skills, "_launch_app", lambda k, d: opened.append((k, d)))
    monkeypatch.setattr(jv.skills, "IS_WIN", True)
    monkeypatch.setattr(jv, "settings", dict(jv.settings, custom_commands=""))
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    jv.skills.configure(apps_open=jv.apps_open_hook)
    monkeypatch.setattr(sys.modules["nucleo.aplicaciones"].time, "sleep", lambda s: None)
    yield jv, opened
    misapps.data.update(apps=[], grupos=[], importado=False)


def test_frases_y_abrir_por_voz(jv_apps, ask, tmp_path):
    jv, opened = jv_apps
    folder = tmp_path / "Clases"
    folder.mkdir()
    canal = misapps.upsert({"nombre": "Canal de YouTube", "destino": "https://www.youtube.com/@canal/videos", "frases": ["abre el canal"]})
    misapps.upsert({"nombre": "Música", "destino": "https://www.youtube.com/watch?v=x", "frases": ["pon música", "música"], "navegador": "brave.exe"})
    misapps.upsert({"nombre": "Clases", "destino": str(folder), "tipo": "carpeta", "frases": ["abre mis clases"]})
    who, said = ask("abre el canal")
    assert opened[-1] == ("web", "https://www.youtube.com/@canal/videos", "") and said == "Abriendo Canal de YouTube."
    who, said = ask("pon música")
    assert opened[-1][2] == "brave.exe" and "en Brave" in said
    ask("abre mis clases")
    assert opened[-1] == ("abrir", str(folder))
    jv._rec.clear()
    jv.skills.REGISTRY["abrir_app"].fn(nombre="canal de youtube en chrome")        # «abre … en chrome» por la habilidad
    assert opened[-1] == ("web", "https://www.youtube.com/@canal/videos", "chrome.exe")
    assert misapps.get(canal["id"])["usos"] == 2
    misapps.upsert({"nombre": "Viejo", "destino": str(tmp_path / "no_existe"), "tipo": "carpeta", "frases": ["abre lo viejo"]})
    who, said = ask("abre lo viejo")
    assert "No encuentro" in said


def test_grupo_y_probar_frase(jv_apps, ask):
    jv, opened = jv_apps
    a = misapps.upsert({"nombre": "Campus", "destino": "https://campus.edu.co", "frases": ["abre el campus"]})
    b = misapps.upsert({"nombre": "PowerPoint", "destino": "Microsoft.Office.POWERPNT.EXE.15", "appid": True, "tipo": "app", "frases": ["abre power"]})
    misapps.upsert_group({"nombre": "Modo clase", "items": [a["id"], b["id"]], "frases": ["prepara la clase"]})
    who, said = ask("prepara la clase")
    assert said.startswith("Abriendo «Modo clase»: Campus, PowerPoint")
    for _ in range(50):
        if len(opened) >= 2:
            break
        import time
        time.sleep(0.02)
    assert ("web", "https://campus.edu.co", "") in opened and ("appid", "Microsoft.Office.POWERPNT.EXE.15") in opened
    r = jv.try_phrase("abre el campus")
    assert r["quien"] == "tarjeta" and "Campus" in r["texto"]
    assert jv.try_phrase("abre la calculadora")["quien"] == "jarvis"
    assert jv.try_phrase("abre youtube")["quien"] == "jarvis"
    assert jv.try_phrase("abre el programa inexistente xyz")["quien"] == "nada"
    assert jv.try_phrase("¿qué hora es?")["quien"] == "orden"
    n = len(opened)
    jv.handle_apps_try({"frase": "abre el campus"})
    assert len(opened) == n                                                  # probar no abre nada


def test_pagina_y_ajustes(jv_apps):
    jv, opened = jv_apps
    st = jv.handle_apps_state()
    assert st["apps"] == [] and "web" in st["tipos"]
    r = jv.handle_apps_save({"nombre": "Calculadora", "destino": "calc.exe", "frases": ["abre la calculadora"]})
    assert r["ok"] and any("Jarvis ya conoce" in w for w in r["avisos"])
    assert jv.handle_apps_save({"nombre": "", "destino": "x"})["ok"] is False
    cid = r["id"]
    assert jv.handle_apps_test({"id": cid})["ok"] and opened[-1] == ("abrir", "calc.exe")
    assert jv.handle_apps_check({"frases": ["abre la calculadora"]})["avisos"]
    assert jv.handle_apps_browse({"tipo": "app"})["ok"] is False           # sin ventana de Jarvis: escribir la ruta
    jv.settings["custom_commands"] = "notas = https://docs.google.com/x"
    assert jv.import_custom() == 1 and jv.settings["custom_commands"] == ""
    assert jv.handle_apps_delete({"id": cid})["ok"]
    c = jv.app.test_client()
    assert c.get("/aplicaciones").status_code == 200 and c.get("/documentos").status_code == 200


def test_abrir_las_paginas_por_voz(jv_apps, ask, monkeypatch):
    jv, _ = jv_apps
    pages = []
    monkeypatch.setattr(jv, "_open_page", lambda path, title, holder: pages.append(path))
    ask("abre mis aplicaciones")
    ask("Jarvis, abre el generador de documentos")
    assert pages == ["/aplicaciones", "/documentos"]


# ============================================================================ GENERADOR DE DOCUMENTOS (lógica)
def test_plantillas_y_validar():
    assert documentos.ok_format("evaluacion", "pdf") and not documentos.ok_format("circular", "excel")
    m = documentos.validate_doc(DOC)
    assert m["secciones"][1]["preguntas"][0]["opciones"] == ["A) 1/2", "B) 2/3"] and m["secciones"][2]["tabla"]["columnas"] == ["Criterio", "Superior"]
    with pytest.raises(ValueError):
        documentos.validate_doc({"titulo": "x", "secciones": []})
    p = documentos.build_prompt("pdf", "evaluacion", "evaluación de fracciones", "7°", "Matemáticas", "corto", "Texto del libro")
    assert "Hoja de respuestas" in p and "1 página" in p and "Texto del libro" in p and "Matemáticas" in p
    assert '"diapositivas"' in documentos.build_prompt("powerpoint", "guia", "fracciones")
    assert '"columnas"' in documentos.build_prompt("excel", "taller", "fracciones")
    assert "Cambio: «más corto»" in documentos.revise_prompt("word", m, "más corto")
    assert documentos.compatible("doc", "pdf") and documentos.compatible("table", "word") and not documentos.compatible("slides", "pdf")
    t = documentos.local_table("notas", "7A", ["Ana", "Luis"], 4)
    assert t["columnas"][-1] == "Definitiva" and len(t["columnas"]) == 7 and t["filas"][1][:2] == [2, "Luis"]
    a = documentos.local_table("asistencia", "7A", ["Ana"], today=dt.date(2026, 11, 7))
    assert a["columnas"][2] == "02/11" and "08/11" not in a["columnas"]                  # solo días de semana
    with pytest.raises(ValueError):
        documentos.local_table("notas", "7A", [])
    assert "1. ¿2/4 simplificado?" in documentos.plain("doc", m)


def test_arma_los_seis_formatos(tmp_path):
    from docx import Document
    m = documentos.validate_doc(DOC)
    paths = {f: documentos.build(f, "doc" if documentos.kind_of(f) != "slides" else "doc", m, str(tmp_path), Document, "Ana", "IE", "7A")
             for f in ("word", "pdf", "texto", "excel", "csv")}
    slides = documentos.validate("powerpoint", {"titulo": "Fracciones", "diapositivas": [{"titulo": "Qué es", "puntos": ["a", "b"]}, {"titulo": "Ejemplo", "puntos": ["c"]}]})
    paths["powerpoint"] = documentos.build("powerpoint", "slides", slides, str(tmp_path))
    for f, p in paths.items():
        assert os.path.exists(p) and os.path.dirname(p).endswith("Documentos") and p.endswith(documentos.FORMATS[f][1]), f
    assert "Docente: Ana" in open(paths["texto"], encoding="utf-8-sig").read()
    assert open(paths["csv"], encoding="utf-8-sig").read().startswith("Criterio;Superior")
    assert open(paths["pdf"], "rb").read(4) == b"%PDF"
    t = documentos.local_table("asistencia", "7A", ["Ana"])
    assert open(documentos.build("pdf", "table", t, str(tmp_path)), "rb").read(4) == b"%PDF"


# ============================================================================ GENERADOR (con Jarvis)
@pytest.fixture
def gen(jv, tmp_path, monkeypatch):
    calls = []

    def fake_ai(msgs, **k):
        calls.append(msgs[0]["content"])
        doc = json.loads(json.dumps(DOC))
        if "Cambio:" in msgs[0]["content"]:
            doc["titulo"] = "Taller corto"
        return json.dumps(doc)
    monkeypatch.setattr(jv, "ai_chat", fake_ai)
    monkeypatch.setattr(jv, "settings", dict(jv.settings, output_dir=str(tmp_path / "out"), aula_docente="Ana Ruiz", aula_institucion="IE San José",
                                             aula_open_docs=False))
    monkeypatch.setattr(jv.aula, "data", dict(jv.aula.data, cursos={"7A": ["Ana Gómez", "Luis Rojas"]}, activo="7A"))
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    events = []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: events.append((ev, data)))
    documentos.history.configure(str(tmp_path))
    import adjuntos
    adjuntos.configure(str(tmp_path))
    yield jv, calls, events
    documentos.history.items = []


def test_generar_cambiar_y_guardar(gen):
    jv, calls, events = gen
    st = jv.handle_doc_state()
    assert st["cursos"] == ["7A"] and st["plantillas"]["notas"]["local"] and "word" in st["formatos"]
    assert jv.handle_doc_generate({"formato": "pdf", "plantilla": "taller", "pedido": "taller de fracciones", "curso": "7A", "largo": "corto"})["ok"]
    d = [e for e in events if e[0] == "doc_draft"][-1][1]
    assert d["ok"] and d["kind"] == "doc" and d["model"]["titulo"] == "Taller de fracciones" and "Grado: 7°" in calls[-1]
    jv.handle_doc_revise({"id": d["id"], "cambio": "más corto"})
    d2 = [e for e in events if e[0] == "doc_draft"][-1][1]
    assert d2["version"] == 2 and d2["model"]["titulo"] == "Taller corto"
    r = jv.handle_doc_save({"id": d["id"]})
    assert r["ok"] and r["item"]["ruta"].endswith(".pdf") and os.path.exists(r["item"]["ruta"])
    r2 = jv.handle_doc_save({"id": d["id"], "formato": "word"})                       # el mismo borrador en Word
    assert r2["ok"] and r2["item"]["ruta"].endswith(".docx") and len(r2["historial"]) == 2
    assert jv.handle_doc_save({"id": d["id"], "formato": "powerpoint"})["ok"] is False
    hid = r2["item"]["id"]
    assert jv.handle_doc_action({"id": hid, "accion": "proyectar"})["ok"]
    assert jv.handle_doc_action({"id": hid, "accion": "drive"})["ok"] is False                    # sin Google conectado
    assert len(jv.handle_doc_action({"id": hid, "accion": "quitar"})["historial"]) == 1
    assert jv.handle_doc_generate({"formato": "excel", "plantilla": "circular", "pedido": "x"})["ok"]
    assert "no se puede hacer en Excel" in [e for e in events if e[0] == "doc_draft"][-1][1]["error"]


def test_listas_del_curso_sin_ia_y_archivo_de_base(gen):
    jv, calls, events = gen
    n = len(calls)
    jv.handle_doc_generate({"formato": "excel", "plantilla": "notas", "curso": "7A", "notas": 3})
    d = [e for e in events if e[0] == "doc_draft"][-1][1]
    assert d["ok"] and d["model"]["filas"][0][:2] == [1, "Ana Gómez"] and len(calls) == n          # sin IA
    assert jv.handle_doc_save({"id": d["id"]})["item"]["ruta"].endswith(".xlsx")
    up = jv.handle_doc_upload({"name": "lectura.txt", "data": "data:text/plain;base64," + __import__("base64").b64encode("El ciclo del agua tiene evaporación.".encode()).decode()})
    assert up["ok"]
    jv.handle_doc_generate({"formato": "word", "plantilla": "guia", "pedido": "", "archivo": up["id"]})
    assert "El ciclo del agua tiene evaporación." in calls[-1]


def test_documento_por_voz_sin_quitarle_ordenes_al_aula(gen, ask, monkeypatch):
    jv, calls, events = gen
    started = []
    monkeypatch.setattr(sys.modules["nucleo.generador"].threading, "Thread", lambda target, **k: type("T", (), {"start": lambda s: (started.append(1), target())})())
    who, said = ask("hazme un acta en PDF de la reunión de padres de 7A")
    assert "acta en PDF" in said and started
    assert documentos.history.items[-1]["ruta"].endswith(".pdf") and documentos.history.items[-1]["plantilla"] == "acta"
    gen_calls = len(calls)
    started.clear()
    monkeypatch.setattr(jv, "generate_material", lambda *a, **k: jv._rec.other.append("material"))
    who, said = ask("hazme un taller de fracciones para séptimo")
    assert not started and "material" in jv._rec.other and len(calls) == gen_calls
