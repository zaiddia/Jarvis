"""12.23: audios y videos que subes con el clip → texto, con resumen y acuerdos; y cambiar el tamaño de una imagen.

- Sube una grabación de reunión, una nota de voz o un video (hasta 300 MB; se sube por partes) y pulsa «Acta» o
  «Transcribir», o di «transcribe este audio», «saca el acta de la reunión».
- La transcripción la hace Gemini con tu clave (el audio viaja a Google, en trozos de 5 minutos). Sin clave o sin
  internet se usa Whisper en tu equipo, si está instalado.
- Queda en Documentos Jarvis › Transcripciones: el texto completo y, si lo pides, el acta (resumen, acuerdos, tareas).
- «déjala de 800 de ancho», «tamaño carné», «redúcela a la mitad»: cambia el tamaño de la imagen que subiste.

Solo trabaja con los archivos que TÚ subes al chat. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import base64
import glob
import os
import re
import shutil
import subprocess
import tempfile
import time

import adjuntos
import conversiones
from nucleo import J

CHUNK_SECS = 300
_TR_NOWIN = 0x08000000


# ============================================================================ SUBIR POR PARTES
_parts = {}                    # uid → {"path", "name", "next", "t"}


@J.socketio.on("attach_part")
def handle_attach_part(data=None):
    """Un audio o video grande llega en trozos de pocos MB: {"uid", "name", "i", "n", "data" (data URL)}."""
    d = data or {}
    uid = re.sub(r"[^\w-]", "", str(d.get("uid") or ""))[:40]
    name = str(d.get("name") or "archivo")
    try:
        i, n = int(d.get("i")), int(d.get("n"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "Subida mal formada."}
    if not adjuntos._dir:
        return {"ok": False, "error": "Jarvis aún está arrancando; inténtalo en unos segundos."}
    if not uid or adjuntos.kind_of(name) not in adjuntos.MEDIA or not (0 <= i < n <= 400):
        return {"ok": False, "error": "Por partes solo se suben audios y videos."}
    for k in [k for k, v in _parts.items() if time.time() - v["t"] > 1800]:      # subidas abandonadas
        _drop_part(k)
    st = _parts.get(uid)
    if st is None:
        if i != 0:
            return {"ok": False, "error": "Se perdió el comienzo del archivo; súbelo otra vez."}
        fd, path = tempfile.mkstemp(prefix="subida_", suffix=".part", dir=adjuntos._dir)
        os.close(fd)
        st = _parts[uid] = {"path": path, "name": name, "next": 0, "t": time.time()}
    if i != st["next"]:
        _drop_part(uid)
        return {"ok": False, "error": "Las partes llegaron en desorden; súbelo otra vez."}
    try:
        m = re.match(r"data:[^;]*;base64,(.*)$", str(d.get("data") or ""), re.S)
        raw = base64.b64decode(m.group(1) if m else "")
        if os.path.getsize(st["path"]) + len(raw) > adjuntos.MAX_MEDIA:
            raise ValueError("el archivo es muy grande (máximo 300 MB)")
        with open(st["path"], "ab") as f:
            f.write(raw)
    except (ValueError, OSError) as e:
        _drop_part(uid)
        return {"ok": False, "error": str(e)}
    st.update(next=i + 1, t=time.time())
    if i + 1 < n:
        return {"ok": True, "sigue": True}
    _parts.pop(uid, None)
    try:
        it = adjuntos.add_path(st["name"], st["path"])
    except (ValueError, OSError) as e:
        try:
            os.remove(st["path"])
        except OSError:
            pass
        return {"ok": False, "error": str(e)}
    J._batch["ids"] = [it["id"]]
    J.log_terminal("Adjuntos: " + adjuntos.describe(it), "ADJUNTOS")
    return {"ok": True, **J.card_of([it]), "errores": []}


def _drop_part(uid):
    st = _parts.pop(uid, None)
    if st:
        try:
            os.remove(st["path"])
        except OSError:
            pass


# ============================================================================ DEL AUDIO AL TEXTO
def media_chunks(src, tmp, secs=CHUNK_SECS):
    """ffmpeg saca solo el sonido (mono, liviano) y lo parte en trozos. → [rutas .mp3]"""
    exe = J._ffmpeg()
    if not exe:
        raise ValueError("falta el componente de audio (ffmpeg): vuelve a ejecutar instalar.bat")
    r = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
                        "-f", "segment", "-segment_time", str(secs), "-reset_timestamps", "1", os.path.join(tmp, "p_%04d.mp3")],
                       capture_output=True, stdin=subprocess.DEVNULL, timeout=1800, creationflags=_TR_NOWIN if J.IS_WIN else 0)
    parts = sorted(glob.glob(os.path.join(tmp, "p_*.mp3")))
    if r.returncode != 0 or not parts:
        err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise ValueError("no pude leer el sonido de ese archivo" + (f" ({err[-1][:120]})" if err else " (¿tiene audio?)"))
    return [p for p in parts if os.path.getsize(p) > 600] or parts[:1]


_TR_PROMPT = ("Transcribe este audio palabra por palabra, en el idioma en que se habla (casi siempre español de Colombia). "
              "Si hablan varias personas, empieza cada intervención en una línea nueva con «Persona 1:», «Persona 2:»… y mantén el mismo "
              "número para la misma voz. No resumas, no corrijas lo dicho y no agregues comentarios. Un tramo que no se entienda va como "
              "[inaudible]. Devuelve SOLO la transcripción. Si no hay ninguna voz, devuelve exactamente: (nada)")


def _tr_gemini(cfg, path, hint=""):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    prompt = _TR_PROMPT + (f" Es la continuación de una grabación; lo último que se dijo fue: «{hint}»." if hint else "")
    body = {"contents": [{"role": "user", "parts": [{"inline_data": {"mime_type": "audio/mp3", "data": b64}}, {"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 8192, "temperature": 0}}

    def call(c):
        return J._gemini_text(J._post(f"{J.GEMINI_BASE}/models/{c['model']}:generateContent", J._gemini_headers(c), body, (), timeout=240))
    out = (J._with_fallback(cfg, call) or "").strip()
    return "" if out.lower().strip(" .") == "(nada)" else out


def _tr_whisper(path):
    """En tu equipo: el trozo a sonido crudo y de ahí a Whisper. → texto o None si Whisper no está."""
    r = subprocess.run([J._ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                       capture_output=True, stdin=subprocess.DEVNULL, timeout=600, creationflags=_TR_NOWIN if J.IS_WIN else 0)
    if r.returncode != 0 or not r.stdout:
        return ""
    return J._whisper_transcribe(r.stdout)


def transcribe_media(it, progress=None):
    """→ (texto, cómo se hizo, minutos). Lanza ValueError si no se pudo."""
    tmp = tempfile.mkdtemp(prefix="jarvis_tr_")
    try:
        parts = J.media_chunks(it["ruta"], tmp)
        cfg = None if J.is_offline() else J._gemini_for_stt()
        out, how, hint = [], "", ""
        for n, p in enumerate(parts, 1):
            if progress:
                progress(n, len(parts))
            text = None
            if cfg:
                try:
                    text, how = J._tr_gemini(cfg, p, hint), how or "Gemini"
                except J.AIError as e:
                    J.log_terminal(f"Gemini no pudo con el trozo {n} ({e.why or e}); pruebo en tu equipo.", "TRANSCRIPCIÓN")
                    text = None
            if text is None:
                text = J._tr_whisper(p)
                if text is None:
                    raise ValueError("para transcribir necesito la clave de Gemini (Ajustes › Inteligencia artificial) con internet, "
                                     "o Whisper instalado en tu equipo" if not cfg else "Gemini no respondió y no hay Whisper en tu equipo para seguir")
                how = "Whisper en tu equipo" if how in ("", "Whisper en tu equipo") else "Gemini y Whisper"
            text = text.strip()
            if text:
                out.append(text)
                hint = re.sub(r"\s+", " ", text)[-160:]
        full = "\n\n".join(out).strip()
        if not full:
            raise ValueError("no se oye ninguna voz en ese archivo")
        return full, how, round(len(parts) * CHUNK_SECS / 60)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================ ACTA
def minutes_prompt(text, local=False):
    cap = 14000 if local else 120000
    cut = len(text) > cap
    return ("Esta es la transcripción de una grabación (reunión, clase o nota de voz)" + (", recortada porque es muy larga" if cut else "") + ":\n\n"
            + text[:cap] +
            "\n\nEscribe en español, sin markdown ni asteriscos, exactamente con estos títulos en mayúsculas, cada uno en su línea:\n"
            "RESUMEN\n(de 4 a 8 frases con lo esencial)\n\nACUERDOS\n(una línea por cada decisión o acuerdo, empezando con «- »)\n\n"
            "TAREAS\n(una línea por tarea: «- qué — quién — para cuándo»; pon «sin responsable» o «sin fecha» si no se dijo)\n\n"
            "PENDIENTES\n(lo que quedó sin resolver, una línea por punto)\n\n"
            "Usa solo lo que se dice en la transcripción: no inventes nombres, fechas ni acuerdos. Si una sección no tiene nada, escribe «- Ninguno».")


def media_minutes(text):
    local = J._is_local_ai(J._ai_cfg())
    return J.ai_chat([{"role": "user", "content": J.minutes_prompt(text, local)}], max_tokens=1400).strip()


def _save_text(base, suffix, title, sections):
    """Guarda un Word (o un .txt si falta python-docx). sections: [(título o "", texto)]. → ruta"""
    folder = os.path.join(J.settings["output_dir"], "Transcripciones")
    if J.Document is not None:
        dst = conversiones._out(folder, f"{base} ({suffix})", "docx")
        doc = J.Document()
        doc.add_heading(title, 1)
        for head, body in sections:
            if head:
                doc.add_heading(head, 2)
            for line in body.split("\n"):
                if line.strip():
                    doc.add_paragraph(line.strip())
        doc.save(dst)
        return dst
    dst = conversiones._out(folder, f"{base} ({suffix})", "txt")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(title + "\n\n" + "\n\n".join((h + "\n" if h else "") + b for h, b in sections) + "\n")
    return dst


def media_run(it, with_minutes=True):
    """El trabajo completo con un audio o video subido. Avisa al terminar. → ruta del documento o None"""
    base = os.path.splitext(it["nombre"])[0]
    t0 = time.time()

    def progress(n, total):
        if total > 1:
            J.log_terminal(f"Transcribiendo «{it['nombre']}»: parte {n} de {total}", "TRANSCRIPCIÓN")
    text, how, mins = J.transcribe_media(it, progress)
    words = len(text.split())
    notes = ""
    if with_minutes:
        try:
            notes = J.media_minutes(text)
        except J.AIError as e:
            J.log_terminal(f"No pude hacer el acta ({e.why or e}); queda la transcripción.", "TRANSCRIPCIÓN")
    stamp = f"Transcrito con {how} el {time.strftime('%d/%m/%Y')} a partir de «{it['nombre']}». Revísalo: puede tener palabras mal oídas."
    if notes:
        secs = [("", stamp)]
        for m in re.finditer(r"^(RESUMEN|ACUERDOS|TAREAS|PENDIENTES)\s*:?\s*\n(.*?)(?=^(?:RESUMEN|ACUERDOS|TAREAS|PENDIENTES)\s*:?\s*$|\Z)", notes, re.S | re.M):
            secs.append((m.group(1).capitalize(), m.group(2).strip()))
        if len(secs) == 1:
            secs.append(("Resumen", notes))
        secs.append(("Transcripción completa", text))
        dst = J._save_text(base, "acta", f"Acta: {base}", secs)
    else:
        dst = J._save_text(base, "transcripción", f"Transcripción: {base}", [("", stamp), ("", text)])
    J.generated_files.add(dst)
    took = time.time() - t0
    head = ""
    if notes:
        m = re.search(r"RESUMEN\s*:?\s*\n(.*?)(?=^\s*(?:ACUERDOS|TAREAS|PENDIENTES)\b|\Z)", notes, re.S | re.M)
        head = " " + re.sub(r"\s+", " ", (m.group(1) if m else notes)).strip()[:420]
        n_ac = len([x for x in re.findall(r"^ACUERDOS\s*:?\s*\n(.*?)(?=^\s*(?:TAREAS|PENDIENTES)\b|\Z)", notes, re.S | re.M)[:1] for x in x.split("\n")
                    if x.strip().startswith("-") and "ninguno" not in x.lower()])
        head += f" Anoté {n_ac} acuerdo{'s' if n_ac != 1 else ''}; el detalle y las tareas están en el documento." if n_ac else " El detalle está en el documento."
    J.notify(f"Listo «{it['nombre']}»: {words} palabras transcritas con {how} en {took / 60:.0f} min." .replace(" en 0 min", "")
             + (head if notes else " " + (re.sub(r"\s+", " ", text)[:260] + ("…" if len(text) > 260 else "")))
             + f" Quedó en Transcripciones: {os.path.basename(dst)}.", "TRANSCRIPCIÓN")
    return dst


# ============================================================================ TAMAÑO DE UNA IMAGEN
_CARD_SPECS = {"carne": {"preset": "carne"}, "cuadrada": {"preset": "cuadrada"}, "w800": {"w": 800}, "mitad": {"pct": 50}}


def resize_run(it, spec):
    dst, before, after, note = conversiones.image_resize(it, os.path.join(J.settings["output_dir"], "Conversiones"), spec)
    J.generated_files.add(dst)
    J.notify(f"Listo: «{it['nombre']}» pasó de {before[0]}×{before[1]} a {after[0]}×{after[1]} píxeles ({os.path.getsize(dst) // 1024} KB)"
             + (f"; {note}" if note else "") + f". Quedó en Conversiones: {os.path.basename(dst)}.", "ADJUNTOS")
    return dst


def media_action(its, action, pregunta=""):
    """Lo de 12.23 dentro de attach_run. → (True, resultado) si era suyo."""
    it = its[0]
    if action.startswith("redim"):
        spec = _CARD_SPECS.get(action[6:]) or conversiones.resize_spec(J.normalize(pregunta) if pregunta else "")
        if it["tipo"] != "imagen" or not spec:
            raise ValueError("dime el tamaño: «déjala de 800 de ancho», «tamaño carné» o «redúcela a la mitad»")
        return True, J.resize_run(it, spec)
    if it["tipo"] in adjuntos.MEDIA:
        if action in ("transcribir", "texto", "conv:texto"):
            return True, J.media_run(it, with_minutes=False)
        return True, J.media_run(it, with_minutes=True)       # acta, resumir, describir, una pregunta…
    return False, None


# ============================================================================ POR VOZ O ESCRIBIENDO
_M_ACTA = re.compile(r"\b(?:acta|minuta|resumen|resume(?:lo|la|me|melo|mela)?|acuerdos|compromisos|puntos clave|de que (?:hablan|hablaron|trata)|"
                     r"que (?:acordaron|se acordo|quedo|dijeron|dicen|dice))\b")
_M_TEXT = re.compile(r"\btranscrib\w*|\b(?:pasa|pasalo|pasala|convierte|conviertelo)\s+(?:.{0,20})?a texto\b|\bsaca(?:le)? el texto\b|\ben texto\b")
_M_REF = re.compile(r"\b(?:este|esta|ese|esa|el|la)\s+(?:audio|video|grabacion|nota de voz|reunion|clase grabada|archivo)\b")


def media_voice(text, t):
    """Con un audio o video recién subido: «transcríbelo», «saca el acta». Con una imagen: «déjala de 800 de ancho»."""
    rec = adjuntos.recent(1800)
    if not rec:
        return False
    last = J._batch_items()[-1]
    fresh = time.time() - last["t"] < 300
    if last["tipo"] in adjuntos.MEDIA:
        if not (fresh or _M_REF.search(t)):
            return False
        if _M_TEXT.search(t) and not re.search(r"\b(?:acta|minuta|resumen|acuerdos)\b", t):
            J.reply(f"Transcribo «{last['nombre']}»; puede tardar unos minutos. Te aviso al terminar.", "TRANSCRIPCIÓN")
            J._attach_go([last], "transcribir", text)
            return True
        if _M_ACTA.search(t) or _M_REF.search(t):
            J.reply(f"Transcribo «{last['nombre']}» y saco el resumen y los acuerdos; puede tardar unos minutos. Te aviso al terminar.", "TRANSCRIPCIÓN")
            J._attach_go([last], "acta", text)
            return True
        return False
    if last["tipo"] == "imagen" and (fresh or J._REF.search(t)):
        spec = conversiones.resize_spec(t)
        if spec:
            J.reply(f"Cambio el tamaño de «{last['nombre']}»…", "ADJUNTOS")
            J._attach_go([last], "redim", text)
            return True
    return False


__all__ = ['CHUNK_SECS', '_M_ACTA', '_M_REF', '_M_TEXT', '_drop_part', '_parts', '_save_text', '_tr_gemini', '_tr_whisper', 'handle_attach_part',
           'media_action', 'media_chunks', 'media_minutes', 'media_run', 'media_voice', 'minutes_prompt', 'resize_run', 'transcribe_media']
