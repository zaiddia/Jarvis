"""Pruebas de la 12.68: voz de Fish Audio, escenas 3D por partes y «sigo en eso»."""
import json
import time

import agil
import escena3d as E3
import pytest

GOOD = {"titulo": "Sistema solar", "fondo": "#050814", "pasos": [
    {"texto": "El Sol", "objetos": [{"forma": "esfera", "pos": [0, 0, 0], "radio": 2, "color": "#ffb300", "etiqueta": "Sol"}]},
    {"texto": "La Tierra", "objetos": [{"forma": "esfera", "pos": [6, 0, 0], "radio": 0.5, "color": "#1e88e5",
                                        "anim": {"tipo": "orbita", "centro": [0, 0, 0], "vel": 20}},
                                       {"forma": "toro", "pos": [0, 0, 0], "radio": 6, "grosor": 0.03, "color": "#555577"}]},
    {"texto": "Saturno", "objetos": [{"forma": "esfera", "pos": [-9, 0, 2], "radio": 1, "color": "cafe"},
                                     {"forma": "flecha", "desde": [0, 3, 0], "hasta": [0, 6, 0], "color": "#ffffff"},
                                     {"forma": "texto", "pos": [0, -4, 0], "texto": "No está a escala"}]}]}


# ---------------------------------------------------------------- escena 3D (puro)
def test_revision_de_la_escena():
    s, p = E3.check(GOOD)
    assert not p and len(s["pasos"]) == 3 and s["pasos"][2]["objetos"][0]["color"] == "#795548"
    assert s["radio"] >= 6.5                                                  # la órbita cabe en cámara
    bad = json.loads(json.dumps(GOOD))
    bad["pasos"][1]["objetos"] = [{"forma": "esfera", "pos": [0, 0, 99], "radio": 1}, {"forma": "caja", "ancho": 0.001},
                                  {"forma": "dragon", "pos": [0, 0, 0]}]
    bad["pasos"][2]["objetos"].append({"forma": "esfera", "pos": [1, 1, 1], "radio": 1, "color": "#060915"})
    s2, p2 = E3.check(bad)
    txt = " | ".join(p2)
    assert "fuera de cámara" in txt and "demasiado pequeño" in txt and "dragon" in txt and "quedó vacío" in txt
    assert "casi no se ve" in txt and s2["pasos"][1]["objetos"][-1]["color"] in ("#f5f5f5", "#333333")
    assert len(s2["pasos"]) == 2 and "casi no se ve" not in " ".join(E3.serious(p2))
    assert E3.check({"pasos": []})[0] is None


def test_escena_por_voz(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    opened, emitted, calls = [], [], []
    monkeypatch.setattr(jv, "open_window", lambda path, title: opened.append(path))
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: emitted.append((ev, data)))
    broken = {"titulo": "Sistema solar", "pasos": [{"texto": "nada", "objetos": [{"forma": "esfera", "pos": [0, 0, 500]}]}]}

    def ai(msgs, **k):
        calls.append(msgs[-1]["content"])
        return json.dumps(broken if len(calls) == 1 else GOOD)
    monkeypatch.setattr(jv, "ai_chat", ai)
    jv._rec.clear()
    jv.process_command("constrúyeme en 3D el sistema solar")
    assert len(calls) == 2 and "fuera de cámara" in calls[1]                   # la revisión se la devolvió a la IA
    assert opened and opened[0].startswith("/escena3d/") and "3 partes" in jv._rec.said()
    sid = opened[0].rsplit("/", 1)[1]
    page = jv.app.test_client().get(f"/escena3d/{sid}")
    assert page.status_code == 200 and b"Sistema solar" in page.data and b"socket.io" in page.data
    assert jv.app.test_client().get("/escena3d/zzz").status_code == 404
    jv._rec.clear()
    jv.process_command("siguiente parte")
    assert ("e3d", {"sid": sid, "cmd": "next"}) in emitted
    jv.process_command("muéstralo todo")
    jv.process_command("deja de girar")
    assert [d["cmd"] for e, d in emitted if e == "e3d"] == ["next", "all", "stop_spin"]
    jv._rec.clear()
    jv.process_command("mis escenas 3D")
    assert "Sistema solar" in jv._rec.said()


