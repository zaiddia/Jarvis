"""Pruebas de la 7.9: notas de voz por Telegram, WhatsApp, panel instalable, imágenes y varios equipos."""
import base64
import json
import os
import time

import imagenes
import proyectos
import sincronizar
import whatsapp


# ----------------------------------------------------------------------------- imágenes
def test_imagenes_reglas(tmp_path):
    assert imagenes.pick_model(["models/gemini-2.5-flash", "models/gemini-2.5-flash-image", "models/text-embedding"]) \
        == "gemini-2.5-flash-image"
    assert imagenes.pick_model(["models/gemini-2.5-flash"]) == ""
    assert imagenes.pick_model([], "mi-modelo") == "mi-modelo"
    assert imagenes.is_image("hazme una ilustracion del ciclo del agua")
    assert imagenes.is_image("genera una imagen de una celula animal")
    assert not imagenes.is_image("abre la imagen que te mandé ayer")
    assert imagenes.subject("hazme una ilustración del ciclo del agua") == "ciclo del agua"
    b = imagenes.body("una célula")
    assert b["generationConfig"]["responseModalities"] == ["IMAGE", "TEXT"]
    png = base64.b64encode(b"\x89PNG-falso").decode()
    raw, ext = imagenes.extract({"candidates": [{"content": {"parts": [{"text": "aquí"}, {"inlineData": {"mimeType": "image/png", "data": png}}]}}]})
    assert raw == b"\x89PNG-falso" and ext == ".png"
    try:
        imagenes.extract({"candidates": [{"content": {"parts": [{"text": "no puedo"}]}}]})
        raise AssertionError("debía fallar")
    except ValueError:
        pass
    p = imagenes.save(raw, ext, str(tmp_path), 'ciclo: del "agua"')
    assert os.path.isfile(p) and p.endswith(".png") and '"' not in os.path.basename(p)


def test_imagen_por_voz(jv, monkeypatch, tmp_path):
    made = []
    monkeypatch.setattr(jv, "make_image", lambda what, folder=None: made.append(what) or str(tmp_path / "x.png"))
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    said = []
    monkeypatch.setattr(jv, "notify", lambda text, origin="JARVIS": said.append(text))
    jv._tl.capture = []
    try:
        jv.process_command("hazme una ilustración del ciclo del agua")
    finally:
        jv._tl.capture = None
    assert made == ["ciclo del agua"]
    assert any("Imágenes" in x for x in said)


def test_imagen_sin_clave(jv, monkeypatch):
    monkeypatch.setattr(jv, "_gemini_for_stt", lambda: None)
    try:
        jv.make_image("una célula")
        raise AssertionError("debía fallar")
    except RuntimeError as e:
        assert "Gemini" in str(e)


def test_paso_imagen_en_proyectos():
    assert "imagen" in proyectos.TYPES


# ----------------------------------------------------------------------------- WhatsApp
def test_whatsapp(jv, monkeypatch):
    u = whatsapp.url("+57 300 123 4567", " clave ", "Hola & adiós")
    assert u.startswith(whatsapp.API) and "phone=%2B573001234567" in u and "apikey=clave" in u and "Hola+%26" in u
    assert whatsapp.valid_phone("+573001234567") and not whatsapp.valid_phone("123")
    monkeypatch.setitem(jv.settings, "whatsapp_phone", "")
    assert not jv.whatsapp_ready() and jv.whatsapp_send("x") is False
    monkeypatch.setitem(jv.settings, "whatsapp_phone", "+573001234567")
    monkeypatch.setitem(jv.settings, "whatsapp_apikey", "123")
    assert jv.whatsapp_ready()
    sent = []
    monkeypatch.setattr(jv, "telegram_ready", lambda: False)
    monkeypatch.setattr(jv, "whatsapp_send", lambda t: sent.append(t) or True)
    assert jv.phone_send("hola") and sent == ["hola"]


def test_whatsapp_clave_es_secreta(jv):
    assert "whatsapp_apikey" in jv.SECRET_FIELDS


