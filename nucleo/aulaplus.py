"""7.8: aula conectada (Google Classroom, seguimiento por estudiante, banco de preguntas) y memoria editable.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import http.server
import re
import secrets
import threading
import time
import urllib.parse
import webbrowser

import aprendizaje
import aula
import banco
import classroom
import perfil
import recuerdos
import seguimiento
import zeti
from nucleo import J

# ============================================================================ GOOGLE CLASSROOM
cr_state = {"client": None, "key": "", "courses": [], "courses_t": 0.0, "auth": None}


def classroom_client():
    s = J.settings
    if not (s["classroom_client_id"] and s["classroom_client_secret"] and s["classroom_refresh"]):
        return None
    key = s["classroom_client_id"] + s["classroom_refresh"][-8:]
    if cr_state["key"] != key:
        cr_state.update(client=classroom.Client(s["classroom_client_id"], s["classroom_client_secret"], s["classroom_refresh"]),
                        key=key, courses=[], courses_t=0.0)
    return cr_state["client"]


def classroom_courses(force=False):
    c = J.classroom_client()
    if not c:
        return []
    if force or time.time() - cr_state["courses_t"] > 600 or not cr_state["courses"]:
        cr_state.update(courses=c.courses(), courses_t=time.time())
    return cr_state["courses"]


def classroom_connect():
    """Abre Google para autorizar y espera la respuesta en 127.0.0.1 (con PKCE). Devuelve un mensaje."""
    cid, secret = J.settings["classroom_client_id"].strip(), J.settings["classroom_client_secret"].strip()
    if not (cid and secret):
        return "Primero pega el ID de cliente y el secreto (Ajustes › Memoria › Cuenta de Google)."
    verifier, challenge = classroom.pkce()
    state = secrets.token_urlsafe(16)
    box = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            ok = q.get("state", [""])[0] == state and "code" in q
            if ok:
                box["code"] = q["code"][0]
            else:
                box["error"] = q.get("error", ["respuesta no válida"])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Listo: Jarvis ya está conectado con tu cuenta de Google. Puedes cerrar esta pestaña." if ok else \
                "No se pudo conectar. Vuelve a intentarlo desde Ajustes de Jarvis."
            self.wfile.write(f"<html><body style='font-family:Segoe UI;padding:40px'><h2>{msg}</h2></body></html>".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    srv.timeout = 1
    redirect = f"http://127.0.0.1:{srv.server_address[1]}/oauth"
    webbrowser.open(classroom.auth_url(cid, redirect, state, challenge))
    t0 = time.time()
    try:
        while time.time() - t0 < 240 and not box:
            srv.handle_request()
    finally:
        srv.server_close()
    if "code" not in box:
        return f"No se completó la conexión ({box.get('error', 'se acabó el tiempo')})."
    try:
        tok = classroom.exchange(cid, secret, box["code"], redirect, verifier)
    except classroom.ClassroomError as e:
        return f"Google no aceptó la conexión: {e}"
    J.apply_settings({"classroom_refresh": tok["refresh_token"], "google_scopes": str(tok.get("scope", ""))[:2000]})
    parts = []
    if J.gmail_ready():                                # 8.5: el correo también queda conectado
        try:
            addr = J.gmail.profile(J.classroom_client()).get("emailAddress", "")
            if addr and not J.settings["email_address"].strip():
                J.apply_settings({"email_address": addr})
            parts.append(f"Gmail ({addr or 'tu cuenta'})")
        except classroom.ClassroomError:
            parts.append("Gmail (activa la Gmail API en tu proyecto de Google Cloud si falla)")
    try:
        n = len(J.classroom_courses(force=True))
        parts.insert(0, f"Classroom: {n} clase{'s' if n != 1 else ''}")
    except classroom.ClassroomError:
        if not parts:
            return "Conectado a Google, pero no pude leer tus clases ni tu correo: activa las APIs en Google Cloud."
    return "Conectado con Google · " + " · ".join(parts) + "."


@J.socketio.on("classroom_connect")
def handle_classroom_connect(data=None):
    def work():
        msg = J.classroom_connect()
        J.socketio.emit("classroom_done", {"msg": msg})
        J.log_terminal(msg, "CLASSROOM")
    threading.Thread(target=work, daemon=True).start()
    return {"ok": True}


@J.socketio.on("classroom_status")
def handle_classroom_status(data=None):
    if not J.classroom_client():
        return {"connected": False}
    try:
        return {"connected": True, "courses": [c.get("name", "") + (" · " + c["section"] if c.get("section") else "")
                                               for c in J.classroom_courses()]}
    except classroom.ClassroomError as e:
        return {"connected": True, "error": str(e)}


@J.socketio.on("classroom_disconnect")
def handle_classroom_disconnect(data=None):
    J.apply_settings({"classroom_refresh_clear": True, "google_scopes": ""})   # (un campo vacío conservaría la clave)
    cr_state.update(client=None, key="", courses=[])
    return {"connected": False}


_CR_RE = re.compile(r"\bclassroom\b")
_CR_PUBLISH = re.compile(r"\b(?:publica|anuncia|pon(?:le)?|manda|envia)\b.*?\bclassroom\b\s*(?:de|para|del|en)?\s*(.+?)\s+(?:que|diciendo(?: que)?|:)\s+(.+)$")
_CR_MISSING = re.compile(r"\b(?:quien|quienes)\s+(?:no\s+)?(?:ha|han)\s+entregado\b|\bque\s+falta(?:n)?\s+por\s+entregar\b|\bno\s+(?:ha|han)\s+entregado\b")
_CR_GRADES = re.compile(r"\b(?:trae|importa|sincroniza|pasa)\b.*\bnotas\b")


def _course_from(t, courses):
    m = re.search(r"\b(?:de|del|en|para)\s+((?:\d{1,2}\s?[a-z]\b|sexto|septimo|octavo|noveno|undecimo|decimo|onceavo|once|quinto)(?:\s+[a-z]\b)?[\w ]{0,20})", t)
    return classroom.find_course(courses, m.group(1)) if m else (classroom.find_course(courses, t) if courses else None)


def classroom_voice(text, t):
    if not _CR_RE.search(t):
        return False
    if not J.classroom_client():
        J.reply("Google Classroom no está conectado. Se conecta en Ajustes › Aula › Google Classroom.", "CLASSROOM")
        return True
    try:
        courses = J.classroom_courses()
        if not courses:
            J.reply("No encuentro clases activas en tu Classroom.", "CLASSROOM")
            return True
        pub = _CR_PUBLISH.search(t)
        if pub:
            course = classroom.find_course(courses, pub.group(1))
            if not course:
                J.reply("¿En cuál clase lo publico? Dímelo con el curso, por ejemplo «de 7A».", "CLASSROOM")
                return True
            texto = re.split(r"\b(?:que|diciendo(?: que)?|:)\s+", text, maxsplit=1, flags=re.I)[-1].strip()
            texto = texto[:1].upper() + texto[1:]
            client = J.classroom_client()

            def go():
                try:
                    client.announce(course["id"], texto)
                    J.reply(f"Publicado en Classroom de {course.get('name')}.", "CLASSROOM")
                except classroom.ClassroomError as e:
                    J.reply(f"No pude publicarlo: {e}", "CLASSROOM")
            J.request_approval("classroom", f"Publicar en Classroom de {course.get('name')}", texto, on_ok=go,
                               on_no=lambda: J.reply("Vale, no lo publico.", "CLASSROOM"),
                               say=f"Publico en {course.get('name')}: «{texto[:300]}». ¿Lo publico? Di «sí» o «no».")
            return True
        course = _course_from(t, courses) or (courses[0] if len(courses) == 1 else None)
        if not course:
            J.reply("¿De qué clase? Por ejemplo: «¿qué tareas tengo en Classroom de 7A?».", "CLASSROOM")
            return True
        client = J.classroom_client()
        works = client.coursework(course["id"])
        if _CR_MISSING.search(t):
            w = classroom.find_work(works, t)
            if not w:
                J.reply(f"No hay tareas en {course.get('name')}.", "CLASSROOM")
                return True
            names = client.students(course["id"])
            falta = classroom.missing(client.submissions(course["id"], w["id"]), names)
            if not falta:
                J.reply(f"En «{w.get('title')}» de {course.get('name')} ya entregaron todos.", "CLASSROOM")
            else:
                J.reply(f"En «{w.get('title')}» faltan {len(falta)}: " + ", ".join(falta[:15]) + ("…" if len(falta) > 15 else "") + ".", "CLASSROOM")
            return True
        if _CR_GRADES.search(t):
            names = client.students(course["id"])
            n = 0
            for w in works[:15]:
                maxp = w.get("maxPoints")
                for s in client.submissions(course["id"], w["id"]):
                    nota = classroom.to_scale(s.get("assignedGrade"), maxp)
                    if nota is not None:
                        seguimiento.add(course.get("name", "Classroom"), names.get(s.get("userId"), s.get("userId")),
                                        w.get("title", "tarea"), nota, origen="classroom")
                        n += 1
            J.reply(f"Traje {n} notas de Classroom de {course.get('name')} (en escala de 1 a 5). Pregúntame «¿quiénes están "
                    f"en riesgo en {course.get('name')}?».", "CLASSROOM")
            return True
        now = datetime.datetime.now()
        upcoming = sorted([w for w in works if (classroom.due_of(w) or now) >= now - datetime.timedelta(days=1)],
                          key=lambda w: classroom.due_of(w) or datetime.datetime.max)[:6]
        if not upcoming:
            J.reply(f"En {course.get('name')} no hay tareas con entrega próxima.", "CLASSROOM")
        else:
            parts = []
            for w in upcoming:
                d = classroom.due_of(w)
                parts.append(f"«{w.get('title')}»" + (f" para el {d.day}/{d.month}" if d else " sin fecha"))
            J.reply(f"Tareas de {course.get('name')}: " + "; ".join(parts) + ".", "CLASSROOM")
        return True
    except classroom.ClassroomError as e:
        J.reply(f"Classroom: {e}", "CLASSROOM")
        return True


# ============================================================================ SEGUIMIENTO POR ESTUDIANTE
def _absences(course):
    out = {}
    for day, lst in aula.data.get("asistencia", {}).get(course, {}).items():
        for n in lst:
            out[n] = out.get(n, 0) + 1
    return out


def _resolve_course(spoken):
    if spoken:
        c = aula.find_course(spoken)
        if c:
            return c
        if spoken.strip().upper() in seguimiento.data:
            return spoken.strip().upper()
        g = aula.grade_of(spoken)                      # 10.3: «de 11» con 11-1 y 11-2: mejor preguntar que adivinar
        if g and sum(1 for c in aula.data.get("cursos", {}) if aula.grade_of(c) == g) > 1:
            return ""
    try:
        return aula.active()[0]
    except ValueError:
        return spoken.strip().upper() if spoken else ""


_STUDENT_RE = re.compile(r"^como (?:va|le va a|esta|vamos con)\s+(?!el |la |los |las |mi |tu |su |todo|eso|esto)(.+?)(?:\s+en\s+(.+))?$")
_RISK_RE = re.compile(r"\b(?:quienes|quien|que estudiantes|cuales estudiantes|que alumnos)\s+(?:estan|esta|van|va)\s+(?:en riesgo|perdiendo|mal|reprobando)\b")


def student_voice(text, t):
    g = seguimiento.parse_voice_grade(t)
    if g:
        nota, quien, actividad, curso_txt = g
        course = _resolve_course(curso_txt)
        if not course:
            J.reply("¿De qué curso? Dímelo al final, por ejemplo «de 7A».", "AULA")
            return True
        names = aula.data.get("cursos", {}).get(course, [])
        name, cands = aula.find_student(quien, names) if names else (quien.title(), [])
        if not name and len(cands) > 1:
            J.reply(f"¿A cuál? " + ", ".join(cands[:4]) + ".", "AULA")
            return True
        name = name or quien.title()
        seguimiento.add(course, name, actividad, nota)
        dim = dict((d, n) for d, n, _ in zeti.DIMS)[zeti.infer_dim(actividad)]
        J.reply(f"Anotado: {str(nota).replace('.', ',')} a {name} en {actividad} ({course}, {dim}). Su valoración va en "
                f"{str(seguimiento.average(course, name)).replace('.', ',')}.", "AULA")
        return True
    if _RISK_RE.search(t):
        m = re.search(r"\ben\s+(.+)$", t)
        course = _resolve_course(m.group(1) if m else "")
        names = sorted(set(aula.data.get("cursos", {}).get(course, [])) | set(seguimiento.data.get(course, {})))
        if not names:
            J.reply("No tengo estudiantes ni notas de ese curso todavía.", "AULA")
            return True
        J.reply(seguimiento.spoken_risk(course, seguimiento.at_risk(course, names, _absences(course), J.settings["risk_grade"],
                                                                     J.settings["risk_absences"])), "AULA")
        return True
    m = _STUDENT_RE.match(t)
    if m:
        course = _resolve_course(m.group(2) or "")
        names = sorted(set(aula.data.get("cursos", {}).get(course, [])) | set(seguimiento.data.get(course, {})))
        name, _ = aula.find_student(m.group(1), names) if names else (None, [])
        if not name:
            return False                               # no es un estudiante: que lo atienda otro
        J.reply(seguimiento.report(course, name, _absences(course).get(name, 0)), "AULA")
        return True
    return False


_risk_state = {"week": ""}


def risk_check(now=None):
    """Los viernes por la tarde: resumen de estudiantes en riesgo (si hay alguno)."""
    now = now or datetime.datetime.now()
    week = now.strftime("%G-%V")
    if now.weekday() != 4 or now.hour < 14 or _risk_state["week"] == week or not J.settings["risk_alerts"]:
        return None
    _risk_state["week"] = week
    msgs = []
    for course in sorted(set(aula.data.get("cursos", {})) | set(seguimiento.data), key=aula.course_sort_key)[:24]:
        names = sorted(set(aula.data.get("cursos", {}).get(course, [])) | set(seguimiento.data.get(course, {})))
        risk = seguimiento.at_risk(course, names, _absences(course), J.settings["risk_grade"], J.settings["risk_absences"])
        if risk:
            msgs.append(seguimiento.spoken_risk(course, risk))
    if msgs:
        J.alert("Resumen de la semana. " + " ".join(msgs), "NOTAS")
    return msgs


def _risk_worker():
    while True:
        time.sleep(300)
        try:
            J.risk_check()
        except Exception as e:
            J.log_terminal(f"Seguimiento: {e}", "AVISO")


# ============================================================================ BANCO DE PREGUNTAS
_BANK_COUNT = re.compile(r"\bcuantas preguntas tengo(?:\s+(?:de|sobre)\s+(.+?))?(?:\s+en el banco)?$")
_BANK_QUIZ = re.compile(r"\b(?:quiz|evaluacion|examen|prueba)\b.*\b(?:con el banco|del banco|con preguntas del banco|con mis preguntas)\b")


def bank_voice(text, t):
    m = _BANK_COUNT.search(t)
    if m:
        tema = (m.group(1) or "").strip()
        n = banco.count(tema)
        J.reply(f"Tengo {n} pregunta{'s' if n != 1 else ''}" + (f" de {tema}" if tema else "") + " en el banco." +
                ("" if n else " Se llena solo cada vez que te preparo un quiz."), "AULA")
        return True
    if not _BANK_QUIZ.search(t):
        return False
    tema_m = re.search(r"\b(?:de|sobre)\s+(?!\d+\s+preguntas)(.+?)\s+(?:con el banco|del banco|con preguntas del banco|con mis preguntas)", t)
    tema = (tema_m.group(1) if tema_m else "").strip()
    n = aula.detect_count(t) or 10
    quiz = banco.build_quiz(tema, n)
    if not quiz:
        J.reply(f"No tengo preguntas de {tema or 'ese tema'} en el banco todavía. Pídeme un quiz normal y las guardo.", "AULA")
        return True
    J.remember_quiz(quiz)                              # 8.1: «pásalo a Forms»
    if J.Document is None:
        J.reply("No puedo crear documentos: falta python-docx.", "ERROR")
        return True
    path = aula.build_docx("quiz", quiz, J.settings["output_dir"], J.Document, J.settings["aula_docente"],
                           J.settings["aula_institucion"], aula.data.get("activo", ""))
    J.generated_files.add(path)
    opened = J._open_doc(path)
    J.reply(f"Listo: quiz de {len(quiz['preguntas'])} preguntas de {tema or 'tu banco'}, sin usar la IA. "
            + ("Lo abrí." if opened else "Está en Material de clase."), "AULA")
    return True


# ============================================================================ MEMORIA EDITABLE Y RECUERDOS ESPONTÁNEOS
_recall_cache = {"t": 0.0, "entries": []}


def recall_ctx(question):
    """Recuerdos muy relacionados con lo que preguntas (de los últimos 60 días), para la IA."""
    if not (J.settings["history_enabled"] and J.settings["memory_proactive"]) or len(question) < 12:
        return ""
    if time.time() - _recall_cache["t"] > 60:
        since = datetime.date.today() - datetime.timedelta(days=60)
        _recall_cache.update(t=time.time(), entries=recuerdos.load(since))
    recent = time.time() - 600
    entries = [e for e in _recall_cache["entries"] if e["dt"].timestamp() < recent]
    if len(entries) < 3:
        return ""
    hits = [h for h in recuerdos.search(question, entries=entries, k=3) if h["score"] >= 0.8 and h["r"] == "u"]
    if not hits:
        return ""
    lines = "; ".join(f"{recuerdos.when_text(h['dt'])} el usuario dijo: «{h['x'][:160]}»" for h in hits[:2])
    return f" Recuerdos de conversaciones anteriores (úsalos solo si vienen al caso, y dilo con naturalidad): {lines}."


@J.socketio.on("profile_edit")
def handle_profile_edit(data=None):
    d = data or {}
    fid, texto = str(d.get("id", "")), str(d.get("texto", "")).strip()
    if fid and texto:
        perfil.update(fid, texto)
    elif texto:
        perfil.add(texto)
    J._profile_changed()
    return {"facts": perfil.snapshot()}


@J.socketio.on("history_search")
def handle_history_search(data=None):
    q = str((data or {}).get("q", "")).strip()
    if not q:
        return {"items": []}
    hits = J.recall(q)
    return {"items": [{"ts": h["dt"].isoformat(timespec="seconds"), "r": h["r"], "x": h["x"], "cuando": recuerdos.when_text(h["dt"])}
                      for h in hits]}


@J.socketio.on("history_delete")
def handle_history_delete(data=None):
    d = data or {}
    n = recuerdos.delete_entry(str(d.get("ts", "")), str(d.get("x", "")))
    _recall_cache["t"] = 0
    return {"ok": n > 0}


@J.socketio.on("habits_info")
def handle_habits_info(data=None):
    d = data or {}
    if d.get("forget"):
        aprendizaje.clear()
    if d.get("unreject"):
        aprendizaje.data["rechazadas"] = []
        aprendizaje.save()
    return {"acciones": len(aprendizaje.data["acciones"]), "rechazadas": len(aprendizaje.data["rechazadas"]),
            "hechas": len(aprendizaje.data["hechas"]), "banco": banco.count(),
            "seguimiento": sum(len(v) for v in seguimiento.data.values())}


def aula_plus_start():
    seguimiento.configure(J.CONFIG_DIR)
    banco.configure(J.CONFIG_DIR)
    threading.Thread(target=J._risk_worker, daemon=True).start()


__all__ = [
    '_BANK_COUNT', '_BANK_QUIZ', '_CR_GRADES', '_CR_MISSING', '_CR_PUBLISH', '_CR_RE', '_RISK_RE', '_STUDENT_RE',
    '_absences', '_course_from', '_recall_cache', '_resolve_course', '_risk_state', '_risk_worker', 'aula_plus_start',
    'bank_voice', 'classroom_client', 'classroom_connect', 'classroom_courses', 'classroom_voice', 'cr_state',
    'handle_classroom_connect', 'handle_classroom_disconnect', 'handle_classroom_status', 'handle_habits_info',
    'handle_history_delete', 'handle_history_search', 'handle_profile_edit', 'recall_ctx', 'risk_check', 'student_voice',
]
