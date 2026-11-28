"""12.74: los generadores de imágenes nuevos. Lógica pura (sin red ni archivos de Jarvis).

  · Integrado en tu PC: stable-diffusion.cpp («sd-cli», el hermano de llama.cpp) con SD-Turbo (2 GB): una imagen en
    1 paso, sin internet y sin que la foto salga del equipo. Calidad sencilla; sirve de respaldo y para lo privado.
  · FLUX.1-schnell en NVIDIA Build, con la misma clave de NVIDIA de la IA (gratis mientras dure su prueba).
  · El orden automático: quién sirve para cada pedido (con letras, foto tuya, sin internet…) y quién falló hace poco.
"""
import base64
import os
import re
import time

RELEASES_API = "https://api.github.com/repos/leejet/stable-diffusion.cpp/releases?per_page=10"
MODEL_REPO = "Green-Sky/SD-Turbo-GGUF"
MODEL_FILE = "sd_turbo-f16-q8_0.gguf"
MODEL_SHA = "d50be7655f0a554cf8041c145d88b210bd5f3c545423119dee62ae08cae51580"
MODEL_GB = 2.0
MODEL_LICENSE = "Stability AI Community License (gratis para uso personal y educativo)"

NV_URL = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-schnell"
NV_SIZES = {"1:1": (1024, 1024), "16:9": (1344, 768), "3:4": (896, 1152)}
LOCAL_SIZES = {"1:1": (512, 512), "16:9": (704, 384), "3:4": (448, 576)}

NAMES = {"gemini": "Gemini", "chatgpt": "ChatGPT", "sensenova": "SenseNova", "nvidia": "FLUX (NVIDIA)",
         "local": "el generador de tu PC"}
# Cuánto se deja descansar a uno que falló, para no esperar por él en cada imagen (segundos)
COOL = {"quota": 20 * 60, "server": 5 * 60, "net": 2 * 60, "balance": 6 * 3600, "key": 6 * 3600, "perm": 6 * 3600,
        "region": 24 * 3600, "model": 30 * 60, "bad": 10 * 60}

_TEXTY = re.compile(r"\b(?:que diga|que digan|con (?:el|la|los|las)? ?(?:texto|titulo|letrero|nombre|palabras?|frase)|letrero|cartel|afiche|"
                    r"poster|infografia|diagrama|mapa conceptual|etiquetas?|rotulad[oa]|tarjeta|invitacion|diploma|certificado|"
                    r"portada|logo|titulo)\b", re.I)


# ============================================================================ EL MOTOR (stable-diffusion.cpp)
def asset_suffix(is_win=True, gpu=False):
    """Vulkan sirve para casi cualquier tarjeta, también la integrada de Intel; si no arranca, la de procesador."""
    if is_win:
        return "bin-win-vulkan-x64.zip" if gpu else "bin-win-cpu-x64.zip"
    return "x86_64-vulkan.zip" if gpu else "x86_64.zip"


def pick_release(releases, is_win=True, gpu=False):
    """(url, nombre, versión) del motor más nuevo con el archivo para este sistema."""
    suf = asset_suffix(is_win, gpu)
    for rel in releases or []:
        for a in rel.get("assets") or []:
            name = str(a.get("name", ""))
            if name.endswith(suf) and name.startswith("sd-") and "rocm" not in name and str(a.get("browser_download_url", "")).startswith("https://"):
                return a["browser_download_url"], name, rel.get("tag_name", "")
    return None


def find_cli(folder, is_win=True):
    """La ruta de sd-cli (o del sd de las versiones viejas) dentro de lo descomprimido, o ""."""
    want = ("sd-cli.exe", "sd.exe") if is_win else ("sd-cli", "sd")
    found = {}
    for root, _dirs, files in os.walk(folder or ""):
        for f in files:
            if f.lower() in want and f.lower() not in found:
                found[f.lower()] = os.path.join(root, f)
    for w in want:
        if w in found:
            return found[w]
    return ""


def cli_args(exe, model, prompt, out, aspect="", seed=-1, threads=0, init="", strength=0.55):
    """La orden para sd-cli. SD-Turbo: 1 paso y sin CFG (escala 1); para editar una foto, 2 pasos sobre ella."""
    w, h = LOCAL_SIZES.get(aspect, LOCAL_SIZES["1:1"])
    args = [exe, "-m", model, "-p", prompt, "-o", out, "-W", str(w), "-H", str(h),
            "--steps", "2" if init else "1", "--cfg-scale", "1", "--sampling-method", "euler", "--seed", str(int(seed))]
    if threads:
        args += ["-t", str(int(threads))]
    if init:
        args += ["-i", init, "--strength", f"{float(strength):.2f}"]
    return args


