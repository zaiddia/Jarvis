"""Generador de documentos (12.14): la página /documentos y la orden por voz.

Escoges formato y plantilla, describes lo que quieres (y si quieres, subes un archivo de base), Jarvis
muestra la vista previa, le pides cambios por partes y lo guardas. Queda en el historial con botones para
abrir, ver la carpeta, proyectar o subir a Drive. Solo se lee el archivo que tú subas a esta página.
"""
import base64
import datetime
import os
import re
import threading
import uuid

import adjuntos
import aula
import documentos
from nucleo import J

gen = {"drafts": {}, "win": None, "busy": False}


def gen_start():
    documentos.history.configure(J.CONFIG_DIR)


def _courses():
    return sorted(aula.data.get("cursos", {}), key=aula.course_sort_key)


def _grade_txt(curso, grado):
    if grado:
        return grado
    g = aula.grade_of(curso) if curso else ""
    return f"{g}°" if g else ""


def _source_text(fid):
    """El texto del archivo que subiste a la página (o leído por la IA si es una foto o un PDF escaneado)."""
    it = adjuntos.get(fid) if fid else None
    if not it:
        return ""
    text, img = J.content_for_ai(it, 20000)
    if text.strip():
        return text
    if img is not None:
        try:
            return J.ocr(it)
        except Exception as e:
            J.log_terminal(f"No pude leer el archivo de base: {e}", "AVISO")
    return ""


def _ask_ai(prompt, fmt, pedido):
    last = None
    for _ in range(2):                                   # un reintento si la IA devuelve algo mal formado
        try:
            raw = J.ai_chat([{"role": "user", "content": prompt}], json_mode=True, max_tokens=8000)
            return documentos.validate(fmt, J._extract_json(raw), pedido)
        except (ValueError, TypeError) as e:
            last = e
    raise ValueError(str(last) or "respuesta no válida")


def make_draft(opts):
    """Arma el borrador (sin guardar archivo). → borrador. Lanza ValueError / J.AIError."""
    fmt, tpl = opts.get("formato", "word"), opts.get("plantilla", "libre")
    if fmt not in documentos.FORMATS:
        raise ValueError("formato desconocido")
    if tpl not in documentos.TEMPLATES:
        tpl = "libre"
    if not documentos.ok_format(tpl, fmt):
        raise ValueError(f"«{documentos.TEMPLATES[tpl][0]}» no se puede hacer en {documentos.FORMATS[fmt][0]}")
    curso = str(opts.get("curso") or "")[:20]
    pedido = re.sub(r"\s+", " ", str(opts.get("pedido") or "")).strip()[:3000]
    if tpl in documentos.LOCAL:
        if not curso:
            raise ValueError("escoge el curso para armar la lista")
        m = documentos.local_table(tpl, curso, aula.students(curso), int(opts.get("notas") or 5))
        kind = "table"
    else:
        if not pedido and not opts.get("archivo"):
            raise ValueError("describe el contenido del documento")
        fuente = _source_text(opts.get("archivo"))
        prompt = documentos.build_prompt(fmt, tpl, pedido or "Un documento a partir del material adjunto", _grade_txt(curso, opts.get("grado")),
                                         str(opts.get("asignatura") or "")[:60], opts.get("largo", "medio"), fuente)
        m = _ask_ai(prompt + J.lessons_ctx(), fmt, pedido)
        kind = documentos.kind_of(fmt)
    did = uuid.uuid4().hex[:8]
    d = {"id": did, "formato": fmt, "plantilla": tpl, "kind": kind, "model": m, "curso": curso, "pedido": pedido,
         "grado": _grade_txt(curso, opts.get("grado")), "encabezado": opts.get("encabezado", True) is not False, "version": 1}
    gen["drafts"][did] = d
    for k in list(gen["drafts"])[:-12]:
        gen["drafts"].pop(k, None)
    return d


def _dg_public(d):
    return {"id": d["id"], "formato": d["formato"], "plantilla": d["plantilla"], "kind": d["kind"], "model": d["model"],
            "version": d["version"], "texto": documentos.plain(d["kind"], d["model"])[:20000]}


def revise_draft(did, cambio):
    d = gen["drafts"].get(did)
    if not d:
        raise ValueError("ese borrador ya no está; genéralo otra vez")
    cambio = re.sub(r"\s+", " ", str(cambio or "")).strip()[:800]
    if not cambio:
        raise ValueError("escribe qué cambiar")
    fmt = d["formato"] if documentos.kind_of(d["formato"]) == d["kind"] else {"doc": "word", "table": "excel", "slides": "powerpoint"}[d["kind"]]
    d["model"] = _ask_ai(documentos.revise_prompt(fmt, d["model"], cambio), fmt, d["pedido"])
    d["version"] += 1
    return d


