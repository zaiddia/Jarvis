"""Pruebas de la 9.1: el HUD expandido es amplio (con el panel «Hoy» al lado) y nunca usa archivos viejos en caché."""


def test_tamano_del_hud_expandido(jv, monkeypatch):
    monkeypatch.setattr(jv, "_work_area", lambda: (0, 0, 1920, 1040))
    monkeypatch.setitem(jv.settings, "hud_expanded", "amplio")
    assert jv.hud_dims("expandido") == (940, 680)
    monkeypatch.setitem(jv.settings, "hud_expanded", "estrecho")
    assert jv.hud_dims("expandido") == (440, 620)
    monkeypatch.setitem(jv.settings, "hud_expanded", "grande")
    monkeypatch.setattr(jv, "_work_area", lambda: (0, 0, 1366, 728))          # pantalla pequeña: se ajusta
    assert jv.hud_dims("expandido") == (1200, 700)
    assert jv.hud_dims("compacto") == jv.HUD_SIZES["compacto"]


def test_sin_cache_vieja(jv):
    c = jv.app.test_client()
    html = c.get("/").get_data(as_text=True)
    assert f"js/hud.js?v={jv.VERSION}" in html and f"css/hud.css?v={jv.VERSION}" in html
    r = c.get(f"/static/js/hud.js?v={jv.VERSION}")
    assert r.status_code == 200 and r.headers.get("Cache-Control") == "no-cache"
    assert f"aula.js?v={jv.VERSION}" in c.get("/aula").get_data(as_text=True)