# ----------------------------------------------------------------------------- notas de voz
def test_nota_de_voz_telegram(jv, monkeypatch):
    sent, voices = [], []
    monkeypatch.setattr(jv, "_tg_file", lambda fid: b"OGG")
    monkeypatch.setattr(jv, "transcribe_voice_note", lambda data, mime="audio/ogg": "qué hora es")
    monkeypatch.setattr(jv, "telegram_send", lambda t: sent.append(t) or True)
    monkeypatch.setattr(jv, "telegram_run", lambda t: "Son las 3.")
    monkeypatch.setattr(jv, "tg_send_voice", lambda t: voices.append(t) or True)
    monkeypatch.setitem(jv.settings, "telegram_voice_reply", True)
    assert jv.tg_voice({"voice": {"file_id": "F", "mime_type": "audio/ogg"}})
    assert sent[0] == "🎙 «qué hora es»" and "Son las 3." in sent
    time.sleep(0.1)
    assert voices == ["Son las 3."]
    assert jv.tg_voice({"text": "hola"}) is False


def test_nota_de_voz_sin_entender(jv, monkeypatch):
    sent = []
    monkeypatch.setattr(jv, "_tg_file", lambda fid: b"OGG")
    monkeypatch.setattr(jv, "transcribe_voice_note", lambda data, mime="audio/ogg": "")
    monkeypatch.setattr(jv, "telegram_send", lambda t: sent.append(t) or True)
    assert jv.tg_voice({"voice": {"file_id": "F"}})
    assert "No entendí" in sent[0]


# ----------------------------------------------------------------------------- panel instalable
def test_manifiesto_del_panel(jv, monkeypatch):
    monkeypatch.setattr(jv, "_mobile_ok", lambda: None)
    c = jv.mobile_app.test_client()
    r = c.get("/manifest.json?k=abc")
    assert r.status_code == 200
    m = json.loads(r.data)
    assert m["display"] == "standalone" and "k=abc" in m["start_url"]
    r = c.get("/icono.png?k=abc")
    assert r.status_code == 200 and r.mimetype == "image/png"


# ----------------------------------------------------------------------------- varios equipos
def test_sincronizar(tmp_path):
    a, b = tmp_path / "pc1", tmp_path / "nube"
    a.mkdir()
    b.mkdir()
    (a / "perfil.json").write_text('{"nombre": "Ana"}', encoding="utf-8")
    (a / "habilidades").mkdir()
    (a / "habilidades" / "x.json").write_text("{}", encoding="utf-8")
    (a / "ajustes.json").write_text('{"clave": "secreta"}', encoding="utf-8")   # nunca se copia
    acts, changed = sincronizar.sync(str(a), str(b))
    remote = b / sincronizar.SUB
    assert (remote / "perfil.json").is_file() and (remote / "habilidades" / "x.json").is_file()
    assert not (remote / "ajustes.json").exists() and changed == []
    # el otro equipo cambia el perfil: se trae
    (remote / "perfil.json").write_text('{"nombre": "Ana María"}', encoding="utf-8")
    later = time.time() + 60
    os.utime(remote / "perfil.json", (later, later))
    acts, changed = sincronizar.sync(str(a), str(b))
    assert changed == ["perfil.json"] and "Ana María" in (a / "perfil.json").read_text(encoding="utf-8")
    # un JSON a medio sincronizar no pisa el bueno
    (remote / "perfil.json").write_text('{"nombre": ', encoding="utf-8")
    os.utime(remote / "perfil.json", (later + 60, later + 60))
    sincronizar.sync(str(a), str(b))
    assert "Ana María" in (a / "perfil.json").read_text(encoding="utf-8")


def test_sincronizar_desde_jarvis(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "sync_folder", "")
    assert "apagada" in jv.sync_now()
    monkeypatch.setitem(jv.settings, "sync_folder", str(tmp_path / "no-existe"))
    assert "No encuentro" in jv.sync_now()
