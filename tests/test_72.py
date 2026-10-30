"""Pruebas de la 7.2: Jarvis dentro de Windows (enlaces jarvis://, registro, notificaciones) y la API del orbe."""
import json
import os
import re

import windows_shell as ws

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def test_enlaces():
    assert ws.parse_link("jarvis://mostrar") == ("mostrar", "")
    assert ws.parse_link('"jarvis://rutina/Modo%20clase"') == ("rutina", "Modo clase")
    assert ws.parse_link("jarvis:orden/qué tengo pendiente") == ("orden", "qué tengo pendiente")
    assert ws.parse_link("JARVIS://Temporizador/5") == ("temporizador", "5")
    assert ws.parse_link(ws.make_link("posponer", "5/Es la hora: sacar la ropa")) == ("posponer", "5/Es la hora: sacar la ropa")
    for mal in ("jarvis://formatear", "jarvis://temporizador/0", "jarvis://temporizador/abc", "jarvis://temporizador/9999",
                "jarvis://orden", "jarvis://posponer/999/x", "jarvis://posponer/5", "http://jarvis", "", None):
        assert ws.parse_link(mal) is None, mal
    assert len(ws.parse_link("jarvis://orden/" + "a" * 2000)[1]) == ws.MAX_ARG
    assert ws.find_link(["jarvis.py", "--tray", "jarvis://mostrar"]) == "jarvis://mostrar"
    assert ws.find_link(["jarvis.py"]) is None


def test_todos_los_menus_son_enlaces_validos():
    for _, label, url in ws.MENU:
        assert ws.parse_link(url), url
    src = open(os.path.join(ROOT, "windhawk", "jarvis-orbe.wh.cpp"), encoding="utf-8").read()
    urls = re.findall(r'"(jarvis://[^"]+)"', src)
    assert len(urls) >= 9
    for u in urls:
        assert ws.parse_link(u), u


