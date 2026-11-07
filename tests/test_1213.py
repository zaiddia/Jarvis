"""Pruebas de la 12.13: el HUD se esconde como píldora en el borde derecho y se abre al pasar el ratón."""
import sys

import pytest


def _m(name):
    return sys.modules["nucleo." + name]


pildora = ventanas = None


class Win:
    def __init__(self):
        self.calls = []

    def resize(self, w, h):
        self.calls.append(("resize", w, h))

    def move(self, x, y):
        self.calls.append(("move", x, y))

    def show(self):
        self.calls.append(("show",))

    def hide(self):
        self.calls.append(("hide",))


@pytest.fixture
def hud(jv, monkeypatch):
    global pildora, ventanas
    pildora, ventanas = _m("pildora"), _m("ventanas")
    win = Win()
    emitted = []
    monkeypatch.setattr(jv, "_work_area", lambda: (0, 0, 1366, 720))
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: emitted.append((ev, data)))
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setattr(pildora, "cursor_over_hud", lambda: False)
    monkeypatch.setattr(jv, "cursor_over_hud", lambda: False)
    monkeypatch.setitem(jv.settings, "hud_auto_hide", True)
    monkeypatch.setitem(jv.settings, "hud_expanded", "amplio")
    old = dict(jv.hud)
    jv.hud.update(window=win, size="compacto", x=922, y=556, w=430, h=150, visible=True)
    pildora.pill.update(docked=False, cy=None, sync=True)
    yield jv, win, emitted
    pildora.pill.update(docked=False, cy=None, sync=False)
    jv.hud.clear()
    jv.hud.update(old)


def test_se_esconde_en_el_borde_derecho_y_vuelve_a_su_altura(hud):
    jv, win, emitted = hud
    assert jv.hud_dock(True) and jv.pill_docked()
    assert win.calls[:2] == [("resize", pildora.PILL_W, pildora.PILL_H), ("move", 1366 - pildora.PILL_W, 579)]
    assert ("hud_pill", {"on": True}) in emitted
    assert not jv.hud_dock(True)                               # ya estaba escondido
    win.calls.clear()
    assert jv.hud_dock(False) and not jv.pill_docked()
    (_, w, h), (_, x, y) = win.calls[:2]
    assert (w, h) == (430, 150) and x + w == 1366 - pildora._EDGE_GAP and y == 556     # junto a la píldora, a la misma altura
    assert emitted[-1] == ("hud_pill", {"on": False})


def test_la_pildora_no_se_sale_de_la_pantalla(hud):
    jv, win, _ = hud
    jv.hud.update(y=-400)
    jv.hud_dock(True)
    assert win.calls[1][2] >= 0
    jv.hud_dock(False)
    jv.hud.update(y=5000)
    jv.hud_dock(True)
    assert win.calls[-1][0] == "move" and win.calls[-1][2] + pildora.PILL_H <= 720


def test_no_se_esconde_con_el_raton_encima(hud, monkeypatch):
    jv, win, emitted = hud
    monkeypatch.setattr(pildora, "cursor_over_hud", lambda: True)
    monkeypatch.setattr(jv, "cursor_over_hud", lambda: True)
    assert not jv.hud_dock(True) and not jv.pill_docked() and win.calls == []
    assert emitted[-1] == ("hud_pill", {"on": False, "refused": True})
    assert jv.hud_dock(True, force=True)                       # por voz sí («escóndete a la derecha»)


def test_mostrar_cambiar_tamano_o_apagarla_la_abre(hud, monkeypatch):
    jv, win, _ = hud
    jv.hud_dock(True)
    ventanas.hud_show(expand=False)                            # al terminar una captura: sigue de píldora
    assert jv.pill_docked()
    ventanas.hud_show()                                        # bandeja, un aviso, «mostrar panel»
    assert not jv.pill_docked()
    jv.hud_dock(True)
    ventanas.hud_set_size("expandido")                         # sale con el tamaño nuevo
    assert not jv.pill_docked() and ("resize", 940, 680) in win.calls
    jv.hud_dock(True)
    ventanas.hud_reposition()                                  # no la mueve de su borde
    assert jv.pill_docked()
    monkeypatch.setitem(jv.settings, "hud_auto_hide", True)
    jv.apply_settings({"hud_auto_hide": False})
    assert not jv.pill_docked()


