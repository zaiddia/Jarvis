"""11.6: archivos e imágenes que subes al chat de Jarvis (botón del clip o arrastrándolos al HUD): leerlos y preguntarles
(«¿qué dice este PDF?», «resúmelo», «extrae la tabla de la foto»), sacar el texto (también de fotos y PDF escaneados,
con la IA con visión) y convertirlos entre formatos («pásalo a Word», «conviértelo a PDF», «únelos en un PDF»).

Solo trabaja con los archivos que TÚ subes al chat. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import base64
import io
import os
import re
import tempfile

import adjuntos
import conversiones
from nucleo import J

ACTIONS = {"describir": "¿Qué es?", "resumir": "Resumir", "texto": "Sacar el texto", "tabla": "Tabla a Excel", "revisar": "Revisar trabajo",
           "preguntas": "Hacer un quiz"}


_batch = {"ids": []}             # lo último que subiste junto (una tarjeta): a eso se refieren «únelos», «¿qué dicen?»


def _batch_items():
    rec = adjuntos.recent(1800)
    ids = {i["id"] for i in rec}
    its = [adjuntos.get(x) for x in _batch["ids"] if x in ids]
    return its if its else rec[-1:]


def _out_dir():
    return os.path.join(J.settings["output_dir"], "Conversiones")


def _preview(it):
    """Miniatura (data URL) para la tarjeta del chat."""
    from PIL import Image
    try:
        if it["tipo"] == "imagen":
            im = Image.open(it["ruta"])
            im.seek(0)
        elif it["tipo"] == "pdf" and adjuntos.pypdfium2:
            pdf = adjuntos.pypdfium2.PdfDocument(it["ruta"])
            im = pdf[0].render(scale=0.5).to_pil()
            pdf.close()
        else:
            return ""
        im = im.convert("RGB")
        im.thumbnail((240, 240))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=75)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def card_of(its):
    kinds = {i["tipo"] for i in its}
    acts = []
    if len(its) == 1:
        k = its[0]["tipo"]
        acts = ["describir"] if k == "imagen" else ["resumir"]
        acts += ["texto"] if k in ("imagen", "pdf") else []
        acts += ["tabla"] if k in ("imagen", "pdf", "word") else []
        acts += ["revisar"] if k == "imagen" else []
        acts += ["preguntas"] if k in ("pdf", "word", "powerpoint", "texto") else []
    convs = conversiones.options_for(its)
    return {"ids": [i["id"] for i in its], "nombres": [i["nombre"] for i in its], "desc": "; ".join(adjuntos.describe(i) for i in its),
            "tipos": sorted(kinds), "preview": _preview(its[0]) if len(its) == 1 else "",
            "acciones": [{"a": a, "t": ACTIONS[a]} for a in acts] + [{"a": "conv:" + c, "t": "→ " + conversiones.TARGETS[c]} for c in convs]}


@J.socketio.on("attach")
def handle_attach(data=None):
    """Uno o varios archivos subidos al chat: [{"name", "data" (data URL)}]."""
    files = (data or {}).get("files") or []
    its, errs = [], []
    for f in files[:10]:
        try:
            m = re.match(r"data:[^;]*;base64,(.+)$", str(f.get("data") or ""), re.S)
            raw = base64.b64decode(m.group(1) if m else "")
            if not raw:
                raise ValueError("vino vacío")
            its.append(adjuntos.add(str(f.get("name") or "archivo"), raw))
        except (ValueError, OSError) as e:
            errs.append(f"{f.get('name', 'archivo')}: {e}")
    if not its:
        return {"ok": False, "error": "; ".join(errs) or "No llegó ningún archivo."}
    _batch["ids"] = [i["id"] for i in its]
    if len(its) == 1 and its[0]["tipo"] == "imagen":
        J._set_review_image(its[0]["ruta"], "imagen")          # «revisa este trabajo» por voz también funciona con la foto subida
    J.log_terminal("Adjuntos: " + "; ".join(adjuntos.describe(i) for i in its), "ADJUNTOS")
    return {"ok": True, **card_of(its), "errores": errs}


@J.socketio.on("attach_card")
def handle_attach_card(data=None):
    """La tarjeta de varios archivos subidos uno por uno (para no pasar el límite de tamaño de un mensaje)."""
    its = [i for i in (adjuntos.get(x) for x in ((data or {}).get("ids") or [])) if i]
    if its:
        _batch["ids"] = [i["id"] for i in its]
    return {"ok": True, **card_of(its)} if its else {"ok": False, "error": "No encontré esos archivos; súbelos otra vez."}


@J.socketio.on("attach_action")
def handle_attach_action(data=None):
    d = data or {}
    its = [adjuntos.get(x) for x in (d.get("ids") or [])]
    its = [i for i in its if i]
    if not its:
        return {"ok": False, "error": "Ese archivo ya no está; súbelo otra vez."}
    a = str(d.get("action") or "")
    J.start_job("Trabajando con tu archivo", lambda: J.attach_run(its, a, str(d.get("pregunta") or "")), "adjunto")
    return {"ok": True}


# ============================================================================ LEER Y PREGUNTAR
def _vision_text(prompt, img_path, max_tokens=2500):
    cfg, err = J._vision_cfg()
    if not cfg:
        raise ValueError(err)
    if cfg["kind"] == "ollama":
        r = J.ollama.Client(host=cfg["ollama_host"], timeout=300).chat(model=J.settings["vision_model"].strip() or "moondream",
                                                                        messages=[{"role": "user", "content": prompt, "images": [img_path]}])
        return r["message"]["content"]
    J._need_key(cfg)
    return J._with_fallback(cfg, lambda c: J._cloud_chat(c, [{"role": "user", "content": prompt}], image_path=img_path, max_tokens=max_tokens))


def ocr(it, max_pages=6):
    """El texto de una imagen o de un PDF escaneado, leído por la IA con visión."""
    tmp = tempfile.mkdtemp(prefix="jarvis_ocr_")
    out = []
    for i, p in enumerate(adjuntos.vision_images(it, tmp, max_pages)):
        txt = J._vision_text("Transcribe EXACTAMENTE todo el texto de esta imagen, en su orden, sin resumir ni comentar. Respeta los párrafos; "
                           "las tablas como filas con « | » entre columnas; las fórmulas en texto plano (x², √9, 3/4). Si no hay texto, responde «(sin texto)».", p, 4000)
        out.append((f"[Página {i + 1}]\n" if it["tipo"] == "pdf" else "") + txt.strip())
    return "\n\n".join(out)


def content_for_ai(it, limit=30000):
    """(texto, imagen o None) para preguntarle a la IA por el archivo."""
    if it["tipo"] == "imagen":
        return "", adjuntos.vision_images(it, tempfile.mkdtemp(prefix="jarvis_v_"), 1)[0]
    text = adjuntos.text_of(it, limit)
    if it["tipo"] == "pdf" and adjuntos.is_scanned(it, text):
        imgs = adjuntos.vision_images(it, tempfile.mkdtemp(prefix="jarvis_v_"), 1)
        return "", (imgs[0] if imgs else None)
    return text, None


def ask_files(its, question):
    """Responde una pregunta sobre los adjuntos. → texto."""
    texts, imgs = [], []
    for it in its:
        t, img = content_for_ai(it)
        if img:
            imgs.append((it, img))
        if t:
            texts.append(f"=== {it['nombre']} ===\n{t}")
    q = question.strip() or "Explica brevemente qué es y qué contiene."
    rule = (" Responde en español, claro y útil para un docente; si citas el archivo, di la página o la hoja. Si algo no está en el archivo, dilo. "
            "Texto plano, sin markdown pesado.")
    if imgs and not texts:
        it, img = imgs[0]
        extra = f" (Hay {len(imgs)} imágenes; esta es la primera.)" if len(imgs) > 1 else ""
        return J._vision_text(f"El docente te muestra este archivo ({adjuntos.describe(it)}){extra}. Pregunta: «{q}».{rule}", img)
    body = "\n\n".join(texts)[:40000]
    return J.ai_chat([{"role": "user", "content": f"El docente subió estos archivos:\n{body}\n\nPregunta: «{q}».{rule}" + J.lessons_ctx()}],
                     max_tokens=1800).strip()


def table_from(it):
    """Las tablas del archivo (también de una foto de una lista de notas) → Excel. → ruta."""
    import json
    rule = ('Extrae TODAS las tablas tal cual (sin inventar), con sus encabezados. Responde SOLO con JSON: {"tablas": [{"nombre": str, '
            '"filas": [[celda, …], …]}]}. Números con punto decimal.')
    t, img = content_for_ai(it, 40000)
    if img:
        cfg, err = J._vision_cfg()
        if not cfg:
            raise ValueError(err)
        raw = J._vision_text("Esta es la foto de un documento. " + rule, img, 6000)
    else:
        raw = J.ai_chat([{"role": "user", "content": f"Del siguiente contenido, {rule[0].lower() + rule[1:]}\n\n{t[:40000]}"}], json_mode=True, max_tokens=8000)
    d = J._extract_json(raw)
    tabs = [x for x in (d.get("tablas") or []) if isinstance(x, dict) and x.get("filas")]
    if not tabs:
        raise ValueError("no encontré tablas en el archivo")
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    wb.remove(wb.active)
    for i, tb in enumerate(tabs[:10], 1):
        ws = wb.create_sheet(re.sub(r"[\[\]:*?/\\]", " ", str(tb.get("nombre") or f"Tabla {i}"))[:30] or f"Tabla {i}")
        for r, row in enumerate(tb["filas"][:5000]):
            vals = []
            for v in (row if isinstance(row, list) else [row]):
                s = str(v).strip() if v is not None else ""
                vals.append(float(s) if re.fullmatch(r"-?\d+\.\d+", s) else int(s) if re.fullmatch(r"-?\d{1,12}", s) else s)
            ws.append(vals)
            if r == 0:
                for c in ws[1]:
                    c.font = Font(bold=True)
    dst = conversiones._out(_out_dir(), it["nombre"] + " (tablas)", "xlsx")
    wb.save(dst)
    return dst, sum(len(t["filas"]) for t in tabs), len(tabs)


# ============================================================================ HACER LA ACCIÓN
def attach_run(its, action, pregunta=""):
    names = ", ".join(i["nombre"] for i in its)
    try:
        if action.startswith("conv:"):
            files, msg = J.convert_files(its, action[5:], pregunta)
            for f in files:
                J.generated_files.add(f)
            J.notify(msg, "ADJUNTOS")
            return files
        if action == "revisar":
            J._set_review_image(its[0]["ruta"], "imagen")
            J.start_review("actual")
            return None
        if action == "tabla":
            dst, n, nt = J.table_from(its[0])
            J.generated_files.add(dst)
            J.notify(f"Saqué {nt} tabla{'s' if nt != 1 else ''} ({n} filas) de «{its[0]['nombre']}» a Excel. Revísala: si viene de una foto, puede haber "
                     "algún número mal leído.", "ADJUNTOS")
            return dst
        if action == "texto":
            it = its[0]
            text = adjuntos.text_of(it, 2_000_000) if it["tipo"] not in ("imagen",) else ""
            how = "del archivo"
            if it["tipo"] == "imagen" or adjuntos.is_scanned(it, text):
                text, how = J.ocr(it), "leído con la IA (revísalo)"
            dst = conversiones.to_text(it, _out_dir(), text)
            J.generated_files.add(dst)
            J.notify(f"Listo el texto de «{it['nombre']}» ({how}): {len(text.split())} palabras. " + (text[:300] + "…" if len(text) > 300 else text), "ADJUNTOS")
            return dst
        if action == "preguntas":
            text, _img = content_for_ai(its[0], 7000)
            J.generate_material(f"quiz de 10 preguntas basado en este contenido:\n{text[:7000]}", "quiz")
            return None
        q = {"describir": "¿Qué es esto? Descríbelo y di qué contiene.", "resumir": "Resúmelo en 5 a 8 puntos clave, para un docente."}.get(action, pregunta)
        J.notify(J.ask_files(its, q), "ADJUNTOS")
    except (ValueError, conversiones.ConvertError) as e:
        J.notify(f"No pude con «{names}»: {e}", "ADJUNTOS")
    except J.AIError as e:
        J.notify(J.ai_error_reply(e), "ADJUNTOS")
    return None


def convert_files(its, target, extra=""):
    """→ ([rutas], mensaje)."""
    out = _out_dir()
    k = its[0]["tipo"]
    if target not in conversiones.options_for(its) and not (target == "pdf" and {i["tipo"] for i in its} == {"imagen"}):
        raise conversiones.ConvertError(f"no sé convertir {adjuntos.KIND_NAMES.get(k, k)} a {conversiones.TARGETS.get(target, target)}")
    if target == "pdf" and k == "imagen":
        f = conversiones.images_to_pdf(its, out)
        return [f], f"Listo: {len(its)} {'imágenes' if len(its) != 1 else 'imagen'} en un PDF ({os.path.basename(f)})."
    if target == "unir":
        f = conversiones.merge_pdfs(its, out)
        return [f], f"Listo: uní {len(its)} PDF en uno ({os.path.basename(f)})."
    it = its[0]
    if target in ("png", "jpg", "webp"):
        f = conversiones.image_to(it, out, target)
        return [f], f"Listo: la imagen en {target.upper()} ({os.path.basename(f)})."
    if target == "comprimir":
        f = conversiones.image_to(it, out, "jpg", compress=True)
        return [f], f"Listo: la imagen más liviana ({os.path.getsize(f) // 1024} KB, antes {it['bytes'] // 1024} KB)."
    if target == "imagenes":
        fs = adjuntos.page_images(it, os.path.join(out, os.path.splitext(it["nombre"])[0]), 1, 60)
        return fs, f"Listo: {len(fs)} página{'s' if len(fs) != 1 else ''} del PDF como imágenes PNG, en Documentos, Jarvis, Conversiones."
    if target == "word":
        ocr_text = J.ocr(it) if adjuntos.is_scanned(it) and J._vision_cfg()[0] else ""
        f, how = conversiones.pdf_to_word(it, out, J.Document, ocr_text)
        return [f], ("Listo el Word, con el formato original (lo convirtió tu Word)." if how == "formato" else
                     "Listo el Word con el texto del PDF, editable" + (" (leído con la IA: revísalo)" if ocr_text else "") +
                     ". Para conservar el diseño exacto hace falta tener Microsoft Word.") + f" ({os.path.basename(f)})"
    if target == "texto":
        text = adjuntos.text_of(it, 2_000_000)
        if k == "pdf" and adjuntos.is_scanned(it, text):
            text = J.ocr(it)
        f = conversiones.to_text(it, out, text)
        return [f], f"Listo el texto ({len(text.split())} palabras) en {os.path.basename(f)}."
    if target == "pdf":
        f = conversiones._to_pdf_office(it, out)
        return [f], f"Listo el PDF ({os.path.basename(f)})."
    if target == "csv":
        f = conversiones.excel_to_csv(it, out)
        return [f], f"Listo el CSV (separado por «;», como lo abre Excel en español): {os.path.basename(f)}."
    if target == "excel":
        f = conversiones.csv_to_excel(it, out)
        return [f], f"Listo el Excel: {os.path.basename(f)}."
    if target == "dividir":
        m = re.search(r"(\d+)\s*(?:a|al|-|hasta)\s*(\d+)", extra or "")
        one = re.search(r"\bpagina\s+(\d+)\b", extra or "")
        fs = conversiones.split_pdf(it, out, int(m.group(1)) if m else (int(one.group(1)) if one else None),
                                    int(m.group(2)) if m else (int(one.group(1)) if one else None))
        return fs, (f"Listo el PDF con esas páginas ({os.path.basename(fs[0])})." if (m or one) else f"Listo: separé el PDF en {len(fs)} archivos, uno por página.")
    if target == "girar":
        deg = 180 if re.search(r"\b180\b|de cabeza|al reves", extra or "") else (270 if re.search(r"\bizquierda\b|270", extra or "") else 90)
        f = conversiones.rotate_pdf(it, out, deg)
        return [f], f"Listo: el PDF girado {deg}° ({os.path.basename(f)})."
    raise conversiones.ConvertError("esa conversión no la tengo")


# ============================================================================ POR VOZ O ESCRIBIENDO
_REF = re.compile(r"\b(?:este|esta|estos|estas|ese|esa|esos|esas)\s+(?:archivos?|documentos?|pdfs?|imagen(?:es)?|fotos?|capturas?|hojas?|tablas?|"
                  r"presentacion(?:es)?|adjuntos?|words?|excels?|listas?|guias?|taller(?:es)?|examen(?:es)?|lecturas?|textos?)\b|"
                  r"\b(?:el|los|mi|mis)\s+(?:archivos?|adjuntos?)\b|"
                  r"\b(?:la|las|el|los)\s+(?:imagen(?:es)?|fotos?|archivos?|documentos?|pdfs?|capturas?)\s+que\s+(?:te\s+)?(?:subi|mande|envie|adjunte|pegue|pase)\b|"
                  r"\blo que (?:te )?(?:subi|mande|envie|adjunte|pegue|pase)\b")
_ASK = re.compile(r"^(?:jarvis\s+)?(?:que dice|que contiene|que hay en|de que (?:trata|habla)|resume(?:lo|la|los|las|me)?|explica(?:lo|la|me)|"
                  r"traduce(?:lo|la)|analiza(?:lo|la)|corrige(?:lo|la)|cuantas? (?:paginas|preguntas|filas|estudiantes|ejercicios|diapositivas))\b|"
                  r"\b(?:resumelo|resumela|resumelos|explicamelo|explicamela|traducelo|traducela)\b")
_CONV = re.compile(r"\b(convierte|pasa|guarda|exporta|transforma|cambia|pon|haz|deja)(lo|la|los|las)?\b.*?\b(?:a|en|como)\s+(?:un\s+|una\s+)?"
                   r"(pdf|word|docx|texto|txt|imagen(?:es)?|png|jpe?g|webp|excel|xlsx|csv)\b")
_MERGE = re.compile(r"\b(?:unelos|unelas|juntalos|juntalas|combinalos|combinalas)\b|\bun solo pdf\b|\btodo en un pdf\b|^(?:jarvis\s+)?(?:une|junta|combina)\b")
_COMPRESS = re.compile(r"\b(?:comprime(?:la|lo)?|reduce(?:le)? el (?:tamano|peso)|hazla mas liviana|que pese menos|bajale el peso)\b")
_SPLIT = re.compile(r"\b(?:dividelo|separalo|partelo)\b|\b(?:divide|separa|parte)\b.*\bpdf\b|\bsolo (?:las )?paginas?\s+\d+|\bsaca (?:la |las )?paginas?\s+\d+")
_ROTATE = re.compile(r"\b(?:giralo|girala|rotalo|rotala|enderezalo|enderezala)\b|\b(?:gira|rota)\s+(?:el|este|ese)\s+pdf\b")
_TEXT = re.compile(r"\b(?:extrae|extraele|sacale|saca|transcribe|copia|dame)\s+(?:el\s+|todo el\s+)?texto\b|\bque texto tiene\b|\btranscribe(?:lo|la)\b")
_TABLE = re.compile(r"\b(?:extrae|saca|pasa|copia)\s+(?:la|las)\s+tablas?\b|\bla tabla (?:a|en) excel\b")


def attachment_voice(text, t):
    import time
    rec = adjuntos.recent(1800)
    if not rec:
        return False
    last = _batch_items()[-1]
    fresh = time.time() - last["t"] < 300
    ref = bool(_REF.search(t))
    if not (fresh or ref):
        return False
    target = None
    m = _CONV.search(t)
    if m and (m.group(2) or ref or (fresh and t.startswith(m.group(1)) and len(t.split()) <= 6)):
        w = m.group(3)
        target = {"docx": "word", "txt": "texto", "jpeg": "jpg", "xlsx": "excel", "imagen": "imagenes" if last["tipo"] == "pdf" else "png",
                  "imagenes": "imagenes" if last["tipo"] == "pdf" else "png"}.get(w, w)
        if target == "excel" and last["tipo"] in ("imagen", "pdf", "word"):         # «pasa la lista de la foto a Excel»
            J.reply(f"Saco las tablas de «{last['nombre']}» a Excel…", "ADJUNTOS")
            J._attach_go([last], "tabla", t)
            return True
    elif _MERGE.search(t) and len(_batch_items()) > 1:
        target = "pdf" if {i["tipo"] for i in _batch_items()} == {"imagen"} else "unir"
    elif _COMPRESS.search(t) and last["tipo"] == "imagen":
        target = "comprimir"
    elif _SPLIT.search(t) and last["tipo"] == "pdf":
        target = "dividir"
    elif _ROTATE.search(t) and last["tipo"] == "pdf":
        target = "girar"
    if target:
        same = [i for i in _batch_items() if i["tipo"] == ("pdf" if target == "unir" else "imagen")]      # lo que subiste junto
        its = same if (len(same) > 1 and target in ("pdf", "unir")) else [last]
        J.reply(f"Convierto {'los ' + str(len(its)) + ' archivos' if len(its) > 1 else '«' + its[0]['nombre'] + '»'} a "
                f"{conversiones.TARGETS.get(target, target)}…", "ADJUNTOS")
        J._attach_go(its, "conv:" + target, t)
        return True
    if _TABLE.search(t):
        J.reply(f"Saco las tablas de «{last['nombre']}» a Excel…", "ADJUNTOS")
        J._attach_go([last], "tabla", t)
        return True
    if _TEXT.search(t):
        J.reply(f"Saco el texto de «{last['nombre']}»…", "ADJUNTOS")
        J._attach_go([last], "texto", t)
        return True
    if ref or _ASK.search(t):
        if J.state.get("ai") != "ok":
            J.reply("Para leer el archivo necesito la IA conectada.", "ADJUNTOS")
            return True
        its = _batch_items()
        J.reply("Leo " + ("los archivos" if len(its) > 1 else f"«{its[-1]['nombre']}»") + "…", "ADJUNTOS")
        J._attach_go(its, "pregunta", text)
        return True
    return False


def _attach_go(its, action, pregunta):
    if getattr(J._tl, "capture", None) is not None:
        J.attach_run(its, action, pregunta)
    else:
        J.start_job("Trabajando con tu archivo", lambda: J.attach_run(its, action, pregunta), "adjunto")


def attach_start():
    adjuntos.configure(J.CONFIG_DIR)


__all__ = ['ACTIONS', '_ASK', '_batch', '_batch_items', '_COMPRESS', '_CONV', '_MERGE', '_REF', '_ROTATE', '_SPLIT', '_TABLE', '_TEXT', '_attach_go', '_out_dir', '_preview', '_vision_text',
           'adjuntos', 'ask_files', 'attach_run', 'attach_start', 'attachment_voice', 'card_of', 'content_for_ai', 'conversiones', 'convert_files',
           'handle_attach', 'handle_attach_action', 'handle_attach_card', 'ocr', 'table_from']
