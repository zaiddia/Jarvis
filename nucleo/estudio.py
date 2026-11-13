"""11.7: estudio de imágenes. Crear imágenes a partir de lo que pides (con Gemini o ChatGPT), con estilo, formato y
varias opciones; seguir trabajándolas («otra versión», «cámbiale el fondo a azul», «hazla horizontal», «imprímela») y
editar con la IA una foto que subas al chat.

La lógica está en imagenes.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import base64
import io
import os
import re
import time
import urllib.error
import urllib.request

import adjuntos
import imagenes
from nucleo import J

studio = {"items": []}          # las imágenes creadas: [{"path", "tema", "estilo", "formato", "t"}]
_oa_model = {"name": "", "checked": 0.0}


# ============================================================================ QUIÉN LAS CREA
def image_backend():
    """(proveedor, cfg) o (None, mensaje)."""
    pref = J.settings.get("image_provider", "auto")
    g = J._gemini_for_stt()
    o = J._ai_cfg({"ai_provider": "chatgpt"})
    o = o if o.get("key") else None
    if pref == "gemini":
        return ("gemini", g) if g else (None, "para crear imágenes con Gemini necesito su clave (Ajustes › Inteligencia artificial)")
    if pref == "chatgpt":
        return ("chatgpt", o) if o else (None, "para crear imágenes con ChatGPT necesito su clave (Ajustes › Inteligencia artificial)")
    order = [("chatgpt", o), ("gemini", g)] if J.settings.get("ai_provider") == "chatgpt" else [("gemini", g), ("chatgpt", o)]
    for name, cfg in order:
        if not cfg:
            continue
        if name == "gemini" and not J.image_model():
            continue
        return name, cfg
    if g:
        return None, "tu cuenta de Gemini no tiene un modelo de imágenes disponible; pon una clave de ChatGPT en Ajustes › Inteligencia artificial o revisa tu cuenta de Gemini"
    return None, "para crear imágenes necesito tu clave de Gemini o de ChatGPT (Ajustes › Inteligencia artificial)"


def openai_image_model(cfg):
    if J.settings.get("image_model_openai", "").strip():
        return J.settings["image_model_openai"].strip()
    if not _oa_model["name"] or time.time() - _oa_model["checked"] > 3600:
        _oa_model["checked"] = time.time()
        try:
            d = J._http("GET", f"{cfg['base']}/models", {"Authorization": f"Bearer {cfg['key']}"}, timeout=10)
            _oa_model["name"] = imagenes.pick_openai_model([m.get("id", "") for m in d.get("data", [])])
        except Exception:
            _oa_model["name"] = "gpt-image-1"
    return _oa_model["name"]


def _post_multipart(url, key, fields, files, timeout=240):
    body, ctype = imagenes.multipart(fields, files)
    req = urllib.request.Request(url, data=body, method="POST", headers={"Authorization": f"Bearer {key}", "Content-Type": ctype,
                                                                        "User-Agent": f"Jarvis/{J.VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            import json
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        kind, why, msg = J._classify(e.code, raw)
        raise J.AIError(f"{why}. (HTTP {e.code}: {msg})", code=e.code, raw=raw[:800], kind=kind, why=why)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise J.AIError(f"Sin conexión: {e}", code=0, kind="net", why="no hay conexión con el servicio de imágenes. Revisa tu internet")


def _png_bytes(path, max_side=2048):
    from PIL import Image
    im = Image.open(path)
    im.seek(0)
    im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _one_image(prov, cfg, prompt, aspect="", src=None):
    """(bytes, extensión) de una imagen nueva o editada."""
    if prov == "gemini":
        b64 = base64.b64encode(_png_bytes(src)).decode() if src else ""

        def gen(model):
            url = f"{J.GEMINI_BASE}/models/{model}:generateContent"
            try:
                return J._http("POST", url, J._gemini_headers(cfg), imagenes.gemini_body(prompt, aspect, b64), timeout=180)
            except J.AIError as e:
                if not (aspect and e.code == 400):
                    raise
                return J._http("POST", url, J._gemini_headers(cfg), imagenes.gemini_body(prompt, "", b64), timeout=180)   # modelo sin formato
        model = J.image_model()
        try:
            data = gen(model)
        except J.AIError as e:
            if e.kind not in ("server", "quota"):
                raise
            data = None
            for alt in [m for m in J.image_models_all() if m != model][:2]:      # 12.25: saturado o sin cuota: otro modelo de imágenes de tu cuenta
                try:
                    data = gen(alt)
                    J.log_terminal(f"Imágenes: «{model}» está {'saturado' if e.kind == 'server' else 'sin cuota'}; usé «{alt}».", "IA")
                    break
                except J.AIError as e2:
                    if e2.kind not in ("server", "quota", "model", "bad"):
                        raise
            if data is None:
                raise e
        return imagenes.extract(data)
    model = J.openai_image_model(cfg)
    if src:
        fields = {"model": model, "prompt": prompt, "n": "1"}
        if aspect:
            fields["size"] = imagenes.OPENAI_SIZES[aspect]
        data = J._post_multipart(f"{cfg['base']}/images/edits", cfg["key"], fields, {"image": ("imagen.png", _png_bytes(src), "image/png")})
    else:
        data = J._http("POST", f"{cfg['base']}/images/generations", {"Authorization": f"Bearer {cfg['key']}"},
                       imagenes.openai_payload(model, prompt, aspect), timeout=240)
    return imagenes.openai_extract(data)


def studio_generate(tema, estilo="", formato="", n=1, folder=None, src=None, instruccion=""):
    """Crea (o edita, con «src») n imágenes. → [rutas]. Lanza RuntimeError con un mensaje claro."""
    prov, cfg = J.image_backend()
    if not prov:
        raise RuntimeError(cfg)
    prompt = imagenes.edit_prompt(instruccion, estilo) if src else imagenes.build_prompt(tema, estilo, formato)
    folder = folder or os.path.join(J.settings["output_dir"], "Imágenes")
    title = (tema or instruccion or "imagen")[:50] + (f" ({imagenes.STYLE_NAMES[estilo]})" if estilo else "")
    out = []
    for i in range(max(1, min(4, n))):
        try:
            raw, ext = J._one_image(prov, cfg, prompt, formato, src)
        except J.AIError as e:
            if out:
                break
            raise RuntimeError(e.why or str(e))
        except ValueError as e:
            if out:
                break
            raise RuntimeError(str(e))
        path = imagenes.save(raw, ext, folder, title + (f" {i + 1}" if n > 1 else ""))
        studio["items"].append({"path": path, "tema": tema or instruccion, "estilo": estilo, "formato": formato, "t": time.time()})
        del studio["items"][:-30]
        out.append(path)
        time.sleep(0.01)
    return out


def studio_info(path):
    it = next((x for x in reversed(studio["items"]) if x["path"] == path), None)
    return {"tema": it["tema"], "estilo": imagenes.STYLE_NAMES.get(it["estilo"], ""), "formato": imagenes.ASPECTS.get(it["formato"], "")} if it else None


# ============================================================================ TRABAJAR LA IMAGEN
def _studio_source(path="", attach_id=""):
    """{"path", "tema", "estilo", "formato", "t", "studio": bool} de la imagen a trabajar."""
    if attach_id:
        a = adjuntos.get(attach_id)
        return {"path": a["ruta"], "tema": "", "estilo": "", "formato": "", "t": a["t"], "studio": False} if a and a["tipo"] == "imagen" else None
    if path:
        it = next((x for x in reversed(studio["items"]) if x["path"] == path), None)
        return dict(it, studio=True) if it and os.path.exists(path) else None
    cands = []
    if studio["items"] and os.path.exists(studio["items"][-1]["path"]):
        cands.append(dict(studio["items"][-1], studio=True))
    imgs = [a for a in adjuntos.recent(1800) if a["tipo"] == "imagen"]
    if imgs:
        cands.append({"path": imgs[-1]["ruta"], "tema": "", "estilo": "", "formato": "", "t": imgs[-1]["t"], "studio": False})
    return max(cands, key=lambda c: c["t"]) if cands else None


def studio_run(src, action, texto=""):
    """action: "otra" (otra versión), "formato" (con texto = horizontal/vertical/cuadrada), "editar", "carta"."""
    try:
        if action == "carta":
            dst = os.path.join(J.settings["output_dir"], "Imágenes", os.path.splitext(os.path.basename(src["path"]))[0] + " (carta).pdf")
            imagenes.letter_pdf(src["path"], dst)
            J.generated_files.add(dst)
            opened = J._open_doc(dst)
            J.notify("Listo: la imagen en una hoja tamaño carta, lista para imprimir" + (" (la abrí)." if opened else "."), "IMAGEN")
            return [dst]
        estilo = imagenes.detect_style(texto) if texto else ""
        formato = imagenes.detect_aspect(texto) if texto else ""
        n = imagenes.detect_count(texto) if texto else 1
        if action == "otra" and src.get("studio"):
            paths = J.studio_generate(src["tema"], estilo or src["estilo"], formato or src["formato"], n)
        elif action == "formato" and src.get("studio"):
            paths = J.studio_generate(src["tema"], src["estilo"], formato or "16:9", 1)
        else:
            instr = texto or ("otra versión de esta imagen" if action == "otra" else
                              f"cámbiala a formato {imagenes.ASPECTS.get(formato, 'horizontal')}")
            paths = J.studio_generate(src.get("tema", ""), estilo, formato, 1, src=src["path"], instruccion=instr)
    except RuntimeError as e:
        J.notify(f"No pude con la imagen: {e}.", "IMAGEN")
        return []
    for p in paths:
        J.generated_files.add(p)
    J.notify(("Listas " + str(len(paths)) + " versiones" if len(paths) > 1 else "Lista la imagen") + ", en Documentos, carpeta Jarvis, Imágenes.", "IMAGEN")
    return paths


@J.socketio.on("studio_action")
def handle_studio_action(data=None):
    d = data or {}
    src = J._studio_source(str(d.get("path") or ""), str(d.get("attach") or ""))
    if not src:
        return {"ok": False, "error": "Ya no encuentro esa imagen."}
    action = str(d.get("action") or "")
    if action not in ("otra", "formato", "editar", "carta"):
        return {"ok": False, "error": "Acción desconocida."}
    if action == "editar" and not str(d.get("texto") or "").strip():
        return {"ok": False, "error": "Dime qué le cambio."}
    if action != "carta":
        prov, msg = J.image_backend()
        if not prov:
            return {"ok": False, "error": f"No puedo: {msg}."}
    J.start_job("Trabajando la imagen", lambda: J.studio_run(src, action, str(d.get("texto") or "")[:600]), "imagen")
    return {"ok": True}


# ============================================================================ POR VOZ O ESCRIBIENDO
_IMG_REF = re.compile(r"\b(?:la|esta|esa)\s+(?:imagen|ilustracion|foto|dibujo|caricatura|afiche|portada|logo|mascota)\b")
_AGAIN = re.compile(r"\b(?:otra version|otras? (?:\d|dos|tres|cuatro)? ?(?:versiones|opciones)|otra opcion|dame otra|haz otra|genera otra|hazla de nuevo|"
                    r"repitela|otra parecida|otra distinta|otra diferente)\b")
_PRINT = re.compile(r"\b(?:imprimela|imprimirla|imprime (?:la|esta) (?:imagen|ilustracion|foto)|tamano carta|hoja carta|pasala a pdf|ponla en (?:un )?pdf)\b")
_FMT = re.compile(r"^(?:jarvis\s+)?(?:hazla|ponla|dejala|cambiala a|pasala a)\s+(?:en\s+)?(?:formato\s+)?(horizontal|vertical|cuadrada)\s*$")
_STRONG = re.compile(r"^(?:jarvis\s+)?(?:cambiale|agregale|anadele|quitale|borrale|eliminale|pintale|coloreale|conviertela|redibujala|transformala|"
                     r"retocala|editala|mejorala|hazla|hazle|edita (?:la|esta|esa) (?:imagen|foto|ilustracion))\b")
_WEAK = re.compile(r"^(?:jarvis\s+)?(?:ponle|dale|cambia el|cambia la|cambia los|quita el|quita la|quita los|agrega|anade|pon el|pon la)\b")
_NOT_EDIT = re.compile(r"\b(?:a|en)\s+(?:pdf|word|png|jpe?g|webp|excel|texto|csv)\b|\bliviana\b|\bpese menos\b|\brecordatorio|\balarma|\bnota\b|\btarea\b")


def studio_voice(text, t):
    src = J._studio_source()
    if not src:
        return False
    age = time.time() - src["t"]
    ref = bool(_IMG_REF.search(t))
    if not (age < 900 or (ref and age < 3600)):
        return False
    action, texto = None, ""
    if _PRINT.search(t):
        action = "carta"
    elif _AGAIN.search(t) and src.get("studio"):
        action, texto = "otra", t
    elif _FMT.match(t):
        action, texto = ("formato" if src.get("studio") else "editar"), _FMT.match(t).group(1)
    elif not _NOT_EDIT.search(t) and (_STRONG.match(t) or (_WEAK.match(t) and (ref or age < 300))):
        action, texto = "editar", re.sub(r"^\s*jarvis[\s,]+", "", text.strip(), flags=re.I)
    if not action:
        return False
    if action != "carta":
        prov, msg = J.image_backend()
        if not prov:
            J.reply(f"No puedo: {msg}.", "IMAGEN")
            return True
    J.reply({"carta": "Pongo la imagen en una hoja tamaño carta…", "otra": "Hago otra versión…", "formato": "La hago en ese formato…",
             "editar": "Edito la imagen…"}[action], "IMAGEN")
    if getattr(J._tl, "capture", None) is not None:
        J.studio_run(src, action, texto)
    else:
        J.start_job("Trabajando la imagen", lambda: J.studio_run(src, action, texto), "imagen")
    return True


__all__ = ['_AGAIN', '_FMT', '_IMG_REF', '_NOT_EDIT', '_PRINT', '_STRONG', '_WEAK', '_oa_model', '_one_image', '_png_bytes', '_post_multipart', '_studio_source',
           'handle_studio_action', 'image_backend', 'openai_image_model', 'studio', 'studio_generate', 'studio_info', 'studio_run', 'studio_voice']
