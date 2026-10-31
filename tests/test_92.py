"""Pruebas de la 9.2: campana de avisos, favoritos, tarjeta «Cursos» y encabezado compacto del HUD."""
import os

import seguimiento


def test_campana_de_avisos(jv, monkeypatch):
    events = []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: events.append((ev, data)))
    jv.notices.clear()
    jv.handle_notices({"seen": True})
    n = jv.notice_add("Recordatorio: reunión a las 3", "aviso")
    assert n and events[-1][0] == "notice" and events[-1][1]["unread"] == 1
    assert jv.notice_add("Recordatorio: reunión a las 3", "aviso") is None         # repetido seguido: no se duplica
    jv.alert("Temporizador de 5 minutos terminado.")
    r = jv.handle_notices()
    assert r["unread"] == 2 and r["items"][0]["text"].startswith("Temporizador")
    assert jv.handle_notices({"seen": True})["unread"] == 0
    jv.request_approval("x", "Publicar algo", "d", on_ok=lambda: None, ttl=60)
    assert jv.handle_notices()["items"][0]["kind"] == "aprobar"
    for a in jv.aprobaciones.pending():
        jv.resolve_approval(a["id"], False, "prueba")
    jv.log_terminal("algo se rompió", "ERROR")
    assert jv.handle_notices()["items"][0]["kind"] == "error"
    assert jv.handle_notices({"clear": True})["items"] == []


def test_favoritos(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "hud_favorites", "")
    monkeypatch.setattr(jv, "apply_settings", lambda d: jv.settings.update(d) or {"ok": True})
    monkeypatch.setattr(jv, "_weather_short", lambda: "")
    assert jv.handle_favorite_toggle({"cmd": "dame el resumen semanal"})["favorites"] == ["dame el resumen semanal"]
    d = jv.dashboard()
    assert d["favoritos"] == ["dame el resumen semanal"]
    assert any(s.get("kind") == "fav" and s["cmd"] == "dame el resumen semanal" for s in d["sugerencias"])
    assert jv.handle_favorite_toggle({"cmd": "dame el resumen semanal"})["favorites"] == []


def test_tarjeta_cursos(jv, monkeypatch):
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["A", "B", "C"]})
    monkeypatch.setattr(seguimiento, "data", {"7A": {"A": [{"actividad": "q", "nota": 4.8}], "B": [{"actividad": "q", "nota": 2.0}],
                                                      "C": [{"actividad": "q", "nota": 3.5}]}})
    c = jv.courses_summary()
    assert c == [{"curso": "7A", "promedio": 3.4, "n": 3, "dist": {"Superior": 1, "Alto": 0, "Básico": 1, "Bajo": 1}}]


def test_chat_lleva_la_fecha():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(here, "jarvis.py"), encoding="utf-8").read()
    assert '"date": now.date().isoformat()' in src


def test_pagina_del_hud():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html = open(os.path.join(here, "templates", "hud.html"), encoding="utf-8").read()
    js = open(os.path.join(here, "static", "js", "hud.js"), encoding="utf-8").read()
    assert 'id="btn-bell"' in html and 'id="ntc"' in html and 'id="vu"' in html and 'id="chat-q"' in html
    for name in ("placePreview", "drawNotices", "toggleFav", "filterChat", '"Cursos"', 'className = "day"'):
        assert name in js, name
