"""Imágenes para tus clases (7.9): «hazme una ilustración del ciclo del agua para quinto».

Usa un modelo de imágenes de Gemini (con tu clave). Jarvis elige el modelo solo (el que tu cuenta tenga) o el que
pongas en Ajustes, y guarda la imagen en Documentos\\Jarvis\\Imágenes.
"""
import base64
import datetime
import os
import re

PREFER = [r"flash.*image", r"image.*flash", r"imagen-\d", r"image"]


def pick_model(names, wanted=""):
    """El modelo de imágenes a usar entre los que tiene la cuenta."""
    if wanted:
        return wanted
    cands = [n.split("/")[-1] for n in names if "image" in n.lower() and "embed" not in n.lower()]
    for rx in PREFER:
        for c in cands:
            if re.search(rx, c, re.I) and "imagen-" not in c:
                return c
    return cands[0] if cands else ""


def prompt(text):
    return ("Crea una imagen clara y atractiva para usar en una clase de colegio en Colombia. " + text.strip() +
            ". Estilo de ilustración educativa, colores agradables, sin marcas de agua. Si lleva textos o etiquetas, "
            "que estén en español, sean pocos, grandes y sin errores de ortografía.")


def body(text):
    return {"contents": [{"role": "user", "parts": [{"text": prompt(text)}]}],
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}}


def extract(data):
    """(bytes, extensión) de la primera imagen de la respuesta. Lanza ValueError si no hay."""
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        raise ValueError("el modelo no devolvió ninguna imagen")
    for p in parts:
        inline = p.get("inlineData") or p.get("inline_data")
        if inline and inline.get("data"):
            mime = inline.get("mimeType") or inline.get("mime_type") or "image/png"
            return base64.b64decode(inline["data"]), (".jpg" if "jpeg" in mime else ".png")
    raise ValueError("el modelo respondió sin imagen (prueba a describirla de otra forma)")


def save(raw, ext, folder, title):
    os.makedirs(folder, exist_ok=True)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", title).strip()[:60] or "imagen"
    path = os.path.join(folder, f"{name} {datetime.datetime.now():%Y-%m-%d %H%M%S}{ext}")
    with open(path, "wb") as f:
        f.write(raw)
    return path


_TRIGGER = re.compile(r"\b(?:haz|hazme|crea|creame|genera|generame|dibuja|dibujame|disena|disename)\s+(?:una?|el|la)?\s*"
                      r"(?:imagen|ilustracion|dibujo|infografia|afiche|cartel|poster|portada)\b")


def is_image(t):
    return bool(_TRIGGER.search(t))


def subject(text):
    s = re.sub(r"^.*?\b(?:imagen|ilustraci[oó]n|dibujo|infograf[ií]a|afiche|cartel|p[oó]ster|portada)\b\s*(?:del|de|sobre|con|para)?\s*",
               "", text.strip(), flags=re.I)
    return s.strip(" .,:") or text.strip()
