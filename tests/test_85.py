"""Pruebas de la 8.5: correo con tu cuenta de Google (sin contraseña de aplicación) y la prueba con lo escrito."""
import base64
import email
import smtplib

import classroom
import correo
import gmail

RAW = (b"From: Coordinadora <coord@colegio.edu.co>\r\nTo: yo@gmail.com\r\nSubject: Reunion\r\n"
       b"Date: Fri, 30 Oct 2026 10:00:00 -0500\r\nMessage-ID: <abc@x>\r\n\r\nHay reunion el lunes.\r\n")


class FakeGmail:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def call(self, method, path, params=None, body=None, base=classroom.API):
        assert base == gmail.API
        self.calls.append((method, path, params, body))
        if self.fail:
            raise classroom.ClassroomError("Gmail API desactivada")
        if path == "users/me/profile":
            return {"emailAddress": "yo@gmail.com"}
        if path == "users/me/messages":
            return {"messages": [{"id": "m1"}]}
        if path == "users/me/messages/m1":
            return {"raw": base64.urlsafe_b64encode(RAW).decode().rstrip("=")}
        return {"id": "sent"}


def _google(jv, monkeypatch, client):
    monkeypatch.setattr(jv, "classroom_client", lambda: client)
    monkeypatch.setitem(jv.settings, "google_scopes", " ".join(classroom.SCOPES))


def test_mensaje_de_gmail():
    raw = gmail.build("yo@gmail.com", "ana@x.co", "Hola", "Cuerpo ñ", "Diana", "<abc@x>")
    m = email.message_from_bytes(base64.urlsafe_b64decode(raw))
    assert m["To"] == "ana@x.co" and m["In-Reply-To"] == "<abc@x>" and "Diana" in m["From"]
    assert gmail.has_scopes(" ".join(classroom.SCOPES)) and not gmail.has_scopes("https://www.googleapis.com/auth/classroom.courses.readonly")


def test_enviar_y_leer_con_la_cuenta_de_google(jv, monkeypatch):
    g = FakeGmail()
    _google(jv, monkeypatch, g)
    monkeypatch.setitem(jv.settings, "email_app_password", "")
    assert jv.mail_method() == "google"
    assert jv.mail_send("ana@x.co", "Hola", "Texto") == "gmail"
    assert g.calls[-1][1] == "users/me/messages/send" and g.calls[-1][3]["raw"]
    msgs = jv.mail_fetch_recent(days=2)
    assert msgs[0]["de"] == "coord@colegio.edu.co" and msgs[0]["asunto"] == "Reunion" and msgs[0]["msgid"] == "<abc@x>"
    assert g.calls[-2][2]["q"] == "in:inbox newer_than:2d"
    assert "cuenta de Google" in jv.email_test()["msg"]


def test_si_gmail_falla_usa_la_contrasena(jv, monkeypatch):
    _google(jv, monkeypatch, FakeGmail(fail=True))
    monkeypatch.setitem(jv.settings, "email_address", "yo@gmail.com")
    monkeypatch.setitem(jv.settings, "email_app_password", "abcd efgh ijkl mnop")
    assert jv.email_password() == "abcdefghijklmnop"
    sent = []
    monkeypatch.setattr(correo, "send", lambda *a, **k: sent.append(a) or "smtp.gmail.com")
    assert jv.mail_send("ana@x.co", "Hola", "Texto") == "smtp.gmail.com"
    assert sent[0][1] == "abcdefghijklmnop"                       # sin espacios


class FakeSMTP:
    logins = []

    def __init__(self, host, port, timeout=0):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def starttls(self, context=None):
        pass

    def login(self, user, pw):
        FakeSMTP.logins.append((user, pw))
        if pw != "abcdefghijklmnop":
            raise smtplib.SMTPAuthenticationError(535, b"bad")


def test_probar_usa_lo_escrito_aunque_no_este_guardado(jv, monkeypatch):
    monkeypatch.setattr(jv, "classroom_client", lambda: None)
    monkeypatch.setitem(jv.settings, "email_address", "")
    monkeypatch.setitem(jv.settings, "email_app_password", "")
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    saved = {}
    monkeypatch.setattr(jv, "apply_settings", lambda d: saved.update(d) or {"ok": True})
    r = jv.email_test("yo@gmail.com", "mi clave normal")
    assert not r["ok"] and "13 caracteres" in r["msg"] and "Conectar con Google" in r["msg"]
    r = jv.email_test("yo@gmail.com", "abcd efgh ijkl mnoq")
    assert not r["ok"] and "rechazó" in r["msg"]
    r = jv.email_test("yo@gmail.com", "abcd efgh ijkl mnop")
    assert r["ok"] and "La guardé" in r["msg"] and saved == {"email_app_password": "abcdefghijklmnop", "email_address": "yo@gmail.com"}
    assert FakeSMTP.logins[-1] == ("yo@gmail.com", "abcdefghijklmnop")


def test_sin_conexion_lo_dice_claro(jv, monkeypatch):
    monkeypatch.setattr(jv, "classroom_client", lambda: None)
    monkeypatch.setitem(jv.settings, "email_app_password", "")
    jv._rec.clear()
    jv.process_command("escríbele un correo a la coordinadora diciendo que mañana llego a las 7")
    assert "Conectar con Google" in jv._rec.said()
