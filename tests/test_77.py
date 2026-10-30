"""Pruebas de la 7.7: galería de conectores, bandeja de correo, eventos y conectores con aprobación."""
import datetime
import json
import time

import aprobaciones
import bandeja
import conectores
import eventos
import mcp_cliente


# ----------------------------------------------------------------------------- galería
def test_galeria():
    n, c = conectores.build("homeassistant", {"url": "http://192.168.1.20:8123/api/mcp_xyz"})
    txt = conectores.add('{"mcpServers": {"hora": {"command": "uvx", "args": ["mcp-server-time"]}}}', n, c)
    assert set(mcp_cliente.parse_config(txt)) == {"hora", "casa"}         # http en la red de casa: permitido
    assert conectores.installed(txt) == ["casa", "hora"]
    assert conectores.installed(conectores.remove(txt, "hora")) == ["casa"]
    n, c = conectores.build("github", {"token": "github_pat_123"})
    assert c["headers"]["Authorization"] == "Bearer github_pat_123"
    for bad in (("github", {}), ("notion", {"token": ""}), ("nada", {})):
        try:
            conectores.build(*bad)
            assert False, bad
        except ValueError:
            pass
    try:
        mcp_cliente.parse_config('{"mcpServers": {"x": {"url": "http://evil.example.com/mcp"}}}')
        assert False, "http fuera de casa no"
    except ValueError:
        pass
    assert {p["id"] for p in conectores.public()} >= {"homeassistant", "github", "notion", "todoist", "hora", "web"}


def test_galeria_desde_ajustes(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "mcp_servers", "")
    monkeypatch.setitem(jv.settings, "mcp_trusted", "")
    monkeypatch.setattr(jv, "mcp_reconfigure", lambda: None)
    r = jv.handle_gallery_add({"id": "hora", "values": {}})
    assert r["ok"] and "hora" in jv.settings["mcp_servers"] and "hora" in jv.settings["mcp_trusted"]   # de confianza por defecto
    r = jv.handle_gallery_add({"id": "homeassistant", "values": {"url": "http://homeassistant.local:8123/api/mcp"}, "trusted": False})
    assert r["ok"] and "casa" in r["installed"] and "casa" not in jv.settings["mcp_trusted"]
    assert not jv.handle_gallery_add({"id": "github", "values": {}})["ok"]
    r = jv.handle_gallery_remove({"name": "casa"})
    assert "casa" not in r["installed"]


def test_conector_sin_confianza_pide_aprobacion(jv, monkeypatch, tmp_path):
    aprobaciones.configure(str(tmp_path))
    monkeypatch.setitem(jv.settings, "approvals_telegram", False)
    monkeypatch.setitem(jv.settings, "mcp_trusted", "")
    calls = []
    monkeypatch.setattr(jv.mcp_hub, "find", lambda tid: object())
    monkeypatch.setattr(jv.mcp_hub, "call", lambda tid, args: (calls.append((tid, args)), ("hecho", False))[1])
    jv.run_mcp("mcp__casa__apagar_luz", {"area": "sala"}, "apaga la luz de la sala")
    assert not calls and aprobaciones.latest()["titulo"].startswith("Usar «apagar_luz»")
    jv.process_command("sí")
    for _ in range(100):
        if calls:
            break
        time.sleep(0.02)
    assert calls == [("mcp__casa__apagar_luz", {"area": "sala"})]


# ----------------------------------------------------------------------------- correo
RAW = (b"From: =?utf-8?q?Ana_Coordinadora?= <ana@colegio.edu.co>\r\nTo: yo@gmail.com\r\nSubject: =?utf-8?q?Reuni=C3=B3n_del_jueves?=\r\n"
       b"Date: Thu, 29 Oct 2026 10:00:00 -0500\r\nMessage-ID: <abc@colegio>\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
       b"Hola, \xc2\xbfpuedes asistir a la reuni\xc3\xb3n del jueves a las 3?\r\n\r\nEl lun, 26 oct 2026 alguien escribi\xc3\xb3:\r\n> viejo\r\n")
PROMO = (b"From: Tienda <noreply@tienda.com>\r\nSubject: Ofertas\r\nList-Unsubscribe: <mailto:x@y>\r\nContent-Type: text/html\r\n\r\n"
         b"<html><style>p{}</style><p>50% de descuento</p></html>")


def test_leer_correos():
    m = bandeja.parse(RAW, "7")
    assert m["de"] == "ana@colegio.edu.co" and m["de_nombre"] == "Ana Coordinadora" and m["asunto"] == "Reunión del jueves"
    assert "puedes asistir" in m["texto"] and "viejo" not in m["texto"] and m["msgid"] == "<abc@colegio>" and not m["masivo"]
    p = bandeja.parse(PROMO)
    assert p["masivo"] and "descuento" in p["texto"] and "p{}" not in p["texto"]
    assert bandeja.importance(m, {"ana@colegio.edu.co"}) > bandeja.importance(p)
    assert bandeja.find([p, m], "la coordinadora") is m and bandeja.find([p, m], "ana") is m


class FakeIMAP:
    def __init__(self, host, timeout=20):
        self.host = host
        FakeIMAP.ro = None

    def login(self, user, pw):
        if pw != "abcd":
            raise __import__("imaplib").IMAP4.error("bad")

    def select(self, box, readonly=False):
        FakeIMAP.ro = readonly

    def uid(self, cmd, *args):
        if cmd == "search":
            return "OK", [b"1 2"]
        return "OK", [(b"1 (BODY[]", RAW if args[0] == b"2" else PROMO), b")"]

    def logout(self):
        pass


