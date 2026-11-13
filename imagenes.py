"""Imágenes para tus clases (7.9; estudio de imágenes 11.7): «hazme una ilustración del ciclo del agua para quinto»,
«tres opciones de un afiche del día del idioma en acuarela», «dibujo para colorear de un triángulo rectángulo».

Usa el modelo de imágenes de Gemini o de ChatGPT (con tu clave). Jarvis elige el modelo solo (el que tu cuenta tenga)
o el que pongas en Ajustes, y guarda la imagen en Documentos\\Jarvis\\Imágenes. Con 11.7 también: estilos, formato
(horizontal para proyectar, vertical para afiches), varias opciones, editar una imagen («cámbiale el fondo») y la hoja
tamaño carta para imprimir. Lógica pura.
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


def model_candidates(names):
    """Todos los modelos de imágenes de la cuenta, del preferido al último (para probar otro si uno está saturado)."""
    out, left = [], list(names)
    while True:
        m = pick_model(left)
        if not m or m in out:
            break
        out.append(m)
        left = [n for n in left if n.split("/")[-1] != m]
    return out


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
    k = 2
    while os.path.exists(path):                        # varias en el mismo segundo (11.7: varias opciones)
        path = os.path.join(folder, f"{name} {datetime.datetime.now():%Y-%m-%d %H%M%S} ({k}){ext}")
        k += 1
    with open(path, "wb") as f:
        f.write(raw)
    return path


_NOUN = r"(?:imagen(?:es)?|ilustracion(?:es)?|dibujos?|infografias?|afiches?|carteles|cartel|posters?|portadas?|caricaturas?|logos?|mascotas?|personajes?)"
_TRIGGER = re.compile(r"\b(?:haz|hazme|crea|creame|genera|generame|dibuja|dibujame|disena|disename|pinta|pintame|ilustra|ilustrame)\s+"
                      r"(?:una?s?|el|la|los|las|mi|me)?\s*(?:(?:\d|dos|tres|cuatro)\s+(?:opciones|versiones|variantes)\s+(?:de\s+)?(?:una?\s+)?)?" + _NOUN + r"\b")


_COLOREAR = re.compile(r"^(?:jarvis\s+)?(?:dibuja|dibujame|pinta|pintame|haz|hazme|crea|creame)\b.*\bpara colorear\b")


def is_image(t):
    return bool(_TRIGGER.search(t) or _COLOREAR.search(t))


_SUBJ_NOUN = (r"(?:im[aá]gen(?:es)?|ilustraci[oó]n(?:es)?|dibujos?|infograf[ií]as?|afiches?|carteles|cartel|p[oó]sters?|portadas?|caricaturas?|logos?|"
              r"mascotas?|personajes?)")


def subject(text):
    """Lo que hay que dibujar. Las palabras genéricas («imagen», «ilustración», «dibujo») se quitan; las que dicen qué es
    («afiche», «logo», «portada»…) se dejan."""
    txt = text.strip()
    m = re.search(r"\b(" + _SUBJ_NOUN + r")\b", txt, flags=re.I)
    if not m:
        m2 = re.match(r"^\s*(?:jarvis[\s,]+)?(?:dib[uú]ja(?:me)?|p[ií]nta(?:me)?)\s+(?:una?\s+)?", txt, flags=re.I)
        return (txt[m2.end():] if m2 else txt).strip(" .,:") or txt
    if re.match(r"im[aá]gen|ilustraci|dibujo", m.group(1), re.I):
        s = re.sub(r"^\s*(?:del|de|sobre|con|para)?\s*", "", txt[m.end():])
    else:
        s = txt[m.start():]
    return s.strip(" .,:") or txt


# ----------------------------------------------------------------------------- 11.7: estudio de imágenes
STYLES = {
    "ilustracion": "ilustración educativa, colores agradables",
    "caricatura": "estilo caricatura amigable para niños y jóvenes, contornos definidos, colores vivos",
    "realista": "fotografía realista, luz natural, nítida",
    "acuarela": "pintura en acuarela, trazos suaves y papel con textura",
    "plano": "ilustración plana (flat design), formas simples, pocos colores, fondo limpio",
    "3d": "render 3D suave tipo animación, iluminación de estudio",
    "colorear": ("dibujo de líneas negras gruesas sobre fondo blanco para que los estudiantes lo coloreen: sin colores, sin grises, "
                 "sin sombras ni texturas, áreas cerradas y amplias"),
    "pixel": "pixel art, estilo videojuego retro",
    "boceto": "boceto a lápiz sobre papel",
    "diagrama": "diagrama educativo limpio, fondo blanco, flechas y etiquetas claras",
    "comic": "viñeta de cómic con colores planos y globos de diálogo en español",
}
STYLE_NAMES = {"ilustracion": "ilustración", "caricatura": "caricatura", "realista": "realista", "acuarela": "acuarela", "plano": "plano",
               "3d": "3D", "colorear": "para colorear", "pixel": "pixel art", "boceto": "boceto", "diagrama": "diagrama", "comic": "cómic"}
_STYLE_RX = [("colorear", r"\bpara colorear\b|\bcolorear\b|\blibro de colorear\b"), ("caricatura", r"\bcaricatura|\bcartoon|\banimad[oa]\b|\binfantil\b"),
             ("realista", r"\brealista|\bfotografi|\bfoto real|\bfotorrealista"), ("acuarela", r"\bacuarela"), ("plano", r"\bplan[oa]\b|\bflat\b|\bminimalista"),
             ("3d", r"\b3d\b|\btres dimensiones|\btipo pixar"), ("pixel", r"\bpixel"), ("boceto", r"\bboceto|\ba lapiz\b"),
             ("diagrama", r"\bdiagrama|\besquema\b|\binfografia"), ("comic", r"\bcomic|\bhistorieta|\bvineta")]
ASPECTS = {"1:1": "cuadrada", "16:9": "horizontal", "3:4": "vertical"}
OPENAI_SIZES = {"1:1": "1024x1024", "16:9": "1536x1024", "3:4": "1024x1536"}
_NUMS = {"dos": 2, "tres": 3, "cuatro": 4, "un par de": 2}


def _norm(t):
    import unicodedata
    t = unicodedata.normalize("NFD", str(t).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def detect_style(text):
    t = _norm(text)
    return next((k for k, rx in _STYLE_RX if re.search(rx, t)), "")


def detect_aspect(text):
    t = _norm(text)
    if re.search(r"\bhorizontal|\bapaisad|\bpanoramic|\bdiapositiva|\bpresentacion|\bproyect|\b16 ?: ?9\b|\bbanner|\bpara el tablero|\bfondo de pantalla", t):
        return "16:9"
    if re.search(r"\bvertical|\bafiche|\bposter|\bcartel|\bportada|\bpara el celular|\bhistoria de|\bcarta\b|\bpara imprimir", t):
        return "3:4"
    if re.search(r"\bcuadrad|\blogo|\bperfil|\bicono", t):
        return "1:1"
    return ""


def detect_count(text):
    t = _norm(text)
    m = re.search(r"\b(\d|dos|tres|cuatro|un par de)\s+(?:opciones|versiones|variantes|propuestas|imagenes|ilustraciones|dibujos|afiches|logos)\b", t)
    if not m:
        return 1
    return max(1, min(4, int(m.group(1)) if m.group(1).isdigit() else _NUMS[m.group(1)]))


def clean_subject(text):
    """El tema sin las palabras de estilo, formato o número de opciones."""
    s = subject(text)
    s = re.sub(r"^(?:\d|dos|tres|cuatro|un par de)\s+(?:opciones|versiones|variantes|propuestas)\s+(?:de\s+)?(?:una?\s+)?" + _SUBJ_NOUN + r"?\s*(?:del|de|sobre)?\s*",
               "", s, flags=re.I)
    s = re.sub(r"\s*,?\s*\b(?:en (?:formato |estilo )?|estilo |tipo )?(?:horizontal|vertical|cuadrada|apaisada)\b", "", s, flags=re.I)
    s = re.sub(r"\s*,?\s*\b(?:en|de|con)\s+estilo\s+[\wáéíóú]+(?:\s+3d)?\b", "", s, flags=re.I)
    s = re.sub(r"\s*,?\s*\ben (?:acuarela|caricatura|pixel art|3d|boceto)\b", "", s, flags=re.I)
    s = re.sub(r"^(?:del|de|sobre)\s+", "", s.strip(" .,:"), flags=re.I)
    return s.strip(" .,:") or subject(text)


def build_prompt(subj, style="", aspect=""):
    fmt = {"16:9": " Formato horizontal 16:9, para proyectar en clase.", "3:4": " Formato vertical, para imprimir o usar como afiche.",
           "1:1": " Formato cuadrado."}.get(aspect, "")
    return ("Crea una imagen clara y atractiva para usar en una clase de colegio en Colombia: " + subj.strip() +
            f". Estilo: {STYLES.get(style, STYLES['ilustracion'])}; sin marcas de agua.{fmt} Si lleva textos o etiquetas, que estén en español, "
            "sean pocos, grandes y sin errores de ortografía.")


def edit_prompt(instruction, style=""):
    st = f" Redibújala con este estilo: {STYLES[style]}." if style else ""
    return (f"Edita esta imagen según esta instrucción del docente: «{instruction.strip()}».{st} Conserva todo lo demás igual (composición, "
            "personajes y colores) salvo lo que se pide. Si hay textos, en español y sin errores de ortografía.")


def gemini_body(prompt_text, aspect="", image_b64="", mime="image/png"):
    parts = [{"text": prompt_text}]
    if image_b64:
        parts.append({"inlineData": {"mimeType": mime, "data": image_b64}})
    gc = {"responseModalities": ["IMAGE", "TEXT"]}
    if aspect:
        gc["imageConfig"] = {"aspectRatio": aspect}
    return {"contents": [{"role": "user", "parts": parts}], "generationConfig": gc}


def pick_openai_model(names, wanted=""):
    """El modelo de imágenes de OpenAI: el que pongas o el más nuevo de la cuenta (gpt-image-…, sin «mini»)."""
    if wanted:
        return wanted
    c = [n for n in names if n.startswith("gpt-image")]

    def ver(n):
        return [int(x) for x in re.findall(r"\d+", n)] or [0]
    full = sorted((n for n in c if "mini" not in n), key=ver, reverse=True)
    return (full or sorted(c, key=ver, reverse=True) or ["gpt-image-1"])[0]


def openai_payload(model, prompt_text, aspect=""):
    return {"model": model, "prompt": prompt_text, "size": OPENAI_SIZES.get(aspect, "1024x1024"), "n": 1}


def openai_extract(data):
    try:
        b = (data.get("data") or [])[0].get("b64_json")
    except (AttributeError, IndexError, TypeError):
        b = None
    if not b:
        raise ValueError("el modelo no devolvió ninguna imagen")
    return base64.b64decode(b), ".png"


def multipart(fields, files):
    """Cuerpo multipart/form-data (para editar con OpenAI). → (bytes, content_type)."""
    import uuid
    bnd = "jarvis" + uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, (name, raw, mime) in files.items():
        out.append(f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\nContent-Type: {mime}\r\n\r\n'.encode() + raw + b"\r\n")
    out.append(f"--{bnd}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={bnd}"


def letter_pdf(img_path, out_path, title=""):
    """La imagen en una hoja tamaño carta para imprimir (horizontal si la imagen es ancha), con márgenes."""
    from PIL import Image, ImageDraw
    im = Image.open(img_path).convert("RGB")
    W, H = (1650, 1275) if im.width > im.height * 1.1 else (1275, 1650)            # carta a 150 ppp
    page = Image.new("RGB", (W, H), "white")
    top = 75
    if title:
        d = ImageDraw.Draw(page)
        try:
            from PIL import ImageFont
            font = ImageFont.truetype("arial.ttf", 34)
        except OSError:
            font = None
        d.text((75, 50), title[:90], fill="black", font=font)
        top = 120
    box = (W - 150, H - top - 75)
    im.thumbnail(box, Image.LANCZOS) if (im.width > box[0] or im.height > box[1]) else None
    if im.width < box[0] and im.height < box[1]:
        k = min(box[0] / im.width, box[1] / im.height)
        im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
    page.paste(im, ((W - im.width) // 2, top + (box[1] - im.height) // 2))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    page.save(out_path, "PDF", resolution=150)
    return out_path
