"""Avisos al WhatsApp (7.9) con CallMeBot, un servicio gratuito para mandarte mensajes a ti mismo.

Solo envía (recordatorios, avisos, tareas y aprobaciones pendientes); para responderle a Jarvis desde el celular
usa Telegram o el panel. Activación: agrega el número de CallMeBot a tus contactos y escríbele
«I allow callmebot to send me messages»; te responde con tu clave (apikey).
"""
import urllib.parse

API = "https://api.callmebot.com/whatsapp.php"
BOT = "+34 698 28 89 73"                                   # 12.30: el número del bot de CallMeBot (puede cambiar: ver callmebot.com)
ACTIVATE = "I allow callmebot to send me messages"
HELP_URL = "https://www.callmebot.com/blog/free-api-whatsapp-messages/"


def activate_link(bot=BOT):
    """Abre WhatsApp con el mensaje de activación ya escrito para el bot (wa.me)."""
    return "https://wa.me/" + "".join(c for c in bot if c.isdigit()) + "?" + urllib.parse.urlencode({"text": ACTIVATE})


def normalize_phone(phone, country="57"):
    """«300 123 4567» → «+573001234567»; «573001234567» → «+573001234567»; «+57 300…» igual. → "" si no parece un número."""
    raw = str(phone or "").strip()
    digits = "".join(c for c in raw if c.isdigit())
    if not digits:
        return ""
    if raw.startswith("+") or raw.startswith("00"):
        digits = digits[2:] if raw.startswith("00") else digits
    elif len(digits) == 10 and digits.startswith("3"):    # celular de Colombia sin indicativo
        digits = country + digits
    out = "+" + digits
    return out if valid_phone(out) else ""


def url(phone, apikey, text):
    phone = "".join(c for c in str(phone) if c.isdigit() or c == "+")
    return API + "?" + urllib.parse.urlencode({"phone": phone, "text": str(text)[:1500], "apikey": str(apikey).strip()})


def valid_phone(phone):
    digits = "".join(c for c in str(phone) if c.isdigit())
    return 10 <= len(digits) <= 15
