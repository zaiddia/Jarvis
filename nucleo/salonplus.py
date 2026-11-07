"""12.12: en el salón, desde el celular de los estudiantes.

- Asistencia con QR que cambia cada 30 s: «toma asistencia con QR (de 9A)», «cierra la asistencia». Pasar el código por
  chat no sirve, y un celular marca a un solo estudiante. Los que no marcaron quedan como ausentes en el Aula.
- Modo examen: «modo examen 45 minutos», «termina el examen». Mientras dura, la práctica, los retos, las guías y los
  juegos se bloquean en los celulares, y el proyector muestra solo el reloj.
- Coevaluación: «abre la coevaluación de 9A», «cierra la coevaluación». Cada estudiante valora a su grupo (los últimos
  grupos que armaste) con 4 criterios de 1 a 5; el promedio queda como nota de «Ser».
- Laboratorio de Python: «abre el laboratorio de Python para 8A, el reto es: … , la salida debe ser: …», «¿cómo va el
  laboratorio?», «cierra el laboratorio». El código corre en el navegador del celular, no en tu equipo.
Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import io
import re
import secrets
import threading
import time

import aula
import practica
import salon
import seguimiento
from nucleo import J

asis = {"code": "", "secret": "", "curso": "", "start": 0.0, "tarde": 15, "tokens": {}}
exam = {"on": False, "until": 0.0, "curso": "", "titulo": "", "timer": None}
coev = {"code": "", "sid": "", "tokens": {}}
pylab = {"code": "", "sid": "", "tokens": {}}
last_groups = {"curso": "", "groups": [], "t": 0.0}
BLOCK_IN_EXAM = ("/p/", "/r/", "/g/", "/x/", "/lab", "/py/", "/a/", "/t/")


def _sp_lan(path):
    return f"http://{J.lan_ip()}:{J.settings['mobile_port']}{path}"


def _sp_course(t, default_active=True):
    cm = J._COURSE_IN.search(t)
    c = J._resolve_course(cm.group(1) if cm else "")
    return c or (aula.data.get("activo", "") if default_active else "")


def _qr_png(url):
    import qrcode
    from flask import Response
    buf = io.BytesIO()
    qrcode.make(url, box_size=10, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


def _login(curso, d, tokens):
    """Nombre de la lista + PIN de la práctica. → (ok, respuesta)."""
    est = str(d.get("nombre") or "")
    if est not in aula.students(curso):
        return False, {"ok": False, "msg": "Escoge tu nombre de la lista."}
    ok, msg = practica.check_pin(curso, est, d.get("pin"))
    if not ok:
        return False, {"ok": False, "msg": msg}
    k = secrets.token_urlsafe(12)
    tokens[k] = est
    return True, {"ok": True, "k": k, "nombre": est.split()[0], "msg": msg}


# ============================================================================ ASISTENCIA CON QR QUE CAMBIA
def asis_url():
    return _sp_lan(f"/as/{asis['code']}?k={salon.qr_token(asis['secret'], time.time())}")


@J.app.route("/asistencia-qr.png")
def asis_qr():
    from flask import abort
    if not asis["code"]:
        abort(404)
    return _qr_png(asis_url())                         # cada vez que el proyector la pide, un código nuevo


@J.mobile_app.route("/as/<code>", methods=["GET"])
def asis_page(code):
    from flask import abort, render_template, request
    if not asis["code"] or not secrets.compare_digest(code, asis["code"]):
        abort(404)
    fresh = salon.qr_valid(asis["secret"], request.args.get("k", ""), time.time())
    return render_template("salon_movil.html", modo="asistencia", code=code, k=request.args.get("k", "") if fresh else "", vencido=not fresh,
                           titulo="Marca tu llegada", curso=asis["curso"], nombres=list(aula.students(asis["curso"])))


@J.mobile_app.route("/as/<code>/marcar", methods=["POST"])
def asis_mark(code):
    from flask import abort, request
    if not asis["code"] or not secrets.compare_digest(code, asis["code"]):
        abort(404)
    d = request.get_json(silent=True) or {}
    if not salon.qr_valid(asis["secret"], d.get("k", ""), time.time()):
        return {"ok": False, "msg": "El código ya cambió. Vuelve a escanear el QR del tablero (cambia cada 30 segundos)."}
    ok, res = _login(asis["curso"], d, {})
    if not ok:
        return res
    est = str(d.get("nombre"))
    now = datetime.datetime.now()
    late = (time.time() - asis["start"]) / 60 > asis["tarde"]
    ok, msg = salon.attend(asis["curso"], est, now.date().isoformat(), now.strftime("%H:%M"), late, str(d.get("dev") or "")[:40])
    if ok:
        J.socketio.emit("ticket", {"open": True, "url": "", "qr": "/asistencia-qr.png", "tipo": "asistencia", "tema": f"Asistencia {asis['curso']}",
                                   "n": len(salon.attended(asis["curso"], now.date().isoformat()))})
    return {"ok": ok, "msg": msg}


def asis_close():
    curso = asis["curso"]
    today = datetime.date.today().isoformat()
    came = salon.attended(curso, today)
    names = list(aula.students(curso))
    absent = [n for n in names if n not in came]
    late = [n for n, v in came.items() if v.get("tarde")]
    with aula._lock:                                   # los que no marcaron: ausentes en el Aula (se corrigen allí si hace falta)
        aula.data["asistencia"].setdefault(curso, {})[today] = absent
    aula.save()
    asis.update(code="", secret="")
    J.socketio.emit("ticket", {"open": False})
    return curso, len(came), late, absent


# ============================================================================ MODO EXAMEN
def exam_start(minutes, curso="", titulo=""):
    if exam["timer"]:
        exam["timer"].cancel()
    exam.update(on=True, until=time.time() + minutes * 60, curso=curso, titulo=titulo or "Examen")
    t = threading.Timer(minutes * 60, exam_end, kwargs={"auto": True})
    t.daemon = True
    t.start()
    exam["timer"] = t
    J._open_projector()
    J.socketio.emit("exam", exam_state())


def exam_end(auto=False):
    if not exam["on"]:
        return False
    if exam["timer"] and not auto:
        exam["timer"].cancel()
    exam.update(on=False, until=0.0, timer=None)
    J.socketio.emit("exam", exam_state())
    if auto:
        J.notify("Se acabó el tiempo del examen. La práctica y los retos vuelven a estar abiertos en los celulares.", "EXAMEN")
    return True


def exam_state():
    return {"on": exam["on"], "left": max(0, int(exam["until"] - time.time())) if exam["on"] else 0, "titulo": exam["titulo"], "curso": exam["curso"]}


@J.socketio.on("exam_state")
def handle_exam_state(data=None):
    return exam_state()


@J.mobile_app.before_request
def _exam_guard():
    from flask import request
    if exam["on"] and request.path.startswith(BLOCK_IN_EXAM):
        mins = max(1, int((exam["until"] - time.time()) // 60) + 1)
        return (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                f"<body style='font-family:system-ui;background:#03060c;color:#e6f6ff;padding:28px;text-align:center'>"
                f"<h1 style='color:#ffb547'>Modo examen</h1><p>La práctica, los retos y las guías vuelven en unos {mins} minutos.</p>"
                f"<p style='color:#7d95ab'>Concéntrate en tu examen. ¡Éxitos!</p></body>"), 423


# ============================================================================ COEVALUACIÓN
def _coev_s():
    return salon.data["coev"].get(coev["sid"]) if coev["code"] else None


@J.app.route("/coev-qr.png")
def coev_qr():
    from flask import abort
    if not coev["code"]:
        abort(404)
    return _qr_png(_sp_lan(f"/co/{coev['code']}"))


@J.mobile_app.route("/co/<code>", methods=["GET"])
def coev_page(code):
    from flask import abort, render_template
    s = _coev_s()
    if not s or not secrets.compare_digest(code, coev["code"]):
        abort(404)
    return render_template("salon_movil.html", modo="coev", code=code, k="", vencido=False, titulo="Coevaluación", curso=s["curso"],
                           nombres=list(aula.students(s["curso"])))


@J.mobile_app.route("/co/<code>/entrar", methods=["POST"])
def coev_enter(code):
    from flask import abort, request
    s = _coev_s()
    if not s or not secrets.compare_digest(code, coev["code"]):
        abort(404)
    ok, res = _login(s["curso"], request.get_json(silent=True) or {}, coev["tokens"])
    if ok:
        est = coev["tokens"][res["k"]]
        peers = salon.coev_peers(s, est)
        res.update(companeros=peers or [n for n in aula.students(s["curso"]) if n != est], libre=not peers, criterios=s["criterios"],
                   hechos=list(s["resp"].get(est, {})))
    return res


@J.mobile_app.route("/co/<code>/enviar", methods=["POST"])
def coev_send(code):
    from flask import abort, request
    s = _coev_s()
    if not s or not secrets.compare_digest(code, coev["code"]):
        abort(404)
    d = request.get_json(silent=True) or {}
    est = coev["tokens"].get(str(d.get("k") or ""))
    if not est or s.get("cerrada"):
        return {"ok": False, "msg": "La coevaluación se cerró o tu sesión venció."}
    if salon.coev_peers(s, est) == [] and len(s["resp"].get(est, {})) >= 3 and str(d.get("evaluado")) not in s["resp"].get(est, {}):
        return {"ok": False, "msg": "Ya evaluaste a 3 compañeros."}
    ok, msg = salon.coev_submit(s, est, str(d.get("evaluado") or ""), d.get("notas") or [])
    if ok:
        J.socketio.emit("ticket", {"open": True, "url": _sp_lan(f"/co/{coev['code']}"), "qr": "/coev-qr.png", "tipo": "coev",
                                   "tema": f"Coevaluación {s['curso']}", "n": len(s["resp"])})
    return {"ok": ok, "msg": msg}


def coev_close():
    s = _coev_s()
    if not s:
        return None
    s["cerrada"] = True
    res = salon.coev_results(s)
    for est, r in res.items():
        if r["nota"] is not None:
            seguimiento.add(s["curso"], est, "Coevaluación", r["nota"], origen="coev", dim="ser")
    salon.save()
    coev.update(code="", sid="", tokens={})
    J.socketio.emit("ticket", {"open": False})
    return s, res


# ============================================================================ LABORATORIO DE PYTHON
def _pylab_s():
    return salon.data["lab"].get(pylab["sid"]) if pylab["code"] else None


@J.app.route("/lab-py-qr.png")
def pylab_qr():
    from flask import abort
    if not pylab["code"]:
        abort(404)
    return _qr_png(_sp_lan(f"/py/{pylab['code']}"))


@J.mobile_app.route("/py/<code>", methods=["GET"])
def pylab_page(code):
    from flask import abort, render_template
    s = _pylab_s()
    if not s or not secrets.compare_digest(code, pylab["code"]):
        abort(404)
    return render_template("salon_movil.html", modo="lab", code=code, k="", vencido=False, titulo="Laboratorio de Python", curso=s["curso"],
                           nombres=list(aula.students(s["curso"])), reto=s["reto"], hay_esperada=bool(s["esperada"]),
                           py_local=pyodide_ready())


@J.mobile_app.route("/py/<code>/entrar", methods=["POST"])
def pylab_enter(code):
    from flask import abort, request
    s = _pylab_s()
    if not s or not secrets.compare_digest(code, pylab["code"]):
        abort(404)
    ok, res = _login(s["curso"], request.get_json(silent=True) or {}, pylab["tokens"])
    if ok:
        prev = s["est"].get(pylab["tokens"][res["k"]], {})
        res.update(codigo=prev.get("codigo", ""), listo=prev.get("ok", False))
    return res


@J.mobile_app.route("/py/<code>/corrida", methods=["POST"])
def pylab_run(code):
    from flask import abort, request
    s = _pylab_s()
    if not s or not secrets.compare_digest(code, pylab["code"]):
        abort(404)
    d = request.get_json(silent=True) or {}
    est = pylab["tokens"].get(str(d.get("k") or ""))
    if not est or s.get("cerrado"):
        return {"ok": False, "msg": "El laboratorio se cerró o tu sesión venció."}
    e = salon.lab_record(s, est, d.get("codigo", ""), d.get("salida", ""), d.get("error", ""))
    J.socketio.emit("ticket", {"open": True, "url": _sp_lan(f"/py/{pylab['code']}"), "qr": "/lab-py-qr.png", "tipo": "lab",
                               "tema": f"Laboratorio de Python {s['curso']}", "n": sum(1 for x in s["est"].values() if x.get("ok"))})
    return {"ok": True, "listo": e["ok"], "hay_esperada": bool(s["esperada"])}


# ============================================================================ PYTHON PARA LOS CELULARES (servido por Jarvis)
PYODIDE_VER = "0.26.4"
PYODIDE_TGZ = f"https://registry.npmjs.org/pyodide/-/pyodide-{PYODIDE_VER}.tgz"
PYODIDE_SHA512 = "z2CHsjVlhhJi5tYBF0AYAfNEPo3zq/z+xOpFtk1tweJkRaTqU4UK/7pLvo8DBU2VDPH31vB3pSI+8fnoqrVrFg=="   # la huella publicada en npm
PYODIDE_FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json", "package.json")
py_job = {"busy": False}


def pyodide_dir():
    import os
    return os.path.join(J.CONFIG_DIR, "pyodide", PYODIDE_VER)


def pyodide_ready():
    import os
    return all(os.path.exists(os.path.join(pyodide_dir(), f)) for f in PYODIDE_FILES)


def install_pyodide():
    """Baja Python para el navegador (Pyodide, 6 MB, del registro oficial npm), comprueba su huella y lo deja en la carpeta de
    Jarvis: así el laboratorio funciona en el Wi-Fi del colegio aunque no tenga internet."""
    import base64
    import hashlib
    import os
    import tarfile
    import urllib.request
    req = urllib.request.Request(PYODIDE_TGZ, headers={"User-Agent": f"Jarvis/{J.VERSION}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        blob = r.read(40_000_000)
    if base64.b64encode(hashlib.sha512(blob).digest()).decode() != PYODIDE_SHA512:
        raise ValueError("la huella del paquete de Python no coincide con la publicada; no lo uso")
    dst = pyodide_dir()
    os.makedirs(dst, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as t:
        for m in t.getmembers():
            name = m.name.split("/", 1)[-1]
            if name in PYODIDE_FILES and m.isfile():
                with t.extractfile(m) as src, open(os.path.join(dst, name), "wb") as out:
                    out.write(src.read())
    return pyodide_ready()


def _ask_pyodide():
    if pyodide_ready() or py_job["busy"]:
        return

    def go():
        def work():
            py_job["busy"] = True
            try:
                ok = install_pyodide()
                J.notify("Listo: Python para el laboratorio quedó en tu equipo. Los celulares ya no necesitan internet, solo el Wi-Fi del colegio."
                         if ok else "No pude dejar Python en tu equipo; el laboratorio seguirá usando internet.", "LABORATORIO")
            except Exception as e:
                J.notify(f"No pude bajar Python para el laboratorio ({str(e)[:120]}); seguirá usando internet en los celulares.", "LABORATORIO")
            finally:
                py_job["busy"] = False
        J.start_job("Bajando Python para el laboratorio", work, "pyodide")
    J.request_approval("instalar", "Python para el laboratorio (6 MB)", "Pyodide, del registro oficial (npm), con su huella verificada. Se baja una "
                       "sola vez; después los celulares programan aunque el Wi-Fi del colegio no tenga internet.", on_ok=go, on_no=lambda: None, ttl=1800,
                       say=None, quiet=True)


@J.mobile_app.route("/pyodide/<path:name>", methods=["GET"])
def pyodide_file(name):
    import os
    from flask import abort, send_file
    if name not in PYODIDE_FILES or not pyodide_ready():
        abort(404)
    mime = {"wasm": "application/wasm", "js": "text/javascript", "zip": "application/zip", "json": "application/json"}[name.rsplit(".", 1)[-1]]
    return send_file(os.path.join(pyodide_dir(), name), mimetype=mime, max_age=86400)


# ============================================================================ ÓRDENES
_AS_OPEN = re.compile(r"\b(?:toma|tomar|pasa|pasar|abre|abrir|haz|activa)\s+(?:la\s+)?(?:asistencia|lista)\s+(?:con|por)\s+(?:el\s+)?(?:qr|codigo|celular)\b")
_AS_CLOSE = re.compile(r"\b(?:cierra|termina|cerrar|guarda)\s+(?:la\s+)?asistencia(?:\s+(?:con|por|del)\s+(?:el\s+)?(?:qr|codigo|celular))?\b")
_EX_ON = re.compile(r"\b(?:activa\s+(?:el\s+)?)?modo examen(?:\s+(?:de|por|durante)?\s*(\d{1,3})\s*(?:minutos?|min)?)?(?:\s+(?:de|para|en)\s+(.+))?$|"
                    r"\b(?:empieza|inicia|comienza)\s+(?:el\s+)?examen(?:\s+(?:de|por)\s+(\d{1,3})\s*(?:minutos?|min))?")
_EX_OFF = re.compile(r"\b(?:termina|acaba|finaliza|cierra|quita|desactiva|sal del)\s+(?:el\s+)?(?:modo\s+)?examen\b")
_CO_OPEN = re.compile(r"\b(?:abre|abrir|haz|hacer|inicia|lanza|activa)\s+(?:la\s+|una\s+)?coevaluacion\b")
_CO_CLOSE = re.compile(r"\b(?:cierra|termina|cerrar)\s+(?:la\s+)?coevaluacion\b")
_LB_OPEN = re.compile(r"\b(?:abre|abrir|inicia|lanza|activa)\s+(?:el\s+)?laboratorio\s+de\s+python\b")
_LB_HOW = re.compile(r"\bcomo va(?:n)?\s+(?:el\s+)?laboratorio\b|\bquien(?:es)?\s+(?:ya\s+)?(?:resolvio|resolvieron|termino|terminaron)\s+(?:el\s+)?(?:laboratorio|reto de python)\b")
_LB_CLOSE = re.compile(r"\b(?:cierra|termina|cerrar)\s+(?:el\s+)?laboratorio(?:\s+de\s+python)?\b")


def salon_voice(text, t):
    if _AS_OPEN.search(t):
        if J._need_lan():
            return True
        curso = _sp_course(t)
        if not aula.students(curso):
            J.reply(f"Necesito la lista de {curso or 'ese curso'} para que cada estudiante escoja su nombre.", "ASISTENCIA")
            return True
        m = re.search(r"\btarde\s+(?:despues\s+de|a\s+los)\s+(\d{1,2})\s*min", t)
        asis.update(code=secrets.token_urlsafe(6), secret=secrets.token_hex(16), curso=curso, start=time.time(), tarde=int(m.group(1)) if m else 15)
        J._open_projector()
        J.socketio.emit("ticket", {"open": True, "url": "", "qr": "/asistencia-qr.png", "tipo": "asistencia", "tema": f"Asistencia {curso}", "n": 0})
        J.reply(f"Asistencia de {curso} con QR: está en el proyector y cambia cada 30 segundos, así que no sirve mandarlo por chat. Cada uno marca "
                f"desde su celular con su nombre y su PIN. Después de {asis['tarde']} minutos queda como «tarde». Al terminar, di «cierra la asistencia».",
                "ASISTENCIA")
        return True
    if _AS_CLOSE.search(t) and asis["code"]:
        curso, n, late, absent = asis_close()
        J.reply(f"Asistencia de {curso} guardada en el Aula: llegaron {n}" + (f" ({len(late)} tarde: {', '.join(late[:6])})" if late else "") +
                (f"; faltan {len(absent)}: {', '.join(absent[:10])}" + ("…" if len(absent) > 10 else "") if absent else "; no falta nadie") + ".",
                "ASISTENCIA")
        return True
    if _EX_OFF.search(t):
        J.reply("Terminé el modo examen: la práctica y los retos vuelven a estar abiertos." if exam_end() else "No había un examen en curso.", "EXAMEN")
        return True
    m = _EX_ON.search(t)
    if m and (m.group(0).startswith(("modo", "activa")) or m.group(3)):
        mins = int(m.group(1) or m.group(3) or 60)
        curso = J._resolve_course(m.group(2)) if m.group(2) else aula.data.get("activo", "")
        exam_start(max(5, min(240, mins)), curso)
        J.reply(f"Modo examen por {mins} minutos" + (f" en {curso}" if curso else "") + ": en los celulares se bloquearon la práctica, los retos, las "
                "guías y los juegos, y el proyector muestra solo el reloj. Para terminar antes, di «termina el examen».", "EXAMEN")
        return True
    if _CO_OPEN.search(t):
        if J._need_lan():
            return True
        curso = _sp_course(t)
        if not aula.students(curso):
            J.reply(f"Necesito la lista de {curso or 'ese curso'}.", "COEVALUACIÓN")
            return True
        groups = last_groups["groups"] if last_groups["curso"] == curso and time.time() - last_groups["t"] < 12 * 3600 else []
        sid = secrets.token_hex(4)
        salon.coev_new(sid, curso, groups)
        coev.update(code=secrets.token_urlsafe(6), sid=sid, tokens={})
        J._open_projector()
        J.socketio.emit("ticket", {"open": True, "url": _sp_lan(f"/co/{coev['code']}"), "qr": "/coev-qr.png", "tipo": "coev", "tema": f"Coevaluación {curso}", "n": 0})
        J.reply(f"Coevaluación de {curso} abierta: el QR está en el proyector. " +
                ("Cada estudiante valora a los de su grupo" if groups else "No hay grupos armados hoy: cada estudiante escoge hasta 3 compañeros") +
                ", con 4 criterios de 1 a 5. Al terminar, di «cierra la coevaluación» y la nota queda en «Ser».", "COEVALUACIÓN")
        return True
    if _CO_CLOSE.search(t):
        r = coev_close()
        if not r:
            J.reply("No hay una coevaluación abierta.", "COEVALUACIÓN")
            return True
        s, res = r
        graded = {e: x for e, x in res.items() if x["nota"] is not None}
        J.reply(f"Coevaluación de {s['curso']} cerrada: {len(s['resp'])} estudiantes evaluaron. Quedó la nota en «Ser» para {len(graded)}"
                + (f"; {len(res) - len(graded)} tienen menos de 2 evaluaciones y no se calificaron" if len(res) > len(graded) else "") + ".", "COEVALUACIÓN")
        return True
    if _LB_OPEN.search(t):
        if J._need_lan():
            return True
        curso = _sp_course(t)
        if not aula.students(curso):
            J.reply(f"Necesito la lista de {curso or 'ese curso'}.", "LABORATORIO")
            return True
        rm = re.search(r"\b(?:el reto es|la tarea es|consigna|reto)\s*:?\s*(.+?)(?:[,.;]?\s*(?:y\s+)?la salida (?:debe ser|esperada es|es)\s*:?\s*(.+))?$", text, re.I)
        sid = secrets.token_hex(4)
        salon.lab_new(sid, curso, rm.group(1).strip() if rm else "", rm.group(2).strip() if rm and rm.group(2) else "")
        pylab.update(code=secrets.token_urlsafe(6), sid=sid, tokens={})
        J._open_projector()
        J.socketio.emit("ticket", {"open": True, "url": _sp_lan(f"/py/{pylab['code']}"), "qr": "/lab-py-qr.png", "tipo": "lab", "tema": f"Laboratorio de Python {curso}",
                                   "n": 0})
        local = pyodide_ready()
        J.reply(f"Laboratorio de Python de {curso} abierto: el QR está en el proyector. Escriben y prueban su código en el celular (corre en su "
                "navegador, no en tu equipo" + ("" if local else "; por ahora necesitan internet. Te pedí permiso para dejar Python en tu equipo y que "
                                               "funcione solo con el Wi-Fi del colegio") + "). Pregúntame «¿cómo va el laboratorio?».", "LABORATORIO")
        if not local:
            _ask_pyodide()
        return True
    if _LB_HOW.search(t):
        s = _pylab_s() or (max(salon.data["lab"].values(), key=lambda x: x["creado"]) if salon.data["lab"] else None)
        if not s:
            J.reply("No hay laboratorio abierto.", "LABORATORIO")
            return True
        x = salon.lab_summary(s, list(aula.students(s["curso"])))
        J.reply(f"Laboratorio de {s['curso']}: {len(x['listos'])} lo resolvieron, {len(x['trabajando'])} trabajando"
                + (f" (atascados con errores: {', '.join(x['atascados'][:5])})" if x["atascados"] else "") + f", {len(x['sin_empezar'])} sin empezar.", "LABORATORIO")
        return True
    if _LB_CLOSE.search(t):
        s = _pylab_s()
        if not s:
            J.reply("No hay laboratorio abierto.", "LABORATORIO")
            return True
        s["cerrado"] = True
        salon.save()
        x = salon.lab_summary(s, list(aula.students(s["curso"])))
        pylab.update(code="", sid="", tokens={})
        J.socketio.emit("ticket", {"open": False})
        J.reply(f"Cerré el laboratorio de {s['curso']}: {len(x['listos'])} lo resolvieron y {len(x['trabajando'])} lo intentaron. Su último código quedó "
                "guardado.", "LABORATORIO")
        return True
    return False


__all__ = ['BLOCK_IN_EXAM', '_AS_CLOSE', '_AS_OPEN', '_CO_CLOSE', '_CO_OPEN', '_EX_OFF', '_EX_ON', '_LB_CLOSE', '_LB_HOW', '_LB_OPEN', '_exam_guard',
           'asis', 'asis_close', 'asis_mark', 'asis_page', 'asis_qr', 'asis_url', 'coev', 'coev_close', 'coev_enter', 'coev_page', 'coev_qr', 'coev_send',
           'exam', 'exam_end', 'exam_start', 'exam_state', 'handle_exam_state', 'pylab', 'pylab_enter', 'pylab_page', 'pylab_qr', 'pylab_run', 'last_groups',
           'salon_voice', 'PYODIDE_FILES', 'PYODIDE_SHA512', 'PYODIDE_TGZ', 'PYODIDE_VER', '_ask_pyodide', 'install_pyodide', 'py_job', 'pyodide_dir',
           'pyodide_file', 'pyodide_ready']
