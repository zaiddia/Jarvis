"""Pruebas de la 8.6: panel «Hoy», tarjetas de archivos, paleta de órdenes, sugerencias y modo proyector."""
import datetime
import os

import horario
import seguimiento


def test_panel_hoy(jv, monkeypatch):
    monkeypatch.setattr(horario, "items", [{"dia": 4, "inicio": "07:00", "fin": "07:55", "curso": "7A", "materia": "Mate"},
                                           {"dia": 4, "inicio": "08:00", "fin": "08:55", "curso": "9B", "materia": "Física"}])
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Juan Pérez"]})
    monkeypatch.setitem(jv.aula.data, "asistencia", {})
    monkeypatch.setattr(seguimiento, "data", {"7A": {"Juan Pérez": [{"actividad": "q", "nota": 2.0, "fecha": "", "origen": "voz"}]}})
    monkeypatch.setitem(jv.project_run, "busy", False)
    monkeypatch.setattr(jv, "_weather_short", lambda: "")
    d = jv.dashboard(datetime.datetime(2026, 10, 30, 7, 30))           # viernes, en clase
    assert d["clase"]["ahora"] == "7A Mate" and d["clase"]["falta"] == 25 and d["clase"]["siguiente"] == "9B Física"
    assert d["riesgo"][0]["curso"] == "7A" and d["riesgo"][0]["nombres"] == ["Juan Pérez"]
    cmds = [s["cmd"] for s in d["sugerencias"]]
    assert "llama a lista" in cmds and "modo proyector" in cmds and "¿qué tengo hoy?" in cmds
    d = jv.dashboard(datetime.datetime(2026, 10, 30, 7, 58))           # entre clases: preparar la siguiente
    assert any(s.get("fill") and s["cmd"].startswith("prepárame la próxima clase") for s in d["sugerencias"])
    assert d["clase"]["en"] == 2


def test_aprobar_desde_las_sugerencias(jv, monkeypatch):
    monkeypatch.setattr(jv, "_weather_short", lambda: "")
    jv.request_approval("notas", "Guardar notas de 7A", "x", on_ok=lambda: None, ttl=60)
    d = jv.dashboard()
    assert d["aprobar"] and d["sugerencias"][0]["kind"] == "aprobar" and d["sugerencias"][0]["cmd"].startswith("sí ")
    for a in jv.aprobaciones.pending():
        jv.resolve_approval(a["id"], False, "prueba")


def test_tarjeta_de_archivo_y_seguridad(jv, monkeypatch, tmp_path):
    emitted = []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: emitted.append((ev, data)))
    img = tmp_path / "ciclo.png"
    img.write_bytes(b"\x89PNG")
    jv.generated_files.add(str(img))
    ev, card = emitted[-1]
    assert ev == "file_card" and card["image"] and card["kind"] == "Imagen" and card["id"] >= 0
    c = jv.app.test_client()
    assert c.get(f"/archivo/{card['id']}").status_code == 200
    assert c.get("/archivo/9999").status_code == 404
    other = tmp_path / "secreto.txt"
    other.write_text("x")
    assert jv.handle_file_open({"path": str(other)}) == {"ok": False}            # solo lo que generó Jarvis
    doc = tmp_path / "quiz.docx"
    doc.write_bytes(b"x")
    jv.generated_files.add(str(doc))
    idx = emitted[-1][1]["id"]
    assert c.get(f"/archivo/{idx}").status_code == 404                            # la ruta solo sirve imágenes


def test_paleta(jv):
    jv.chat_buffer.append({"role": "user", "text": "haz un quiz de fracciones", "source": "", "time": ""})
    r = jv.handle_palette()
    assert "haz un quiz de fracciones" in r["recent"]
    assert any(e["t"] == "modo proyector" for e in r["examples"]) and len(r["examples"]) > 50


def test_modo_proyector(jv, monkeypatch):
    opened = []
    monkeypatch.setattr(jv, "_open_projector", lambda: opened.append(1))
    jv._rec.clear()
    jv.process_command("modo proyector")
    assert opened and "proyector" in jv._rec.said()
    st = jv.projector_state()
    assert set(st) >= {"clase", "last", "imagen", "timers", "theme"}
    assert jv.app.test_client().get("/proyector").status_code == 200


def test_paginas_del_hud():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html = open(os.path.join(here, "templates", "hud.html"), encoding="utf-8").read()
    js = open(os.path.join(here, "static", "js", "hud.js"), encoding="utf-8").read()
    assert 'id="dash"' in html and 'id="pal"' in html and 'id="chips"' in html
    assert "renderDash" in js and "openPal" in js and "startSubs" in js and "file_card" in js
