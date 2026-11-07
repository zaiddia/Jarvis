"""Telegram recibe fotos y archivos (12.16).

Desde el celular le mandas a tu bot la foto de un recibo, un PDF o la foto de un taller. Si el mensaje trae una palabra
(«recibo», «audio», «revisa», «resume», «texto»), Jarvis lo hace de una vez; si no, te pregunta qué hacer.
Solo obedece a tu chat (como siempre) y solo lee el archivo que le mandaste.
"""
import re
import time

import adjuntos
from nucleo import J

tgf = {"pending": None, "t": 0.0}
TG_ACTIONS = {"recibo": r"recibo|factura|gasto|tiquete", "audio": r"audio|escuchar|mp3|leelo|leemelo", "revisar": r"revisa|revisar|califica|corrige|taller",
              "resumir": r"resume|resumen|resumir|de que trata", "texto": r"texto|transcribe|saca el texto|ocr"}


def tg_action_of(text):
    t = J.normalize(text or "")
    for a, rx in TG_ACTIONS.items():
        if re.search(rf"\b(?:{rx})", t):
            return a
    return ""


def tg_file_in(msg):
    """Una foto o un documento desde Telegram. → True si era un archivo."""
    photo, doc = msg.get("photo"), msg.get("document")
    if not photo and not doc:
        return False
    if photo:
        f = max(photo, key=lambda p: p.get("file_size") or p.get("width", 0))
        name = f"foto_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
    else:
        f, name = doc, doc.get("file_name") or "archivo"
    if (f.get("file_size") or 0) > 19_000_000:
        J.telegram_send("Ese archivo es muy grande (Telegram deja bajar hasta 20 MB).")
        return True
    try:
        it = adjuntos.add(name, J._tg_file(f["file_id"]))
    except (ValueError, OSError) as e:
        J.telegram_send(f"No pude recibir «{name}»: {e}")
        return True
    except Exception as e:
        J.telegram_send(f"No pude descargar el archivo: {e}")
        return True
    J.tg["last_cmd"] = time.time()
    J.log_terminal(f"Desde el celular: archivo «{it['nombre']}»", "TELEGRAM")
    action = tg_action_of(msg.get("caption") or "")
    if not action:
        tgf.update(pending=it["id"], t=time.time())
        opts = ["recibo", "texto", "resumir"] if it["tipo"] == "imagen" else ["audio", "resumir", "texto"]
        if it["tipo"] in ("imagen", "pdf"):
            opts += ["revisar"]
        J.telegram_send(f"Recibí «{it['nombre']}». ¿Qué hago? Responde: " + " · ".join(dict.fromkeys(opts)) + ".")
        return True
    tg_run_action(it, action)
    return True


def tg_run_action(it, action):
    J.telegram_send({"recibo": "Leyendo el recibo…", "audio": "Convirtiendo en audio…", "revisar": "Revisando el trabajo…",
                     "resumir": "Leyendo…", "texto": "Sacando el texto…"}[action])

    def work():
        try:
            if action == "recibo":
                J.telegram_send(J.receipt_from(it))
            elif action == "audio":
                J.audio_from_item(it)                    # avisa al terminar (y por Telegram, porque la orden vino de ahí)
            else:
                J.attach_run([it], action)
        except ValueError as e:
            J.telegram_send(f"No pude: {e}")
        except J.AIError as e:
            J.telegram_send(J.ai_error_reply(e))
    J.start_job("Archivo desde el celular", work, "telegram-archivo")


def tg_pending_answer(text):
    """«recibo», «audio»… como respuesta a «¿Qué hago con…?» (hasta 15 minutos después). → True si la atendió."""
    if not tgf["pending"] or time.time() - tgf["t"] > 900:
        return False
    action = tg_action_of(text)
    if not action or len(J.normalize(text).split()) > 4:
        return False
    it = adjuntos.get(tgf["pending"])
    tgf["pending"] = None
    if not it:
        J.telegram_send("Ese archivo ya no está; mándamelo otra vez.")
        return True
    tg_run_action(it, action)
    return True


__all__ = ['TG_ACTIONS', 'tg_action_of', 'tg_file_in', 'tg_pending_answer', 'tg_run_action', 'tgf']
