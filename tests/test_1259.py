"""Pruebas de la 12.59: ventanas que se abrían y se cerraban solas tras actualizar, y confirmaciones en vivo."""
import types


class P:
    def __init__(self, name, cmd, ppid=1):
        self.info = {"name": name, "cmdline": cmd, "ppid": ppid}
        self.killed = False

    def kill(self):
        self.killed = True


def _psutil(monkeypatch, procs):
    import sys
    monkeypatch.setitem(sys.modules, "psutil", types.SimpleNamespace(process_iter=lambda attrs: list(procs)))


def test_procesos_del_jarvis_viejo(jv, monkeypatch, tmp_path):
    st = str(tmp_path / "webview")
    old = P("msedgewebview2.exe", ["msedgewebview2.exe", f"--user-data-dir={st}\\EBWebView"])
    other = P("msedgewebview2.exe", ["msedgewebview2.exe", "--user-data-dir=C:\\otra\\app"])
    edge = P("msedge.exe", ["msedge.exe", st])
    monkeypatch.setattr(jv, "IS_WIN", True)
    _psutil(monkeypatch, [old, other, edge])
    assert jv.vw59_webview_procs(st) == [old]
    assert jv.vw59_wait_webview(st, timeout=0.01, sleep=lambda s: None) == 1 and old.killed and not other.killed
    _psutil(monkeypatch, [other])
    assert jv.vw59_wait_webview(st, sleep=lambda s: None) == 0
    monkeypatch.setattr(jv, "IS_WIN", False)
    assert jv.vw59_webview_procs(st) == []


def test_panel_caido_se_reinicia_una_vez(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    calls = []
    monkeypatch.setattr(jv, "restart_jarvis", lambda delay=1.0: calls.append("restart"))
    monkeypatch.setattr(jv, "_open_browser_hud", lambda: calls.append("browser"))
    monkeypatch.setattr(jv, "note_error", lambda *a, **k: None)
    assert jv.vw59_hud_died() is True and calls == ["restart"]
    assert jv.vw59_hud_died() is False and calls == ["restart", "browser"]      # no entra en un bucle de reinicios
    assert jv.vw59_can_restart(now=__import__("time").time() + 700)


def test_ajustes_caidos_al_navegador(jv, monkeypatch):
    opened = []
    monkeypatch.setattr(jv.webbrowser if hasattr(jv, "webbrowser") else __import__("webbrowser"), "open", lambda u: opened.append(u))
    import nucleo.ventanas59 as V
    monkeypatch.setattr(V.webbrowser, "open", lambda u: opened.append(u))
    monkeypatch.setattr(jv, "note_error", lambda *a, **k: None)
    assert jv.vw59_settings_closed(100.0, False, now=101.0) is True and opened[-1].endswith("/ajustes")
    assert jv.vw59_settings_closed(100.0, True, now=101.0) is False             # la cerró Jarvis
    assert jv.vw59_settings_closed(100.0, False, now=200.0) is False            # la cerraste tú después de usarla


def test_voz(jv, monkeypatch):
    import nucleo.ventanas59 as V
    calls = []
    monkeypatch.setattr(jv, "restart_jarvis", lambda delay=1.0: calls.append("restart"))
    monkeypatch.setattr(jv, "_open_browser_hud", lambda: calls.append("hud"))
    monkeypatch.setattr(V.webbrowser, "open", lambda u: calls.append(u))
    for frase in ("reiníciate", "abre los ajustes en el navegador", "abre el panel en el navegador"):
        jv._rec.clear()
        jv.process_command(frase)
        assert jv._rec.replies, frase
    assert calls[0] == "restart" and calls[1].endswith("/ajustes") and calls[2] == "hud"


def test_confirmar_actualizacion_en_vivo(jv, monkeypatch):
    import time
    ran = []
    monkeypatch.setattr(jv, "run_skill", lambda name, args, confirmed=False: (ran.append((name, confirmed)),
                                                                              jv._tl.capture.append("Me actualizo.")))
    jv.pending.update(skill="instalar_actualizacion", args={}, expires=time.time() + 20)
    assert jv.live_run_order("Confirmar la actualización a la versión 12.58") == {"result": "Me actualizo."}
    assert ran == [("instalar_actualizacion", True)] and jv.pending["skill"] is None
    jv.pending.update(skill="apagar", args={}, expires=time.time() + 20)            # lo demás peligroso, no
    assert "no se confirma" in jv.live_run_order("sí")["result"] and len(ran) == 1
    jv.pending.update(skill="instalar_actualizacion", args={}, expires=time.time() + 20)
    assert jv.live_run_order("no, cancela") == {"result": "Cancelado."} and jv.pending["skill"] is None
    assert "nada pendiente" in jv.live_run_order("sí")["result"]                    # ya no se vuelve «actualiza mis programas»
    n = len(ran)
    jv.live_run_order("abre la calculadora")                                         # una orden normal sigue su camino
    assert ran[n:] and ran[-1][0] == "abrir_app"


def test_version_en_vivo(jv):
    assert f"versión {jv.VERSION}" in jv._live_system()


def test_reinicio_del_exe(jv, monkeypatch):
    import nucleo.servicios as S
    started = []
    monkeypatch.setattr(S.sys, "frozen", True, raising=False)
    monkeypatch.setattr(S.sys, "executable", "C:\\Jarvis\\Jarvis.exe")
    monkeypatch.setattr(S.sys, "argv", ["Jarvis.exe", "--tray"])
    monkeypatch.setattr(S.subprocess, "Popen", lambda args, **k: started.append(args))
    monkeypatch.setattr(S.threading, "Timer", lambda d, f: types.SimpleNamespace(start=lambda: None))
    S.restart_jarvis()
    assert started == [["C:\\Jarvis\\Jarvis.exe", "--tray"]]
