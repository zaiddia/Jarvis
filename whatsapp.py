"""Avisos al WhatsApp (7.9) con CallMeBot, un servicio gratuito para mandarte mensajes a ti mismo.

Solo envía (recordatorios, avisos, tareas y aprobaciones pendientes); para responderle a Jarvis desde el celular
usa Telegram o el panel. Activación: agrega el número de CallMeBot a tus contactos y escríbele
«I allow callmebot to send me messages»; te responde con tu clave (apikey).
"""
import urllib.parse

API = "https://api.callmebot.com/whatsapp.php"


def url(phone, apikey, text):
    phone = "".join(c for c in str(phone) if c.isdigit() or c == "+")
    return API + "?" + urllib.parse.urlencode({"phone": phone, "text": str(text)[:1500], "apikey": str(apikey).strip()})


def valid_phone(phone):
    digits = "".join(c for c in str(phone) if c.isdigit())
    return 10 <= len(digits) <= 15
