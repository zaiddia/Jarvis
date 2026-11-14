"""12.30: «Conectar en 3 pasos» (WhatsApp con CallMeBot y correo con contraseña de aplicación)."""
import urllib.parse

import pytest

import whatsapp


def test_numero_y_enlace():
    n = whatsapp.normalize_phone
    assert n("300 123 4567") == "+573001234567" and n("573001234567") == "+573001234567" and n("+57 300-123-4567") == "+573001234567"
    assert n("0034 612 345 678") == "+34612345678" and n("123") == "" and n("") == ""
    link = whatsapp.activate_link()
    assert link.startswith("https://wa.me/34698288973?") and urllib.parse.parse_qs(link.split("?", 1)[1])["text"] == [whatsapp.ACTIVATE]


@pytest.fixture
def cx(jv, monkeypatch):
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    for k in ("whatsapp_phone", "whatsapp_apikey", "email_address", "email_app_password", "email_sender_name"):
        monkeypatch.setitem(jv.settings, k, "")
    opened = []
    monkeypatch.setattr(jv.sys.modules["nucleo.conectar"].webbrowser, "open", lambda u: opened.append(u))
    monkeypatch.setattr(jv, "_open_page", lambda path, title, holder: opened.append(path))
    jv._cx["wa_ok"] = None
    return opened


def test_whatsapp_guardar_y_probar(jv, cx, monkeypatch):
    sent = []
    monkeypatch.setattr(jv, "whatsapp_send", lambda text: sent.append(text) or True)
    r = jv.handle_connect_save({"kind": "whatsapp", "phone": "300 123 4567", "apikey": " 123 456 "})
    assert r["ok"] and r["phone"] == "+573001234567" and jv.settings["whatsapp_apikey"] == "123456" and sent
    assert jv.handle_connect_state()["whatsapp"]["ready"]
    monkeypatch.setattr(jv, "whatsapp_send", lambda text: False)
    r = jv.handle_connect_save({"kind": "whatsapp", "phone": "+573001234567", "apikey": ""})          # la clave guardada se conserva
    assert not r["ok"] and "24 horas" in r["msg"] and jv.settings["whatsapp_apikey"] == "123456"
    assert not jv.handle_connect_state()["whatsapp"]["ready"]                                           # la prueba falló: sin ✓
    assert "indicativo" in jv.handle_connect_save({"kind": "whatsapp", "phone": "12", "apikey": "1"})["msg"]
    jv.settings["whatsapp_apikey"] = ""
    assert "Falta la clave" in jv.handle_connect_save({"kind": "whatsapp", "phone": "3001234567", "apikey": ""})["msg"]


def test_correo_solo_guarda_si_entra(jv, cx, monkeypatch):
    monkeypatch.setattr(jv, "email_test", lambda a, p: {"ok": False, "msg": "Google rechazó la contraseña."})
    r = jv.handle_connect_save({"kind": "correo", "address": "ana@gmail.com", "password": "abcd efgh ijkl mnop"})
    assert not r["ok"] and "rechazó" in r["msg"] and jv.settings["email_address"] == ""
    seen = []
    monkeypatch.setattr(jv, "email_test", lambda a, p: seen.append((a, p)) or {"ok": True, "msg": "ok"})
    r = jv.handle_connect_save({"kind": "correo", "address": "ana@gmail.com", "password": "abcd efgh ijkl mnop", "name": "Ana"})
    assert r["ok"] and seen[-1] == ("ana@gmail.com", "abcdefghijklmnop")
    assert (jv.settings["email_address"], jv.settings["email_app_password"], jv.settings["email_sender_name"]) == ("ana@gmail.com", "abcdefghijklmnop", "Ana")


def test_enlaces_permitidos_y_voz(jv, cx, ask):
    assert jv.handle_connect_open({"k": "g_apppass"})["ok"] and cx[-1] == "https://myaccount.google.com/apppasswords"
    assert not jv.handle_connect_open({"k": "https://otra.com"})["ok"]                                  # solo los de la lista
    assert ask("ayúdame a conectar el WhatsApp")[0] == "CONECTAR" and cx[-1] == "/conectar#whatsapp"
    assert ask("conecta el correo")[0] == "CONECTAR" and cx[-1] == "/conectar#correo"
    assert ask("abre el asistente de conexiones")[0] == "CONECTAR" and cx[-1] == "/conectar"


def test_pagina_y_salud(jv):
    c = jv.app.test_client()
    html = c.get("/conectar").get_data(as_text=True)
    assert "+34 698 28 89 73" in html and "I allow callmebot to send me messages" in html and 'data-open="g_apppass"' in html
    png = c.get("/conectar/qr-whatsapp.png")
    assert png.status_code == 200 and png.data[:4] == b"\x89PNG"
    import os
    js = open(os.path.join(os.path.dirname(__file__), "..", "static", "js", "settings.js"), encoding="utf-8").read()
    assert 'startsWith("conectar:")' in js and "Conectar paso a paso" in js
    src = open(os.path.join(os.path.dirname(__file__), "..", "nucleo", "salud.py"), encoding="utf-8").read()
    assert '"conectar:whatsapp"' in src and '"conectar:correo"' in src
