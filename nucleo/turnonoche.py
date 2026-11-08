"""12.0: Jarvis trabaja mientras duermes.

En la noche (a la hora de Ajustes, por defecto 9 p. m.) mira tu horario del día siguiente y deja lista cada clase: plan,
evaluación corta y diapositivas, con el tema que toca según tu planeación anual o tu diario de clase. Revisa las fotos
de procedimientos que dejaste en «Documentos › Jarvis › Por calificar › <curso>» y propone las notas. Redacta los
mensajes a los padres de quien viene bajando. Nada se guarda ni se envía sin tu aprobación: todo queda en la bandeja.
En la mañana: «Buenos días, te dejé lista la clase de 10A, califiqué 23 entregas y hay 2 mensajes por aprobar».
Si el equipo estaba apagado en la noche, lo hace temprano en la mañana, antes de tu primera clase.

La lógica está en nocturno.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import json
import os
import re
import shutil
import threading
import time

import aula
import bitacora
import horario
import nocturno
import oficina
import seguimiento
from nucleo import J

night = {"busy": False, "report": None}


def _report_path():
    return os.path.join(J.CONFIG_DIR, "turno_noche.json")


def load_report():
    try:
        with open(_report_path(), encoding="utf-8") as f:
            night["report"] = json.load(f)
    except (OSError, ValueError):
        night["report"] = None
    return night["report"]


def _night_save(rep):
    night["report"] = rep
    try:
        with open(_report_path(), "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def _mark(key, value):
    J.settings[key] = value
    try:
        J.save_settings_file()
    except OSError:
        pass


def _ttl_until_noon(now=None):
    now = now or datetime.datetime.now()
    noon = datetime.datetime.combine(now.date() + datetime.timedelta(days=1 if now.hour >= 12 else 0), datetime.time(13, 0))
    return max(3600, int((noon - now).total_seconds()))


# ============================================================================ 1. LAS CLASES DE MAÑANA
def class_topic(curso, materia):
    """El tema que toca: la semana de la planeación anual; si no, lo que sigue en la malla o el diario de clase."""
    for key in ([f"{curso} · {materia}"] if materia else []) + [curso]:
        try:
            st = J.plan_status(key)
        except Exception:
            st = None
        if st and st.get("tema_semana"):
            return st["tema_semana"]
    try:
        return J.week_topic(curso) or ""
    except Exception:
        return ""


def _quiet_material(kind, pedido, grade, topic, folder, curso=""):
    """Como generate_material, pero sin hablar ni abrir nada: deja el Word en la carpeta. → (ruta, material)."""
    prompt = aula.build_prompt(kind, pedido, 5 if kind == "quiz" else None, grade, topic) + J.lessons_ctx() + J.book_ctx(topic, curso)
    if kind == "plan":
        prompt += J.clasevivo.worked_ctx(topic)
    last = None
    for _ in range(2):
        try:
            m = aula.validate(kind, J._extract_json(J.ai_chat([{"role": "user", "content": prompt}], json_mode=True, max_tokens=8000)), pedido)
            path = aula.build_docx(kind, m, folder, J.Document, J.settings["aula_docente"], J.settings["aula_institucion"], curso)
            return path, m
        except (ValueError, TypeError) as e:
            last = e
    raise ValueError(f"la IA no devolvió un material válido ({last})")


def prepare_class(curso, materia, folder):
    """Plan + evaluación corta + diapositivas de una clase. → {"curso", "materia", "tema", "archivos", "ok", "fallo"}."""
    tema = J.class_topic(curso, materia)
    out = {"curso": curso, "materia": materia, "tema": tema, "archivos": [], "ok": False, "fallo": ""}
    if not tema:
        out["fallo"] = "sin tema (falta la planeación anual o el diario de clase)"
        return out
    g = aula.grade_of(curso)
    grade = f"{g}° (curso {curso})" if g else ""
    sub = os.path.join(folder, re.sub(r"[^\w\s-]", "", f"{curso} {materia}").strip() or "Clase")
    os.makedirs(sub, exist_ok=True)
    asig = f" (asignatura: {materia})" if materia else ""
    try:
        path, m = _quiet_material("plan", f"plan de clase de {tema} para {curso}{asig}", grade, tema, sub, curso)
        out["archivos"].append(path)
        try:
            J.clasevivo.remember_plan(m, curso)                 # para «empieza la clase» mañana
        except Exception:
            pass
        if J.settings.get("night_quiz", True):
            path, m = _quiet_material("quiz", f"quiz corto de 5 preguntas de {tema} para {curso}{asig}", grade, tema, sub, curso)
            out["archivos"].append(path)
            try:
                J.banco.add_quiz(m)
                J.remember_quiz(m)
            except Exception:
                pass
        if J.settings.get("night_slides", True):
            gr = oficina.detect_grade(J.normalize(curso)) or (str(g) if g else "")
            mm = oficina.pptx_validate(J._extract_json(J.ai_chat([{"role": "user", "content": oficina.pptx_prompt(f"{tema}{asig}", 7, gr)}],
                                                                 json_mode=True, max_tokens=6000)), tema)
            out["archivos"].append(oficina.build_pptx(mm, sub, J.settings["aula_docente"], J.settings["aula_institucion"], gr))
        out["ok"] = True
    except J.AIError as e:
        out["fallo"] = e.why or str(e)
    except Exception as e:
        out["fallo"] = str(e)[:120]
    return out


# ============================================================================ 2. CALIFICAR LO QUE DEJASTE
def pending_dir():
    return os.path.join(J.settings["output_dir"], "Por calificar")


def grade_pending(day_label):
    """Revisa las fotos de «Por calificar/<curso>», propone las notas (con aprobación) y mueve las fotos a «Revisadas».
    → (n calificadas, n aprobaciones)."""
    base = pending_dir()
    os.makedirs(base, exist_ok=True)
    total, approvals = 0, 0
    for curso_dir in sorted(os.listdir(base)):
        folder = os.path.join(base, curso_dir)
        if not os.path.isdir(folder) or curso_dir.lower().startswith("revisadas"):
            continue
        fotos = [f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
        if not fotos:
            continue
        curso = J._resolve_course(curso_dir) or curso_dir
        results = J.review_folder(folder, curso)
        names = aula.students(curso)
        rows = []
        for name, res in results:
            nota = nocturno.grade_from_review(res)
            if nota is None:
                continue
            real = name
            if names:
                try:
                    real = aula.find_student(name, names)[0] or name
                except Exception:
                    pass
            err = (res.get("error") or {}).get("explicacion", "")
            rows.append((real, nota, err))
        total += len(rows)
        done = os.path.join(folder, f"Revisadas {day_label}")
        os.makedirs(done, exist_ok=True)
        for f in fotos:
            try:
                shutil.move(os.path.join(folder, f), os.path.join(done, f))
            except OSError:
                pass
        if rows:
            act = f"Procedimiento {day_label}"
            detail = "\n".join(f"{n}: {str(x).replace('.', ',')}" + (f" — {e}" if e else "") for n, x, e in rows)

            def save(rows=rows, curso=curso, act=act):
                for n, x, _e in rows:
                    seguimiento.add(curso, n, act, x, origen="revision")
                J.reply(f"Guardé {len(rows)} notas de «{act}» en {curso}.", "TURNO DE NOCHE")
            J.request_approval("notas", f"Notas de procedimientos de {curso} ({len(rows)})", detail, on_ok=save,
                               on_no=lambda: None, ttl=_ttl_until_noon(), quiet=True)
            approvals += 1
    return total, approvals


# ============================================================================ 3. MENSAJES A LOS PADRES
def _parent_message(a):
    name = a["estudiante"].split()[0]
    base = (f"Buenos días. Les escribe {J.settings['aula_docente'] or 'el docente'} de {a['curso']}. Quería contarles que {name} "
            f"{a['detalle']}. Me gustaría que lo habláramos para apoyarlo juntos; quedo atento a su respuesta. Gracias.")
    if J.state.get("ai") != "ok":
        return base
    try:
        txt = J.ai_chat([{"role": "user", "content": "Redacta un mensaje corto (máximo 70 palabras), cálido y respetuoso, de un docente colombiano "
                          f"a los padres de {a['estudiante']} ({a['curso']}): {a['detalle']}. Sin culpar; propone hablar y apoyar juntos. "
                          "Firma como «el docente». Solo el mensaje." + J.style_ctx()}], max_tokens=300)
        return txt.strip().strip('"') or base
    except Exception:
        return base


def draft_parent_messages(folder, limit=5):
    try:
        al = [a for a in J.early_alerts() if a["tipo"] != "mejora"][:limit]
    except Exception:
        al = []
    n = 0
    for a in al:
        msg = _parent_message(a)
        title = f"Mensaje a la familia de {a['estudiante']} ({a['curso']})"

        def ok(a=a, msg=msg):
            path = os.path.join(folder, "Mensajes a padres.docx")
            doc = J.Document(path) if os.path.exists(path) else J.Document()
            if not os.path.exists(path):
                doc.add_heading("Mensajes a padres (aprobados)", 1)
            doc.add_heading(f"{a['estudiante']} · {a['curso']}", 2)
            doc.add_paragraph(msg)
            doc.save(path)
            J.generated_files.add(path)
            J.reply(f"Aprobado: el mensaje para la familia de {a['estudiante']} quedó en «Mensajes a padres», listo para enviar.",
                    "TURNO DE NOCHE")
        J.request_approval("mensaje", title, msg, on_ok=ok, on_no=lambda: None, ttl=_ttl_until_noon(), quiet=True)
        n += 1
    return n


# ============================================================================ EL TURNO
def run_night(day=None, mode="noche", say=False):
    """Hace el turno para el día `day` (por defecto, el siguiente día de clases). → informe."""
    if night["busy"]:
        return None
    night["busy"] = True
    try:
        now = datetime.datetime.now()
        if day is None:
            day = now.date() if mode == "madrugada" else nocturno.next_school_day(
                now.date(), lambda d: bool(horario.today(datetime.datetime.combine(d, datetime.time(0)))))
        folder = os.path.join(J.settings["output_dir"], "Turno de noche", day.isoformat())
        os.makedirs(folder, exist_ok=True)
        rep = {"fecha": now.date().isoformat(), "para": day.isoformat(), "carpeta": folder, "clases": [], "calificadas": 0, "mensajes": 0,
               "aprobar": 0, "fallos": [], "dicho": False}
        if J.state.get("ai") == "ok" and J.Document is not None:
            for curso, materia, _ini in nocturno.classes_for(horario.items, day):
                c = prepare_class(curso, materia, folder)
                rep["clases"].append(c)
                if not c["ok"]:
                    rep["fallos"].append(f"{curso or materia} ({c['fallo']})")
        elif horario.items:
            rep["fallos"].append("las clases (la IA no estaba conectada)")
        if J.settings.get("night_grade", True) and J.state.get("ai") == "ok":
            try:
                n, ap = grade_pending(day.strftime("%d-%m"))
                rep["calificadas"], rep["aprobar"] = n, rep["aprobar"] + ap
            except Exception as e:
                rep["fallos"].append(f"calificar ({str(e)[:60]})")
        if J.settings.get("night_parents", True):
            try:
                m = draft_parent_messages(folder)
                rep["mensajes"], rep["aprobar"] = m, rep["aprobar"] + m
            except Exception as e:
                rep["fallos"].append(f"los mensajes ({str(e)[:60]})")
        _night_save(rep)
        _mark("night_last", now.date().isoformat() if mode == "noche" else (now.date() - datetime.timedelta(days=1)).isoformat())
        files = [f for c in rep["clases"] for f in c["archivos"]]
        for f in files[-6:]:
            J.generated_files.add(f)
        line = nocturno.morning_line(dict(rep, hola=False))
        if line:
            J.notice_add("Turno de noche: " + line, "aviso", "TURNO DE NOCHE")
            try:
                bitacora.add("Turno de noche: " + line, "turno")       # «Lo que hice hoy»
            except Exception:
                pass
        if say:
            J.notify((line or "Terminé el turno, pero no había nada que preparar (¿tienes el horario en Ajustes?).")
                     + (" Todo está en Documentos, Jarvis, Turno de noche." if files else ""), "TURNO DE NOCHE")
        return rep
    finally:
        night["busy"] = False


def night_morning_line():
    """Para el saludo de la mañana: lo que dejó listo anoche (una sola vez)."""
    rep = night["report"] or load_report()
    if not rep or rep.get("dicho"):
        return ""
    today = datetime.date.today().isoformat()
    if rep.get("para") != today and rep.get("fecha") not in (today, (datetime.date.today() - datetime.timedelta(days=1)).isoformat()):
        return ""
    rep["dicho"] = True
    rep["aprobar"] = sum(1 for i in J.aprobaciones.pending() if i["tipo"] in ("notas", "mensaje"))
    _night_save(rep)
    return nocturno.morning_line(dict(rep, hola=False))


def night_tick(now=None):
    now = now or datetime.datetime.now()
    first = horario.today(now)
    mode = nocturno.due(now, J.settings.get("night_shift", False), int(J.settings.get("night_hour", 21)), J.settings.get("night_last", ""),
                        first[0]["inicio"] if first else None)
    if not mode or night["busy"]:
        return ""
    J.log_terminal(f"Turno de noche ({mode}): preparo las clases, califico y redacto.", "TURNO DE NOCHE")
    threading.Thread(target=run_night, kwargs={"mode": mode, "say": mode == "madrugada"}, daemon=True, name="turno-noche").start()
    return mode


def _night_worker():
    time.sleep(120)
    while True:
        try:
            J.night_tick()
        except Exception as e:
            J.note_error("TURNO DE NOCHE", e)
        time.sleep(300)


_NS_ON = re.compile(r"\b(?:activa|enciende|prende|habilita)\s+(?:el\s+)?turno de noche\b|\btrabaja (?:esta noche|de noche|mientras duermo|en la noche)\b")
_NS_OFF = re.compile(r"\b(?:desactiva|apaga|quita|deshabilita)\s+(?:el\s+)?turno de noche\b|\bno trabajes (?:esta noche|de noche|en la noche)\b")
_NS_NOW = re.compile(r"\b(?:haz|hazme|corre|lanza|empieza)\s+(?:el\s+)?turno de noche(?:\s+(?:ya|ahora|ahorita))?\b|"
                     r"\b(?:deja|dejame|alista|alistame)\s+(?:listas?|lista)\s+(?:las\s+)?clases de manana\b")
_NS_ASK = re.compile(r"\bque (?:me )?dejaste (?:listo|preparado)\b|\bque hiciste (?:anoche|esta noche|en la noche)\b|\bcomo te fue (?:anoche|en el turno)\b")
_NS_WHERE = re.compile(r"\babre (?:la carpeta del|el)\s+turno de noche\b")


def night_voice(text, t):
    if _NS_OFF.search(t):
        _mark("night_shift", False)
        J.reply("Listo, ya no trabajo de noche. Cuando quieras: «activa el turno de noche».", "TURNO DE NOCHE")
        return True
    if _NS_ON.search(t):
        _mark("night_shift", True)
        h = int(J.settings.get("night_hour", 21))
        J.reply(f"Turno de noche activado: desde las {h % 12 or 12} {'p. m.' if h >= 12 else 'a. m.'} preparo las clases del día siguiente según tu horario "
                "(plan, evaluación corta y diapositivas), califico las fotos que dejes en Documentos, Jarvis, Por calificar, una carpeta por curso, "
                "y redacto los mensajes a padres. Nada se guarda ni se envía sin tu aprobación. Deja el equipo encendido "
                "(si está apagado, lo hago temprano en la mañana).", "TURNO DE NOCHE")
        os.makedirs(pending_dir(), exist_ok=True)
        return True
    if _NS_NOW.search(t):
        if night["busy"]:
            J.reply("Ya estoy en el turno; te aviso al terminar.", "TURNO DE NOCHE")
            return True
        if not horario.items and J.state.get("ai") == "ok":
            J.reply("No tengo tu horario, así que no sé qué clases preparar. Escríbelo en Ajustes › Aula y colegio › Horario.", "TURNO DE NOCHE")
        J.reply("Empiezo el turno ahora: preparo las clases del próximo día de clases, califico lo pendiente y redacto los mensajes. Te aviso.",
                "TURNO DE NOCHE")
        J.start_job("Turno de noche", lambda: run_night(say=True), "turno-noche")
        return True
    if _NS_ASK.search(t):
        rep = night["report"] or load_report()
        line = nocturno.morning_line(dict(rep or {}, hola=False)) if rep else ""
        J.reply(line or "Anoche no hice el turno. Actívalo con «activa el turno de noche» o dime «haz el turno de noche ahora».", "TURNO DE NOCHE")
        return True
    if _NS_WHERE.search(t):
        rep = night["report"] or load_report()
        if rep and os.path.isdir(rep.get("carpeta", "")) and J.IS_WIN:
            try:
                os.startfile(rep["carpeta"])
            except OSError:
                pass
        J.reply("Abrí la carpeta del turno de noche." if rep else "Todavía no hay turno de noche.", "TURNO DE NOCHE")
        return True
    return False


def night_start():
    load_report()
    threading.Thread(target=J._night_worker, daemon=True, name="turno-noche").start()


__all__ = ['_NS_ASK', '_NS_NOW', '_NS_OFF', '_NS_ON', '_NS_WHERE', '_mark', '_night_worker', '_parent_message', '_quiet_material', '_report_path',
           '_night_save', '_ttl_until_noon', 'class_topic', 'draft_parent_messages', 'grade_pending', 'load_report', 'night', 'night_morning_line',
           'night_start', 'night_tick', 'night_voice', 'nocturno', 'pending_dir', 'prepare_class', 'run_night']
