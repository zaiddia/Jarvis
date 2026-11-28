"""12.74: el Estudio creativo, una pantalla para crear imágenes, programar y hacer videos con IA.

  · Imágenes: describe lo que quieres, escoge estilo, formato y cuántas; Jarvis escoge el generador (o tú). Galería con
    «otra versión», «horizontal», «imprimir» y «editar».
  · Código: generar un programa a partir de lo que pides, revisar, explicar o corregir el que pegas. Lo hace la mejor IA
    para programar que tengas, y el analizador revisa la sintaxis. Nunca se ejecuta.
  · Video: clips cortos con IA (NVIDIA Cosmos), de texto o animando una imagen de la galería.
  · «Jarvis, abre el estudio creativo» · «abre el estudio de código» · «abre el estudio de imágenes» · «… de video».

Solo responde en este equipo (127.0.0.1). Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import itertools
import os
import re
import threading
import time

import imagenes
from nucleo import J

e73 = {"jobs": {}, "videos": []}
_e73_seq = itertools.count(1)
_e73_lock = threading.Lock()
E73_TABS = ("imagenes", "codigo", "video")


def _e73_local():
    from flask import abort, request
    if request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403)


def e73_job(tipo, fn):
    """Corre fn() en segundo plano y guarda su resultado para que la pantalla lo recoja. → id del trabajo."""
    jid = str(next(_e73_seq))
    with _e73_lock:
        e73["jobs"][jid] = {"tipo": tipo, "estado": "trabajando", "msg": "", "res": None, "t": time.time()}
        for old in sorted(e73["jobs"], key=lambda k: e73["jobs"][k]["t"])[:-20]:
            e73["jobs"].pop(old, None)

    def work():
        job = e73["jobs"][jid]
        try:
            job["res"] = fn()
            job["estado"] = "listo"
        except J.AIError as e:
            job.update(estado="error", msg=J.ai_error_reply(e))
        except Exception as e:
            job.update(estado="error", msg=str(e)[:300])
    J.start_job({"imagen": "Creando la imagen", "codigo": "Trabajando el código", "video": "Haciendo el video"}.get(tipo, "Estudio"), work, "estudio")
    return jid


def e73_items():
    out = []
    for i, it in enumerate(J.studio["items"]):
        if os.path.exists(it["path"]):
            out.append({"i": i, "tema": it.get("tema", ""), "estilo": imagenes.STYLE_NAMES.get(it.get("estilo", ""), ""),
                        "formato": imagenes.ASPECTS.get(it.get("formato", ""), ""), "t": it.get("t", 0)})
    return list(reversed(out))


def e73_state():
    return {"imagenes": J.im73_status(), "ia": J.c73_status(), "galeria": e73_items(),
            "videos": [{"i": i, "tema": v["tema"]} for i, v in enumerate(e73["videos"]) if os.path.exists(v["path"])][::-1],
            "jobs": {k: {kk: vv for kk, vv in v.items() if kk != "t"} for k, v in e73["jobs"].items()},
            "estilos": imagenes.STYLE_NAMES, "formatos": imagenes.ASPECTS, "nvidia": bool(J._ai_cfg({"ai_provider": "nvidia"}).get("key"))}


# ============================================================================ LAS ACCIONES
def e73_image(tema, estilo="", formato="", n=1, generador="auto"):
    def fn():
        prev = getattr(J._tl, "img_pref", "")
        J._tl.img_pref = generador if generador and generador != "auto" else ""
        try:
            paths = J.studio_generate(tema, estilo, formato, n)
        except RuntimeError as e:
            raise ValueError(str(e))
        finally:
            J._tl.img_pref = prev
        for p in paths:
            J.generated_files.add(p)
        return {"n": len(paths)}
    return e73_job("imagen", fn)


def e73_image_action(i, action, texto=""):
    items = J.studio["items"]
    if not (0 <= i < len(items)) or not os.path.exists(items[i]["path"]):
        raise ValueError("ya no encuentro esa imagen")
    src = dict(items[i], studio=True)

    def fn():
        paths = J.studio_run(src, action, texto)
        if not paths:
            raise ValueError("no pude con la imagen (mira el chat de Jarvis)")
        return {"n": len(paths), "pdf": action == "carta"}
    return e73_job("imagen", fn)


def e73_code(accion, codigo="", nombre="", descripcion="", lenguaje=""):
    def fn():
        if accion == "generar":
            g = J.code_generate(descripcion, lenguaje, J.agent.get("curso", ""))
            return {"accion": "generar", "codigo": g["codigo"], "explicacion": g["explicacion"], "como_probarlo": g["como_probarlo"],
                    "lenguaje": g["lenguaje"], "errores": g["errores"], "archivo": os.path.basename(g["ruta"]),
                    "correcciones": g["correcciones"], "ia": J.c73_status()["codigo"]}
        r, lang, findings = J.code_review_data(codigo, nombre, accion)
        return {"accion": accion, "lenguaje": lang, "analizador": findings, "ia": J.c73_status()["codigo"], **r}
    return e73_job("codigo", fn)


def e73_video(tema, segundos=5, formato="16:9", img=-1):
    image = ""
    if img is not None and img >= 0:
        items = J.studio["items"]
        if not (0 <= img < len(items)):
            raise ValueError("ya no encuentro esa imagen")
        image = items[img]["path"]

    def fn():
        try:
            path = J.vi63_make(tema, segundos, formato, image)
        except RuntimeError as e:
            raise ValueError(str(e))
        e73["videos"].append({"path": path, "tema": tema or "imagen animada"})
        del e73["videos"][:-20]
        return {"i": len(e73["videos"]) - 1}
    return e73_job("video", fn)


# ============================================================================ LA PÁGINA
@J.app.route("/estudio")
def e73_page():
    from flask import render_template, request
    _e73_local()
    tab = request.args.get("tab", "imagenes")
    return render_template("estudio73.html", tab=tab if tab in E73_TABS else "imagenes", version=J.VERSION)


@J.app.route("/estudio/api/estado")
def e73_api_state():
    from flask import jsonify
    _e73_local()
    return jsonify(e73_state())


@J.app.route("/estudio/api/<accion>", methods=["POST"])
def e73_api(accion):
    from flask import jsonify, request
    _e73_local()
    d = request.get_json(silent=True) or {}
    try:
        if accion == "imagen":
            tema = str(d.get("tema") or "").strip()[:800]
            if len(tema) < 3:
                raise ValueError("describe la imagen que quieres")
            jid = e73_image(tema, str(d.get("estilo") or "")[:20], str(d.get("formato") or "")[:6],
                            max(1, min(4, int(d.get("n") or 1))), str(d.get("generador") or "auto")[:12])
        elif accion == "accion":
            act = str(d.get("action") or "")
            if act not in ("otra", "formato", "editar", "carta"):
                raise ValueError("acción desconocida")
            jid = e73_image_action(int(d.get("i", -1)), act, str(d.get("texto") or "")[:600])
        elif accion == "codigo":
            acc = str(d.get("accion") or "revisar")
            if acc not in ("generar", "revisar", "explicar", "corregir"):
                raise ValueError("acción desconocida")
            code = str(d.get("codigo") or "")[:48000]
            desc = str(d.get("descripcion") or "").strip()[:2000]
            if acc == "generar" and len(desc) < 5:
                raise ValueError("cuéntame qué debe hacer el programa")
            if acc != "generar" and not code.strip():
                raise ValueError("pega el código que reviso")
            jid = e73_code(acc, code, str(d.get("nombre") or "")[:80], desc, str(d.get("lenguaje") or "")[:20])
        elif accion == "video":
            img = d.get("img")
            jid = e73_video(str(d.get("tema") or "").strip()[:400], max(1, min(10, float(d.get("segundos") or 5))),
                            str(d.get("formato") or "16:9")[:6], int(img) if img not in (None, "") else -1)
        elif accion == "instalar":
            started = J.im73_install_job()
            return jsonify({"ok": True, "msg": "Instalando el generador de tu PC; tarda unos minutos." if started else "Ya se está instalando."})
        elif accion == "generador":
            pid = str(d.get("id") or "auto")
            if pid not in ("auto", "gemini", "chatgpt", "sensenova", "nvidia", "local"):
                raise ValueError("generador desconocido")
            J.apply_settings({"image_provider": pid})
            return jsonify({"ok": True})
        else:
            raise ValueError("acción desconocida")
    except (ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": str(e)})
    return jsonify({"ok": True, "job": jid})


@J.app.route("/estudio/archivo/<int:i>")
def e73_file(i):
    from flask import abort, send_file
    _e73_local()
    items = J.studio["items"]
    if not (0 <= i < len(items)) or not os.path.exists(items[i]["path"]):
        abort(404)
    return send_file(items[i]["path"])


@J.app.route("/estudio/video/<int:i>")
def e73_video_file(i):
    from flask import abort, send_file
    _e73_local()
    if not (0 <= i < len(e73["videos"])) or not os.path.exists(e73["videos"][i]["path"]):
        abort(404)
    return send_file(e73["videos"][i]["path"], mimetype="video/mp4")


# ============================================================================ POR VOZ
_E73_OPEN = re.compile(r"^(?:jarvis\s+)?(?:abre|abreme|muestrame|ensename|lleva(?:me)? a|ve a|vamos a)\s+(?:el\s+)?estudio"
                       r"(?:\s+(creativo|de (?:imagenes|imagen|codigo|programacion|programar|video|videos)))?$")


def estudio73_voice(text, t):
    m = _E73_OPEN.match(t)
    if not m:
        return False
    w = m.group(1) or ""
    tab = "codigo" if re.search(r"codigo|program", w) else "video" if "video" in w else "imagenes"
    J.open_window(f"/estudio?tab={tab}", "Estudio creativo")
    J.reply({"codigo": "Te abro el Estudio en la parte de código: genera, revisa o corrige programas.",
             "video": "Te abro el Estudio en la parte de video.",
             "imagenes": "Te abro el Estudio creativo: imágenes, código y video en una sola pantalla."}[tab], "ESTUDIO")
    return True


__all__ = ["E73_TABS", "e73", "e73_code", "e73_image", "e73_image_action", "e73_items", "e73_job", "e73_state", "e73_video",
           "estudio73_voice", "_E73_OPEN", "e73_page", "e73_api_state", "e73_api", "e73_file", "e73_video_file"]
