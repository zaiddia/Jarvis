"""7.7: galería de conectores, tu bandeja de correo, eventos en tu calendario y conectores con aprobación.

  · Galería (conectores.py): Home Assistant, GitHub, Notion, Todoist, hora y web con un formulario.
  · Correo (bandeja.py): «¿qué correos importantes tengo?», «lee el de la coordinadora», «contéstale que sí asisto»
    (la respuesta pasa por el centro de aprobaciones).
  · Calendario (eventos.py): «agenda una reunión con los padres de Juan el jueves a las 3».
Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import json
import os
import re
import time
import webbrowser

import bandeja
import conectores
import correo
import diario
import eventos
from nucleo import J

# ============================================================================ GALERÍA DE CONECTORES


@J.socketio.on("gallery_list")
def handle_gallery_list(data=None):
    return {"presets": conectores.public(), "installed": conectores.installed(J.settings["mcp_servers"]),
            "status": J.mcp_hub.status()}


@J.socketio.on("gallery_add")
def handle_gallery_add(data=None):
    d = data or {}
    try:
        name, cfg = conectores.build(str(d.get("id", "")), d.get("values") or {})
        new = conectores.add(J.settings["mcp_servers"], name, cfg)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    changes = {"mcp_servers": new}
    preset = conectores.PRESETS[str(d.get("id"))]
    trusted = [x.strip() for x in J.settings["mcp_trusted"].split(",") if x.strip()]
    if (d.get("trusted") if "trusted" in d else preset["confianza"]) and name not in trusted:
        changes["mcp_trusted"] = ", ".join(trusted + [name])
    errors = J.apply_settings(changes)
    if errors:
        return {"ok": False, "error": " ".join(errors)}
    J.socketio.emit("settings_updated", J.public_settings())
    J.log_terminal(f"Conector añadido desde la galería: {preset['nombre']} («{name}»).", "MCP")
    return {"ok": True, "name": name, **handle_gallery_list()}


@J.socketio.on("gallery_remove")
def handle_gallery_remove(data=None):
    name = str((data or {}).get("name", ""))
    J.apply_settings({"mcp_servers": conectores.remove(J.settings["mcp_servers"], name)})
    J.socketio.emit("settings_updated", J.public_settings())
    return {"ok": True, **handle_gallery_list()}


def mcp_approval(tid, args, prompt):
    """Un conector que no es de confianza: se pide permiso en el centro de aprobaciones."""
    import mcp_cliente
    server, tool = mcp_cliente.split_id(tid)
    detalle = json.dumps(args or {}, ensure_ascii=False)[:600]
    J.request_approval("conector", f"Usar «{tool}» del conector {server}", detalle,
                       on_ok=lambda: J.run_mcp(tid, args, prompt, confirmed=True),
                       on_no=lambda: J.reply("Vale, no uso el conector.", "MCP"))


# ============================================================================ BANDEJA DE CORREO
mail_cache = {"t": 0.0, "msgs": [], "last": None}
_MAIL_LIST = re.compile(r"\b(?:que|cuales|tengo) correos\b|\bcorreos? (?:nuevos|importantes|sin leer|recientes)\b|"
                        r"\brevisa (?:mi|el) (?:correo|email|bandeja|gmail|outlook)\b|\bque hay en mi (?:correo|bandeja)\b|"
                        r"\btengo (?:algun |algún )?correo\b|\bme (?:ha|han) escrito\b|\bme escribio alguien\b")
_MAIL_READ = re.compile(r"\b(?:lee(?:me)?|que dice|de que trata|resume(?:me)?)\s+(?:el|ese|este)?\s*(?:ultimo\s+)?correo\b(.*)$")
_MAIL_REPLY = re.compile(r"\b(?:contestale|respondele|contesta(?:le)?|responde(?:le)?)\b(?:\s+(?:el correo\s+)?(?:a|de)\s+(.+?))?"
                         r"\s+(?:que|diciendo(?: que)?|:)\s+(.+)$")


def _mail_ready():
    return correo.valid_sender(J.settings["email_address"]) and J.settings["email_app_password"].strip()


def _mail_fetch(force=False):
    if not force and time.time() - mail_cache["t"] < 300 and mail_cache["msgs"]:
        return mail_cache["msgs"]
    msgs = bandeja.fetch_recent(J.settings["email_address"], J.settings["email_app_password"].replace(" ", ""),
                                days=J.settings["email_days"])
    book = {addr.lower() for _, addr in J._mail_book().values()}
    msgs.sort(key=lambda m: (-bandeja.importance(m, book), m["fecha"]), reverse=False)
    mail_cache.update(t=time.time(), msgs=msgs)
    return msgs


def mail_voice(text, t):
    reply_m = _MAIL_REPLY.search(t)
    read_m = _MAIL_READ.search(t)
    if not (_MAIL_LIST.search(t) or read_m or reply_m):
        return False
    if not J.settings["email_read"]:
        J.reply("Leer tu correo está apagado (Ajustes › Integraciones › Correo).", "CORREO")
        return True
    if not _mail_ready():
        J.reply("Para leer tu correo pon tu dirección y la contraseña de aplicación en Ajustes › Integraciones › Correo.", "CORREO")
        return True
    try:
        msgs = _mail_fetch(force=bool(_MAIL_LIST.search(t)))
    except RuntimeError as e:
        J.reply(f"No pude revisar tu correo: {e}", "CORREO")
        return True
    if reply_m:
        who, what = (reply_m.group(1) or "").strip(), reply_m.group(2).strip()
        m = bandeja.find(msgs, who) if who else mail_cache["last"]
        if not m:
            J.reply("No sé a qué correo responder. Primero dime «lee el correo de…».", "CORREO")
            return True
        J.mail_reply(m, what)
        return True
    if read_m:
        who = read_m.group(1).strip()
        who = re.sub(r"^(?:de|del|que me (?:mando|envio|escribio))\s+", "", who)
        m = bandeja.find(msgs, who) if who else (msgs[0] if msgs else None)
        if not m:
            J.reply(f"No encuentro un correo reciente{(' de ' + who) if who else ''}.", "CORREO")
            return True
        mail_cache["last"] = m
        J.mail_read(m)
        return True
    useful = [m for m in msgs if not m["masivo"]][:8] or msgs[:5]
    if not useful:
        J.reply(f"No tienes correos en los últimos {J.settings['email_days']} días.", "CORREO")
        return True
    mail_cache["last"] = useful[0]
    if J.state.get("ai") == "ok":
        try:
            J.reply(J.ai_chat([{"role": "user", "content": bandeja.triage_prompt(useful)}], max_tokens=400).strip(), "CORREO")
            return True
        except Exception:
            pass
    J.reply(f"Tienes {len(useful)} correos que parecen importantes: " +
            "; ".join(f"de {m['de_nombre']}, «{m['asunto']}»" for m in useful[:4]) + ".", "CORREO")
    return True


def mail_read(m):
    texto = m["texto"] or "(sin texto)"
    if J.state.get("ai") == "ok" and len(texto) > 500:
        try:
            resumen = J.ai_chat([{"role": "user", "content": f"Resume en 2 o 3 frases, para decirlo en voz alta, este correo de "
                                  f"{m['de_nombre']} con asunto «{m['asunto']}»:\n{texto[:4000]}"}], max_tokens=300).strip()
            J.reply(f"Correo de {m['de_nombre']}: {resumen} Si quieres, dime «contéstale que…».", "CORREO")
            return
        except Exception:
            pass
    J.reply(f"Correo de {m['de_nombre']}, «{m['asunto']}»: {texto[:600]}", "CORREO")


def mail_reply(m, instruction):
    """Redacta la respuesta y pide aprobación antes de enviarla."""
    if J.state.get("ai") != "ok":
        J.reply("Para redactar la respuesta necesito la IA conectada.", "CORREO")
        return
    try:
        raw = J.ai_chat([{"role": "user", "content": bandeja.reply_prompt(m, instruction, J.settings["email_sender_name"])}],
                        json_mode=True, max_tokens=900)
        cuerpo = str(J._extract_json(raw).get("cuerpo", "")).strip()
    except Exception as e:
        J.reply(f"No pude redactar la respuesta: {getattr(e, 'why', e)}", "CORREO")
        return
    if not cuerpo:
        J.reply("No me salió la respuesta. Inténtalo con otras palabras.", "CORREO")
        return
    asunto = m["asunto"] if m["asunto"].lower().startswith(("re:", "re ")) else "Re: " + m["asunto"]

    def send():
        try:
            correo.send(J.settings["email_address"], J.settings["email_app_password"].replace(" ", ""), m["de"], asunto,
                        cuerpo, J.settings["email_sender_name"], in_reply_to=m.get("msgid", ""))
            J.reply(f"Respuesta enviada a {m['de_nombre']}.", "CORREO")
            diario.log("orden", f"respondí el correo de {m['de_nombre']}")
        except RuntimeError as e:
            J.reply(f"No pude enviarla: {e}", "CORREO")
    J.request_approval("correo", f"Responder a {m['de_nombre']} («{asunto}»)", cuerpo, on_ok=send,
                       on_no=lambda: J.reply("Vale, no la envío.", "CORREO"),
                       say=f"Esta es la respuesta para {m['de_nombre']}: {cuerpo[:400]} ¿La envío? Di «sí» o «no».")


# ============================================================================ EVENTOS EN EL CALENDARIO
def event_voice(text, t):
    if not eventos.is_event(t):
        return False
    if J.state.get("ai") != "ok":
        J.reply("Para entender la fecha del evento necesito la IA conectada. Mientras tanto puedo ponerte un "
                "recordatorio: «recuérdame el jueves a las 3…».", "CALENDARIO")
        return True
    try:
        raw = J.ai_chat([{"role": "user", "content": eventos.parse_prompt(text)}], json_mode=True, max_tokens=300)
        ev = eventos.validate(J._extract_json(raw))
    except Exception as e:
        J.reply(f"No entendí bien el evento ({getattr(e, 'why', e)}). Dímelo con el día y la hora.", "CALENDARIO")
        return True
    J.request_approval("evento", f"Agendar {eventos.spoken(ev)}", eventos.dumps(ev), on_ok=lambda: J.event_create(ev),
                       on_no=lambda: J.reply("Vale, no lo agendo.", "CALENDARIO"),
                       say=f"Agendo {eventos.spoken(ev)}. ¿Está bien? Di «sí» o «no».")
    return True


def event_create(ev):
    mode = J.settings["calendar_create"]
    if mode == "google":
        webbrowser.open(eventos.google_url(ev))
        J.reply("Te abrí Google Calendar con el evento listo: solo pulsa «Guardar».", "CALENDARIO")
    else:
        path = eventos.save_ics(ev, os.path.join(J.settings["output_dir"], "Eventos"))
        opened = False
        if J.IS_WIN:
            try:
                os.startfile(path)
                opened = True
            except OSError:
                pass
        J.reply("Creé el evento" + (" y lo abrí en tu calendario: confírmalo allí." if opened else f": {os.path.basename(path)}."), "CALENDARIO")
    diario.log("orden", f"agendé {ev['titulo']} ({ev['fecha']} {ev['hora']})")


@J.socketio.on("mail_test")
def handle_mail_test(data=None):
    if not _mail_ready():
        return {"ok": False, "error": "Falta tu correo o la contraseña de aplicación."}
    try:
        msgs = _mail_fetch(force=True)
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "n": len(msgs), "importantes": sum(1 for m in msgs if not m["masivo"])}


__all__ = [
    '_MAIL_LIST', '_MAIL_READ', '_MAIL_REPLY', '_mail_fetch', '_mail_ready', 'event_create', 'event_voice',
    'handle_gallery_add', 'handle_gallery_list', 'handle_gallery_remove', 'handle_mail_test', 'mail_cache', 'mail_read',
    'mail_reply', 'mail_voice', 'mcp_approval',
]
