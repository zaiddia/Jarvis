"""Pruebas de la 11.2: ruta de dominio (no avanza hasta dominar) y tarjetas de memoria con repaso espaciado."""
import datetime
import json
import os

import pytest

import anual
import dominio
import examenes
import practica
import seguimiento

ROUTE = ["Fracciones equivalentes", "Suma de fracciones", "Multiplicación de fracciones", "Refuerzo y evaluación del periodo"]


def test_estados_de_la_ruta():
    r = ROUTE[:3]
    temas = {"Fracciones equivalentes": {"n": 6, "ok": 5, "nivel": 3, "racha": 2}, "Suma de fracciones": {"n": 2, "ok": 1, "nivel": 1, "racha": 0}}
    st = dominio.status(r, temas)
    assert [s["estado"] for s in st] == ["dominado", "actual", "bloqueado"] and st[1]["pct"] == 50
    assert dominio.current(r, temas) == "Suma de fracciones"
    rows, per = dominio.course_view(r, {"Ana": temas, "Luis": {}})
    assert per[0] == {"tema": "Fracciones equivalentes", "dominan": 1, "total": 2}


def test_tarjetas_leitner(tmp_path):
    dominio.data = {"mazos": {}, "rep": {}}
    dominio._path = None
    cards = dominio.clean_cards({"tarjetas": [{"frente": "¿1/2 = 2/4?", "reverso": "Sí"}, {"frente": "x", "reverso": ""}]})
    assert len(cards) == 1 and dominio.add_deck("7A", "Fracciones", cards) == 1 and dominio.add_deck("7A", "Fracciones", cards) == 0
    d0 = datetime.date(2026, 11, 2)
    cid = dominio.due("7A", "Ana", d0)[0][1]["id"]
    assert dominio.review("7A", "Ana", cid, True, d0)["proxima"] == "2026-11-03"
    assert dominio.due("7A", "Ana", d0) == []
    assert dominio.review("7A", "Ana", cid, True, datetime.date(2026, 11, 3))["proxima"] == "2026-11-06"     # caja 2: 3 días
    assert dominio.review("7A", "Ana", cid, False, datetime.date(2026, 11, 6))["caja"] == 1
    n = dominio.export_tsv("7A", str(tmp_path / "a.txt"))
    assert n == 1 and "¿1/2 = 2/4?\tSí\tFracciones" in open(tmp_path / "a.txt", encoding="utf-8").read()


@pytest.fixture
def ruta(jv, monkeypatch, tmp_path):
    for mod, val in ((practica, {"cursos": {}}), (dominio, {"mazos": {}, "rep": {}}), (examenes, {"examenes": {}})):
        monkeypatch.setattr(mod, "_path", str(tmp_path / (mod.__name__ + ".json")))
        monkeypatch.setattr(mod, "data", val)
    monkeypatch.setattr(practica, "pool", {})
    monkeypatch.setattr(anual, "_path", str(tmp_path / "pa.json"))
    monkeypatch.setattr(anual, "data", {"planes": {"7A": {"grado": 7, "asignatura": "Matemáticas", "periodos": [
        {"n": 1, "semanas": [{"semana": i + 1, "tema": t, "dba": "", "evaluacion": ""} for i, t in enumerate(ROUTE)]}]}}})
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "n.json"))
    monkeypatch.setattr(seguimiento, "data", {})
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Ana Gómez", "Luis Rojas"]})
    monkeypatch.setitem(jv.settings, "course_subjects", "")
    monkeypatch.setitem(jv.settings, "period_current", 1)
    monkeypatch.setitem(jv.settings, "year_start", "")
    monkeypatch.setattr(jv.horario, "items", [])
    monkeypatch.setitem(jv.mobile, "server", object())
    monkeypatch.setattr(jv, "_open_projector", lambda: None)
    monkeypatch.setattr("webbrowser.open", lambda *a, **k: None)
    monkeypatch.setitem(jv.state, "ai", "ok")
    jv.ps.update(code="", curso="", tokens={})
    return tmp_path


def test_ruta_en_la_practica(jv, ruta, monkeypatch):
    assert jv.course_route("7A") == ROUTE[:3]                              # sin la semana de refuerzo
    assert jv.route_current("7A", "Ana Gómez") == "Fracciones equivalentes"
    for _ in range(2):                                                     # sube al nivel 3 y domina
        practica.record("7A", "Ana Gómez", "Fracciones equivalentes", True, 1)
    for _ in range(2):
        practica.record("7A", "Ana Gómez", "Fracciones equivalentes", True, 1)
    for _ in range(2):
        practica.record("7A", "Ana Gómez", "Fracciones equivalentes", True, 1)
    assert practica.student("7A", "Ana Gómez")["temas"]["Fracciones equivalentes"].get("dom")
    assert jv.route_current("7A", "Ana Gómez") == "Suma de fracciones"
    assert jv.focus_for("7A", "Ana Gómez")[0]["tema"] == "Suma de fracciones"
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps({"tarjetas": [{"frente": f"F{i}", "reverso": f"R{i}"} for i in range(4)]}))
    jv._rec.clear()
    jv.process_command("haz tarjetas de suma de fracciones para 7A")
    assert "4 tarjetas" in jv._rec.said()
    jv.process_command("activa la práctica de 7A")
    c = jv.mobile_app.test_client()
    base = f"/p/{jv.ps['code']}"
    r = c.post(base + "/entrar", json={"nombre": "Ana Gómez", "pin": "1111"}).get_json()
    assert [x["estado"] for x in r["ruta"]] == ["dominado", "actual", "bloqueado"] and r["tarjetas"] == 4
    x = c.post(base + "/tarjetas", json={"k": r["k"]}).get_json()
    assert x["frente"] == "F0" and x["reverso"] == "R0"
    x = c.post(base + "/tarjeta", json={"k": r["k"], "id": x["id"], "sabia": True}).get_json()
    assert x["quedan"] == 3
    jv._rec.clear()
    jv.process_command("¿cómo va la ruta de 7A?")
    assert "«Fracciones equivalentes» 1/2" in jv._rec.said()
    page = jv.app.test_client().get("/ruta/7A").get_data(as_text=True)
    assert "Ana Gómez" in page and "✔" in page and "🔒" in page
    jv._rec.clear()
    jv.process_command("exporta las tarjetas de 7A a Anki")
    assert "4 tarjetas de 7A para Anki" in jv._rec.said()
    jv.process_command("¿cómo van las tarjetas de 7A?")
    assert "Ana Gómez: 0 firmes de 1" in jv._rec.said()
