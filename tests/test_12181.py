"""12.18.1: la voz se oye y va al ritmo del texto (conversación en vivo y voz normal)."""
import time


class FakePlayer:
    def __init__(self):
        self.buf = b""
        self.until = 0.0
        self.cleared = 0
        self.closed = False

    def write(self, pcm):
        self.buf += pcm
        self.until = time.time() + 3.0

    def clear(self):
        self.cleared += 1
        self.until = time.time() + 0.1

    def playing(self):
        return time.time() < self.until

    def close(self):
        self.closed = True


def _live(jv, monkeypatch, **kw):
    p = FakePlayer()
    st = dict(jv.live)
    st.update(active=True, connecting=False, player=p, out_buf="", in_buf="", shown="", mute_turn=False, turn_audio=False, loud=0)
    st.update(kw)
    monkeypatch.setattr(jv, "live", st)
    import nucleo
    monkeypatch.setattr(nucleo.J, "live", st, raising=False)
    return p


def test_voz_normal_dice_mas_que_la_primera_linea(jv):
    s = jv._clean_for_speech("Tienes 3 pendientes:\n- Calificar 7B\n- Llamar a mamá\n1. Comprar pan")
    assert "Calificar 7B" in s and "Llamar a mamá" in s and "Comprar pan" in s and "-" not in s
    assert jv._clean_for_speech("Mira:\n| a | b |\n| 1 | 2 |") == "Mira:"            # las tablas se leen en pantalla
    assert "C:" not in jv._clean_for_speech("Lo guardé en C:\\Users\\Ana\\nota.txt listo")
    long = jv._clean_for_speech("Esta es una frase de prueba. " * 60)
    assert len(long) < jv.SPEECH_MAX_CHARS + 60 and long.endswith("El resto está en la pantalla.")
    many = jv._clean_for_speech("\n".join(f"Punto número {i} con algo de texto para leer" for i in range(30)))
    assert "Punto número 0" in many and "Punto número 29" not in many and many.endswith("pantalla.")


def test_en_vivo_su_propia_voz_no_lo_interrumpe(jv, monkeypatch):
    p = _live(jv, monkeypatch)
    monkeypatch.setitem(jv.settings, "barge_in", True)
    monkeypatch.setitem(jv.settings, "live_headset", False)
    assert not jv.live_echo_gate(0.9)                     # callado: el micrófono pasa
    p.write(b"\x00" * 100)
    assert all(jv.live_echo_gate(0.95) for _ in range(6))  # hablando por parlantes: nunca se manda su voz, aunque suene fuerte
    monkeypatch.setitem(jv.settings, "live_headset", True)
    monkeypatch.setitem(jv.settings, "live_barge_level", 30)
    assert jv.live_echo_gate(0.9) and not jv.live_echo_gate(0.9)   # con audífonos: medio segundo de voz fuerte sí pasa
    assert jv.live_echo_gate(0.1)


def test_en_vivo_se_interrumpe_con_jarvis_y_no_con_su_eco(jv, monkeypatch):
    p = _live(jv, monkeypatch, out_buf="Mañana va a llover en Medellín por la tarde")
    p.write(b"\x00" * 100)
    monkeypatch.setitem(jv.settings, "wake_word_enabled", True)
    assert not jv.live_barge("va a llover en medellín")     # su propia voz
    assert not jv.live_barge("pásame el borrador")          # alguien del salón
    assert p.cleared == 0
    assert jv.live_barge("jarvis para")
    assert p.cleared == 1 and jv.live["mute_turn"]
    n = len(p.buf)
    jv._live_on_audio(b"\x01" * 50)                         # lo que quedaba de esa respuesta ya no suena
    assert len(p.buf) == n


def test_en_vivo_el_texto_sale_al_ritmo_de_la_voz(jv, monkeypatch):
    p = _live(jv, monkeypatch)
    sent = []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: sent.append((ev, data)))
    jv._live_on_output("Hola, ")                           # sin audio pendiente: sale ya
    assert sent[-1] == ("chat_partial", {"text": "Hola,", "source": "EN VIVO"})
    p.until = time.time() + 0.6                            # hay audio por sonar: el texto espera su turno
    jv._live_on_output("profe.")
    assert [e for e, _ in sent].count("chat_partial") == 1
    time.sleep(0.6)
    assert sent[-1] == ("chat_partial", {"text": "Hola, profe.", "source": "EN VIVO"})


def test_en_vivo_sin_audio_lo_dice_la_voz_normal(jv, monkeypatch):
    _live(jv, monkeypatch, out_buf="Son las tres de la tarde.", turn_audio=False)
    spoken = []
    monkeypatch.setattr(jv, "speak", lambda text, **k: spoken.append((text, k)))
    import nucleo
    monkeypatch.setattr(nucleo.J, "speak", lambda text, **k: spoken.append((text, k)), raising=False)
    monkeypatch.setattr(jv, "save_memory", lambda: None)
    jv._live_on_turn_complete()
    assert spoken and spoken[0][0] == "Son las tres de la tarde." and spoken[0][1].get("force")


def test_ajuste_audifonos_y_hud(jv):
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert jv.settings.get("live_headset") is False
    html = open(os.path.join(root, "templates", "settings.html"), encoding="utf-8").read()
    assert 'data-key="live_headset"' in html
    js = open(os.path.join(root, "static", "js", "hud.js"), encoding="utf-8").read()
    assert 'socket.on("chat_partial"' in js and ".msg.partial" in js
