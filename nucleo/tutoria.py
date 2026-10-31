"""10.7: tutor personal de cada estudiante. Práctica a la medida desde el celular (QR), con pistas que no dan la respuesta,
niveles que se ajustan solos, avance visible para el docente y nota de práctica (Hacer) con tu aprobación.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import html
import random
import re
import secrets
import threading
import time

import aula
import banco
import diarioclase
import examenes
import practica
import saber
import seguimiento
from nucleo import J

ps = {"code": "", "curso": "", "abierta": 0.0, "tokens": {}}   # tokens: {token: {"est", "actual": ejercicio, "intentos", "chat"}}
_gen_lock = threading.Lock()


# ============================================================================ QUÉ PRACTICA CADA UNO
def focus_for(curso, est):
    """Los temas que más le cuestan: lo que falló con hoja, su competencia Saber más floja, sus notas bajas o el tema de clase."""
    out, seen = [], set()

    def add(tema, detalle=""):
        k = J.normalize(tema)[:60]
        if tema and k not in seen:
            seen.add(k)
            out.append({"tema": tema[:80], "detalle": detalle[:200]})
    exs = sorted((e for e in examenes.data["examenes"].values() if e["curso"] == curso and e["resultados"]), key=lambda e: e["creado"])[-3:]
    for ex in reversed(exs):
        for r in ex["resultados"].values():
            if r["nombre"] != est:
                continue
            bad = [i for i, x in enumerate(r["detalle"]) if x is not True and i < len(ex["preguntas"])]
            if bad:
                q = ex["preguntas"][bad[0]]
                add(ex.get("tema") or ex["titulo"], q.get("enunciado", ""))
    prof = saber.profile(curso).get(est) if curso in saber.data["cursos"] else None
    if prof:
        w = saber.weakest(prof)
        if w and (prof.get(w) or 100) < 70:
            add(f"Saber: {w}")
    for n in sorted(seguimiento.data.get(curso, {}).get(est, []), key=lambda n: n.get("fecha", ""))[-8:]:
        if n.get("nota") is not None and n["nota"] < 3.5:
            add(n["actividad"])
    for e in diarioclase.entries(curso.split(" · ")[0])[-2:][::-1]:
        add(e["tema"])
    if not out:
        add("repaso general del grado")
    return out[:4]


def _grade_label(curso):
    g = aula.grade_of(curso)
    return f"{g}°" if g else "bachillerato"


def _subject(curso):
    _, s = curso.partition(" · ")[::2]
    if s:
        return s
    subs = J.subjects_for(curso)
    return subs[0] if len(subs) == 1 else "Matemáticas"


def next_exercise(curso, est, tok):
    """El siguiente ejercicio para ese estudiante (genera más si hace falta)."""
    f = practica.pick_topic(curso, est, focus_for(curso, est))
    tema, detalle = f["tema"], f["detalle"]
    nivel = practica.level(curso, est, tema)
    key = (curso, tema, nivel)
    seen = tok.setdefault("vistos", set())
    lst = [e for e in practica.pool.get(key, []) if e["id"] not in seen]
    if not lst:
        with _gen_lock:
            lst = [e for e in practica.pool.get(key, []) if e["id"] not in seen]
            if not lst:
                new = []
                if J.state.get("ai") == "ok":
                    try:
                        raw = J.ai_chat([{"role": "user", "content": practica.exercise_prompt(tema.replace("Saber: ", "competencia Saber "), detalle, nivel,
                                                                                                _grade_label(curso), _subject(curso))}],
                                        json_mode=True, max_tokens=5000)
                        new = practica.clean_exercises(J._extract_json(raw), tema, nivel)
                    except Exception as e:
                        J.log_terminal(f"Tutor personal: {getattr(e, 'why', e)}", "AVISO")
                if not new:
                    new = practica.from_bank(banco.search(tema, "", 6), tema, nivel)
                practica.pool.setdefault(key, []).extend(new)
                del practica.pool[key][:-60]
                lst = [e for e in practica.pool.get(key, []) if e["id"] not in seen]
    if not lst:
        return None
    e = random.choice(lst) if len(lst) > 1 else lst[0]
    seen.add(e["id"])
    tok.update(actual=e, intentos=0)
    return e


# ============================================================================ PÁGINAS DEL CELULAR
def _ok_code(code):
    return bool(ps["code"]) and secrets.compare_digest(str(code), ps["code"])


def _tok(code, k):
    if not _ok_code(code):
        return None
    return ps["tokens"].get(str(k or ""))


@J.mobile_app.route("/p/<code>", methods=["GET"])
def practice_page(code):
    from flask import abort, render_template
    if not _ok_code(code):
        abort(404)
    return render_template("practica.html", code=code)


@J.mobile_app.route("/p/<code>/lista", methods=["GET"])
def practice_list(code):
    from flask import abort
    if not _ok_code(code):
        abort(404)
    return {"curso": ps["curso"].replace(" · ", " – "), "nombres": list(aula.students(ps["curso"]))}


@J.mobile_app.route("/p/<code>/entrar", methods=["POST"])
def practice_enter(code):
    from flask import abort, request
    if not _ok_code(code):
        abort(404)
    d = request.get_json(silent=True) or {}
    est = str(d.get("nombre") or "")
    if est not in aula.students(ps["curso"]):
        return {"ok": False, "msg": "Escoge tu nombre de la lista."}
    ok, msg = practica.check_pin(ps["curso"], est, d.get("pin"))
    if not ok:
        return {"ok": False, "msg": msg}
    k = secrets.token_urlsafe(12)
    ps["tokens"][k] = {"est": est, "chat": 0, "t": time.time()}
    s = practica.student(ps["curso"], est)
    return {"ok": True, "k": k, "msg": msg, "nombre": est.split()[0], "ej": s["ej"],
            "temas": [f["tema"] for f in focus_for(ps["curso"], est)]}


def _public(e, tok):
    return {"id": e["id"], "tema": e["tema"].replace("Saber: ", "Saber · "), "nivel": e["nivel"], "enunciado": e["enunciado"], "opciones": e["opciones"],
            "hecho": practica.student(ps["curso"], tok["est"])["ej"]}


@J.mobile_app.route("/p/<code>/siguiente", methods=["POST"])
def practice_next(code):
    from flask import request
    tok = _tok(code, (request.get_json(silent=True) or {}).get("k"))
    if not tok:
        return {"ok": False, "msg": "Vuelve a entrar con tu nombre y PIN."}
    e = next_exercise(ps["curso"], tok["est"], tok)
    if not e:
        return {"ok": False, "msg": "No tengo ejercicios ahora mismo. Inténtalo en un momento."}
    return {"ok": True, **_public(e, tok)}


@J.mobile_app.route("/p/<code>/responder", methods=["POST"])
def practice_answer(code):
    from flask import request
    d = request.get_json(silent=True) or {}
    tok = _tok(code, d.get("k"))
    if not tok or not tok.get("actual") or tok["actual"]["id"] != d.get("id"):
        return {"ok": False, "msg": "Ese ejercicio ya no está activo."}
    e = tok["actual"]
    try:
        op = int(d.get("opcion"))
    except (TypeError, ValueError):
        return {"ok": False, "msg": "Escoge una opción."}
    tok["intentos"] += 1
    if op == e["respuesta"]:
        nivel = practica.record(ps["curso"], tok["est"], e["tema"], tok["intentos"] == 1, tok["intentos"])
        tok["actual"] = None
        return {"ok": True, "correcto": True, "msg": "¡Muy bien!" if tok["intentos"] == 1 else "¡Eso es! Lo lograste.",
                "explicacion": e["explicacion"] if tok["intentos"] > 1 else "", "nivel": nivel}
    if tok["intentos"] <= len(e["pistas"]):
        return {"ok": True, "correcto": False, "pista": e["pistas"][tok["intentos"] - 1], "msg": "Casi. Mira esta pista e inténtalo otra vez."}
    nivel = practica.record(ps["curso"], tok["est"], e["tema"], False, tok["intentos"] + 1)
    tok["actual"] = None
    return {"ok": True, "correcto": False, "fin": True, "msg": "Veamos cómo se resuelve:", "explicacion": e["explicacion"],
            "respuesta": e["opciones"][e["respuesta"]], "nivel": nivel}


@J.mobile_app.route("/p/<code>/preguntar", methods=["POST"])
def practice_ask(code):
    from flask import request
    d = request.get_json(silent=True) or {}
    tok = _tok(code, d.get("k"))
    if not tok:
        return {"ok": False, "msg": "Vuelve a entrar con tu nombre y PIN."}
    q = str(d.get("texto") or "").strip()[:300]
    if not q:
        return {"ok": False, "msg": "Escribe tu pregunta."}
    if tok["chat"] >= 25:
        return {"ok": False, "msg": "Ya hiciste muchas preguntas en esta sesión: pregúntale a tu profe."}
    if J.state.get("ai") != "ok":
        return {"ok": False, "msg": "El tutor no está disponible ahora."}
    tok["chat"] += 1
    e = tok.get("actual") or {}
    sys = practica.TUTOR_CHAT.format(grado=_grade_label(ps["curso"]), asignatura=_subject(ps["curso"]), ejercicio=e.get("enunciado", "(práctica)"))
    try:
        ans = J.ai_chat([{"role": "user", "content": f"{sys}\n\nPregunta del estudiante: {q}"}], max_tokens=200).strip()
    except Exception:
        return {"ok": False, "msg": "No pude responder ahora. Inténtalo otra vez."}
    nans = J.normalize(ans)
    right = J.normalize(e["opciones"][e["respuesta"]]) if e.get("opciones") else ""
    if re.search(r"\b(?:respuesta|opcion)\s+(?:correcta\s+)?(?:es\s+)?(?:la\s+)?[a-d]\b|\bes la (?:opcion )?[a-d]\b", nans) or \
            (right and len(right) > 2 and re.search(rf"\b(?:respuesta|resultado) (?:correct[ao] )?es {re.escape(right)}\b", nans)):
        ans = "Piénsalo paso a paso: ¿qué te pide exactamente el enunciado y qué dato usarías primero?"
    return {"ok": True, "msg": ans}


# ============================================================================ DOCENTE
_TU_OPEN = re.compile(r"\b(?:activa|abre|inicia|empieza|lanza|habilita)\s+(?:la\s+|el\s+)?(?:practica(?: personal)?|tutor personal|tutor individual)\b")
_TU_CLOSE = re.compile(r"\b(?:cierra|termina|desactiva|apaga)\s+(?:la\s+|el\s+)?(?:practica|tutor personal)\b")
_TU_ASK = re.compile(r"\b(?:quien|quienes) (?:ha |han )?practicad[oa]\b|\bcomo va la practica\b|\bavance (?:de|en) la practica\b")
_TU_GRADE = re.compile(r"\banota(?:r)? (?:la |las notas de la )?practica\b")
_TU_PIN = re.compile(r"\b(?:borra|reinicia|resetea|quita)\s+(?:el\s+)?pin\s+de\s+(.+)$")


def practice_url():
    return f"http://{J.lan_ip()}:{J.settings['mobile_port']}/p/{ps['code']}"


def practice_voice(text, t):
    if _TU_OPEN.search(t):
        if J._need_lan():
            return True
        cm = J._COURSE_IN.search(t)
        course = J._resolve_course(cm.group(1) if cm else "")
        if not course:
            J.reply("¿Para qué curso? Por ejemplo: «activa la práctica de 7A».", "TUTOR")
            return True
        course = J.grade_key(course, t, ask=False) or course
        if not aula.students(course):
            J.reply(f"Necesito la lista de {course} para que cada estudiante escoja su nombre.", "TUTOR")
            return True
        ps.update(code=secrets.token_urlsafe(6), curso=course, abierta=time.time(), tokens={})
        J._open_projector()
        J.socketio.emit("ticket", {"open": True, "url": practice_url(), "qr": "/practica-qr.png", "tipo": "practica",
                                   "tema": f"Práctica personal · {course}", "n": 0})
        J.reply(f"Práctica personal abierta para {course}: en el proyector está el código QR. Cada estudiante escoge su nombre, crea un PIN de 4 "
                "números la primera vez y practica lo que más le cuesta, con pistas. Cuando quieras: «¿quién ha practicado?» o «cierra la práctica».",
                "TUTOR")
        return True
    if _TU_CLOSE.search(t):
        if not ps["code"]:
            return False
        c = ps["curso"]
        ps.update(code="", tokens={})
        J.socketio.emit("ticket", {"open": False, "results": None})
        J.reply(f"Cerré la práctica de {c}. " + J.practice_spoken(c), "TUTOR")
        return True
    if _TU_ASK.search(t):
        cm = J._COURSE_IN.search(t)
        c = J._resolve_course(cm.group(1)) if cm else (ps["curso"] or aula.data.get("activo", ""))
        J.reply(J.practice_spoken(c), "TUTOR")
        return True
    if _TU_GRADE.search(t):
        cm = J._COURSE_IN.search(t)
        c = J._resolve_course(cm.group(1)) if cm else ps["curso"]
        rows = practica.summary(c) if c else []
        if not rows:
            J.reply("Nadie ha practicado todavía en ese curso.", "TUTOR")
            return True
        meta = J.settings["practice_goal"]
        notas = [(r["nombre"], practica.nota(practica.data["cursos"][c][r["nombre"]], meta)) for r in rows if r["ej"]]
        J.request_approval("notas", f"Anotar la práctica personal de {c} ({len(notas)} estudiantes, en Hacer)",
                           "; ".join(f"{n}: {str(v).replace('.', ',')}" for n, v in notas[:40]) + f". Meta: {meta} puntos.",
                           on_ok=lambda: (
                               [seguimiento.add(c, n, "Práctica con el tutor", v, origen="practica", dim="hacer") for n, v in notas],
                               J.reply(f"Anoté la práctica de {len(notas)} estudiantes en Hacer.", "TUTOR")),
                           on_no=lambda: None, ttl=24 * 3600,
                           say=f"¿Anoto la nota de práctica de {len(notas)} estudiantes de {c} en Hacer? (Meta: {meta} puntos.) Di «sí» o «no».")
        return True
    m = _TU_PIN.search(t)
    if m:
        course, name = J._student_or_ask(m.group(1), "TUTOR")
        if name:
            keys = [k for k in practica.data["cursos"] if k.split(" · ")[0] == course.split(" · ")[0]] or [course]
            done = any(practica.reset_pin(k, name) for k in keys)
            J.reply(f"Listo, {name} puede crear un PIN nuevo." if done else f"{name} todavía no tenía PIN.", "TUTOR")
        return True
    return False


def practice_spoken(c):
    rows = [r for r in practica.summary(c) if r["ej"]] if c else []
    if not rows:
        return f"Nadie ha practicado todavía en {c or 'ese curso'}."
    tot = sum(r["ej"] for r in rows)
    top = ", ".join(f"{r['nombre']} ({r['ej']})" for r in rows[:3])
    names = set(aula.students(c))
    falta = [n for n in names if n not in {r["nombre"] for r in rows}]
    return (f"En {c} practicaron {len(rows)} estudiantes, {tot} ejercicios en total. Los que más: {top}." +
            (f" Aún no han entrado {len(falta)}." if falta else ""))


@J.app.route("/practica-qr.png")
def practice_qr():
    import io
    from flask import Response, abort
    if not ps["code"]:
        abort(404)
    import qrcode
    buf = io.BytesIO()
    qrcode.make(practice_url(), box_size=10, border=2).save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


@J.app.route("/practica/<path:curso>")
def practice_board(curso):
    rows = practica.summary(curso)
    def row(r):
        temas = html.escape("; ".join("%s (nivel %s)" % (k, v["nivel"]) for k, v in r["temas"].items())[:200])
        pct = "—" if r["pct"] is None else "%s %%" % r["pct"]
        return "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (html.escape(r["nombre"]), r["ej"], pct, r["dias"], temas)
    trs = "".join(row(r) for r in rows)
    return (f"<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'><title>Práctica · {html.escape(curso)}</title><style>"
            "body{margin:0;padding:20px;background:#03060c;color:#e6f6ff;font-family:system-ui,sans-serif}h1{color:#2ee6ff;font-size:20px}"
            "table{border-collapse:collapse;width:100%;max-width:960px;font-size:14px}td,th{padding:7px 8px;border-bottom:1px solid #1d3344;text-align:left}"
            f"th{{color:#7d95ab}}</style></head><body><h1>Práctica personal · {html.escape(curso)}</h1><table><tr><th>Estudiante</th><th>Ejercicios</th>"
            f"<th>A la primera</th><th>Días</th><th>Temas</th></tr>{trs}</table></body></html>")


def practice_start():
    practica.configure(J.CONFIG_DIR)


__all__ = ['_TU_ASK', '_TU_CLOSE', '_TU_GRADE', '_TU_OPEN', '_TU_PIN', '_grade_label', '_ok_code', '_public', '_subject', '_tok', 'focus_for',
           'next_exercise', 'practica', 'practice_answer', 'practice_ask', 'practice_board', 'practice_enter', 'practice_list', 'practice_next',
           'practice_page', 'practice_qr', 'practice_spoken', 'practice_start', 'practice_url', 'practice_voice', 'ps']