def save_draft(did, fmt=None):
    d = gen["drafts"].get(did)
    if not d:
        raise ValueError("ese borrador ya no está; genéralo otra vez")
    fmt = fmt or d["formato"]
    if not documentos.compatible(d["kind"], fmt):
        raise ValueError(f"este borrador no se puede guardar en {documentos.FORMATS[fmt][0]}; genéralo en ese formato")
    head = d["encabezado"]
    path = documentos.build(fmt, d["kind"], d["model"], J.settings["output_dir"], J.Document,
                            J.settings["aula_docente"] if head else "", J.settings["aula_institucion"] if head else "",
                            d["curso"] if head else "", d["grado"])
    J.generated_files.add(path)                      # (también lo sube a Drive si activaste «Subir automáticamente»)
    item = {"id": uuid.uuid4().hex[:8], "titulo": d["model"]["titulo"], "formato": fmt, "plantilla": d["plantilla"], "ruta": path,
            "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "pedido": d["pedido"][:300],
            "texto": documentos.plain(d["kind"], d["model"])[:20000]}
    documentos.history.add(item)
    J.log_terminal(f"Documento guardado: {path}", "DOCUMENTOS")
    return item


# ============================================================================ PÁGINA
@J.app.route("/documentos")
def docs_page():
    from flask import render_template
    return render_template("documentos.html", version=J.VERSION, asset_v=getattr(J, "ASSET_V", ""), look=J.settings.get("look", "clasico"))


def open_docs_page():
    J._open_page("/documentos", "Generador de documentos", gen)


@J.socketio.on("open_docs_page")
def handle_open_docs_page(data=None):
    open_docs_page()
    return {"ok": True}


@J.socketio.on("doc_state")
def handle_doc_state(data=None):
    return {"formatos": {k: v[0] for k, v in documentos.FORMATS.items()},
            "plantillas": {k: {"nombre": v[0], "formatos": list(v[2]), "local": k in documentos.LOCAL} for k, v in documentos.TEMPLATES.items()},
            "largos": {k: v[0] for k, v in documentos.LENGTHS.items()}, "cursos": _courses(),
            "activo": aula.data.get("activo") or "", "asignaturas": J.subject_choices(),
            "docente": J.settings.get("aula_docente", ""), "institucion": J.settings.get("aula_institucion", ""),
            "historial": documentos.history.listing()[:40], "drive": bool(J.gdrive_ready()), "ocupado": gen["busy"]}


def _dg_run(label, fn, done_event):
    if gen["busy"]:
        return {"ok": False, "error": "Ya estoy preparando otro documento; espera a que termine."}
    gen["busy"] = True
    J.socketio.emit("doc_busy", {"on": True, "label": label})

    def work():
        try:
            out = fn()
            J.socketio.emit(done_event, {"ok": True, **out})
        except J.AIError as e:
            J.socketio.emit(done_event, {"ok": False, "error": J.ai_error_reply(e)})
        except ValueError as e:
            J.socketio.emit(done_event, {"ok": False, "error": str(e)[:300]})
        except Exception as e:
            J.note_error("DOCUMENTOS", e)
            J.socketio.emit(done_event, {"ok": False, "error": f"No me salió bien: {e}"})
        finally:
            gen["busy"] = False
            J.socketio.emit("doc_busy", {"on": False})
    J.start_job(label, work, "documentos")
    return {"ok": True}


@J.socketio.on("doc_generate")
def handle_doc_generate(data=None):
    opts = dict(data or {})
    return _dg_run("Generando documento", lambda: _dg_public(make_draft(opts)), "doc_draft")


@J.socketio.on("doc_revise")
def handle_doc_revise(data=None):
    d = data or {}
    return _dg_run("Cambiando el documento", lambda: _dg_public(revise_draft(str(d.get("id")), d.get("cambio"))), "doc_draft")


@J.socketio.on("doc_save")
def handle_doc_save(data=None):
    d = data or {}
    try:
        item = save_draft(str(d.get("id")), d.get("formato") or None)
    except (ValueError, OSError) as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        J.note_error("DOCUMENTOS", e)
        return {"ok": False, "error": f"No se pudo guardar: {e}"}
    if J.IS_WIN and d.get("abrir"):
        try:
            os.startfile(item["ruta"])
        except OSError:
            pass
    return {"ok": True, "item": item, "historial": documentos.history.listing()[:40]}


def _hist(hid):
    return next((x for x in documentos.history.items if x.get("id") == hid), None)


@J.socketio.on("doc_action")
def handle_doc_action(data=None):
    d = data or {}
    it = _hist(str(d.get("id") or ""))
    if not it:
        return {"ok": False, "error": "No encuentro ese documento en el historial."}
    act = d.get("accion")
    if act in ("abrir", "carpeta"):
        if not os.path.exists(it["ruta"]):
            return {"ok": False, "error": "El archivo ya no está en su carpeta."}
        J.generated_files.add(it["ruta"])
        return J.handle_file_open({"path": it["ruta"], "folder": act == "carpeta"})
    if act == "proyectar":
        J.project_show({"kind": "texto", "text": it.get("texto") or it["titulo"], "title": it["titulo"]})
        return {"ok": True, "msg": "En el proyector."}
    if act == "drive":
        if not J.gdrive_ready():
            return {"ok": False, "error": "Conecta tu cuenta de Google en Ajustes › Integraciones para subir a Drive."}
        try:
            f = J.drive_upload(it["ruta"])
            return {"ok": True, "msg": "Subido a tu carpeta Jarvis de Drive.", "link": (f or {}).get("webViewLink", "")}
        except Exception as e:
            return {"ok": False, "error": f"No se pudo subir: {e}"}
    if act == "quitar":
        documentos.history.items = [x for x in documentos.history.items if x.get("id") != it["id"]]
        documentos.history.save()
        return {"ok": True, "historial": documentos.history.listing()[:40]}
    return {"ok": False}


