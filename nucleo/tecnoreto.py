"""11.1: entregas de programación (Tecnología e Informática) revisadas por la IA sin ejecutar el código, y el reto
matemático de la semana con puntos, insignias y ranking en el proyector.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import base64
import html
import os
import re
import secrets
import tempfile
import time
import urllib.parse

import aula
import entregas
import practica
import retos
import seguimiento
from nucleo import J

es = {"code": "", "tid": "", "tokens": {}}           # entregas abiertas: el código del QR y la tarea
rs = {"tokens": {}}                                   # reto: {token: (curso, est)}


def _tr_course(t):
    cm = J._COURSE_IN.search(t)
    return J._resolve_course(cm.group(1) if cm else "")


def _vision_json(prompt, img_path):
    cfg, err = J._vision_cfg()
    if not cfg:
        raise ValueError(err)
    if cfg["kind"] == "ollama":
        r = J.ollama.Client(host=cfg["ollama_host"], timeout=240).chat(model=J.settings["vision_model"].strip() or "moondream", format="json",
                                                                        messages=[{"role": "user", "content": prompt, "images": [img_path]}])
        raw = r["message"]["content"]
    else:
        J._need_key(cfg)
        raw = J._with_fallback(cfg, lambda c: J._cloud_chat(c, [{"role": "user", "content": prompt}], json_mode=True, image_path=img_path,
                                                            max_tokens=2000))
    return J._extract_json(raw)


# ============================================================================ ENTREGAS DE PROGRAMACIÓN
def review_code(task, lenguaje, codigo="", img_bytes=None):
    """Revisa una entrega con la IA (nunca la ejecuta). → revisión validada."""
    curso = task["curso"]
    grado = f"{aula.grade_of(curso)}°" if aula.grade_of(curso) else ""
    if img_bytes:
        fd, path = tempfile.mkstemp(suffix=".jpg")
        with os.fdopen(fd, "wb") as f:
            f.write(img_bytes)
        try:
            d = _vision_json(entregas.review_prompt(task["consigna"], lenguaje, "", grado, foto=True), path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
    else:
        raw = J.ai_chat([{"role": "user", "content": entregas.review_prompt(task["consigna"], lenguaje, codigo, grado) + J.lessons_ctx()}],
                        json_mode=True, max_tokens=1500)
        d = J._extract_json(raw)
    rev = entregas.validate(d)
    if entregas.leaks_solution(rev):                   # la pista no puede traer la solución hecha
        rev["pista"] = "Revisa paso a paso qué hace tu programa con un ejemplo pequeño, línea por línea, y compáralo con lo que pide la tarea."
        for e in rev["errores"]:
            e["que"] = re.sub(r"```.*?```", "", e["que"], flags=re.S)[:300]
    return rev


def _es_ok(code):
    return bool(es["code"]) and secrets.compare_digest(str(code), es["code"])


@J.mobile_app.route("/e/<code>", methods=["GET"])
def code_page(code):
    from flask import abort, render_template
    if not _es_ok(code):
        abort(404)
    return render_template("entrega.html", code=code)


@J.mobile_app.route("/e/<code>/lista", methods=["GET"])
def code_list(code):
    from flask import abort
    if not _es_ok(code):
        abort(404)
    t = entregas.data["tareas"].get(es["tid"]) or {}
    return {"curso": t.get("curso", "").replace(" · ", " – "), "consigna": t.get("consigna", ""), "nombres": list(aula.students(t.get("curso", ""))),
            "lenguajes": list(entregas.LANGS), "max": entregas.MAX_TRIES}


@J.mobile_app.route("/e/<code>/entrar", methods=["POST"])
def code_enter(code):
    from flask import abort, request
    if not _es_ok(code):
        abort(404)
    d = request.get_json(silent=True) or {}
    t = entregas.data["tareas"].get(es["tid"])
    est = str(d.get("nombre") or "")
    if not t or est not in aula.students(t["curso"]):
        return {"ok": False, "msg": "Escoge tu nombre de la lista."}
    ok, msg = practica.check_pin(t["curso"], est, d.get("pin"))
    if not ok:
        return {"ok": False, "msg": msg}
    k = secrets.token_urlsafe(12)
    es["tokens"][k] = est
    return {"ok": True, "k": k, "nombre": est.split()[0], "intentos": entregas.tries(t, est), "msg": msg}


@J.mobile_app.route("/e/<code>/enviar", methods=["POST"])
def code_submit(code):
    from flask import abort, request
    if not _es_ok(code):
        abort(404)
    d = request.get_json(silent=True) or {}
    est = es["tokens"].get(str(d.get("k") or ""))
    t = entregas.data["tareas"].get(es["tid"])
    if not est or not t or t["cerrada"]:
        return {"ok": False, "msg": "La entrega ya se cerró o tu sesión venció. Vuelve a entrar."}
    if entregas.tries(t, est) >= entregas.MAX_TRIES:
        return {"ok": False, "msg": f"Ya usaste tus {entregas.MAX_TRIES} intentos. Tu profe revisará la mejor."}
    lenguaje = str(d.get("lenguaje") or "Otro")[:40]
    codigo = str(d.get("codigo") or "")[:12000]
    img = None
    if d.get("foto"):
        m = re.match(r"data:image/(?:png|jpe?g|webp);base64,(.+)$", str(d["foto"]), re.S)
        if not m:
            return {"ok": False, "msg": "La foto no se pudo leer."}
        img = base64.b64decode(m.group(1))[:12_000_000]
    if not img and len(codigo.strip()) < 10:
        return {"ok": False, "msg": "Pega tu código o toma una foto de tu diagrama o programa."}
    rev = None
    if J.state.get("ai") == "ok":
        try:
            rev = J.review_code(t, lenguaje, codigo, img)
        except Exception as e:
            J.log_terminal(f"Revisión de programación: {getattr(e, 'why', e)}", "AVISO")
    entregas.add(t, est, "foto" if img else "codigo", lenguaje, codigo, rev)
    J.socketio.emit("ticket", {"open": True, "url": code_url(), "qr": "/entregas-qr.png", "tipo": "entregas",
                               "tema": t["consigna"][:80] or "Entregas de programación", "n": len(t["entregas"])})
    left = entregas.MAX_TRIES - entregas.tries(t, est)
    if not rev:
        return {"ok": True, "revisado": False, "msg": "¡Recibido! Tu profe lo revisará.", "quedan": left}
    return {"ok": True, "revisado": True, "funciona": rev["funciona"], "bien": rev["bien"], "errores": rev["errores"], "pista": rev["pista"],
            "quedan": left}


def code_url():
    return f"http://{J.lan_ip()}:{J.settings['mobile_port']}/e/{es['code']}"


@J.app.route("/entregas-qr.png")
def code_qr():
    import io
    from flask import Response, abort
    if not es["code"]:
        abort(404)
    import qrcode
    buf = io.BytesIO()
    qrcode.make(code_url(), box_size=10, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


_EN_OPEN = re.compile(r"\b(?:recibe|recibir|abre|activa|lanza|habilita|empieza)\s+(?:las\s+|los\s+)?(?:entregas?|programas|codigos)(?:\s+de\s+programacion)?\b")
_EN_CLOSE = re.compile(r"\b(?:cierra|termina|desactiva)\s+(?:las\s+|los\s+)?(?:entregas?|programas)\b")
_EN_ASK = re.compile(r"\bcomo van las entregas\b|\bquien(?:es)? (?:ha|han) entregado\b|\bquien(?:es)? falta(?:n)? por entregar\b")
_EN_GRADE = re.compile(r"\banota(?:r)? (?:las )?(?:notas de las )?entregas\b")


def _last_task():
    ts = sorted(entregas.data["tareas"].items(), key=lambda kv: kv[1]["creado"])
    return (ts[-1][0], ts[-1][1]) if ts else (None, None)


def code_spoken(task):
    names = aula.students(task["curso"])
    rows = entregas.summary(task, names)
    done = [r for r in rows if r["intentos"]]
    falta = [r["nombre"] for r in rows if not r["intentos"]]
    notas = [r["nota"] for r in done if r["nota"] is not None]
    t = f"Entregas de {task['curso']}: {len(done)} de {len(names)}"
    if notas:
        t += f", nota sugerida promedio {str(round(sum(notas) / len(notas), 1)).replace('.', ',')}; {sum(1 for r in done if r['funciona'])} funcionan"
    if falta and len(falta) <= 8:
        t += ". Faltan: " + ", ".join(falta)
    elif falta:
        t += f". Faltan {len(falta)}"
    return t + "."


def code_voice(text, t):
    if _EN_OPEN.search(t) and not re.search(r"\bhojas?\b", t):
        if J._need_lan():
            return True
        course = _tr_course(t)
        if not course:
            J.reply("¿Para qué curso? Por ejemplo: «recibe los programas de 8A, la tarea es: un programa que diga si un número es par».", "ENTREGAS")
            return True
        course = J.grade_key(course, "tecnologia " + t, ask=False) or course
        if not aula.students(course):
            J.reply(f"Necesito la lista de {course} para que cada estudiante escoja su nombre.", "ENTREGAS")
            return True
        cm = re.search(r"\b(?:la tarea es|consigna|el ejercicio es|sobre)\s*:?\s*(.+)$", text, re.I)
        tid = secrets.token_hex(4)
        task = entregas.new_task(tid, course, cm.group(1).strip() if cm else "")
        es.update(code=secrets.token_urlsafe(6), tid=tid, tokens={})
        J._open_projector()
        J.socketio.emit("ticket", {"open": True, "url": code_url(), "qr": "/entregas-qr.png", "tipo": "entregas",
                                   "tema": task["consigna"][:80] or "Entregas de programación", "n": 0})
        J.reply(f"Entregas abiertas para {course}" + (f" (tarea: {task['consigna'][:120]})" if task["consigna"] else "") +
                ": en el proyector está el QR. Cada estudiante entra con su nombre y su PIN, pega su código o le toma foto a su diagrama "
                f"o a su programa de Scratch, y recibe al momento qué está bien y una pista, sin la solución ({entregas.MAX_TRIES} intentos). "
                "Nunca ejecuto su código. Luego: «¿cómo van las entregas?», «cierra las entregas» y «anota las entregas».", "ENTREGAS")
        return True
    if _EN_CLOSE.search(t):
        tid, task = (es["tid"], entregas.data["tareas"].get(es["tid"])) if es["tid"] else _last_task()
        if not task:
            return False
        task["cerrada"] = True
        entregas.save()
        es.update(code="", tokens={})
        J.socketio.emit("ticket", {"open": False, "results": None})
        J.reply("Cerré las entregas. " + J.code_spoken(task), "ENTREGAS")
        return True
    if _EN_ASK.search(t):
        _tid, task = (es["tid"], entregas.data["tareas"].get(es["tid"])) if es["tid"] else _last_task()
        J.reply(J.code_spoken(task) if task else "No hay entregas abiertas. Dime «recibe los programas de 8A…».", "ENTREGAS")
        return True
    if _EN_GRADE.search(t):
        _tid, task = (es["tid"], entregas.data["tareas"].get(es["tid"])) if es["tid"] else _last_task()
        if not task:
            J.reply("No tengo entregas para anotar.", "ENTREGAS")
            return True
        notas = [(n, entregas.best(task, n)["rev"]["nota"]) for n in task["entregas"] if entregas.best(task, n) and entregas.best(task, n)["rev"]["nota"]]
        if not notas:
            J.reply("Aún no hay entregas revisadas con nota.", "ENTREGAS")
            return True
        act = ("Programa: " + task["consigna"][:50]) if task["consigna"] else "Entrega de programación"
        J.request_approval("notas", f"Anotar las entregas de {task['curso']} ({len(notas)} estudiantes, en Hacer)",
                           "; ".join(f"{n}: {str(v).replace('.', ',')}" for n, v in notas[:40]),
                           on_ok=lambda: ([seguimiento.add(task["curso"], n, act, v, origen="entregas", dim="hacer") for n, v in notas],
                                          J.reply(f"Anoté {len(notas)} notas de programación en Hacer.", "ENTREGAS")),
                           on_no=lambda: None, ttl=24 * 3600,
                           say=f"¿Anoto la nota sugerida de {len(notas)} entregas de {task['curso']} en Hacer? (Puedes corregir cualquiera después.) Di «sí» o «no».")
        return True
    return False


# ============================================================================ RETO DE LA SEMANA
def _rcourse(code):
    for c, r in retos.data["retos"].items():
        if r.get("code") and secrets.compare_digest(str(code), r["code"]) and not r["cerrado"]:
            return c
    return None


@J.mobile_app.route("/r/<code>", methods=["GET"])
def challenge_page(code):
    from flask import abort, render_template
    if not _rcourse(code):
        abort(404)
    return render_template("reto.html", code=code)


@J.mobile_app.route("/r/<code>/lista", methods=["GET"])
def challenge_list(code):
    from flask import abort
    c = _rcourse(code)
    if not c:
        abort(404)
    return {"curso": c.replace(" · ", " – "), "tema": retos.data["retos"][c]["tema"], "nombres": list(aula.students(c))}


@J.mobile_app.route("/r/<code>/entrar", methods=["POST"])
def challenge_enter(code):
    from flask import abort, request
    c = _rcourse(code)
    if not c:
        abort(404)
    d = request.get_json(silent=True) or {}
    est = str(d.get("nombre") or "")
    if est not in aula.students(c):
        return {"ok": False, "msg": "Escoge tu nombre de la lista."}
    ok, msg = practica.check_pin(c, est, d.get("pin"))
    if not ok:
        return {"ok": False, "msg": msg}
    k = secrets.token_urlsafe(12)
    rs["tokens"][k] = (c, est)
    return {"ok": True, "k": k, "nombre": est.split()[0], "msg": msg, **_challenge_state(c, est)}


def _challenge_state(c, est):
    r = retos.data["retos"][c]
    st = r["respuestas"].get(est, {})
    p = retos.data["puntos"].get(c, {}).get(est, {})
    return {"preguntas": [{"nivel": q["nivel"], "enunciado": q["enunciado"], "opciones": q["opciones"],
                           "estado": ("ok" if st.get(str(i), {}).get("ok") else "fin" if st.get(str(i), {}).get("intentos", 0) >= 2 else
                                      "uno" if st.get(str(i)) else ""),
                           "explicacion": q["explicacion"] if st.get(str(i), {}).get("ok") or st.get(str(i), {}).get("intentos", 0) >= 2 else ""}
                          for i, q in enumerate(r["preguntas"])],
            "total": p.get("total", 0), "insignias": [retos.BADGES[b] for b in p.get("insignias", []) if b in retos.BADGES]}


@J.mobile_app.route("/r/<code>/responder", methods=["POST"])
def challenge_answer(code):
    from flask import abort, request
    c = _rcourse(code)
    if not c:
        abort(404)
    d = request.get_json(silent=True) or {}
    who = rs["tokens"].get(str(d.get("k") or ""))
    if not who or who[0] != c:
        return {"ok": False, "msg": "Tu sesión venció. Vuelve a entrar."}
    try:
        q, op = int(d.get("q")), int(d.get("opcion"))
    except (TypeError, ValueError):
        return {"ok": False, "msg": "Respuesta no válida."}
    r = retos.answer(c, who[1], q, op)
    if r is None:
        return {"ok": False, "msg": "El reto ya se cerró."}
    first = retos.data["retos"][c]["orden"][:1] == [who[1]]
    msg = ("¡Correcto! 🎉" if r["ok"] else ("Esa no es. Tienes un intento más." if not r["fin"] else "Esa tampoco. Mira la explicación."))
    if r["ok"] and first and all(x["estado"] == "ok" for x in _challenge_state(c, who[1])["preguntas"]):
        msg += " ¡Eres el primero en resolver todo el reto! ⚡"
    return {"ok": True, "correcto": r["ok"], "fin": r["fin"], "msg": msg, **_challenge_state(c, who[1])}


def challenge_url(curso):
    return f"http://{J.lan_ip()}:{J.settings['mobile_port']}/r/{retos.data['retos'][curso]['code']}"


@J.app.route("/reto-qr.png")
def challenge_qr():
    import io
    from flask import Response, abort, request
    c = request.args.get("c") or next((k for k, r in retos.data["retos"].items() if not r["cerrado"]), None)
    if not c or c not in retos.data["retos"] or retos.data["retos"][c]["cerrado"]:
        abort(404)
    import qrcode
    buf = io.BytesIO()
    qrcode.make(challenge_url(c), box_size=10, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


@J.app.route("/ranking/<path:curso>")
def challenge_ranking(curso):
    rows = retos.ranking(curso, 15)
    r = retos.data["retos"].get(curso) or {}
    medal = ["🥇", "🥈", "🥉"]
    trs = "".join(f"<tr class='p{i}'><td class='pos'>{medal[i] if i < 3 else i + 1}</td><td>{html.escape(x['nombre'])}</td>"
                  f"<td class='pts'>{str(x['total']).replace('.', ',')}</td><td class='ins'>{html.escape(' '.join(x['insignias']))}</td></tr>"
                  for i, x in enumerate(rows))
    return (f"<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'><title>Ranking · {html.escape(curso)}</title><meta http-equiv='refresh' content='20'>"
            "<style>body{margin:0;padding:3vh 5vw;background:#03060c;color:#e6f6ff;font-family:system-ui,sans-serif}"
            "h1{color:#ffb547;font-size:5vh;margin:0 0 1vh}p{color:#7d95ab;font-size:2.4vh;margin:0 0 3vh}table{width:100%;border-collapse:collapse;font-size:3.4vh}"
            "td{padding:1.4vh 1vw;border-bottom:1px solid #1d3344}.pos{width:8vw;font-size:4vh}.pts{color:#3dff9a;font-weight:800;text-align:right;width:12vw}"
            ".ins{font-size:2.6vh;color:#c9d6e2}.p0 td{font-size:4.4vh}.p0 .pts{color:#ffd54a}</style></head><body>"
            f"<h1>🏆 Ranking del reto · {html.escape(curso.replace(' · ', ' – '))}</h1>"
            f"<p>{html.escape(('Reto de esta semana: ' + r.get('tema', '')) if r and not r.get('cerrado') else 'Puntos acumulados de los retos semanales')}</p>"
            f"<table>{trs or '<tr><td>Aún no hay puntos. ¡Participa en el reto!</td></tr>'}</table></body></html>")


_RT_OPEN = re.compile(r"\b(?:lanza|abre|activa|pon|publica|crea|haz)\s+(?:el\s+)?reto(?:\s+(?:matematico|de la semana|semanal))*\b")
_RT_CLOSE = re.compile(r"\b(?:cierra|termina|finaliza)\s+(?:el\s+)?reto\b")
_RT_RANK = re.compile(r"\b(?:muestra|ensena|abre|pon)\s+(?:el\s+)?ranking\b|\bcomo va el reto\b|\bquien va ganando(?: el reto)?\b")


def challenge_voice(text, t):
    if _RT_OPEN.search(t):
        if J._need_lan():
            return True
        course = _tr_course(t)
        if not course:
            J.reply("¿Para qué curso? Por ejemplo: «lanza el reto de la semana para 7A» (o «…sobre fracciones»).", "RETO")
            return True
        course = J.grade_key(course, "matematicas " + t, ask=False) or course
        if not aula.students(course):
            J.reply(f"Necesito la lista de {course} para el reto.", "RETO")
            return True
        tm = re.search(r"\bsobre\s+(.+?)(?:\s+(?:para|de|en)\s+(?:grado\s+)?\d.*)?$", t)
        tema = tm.group(1).strip() if tm else ""
        J.reply(f"Preparo el reto de la semana para {course}…", "RETO")

        def work():
            reto = None
            if J.state.get("ai") == "ok":
                try:
                    raw = J.ai_chat([{"role": "user", "content": retos.prompt(f"{aula.grade_of(course) or ''}°", tema) + J.lessons_ctx()}],
                                    json_mode=True, max_tokens=2500)
                    reto = retos.clean(J._extract_json(raw))
                except Exception as e:
                    J.log_terminal(f"Reto: {getattr(e, 'why', e)}", "AVISO")
            if not reto:
                qs = (J.banco.build_quiz(tema or "matemáticas", 3) or {}).get("preguntas") or []
                try:
                    reto = retos.clean({"tema": tema, "preguntas": [dict(q, respuesta=q.get("respuesta", "a")) for q in qs]})
                except ValueError:
                    J.notify("No pude preparar el reto (necesito la IA o preguntas en el banco sobre ese tema).", "RETO")
                    return
            retos.open_challenge(course, secrets.token_urlsafe(6), reto)
            J._open_projector()
            J.socketio.emit("ticket", {"open": True, "url": challenge_url(course), "qr": "/reto-qr.png?c=" + urllib.parse.quote(course),
                                       "tipo": "reto", "tema": f"Reto · {reto['tema'] or course}", "n": 0})
            J.notify(f"¡Listo el reto de la semana de {course}" + (f" ({reto['tema']})" if reto["tema"] else "") + "! Tres preguntas: bronce, plata y "
                     "oro. El QR está en el proyector (los estudiantes entran con su nombre y su PIN, en la wifi del colegio). Queda abierto "
                     "hasta que digas «cierra el reto»; «muestra el ranking» lo pone en grande.", "RETO")
        if getattr(J._tl, "capture", None) is not None:
            work()
        else:
            J.start_job("Preparando el reto", work, "reto")
        return True
    if _RT_CLOSE.search(t):
        cm = J._COURSE_IN.search(t)
        open_c = [c for c, r in retos.data["retos"].items() if not r["cerrado"]]
        course = J._resolve_course(cm.group(1)) if cm else (open_c[0] if len(open_c) == 1 else "")
        if course not in retos.data["retos"]:
            course = next((c for c in open_c if c.split(" · ")[0] == course.split(" · ")[0]), "")
        if not course:
            J.reply("¿Qué reto cierro? " + (f"Hay abiertos: {', '.join(open_c)}." if open_c else "No hay retos abiertos."), "RETO")
            return True
        res = retos.close(course)
        J.socketio.emit("ticket", {"open": False, "results": None})
        if not res:
            J.reply(f"Cerré el reto de {course}; nadie participó esta vez.", "RETO")
            return True
        top = "; ".join(f"{e} ({str(p).replace('.', ',')} pts" + (f", {' '.join(b)}" if b else "") + ")" for e, p, b in res[:3])
        J.reply(f"Cerré el reto de {course}: participaron {len(res)}. Esta semana: {top}. «Muestra el ranking de {course}» para verlo en grande.", "RETO")
        return True
    if _RT_RANK.search(t):
        cm = J._COURSE_IN.search(t)
        course = J._resolve_course(cm.group(1)) if cm else next(iter(sorted(retos.data["puntos"] or retos.data["retos"], key=aula.course_sort_key)), "")
        if course not in retos.data["puntos"] and course not in retos.data["retos"]:
            course = next((c for c in list(retos.data["puntos"]) + list(retos.data["retos"]) if c.split(" · ")[0] == course.split(" · ")[0]), course)
        rows = retos.ranking(course, 3)
        try:
            import webbrowser
            webbrowser.open(J.URL + "/ranking/" + urllib.parse.quote(course))
        except Exception:
            pass
        r = retos.data["retos"].get(course)
        live = f" En el reto abierto van {len(r['respuestas'])} participando." if r and not r["cerrado"] else ""
        J.reply((f"Ranking de {course}: " + "; ".join(f"{i + 1}. {x['nombre']} ({str(x['total']).replace('.', ',')})" for i, x in enumerate(rows)) + "."
                 if rows else f"Aún no hay puntos en {course}.") + live + " Lo abrí en grande para el proyector.", "RETO")
        return True
    return False


def tecno_start():
    entregas.configure(J.CONFIG_DIR)
    retos.configure(J.CONFIG_DIR)


__all__ = ['_EN_ASK', '_EN_CLOSE', '_EN_GRADE', '_EN_OPEN', '_RT_CLOSE', '_RT_OPEN', '_RT_RANK', '_challenge_state', '_tr_course', '_es_ok',
           '_last_task', '_rcourse', '_vision_json', 'challenge_answer', 'challenge_enter', 'challenge_list', 'challenge_page', 'challenge_qr',
           'challenge_ranking', 'challenge_url', 'challenge_voice', 'code_enter', 'code_list', 'code_page', 'code_qr', 'code_spoken', 'code_submit',
           'code_url', 'code_voice', 'entregas', 'es', 'retos', 'review_code', 'rs', 'tecno_start']