# ============================================================================ FLUX EN NVIDIA
def nv_payload(prompt, aspect="", seed=0, steps=4):
    w, h = NV_SIZES.get(aspect, NV_SIZES["1:1"])
    return {"prompt": str(prompt)[:1500], "width": w, "height": h, "steps": int(steps), "seed": int(seed)}


def nv_extract(data):
    """(bytes, ".jpg"|".png") de la respuesta de NVIDIA (artifacts[].base64; también acepta el formato de OpenAI)."""
    d = data if isinstance(data, dict) else {}
    b64 = ""
    arts = d.get("artifacts") or []
    if arts and isinstance(arts[0], dict):
        if str(arts[0].get("finishReason", "SUCCESS")).upper() not in ("SUCCESS", ""):
            raise ValueError("NVIDIA no entregó la imagen (su filtro de contenido la bloqueó)")
        b64 = arts[0].get("base64") or ""
    elif d.get("data") and isinstance(d["data"][0], dict):
        b64 = d["data"][0].get("b64_json") or ""
    elif d.get("image"):
        b64 = str(d["image"])
    if not b64:
        raise ValueError("NVIDIA no devolvió la imagen")
    b64 = re.sub(r"^data:image/\w+;base64,", "", b64)
    raw = base64.b64decode(b64)
    if len(raw) < 50:
        raise ValueError("la imagen llegó vacía")
    return raw, (".png" if raw[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg")


# ============================================================================ QUIÉN LA HACE
def texty(tema):
    """¿El pedido lleva letras (cartel, título, etiquetas…)? Ahí escriben mejor Gemini y ChatGPT."""
    return bool(_TEXTY.search(str(tema or "")))


def order(available, chosen="auto", ai_provider="", tema="", own_photo=False, offline=False, private=False, cool=None, now=None):
    """El orden en que se intenta: [nombres]. available: los que tienen clave o están instalados.
    · chosen distinto de "auto": ese primero (si está) y los demás detrás para no quedarse parado.
    · Sin internet o en modo privado con una foto tuya: solo el del PC.
    · Una foto tuya nunca va a SenseNova (China) en automático.
    · Los que fallaron hace poco van al final (cool = {nombre: hasta}), para no esperar por ellos."""
    now = time.time() if now is None else now
    av = [a for a in available]
    if offline or (private and own_photo):
        return ["local"] if "local" in av else []
    if own_photo and chosen != "sensenova":
        av = [a for a in av if a != "sensenova"]
    if texty(tema):
        base = ["chatgpt", "gemini", "nvidia", "sensenova", "local"] if ai_provider == "chatgpt" else ["gemini", "chatgpt", "nvidia", "sensenova", "local"]
    elif own_photo:
        base = ["gemini", "chatgpt", "sensenova", "local", "nvidia"]          # editar una foto: los que la entienden
    else:
        base = (["chatgpt", "gemini"] if ai_provider == "chatgpt" else ["gemini", "chatgpt"]) + ["nvidia", "sensenova", "local"]
    if own_photo:
        base = [b for b in base if b != "nvidia"]                             # FLUX schnell no edita fotos
    seq = [b for b in base if b in av]
    if chosen and chosen != "auto" and chosen in av:
        seq = [chosen] + [b for b in seq if b != chosen]
    cool = cool or {}
    fresh = [b for b in seq if cool.get(b, 0) <= now]
    rested = [b for b in seq if cool.get(b, 0) > now]
    if chosen and chosen != "auto" and chosen in fresh:
        fresh = [chosen] + [b for b in fresh if b != chosen]
    return fresh + rested


def cool_until(kind, now=None):
    return (time.time() if now is None else now) + COOL.get(kind, 60)


def english_prompt_rule():
    return ("Rewrite the request as ONE short English prompt (max 60 words) for an image model: subject, setting, style, "
            "colors, composition. Keep any text to show in the image exactly as written, inside quotes. "
            "Reply only with the prompt.")


__all__ = ["RELEASES_API", "MODEL_REPO", "MODEL_FILE", "MODEL_SHA", "MODEL_GB", "MODEL_LICENSE", "NV_URL", "NV_SIZES", "LOCAL_SIZES",
           "NAMES", "COOL", "asset_suffix", "pick_release", "find_cli", "cli_args", "nv_payload", "nv_extract", "texty", "order",
           "cool_until", "english_prompt_rule"]
