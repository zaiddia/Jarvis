"""12.24: la píldora ya no encoge la ventana (Windows) y el clic en la bandeja abre el HUD a la primera."""
import os
import sys

import pytest

pildora = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    global pildora
    pildora = sys.modules["nucleo.pildora"]
    win, emitted, regions = Win(), [], []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: emitted.append((ev, data)))
    monkeypatch.setattr(jv, "_work_area", lambda: (0, 0, 1366, 728))
    monkeypatch.setattr(pildora, "cursor_over_hud", lambda: False)
    # Windows al 125 %: la ventana de 440×620 mide 550×775 píxeles reales
    monkeypatch.setattr(pildora, "_win_rect", lambda: (77, 900, 50, 900 + 550, 50 + 775))
    monkeypatch.setattr(pildora, "_set_region", lambda hwnd, box: regions.append(box if box is None else tuple(round(v) for v in box)))
    monkeypatch.setattr(pildora, "_shape", lambda: regions.append("forma-vieja"))
    monkeypatch.setitem(jv.settings, "hud_auto_hide", True)
    old = dict(jv.hud)
    jv.hud.update(window=win, size="expandido", x=900, y=50, w=440, h=620, visible=True)
    monkeypatch.setattr(jv, "hud_dims", lambda size: (440, 620))
    pildora.pill.update(docked=False, cy=None, sync=True, strip=False, wh=None)
    yield jv, win, emitted, regions
    pildora.pill.update(docked=False, cy=None, sync=False, strip=False, wh=None)
    jv.hud.clear()
    jv.hud.update(old)


def test_la_pildora_no_cambia_el_tamano_de_la_ventana(hud):
    jv, win, emitted, regions = hud
    assert jv.hud_dock(True) and jv.pill_docked()
    assert win.calls == [("move", 1366 - 22, 50)]                       # solo se desliza: queda a la vista una franja de 22
    assert regions == [(0, 322, 28, 452, 28)]                           # recorte: franja de 22×104 (al 125 %), centrada en la altura
    assert ("hud_pill", {"on": True, "strip": True}) in emitted
    win.calls.clear()
    assert jv.hud_dock(False) and not jv.pill_docked()
    assert win.calls == [("move", 1366 - 440, 50)]                      # vuelve pegado al borde, a la misma altura, sin «resize»
    assert regions[-1] is None and "forma-vieja" not in regions         # se quita el recorte: la página ya estaba dibujada
    assert emitted[-1] == ("hud_pill", {"on": False})


def test_si_cambio_de_tamano_escondido_se_ajusta_al_abrir(hud, monkeypatch):
    jv, win, _e, _r = hud
    jv.hud_dock(True)
    win.calls.clear()
    monkeypatch.setattr(jv, "hud_dims", lambda size: (940, 680))
    jv.hud_dock(False)
    assert win.calls[0] == ("resize", 940, 680) and win.calls[1][0] == "move"


def test_pedir_lo_que_ya_esta_pone_la_pagina_al_dia(hud):
    jv, _w, emitted, _r = hud
    jv.hud_dock(True)
    emitted.clear()
    assert not jv.hud_dock(True)
    assert emitted == [("hud_pill", {"on": True, "strip": True})]       # la página nunca se queda con un estado viejo


def test_clic_en_la_bandeja_abre_la_pildora(hud, monkeypatch):
    jv, win, _e, _r = hud
    monkeypatch.setattr(jv, "_hud_front", lambda: None)
    v = sys.modules["nucleo.ventanas"]
    monkeypatch.setattr(jv, "hud_show", v.hud_show)                     # las de verdad (en las pruebas vienen sustituidas)
    monkeypatch.setattr(jv, "hud_hide", v.hud_hide)
    jv.hud_dock(True)
    win.calls.clear()
    jv.hud_toggle()                                                    # antes: lo escondía del todo y había que volver a hacer clic
    assert not jv.pill_docked() and ("hide",) not in win.calls and ("show",) in win.calls
    jv.hud_toggle()                                                    # abierto → a la bandeja
    assert win.calls[-1] == ("hide",) and not jv.hud["visible"]
    jv.hud_toggle()
    assert win.calls[-1][0] in ("show", "move") and jv.hud["visible"]


def test_pagina():
    css = open(os.path.join(ROOT, "static", "css", "hud.css"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "static", "js", "pildora.js"), encoding="utf-8").read()
    hud = open(os.path.join(ROOT, "static", "js", "hud.js"), encoding="utf-8").read()
    assert "body.pill-strip #pill" in css and "body.pill-mode:not(.pill-strip) > :not(#pill)" in css   # en franja el HUD sigue dibujado
    assert 'classList.toggle("pill-strip"' in js and 'pillEl.matches(":hover")' in js
    assert hud.index('socket.on("hud_visible"') > hud.index("const socket = ")    # después de crear la conexión (antes rompía el arranque)
