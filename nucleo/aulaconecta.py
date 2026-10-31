"""8.1: el quiz en Google Forms (y sus notas de vuelta), retroalimentación de entregas de Classroom y horario de clases.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import json
import os
import re
import threading
import time
import webbrowser

import aula
import banco
import classroom
import formularios
import horario
import seguimiento
from nucleo import J

last_quiz = {"m": None}          # el último quiz que preparó Jarvis (para «pásalo a Forms»)
_forms_lock = threading.Lock()


# ============================================================================ GOOGLE FORMS
def _forms_path():
    return os.path.join(J.CONFIG_DIR, "formularios.json")


def forms_load():
    try:
        with open(_forms_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def forms_save(lst):
    with _forms_lock:
        try:
            with open(_forms_path() + ".tmp", "w", encoding="utf-8") as f:
                json.dump(lst[-100:], f, ensure_ascii=False, indent=1)
            os.replace(_forms_path() + ".tmp", _forms_path())
        except OSError:
            pass


def _open_link(url):
    try:
        webbrowser.open(url)
    except Exception:
        pass


def remember_quiz(m):
    last_quiz["m"] = m


def quiz_to_form(quiz, curso=""):
    """Crea el formulario autocalificable. Devuelve el registro guardado (con url)."""
    client = J.classroom_client()
    if not client:
        raise classroom.ClassroomError("conecta Google (Ajustes › Memoria › Google Classroom) para usar Forms")
    form = client.form_create(formularios.create_body(quiz))
    client.form_update(form["formId"], formularios.batch_requests(quiz))
    rec = {"id": form["formId"], "url": form.get("responderUri") or f"https://docs.google.com/forms/d/{form['formId']}/viewform",
           "editar": f"https://docs.google.com/forms/d/{form['formId']}/edit", "titulo": quiz.get("titulo", "Evaluación"),
           "tema": quiz.get("tema", ""), "curso": curso, "n": len(quiz.get("preguntas") or []),
           "creado": datetime.datetime.now().isoformat(timespec="minutes")}
    lst = forms_load()
    lst.append(rec)
    forms_save(lst)
    return rec


def form_grades(rec, course=None):
    """Lee las respuestas, las pasa a 1-5 y las guarda en el seguimiento. Devuelve (n, sin_estudiante)."""
    client = J.classroom_client()
    by_mail = formularios.scores(client.form_responses(rec["id"]), rec["n"])
    roster = client.roster_emails(course["id"]) if course else {}
    named, unknown = formularios.match_names(by_mail, roster)
    curso = (course or {}).get("name") or rec.get("curso") or "Forms"
    for name, nota in named.items():
        seguimiento.add(curso, name, rec["titulo"], nota, origen="forms")
    for mail in unknown:                                # sin Classroom: se guarda con el correo
        seguimiento.add(curso, mail, rec["titulo"], by_mail[mail], origen="forms")
    return len(by_mail), unknown if roster else []


def _find_form(t):
    lst = forms_load()
    if not lst:
        return None
    words = {w for w in re.findall(r"[a-z0-9]{4,}", t)} - {"notas", "forms", "formulario", "quiz", "trae", "importa"}
    best = max(lst, key=lambda r: (len(words & set(re.findall(r"[a-z0-9]{4,}", J.normalize(r["titulo"] + " " + r["tema"])))),
                                   r["creado"]))
    return best


_F_SEND = re.compile(r"\b(?:pasa|pasalo|sube|subelo|publica|publicalo|crea|crealo|convierte|conviertelo|ponlo|montalo|monta)\b"
                     r".*\b(?:a|en|como)\s+(?:un\s+)?(?:google\s+)?(?:forms?|formulario)\b")
_F_NEW = re.compile(r"\b(?:haz|hazme|crea|creame|prepara|preparame|genera)\b.*\b(?:quiz|evaluacion|examen|cuestionario)\b.*"
                    r"\b(?:en|por|con)\s+(?:google\s+)?(?:forms?|formulario)\b")
_F_GRADES = re.compile(r"\b(?:trae|traeme|importa|pasa|sincroniza|lee|revisa)\b.*\bnotas\b.*\b(?:forms?|formulario)\b|"
                       r"\bcomo (?:les )?fue en el (?:formulario|forms)\b")


def _course_hint(t):
    try:
        courses = J.classroom_courses()
    except Exception:
        return None
    if not courses:
        return None
    c = J._course_from(t, courses)
    if not c:
        nc = horario.now_class()
        if nc and nc["curso"]:
            c = classroom.find_course(courses, nc["curso"])
    return c


def forms_voice(text, t):
    send, new, grades = _F_SEND.search(t), _F_NEW.search(t), _F_GRADES.search(t)
    if not (send or new or grades):
        return False
    if not J.classroom_client():
        J.reply("Para Google Forms conecta primero tu cuenta de Google en Ajustes › Memoria › Google Classroom.", "FORMS")
        return True
    if grades:
        rec = _find_form(t)
        if not rec:
            J.reply("Aún no he creado formularios. Di «pasa el quiz a Forms» después de preparar uno.", "FORMS")
            return True
        try:
            course = _course_hint(t)
            n, unknown = form_grades(rec, course)
        except classroom.ClassroomError as e:
            J.reply(f"Forms: {e}", "FORMS")
            return True
        if not n:
            J.reply(f"«{rec['titulo']}» todavía no tiene respuestas.", "FORMS")
            return True
        J.reply(f"Traje {n} nota{'s' if n != 1 else ''} de «{rec['titulo']}» al seguimiento (escala de 1 a 5)." +
                (f" {len(unknown)} correo(s) no son de estudiantes de la clase; los guardé con el correo." if unknown else ""), "FORMS")
        return True
    quiz = None
    if send:
        quiz = last_quiz["m"]
        if not quiz:
            J.reply("No tengo un quiz reciente. Pídeme «haz un quiz de 10 preguntas de fracciones en Forms».", "FORMS")
            return True
    J.reply("Creo el formulario autocalificable en Google Forms…", "FORMS")
    capture = getattr(J._tl, "capture", None)

    def work():
        q = quiz
        try:
            if q is None:
                tm = re.search(r"\b(?:de|sobre)\s+(?!\d+\s+preguntas)(.+?)\s+(?:en|por|con)\s+(?:google\s+)?(?:forms?|formulario)\b", t)
                tema = (tm.group(1) if tm else "").strip()
                n = aula.detect_count(t) or 10
                q = banco.build_quiz(tema, n) if banco.count(tema) >= n else None
                if q is None:
                    prompt = aula.build_prompt("quiz", re.sub(r"\b(?:en|por|con)\s+(?:google\s+)?(?:forms?|formulario)\b", "", text,
                                                              flags=re.I), n, "", tema)
                    q = aula.validate("quiz", J._extract_json(J.ai_chat([{"role": "user", "content": prompt}], json_mode=True,
                                                                         max_tokens=8000)), text)
                    banco.add_quiz(q)
                remember_quiz(q)
            course = _course_hint(t)
            rec = quiz_to_form(q, (course or {}).get("name", ""))
        except J.AIError as e:
            J.notify(J.ai_error_reply(e), "FORMS")
            return
        except (classroom.ClassroomError, ValueError, KeyError) as e:
            J.notify(f"No pude crear el formulario: {e}", "FORMS")
            return
        J.diario.log("orden", f"formulario {rec['titulo']}")
        J._open_link(rec["editar"])
        msg = (f"Listo: «{rec['titulo']}» en Google Forms, con {rec['n']} preguntas que se califican solas. Lo abrí para "
               "que lo revises. Cuando respondan, dime «trae las notas del formulario».")
        J.notify(msg, "FORMS")
        if course:
            def go():
                try:
                    J.classroom_client().announce(course["id"], f"{rec['titulo']}: {rec['url']}")
                    J.reply(f"Publiqué el enlace en Classroom de {course.get('name')}.", "FORMS")
                except classroom.ClassroomError as e:
                    J.reply(f"No pude publicar el enlace: {e}", "FORMS")
            J.request_approval("classroom", f"Publicar el formulario en Classroom de {course.get('name')}", rec["url"],
                               on_ok=go, on_no=lambda: J.reply("Vale, no lo publico.", "FORMS"),
                               say=f"¿Publico el enlace del formulario en Classroom de {course.get('name')}? Di «sí» o «no».")
    if capture is not None:
        work()
    else:
        J.start_job("Creando el formulario de Google Forms", work, "forms")
    return True


# ============================================================================ RETROALIMENTACIÓN DE ENTREGAS
_FB_RE = re.compile(r"\b(?:revisa|revisame|califica|calificame|retroalimenta|corrige|evalua)\b.*\b(?:respuestas|entregas|trabajos)\b"
                    r".*\bclassroom\b")


def feedback_prompt(work, answers, rubric=""):
    lines = [f'- id {i}: "{a[:1500]}"' for i, (_, a) in enumerate(answers)]
    return ("Eres un docente colombiano que da retroalimentación clara, amable y concreta a estudiantes de colegio. "
            f"Tarea: «{work.get('title', '')}». Enunciado: {str(work.get('description', ''))[:1500]}\n"
            + (f"Criterios o rúbrica: {rubric[:1500]}\n" if rubric else "")
            + "Respuestas de los estudiantes:\n" + "\n".join(lines)
            + "\n\nPara cada respuesta propone una nota de 1.0 a 5.0 (escala colombiana, 3.0 aprueba) y un comentario de "
              "una o dos frases en segunda persona: qué hizo bien y qué mejorar. No inventes datos que no estén en la "
              'respuesta. Devuelve SOLO JSON: {"revision": [{"id": 0, "nota": 4.2, "comentario": "..."}]}')


def feedback_validate(d, n):
    out = {}
    for r in (d or {}).get("revision") or []:
        try:
            i, nota = int(r["id"]), round(float(str(r["nota"]).replace(",", ".")), 1)
        except (KeyError, ValueError, TypeError):
            continue
        if 0 <= i < n and 1.0 <= nota <= 5.0:
            out[i] = {"nota": nota, "comentario": str(r.get("comentario", ""))[:600]}
    return out


def _feedback_docx(course_name, work, rows):
    folder = os.path.join(J.settings["output_dir"], "Retroalimentación")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, aula.safe_filename(f"{course_name} - {work.get('title', 'tarea')}") +
                        f" {datetime.date.today():%Y-%m-%d}.docx")
    doc = J.Document()
    doc.add_heading(f"Retroalimentación: {work.get('title', '')}", 1)
    doc.add_paragraph(f"{course_name} · {datetime.date.today():%d/%m/%Y}")
    for name, r in rows:
        doc.add_heading(f"{name} — {str(r['nota']).replace('.', ',')}", 2)
        doc.add_paragraph(r["comentario"])
    doc.save(path)
    return path


def feedback_voice(text, t):
    if not _FB_RE.search(t):
        return False
    if not J.classroom_client():
        J.reply("Google Classroom no está conectado. Se conecta en Ajustes › Memoria › Google Classroom.", "CLASSROOM")
        return True
    J.reply("Leo las respuestas en Classroom y te propongo notas y comentarios…", "CLASSROOM")
    capture = getattr(J._tl, "capture", None)

    def work():
        try:
            courses = J.classroom_courses()
            course = J._course_from(t, courses) or (courses[0] if len(courses) == 1 else None)
            if not course:
                J.notify("¿De qué clase? Por ejemplo: «revisa las respuestas del taller en Classroom de 7A».", "CLASSROOM")
                return
            client = J.classroom_client()
            w = classroom.find_work([x for x in client.coursework(course["id"]) if x.get("workType") == "SHORT_ANSWER_QUESTION"]
                                    or client.coursework(course["id"]), t)
            if not w:
                J.notify(f"No hay tareas en {course.get('name')}.", "CLASSROOM")
                return
            names = client.students(course["id"])
            answers = [(names.get(s.get("userId"), s.get("userId")), (s.get("shortAnswerSubmission") or {}).get("answer", ""))
                       for s in client.submissions(course["id"], w["id"]) if s.get("state") in ("TURNED_IN", "RETURNED")]
            answers = [a for a in answers if a[1].strip()]
            if not answers:
                J.notify(f"En «{w.get('title')}» no hay respuestas de texto que pueda leer. Reviso respuestas cortas de "
                         "Classroom; los trabajos en papel o en archivo, muéstramelos con «revisa este trabajo».", "CLASSROOM")
                return
            res = {}
            for start in range(0, len(answers), 25):
                part = answers[start:start + 25]
                raw = J.ai_chat([{"role": "user", "content": feedback_prompt(w, part)}], json_mode=True, max_tokens=6000)
                res.update({start + i: v for i, v in feedback_validate(J._extract_json(raw), len(part)).items()})
        except J.AIError as e:
            J.notify(J.ai_error_reply(e), "CLASSROOM")
            return
        except (classroom.ClassroomError, ValueError, TypeError) as e:
            J.notify(f"Classroom: {e}", "CLASSROOM")
            return
        rows = [(answers[i][0], r) for i, r in sorted(res.items())]
        if not rows:
            J.notify("La IA no devolvió una revisión válida. Inténtalo otra vez.", "CLASSROOM")
            return
        path = _feedback_docx(course.get("name", ""), w, rows) if J.Document else ""
        if path:
            J.generated_files.add(path)
            J._open_doc(path)
        avg = round(sum(r["nota"] for _, r in rows) / len(rows), 1)
        detail = "\n".join(f"{n}: {str(r['nota']).replace('.', ',')}" for n, r in rows[:40])

        def save():
            for n, r in rows:
                seguimiento.add(course.get("name", "Classroom"), n, w.get("title", "tarea"), r["nota"], origen="revision")
            J.reply(f"Guardé {len(rows)} notas de «{w.get('title')}» en el seguimiento.", "CLASSROOM")
        J.request_approval("notas", f"Notas propuestas para «{w.get('title')}» ({course.get('name')})", detail, on_ok=save,
                           on_no=lambda: J.reply("Vale, no guardo las notas; los comentarios quedan en el Word.", "CLASSROOM"),
                           say=f"Revisé {len(rows)} respuestas de «{w.get('title')}»: promedio propuesto "
                               f"{str(avg).replace('.', ',')}. Los comentarios están en el Word"
                               + (" que abrí" if path else "") + ". ¿Guardo las notas en el seguimiento? Di «sí» o «no».")
    if capture is not None:
        work()
    else:
        J.start_job("Revisando entregas de Classroom", work, "retroalimentacion")
    return True


# ============================================================================ HORARIO DE CLASES
_H_NOW = re.compile(r"\b(?:que|cual|en que)\s+(?:clase|curso)\s+(?:tengo|me toca|es)\s+(?:ahora|ahorita|en este momento)\b|"
                    r"\bque me toca ahora\b|\bdonde (?:tengo|me toca) (?:clase )?ahora\b")
_H_NEXT = re.compile(r"\b(?:cual es mi|que|cual)\s+(?:es\s+)?(?:la\s+)?(?:proxima|siguiente)\s+clase\b|\bque clase sigue\b|"
                     r"\bque (?:clase )?me toca despues\b")
_H_DAY = re.compile(r"\b(?:mi\s+)?horario(?:\s+de\s+clases)?\s+(?:de\s+|del\s+|para\s+)?(hoy|manana|lunes|martes|miercoles|jueves|viernes|sabado)\b|"
                    r"\bque clases tengo\s+(hoy|manana|el lunes|el martes|el miercoles|el jueves|el viernes)\b")
_H_PREP = re.compile(r"\b(?:preparame|prepara|planea|planeame|haz(?:me)? el plan de)\s+(?:la\s+)?(?:proxima|siguiente)\s+clase"
                     r"(?:\s+(?:de|sobre)\s+(.+))?$")
_H_ADD = re.compile(rf"^(?:los|el)\s+(?:{'|'.join(horario.DAYS)})s?\b.*\btengo\b")


def schedule_voice(text, t):
    if _H_ADD.search(t):
        it = horario.parse_line(text)
        if not it:
            J.reply("No entendí la hora. Dilo así: «los lunes de 7 a 7:55 tengo 7A matemáticas».", "HORARIO")
            return True
        horario.add(it)
        J.reply(f"Anotado: los {horario.DAYS[it['dia']]} de {it['inicio']} a {it['fin']}, {horario.label(it)}.", "HORARIO")
        return True
    if _H_NOW.search(t):
        x = horario.now_class()
        if x:
            J.reply(f"Ahora tienes {horario.label(x)}, hasta las {x['fin']}.", "HORARIO")
        else:
            nx, day = horario.next_class()
            J.reply("Ahora no tienes clase." + (f" La próxima: {horario.label(nx)} a las {nx['inicio']}"
                                                + ("" if day == datetime.date.today() else f" del {horario.DAYS[day.weekday()]}") + "."
                                                if nx else " Aún no tengo tu horario: escríbelo en Ajustes › Memoria › Horario."),
                    "HORARIO")
        return True
    if _H_NEXT.search(t):
        nx, day = horario.next_class()
        if not nx:
            J.reply("Aún no tengo tu horario: escríbelo en Ajustes › Memoria › Horario.", "HORARIO")
        else:
            when = "hoy" if day == datetime.date.today() else ("mañana" if day == datetime.date.today() + datetime.timedelta(days=1)
                                                               else f"el {horario.DAYS[day.weekday()]}")
            J.reply(f"Tu próxima clase es {horario.label(nx)}, {when} a las {nx['inicio']}.", "HORARIO")
        return True
    m = _H_DAY.search(t)
    if m:
        w = (m.group(1) or m.group(2)).replace("el ", "")
        today = datetime.date.today()
        if w == "hoy":
            d, when = today, "hoy"
        elif w == "manana":
            d, when = today + datetime.timedelta(days=1), "mañana"
        else:
            idx = horario.DAYS.index(w)
            d, when = today + datetime.timedelta(days=(idx - today.weekday()) % 7), f"el {w}"
        J.reply(horario.spoken_day(horario.today(datetime.datetime.combine(d, datetime.time(0))), when), "HORARIO")
        return True
    m = _H_PREP.search(t)
    if m:
        nx, _ = horario.next_class()
        if not nx:
            J.reply("Aún no tengo tu horario: escríbelo en Ajustes › Memoria › Horario, o dime el curso.", "HORARIO")
            return True
        tema = (m.group(1) or "").strip() or nx["materia"] or "la clase"
        J.generate_material(f"plan de clase de {tema} para {nx['curso'] or nx['materia']}", kind="plan", grade=nx["curso"],
                            topic=tema)
        return True
    return False


_sched_state = {"active": "", "warned": ""}


def schedule_tick(now=None):
    """Cada minuto: el curso activo del aula sigue tu horario y (si quieres) te avisa 5 minutos antes."""
    now = now or datetime.datetime.now()
    x = horario.now_class(now)
    if J.settings["schedule_auto_course"] and x and x["curso"]:
        key = f"{now:%Y-%m-%d}{x['inicio']}"
        if _sched_state["active"] != key:
            _sched_state["active"] = key
            name = aula.find_course(x["curso"])
            if name:
                aula.set_active(name)
                J.log_terminal(f"Horario: curso activo {name}.", "HORARIO")
    if J.settings["schedule_warn"]:
        nx, day = horario.next_class(now)
        if nx and day == now.date():
            start = datetime.datetime.combine(day, datetime.time(*map(int, nx["inicio"].split(":"))))
            key = f"{day}{nx['inicio']}"
            if 0 < (start - now).total_seconds() <= 300 and _sched_state["warned"] != key:
                _sched_state["warned"] = key
                J.alert(f"En 5 minutos: {horario.label(nx)}.")
                return key
    return None


def _schedule_worker():
    while True:
        try:
            J.schedule_tick()
        except Exception as e:
            J.note_error("HORARIO", e)
        time.sleep(60)


@J.socketio.on("schedule_get")
def handle_schedule_get(data=None):
    return {"text": horario.to_text()}


@J.socketio.on("schedule_save")
def handle_schedule_save(data=None):
    items, bad = horario.parse_text((data or {}).get("text", ""))
    if not bad:
        horario.set_all(items)
    return {"ok": not bad, "bad": bad, "n": len(items), "text": horario.to_text(items) if not bad else (data or {}).get("text", "")}


@J.socketio.on("forms_list")
def handle_forms_list(data=None):
    return {"items": forms_load()[::-1][:20]}


def classroom_plus_start():
    horario.configure(J.CONFIG_DIR)
    threading.Thread(target=J._schedule_worker, daemon=True).start()


__all__ = [
    '_FB_RE', '_F_GRADES', '_F_NEW', '_F_SEND', '_H_ADD', '_H_DAY', '_H_NEXT', '_H_NOW', '_H_PREP', '_course_hint',
    '_feedback_docx', '_find_form', '_forms_lock', '_forms_path', '_open_link', '_sched_state', '_schedule_worker',
    'classroom_plus_start', 'feedback_prompt', 'feedback_validate', 'feedback_voice', 'form_grades', 'forms_load',
    'forms_save', 'forms_voice', 'handle_forms_list', 'handle_schedule_get', 'handle_schedule_save', 'last_quiz',
    'quiz_to_form', 'remember_quiz', 'schedule_tick', 'schedule_voice',
]