@J.socketio.on("doc_upload")
def handle_doc_upload(data=None):
    """El archivo de base que subes a la página (solo ese se lee)."""
    f = data or {}
    try:
        m = re.match(r"data:[^;]*;base64,(.+)$", str(f.get("data") or ""), re.S)
        raw = base64.b64decode(m.group(1) if m else "")
        if not raw:
            raise ValueError("vino vacío")
        it = adjuntos.add(str(f.get("name") or "archivo"), raw)
    except (ValueError, OSError) as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "id": it["id"], "nombre": it["nombre"], "tipo": it["tipo"]}


# ============================================================================ VOZ
_DG_PAGE = re.compile(r"\b(?:abre|abreme|muestra|muestrame|abrir)\s+(?:el |la )?(?:generador de documentos|generador|creador de documentos)\b")
_DG_VERB = r"(?:crea|creame|haz|hazme|prepara|preparame|genera|generame|redacta|redactame|elabora|elaborame|escribe|escribeme)"
_DG_FMT = {"pdf": "pdf", "word": "word", "texto": "texto", "txt": "texto", "bloc de notas": "texto", "csv": "csv"}
_DG_TPL = {"informe": "informe", "circular": "circular", "acta": "acta", "documento": "libre", "carta": "libre"}


def docs_voice(text, t):
    if _DG_PAGE.search(t):
        open_docs_page()
        J.reply("Te abrí el generador de documentos: escoge el formato, describe lo que necesitas y te muestro la vista previa.", "DOCUMENTOS")
        return True
    if not re.match(rf"^(?:por favor )?{_DG_VERB}\b", t):
        return False
    fm = re.search(r"\ben (pdf|word|texto|txt|bloc de notas|csv)\b", t)
    tm = re.search(r"\b(?:un|una|el|la)\s+(informe|circular|acta|documento|carta)\b", t)
    if not tm or (tm.group(1) in ("documento", "carta") and not fm):
        return False                                     # lo demás lo atienden el aula y la oficina, como siempre
    fmt = _DG_FMT[fm.group(1)] if fm else "word"
    tpl = _DG_TPL[tm.group(1)]
    pedido = re.sub(r"\s+en (?:pdf|word|texto|txt|bloc de notas|csv)\b", "", text, flags=re.I).strip()
    if gen["busy"]:
        J.reply("Ya estoy preparando otro documento. Te aviso cuando termine.", "DOCUMENTOS")
        return True
    J.reply(f"Preparando {documentos.TEMPLATES[tpl][0].lower() if tpl != 'libre' else 'el documento'} en {documentos.FORMATS[fmt][0]}. Te aviso cuando esté.",
            "DOCUMENTOS")

    def work():
        gen["busy"] = True
        try:
            d = make_draft({"formato": fmt, "plantilla": tpl, "pedido": pedido, "curso": aula.data.get("activo") or ""})
            item = save_draft(d["id"])
            if J.IS_WIN and J.settings.get("aula_open_docs", True):
                try:
                    os.startfile(item["ruta"])
                except OSError:
                    pass
            J.reply(f"Listo: «{item['titulo']}» en {documentos.FORMATS[fmt][0]}, en la carpeta Documentos. "
                    "Para cambiarlo por partes, ábrelo en el generador de documentos.", "DOCUMENTOS")
        except J.AIError as e:
            J.reply(J.ai_error_reply(e), "DOCUMENTOS")
        except Exception as e:
            J.log_terminal(f"Documento por voz: {e}", "ERROR")
            J.reply("No me salió bien el documento. Inténtalo otra vez con más detalle.", "DOCUMENTOS")
        finally:
            gen["busy"] = False
    threading.Thread(target=work, daemon=True, name="documento-voz").start()
    return True


__all__ = [
    '_DG_FMT',
    '_DG_PAGE',
    '_DG_TPL',
    '_DG_VERB',
    '_ask_ai',
    '_courses',
    '_grade_txt',
    '_hist',
    '_dg_public',
    '_dg_run',
    '_source_text',
    'docs_page',
    'docs_voice',
    'gen',
    'gen_start',
    'handle_doc_action',
    'handle_doc_generate',
    'handle_doc_revise',
    'handle_doc_save',
    'handle_doc_state',
    'handle_doc_upload',
    'handle_open_docs_page',
    'make_draft',
    'open_docs_page',
    'revise_draft',
    'save_draft',
]
