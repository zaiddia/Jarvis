"""Pruebas de la 12.10: acciones de la ventana (atajos fijos sobre la ventana que nombras o la del frente)."""
import pytest

import atajos

WINS = [{"hwnd": 1, "title": "Chrome - Gmail", "proc": "chrome.exe", "cls": "Chrome_WidgetWin_1"},
        {"hwnd": 2, "title": "Descargas", "proc": "explorer.exe", "cls": "CabinetWClass"},
        {"hwnd": 3, "title": "Informe.docx - Word", "proc": "WINWORD.EXE", "cls": "OpusApp"},
        {"hwnd": 4, "title": "", "proc": "explorer.exe", "cls": "Shell_TrayWnd"}]


def test_frases():
    assert atajos.parse_tab("cierra la pestaña del explorador") == {"accion": "cerrar", "app": "explorador"}
    assert atajos.parse_tab("abre una pestaña nueva en Chrome") == {"accion": "nueva", "app": "chrome"}
    assert atajos.parse_tab("cierra la pestaña") == {"accion": "cerrar", "app": ""}
    assert atajos.parse_action("sube una carpeta")[0] == "carpeta_arriba" and atajos.parse_action("nueva carpeta")[1] == ("ctrl", "shift", "n")
    assert atajos.parse_action("pasa la ventana al otro monitor")[1] == ("win", "shift", "right")
    for no in ("acerca de ti", "abre la carpeta de descargas", "copia el taller de 7A", "guarda la planilla", "abre spotify"):
        assert atajos.parse_action(no) is None, no
    assert atajos.pick_window(WINS, ("explorer.exe",))["hwnd"] == 2          # nunca el escritorio ni la barra de tareas
    assert atajos.pick_window(WINS, ("firefox.exe",)) is None


@pytest.fixture
def win(jv, monkeypatch):
    import nucleo.ventanaactiva as va
    sent = []
    front = {"h": 3}
    monkeypatch.setattr(jv, "IS_WIN", True)
    monkeypatch.setattr(va.skills, "list_windows", lambda: WINS)
    monkeypatch.setattr(va.skills, "target_window", lambda: front["h"])
    monkeypatch.setattr(va.skills, "_pid_of", lambda h: h)
    monkeypatch.setattr(va.skills, "_proc_name", lambda pid: next(w["proc"] for w in WINS if w["hwnd"] == pid))
    monkeypatch.setattr(va.skills, "_class_of", lambda h: next(w["cls"] for w in WINS if w["hwnd"] == h))
    monkeypatch.setattr(va.skills, "_title_of", lambda h: next(w["title"] for w in WINS if w["hwnd"] == h))
    monkeypatch.setattr(va, "_send", lambda h, keys: sent.append((h, keys)))
    return sent, front


def test_pestanas_por_programa(jv, win):
    sent, front = win
    jv._rec.clear()
    jv.process_command("cierra la pestaña del explorador")
    assert sent[-1] == (2, ("ctrl", "w")) and "Descargas" in jv._rec.said()
    jv.process_command("cierra la pestaña de Chrome")
    assert sent[-1] == (1, ("ctrl", "w"))
    jv._rec.clear()
    jv.process_command("cierra la pestaña de Firefox")
    assert "No tienes abierto firefox" in jv._rec.said()
    # al frente Word (sin pestañas): Ctrl+W cerraría el documento → va al navegador
    jv.process_command("cierra la pestaña")
    assert sent[-1] == (1, ("ctrl", "w"))
    # al frente el Explorador: su pestaña
    front["h"] = 2
    jv.process_command("cierra la pestaña")
    assert sent[-1] == (2, ("ctrl", "w"))


def test_explorador_ventanas_y_escritorios(jv, win):
    sent, front = win
    jv.process_command("sube una carpeta")                                 # Word al frente: busca el Explorador
    assert sent[-1] == (2, ("alt", "up"))
    jv.process_command("pon la ventana a la izquierda")
    assert sent[-1] == (3, ("win", "left"))
    jv.process_command("nuevo escritorio virtual")
    assert sent[-1] == (0, ("win", "ctrl", "d"))
    jv.process_command("guarda el archivo")
    assert sent[-1] == (3, ("ctrl", "s"))


def test_la_ia_los_conoce(jv):
    import skills
    assert "cierra la pestaña del <explorador" in skills.REGISTRY["orden_asistente"].args and "pestañas, carpetas y ventanas" in jv.ACTION_RULE


def test_control_por_voz(jv, monkeypatch):
    import nucleo.ventanaactiva as va
    calls = []
    monkeypatch.setattr(jv, "IS_WIN", True)
    monkeypatch.setattr(va, "voice_access_on", lambda origin="PC": calls.append("on"))
    monkeypatch.setattr(va, "voice_access_off", lambda origin="PC": calls.append("off"))
    for text in ("activa el control por voz", "Jarvis, abre el acceso por voz", "activa el mouse por voz", "desactiva el control por voz"):
        jv.process_command(text)
    assert calls == ["on", "on", "on", "off"]
    assert "clic en 5" in va.VA_HELP