def test_plan_del_registro():
    plan = ws.registry_plan(r"C:\Py\pythonw.exe", [r"C:\Jarvis\jarvis.py"], r"C:\Jarvis\static\jarvis.ico",
                            r"C:\Jarvis\Jarvis.vbs")
    keys = [k for k, _ in plan]
    assert all(k.startswith(("Software\\Classes\\", "Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\")) for k in keys)
    assert not any("\\\\" in k for k in keys)
    assert all(any(k == o or k.startswith(o + "\\") for o in ws.KEYS_OWNED) for k in keys)   # remove() lo quita todo
    d = dict(plan)
    assert d["Software\\Classes\\jarvis"]["URL Protocol"] == ""
    assert d["Software\\Classes\\jarvis\\shell\\open\\command"][""] == '"C:\\Py\\pythonw.exe" "C:\\Jarvis\\jarvis.py" "%1"'
    cmd = d["Software\\Classes\\DesktopBackground\\Shell\\Jarvis\\shell\\03clase\\command"][""]
    assert cmd.endswith('"jarvis://rutina/Modo clase"')
    assert d["Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\jarvis.exe"][""] == r"C:\Jarvis\Jarvis.vbs"
    exe, args = ws.launcher(True, r"C:\Jarvis\jarvis.exe", "x")
    assert (exe, args) == (r"C:\Jarvis\jarvis.exe", [])


def test_notificacion():
    x = ws.toast_xml("Recordatorio", 'Es la hora: "examen" & <todo>', [("Posponer 5 min", "jarvis://posponer/5/x%20y")] * 5)
    assert x.count("<action ") == 3
    assert "&amp;" in x and "&lt;todo&gt;" in x
    assert 'arguments="jarvis://posponer/5/x%20y"' in ws.toast_xml("a", "b", [("c", "jarvis://posponer/5/x%20y")])
    assert "&quot;" in ws.toast_xml("a", "b", [('Di "hola"', "jarvis://mostrar")])
    import xml.dom.minidom
    xml.dom.minidom.parseString(x)                          # XML válido
    script = ws.toast_script(x.replace("examen", "it's"))
    assert "it''s" in script and ws.APP_ID in script


def test_enlaces_en_jarvis(jv, monkeypatch):
    rec = jv._rec
    rec.clear()
    calls = []
    monkeypatch.setattr(jv, "hud_show", lambda: calls.append("show"))
    monkeypatch.setattr(jv, "toggle_mic", lambda: calls.append("mic"))
    monkeypatch.setattr(jv, "trigger_alarm", lambda s, l: calls.append(("alarma", s, l)))
    assert jv.run_link("jarvis://mostrar") and calls == ["show"]
    assert jv.run_link("jarvis://microfono") and calls[-1] == "mic"
    assert jv.run_link(ws.make_link("posponer", "15/Es la hora: llamar")) and calls[-1] == ("alarma", 900, "Es la hora: llamar")
    assert not jv.run_link("jarvis://borrar-todo")
    assert jv.run_link("jarvis://temporizador/5") and "temporizador" in rec.other


def test_orden_por_enlace_con_reglas_del_celular(jv):
    import time
    rec = jv._rec
    rec.clear()
    jv.link_order("apaga el equipo")
    for _ in range(50):
        if rec.other or rec.replies:
            break
        time.sleep(0.02)
    assert "bloqueado" in rec.other                         # desde un enlace no se apaga el equipo
    rec.clear()
    jv.link_order("sube el volumen")
    for _ in range(50):
        if rec.skills:
            break
        time.sleep(0.02)
    assert rec.skills and rec.skills[0][0] == "volumen"


def test_api_del_orbe_y_enlace(jv, monkeypatch):
    jv.write_link_file()
    with open(jv.LINK_FILE, encoding="utf-8") as f:
        d = json.load(f)
    assert d["token"] == jv.link_token["value"] and d["port"] == jv.PORT
    c = jv.app.test_client()
    assert c.get("/api/orbe").status_code == 403
    assert c.get("/api/orbe", headers={"X-Jarvis-Token": "x" * 64}).status_code == 403
    r = c.get("/api/orbe", headers={"X-Jarvis-Token": d["token"]})
    assert r.status_code == 200 and set(r.get_json()) >= {"mode", "mic", "timers", "next", "version"}
    calls = []
    monkeypatch.setattr(jv, "hud_toggle", lambda: calls.append("toggle"))
    r = c.post("/api/enlace", json={"url": "jarvis://alternar"}, headers={"X-Jarvis-Token": d["token"]})
    assert r.get_json()["ok"] and calls == ["toggle"]
    assert c.post("/api/enlace", json={"url": "jarvis://alternar"}).status_code == 403


def test_notificacion_solo_si_esta_activada(jv, monkeypatch):
    sent = []
    monkeypatch.setattr(ws, "toast", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(jv, "IS_WIN", True)
    jv.settings["windows_integration"] = False
    jv.windows_toast("Es la hora: examen.", "NOTAS")
    assert not sent
    jv.settings["windows_integration"] = True
    jv.windows_toast("Es la hora: examen.", "NOTAS")
    jv.windows_toast("Es la hora: examen.", "NOTAS")        # repetida: una sola
    jv.windows_toast("Hola", "JARVIS")                      # no es un aviso
    assert len(sent) == 1 and sent[0][0] == "Recordatorio"
    assert any("posponer" in u for _, u in sent[0][2])
    jv.settings["windows_integration"] = False


# ----------------------------------------------------------------------------- en Windows de verdad (la compilación de GitHub)
import sys  # noqa: E402

import pytest  # noqa: E402

solo_windows = pytest.mark.skipif(sys.platform != "win32", reason="solo en Windows")


@solo_windows
def test_registro_de_windows_se_pone_y_se_quita():
    import winreg
    exe = sys.executable
    plan = ws.registry_plan(exe, [os.path.join(ROOT, "jarvis.py")], os.path.join(ROOT, "static", "jarvis.ico"))
    try:
        ws.apply(plan)
        assert ws.installed()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\jarvis\shell\open\command") as k:
            assert winreg.QueryValueEx(k, "")[0].endswith('"%1"')
    finally:
        ws.remove()
    assert not ws.installed()
    for key in ws.KEYS_OWNED:
        with pytest.raises(OSError):
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, key)


@solo_windows
def test_lista_de_saltos_y_accesos_directos(tmp_path):
    pytest.importorskip("win32com")
    ws.set_jump_list(sys.executable, [os.path.join(ROOT, "jarvis.py")], os.path.join(ROOT, "static", "jarvis.ico"))
    ws.clear_jump_list()
    lnk = str(tmp_path / "Jarvis.lnk")
    import subprocess
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');$s.TargetPath='{sys.executable}';$s.Save()"],
                   check=True)
    assert ws.stamp_shortcuts([lnk]) == 1


@solo_windows
def test_identidad_en_la_barra():
    assert ws.set_app_id()
