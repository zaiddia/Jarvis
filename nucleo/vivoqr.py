"""11.4: guía viva por QR (explicación, ejemplo, figura, laboratorio, tarjetas y mini quiz que suma a la ruta de
dominio) y podcast de repaso con dos voces, que los estudiantes escuchan desde el celular.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import asyncio
import io
import os
import re
import secrets
import tempfile
import time
import urllib.parse

import aula
import graficas
import guiaviva
import practica
from nucleo import J

gtok = {}                                             # {token: (code, est)}


def _lan(path):
    return f"http://{J.lan_ip()}:{J.settings['mobile_port']}{path}"


def _g(code):
    g = guiaviva.data["guias"].get(str(code))
    return g if g and g.get("abierta") else None


# ============================================================================ GUÍA VIVA
@J.mobile_app.route("/g/<code>", methods=["GET"])
def guide_page(code):
    from flask import abort, render_template
    if not _g(code):
        abort(404)
    return render_template("guia.html", code=code)


@J.mobile_app.route("/g/<code>/datos", methods=["GET"])
def guide_data(code):
    from flask import abort
    g = _g(code)
    if not g:
        abort(404)
    return {"curso": g["curso"].replace(" · ", " – "), "tema": g["tema"], "nombres": list(aula.students(g["curso"])), **guiaviva.public_guide(g["guia"])}


@J.mobile_app.route("/g/<code>/img/<int:i>.png", methods=["GET"])
def guide_img(code, i):
    from flask import Response, abort
    g = _g(code)
    if not g or not 0 <= i < len(g["guia"]["bloques"]) or g["guia"]["bloques"][i]["tipo"] != "grafica":
        abort(404)
    path = graficas.render(g["guia"]["bloques"][i]["grafica"])
    if not path:
        abort(404)
    try:
        with open(path, "rb") as f:
            return Response(f.read(), mimetype="image/png", headers={"Cache-Control": "max-age=3600"})
    finally:
        os.remove(path)


@J.mobile_app.route("/g/<code>/entrar", methods=["POST"])
def guide_enter(code):
    from flask import abort, request
    g = _g(code)
    if not g:
        abort(404)
    d = request.get_json(silent=True) or {}
    est = str(d.get("nombre") or "")
    if est not in aula.students(g["curso"]):
        return {"ok": False, "msg": "Escoge tu nombre de la lista."}
    ok, msg = practica.check_pin(g["curso"], est, d.get("pin"))
    if not ok:
        return {"ok": False, "msg": msg}
    k = secrets.token_urlsafe(10)
    gtok[k] = (str(code), est)
    return {"ok": True, "k": k, "nombre": est.split()[0], "msg": msg}


@J.mobile_app.route("/g/<code>/quiz", methods=["POST"])
def guide_quiz(code):
    from flask import abort, request
    g = _g(code)
    if not g:
        abort(404)
    d = request.get_json(silent=True) or {}
    who = gtok.get(str(d.get("k") or ""))
    if not who or who[0] != str(code):
        return {"ok": False, "msg": "Entra con tu nombre y PIN para guardar tu resultado."}
    ans = [int(a) if isinstance(a, (int, float)) or str(a).isdigit() else None for a in (d.get("respuestas") or [])][:10]
    res = guiaviva.grade_quiz(g["guia"], ans)
    ok = sum(1 for r in res if r["ok"])
    first = who[1] not in g["lectores"]
    g["lectores"][who[1]] = {"ok": ok, "total": len(res), "t": time.strftime("%Y-%m-%d %H:%M")}
    guiaviva.save()
    if first:                                          # la primera vez: cuenta en su práctica y en su ruta de dominio
        for r in res:
            practica.record(g["curso"], who[1], g["tema"], r["ok"], 1 if r["ok"] else 2)
    return {"ok": True, "aciertos": ok, "total": len(res), "resultados": res}


@J.mobile_app.route("/lab", methods=["GET"])
@J.mobile_app.route("/lab/<name>", methods=["GET"])
def guide_lab(name=""):
    return J.lab_page(name)


@J.app.route("/guia-qr.png")
def guide_qr():
    import qrcode
    from flask import Response, abort, request
    c = request.args.get("c", "")
    if not _g(c):
        abort(404)
    buf = io.BytesIO()
    qrcode.make(_lan(f"/g/{c}"), box_size=10, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


def make_guide(curso, tema):
    g = aula.grade_of(curso)
    raw = J.ai_chat([{"role": "user", "content": guiaviva.guide_prompt(tema, f"{g}°" if g else "bachillerato", J._subject(curso), list(J.LABS))
                      + J.lessons_ctx()}], json_mode=True, max_tokens=7000)
    guia = guiaviva.clean_guide(J._extract_json(raw), list(J.LABS), graficas.clean)
    code = secrets.token_urlsafe(5)
    guiaviva.data["guias"][code] = {"curso": curso, "tema": tema, "guia": guia, "creado": time.strftime("%Y-%m-%d %H:%M"), "abierta": True,
                                    "lectores": {}}
    guiaviva.save()
    return code


# ============================================================================ PODCAST
def synth_podcast(script, path):
    """Graba cada línea con su voz (Edge) y une los MP3. → ruta o "" si no hay voz."""
    if J.edge_tts is None:
        return ""
    parts = []
    for line in script["lineas"]:
        fd, tmp = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        try:
            asyncio.run(J.edge_tts.Communicate(line["texto"], guiaviva.VOICES[line["quien"]], rate="+0%").save(tmp))
            with open(tmp, "rb") as f:
                parts.append(f.read())
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    with open(path, "wb") as f:
        for p in parts:
            f.write(p)
    return path


@J.mobile_app.route("/a/<code>", methods=["GET"])
def podcast_page(code):
    from flask import abort
    p = guiaviva.data["podcasts"].get(str(code))
    if not p:
        abort(404)
    import html
    lines = "".join(f"<p><b>{html.escape(l['quien'])}:</b> {html.escape(l['texto'])}</p>" for l in p["guion"]["lineas"])
    return (f"<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{html.escape(p['titulo'])}</title><style>body{{margin:0;padding:18px;background:#03060c;color:#e6f6ff;font-family:system-ui,sans-serif;"
            "line-height:1.5}h1{color:#2ee6ff;font-size:21px}audio{width:100%;margin:12px 0 18px}p{font-size:15px;margin:0 0 10px}b{color:#ffb547}"
            f"details{{background:#071320;border:1px solid #1d3344;border-radius:12px;padding:12px}}</style></head><body><h1>🎧 {html.escape(p['titulo'])}</h1>"
            f"<p style='color:#7d95ab'>{html.escape(p['curso'].replace(' · ', ' – '))} · podcast de repaso</p>"
            + (f"<audio controls preload='none' src='/a/{code}.mp3'></audio>" if p.get("mp3") else "<p>(Sin audio: aquí está el guion.)</p>")
            + f"<details><summary>Leer el guion</summary>{lines}</details></body></html>")


@J.mobile_app.route("/a/<code>.mp3", methods=["GET"])
def podcast_mp3(code):
    from flask import abort, send_file
    p = guiaviva.data["podcasts"].get(str(code))
    if not p or not p.get("mp3") or not os.path.exists(p["mp3"]):
        abort(404)
    return send_file(p["mp3"], mimetype="audio/mpeg")


@J.app.route("/podcast-qr.png")
def podcast_qr():
    import qrcode
    from flask import Response, abort, request
    c = request.args.get("c", "")
    if c not in guiaviva.data["podcasts"]:
        abort(404)
    buf = io.BytesIO()
    qrcode.make(_lan(f"/a/{c}"), box_size=10, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


# ============================================================================ VOZ
_COURSE_TAIL = r"(?:\s+(?:para|de|en)\s+((?:grado\s+)?(?:\d{1,2}\s?[a-z]?|sexto|septimo|octavo|noveno|undecimo|decimo|once)\b.*))?$"
_GV_MAKE = re.compile(r"\b(?:haz|hazme|crea|creame|genera|prepara|preparame|arma)\s+(?:una\s+)?guia viva\s+(?:de|sobre)\s+(.+?)" + _COURSE_TAIL)
_GV_CLOSE = re.compile(r"\b(?:cierra|termina|desactiva)\s+(?:la\s+)?guia(?: viva)?\b")
_GV_ASK = re.compile(r"\bquien(?:es)? (?:ha |han )?(?:leido|hecho|visto) la guia\b|\bcomo va la guia(?: viva)?\b")
_PC_MAKE = re.compile(r"\b(?:haz|hazme|crea|creame|genera|prepara|preparame|graba)\s+(?:un\s+)?(?:podcast|audio)(?:\s+de repaso)?\s+(?:de|sobre)\s+(.+?)" + _COURSE_TAIL)


def _vq_course(spoken):
    c = J._resolve_course((spoken or "").strip())
    return (J.grade_key(c, spoken or "", ask=False) or c) if c else ""


def live_guide_voice(text, t):
    m = _GV_MAKE.search(t)
    if m:
        curso = _vq_course(m.group(2) or "")
        if not curso or not aula.students(curso):
            J.reply("¿Para qué curso (con su lista)? Por ejemplo: «haz una guía viva de funciones lineales para 9A».", "GUÍA VIVA")
            return True
        if J.state.get("ai") != "ok":
            J.reply("Para la guía viva necesito la IA conectada.", "GUÍA VIVA")
            return True
        if J._need_lan():
            return True
        tema = m.group(1).strip()
        J.reply(f"Preparo la guía viva de «{tema}» para {curso}…", "GUÍA VIVA")

        def work():
            try:
                code = J.make_guide(curso, tema)
            except Exception as e:
                J.notify(f"No pude preparar la guía: {getattr(e, 'why', e)}", "GUÍA VIVA")
                return
            J._open_projector()
            J.socketio.emit("ticket", {"open": True, "url": _lan(f"/g/{code}"), "qr": "/guia-qr.png?c=" + code, "tipo": "guia",
                                       "tema": f"Guía viva · {tema}", "n": 0})
            g = guiaviva.data["guias"][code]["guia"]
            kinds = {b["tipo"] for b in g["bloques"]}
            J.notify(f"Lista la guía viva de «{tema}» para {curso}: " + ", ".join(x for x, k in (("explicación", "explicacion"), ("ejemplo resuelto", "ejemplo"),
                     ("figura", "grafica"), ("laboratorio", "lab"), ("tarjetas", "tarjetas"), ("mini quiz", "quiz")) if k in kinds) +
                     ". El QR está en el proyector; el quiz final suma a la práctica y a la ruta de dominio de cada uno. «¿Quién ha leído la guía?».",
                     "GUÍA VIVA")
        if getattr(J._tl, "capture", None) is not None:
            work()
        else:
            J.start_job("Preparando la guía viva", work, "guia")
        return True
    if _GV_CLOSE.search(t):
        open_g = [c for c, g in guiaviva.data["guias"].items() if g["abierta"]]
        if not open_g:
            return False
        for c in open_g:
            guiaviva.data["guias"][c]["abierta"] = False
        guiaviva.save()
        J.socketio.emit("ticket", {"open": False, "results": None})
        J.reply(f"Cerré {'la guía viva' if len(open_g) == 1 else f'{len(open_g)} guías vivas'}.", "GUÍA VIVA")
        return True
    if _GV_ASK.search(t):
        gs = sorted(guiaviva.data["guias"].values(), key=lambda g: g["creado"])
        if not gs:
            J.reply("No has hecho guías vivas todavía.", "GUÍA VIVA")
            return True
        g = gs[-1]
        ls = g["lectores"]
        falta = [n for n in aula.students(g["curso"]) if n not in ls]
        J.reply(f"Guía «{g['tema']}» ({g['curso']}): la terminaron {len(ls)}" +
                (f", con {round(100 * sum(v['ok'] for v in ls.values()) / max(1, sum(v['total'] for v in ls.values())))} % de aciertos en el quiz" if ls else "") +
                (f". Faltan: {', '.join(falta[:8])}" + ("…" if len(falta) > 8 else "") if falta else ". ¡Todos!") + ".", "GUÍA VIVA")
        return True
    m = _PC_MAKE.search(t)
    if m:
        curso = _vq_course(m.group(2) or "") or aula.data.get("activo", "")
        if J.state.get("ai") != "ok":
            J.reply("Para el podcast necesito la IA conectada (para el guion).", "PODCAST")
            return True
        tema = m.group(1).strip()
        J.reply(f"Escribo y grabo el podcast de repaso de «{tema}»" + (f" para {curso}" if curso else "") + "…", "PODCAST")

        def work():
            g = aula.grade_of(curso) if curso else None
            try:
                raw = J.ai_chat([{"role": "user", "content": guiaviva.podcast_prompt(tema, f"{g}°" if g else "bachillerato", J._subject(curso) if curso else "Matemáticas")}],
                                json_mode=True, max_tokens=4000)
                script = guiaviva.clean_script(J._extract_json(raw))
            except Exception as e:
                J.notify(f"No pude escribir el guion: {getattr(e, 'why', e)}", "PODCAST")
                return
            path = guiaviva.podcast_path(J.settings["output_dir"], curso.replace(" · ", " "), script["titulo"])
            try:
                mp3 = J.synth_podcast(script, path)
            except Exception as e:
                J.log_terminal(f"Podcast: {e}", "AVISO")
                mp3 = ""
            code = secrets.token_urlsafe(5)
            guiaviva.data["podcasts"][code] = {"titulo": script["titulo"], "curso": curso, "tema": tema, "guion": script, "mp3": mp3,
                                               "creado": time.strftime("%Y-%m-%d %H:%M")}
            guiaviva.save()
            if mp3:
                J.generated_files.add(mp3)
            if J.mobile.get("server"):
                J._open_projector()
                J.socketio.emit("ticket", {"open": True, "url": _lan(f"/a/{code}"), "qr": "/podcast-qr.png?c=" + code, "tipo": "podcast",
                                           "tema": f"🎧 {script['titulo']}", "n": 0})
            mins = round(sum(len(l["texto"].split()) for l in script["lineas"]) / 150, 1)
            J.notify((f"Listo el podcast «{script['titulo']}» (unos {str(mins).replace('.', ',')} minutos, voces de Laura y Mateo). "
                      if mp3 else f"Listo el guion de «{script['titulo']}», pero no pude grabar el audio (falta la voz de Edge o internet). ")
                     + ("Los estudiantes lo escuchan con el QR del proyector; " if J.mobile.get("server") else "") +
                     "el MP3 queda en Documentos, Jarvis, Podcasts, para compartirlo por WhatsApp.", "PODCAST")
        if getattr(J._tl, "capture", None) is not None:
            work()
        else:
            J.start_job("Grabando el podcast", work, "podcast")
        return True
    return False


def live_guide_start():
    guiaviva.configure(J.CONFIG_DIR)


__all__ = ['_COURSE_TAIL', '_GV_ASK', '_GV_CLOSE', '_GV_MAKE', '_PC_MAKE', '_g', '_lan', '_vq_course', 'gtok', 'guiaviva', 'guide_data', 'guide_enter',
           'guide_img', 'guide_lab', 'guide_page', 'guide_qr', 'guide_quiz', 'live_guide_start', 'live_guide_voice', 'make_guide', 'podcast_mp3',
           'podcast_page', 'podcast_qr', 'synth_podcast']
