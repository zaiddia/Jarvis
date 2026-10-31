"""9.8: la semana lista el domingo, el cierre de periodo automático y la bandeja limpia (respuestas de correo
redactadas en la mañana, esperando tu aprobación).

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import re
import threading
import time

import aula
import bandeja
import compromisos
import diarioclase
import exportar
import horario
import proyectos
import semana
import seguimiento
from nucleo import J


def _mark_day(key, value):
    J.settings[key] = value
    try:
        J.save_settings_file()
    except OSError:
        pass


# ============================================================================ SEMANA LISTA
def week_topic(course):
    """El siguiente tema de la malla del curso o, sin malla, «continuación» del último tema del diario de clase."""
    p = diarioclase.pending(course)
    if p and p[1]:
        return p[1][0]["tema"]
    e = diarioclase.entries(course)
    if e:
        return f"continuación de {e[-1]['tema']}"
    return ""


def week_brief(monday):
    """Lo que viene la semana: clases, compromisos y alertas tempranas."""
    cs = semana.courses_of_week(horario.items)
    out = []
    if cs:
        out.append(f"{sum(c['sesiones'] for c in cs.values())} clases en {len(cs)} curso{'s' if len(cs) != 1 else ''}")
    end = monday + datetime.timedelta(days=6)
    due = [x for x in compromisos.pending() if x.get("fecha") and monday.isoformat() <= x["fecha"] <= end.isoformat()]
    if due:
        out.append("compromisos: " + "; ".join(x["texto"][:60] for x in due[:4]))
    try:
        al = [a for a in J.early_alerts() if a["tipo"] != "mejora"]
        if al:
            out.append("ojo con " + ", ".join(f"{a['estudiante']} ({a['curso']})" for a in al[:4]))
    except Exception:
        pass
    return out


def propose_week(today=None, say=True):
    """Arma el proyecto de la semana desde el horario y la malla, y pide aprobación. Devuelve el plan (o None)."""
    today = today or datetime.date.today()
    monday = semana.next_monday(today) if today.weekday() >= 4 else today - datetime.timedelta(days=today.weekday())
    if not horario.items:
        if say:
            J.reply("Para prepararte la semana necesito tu horario (Ajustes › Memoria › Horario, o dime «los lunes de 7 a 8 "
                    "tengo 7A matemáticas»).", "SEMANA")
        return None
    plan, sin_tema = semana.week_plan(horario.items, J.week_topic, monday, J.settings["week_prep_quiz"])
    brief = J.week_brief(monday)
    if not plan["pasos"]:
        if say:
            J.reply("No sé qué tema toca en ningún curso: guarda la malla del periodo («haz la malla de 7A…») o anota lo que "
                    "ves en el diario de clase, y la próxima vez te preparo la semana sola.", "SEMANA")
        return None

    def go():
        st = proyectos.new("prepárame la semana", plan, J.settings["output_dir"])
        J.reply(f"Preparo «{plan['nombre']}»: {len(plan['pasos'])} materiales. Te aviso cuando estén.", "SEMANA")
        J.run_project(st)
    extra = (f" Sin tema: {', '.join(sin_tema)}." if sin_tema else "") + (" La semana: " + "; ".join(brief) + "." if brief else "")
    J.request_approval("proyecto", f"Preparar la semana del {monday:%d/%m} ({len(plan['pasos'])} materiales)",
                       proyectos.spoken_plan(plan) + extra, on_ok=go,
                       on_no=lambda: J.reply("Vale, no preparo la semana.", "SEMANA"), ttl=36 * 3600,
                       say=f"Te propongo preparar la semana del {monday:%d/%m}: " + "; ".join(p["titulo"] for p in plan["pasos"]
                                                                                             if p["tipo"] == "plan") +
                           (", con su evaluación corta" if J.settings["week_prep_quiz"] else "") + "." + extra + " ¿La preparo? Di «sí» o «no».")
    return plan


def week_prep_tick(now=None):
    now = now or datetime.datetime.now()
    if not J.settings["week_prep"] or now.weekday() != 6 or now.hour < J.settings["week_prep_hour"]:
        return None
    if J.settings["week_prep_last"] == now.date().isoformat() or J.project_run["busy"]:
        return None
    _mark_day("week_prep_last", now.date().isoformat())
    return J.propose_week(now.date())


_WK_RE = re.compile(r"^(?:jarvis\s+)?(?:preparame|prepara|preparemos|alista|alistame|deja lista|dejame lista)\s+(?:toda\s+)?la\s+(?:proxima\s+)?semana"
                    r"(?:\s+(?:que viene|siguiente|entrante))?$")
_WK_BRIEF = re.compile(r"\bcomo viene la (?:proxima )?semana\b|\bque (?:me )?viene la (?:proxima )?semana\b|\bresumen de la (?:proxima )?semana que viene\b|"
                       r"\bresumen de la proxima semana\b")


def week_voice(text, t):
    if _WK_RE.match(t):
        J.propose_week()
        return True
    if _WK_BRIEF.search(t):
        today = datetime.date.today()
        monday = semana.next_monday(today)
        b = J.week_brief(monday)
        topics = [f"{c}: {J.week_topic(c)}" for c in semana.courses_of_week(horario.items) if J.week_topic(c)]
        J.reply(f"La semana del {monday:%d/%m}: " + ("; ".join(b) if b else "aún no tengo tu horario") +
                (". Temas que tocan: " + "; ".join(topics[:6]) if topics else "") + ". Si quieres, «prepárame la semana».", "SEMANA")
        return True
    return False


# ============================================================================ CIERRE DE PERIODO
def _period_courses():
    return sorted(set(aula.data.get("cursos", {})) | set(seguimiento.data))


def _period_names(course):
    names = list(aula.data.get("cursos", {}).get(course, []))
    return names + [n for n in seguimiento.data.get(course, {}) if n not in names]


def period_summaries():
    out = []
    for c in _period_courses():
        p = diarioclase.pending(c)
        out.append(semana.course_summary(c, _period_names(c), seguimiento.data.get(c, {}), J._absences(c), J.settings["risk_grade"],
                                         J.settings["risk_absences"], [s["tema"] for s in (p[1] if p else [])]))
    return out


def close_period(say=True):
    """Consolidado en Word + planilla de Zeti de cada curso. Devuelve las rutas."""
    sums = J.period_summaries()
    if not sums:
        if say:
            J.reply("No tengo cursos con estudiantes ni notas para cerrar el periodo.", "CIERRE")
        return []
    if J.Document is None:
        J.reply("No puedo crear documentos: falta python-docx.", "ERROR")
        return []
    name = J.settings["period_name"].strip() or "Cierre de periodo"
    paths = [semana.close_docx(sums, J.settings["output_dir"], J.Document, f"Cierre - {name}" if J.settings["period_name"].strip() else name,
                               J.settings["aula_docente"], J.settings["aula_institucion"])]
    for s in sums:
        names = _period_names(s["curso"])
        if names and seguimiento.data.get(s["curso"]):
            p, _n, _a = exportar.zeti_xlsx(s["curso"], names, seguimiento.data.get(s["curso"], {}), J._absences(s["curso"]),
                                           J.settings["output_dir"], J.settings["zeti_since"], J.settings["zeti_order"],
                                           J.settings["zeti_comma"], J.settings["aula_institucion"], J.settings["aula_docente"])
            paths.append(p)
    for p in paths:
        J.generated_files.add(p)
    J._open_doc(paths[0])
    risk = [s for s in sums if s["riesgo"]]
    if J.settings["period_end"]:
        _mark_day("period_closed", J.settings["period_end"])
        try:                                           # el siguiente periodo empieza al día siguiente (para Zeti)
            nxt = datetime.date.fromisoformat(J.settings["period_end"]) + datetime.timedelta(days=1)
            _mark_day("zeti_since", nxt.isoformat())
        except ValueError:
            pass
    if say:
        J.reply(f"Cerré el periodo: el consolidado de {len(sums)} curso{'s' if len(sums) != 1 else ''} y {len(paths) - 1} planilla"
                f"{'s' if len(paths) - 1 != 1 else ''} para Zeti, en Documentos, Jarvis, Cierre de periodo." +
                (" Para quienes deben recuperar: " + "; ".join(f"«haz los planes de recuperación de {s['curso']}»" for s in risk[:3]) + "."
                 if risk else " Nadie quedó en riesgo. 🎉"), "CIERRE")
    return paths


def period_tick(today=None):
    today = today or datetime.date.today()
    s = J.settings
    left = semana.days_left(s["period_end"], today)
    if left is None or s["period_closed"] == s["period_end"] or s["period_warned"] == today.isoformat():
        return None
    if left in (7, 3):
        _mark_day("period_warned", today.isoformat())
        msg = semana.spoken_close(J.period_summaries(), left) + " Revisa quién no tiene notas y, si quieres, pide los planes de recuperación."
        J.notice_add(msg, "aviso", "CIERRE")
        J.push_chat("jarvis", msg, "CIERRE")
        return "aviso"
    if left <= 0:
        _mark_day("period_warned", today.isoformat())
        J.request_approval("cierre", f"Cerrar {s['period_name'].strip() or 'el periodo'}", semana.spoken_close(J.period_summaries(), 0),
                           on_ok=lambda: J.close_period(), on_no=lambda: None, ttl=20 * 3600,
                           say="Hoy cierra el periodo. ¿Preparo el consolidado de notas y las planillas para Zeti? Di «sí» o «no».")
        return "cierre"
    return None


_PE_SET = re.compile(r"\b(?:el )?periodo (?:termina|cierra|acaba|se cierra|finaliza|va hasta)\s+(?:el\s+)?(.+)$|"
                     r"\b(?:el )?cierre (?:del|de) periodo es (?:el\s+)?(.+)$")
_PE_CLOSE = re.compile(r"^(?:jarvis\s+)?(?:cierra|cerremos|haz el cierre del?|haz el cierre de|prepara el cierre del?)\s+(?:el\s+)?periodo\b")
_PE_ASK = re.compile(r"\bcuanto falta para (?:cerrar|el cierre del?|que (?:cierre|termine)) (?:el\s+)?periodo\b|\bcomo voy con el cierre\b|"
                     r"\bcomo va el periodo\b")


def period_voice(text, t):
    m = _PE_SET.search(t)
    if m:
        d = semana.parse_date(m.group(1) or m.group(2) or "")
        if not d:
            J.reply("¿Qué fecha? Por ejemplo: «el periodo termina el 28 de noviembre».", "CIERRE")
            return True
        _mark_day("period_end", d.isoformat())
        _mark_day("period_warned", "")
        J.reply(f"Anotado: el periodo cierra el {d.day} de {semana.MESES[d.month - 1]}. Te aviso una semana antes y ese día te "
                "propongo el consolidado y las planillas para Zeti.", "CIERRE")
        return True
    if _PE_CLOSE.match(t):
        J.reply("Preparo el cierre del periodo…", "CIERRE")
        if getattr(J._tl, "capture", None) is not None:
            J.close_period()
        else:
            J.start_job("Cerrando el periodo", J.close_period, "cierre")
        return True
    if _PE_ASK.search(t):
        J.reply(semana.spoken_close(J.period_summaries(), semana.days_left(J.settings["period_end"])), "CIERRE")
        return True
    return False


# ============================================================================ BANDEJA LIMPIA
_DRAFT_HINT = ("Responde lo que corresponda según el correo. Si hace falta un dato que solo yo sé (una fecha, una nota, una "
               "decisión), déjalo entre [corchetes] para que lo complete.")


def _draft_send(m, asunto, cuerpo):
    try:
        J.mail_send(m["de"], asunto, cuerpo, in_reply_to=m.get("msgid", ""))
        compromisos.mark_answered(m)
        J.learn_style(cuerpo, "respuesta")
        J.reply(f"Respuesta enviada a {m['de_nombre']}.", "CORREO")
    except RuntimeError as e:
        J.reply(f"No pude enviar la respuesta a {m['de_nombre']}: {e}", "CORREO")


def inbox_drafts(force=False, say=False):
    """Redacta las respuestas de los correos que piden respuesta y las deja por aprobar. Devuelve cuántas."""
    if not (J.settings["email_read"] and J.mail_method()) or J.state.get("ai") != "ok":
        if say:
            J.reply("Para redactar respuestas necesito el correo conectado (Ajustes › Integraciones › Correo) y la IA.", "CORREO")
        return 0
    try:
        msgs = J._mail_fetch(force=True)
    except RuntimeError as e:
        if say:
            J.reply(f"No pude revisar tu correo: {e}", "CORREO")
        return 0
    pend_titles = {a["titulo"] for a in J.aprobaciones.pending()}
    owe = compromisos.to_answer(msgs, J.settings["email_address"])[:J.settings["inbox_max"]]
    n = 0
    for m in owe:
        asunto = m["asunto"] if m["asunto"].lower().startswith(("re:", "re ")) else "Re: " + m["asunto"]
        title = f"Responder a {m['de_nombre']} («{asunto[:60]}»)"
        if title in pend_titles:
            continue
        try:
            raw = J.ai_chat([{"role": "user", "content": bandeja.reply_prompt(m, _DRAFT_HINT, J.settings["email_sender_name"]) + J.style_ctx()}],
                            json_mode=True, max_tokens=900)
            cuerpo = str(J._extract_json(raw).get("cuerpo", "")).strip()
        except Exception:
            continue
        if not cuerpo:
            continue
        J.request_approval("correo", title, cuerpo, on_ok=lambda m=m, a=asunto, c=cuerpo: J._draft_send(m, a, c),
                           on_no=lambda: None, ttl=16 * 3600, quiet=True)
        n += 1
    if n:
        msg = (f"Te dejé {n} respuesta{'s' if n != 1 else ''} de correo lista{'s' if n != 1 else ''} para revisar: " +
               ", ".join(m["de_nombre"][:24] for m in owe[:n]) + ". Míralas en «por aprobar» (o di «¿qué tengo por aprobar?»): "
               "las envío solo si dices «sí».")
        J.notice_add(msg, "aviso", "CORREO")
        J.push_chat("jarvis", msg, "CORREO") if not say else J.reply(msg, "CORREO")
    elif say:
        J.reply("No hay correos que pidan respuesta ahora mismo. Bandeja limpia. 👌", "CORREO")
    return n


def inbox_tick(now=None):
    now = now or datetime.datetime.now()
    if not J.settings["inbox_drafts"] or now.weekday() >= 5 or now.hour < J.settings["inbox_hour"] or now.hour >= 12:
        return None
    if J.settings["inbox_last"] == now.date().isoformat() or J.is_offline():
        return None
    _mark_day("inbox_last", now.date().isoformat())
    return J.inbox_drafts()


_IN_RE = re.compile(r"\b(?:redactame|redacta|preparame|prepara|escribeme|haz|hazme)\s+(?:las\s+)?respuestas?\s+(?:de|a|para)\s+(?:mis|los)\s+correos\b|"
                    r"\blimpia (?:mi|la) bandeja\b|\bbandeja limpia\b")


def inbox_voice(text, t):
    if not _IN_RE.search(t):
        return False
    J.reply("Reviso tu correo y redacto las respuestas…", "CORREO")
    if getattr(J._tl, "capture", None) is not None:
        J.inbox_drafts(say=True)
    else:
        J.start_job("Redactando respuestas de correo", lambda: J.inbox_drafts(say=True), "bandeja")
    return True


# ============================================================================ ARRANQUE
def _weekly_routines_worker():
    time.sleep(180)
    while True:
        for fn in (J.week_prep_tick, J.period_tick, J.inbox_tick):
            try:
                fn()
            except Exception as e:
                J.note_error("RUTINAS", e)
        time.sleep(300)


def routines98_start():
    threading.Thread(target=J._weekly_routines_worker, daemon=True, name="rutinas-semana").start()


__all__ = ['_DRAFT_HINT', '_IN_RE', '_PE_ASK', '_PE_CLOSE', '_PE_SET', '_WK_BRIEF', '_WK_RE', '_draft_send', '_mark_day', '_period_courses',
           '_period_names', '_weekly_routines_worker', 'close_period', 'inbox_drafts', 'inbox_tick', 'inbox_voice', 'period_summaries',
           'period_tick', 'period_voice', 'propose_week', 'routines98_start', 'week_brief', 'week_prep_tick', 'week_topic', 'week_voice']