def test_solidos_no_cambian(jv, monkeypatch):
    opened = []
    monkeypatch.setattr(jv, "open_window", lambda path, title: opened.append(path))
    jv.process_command("muéstrame el cubo en 3D")
    assert opened and opened[0].startswith("/solidos")


# ---------------------------------------------------------------- Fish Audio
class _Resp:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fish_tts(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "fish_api_key", "clave-de-prueba")
    monkeypatch.setitem(jv.settings, "fish_voice", "9a9cf47702da476aa4629e2506d4a857")
    monkeypatch.setitem(jv.settings, "fish_paid", False)
    monkeypatch.setattr(jv, "_ftts", {"pause_until": 0.0, "warned": 0.0, "free_over": False})
    sent = []

    def http(method, url, headers=None, payload=None, timeout=0, stream=False):
        sent.append((headers["model"], payload))
        if headers["model"] == "s2.1-pro-free" and len(sent) > 1:
            raise jv.AIError("pago", code=402, kind="balance", why="sin saldo", raw="payment required")
        return _Resp(b"ID3" + b"\0" * 500)
    monkeypatch.setattr(jv, "_http", http)
    out = jv._fish_tts("Hola profe", str(tmp_path / "a.mp3"))
    assert out.endswith("a.mp3") and sent[0][0] == "s2.1-pro-free" and sent[0][1]["reference_id"].startswith("9a9c")
    with pytest.raises(jv.AIError) as e:                                     # se acabó lo gratis y no hay permiso de pagar
        jv._fish_tts("Hola otra vez", str(tmp_path / "b.mp3"))
    assert e.value.kind == "balance" and jv._ftts["free_over"]
    monkeypatch.setitem(jv.settings, "fish_paid", True)
    jv._fish_tts("Ahora con pago", str(tmp_path / "c.mp3"))
    assert sent[-1][0] == "s2.1-pro"
    jv._rec.clear()
    jv.fish_failed(e.value)
    jv.fish_failed(e.value)
    assert jv._rec.said().count("dejó de ser gratis") == 1                  # avisa una sola vez


def test_fish_voz_y_ajustes(jv, monkeypatch):
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.settings, "tts_backend", "edge")
    monkeypatch.setitem(jv.settings, "fish_api_key", "")
    jv._rec.clear()
    jv.process_command("usa la voz de Fish Audio")
    assert "necesito tu clave" in jv._rec.said() and jv.settings["tts_backend"] == "edge"
    monkeypatch.setitem(jv.settings, "fish_api_key", "x")
    jv.process_command("usa la voz de Fish Audio")
    assert jv.settings["tts_backend"] == "fish"
    jv.process_command("la voz de fish es 9a9cf47702da476aa4629e2506d4a857")
    assert jv.settings["fish_voice"] == "9a9cf47702da476aa4629e2506d4a857"
    with pytest.raises(ValueError):
        jv._validate("fish_voice", "no-es-un-codigo")
    assert jv._validate("tts_backend", "fish") == "fish"
    assert "fish_api_key" in jv.SECRET_FIELDS and jv.ENV_ALIASES["FISH_API_KEY"] == "fish_api_key"


# ---------------------------------------------------------------- «sigo en eso»
def test_frases_de_espera(jv, monkeypatch):
    assert agil.still_for(1) in agil.STILL and agil.still_for(2) in agil.LONG
    assert all(p in agil.all_acks() for p in agil.STILL)
    spoken = []
    monkeypatch.setattr(jv, "speak", lambda text, **k: spoken.append(text))
    monkeypatch.setitem(jv.settings, "ack_ms", 20)
    monkeypatch.setattr(jv, "ACK_STILL_SECS", 0.08)
    monkeypatch.setattr(jv, "ACK_LONG_SECS", 0.16)
    a = jv._Ack("explícame la fotosíntesis")
    time.sleep(0.35)
    a.done()
    assert len(spoken) == 3 and spoken[1] in agil.STILL and spoken[2] in agil.LONG
    spoken.clear()
    b = jv._Ack("hola")
    b.done()                                                                   # llegó la respuesta: nada más
    time.sleep(0.25)
    assert spoken == []
