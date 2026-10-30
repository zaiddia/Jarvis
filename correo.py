"""Correo por voz: Jarvis redacta el correo con la IA, lo lee y, solo si confirmas, lo envía
por tu cuenta de Gmail (SMTP con una «contraseña de aplicación», no tu clave normal).

jarvis.py pone la IA y lee los ajustes; aquí va la agenda de correos, el prompt y el envío.
"""
import re
import smtplib
import ssl
import unicodedata
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

SMTP = {"gmail.com": ("smtp.gmail.com", 587), "googlemail.com": ("smtp.gmail.com", 587),
        "outlook.com": ("smtp-mail.outlook.com", 587), "hotmail.com": ("smtp-mail.outlook.com", 587),
        "live.com": ("smtp-mail.outlook.com", 587)}
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def normalize(text):
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def parse_book(text):
    """«Coordinadora = ana@colegio.edu.co» (una por línea) -> {clave_normalizada: (nombre, correo)}."""
    book = {}
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        name, addr = line.split("=", 1)
        addr = addr.strip()
        name = name.strip()
        if _EMAIL.fullmatch(addr):
            book[normalize(name)] = (name, addr)
    return book


def resolve_recipient(who, book):
    """Devuelve (nombre, correo) a partir de lo dicho: un correo literal, o un nombre de la agenda."""
    who = (who or "").strip()
    m = _EMAIL.search(who)
    if m:
        return ("", m.group(0))
    key = normalize(who)
    if key in book:
        return book[key]
    import difflib
    for k in book:                                     # «a la coordinadora» -> «coordinadora»
        if k in key or key in k:
            return book[k]
    match = difflib.get_close_matches(key, list(book), n=1, cutoff=0.7)
    return book[match[0]] if match else None


def valid_sender(addr):
    return bool(addr and _EMAIL.fullmatch(addr.strip()))


def prompt(instruccion, remitente_nombre=""):
    return ("Eres el asistente de un docente en Colombia y le ayudas a escribir un correo. "
            f"Lo que te pidió: «{instruccion}».\n"
            "Devuelve SOLO un JSON: {\"asunto\": \"…\", \"cuerpo\": \"…\"}.\n"
            "El cuerpo es un correo breve, cordial y claro, en español, bien redactado (no es para "
            "escucharse: puede tener saludo y despedida). "
            + (f"Fírmalo como {remitente_nombre}. " if remitente_nombre else "")
            + "No inventes datos que no estén en la petición (fechas, nombres, cifras). Si falta un dato "
            "importante, deja un espacio entre corchetes como [hora]. Sin markdown.")


def validate(d):
    if not isinstance(d, dict):
        raise ValueError("respuesta no válida")
    asunto = re.sub(r"\s+", " ", str(d.get("asunto") or "")).strip()[:150] or "Mensaje"
    cuerpo = str(d.get("cuerpo") or "").strip()[:4000]
    if not cuerpo:
        raise ValueError("el correo vino vacío")
    return {"asunto": asunto, "cuerpo": cuerpo}


def spoken_preview(to_name, to_addr, asunto, cuerpo):
    """Lo que Jarvis lee en voz alta antes de enviar."""
    dest = to_name or to_addr
    cuerpo_voz = re.sub(r"\s+", " ", cuerpo).strip()
    if len(cuerpo_voz) > 400:
        cuerpo_voz = cuerpo_voz[:400].rsplit(" ", 1)[0] + "…"
    falta = " Ojo: dejé algún dato entre corchetes para que lo completes." if "[" in cuerpo else ""
    return (f"Le voy a escribir a {dest}. Asunto: {asunto}. Dice: {cuerpo_voz}."
            f"{falta} ¿Lo envío? Di «sí, envíalo» o «no».")


def send(sender, app_password, to_addr, asunto, cuerpo, sender_name="", in_reply_to=""):
    """Envía el correo por SMTP. Lanza una excepción con un mensaje claro si algo falla."""
    dominio = sender.split("@")[-1].lower()
    host, port = SMTP.get(dominio, ("smtp.gmail.com", 587))
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name or "", sender))
    msg["To"] = to_addr
    msg["Subject"] = asunto
    if in_reply_to:                                    # respuesta: que quede en el mismo hilo
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(cuerpo)
    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.ehlo()
            s.starttls(context=ssl.create_default_context())
            s.login(sender, app_password)
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError("tu cuenta rechazó la contraseña. Usa una «contraseña de aplicación» de 16 letras "
                           "(no tu clave normal); se crea en la seguridad de tu cuenta de Google.")
    except smtplib.SMTPRecipientsRefused:
        raise RuntimeError("el correo del destinatario no es válido.")
    except Exception as e:
        raise RuntimeError(f"no pude conectar con el servidor de correo ({e}).")
    return host
