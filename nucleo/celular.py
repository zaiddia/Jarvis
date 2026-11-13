"""Telegram recibe fotos y archivos (12.16).

Desde el celular le mandas a tu bot la foto de un recibo, un PDF o la foto de un taller. Si el mensaje trae una palabra
(«recibo», «audio», «revisa», «resume», «texto»), Jarvis lo hace de una vez; si no, te pregunta qué hacer.
Solo obedece a tu chat (como siempre) y solo lee el archivo que le mandaste.
"""
import os
import re
import tempfile
import time

import adjuntos
from nucleo import J

tgf = {"pending": None, "t": 0.0}
TG_MEDIA_ACTIONS = {"subtitulos": r"subtitul|srt", "acta": r"acta|minuta|acuerdos|compromisos|resume|resumen|resumir|de que (?:trata|hablan)|que dice",
                    "transcribir": r"transcrib|texto|pasalo a texto|escrib"}
TG_ACTIONS = {"recibo": r"recibo|factura|gasto|tiquete", "audio": r"audio|escuchar|mp3|leelo|leemelo", "revisar": r"revisa|revisar|califica|corrige|taller",
              "resumir": r"resume|resumen|resumir|de que trata", "texto": r"texto|transcribe|saca el texto|ocr"}


def tg_action_of(text):
    t = J.normalize(text or "")
    for a, rx in TG_ACTIONS.items():
        if re.search(rf"\b(?:{rx})", t):
            return a
    return ""


def tg_media_action_of(text):
    t = J.normalize(text or "")
    for a, rx in TG_MEDIA_ACTIONS.items():
        if re.search(rf"\b(?:{rx})", t):
            return a
    return ""


def tg_is_material(msg):
    """12.25: ¿este audio o video es para TRANSCRIBIR (y no una orden hablada)? Sí cuando es un video, cuando viene
    reenviado de otro chat, cuando dura más de un minuto y medio, o cuando el mensaje dice qué hacer («acta»,
    «transcribe», «subtítulos»). Una nota de voz corta tuya, sin texto, sigue siendo una orden."""
    if msg.get("video") or "video_note" in msg or msg.get("_material"):
        return True
    v = msg.get("voice") or msg.get("audio")
    if not v:
        return False
    if msg.get("forward_origin") or msg.get("forward_date") or msg.get("forward_from") or msg.get("forward_sender_name"):
        return True
    if tg_media_action_of(msg.get("caption") or ""):
        return True
    return (v.get("duration") or 0) > 90


def tg_media_in(msg):
    """Un audio, nota de voz o video para pasar a texto. → True si lo atendió."""
    if not tg_is_material(msg):
        return False
    kind = next(k for k in ("video", "video_note", "voice", "audio") if k in msg)
    f = msg[kind]
    ext = {"video": ".mp4", "video_note": ".mp4", "voice": ".ogg", "audio": ".mp3"}[kind]
    name = f.get("file_name") or f"{'video' if kind.startswith('video') else 'audio'}_{time.strftime('%Y%m%d_%H%M%S')}{ext}"
    if adjuntos.kind_of(name) not in adjuntos.MEDIA:
        name = os.path.splitext(name)[0] + ext
    if (f.get("file_size") or 0) > 19_500_000:
        J.telegram_send("Ese archivo pesa más de 20 MB y Telegram no deja que un bot lo baje. Súbelo en el computador con el clip del HUD "
                        "(ahí acepta hasta 300 MB).")
        return True
    try:
        fd, tmp = tempfile.mkstemp(prefix="tg_", suffix=".part", dir=adjuntos._dir)
        with os.fdopen(fd, "wb") as out:
            out.write(J._tg_file(f["file_id"]))
        it = adjuntos.add_path(name, tmp)
    except (ValueError, OSError) as e:
        J.telegram_send(f"No pude recibir el archivo: {e}")
        return True
    except Exception as e:
        J.telegram_send(f"No pude descargar el archivo: {e}")
        return True
    J.tg["last_cmd"] = time.time()
    J._batch["ids"] = [it["id"]]
    J.log_terminal(f"Desde el celular: {adjuntos.describe(it)}", "TELEGRAM")
    largo = (f.get("duration") or 0) > 180 or (not f.get("duration") and (f.get("file_size") or 0) > 3_000_000)
    action = tg_media_action_of(msg.get("caption") or "") or ("acta" if largo else "transcribir")       # corto: el texto; largo: el acta
    tg_media_run(it, action)
    return True


def tg_send_document(path):
    with open(path, "rb") as fh:
        J._tg_call("sendDocument", {"chat_id": J.settings["telegram_chat"].strip()},
                   files={"document": (os.path.basename(path), fh.read(), "application/octet-stream")}, timeout=120)


def tg_media_run(it, action):
    J.telegram_send({"acta": "Transcribo y saco el resumen y los acuerdos…", "transcribir": "Transcribiendo…",
                     "subtitulos": "Haciendo los subtítulos…"}[action] + " Puede tardar unos minutos; te aviso aquí."
                    + ("" if action != "transcribir" else " (Responde «acta» o «subtítulos» si prefieres eso.)"))
    tgf.update(pending=it["id"], t=time.time())           # para poder pedir después «acta» o «subtítulos» del mismo archivo

    def work():
        J.tg["last_cmd"] = time.time()                     # el aviso final también llega al celular
        dst = J.attach_run([it], action)                   # avisa al terminar (y dice el error si lo hubo)
        if not dst:
            return
        last = J.tr_last
        try:
            if action == "transcribir" and last.get("text") and len(last["text"]) <= 3500:
                J.telegram_send("📝 " + last["text"])       # en el celular sirve más el texto que un archivo
            else:
                J.tg_send_document(dst)
        except Exception as e:
            J.log_terminal(f"Telegram: no pude mandar el resultado ({e}).", "AVISO")
    J.start_job("Audio desde el celular", work, "telegram-audio")


def tg_file_in(msg):
    """Una foto o un documento desde Telegram. → True si era un archivo."""
    photo, doc = msg.get("photo"), msg.get("document")
    if not photo and not doc:
        return False
    if doc and adjuntos.kind_of(doc.get("file_name") or "") in adjuntos.MEDIA:        # 12.25: un audio o video mandado «como archivo»
        return tg_media_in({"audio": doc, "caption": msg.get("caption") or "", "_material": True})
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
    action = tg_action_of(text) or tg_media_action_of(text)
    if not action or len(J.normalize(text).split()) > 4:
        return False
    it = adjuntos.get(tgf["pending"])
    tgf["pending"] = None
    if not it:
        J.telegram_send("Ese archivo ya no está; mándamelo otra vez.")
        return True
    if it["tipo"] in adjuntos.MEDIA:
        tg_media_run(it, tg_media_action_of(text) or "acta")
        return True
    tg_run_action(it, action)
    return True


__all__ = ['TG_MEDIA_ACTIONS', 'tg_is_material', 'tg_media_action_of', 'tg_media_in', 'tg_media_run', 'tg_send_document', 'TG_ACTIONS', 'tg_action_of', 'tg_file_in', 'tg_pending_answer', 'tg_run_action', 'tgf']
