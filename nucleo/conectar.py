"""12.30: «Conectar en 3 pasos»: WhatsApp (CallMeBot) y correo (contraseña de aplicación) sin pelear con Ajustes.

Una página con cada paso: el número del bot y un botón (y un QR para el celular) que abre WhatsApp con el mensaje de
activación ya escrito; los enlaces directos de Google para la verificación en dos pasos y la contraseña de aplicación;
y «Guardar y probar», que solo guarda si la prueba sale bien (el correo) o te dice qué falta. Se abre por voz
(«ayúdame a conectar el WhatsApp», «conecta el correo») o desde la revisión de salud («Conectar paso a paso»).
"""
import io
import re
import webbrowser

import whatsapp
from nucleo import J

CONNECT_LINKS = {                                            # solo estas páginas se abren desde el asistente
    "wa_activar": whatsapp.activate_link(),
    "wa_ayuda": whatsapp.HELP_URL,
    "g_2pasos": "https://myaccount.google.com/signinoptions/twosv",
    "g_apppass": "https://myaccount.google.com/apppasswords",
}
_cx = {"win": None, "wa_ok": None}                           # wa_ok: cómo salió la última prueba de WhatsApp aquí


@J.app.route("/conectar")
def connect_page():
    from flask import render_template
    return render_template("conectar.html", version=J.VERSION, asset_v=getattr(J, "ASSET_V", ""), look=J.settings.get("look", "clasico"),
                           bot=whatsapp.BOT, activar=whatsapp.ACTIVATE)


@J.app.route("/conectar/qr-whatsapp.png")
def connect_qr():
    import qrcode
    from flask import Response
    buf = io.BytesIO()
    qrcode.make(CONNECT_LINKS["wa_activar"], box_size=8, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


def open_connect_page(which=""):
    J._open_page("/conectar" + (f"#{which}" if which in ("whatsapp", "correo") else ""), "Conectar", _cx)


def connect_state():
    s = J.settings
    return {"whatsapp": {"phone": s["whatsapp_phone"], "has_key": bool(s["whatsapp_apikey"].strip()), "ready": J.whatsapp_ready() and _cx["wa_ok"] is not False},
            "correo": {"address": s["email_address"], "has_pw": bool(s["email_app_password"].strip()), "method": J.mail_method(),
                       "name": s["email_sender_name"]},
            "bot": whatsapp.BOT}


@J.socketio.on("connect_state")
def handle_connect_state(data=None):
    return connect_state()


@J.socketio.on("connect_open")
def handle_connect_open(data=None):
    url = CONNECT_LINKS.get(str((data or {}).get("k") or ""))
    if not url:
        return {"ok": False}
    webbrowser.open(url)
    return {"ok": True}


@J.socketio.on("open_connect")
def handle_open_connect(data=None):
    open_connect_page(str((data or {}).get("k") or ""))
    return {"ok": True}


def connect_save_whatsapp(phone, apikey):
    num = whatsapp.normalize_phone(phone)
    if not num:
        return {"ok": False, "msg": "Ese número no parece completo. Escríbelo con el indicativo, por ejemplo +57 300 123 4567."}
    key = re.sub(r"\s+", "", str(apikey or ""))
    if not key and not J.settings["whatsapp_apikey"].strip():
        return {"ok": False, "msg": "Falta la clave: es el número que te manda el bot por WhatsApp después del paso 2."}
    J.apply_settings({"whatsapp_phone": num, **({"whatsapp_apikey": key} if key else {})})
    ok = J.whatsapp_send("✅ Jarvis conectado: aquí te llegarán tus avisos.")
    _cx["wa_ok"] = ok
    return {"ok": ok, "phone": num,
            "msg": "¡Listo! Te envié un WhatsApp de prueba." if ok else
            "Guardé el número y la clave, pero CallMeBot no aceptó el mensaje. Revisa que la clave sea la que te mandó el bot "
            "para ESTE número; si el bot nunca te respondió, espera 24 horas y repite el paso 2."}


def connect_save_email(address, password, name=""):
    addr = str(address or "").strip()
    pw = J.clean_app_password(str(password or ""))
    r = J.email_test(addr, pw)
    if not r.get("ok"):
        return {"ok": False, "msg": r.get("msg") or r.get("error") or "No pude entrar con esos datos."}
    J.apply_settings({"email_address": addr, "email_app_password": pw, **({"email_sender_name": name.strip()} if str(name).strip() else {})})
    return {"ok": True, "msg": "¡Listo! Tu correo quedó conectado: ya puedes decir «escríbele un correo a…» y «¿qué correos tengo?»."}


@J.socketio.on("connect_save")
def handle_connect_save(data=None):
    d = data or {}
    if d.get("kind") == "whatsapp":
        return connect_save_whatsapp(d.get("phone"), d.get("apikey"))
    if d.get("kind") == "correo":
        return connect_save_email(d.get("address"), d.get("password"), str(d.get("name") or ""))
    return {"ok": False, "msg": "¿Qué quieres conectar?"}


_CX_RE = re.compile(r"\b(?:ayudame a |quiero |necesito )?(?:conecta|conectar|configura|configurar|activa|activar|vincula|vincular)\s+"
                    r"(?:el |mi |los |las )?(whatsapp|wasap|guasap|correo|gmail|email|mail|avisos? (?:al|de|por) whatsapp)\b|"
                    r"\basistente de conexion(?:es)?\b|\bconectar en (?:3|tres) pasos\b")


def connect_voice(text, t):
    m = _CX_RE.search(t)
    if not m:
        return False
    w = m.group(1) or ""
    which = "whatsapp" if re.search(r"whatsapp|wasap|guasap", w) else "correo" if w else ""
    open_connect_page(which)
    J.reply({"whatsapp": "Te abrí «Conectar en 3 pasos» en WhatsApp: el botón te abre el chat con el bot y el mensaje ya escrito.",
             "correo": "Te abrí «Conectar en 3 pasos» en el correo: con dos enlaces de Google y tu contraseña de aplicación queda listo."}
            .get(which, "Te abrí «Conectar en 3 pasos»: WhatsApp y correo, cada uno con sus pasos."), "CONECTAR")
    return True


__all__ = ['CONNECT_LINKS', '_CX_RE', '_cx', 'connect_page', 'connect_qr', 'connect_save_email', 'connect_save_whatsapp', 'connect_state',
           'connect_voice', 'handle_connect_open', 'handle_connect_save', 'handle_connect_state', 'handle_open_connect', 'open_connect_page']
