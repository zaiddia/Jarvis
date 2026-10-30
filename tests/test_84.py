"""Pruebas de la 8.4: buscador de ajustes, arranque más rápido y avance del proyecto en el reactor."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_reactor_recibe_el_avance_del_proyecto(jv, monkeypatch):
    monkeypatch.setitem(jv.project_run, "busy", False)
    assert jv._orb_project() == {"project_total": 0, "project_done": 0, "project_name": ""}
    st = {"nombre": "Semana de 7A", "pasos": [{"estado": "hecho"}, {"estado": "error"}, {"estado": "en marcha"}, {"estado": "pendiente"}]}
    monkeypatch.setitem(jv.project_run, "busy", True)
    monkeypatch.setitem(jv.project_run, "st", st)
    assert jv._orb_project() == {"project_total": 4, "project_done": 2, "project_name": "Semana de 7A"}
    monkeypatch.setattr(jv, "_token_ok", lambda: None)
    r = jv.app.test_client().get("/api/orbe")
    assert r.status_code == 200 and r.get_json()["project_total"] == 4


def test_el_mod_pinta_el_proyecto():
    with open(os.path.join(HERE, "windhawk", "jarvis-orbe.wh.cpp"), encoding="utf-8") as f:
        src = f.read()
    assert "@version         2.2.0" in src and '"project_total"' in src and "v.project" in src


def test_sympy_no_se_carga_al_arrancar():
    code = ("import sys; sys.path.insert(0, %r); import mates; print('sympy' in sys.modules); "
            "print(mates.resolver('cuánto es 15 por 4')); print('sympy' in sys.modules)") % HERE
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120).stdout.split("\n")
    assert out[0] == "False" and "60" in out[1] and out[2] == "True"


def test_buscador_de_ajustes():
    with open(os.path.join(HERE, "templates", "settings.html"), encoding="utf-8") as f:
        html = f.read()
    with open(os.path.join(HERE, "static", "js", "settings.js"), encoding="utf-8") as f:
        js = f.read()
    assert 'id="s-search"' in html and "runSearch" in js and "searching" in js