def test_desde_la_pagina_solo_si_esta_activada(hud, monkeypatch):
    jv, _, _ = hud
    monkeypatch.setitem(jv.settings, "hud_auto_hide", False)
    jv.handle_hud_dock({"on": True})
    assert not jv.pill_docked()
    monkeypatch.setitem(jv.settings, "hud_auto_hide", True)
    jv.handle_hud_dock({"on": True})
    assert jv.handle_hud_pill_state() == {"on": True, "enabled": True}
    jv.handle_hud_dock({"on": False})
    assert not jv.pill_docked()


def test_por_voz(hud, ask, monkeypatch):
    jv, _, _ = hud
    timers = []
    monkeypatch.setattr(pildora.threading, "Timer", lambda s, f: type("T", (), {"start": lambda self: timers.append(f)})())
    who, said = ask("Jarvis, no te escondas")
    assert jv.settings["hud_auto_hide"] is False and "abierto" in said
    who, said = ask("escóndete solo")
    assert jv.settings["hud_auto_hide"] is True and "píldora" in said
    who, said = ask("escóndete a la derecha")
    assert "Pasa el ratón" in said and timers
    timers[-1]()
    assert jv.pill_docked()
    who, said = ask("modo sigilo")                             # lo de siempre sigue igual
    assert said.startswith("Modo sigilo")


def test_ajustes_validos(jv):  # noqa: D103
    assert jv.DEFAULT_SETTINGS["hud_auto_hide"] is True and jv.DEFAULT_SETTINGS["hud_hide_secs"] == 5
    assert jv._validate("hud_hide_secs", 1) == 2 and jv._validate("hud_hide_secs", 300) == 60


def test_al_decir_jarvis_se_abre_sin_depender_de_la_pagina(hud):
    jv, win, _ = hud
    jv.hud_dock(True)
    jv.set_state(mode="idle")
    jv.set_state(mode="awaiting")                              # «Jarvis»
    assert not jv.pill_docked()
    jv.hud_dock(True)
    jv.set_state(mode="thinking")                              # «Jarvis, abre YouTube» de una vez
    assert not jv.pill_docked()
    jv.set_state(mode="idle")
    jv.hud_dock(True)
    jv.hud["visible"] = False                                  # en modo sigilo no aparece
    jv.set_state(mode="speaking")
    assert jv.pill_docked()
    jv.hud["visible"] = True
    jv.set_state(mode="idle")


def test_mover_la_ventana_no_frena_la_escucha(hud):
    """La escucha pide abrir la píldora y sigue al instante, aunque la ventana tarde en moverse."""
    import threading
    import time
    jv, win, _ = hud
    jv.hud_dock(True)
    pildora.pill["sync"] = False
    gate = threading.Event()
    slow = win.resize
    win.resize = lambda w, h: (gate.wait(2), slow(w, h))
    t0 = time.time()
    assert jv.hud_dock(False) is True and time.time() - t0 < 0.2
    gate.set()
    for _ in range(100):
        if not jv.pill_docked() and ("resize", 430, 150) in win.calls:
            break
        time.sleep(0.02)
    assert ("resize", 430, 150) in win.calls


def test_queda_anotado_quien_pauso_el_microfono(jv, monkeypatch):
    logs = []
    monkeypatch.setattr(jv, "log_terminal", lambda msg, tag="": logs.append(msg))
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.settings, "mic_enabled", True)
    monkeypatch.setattr(jv.mic_restart, "set", lambda: None)
    jv.handle_toggle_mic()
    assert jv.settings["mic_enabled"] is False and "Micrófono en pausa (botón del HUD)" in logs[-1]
    sys.modules["nucleo.ventanas"].toggle_mic("bandeja")
    assert jv.settings["mic_enabled"] is True and logs[-1] == "Micrófono activado (bandeja)."
