"""Gmail con tu cuenta de Google (8.5): la otra forma de conectar el correo, sin contraseña de aplicación.

Usa la misma conexión de Google que Classroom (botón «Conectar con Google»): enviar correos y leer tu bandeja
(solo lectura) con la API de Gmail. Si no está conectada, Jarvis sigue usando la contraseña de aplicación.
"""
import base64
from email.message import EmailMessage
from email.utils import formataddr

API = "https://gmail.googleapis.com/gmail/v1/"
SCOPES = ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"]


def has_scopes(granted):
    g = str(granted or "")
    return all(s in g for s in SCOPES[:1])


def build(sender, to_addr, asunto, cuerpo, sender_name="", in_reply_to=""):
    msg = EmailMessage()
    if sender:
        msg["From"] = formataddr((sender_name or "", sender))
    msg["To"] = to_addr
    msg["Subject"] = asunto
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(cuerpo)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def send(client, sender, to_addr, asunto, cuerpo, sender_name="", in_reply_to=""):
    return client.call("POST", "users/me/messages/send", body={"raw": build(sender, to_addr, asunto, cuerpo, sender_name,
                                                                             in_reply_to)}, base=API)


def profile(client):
    return client.call("GET", "users/me/profile", base=API)


def fetch_recent(client, days=3, limit=25):
    """[(id, bytes del correo)] de la bandeja de entrada de los últimos días, más nuevos primero."""
    d = client.call("GET", "users/me/messages", {"q": f"in:inbox newer_than:{int(days)}d", "maxResults": int(limit)}, base=API)
    out = []
    for m in d.get("messages") or []:
        full = client.call("GET", f"users/me/messages/{m['id']}", {"format": "raw"}, base=API)
        raw = full.get("raw")
        if raw:
            out.append((m["id"], base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))))
    return out
