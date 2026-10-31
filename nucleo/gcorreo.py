"""8.5: el correo por voz con dos formas de conexión: tu cuenta de Google (sin contraseña de aplicación) o la
contraseña de aplicación de siempre. Todo el envío y la lectura del correo de Jarvis pasa por aquí.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import re

import bandeja
import classroom
import correo
import gmail
from nucleo import J


def email_password():
    """La contraseña de aplicación sin espacios (Google la muestra como «abcd efgh ijkl mnop»)."""
    return re.sub(r"\s+", "", J.settings["email_app_password"])


def gmail_ready():
    return bool(J.classroom_client()) and gmail.has_scopes(J.settings["google_scopes"])


def mail_method():
    if J.gmail_ready():
        return "google"
    if correo.valid_sender(J.settings["email_address"]) and J.email_password():
        return "password"
    return ""


def mail_send(to_addr, asunto, cuerpo, in_reply_to=""):
    """Envía con la cuenta de Google si está conectada; si no, por SMTP. Lanza RuntimeError con un mensaje claro."""
    name = J.settings["email_sender_name"].strip()
    if J.gmail_ready():
        try:
            gmail.send(J.classroom_client(), J.settings["email_address"].strip(), to_addr, asunto, cuerpo, name, in_reply_to)
            return "gmail"
        except classroom.ClassroomError as e:
            if not J.email_password():
                raise RuntimeError(f"Gmail no lo aceptó: {e}")
            J.log_terminal(f"Gmail con tu cuenta de Google falló ({e}); pruebo con la contraseña de aplicación.", "AVISO")
    if not J.email_password():
        raise RuntimeError("el correo no está conectado: pulsa «Conectar con Google» o pon una contraseña de aplicación "
                           "(Ajustes › Integraciones › Correo).")
    return correo.send(J.settings["email_address"].strip(), J.email_password(), to_addr, asunto, cuerpo, name,
                       in_reply_to=in_reply_to)


def mail_fetch_recent(days=3):
    """Correos recientes ya leídos con bandeja.parse (más nuevos primero)."""
    if J.gmail_ready():
        try:
            return [bandeja.parse(raw, mid) for mid, raw in gmail.fetch_recent(J.classroom_client(), days)]
        except classroom.ClassroomError as e:
            if not J.email_password():
                raise RuntimeError(f"Gmail: {e}")
    if not J.email_password():
        raise RuntimeError("el correo no está conectado (Ajustes › Integraciones › Correo).")
    return bandeja.fetch_recent(J.settings["email_address"], J.email_password(), days=days)


def email_test(address="", password=""):
    """Prueba la conexión con lo que esté escrito en Ajustes (aunque no lo hayas guardado)."""
    if J.gmail_ready() and not password:
        try:
            addr = gmail.profile(J.classroom_client()).get("emailAddress", "")
            return {"ok": True, "msg": f"Conectado con tu cuenta de Google ({addr}). Ya puedes dictar y leer correos."}
        except classroom.ClassroomError as e:
            return {"ok": False, "msg": f"Tu cuenta de Google está conectada, pero Gmail no responde: {e}. Activa la "
                                        "«Gmail API» en tu proyecto de Google Cloud y vuelve a conectar."}
    addr = (address or J.settings["email_address"]).strip()
    pw = re.sub(r"\s+", "", password or J.settings["email_app_password"])
    if not correo.valid_sender(addr):
        return {"ok": False, "msg": "Escribe tu dirección de Gmail."}
    if not pw:
        return {"ok": False, "msg": "Escribe la contraseña de aplicación (16 letras), o usa «Conectar con Google»."}
    if len(pw) != 16 and addr.lower().endswith(("@gmail.com", "@googlemail.com")):
        return {"ok": False, "msg": f"La contraseña tiene {len(pw)} caracteres y la de aplicación de Google tiene 16 letras. "
                                    "Tu clave normal no sirve: créala en myaccount.google.com/apppasswords (necesita la "
                                    "verificación en dos pasos), o usa «Conectar con Google»."}
    import smtplib
    import ssl
    host, port = correo.SMTP.get(addr.split("@")[-1].lower(), ("smtp.gmail.com", 587))
    try:
        with smtplib.SMTP(host, port, timeout=20) as sm:
            sm.ehlo()
            sm.starttls(context=ssl.create_default_context())
            sm.login(addr, pw)
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "msg": "Google rechazó la contraseña. Revisa que sea una contraseña de aplicación nueva (no tu "
                                    "clave normal) y que la verificación en dos pasos esté activa. Si tu cuenta es del "
                                    "colegio, puede que el administrador no las permita: usa «Conectar con Google»."}
    except Exception as e:
        return {"ok": False, "msg": f"No pude conectar con {host}: {e}"}
    msg = f"Conexión correcta con {host}."
    if password and password != J.settings["email_app_password"]:
        J.apply_settings({"email_app_password": pw, "email_address": addr})   # funcionó: se guarda (cifrada)
        msg += " La guardé."
    return {"ok": True, "msg": msg + " Ya puedes dictar correos."}


__all__ = ['email_password', 'email_test', 'gmail_ready', 'mail_fetch_recent', 'mail_method', 'mail_send']
