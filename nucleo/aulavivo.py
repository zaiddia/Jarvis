"""8.8: planes de recuperación, diario de clase y quiz en vivo en el proyector.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import re
import threading
import time

import aula
import diarioclase
import horario
import informes
import recuperacion
import seguimiento
from nucleo import J


# ============================================================================ PLANES DE RECUPERACIÓN
_REC_RE = re.compile(r"\b(?:haz|hazme|genera|generame|prepara|preparame|arma|armame|crea|creame)\b.*\b(?:plan|planes)\s+de\s+"
                     r"(?:recuperacion|nivelacion|apoyo|mejoramiento)\b(?:\s+(?:de|del|para)\s+(.+))?$")


def recovery_voice(text, t):
    m = _REC_RE.search(t)
    if not m:
        return False
    target = re.sub(r"^(?:todo el curso|todos los de|los de|el curso|los estudiantes en riesgo de|los que van perdiendo en)\s+", "",
                    (m.group(1) or "").strip())
    whole = (not target) or aula.find_course(target) or (target.upper() in seguimiento.data and target.upper())
    if whole:
        course = J._resolve_course(target if target else "")
        names = sorted(set(aula.data.get("cursos", {}).get(course, [])) | set(seguimiento.data.get(course, {})))
        risk = seguimiento.at_risk(course, names, J._absences(course), J.settings["risk_grade"], J.settings["risk_absences"])
        names = [n for n, _ in risk]
        if not names:
            J.reply(f"En {course or 'ese curso'} nadie está en riesgo ahora mismo: no hacen falta planes de recuperación.", "RECUPERACIÓN")
            return True
    else:
        course, name = J._student_or_ask(target, "RECUPERACIÓN")
        if not name:
            return True
        names = [name]
    if J.Document is None:
        J.reply("No puedo crear documentos: falta python-docx.", "ERROR")
        return True
    J.reply(f"Preparo {'el plan' if len(names) == 1 else f'{len(names)} planes'} de recuperación de {course}…", "RECUPERACIÓN")
    capture = getattr(J._tl, "capture", None)

    def work():
        facts = [informes.facts(course, n, seguimiento.data.get(course, {}).get(n, []), J._absences(course).get(n, 0)) for n in names]
        plans = {}
        try:
            for start in range(0, len(facts), 6):
                part = facts[start:start + 6]
                raw = J.ai_chat([{"role": "user", "content": recuperacion.prompt(part, "", course, J.settings["recovery_days"])}],
                                json_mode=True, max_tokens=8000)
                plans.update({start + i: v for i, v in recuperacion.validate(J._extract_json(raw), len(part)).items()})
        except J.AIError as e:
            J.notify(J.ai_error_reply(e), "RECUPERACIÓN")
            return
        except (ValueError, TypeError) as e:
            J.notify(f"La IA no devolvió los planes bien: {e}", "RECUPERACIÓN")
            return
        items = [(facts[i], plans[i]) for i in sorted(plans)]
        if not items:
            J.notify("La IA no devolvió planes válidos. Inténtalo otra vez.", "RECUPERACIÓN")
            return
        path = recuperacion.build_docx(items, course, J.settings["output_dir"], J.Document, J.settings["aula_docente"],
                                       J.settings["aula_institucion"], J.settings["recovery_days"])
        J.generated_files.add(path)
        opened = J._open_doc(path)
        J.notify(f"Listo{'s' if len(items) > 1 else ''} {len(items)} plan{'es' if len(items) != 1 else ''} de recuperación de {course}, "
                 "cada uno con su carta para el acudiente" + (". Lo abrí para que lo revises." if opened else
                                                              ". Están en Documentos, Jarvis, Planes de recuperación."), "RECUPERACIÓN")
    if capture is not None:
        work()
    else:
        threading.Thread(target=work, daemon=True, name="recuperacion").start()
    return True


# ============================================================================ DIARIO DE CLASE
_D_ADD = re.compile(r"^(?:registra(?: que)?|anota(?: que)?|apunta(?: que)?)?\s*(?:hoy\s+)?(?:en|con)\s+(?:la clase de\s+)?(\S+(?:\s+[a-z]\b)?)\s+"
                    r"(?:hoy\s+)?(?:vimos|trabajamos|explique|repasamos|hicimos|dimos|estudiamos|empezamos|terminamos)\s+(.+)$")
_D_NOW = re.compile(r"^(?:hoy\s+)?(?:en (?:la )?clase\s+)?(?:vimos|trabajamos|explique|repasamos|dimos|estudiamos)\s+(.+?)(?:\s+en\s+(\S+(?:\s+[a-z]\b)?))?$")
_D_ASK = re.compile(r"\bque (?:vimos|hemos visto|trabajamos|he visto|hemos dado|he dado)\s+(?:en|con)\s+(.+?)$")
_D_MISS = re.compile(r"\bque (?:temas )?(?:me )?(?:faltan|falta|queda|quedan)\s+(?:por ver\s+)?(?:del periodo\s+)?(?:de la malla\s+)?(?:en|de|con)\s+(.+?)"
                     r"(?:\s+del periodo)?$|\bcomo voy con la malla (?:de|en)\s+(.+)$")
_D_EXP = re.compile(r"\b(?:exporta|exportame|saca|sacame|dame)\b.*\bregistro de clase\b(?:\s+(?:de|del)\s+(.+))?$")


def _course(spoken):
    if spoken:
        c = aula.find_course(spoken) or J._resolve_course(spoken)
        if c:
            return c
    x = horario.now_class()
    if x and x["curso"]:
        return aula.find_course(x["curso"]) or x["curso"]
    return J._resolve_course("")


def _orig_tail(text, t_tail):
    """El tema con las tildes y mayúsculas como lo dijiste."""
    words = text.strip().rstrip(".").split()
    n = len(t_tail.split())
    return " ".join(words[-n:]) if n and len(words) >= n else t_tail


def class_diary_voice(text, t):
    m = _D_ADD.match(t)
    course_txt, tema = (m.group(1), m.group(2)) if m else (None, None)
    if m and not (aula.find_course(course_txt) or re.match(r"^\d{1,2}[a-z]?$|^\d{1,2} [a-z]$", course_txt)):
        m = None
    if not m:
        m2 = _D_NOW.match(t)
        if m2 and (horario.now_class() or m2.group(2)):
            course_txt, tema = m2.group(2) or "", m2.group(1)
            m = m2
    if m:
        course = _course(course_txt)
        if not course:
            J.reply("¿En qué curso? Dilo así: «hoy en 7A vimos fracciones equivalentes».", "DIARIO DE CLASE")
            return True
        r = diarioclase.add(course, _orig_tail(text, tema))
        extra = ""
        pend = diarioclase.pending(course)
        if pend:
            extra = f" De la malla del periodo van {len(pend[0])} de {len(pend[0]) + len(pend[1])} temas."
        J.reply(f"Anotado en el diario de {course}: {r['tema']}.{extra}", "DIARIO DE CLASE")
        return True
    m = _D_MISS.search(t)
    if m:
        course = _course((m.group(1) or m.group(2) or "").strip())
        pend = diarioclase.pending(course)
        if pend is None:
            J.reply(f"No tengo la malla del periodo de {course}. Pídemela («haz la malla curricular de matemáticas de 7A») y la "
                    "comparo con tu diario de clase.", "DIARIO DE CLASE")
        elif not pend[1]:
            J.reply(f"En {course} ya viste todos los temas de la malla del periodo. 🎉", "DIARIO DE CLASE")
        else:
            J.reply(f"En {course} van {len(pend[0])} de {len(pend[0]) + len(pend[1])} temas de la malla. Faltan: "
                    + "; ".join(f"semana {s['semana']}, {s['tema']}" for s in pend[1][:8]) + ("…" if len(pend[1]) > 8 else "") + ".",
                    "DIARIO DE CLASE")
        return True
    m = _D_ASK.search(t)
    if m:
        course = _course(m.group(1))
        e = diarioclase.entries(course)
        if not e:
            J.reply(f"No tengo nada anotado del diario de {course}. Dime al final de la clase «hoy en {course} vimos…».", "DIARIO DE CLASE")
        else:
            J.reply(f"En {course}, lo último: " + "; ".join(f"{x['fecha'][8:10]}/{x['fecha'][5:7]} {x['tema']}" for x in e[-5:][::-1]) + ".",
                    "DIARIO DE CLASE")
        return True
    m = _D_EXP.search(t)
    if m:
        course = _course((m.group(1) or "").strip())
        if not diarioclase.entries(course):
            J.reply(f"No hay registro de clase de {course}.", "DIARIO DE CLASE")
            return True
        path = diarioclase.export_xlsx(course, J.settings["output_dir"])
        J.generated_files.add(path)
        J._open_doc(path)
        J.reply(f"Listo el registro de clase de {course} en Excel, para pasarlo a la plataforma del colegio.", "DIARIO DE CLASE")
        return True
    return False


# ============================================================================ QUIZ EN VIVO EN EL PROYECTOR
live_quiz = {"on": False, "quiz": None, "i": 0, "phase": "", "until": 0.0, "secs": 30}
_LQ_START = re.compile(r"\b(?:quiz|evaluacion|preguntas?|concurso|repaso)\s+en\s+vivo\b|\b(?:juguemos|vamos a jugar|haz|pon|lanza|inicia|empieza)\b.*"
                       r"\b(?:quiz|preguntas|concurso)\b.*\b(?:proyector|televisor|tv|en vivo)\b")
_LQ_NEXT = re.compile(r"^(?:siguiente|la siguiente|siguiente pregunta|otra|otra pregunta|pasa a la siguiente|next)$")
_LQ_ANSWER = re.compile(r"^(?:respuesta|la respuesta|muestra la respuesta|muestrame la respuesta|cual era|cual es la respuesta|revela la respuesta)$")
_LQ_STOP = re.compile(r"^(?:termina|terminar|acaba|cierra|para|deten|fin del)\s+(?:el\s+)?(?:quiz|concurso|juego)(?: en vivo)?$")


def live_emit():
    q = live_quiz
    if not q["on"]:
        J.socketio.emit("live_quiz", {"on": False})
        return
    item = q["quiz"]["preguntas"][q["i"]]
    J.socketio.emit("live_quiz", {"on": True, "n": q["i"] + 1, "total": len(q["quiz"]["preguntas"]), "phase": q["phase"],
                                  "titulo": q["quiz"].get("titulo", ""), "contexto": item.get("contexto", ""),
                                  "enunciado": item["enunciado"], "opciones": item["opciones"],
                                  "correcta": "abcd".find(item["respuesta"]) if q["phase"] == "respuesta" else -1,
                                  "explicacion": item.get("explicacion", "") if q["phase"] == "respuesta" else "",
                                  "left": max(0, round(q["until"] - time.time())) if q["phase"] == "pregunta" else 0,
                                  "secs": q["secs"]})


def live_step(action):
    q = live_quiz
    if action == "answer":
        q["phase"] = "respuesta"
    elif action == "next":
        if q["i"] + 1 >= len(q["quiz"]["preguntas"]):
            q.update(on=False)
            J.socketio.emit("live_quiz", {"on": False, "done": True, "total": len(q["quiz"]["preguntas"])})
            return "fin"
        q.update(i=q["i"] + 1, phase="pregunta", until=time.time() + q["secs"])
    elif action == "stop":
        q.update(on=False)
    live_emit()
    return q["phase"] if q["on"] else "fin"


def live_quiz_voice(text, t):
    q = live_quiz
    if q["on"]:
        if _LQ_NEXT.match(t):
            if q["phase"] == "pregunta":                # primero la respuesta, luego la siguiente
                live_step("answer")
                J.reply("Respuesta en pantalla. Di «siguiente» para seguir.", "QUIZ EN VIVO")
            elif live_step("next") == "fin":
                J.reply(f"Terminamos el quiz: {len(q['quiz']['preguntas'])} preguntas. ¡Buen trabajo!", "QUIZ EN VIVO")
            else:
                J.reply(f"Pregunta {q['i'] + 1}.", "QUIZ EN VIVO")
            return True
        if _LQ_ANSWER.match(t):
            live_step("answer")
            J.reply("Respuesta en pantalla.", "QUIZ EN VIVO")
            return True
        if _LQ_STOP.match(t):
            live_step("stop")
            J.reply("Quiz en vivo terminado.", "QUIZ EN VIVO")
            return True
    if not _LQ_START.search(t):
        return False
    quiz = None
    tm = re.search(r"\b(?:de|sobre)\s+(?!\d+\s+preguntas)(.+?)(?:\s+(?:en|para)\s+(?:el\s+)?(?:proyector|televisor|vivo|tv).*)?$", t)
    tema = (tm.group(1) if tm else "").strip()
    if tema and tema not in ("vivo",):
        quiz = J.banco.build_quiz(tema, aula.detect_count(t) or 10)
    quiz = quiz or J.last_quiz["m"]
    if not quiz or not quiz.get("preguntas"):
        J.reply("No tengo un quiz listo. Prepárame uno («haz un quiz de fracciones») o dime el tema del banco.", "QUIZ EN VIVO")
        return True
    q.update(on=True, quiz=quiz, i=0, phase="pregunta", secs=J.settings["live_quiz_secs"], until=time.time() + J.settings["live_quiz_secs"])
    J._open_projector()
    live_emit()
    J.reply(f"Quiz en vivo en el proyector: {len(quiz['preguntas'])} preguntas de {q['secs']} segundos. Di «respuesta» para "
            "mostrarla y «siguiente» para seguir.", "QUIZ EN VIVO")
    return True


def _live_worker():
    while True:
        time.sleep(1)
        q = live_quiz
        if q["on"] and q["phase"] == "pregunta" and time.time() >= q["until"]:
            try:
                live_step("answer")                         # se acabó el tiempo: se muestra la respuesta
            except Exception as e:
                J.note_error("QUIZ EN VIVO", e)


@J.socketio.on("live_quiz_action")
def handle_live_quiz_action(data=None):
    a = (data or {}).get("a")
    if live_quiz["on"] and a in ("answer", "next", "stop"):
        live_step(a)
    return {"on": live_quiz["on"]}


@J.socketio.on("live_quiz_state")
def handle_live_quiz_state(data=None):
    live_emit()
    return {"on": live_quiz["on"]}


def class_plus_start():
    diarioclase.configure(J.CONFIG_DIR)
    threading.Thread(target=J._live_worker, daemon=True, name="quiz-en-vivo").start()


__all__ = [
    '_D_ADD', '_D_ASK', '_D_EXP', '_D_MISS', '_D_NOW', '_LQ_ANSWER', '_LQ_NEXT', '_LQ_START', '_LQ_STOP', '_REC_RE', '_course',
    '_live_worker', '_orig_tail', 'class_plus_start', 'class_diary_voice', 'handle_live_quiz_action', 'handle_live_quiz_state',
    'live_emit', 'live_quiz', 'live_quiz_voice', 'live_step', 'recovery_voice',
]
