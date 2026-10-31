"""9.6: clase en vivo conducida con el proyector, ticket de salida y semáforo con el celular de los estudiantes, y el
banco de actividades que aprende de los resultados.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import io
import re
import threading
import time

import aula
import clasevivo
import diarioclase
import horario
import ticket
from nucleo import J


# ============================================================================ CLASE EN VIVO
live_class = {"on": False, "plan": None, "steps": [], "i": 0, "end": 0.0, "tema": "", "curso": "", "hook": ""}
_LC_START = re.compile(r"^(?:jarvis\s+)?(?:empieza|empecemos|inicia|iniciemos|arranca|comienza|comencemos|vamos con)\s+(?:la\s+)?clase"
                       r"(?:\s+(?:de|sobre)\s+(.+?))?(?:\s+(?:en|con|para)\s+((?:\d{1,2}\s?[a-z]?|sexto|septimo|octavo|noveno|decimo|once)(?:\s+[a-z])?))?$")
_LC_NEXT = re.compile(r"^(?:siguiente momento|pasemos al siguiente momento|sigue|siguiente actividad|pasa al siguiente momento|continua)$")
_LC_MORE = re.compile(r"^(?:dame|danos|agrega|pon)\s+(\d{1,2}|un|una|dos|tres|cinco|diez)\s+minutos?\s+mas$")
_LC_END = re.compile(r"^(?:termina|terminemos|cierra|acaba|finaliza|fin de)\s+(?:la\s+)?clase$")
_NUM = {"un": 1, "una": 1, "dos": 2, "tres": 3, "cinco": 5, "diez": 10}


def class_emit():
    lc = live_class
    if not lc["on"]:
        J.socketio.emit("live_class", {"on": False})
        return
    st = lc["steps"][lc["i"]]
    J.socketio.emit("live_class", {"on": True, "tema": lc["tema"], "curso": lc["curso"], "i": lc["i"], "n": len(lc["steps"]),
                                   "nombre": st["nombre"], "actividades": st["actividades"][:900], "min": st["min"],
                                   "left": max(0, round(lc["end"] - time.time())), "hook": lc["hook"] if lc["i"] == 0 else "",
                                   "pasos": [s["nombre"] for s in lc["steps"]]})


def _start_class(plan, tema, curso):
    lc = live_class
    lc.update(on=True, plan=plan, steps=clasevivo.steps(plan), i=0, tema=tema or plan.get("tema", ""), curso=curso,
              hook=clasevivo.hook_question(plan))
    lc["end"] = time.time() + lc["steps"][0]["min"] * 60
    J._open_projector()
    class_emit()
    J.reply(f"¡Empezamos la clase de {lc['tema']}! {len(lc['steps'])} momentos: " + ", ".join(s["nombre"] for s in lc["steps"]) +
            f". En pantalla está la pregunta de enganche: {lc['hook']} Di «siguiente momento» para avanzar.", "CLASE EN VIVO")


def live_class_voice(text, t):
    lc = live_class
    if lc["on"]:
        if _LC_NEXT.match(t):
            if lc["i"] + 1 >= len(lc["steps"]):
                return J.live_class_voice(text, "termina la clase")
            lc["i"] += 1
            lc["end"] = time.time() + lc["steps"][lc["i"]]["min"] * 60
            class_emit()
            st = lc["steps"][lc["i"]]
            J.reply(f"{st['nombre']}, {st['min']} minutos.", "CLASE EN VIVO")
            return True
        m = _LC_MORE.match(t)
        if m:
            n = _NUM.get(m.group(1)) or int(m.group(1))
            lc["end"] = max(lc["end"], time.time()) + n * 60
            class_emit()
            J.reply(f"Listo, {n} minutos más.", "CLASE EN VIVO")
            return True
        if _LC_END.match(t):
            lc["on"] = False
            class_emit()
            if lc["curso"]:
                diarioclase.add(lc["curso"], lc["tema"])
            J.reply(f"Clase terminada. Anoté «{lc['tema']}» en el diario de clase" + (f" de {lc['curso']}" if lc["curso"] else "") +
                    ". ¿Lanzo el ticket de salida? Di «lanza el ticket de salida» o «semáforo de comprensión».", "CLASE EN VIVO")
            return True
    m = _LC_START.match(t)
    if not m:
        return False
    tema = (m.group(1) or "").strip()
    nc = horario.now_class()
    curso = aula.find_course(m.group(2)) if m.group(2) else (aula.find_course(nc["curso"]) if nc and nc["curso"] else aula.data.get("activo", ""))
    if not tema and nc:
        tema = nc["materia"]
    if not tema:
        J.reply("¿De qué tema es la clase? Por ejemplo: «empieza la clase de fracciones».", "CLASE EN VIVO")
        return True
    plan = clasevivo.find_plan(tema)
    if plan:
        _start_class(plan, tema, curso or plan.get("curso", ""))
        return True
    if J.state.get("ai") != "ok":
        J.reply(f"No tengo un plan de clase de {tema} y la IA no está conectada para prepararlo.", "CLASE EN VIVO")
        return True
    J.reply(f"No tengo un plan de {tema}: lo preparo en un momento y empezamos…", "CLASE EN VIVO")

    def work():
        try:
            prompt = aula.build_prompt("plan", f"plan de clase de {tema}", None, curso, tema) + J.lessons_ctx() + clasevivo.worked_ctx(tema)
            m2 = aula.validate("plan", J._extract_json(J.ai_chat([{"role": "user", "content": prompt}], json_mode=True, max_tokens=4000)))
        except Exception as e:
            J.notify(f"No pude preparar el plan: {getattr(e, 'why', e)}", "CLASE EN VIVO")
            return
        clasevivo.remember_plan(m2, curso)
        _start_class(m2, tema, curso)
    J.start_job(f"Preparando la clase de {tema}", work, "clase-vivo")
    return True


def _class_worker():
    warned = {}
    while True:
        time.sleep(5)
        lc = live_class
        if lc["on"]:
            left = lc["end"] - time.time()
            key = (lc["tema"], lc["i"])
            if 0 < left <= 60 and warned.get(key) != "1min":
                warned[key] = "1min"
                J.notice_add(f"Queda 1 minuto de «{lc['steps'][lc['i']]['nombre']}».", "aviso", "CLASE EN VIVO")
            elif left <= 0 and warned.get(key) != "fin":
                warned[key] = "fin"
                J.socketio.emit("live_class_time", {"i": lc["i"]})
                J.notice_add(f"Se acabó el tiempo de «{lc['steps'][lc['i']]['nombre']}». Di «siguiente momento».", "aviso", "CLASE EN VIVO")


@J.socketio.on("live_class_state")
def handle_live_class_state(data=None):
    class_emit()
    return {"on": live_class["on"]}


# ============================================================================ TICKET DE SALIDA Y SEMÁFORO
_TK_OPEN = re.compile(r"\b(?:lanza|abre|haz|inicia|pon)\s+(?:el|un)\s+ticket(?:\s+de\s+salida)?(?:\s+(?:de|sobre)\s+(.+))?$")
_TK_SEM = re.compile(r"\b(?:semaforo de comprension|haz el semaforo|lanza el semaforo|como les fue|abre el semaforo)\b")
_TK_CLOSE = re.compile(r"\b(?:cierra|termina|resultados del)\s+(?:el\s+)?(?:ticket|semaforo)\b")


def ticket_url():
    return f"http://{J.lan_ip()}:{J.settings['mobile_port']}/t/{ticket.state['code']}"


def _need_lan():
    if J.mobile.get("server"):
        return False
    J.reply("Para que los estudiantes respondan desde su celular, activa el «panel del celular» en Ajustes › Integraciones "
            "(los celulares deben estar en la misma red wifi que este computador).", "TICKET")
    return True


def ticket_voice(text, t):
    if _TK_CLOSE.search(t):
        if not ticket.state["open"]:
            J.reply("No hay ningún ticket abierto.", "TICKET")
            return True
        res = ticket.close()
        J.socketio.emit("ticket", {"open": False, "results": res})
        _learn_from(res)
        if res["curso"] and res["n"] and res["tipo"] == "semaforo" and res["semaforo"]:
            ent = diarioclase.entries(res["curso"])
            if ent:
                ent[-1]["nota"] = f"Semáforo: {res['semaforo']['verde']} % verde, {res['semaforo']['rojo']} % rojo"
                diarioclase.save()
        J.reply(ticket.spoken(res), "TICKET")
        return True
    sem = _TK_SEM.search(t)
    m = _TK_OPEN.search(t)
    if not (sem or m):
        return False
    if _need_lan():
        return True
    lc = live_class
    tema = ((m.group(1) if m else "") or lc["tema"] or "").strip()
    curso = lc["curso"] or aula.data.get("activo", "")
    if sem:
        ticket.open_ticket([dict(ticket.SEMAFORO)], "semaforo", tema, curso)
    else:
        quiz = (J.banco.build_quiz(tema, 2) if tema else None) or J.last_quiz["m"]
        qs = ticket.from_quiz(quiz, 2) if quiz else []
        if not qs:
            J.reply("No tengo preguntas para el ticket. Prepara un quiz del tema («haz un quiz de fracciones») o usa el «semáforo de comprensión».",
                    "TICKET")
            return True
        ticket.open_ticket(qs, "ticket", tema, curso)
    J._open_projector()
    J.socketio.emit("ticket", {"open": True, "url": ticket_url(), "tipo": ticket.state["tipo"], "tema": tema, "n": 0})
    J.reply(("Semáforo" if sem else "Ticket de salida") + " abierto: en el proyector está el código QR para que respondan desde el "
            "celular. Cuando terminen, di «cierra el ticket».", "TICKET")
    return True


def _learn_from(res):
    """El banco de actividades aprende: guarda cómo le fue a la actividad de desarrollo de la clase en vivo."""
    lc = live_class
    if not (res["n"] and lc.get("plan") and lc["tema"]):
        return
    resultado = res["semaforo"]["verde"] if res["tipo"] == "semaforo" and res["semaforo"] else res["pct"]
    if resultado is None:
        return
    st = lc["steps"]
    dev = next((s for s in st if "desarrollo" in J.normalize(s["nombre"])), st[min(1, len(st) - 1)])
    clasevivo.record_outcome(lc["tema"], lc["curso"], dev["actividades"], resultado)


@J.mobile_app.route("/t/<code>", methods=["GET"])
def ticket_page(code):
    from flask import abort, render_template
    if not ticket.public(code):
        abort(404)
    return render_template("ticket.html", code=code)


@J.mobile_app.route("/t/<code>/datos", methods=["GET"])
def ticket_data(code):
    from flask import abort
    pub = ticket.public(code)
    if not pub:
        abort(404)
    return pub


@J.mobile_app.route("/t/<code>/enviar", methods=["POST"])
def ticket_submit(code):
    from flask import request
    d = request.get_json(silent=True) or {}
    ok, msg = ticket.submit(code, d.get("nombre", ""), d.get("respuestas") or [], request.remote_addr or "")
    if ok:
        try:
            J.socketio.emit("ticket", {"open": True, "url": ticket_url(), "tipo": ticket.state["tipo"], "tema": ticket.state["tema"],
                                       "n": len(ticket.state["respuestas"])})
        except Exception:
            pass
    return {"ok": ok, "msg": msg}


@J.app.route("/ticket-qr.png")
def ticket_qr():
    """El código QR del ticket abierto, para el proyector (solo en este equipo)."""
    from flask import Response, abort
    if not ticket.state["open"]:
        abort(404)
    try:
        import qrcode
        img = qrcode.make(ticket_url(), box_size=10, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})
    except Exception:
        abort(404)


@J.socketio.on("ticket_state")
def handle_ticket_state(data=None):
    if ticket.state["open"]:
        return {"open": True, "url": ticket_url(), "tipo": ticket.state["tipo"], "tema": ticket.state["tema"], "n": len(ticket.state["respuestas"])}
    return {"open": False}


# ============================================================================ BANCO DE ACTIVIDADES QUE APRENDE
_ACT_RE = re.compile(r"\bque actividades (?:me )?(?:funcionaron|han funcionado|sirvieron|dieron resultado)(?:\s+(?:en|de|con|para)\s+(.+))?$")


def activities_voice(text, t):
    m = _ACT_RE.search(t)
    if not m:
        return False
    tema = (m.group(1) or live_class["tema"] or "").strip()
    hits = clasevivo.worked(tema) if tema else sorted([a for a in clasevivo.data["actividades"] if (a["resultado"] or 0) >= 70],
                                                     key=lambda a: -a["resultado"])[:3]
    if not hits:
        J.reply("Aún no tengo resultados de actividades" + (f" de {tema}" if tema else "") + ". Se aprenden con el ticket de salida o el "
                "semáforo después de una clase en vivo.", "ACTIVIDADES")
    else:
        J.reply("Las que mejor funcionaron: " + "; ".join(f"{a['actividad'][:120]} ({a['resultado']} %, {a['tema']})" for a in hits) + ".",
                "ACTIVIDADES")
    return True


def live_class_start():
    clasevivo.configure(J.CONFIG_DIR)
    threading.Thread(target=J._class_worker, daemon=True, name="clase-en-vivo").start()


__all__ = [
    '_ACT_RE', '_LC_END', '_LC_MORE', '_LC_NEXT', '_LC_START', '_NUM', '_TK_CLOSE', '_TK_OPEN', '_TK_SEM', '_class_worker', '_learn_from',
    '_need_lan', '_start_class', 'activities_voice', 'class_emit', 'handle_live_class_state', 'handle_ticket_state', 'live_class',
    'live_class_start', 'live_class_voice', 'ticket_data', 'ticket_page', 'ticket_qr', 'ticket_submit', 'ticket_url', 'ticket_voice',
]