def test_bandeja_imap(monkeypatch):
    monkeypatch.setattr(bandeja.imaplib, "IMAP4_SSL", FakeIMAP)
    msgs = bandeja.fetch_recent("yo@gmail.com", "abcd")
    assert FakeIMAP.ro is True                                         # solo lectura: no marca nada
    assert [m["asunto"] for m in msgs] == ["Reunión del jueves", "Ofertas"]
    try:
        bandeja.fetch_recent("yo@gmail.com", "mala")
        assert False
    except RuntimeError as e:
        assert "contraseña de aplicación" in str(e)


def test_correo_por_voz_y_respuesta_aprobada(jv, monkeypatch, tmp_path):
    aprobaciones.configure(str(tmp_path))
    monkeypatch.setattr(bandeja.imaplib, "IMAP4_SSL", FakeIMAP)
    for k, v in {"email_address": "yo@gmail.com", "email_app_password": "abcd", "email_read": True, "approvals_telegram": False,
                 "email_sender_name": "Zaid"}.items():
        monkeypatch.setitem(jv.settings, k, v)
    jv.mail_cache.update(t=0, msgs=[], last=None)
    rec = jv._rec
    rec.clear()
    jv.state["ai"] = "error"
    jv.process_command("¿qué correos importantes tengo?")
    assert rec.replies[-1][1] == "CORREO" and "Ana Coordinadora" in rec.replies[-1][0] and "Ofertas" not in rec.replies[-1][0]
    jv.process_command("lee el correo de la coordinadora")
    assert "puedes asistir" in rec.replies[-1][0]
    sent = []
    monkeypatch.setattr(jv.correo, "send", lambda *a, **k: sent.append((a, k)))
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, json_mode=False, max_tokens=None: '{"cuerpo": "Hola Ana, sí asisto. Zaid"}')
    jv.state["ai"] = "ok"
    jv.process_command("contéstale que sí asisto")
    assert not sent and "¿La envío?" in rec.replies[-1][0]           # antes de enviar, pregunta
    jv.process_command("sí")
    for _ in range(100):
        if sent:
            break
        time.sleep(0.02)
    jv.state["ai"] = "unknown"
    a, k = sent[0]
    assert a[2] == "ana@colegio.edu.co" and a[3] == "Re: Reunión del jueves" and "sí asisto" in a[4]
    assert k["in_reply_to"] == "<abc@colegio>"


# ----------------------------------------------------------------------------- eventos
def test_eventos():
    ev = eventos.validate({"titulo": "Reunión con padres", "fecha": "2026-11-05", "hora": "15:00", "duracion_min": 45, "lugar": "Sala 2"})
    url = eventos.google_url(ev)
    assert "action=TEMPLATE" in url and "20261105T150000%2F20261105T154500" in url and "Sala+2" in url
    assert "jueves 5 de noviembre a las 15:00" in eventos.spoken(ev)
    ics = eventos.ics(ev, now=datetime.datetime(2026, 10, 30))
    assert "DTSTART:20261105T150000" in ics and "SUMMARY:Reunión con padres" in ics and "\r\n" in ics
    allday = eventos.validate({"titulo": "Día del idioma", "fecha": "2026-04-23"})
    assert "dates=20260423%2F20260424" in eventos.google_url(allday) and "DTSTART;VALUE=DATE:20260423" in eventos.ics(allday)
    for bad in ({"titulo": "x", "fecha": "mañana"}, {"fecha": "2026-01-01"}, "nada"):
        try:
            eventos.validate(bad)
            assert False
        except ValueError:
            pass
    assert eventos.is_event("agenda una reunion con los padres de juan el jueves a las 3")
    assert eventos.is_event("ponme en el calendario el consejo academico el lunes")
    assert not eventos.is_event("que tengo en la agenda") and not eventos.is_event("agenda que tengo hoy")


def test_agendar_por_voz(jv, monkeypatch, tmp_path):
    aprobaciones.configure(str(tmp_path))
    monkeypatch.setitem(jv.settings, "approvals_telegram", False)
    monkeypatch.setitem(jv.settings, "calendar_create", "google")
    opened = []
    import nucleo.conecta as nc
    monkeypatch.setattr(nc.webbrowser, "open", lambda u: opened.append(u))
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, json_mode=False, max_tokens=None:
                        json.dumps({"titulo": "Reunión con los padres de Juan", "fecha": "2026-11-05", "hora": "15:00"}))
    jv.state["ai"] = "ok"
    rec = jv._rec
    rec.clear()
    jv.process_command("agenda una reunión con los padres de Juan el jueves a las 3")
    assert "¿Está bien?" in rec.replies[-1][0] and not opened
    jv.process_command("sí")
    for _ in range(100):
        if opened:
            break
        time.sleep(0.02)
    jv.state["ai"] = "unknown"
    assert opened and "calendar.google.com" in opened[0]
    monkeypatch.setitem(jv.settings, "calendar_create", "ics")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    jv.event_create(eventos.validate({"titulo": "Consejo", "fecha": "2026-11-09", "hora": "07:00"}))
    assert (tmp_path / "Eventos").exists() and any(p.suffix == ".ics" for p in (tmp_path / "Eventos").iterdir())
