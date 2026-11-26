"""12.63: videos cortos con IA, gratis, con NVIDIA Cosmos3 Nano (la misma clave de NVIDIA de la sección IA).

  · «hazme un video de 5 segundos de un volcán en erupción» · «un clip con IA de un colibrí volando» · «video realista de…»
  · «anima esta imagen» / «convierte la imagen en video»: la última imagen creada en el estudio o la foto que subiste.
  · Texto a video e imagen a video, 480p a 24 cuadros por segundo, de 1 a 10 segundos. Queda en Documentos › Jarvis ›
    Videos › IA. NVIDIA le pone su marca de agua invisible (SynthID) y revisa el contenido.

Los videos explicativos animados (los de «hazme un video de 2 minutos que explique…») siguen siendo de videomate.
Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import base64
import datetime
import json
import os
import re
import time
import urllib.error
import urllib.request
import webbrowser

import imagenes
from nucleo import J

VI63_URL = "https://ai.api.nvidia.com/v1/cosmos/nvidia/cosmos3-nano"
VI63_STATUS = "https://api.nvcf.nvidia.com/v2/nvcf/pexec/status/"
VI63_FPS = 24
VI63_RES = {"16:9": "480_16_9", "1:1": "480_1_1", "3:4": "480_3_4", "9:16": "480_9_16"}
vi63_job = {"busy": False, "tema": ""}
VI63_PLAYGROUND = "https://build.nvidia.com/nvidia/cosmos3-nano"
VI63_NO_ACCESS = ("NVIDIA todavía no le da acceso por programa a ese modelo de video a tu cuenta (responde «404 page not "
                  "found»; es una falla de NVIDIA que les pasa a muchas cuentas personales: les falta el permiso «Public API "
                  "Endpoints»). Tu clave sí sirve para Kimi. Mientras NVIDIA lo arregla, puedes crear el video en su página "
                  f"({VI63_PLAYGROUND}), que en el navegador sí funciona, y si es para una película, descargarlo a la carpeta «clips» "
                  "del proyecto y decirme «arma la película». Te abro la página")

_VI63_NUM = {"un": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}


def vi63_frames(seconds):
    """Cuadros para esa duración (a 24 por segundo, entre 25 y 241: hasta 10 s en 480p)."""
    return max(25, min(241, int(round(float(seconds) * VI63_FPS)) + 1))


def vi63_body(prompt, seconds=5, aspect="16:9", image_b64="", seed=None):
    body = {"model_mode": "image2video" if image_b64 else "text2video", "prompt": prompt,
            "resolution": VI63_RES.get(aspect, "480_16_9"), "num_frames": vi63_frames(seconds), "fps": VI63_FPS,
            "num_inference_steps": 35}
    if image_b64:
        body["input_reference"] = "data:image/png;base64," + image_b64
    if seed is not None:
        body["seed"] = int(seed)
    return body


def vi63_extract(data):
    b = (data or {}).get("b64_video") if isinstance(data, dict) else None
    if not b:
        raise ValueError("NVIDIA no devolvió el video")
    raw = base64.b64decode(b, validate=True)
    if len(raw) < 100:
        raise ValueError("el video llegó vacío")
    return raw


# ============================================================================ LA PETICIÓN (con espera si NVIDIA la encola)
def _vi63_request(url, key, body=None, timeout=600):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 method="POST" if body is not None else "GET",
                                 headers={"Authorization": f"Bearer {key}", "Accept": "application/json",
                                          "Content-Type": "application/json", "User-Agent": f"Jarvis/{J.VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        if e.code == 404 and "page not found" in raw.lower():           # 12.64: falla conocida de NVIDIA
            raise RuntimeError(VI63_NO_ACCESS)
        if e.code == 422:
            raise RuntimeError("NVIDIA no aceptó el pedido (puede que lo haya bloqueado su filtro de contenido): "
                               + raw[:200])
        kind, why, msg = J._classify(e.code, raw)
        raise J.AIError(f"{why}. (HTTP {e.code}: {msg})", code=e.code, raw=raw[:800], kind=kind, why=why)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise J.AIError(f"Sin conexión: {e}", code=0, kind="net", why="no hay conexión con NVIDIA. Revisa tu internet")


def vi63_call(key, body, wait=900, sleep=time.sleep, request=None):
    """Pide el video. Si NVIDIA responde 202 (en cola), pregunta por él hasta que esté. → bytes del MP4."""
    request = request or J._vi63_request
    status, headers, raw = request(VI63_URL, key, body)
    t0 = time.time()
    while status == 202:
        reqid = headers.get("NVCF-REQID") or headers.get("nvcf-reqid")
        if not reqid:
            raise ValueError("NVIDIA dejó el video en cola sin decir cómo recogerlo")
        if time.time() - t0 > wait:
            raise ValueError("NVIDIA tardó demasiado en hacer el video; inténtalo más tarde")
        sleep(5)
        status, headers, raw = request(VI63_STATUS + reqid, key, None)
    return vi63_extract(json.loads(raw.decode("utf-8", "replace") or "{}"))


# ============================================================================ CREAR
def _vi63_key():
    return (J._ai_cfg({"ai_provider": "nvidia"}).get("key") or "").strip()


def vi63_prompt(tema):
    """El pedido en español → una descripción en inglés para el modelo de video (si la IA no está, va tal cual)."""
    try:
        out = J.ai_chat([{"role": "system", "content": "Write ONE English prompt (max 70 words) for a text-to-video model: "
                                                       "subject, action, setting, camera movement, lighting, realistic style. "
                                                       "No text or letters in the scene. Reply only with the prompt."},
                         {"role": "user", "content": tema}], max_tokens=200)
        out = re.sub(r"\s+", " ", str(out or "")).strip().strip('"')
        return out[:600] or tema
    except Exception:
        return tema


def vi63_make(tema, seconds=5, aspect="16:9", image_path="", folder=None):
    """Crea el video y devuelve la ruta del MP4. Lanza RuntimeError con un mensaje claro."""
    key = J._vi63_key()
    if not key:
        raise RuntimeError("para crear videos con IA gratis necesito la clave de NVIDIA (Ajustes › Inteligencia artificial "
                           "› NVIDIA; se saca gratis en build.nvidia.com)")
    b64 = base64.b64encode(J._png_bytes(image_path, 1280)).decode() if image_path else ""
    body = vi63_body(J.vi63_prompt(tema or "gentle camera movement, natural motion"), seconds, aspect, b64)
    try:
        raw = J.vi63_call(key, body)
    except J.AIError as e:
        raise RuntimeError(e.why or str(e))
    except ValueError as e:
        raise RuntimeError(str(e))
    folder = folder or os.path.join(J.settings["output_dir"], "Videos", "IA")
    os.makedirs(folder, exist_ok=True)
    name = re.sub(r"[^\w\- ]+", "", (tema or "imagen animada"))[:50].strip() or "video"
    path = os.path.join(folder, f"{name} {datetime.datetime.now():%Y%m%d-%H%M%S}.mp4")
    with open(path, "wb") as f:
        f.write(raw)
    return path


def _vi63_job(tema, seconds, aspect, image_path):
    try:
        path = J.vi63_make(tema, seconds, aspect, image_path)
    except RuntimeError as e:
        J.reply(f"No pude crear el video: {e}.", "VIDEO IA")
        if str(e) == VI63_NO_ACCESS:
            webbrowser.open(VI63_PLAYGROUND)
        return
    finally:
        vi63_job.update(busy=False, tema="")
    J.reply(f"¡Listo! Tu video de {seconds:g} segundos quedó en Documentos, Jarvis, Videos, IA. Te lo abro.", "VIDEO IA")
    J._open_doc(path)


# ============================================================================ POR VOZ
_VI63_SECS = r"(\d{1,2}|un|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+segundos?"
_VI63_TEXT = re.compile(
    rf"^(?:jarvis\s+)?(?:haz|hazme|crea|creame|genera|generame|arma|armame)\s+(?:un|una)\s+(?:video|videito|clip)"
    rf"(?:\s+(?:corto|cortico|realista|con (?:ia|inteligencia artificial)))*"
    rf"(?:\s+de\s+{_VI63_SECS})?(?:\s+(?:corto|realista|con (?:ia|inteligencia artificial)))*"
    rf"\s+(?:de|sobre|con|donde (?:se vea|salga|aparezca))\s+(.{{3,300}})$")
_VI63_SIGNAL = re.compile(r"\bsegundos?\b|\bclip\b|\brealista\b|\bcon (?:ia|inteligencia artificial)\b")
_VI63_ANIM = re.compile(r"^(?:jarvis\s+)?(?:anima|animame|dale (?:vida|movimiento) a|convierte(?:me)?|vuelve|pasa)\s+(?:esta|esa|la|mi)\s+"
                        r"(?:imagen|foto|ilustracion|dibujo)(?:\s+(?:en|a)\s+(?:un\s+)?video)?(?:\s+de\s+" + _VI63_SECS + r")?"
                        r"(?:\s*[,:]?\s*(?:que|donde|con|y)\s+(.{3,200}))?$")


def _vi63_orig(text, norm_tail):
    """El mismo final de la frase, pero como lo escribiste (con tildes)."""
    raw = re.sub(r"[\s.!?¡¿]+$", "", str(text or ""))
    tail = raw[-len(norm_tail):] if norm_tail and len(raw) >= len(norm_tail) else ""
    return tail if tail and J.skills.normalize(tail) == norm_tail else norm_tail


def _vi63_secs(word):
    if not word:
        return 5
    return float(_VI63_NUM.get(word, word)) if (word in _VI63_NUM or word.isdigit()) else 5


def videoia63_voice(text, t):
    m = _VI63_TEXT.match(t)
    if m and _VI63_SIGNAL.search(t):
        seconds, tema, image = _vi63_secs(m.group(1)), _vi63_orig(text, m.group(2)), ""
    else:
        m = _VI63_ANIM.match(t)
        if not m:
            return False
        src = J._studio_source()
        if not src:
            J.reply("¿Cuál imagen animo? Créala primero («hazme una ilustración de…») o súbela al chat.", "VIDEO IA")
            return True
        seconds, tema, image = _vi63_secs(m.group(1)), (_vi63_orig(text, m.group(2)) if m.group(2) else src.get("tema") or ""), src["path"]
    seconds = max(1, min(10, seconds))
    if vi63_job["busy"]:
        J.reply(f"Ya estoy haciendo el video de «{vi63_job['tema']}». Te aviso al terminar.", "VIDEO IA")
        return True
    if not J._vi63_key():
        J.reply("Para crear videos con IA gratis uso NVIDIA: pon tu clave de NVIDIA en Ajustes, sección Inteligencia "
                "artificial (se saca gratis en build.nvidia.com).", "VIDEO IA")
        return True
    aspect = imagenes.detect_aspect(text) or "16:9"
    aspect = "9:16" if aspect == "3:4" else aspect
    vi63_job.update(busy=True, tema=tema[:60] or "la imagen")
    J.reply(f"Hago un video de {seconds:g} segundos" + (" animando la imagen" if image else f" de «{tema[:60]}»") +
            " con la IA gratis de NVIDIA. Tarda unos minutos; te aviso al terminar.", "VIDEO IA")
    J.start_job("Creando el video con IA", lambda: J._vi63_job(tema, seconds, aspect, image), "video_ia")
    return True


__all__ = ['VI63_NO_ACCESS', 'VI63_PLAYGROUND', 'VI63_FPS', 'VI63_RES', 'VI63_STATUS', 'VI63_URL', '_VI63_ANIM', '_VI63_NUM', '_VI63_SECS', '_VI63_SIGNAL', '_VI63_TEXT',
           '_vi63_job', '_vi63_key', '_vi63_orig', '_vi63_request', '_vi63_secs', 'vi63_body', 'vi63_call', 'vi63_extract', 'vi63_frames',
           'vi63_job', 'vi63_make', 'vi63_prompt', 'videoia63_voice']
