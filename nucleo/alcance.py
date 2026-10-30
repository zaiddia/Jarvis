"""7.9: notas de voz por Telegram, avisos al WhatsApp, panel del celular instalable, imágenes para tus clases y
sincronización entre equipos.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import base64
import io
import os
import tempfile
import threading
import time
import urllib.request

import imagenes
import sincronizar
import whatsapp
from nucleo import J

# ============================================================================ NOTAS DE VOZ POR TELEGRAM


def _tg_file(file_id):
    info = J._tg_call("getFile", {"file_id": file_id}, timeout=20)
    url = f"{J.TELEGRAM_API}/file/bot{J.settings['telegram_token'].strip()}/{info['file_path']}"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = r.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise RuntimeError("la nota de voz es demasiado larga")
    return data


def transcribe_voice_note(data, mime="audio/ogg"):
    """Texto de una nota de voz (Gemini; si no, Whisper local). None si no se pudo."""
    cfg = J._gemini_for_stt()
    if cfg and not J.is_offline():
        payload = {"contents": [{"role": "user", "parts": [
            {"text": "Transcribe exactamente lo que dice esta nota de voz, en español de Colombia. Es una orden o pregunta "
                     "para un asistente. Devuelve SOLO la transcripción, sin comillas. Si no hay voz, devuelve: (nada)"},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}}]}],
            "generationConfig": {"temperature": 0}}

        def call(c):
            return J._gemini_text(J._post(f"{J.GEMINI_BASE}/models/{c['model']}:generateContent", J._gemini_headers(c),
                                          payload, J._GEMINI_OPTIONAL, timeout=30))
        try:
            out = (J._with_fallback(cfg, call) or "").strip().strip('"«»')
            return "" if out.lower().strip(" .") == "(nada)" else out
        except Exception as e:
            J.log_terminal(f"Nota de voz con Gemini: {getattr(e, 'why', e)}", "AVISO")
    try:
        from faster_whisper import WhisperModel
        if J._whisper_refiner["model"] is None:
            J._whisper_refiner.update(model=WhisperModel(J.settings["whisper_model"], device="cpu", compute_type="int8"),
                                      size=J.settings["whisper_model"])
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(data)
            path = f.name
        try:
            segs, _ = J._whisper_refiner["model"].transcribe(path, language="es", beam_size=1)
            return " ".join(s.text for s in segs).strip()
        finally:
            os.remove(path)
    except Exception:
        return None


def tg_voice(msg):
    """Una nota de voz desde Telegram: se transcribe, se atiende como texto y se responde (también con voz)."""
    v = msg.get("voice") or msg.get("audio")
    if not v:
        return False
    try:
        text = J.transcribe_voice_note(J._tg_file(v["file_id"]), v.get("mime_type") or "audio/ogg")
    except Exception as e:
        J.telegram_send(f"No pude descargar la nota de voz: {e}")
        return True
    if not text:
        J.telegram_send("No entendí la nota de voz. Para notas de voz necesito tu clave de Gemini (o Whisper instalado).")
        return True
    J.telegram_send(f"🎙 «{text}»")
    J.tg["last_cmd"] = time.time()
    J.push_chat("user", text, "telegram")
    out = J.telegram_run(text)
    if out:
        J.telegram_send(out)
        if J.settings["telegram_voice_reply"]:
            threading.Thread(target=J.tg_send_voice, args=(out,), daemon=True).start()
    return True


def tg_send_voice(text):
    try:
        path, delete = J._synthesize({"text": text[:900], "voice": None, "rate": None, "volume": None, "pitch": None,
                                      "backend": None if J.settings["tts_backend"] != "gemini" else "edge", "gemini": {},
                                      "gen": J.tts_gen["n"]})
    except Exception as e:
        J.log_terminal(f"Telegram, respuesta con voz: {e}", "AVISO")
        return False
    if not path:
        return False
    try:
        with open(path, "rb") as f:
            data = f.read()
        ext = os.path.splitext(path)[1].lower()
        J._tg_call("sendVoice" if ext in (".mp3", ".ogg", ".m4a") else "sendAudio",
                   {"chat_id": J.settings["telegram_chat"].strip()},
                   files={"voice" if ext in (".mp3", ".ogg", ".m4a") else "audio":
                          ("jarvis" + ext, data, "audio/mpeg" if ext == ".mp3" else "audio/ogg" if ext == ".ogg" else "audio/wav")},
                   timeout=60)
        return True
    except Exception as e:
        J.log_terminal(f"Telegram, respuesta con voz: {e}", "AVISO")
        return False
    finally:
        if delete:
            try:
                os.remove(path)
            except OSError:
                pass


# ============================================================================ AVISOS AL WHATSAPP
def whatsapp_ready():
    return whatsapp.valid_phone(J.settings["whatsapp_phone"]) and bool(J.settings["whatsapp_apikey"].strip())


def whatsapp_send(text):
    if not whatsapp_ready():
        return False
    try:
        with urllib.request.urlopen(whatsapp.url(J.settings["whatsapp_phone"], J.settings["whatsapp_apikey"], text),
                                    timeout=20) as r:
            body = r.read(2000).decode("utf-8", "replace").lower()
        return "error" not in body or "queued" in body or "sent" in body
    except Exception as e:
        J.log_terminal(f"WhatsApp: {e}", "AVISO")
        return False


def phone_send(text):
    """Al celular por el mejor canal disponible: Telegram y, si no, WhatsApp."""
    if J.telegram_ready():
        return J.telegram_send(text)
    if J.whatsapp_ready():
        return J.whatsapp_send(text)
    return False


def whatsapp_alert(text):
    if J.settings["whatsapp_alerts"] and J.whatsapp_ready():
        threading.Thread(target=J.whatsapp_send, args=("🔔 " + text,), daemon=True).start()


@J.socketio.on("whatsapp_test")
def handle_whatsapp_test(data=None):
    if not whatsapp_ready():
        return {"ok": False, "msg": "Pon tu número (con +57) y la clave de CallMeBot, y guarda."}
    ok = J.whatsapp_send("✅ Jarvis conectado: aquí te llegarán tus avisos.")
    return {"ok": ok, "msg": "Te envié un mensaje de prueba." if ok else "CallMeBot no aceptó el mensaje: revisa el número y la clave."}


# ============================================================================ PANEL DEL CELULAR INSTALABLE
_icon_cache = {}


@J.mobile_app.route("/manifest.json")
def mobile_manifest():
    J._mobile_ok()
    from flask import request
    k = request.args.get("k", "")
    return {"name": "Jarvis", "short_name": "Jarvis", "start_url": f"/?k={k}", "display": "standalone",
            "background_color": "#03060c", "theme_color": "#03060c", "orientation": "portrait",
            "icons": [{"src": f"/icono.png?k={k}", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}


@J.mobile_app.route("/icono.png")
def mobile_icon():
    J._mobile_ok()
    from flask import Response
    if "png" not in _icon_cache:
        try:
            from PIL import Image
            src = J.get_resource_path(os.path.join("static", "jarvis.ico"))
            im = Image.open(src)
            im.size = max(im.info.get("sizes", [im.size]))
            buf = io.BytesIO()
            im.convert("RGBA").resize((512, 512)).save(buf, "PNG")
            _icon_cache["png"] = buf.getvalue()
        except Exception:
            _icon_cache["png"] = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    return Response(_icon_cache["png"], mimetype="image/png")


# ============================================================================ IMÁGENES PARA TUS CLASES
_img_state = {"model": "", "checked": 0.0}


def image_model():
    cfg = J._gemini_for_stt()
    if not cfg:
        return ""
    if J.settings["image_model"].strip():
        return J.settings["image_model"].strip()
    if time.time() - _img_state["checked"] > 3600 or not _img_state["model"]:
        _img_state["checked"] = time.time()
        try:
            d = J._http("GET", f"{J.GEMINI_BASE}/models?pageSize=200", J._gemini_headers(cfg), timeout=10)
            _img_state["model"] = imagenes.pick_model([m.get("name", "") for m in d.get("models", [])])
        except Exception:
            pass
    return _img_state["model"]


def make_image(text, folder=None):
    """Genera la imagen y devuelve su ruta. Lanza RuntimeError con un mensaje claro."""
    cfg = J._gemini_for_stt()
    if not cfg:
        raise RuntimeError("para crear imágenes necesito tu clave de Gemini (Ajustes › IA)")
    model = J.image_model()
    if not model:
        raise RuntimeError("tu cuenta de Gemini no tiene un modelo de imágenes disponible")
    try:
        data = J._http("POST", f"{J.GEMINI_BASE}/models/{model}:generateContent", J._gemini_headers(cfg),
                       imagenes.body(text), timeout=120)
        raw, ext = imagenes.extract(data)
    except J.AIError as e:
        raise RuntimeError(e.why)
    except ValueError as e:
        raise RuntimeError(str(e))
    return imagenes.save(raw, ext, folder or os.path.join(J.settings["output_dir"], "Imágenes"), text[:60])


def image_voice(text, t):
    if not imagenes.is_image(t):
        return False
    what = imagenes.subject(text)
    remote = getattr(J._tl, "remote", False)              # se pierde al pasar a otro hilo
    if getattr(J._tl, "capture", None) is None:
        J.reply(f"Creo la imagen de {what}…", "IMAGEN")

    def work():
        try:
            path = J.make_image(what)
        except RuntimeError as e:
            J.notify(f"No pude crear la imagen: {e}.", "IMAGEN")
            return
        J.generated_files.add(path)
        opened = J._open_doc(path)
        J.notify("Listo, la imagen está en Documentos, carpeta Jarvis, Imágenes" + (" y la abrí." if opened else "."), "IMAGEN")
        if remote and J.telegram_ready():
            try:
                with open(path, "rb") as f:
                    J._tg_call("sendPhoto", {"chat_id": J.settings["telegram_chat"].strip()},
                               files={"photo": (os.path.basename(path), f.read(), "image/png")}, timeout=60)
            except Exception:
                pass
    if getattr(J._tl, "capture", None) is not None:
        work()
    else:
        threading.Thread(target=work, daemon=True, name="imagen").start()
    return True


# ============================================================================ VARIOS EQUIPOS (SINCRONIZACIÓN)
sync_state = {"last": 0.0, "msg": "", "error": ""}
_RELOAD = {"perfil.json": "perfil", "rutinas.json": "rutinas", "tareas.json": "tareas", "notas.json": "notas",
           "aula.json": "aula", "banco_preguntas.json": "banco", "notas_estudiantes.json": "seguimiento", "horario.json": "horario",
           "aprendizaje.json": "aprendizaje"}


def sync_now():
    folder = J.settings["sync_folder"].strip()
    if not folder:
        return "La sincronización está apagada."
    if not os.path.isdir(folder):
        sync_state["error"] = f"No encuentro la carpeta {folder}."
        return sync_state["error"]
    try:
        acts, changed = sincronizar.sync(J.CONFIG_DIR, folder)
    except OSError as e:
        sync_state["error"] = f"No pude sincronizar: {e}"
        return sync_state["error"]
    for k in changed:
        mod = _RELOAD.get(k) or ("habilidades" if k.startswith("habilidades/") else "")
        m = getattr(J, mod, None) if mod else None
        if m is not None and hasattr(m, "load"):
            try:
                m.load()
            except Exception:
                pass
    if any(k == "perfil.json" for k in changed):
        J._profile_changed()
    up = sum(1 for a, _ in acts if a == "subir")
    sync_state.update(last=time.time(), error="", msg=f"Subí {up} y traje {len(changed)} archivo(s)." if acts else "Todo al día.")
    if acts:
        J.log_terminal("Sincronización: " + sync_state["msg"], "SISTEMA")
    return sync_state["msg"]


def _sync_worker():
    while True:
        try:
            if J.settings["sync_folder"].strip():
                J.sync_now()
        except Exception as e:
            sync_state["error"] = str(e)
        time.sleep(180)


@J.socketio.on("sync_info")
def handle_sync_info(data=None):
    if (data or {}).get("now"):
        J.sync_now()
    return {"folder": J.settings["sync_folder"], "msg": sync_state["msg"], "error": sync_state["error"],
            "last": sync_state["last"]}


def reach_start():
    threading.Thread(target=J._sync_worker, daemon=True).start()


__all__ = [
    '_RELOAD', '_icon_cache', '_img_state', '_sync_worker', '_tg_file', 'handle_sync_info', 'handle_whatsapp_test',
    'image_model', 'image_voice', 'make_image', 'mobile_icon', 'mobile_manifest', 'phone_send', 'reach_start',
    'sync_now', 'sync_state', 'tg_send_voice', 'tg_voice', 'transcribe_voice_note', 'whatsapp_alert', 'whatsapp_ready',
    'whatsapp_send',
]
