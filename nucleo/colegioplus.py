"""12.12: recuperaciones con seguimiento, calendario escolar (festivos de Colombia), detector de copia, juegos de matemáticas
para imprimir y dificultad medida de las preguntas del banco.

- «¿Quiénes deben recuperar?», «¿cómo van las recuperaciones de 7A?», «Ana Gómez entregó la recuperación», «Ana Gómez sacó 3,5
  en la recuperación». Los planes («haz los planes de recuperación de 7A») quedan en seguimiento con su fecha límite.
- «¿Cuándo es el próximo festivo?», «¿mañana hay clase?», «semana de receso del 6 al 10 de octubre», «entrega de notas a
  coordinación el 20 de noviembre», «¿qué hay en el calendario escolar?», «borra del calendario la reunión de padres».
- «¿Hay copia en las entregas de 8A?», o sube varios trabajos con el clip y pulsa «Detectar copia».
- «Haz un bingo de fracciones para 7A», «dominó de enteros», «parejas de potencias».
- «¿Qué tan difíciles son mis preguntas de fracciones?», «haz un examen equilibrado de fracciones de 10 preguntas».
Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import os
import re
import threading
import time

import adjuntos
import aula
import banco
import copia
import entregas
import examenes
import festivos
import juegos
import salon
import seguimiento
import zeti
from nucleo import J


# ============================================================================ 1. RECUPERACIONES
_RC_WHO = re.compile(r"\b(?:quienes|quien|que estudiantes|cuales estudiantes)\s+(?:deben|tienen que|van a|necesitan)\s+(?:recuperar|hacer (?:la )?recuperacion)"
                     r"(?:\s+(?:en|de)\s+(.+))?$")
_RC_HOW = re.compile(r"\bcomo van (?:las )?recuperaciones(?:\s+(?:de|en)\s+(.+))?$|\b(?:estado|seguimiento) de (?:las )?recuperaciones(?:\s+(?:de|en)\s+(.+))?$")
_RC_DONE = re.compile(r"^(?:jarvis\s+)?(.+?)\s+(?:ya\s+)?entrego\s+(?:la\s+|el\s+)?(?:recuperacion|taller de recuperacion|plan de recuperacion)$")
_RC_NOTE = re.compile(r"^(?:jarvis\s+)?(.+?)\s+(?:saco|tuvo|obtuvo|tiene)\s+(\d(?:\s+\d)?)\s+en\s+(?:la\s+)?recuperacion$")


def period_vals(course):
    """{estudiante: valoración del periodo como en Zeti} del curso (todas sus asignaturas juntas, la más baja)."""
    J.zeti_apply()
    since = J.settings.get("zeti_since", "")
    out = {}
    for key, ests in seguimiento.data.items():
        if aula.course_key(key.split(" · ")[0]) != aula.course_key(course):
            continue
        for est, notas in ests.items():
            v = zeti.valoracion([n for n in notas if str(n.get("fecha", "")) >= since], zeti.WEIGHTS)["val"]
            if v is not None:
                out[est] = min(out.get(est, 9), v)
    return out


def register_plans(course, names):
    """Lo llama el generador de planes de recuperación: cada uno queda en seguimiento con su fecha límite."""
    vals = period_vals(course)
    limit = datetime.date.today() + datetime.timedelta(days=int(J.settings.get("recovery_days", 10)))
    for n in names:
        salon.recup_open(course, n, vals.get(n), limit)


def _rc_course(target):
    target = (target or "").strip()
    return J._resolve_course(target) if target else ""


def recovery_track_voice(text, t):
    m = _RC_WHO.search(t)
    if m:
        courses = [_rc_course(m.group(1))] if m.group(1) else sorted({k.split(" · ")[0] for k in seguimiento.data}, key=aula.course_sort_key)
        parts = []
        for c in courses:
            risk = salon.at_risk(period_vals(c), J.settings.get("risk_grade", 3.0))
            if risk:
                parts.append(f"{c}: " + ", ".join(f"{e} ({str(round(v, 1)).replace('.', ',')})" for e, v in risk[:12]))
        J.reply(("Por debajo de 3,0 en el periodo: " + "; ".join(parts) + ". Para armar sus planes: «haz los planes de recuperación de " +
                 courses[0] + "»." if parts else "Nadie está por debajo de 3,0 en el periodo."), "RECUPERACIÓN")
        return True
    m = _RC_HOW.search(t)
    if m:
        c = _rc_course(m.group(1) or m.group(2) or "")
        s = salon.recup_summary(c or None)
        if not s:
            J.reply("No hay recuperaciones abiertas. Se abren al hacer los planes («haz los planes de recuperación de 7A»).", "RECUPERACIÓN")
            return True
        parts = []
        for cur, x in s.items():
            bits = [f"{len(x['aprobada'])} aprobaron"] if x["aprobada"] else []
            bits += [f"{len(x['entregado'])} entregaron y esperan nota"] if x["entregado"] else []
            bits += [f"{len(x['pendiente'])} pendientes" + (f" ({len(x['vencidas'])} vencidas: {', '.join(x['vencidas'][:5])})" if x["vencidas"] else "")] \
                if x["pendiente"] else []
            bits += [f"{len(x['no_aprobada'])} no aprobaron"] if x["no_aprobada"] else []
            parts.append(f"{cur}: " + ", ".join(bits))
        J.reply("Recuperaciones — " + "; ".join(parts) + ".", "RECUPERACIÓN")
        return True
    for rx, kind in ((_RC_NOTE, "nota"), (_RC_DONE, "entrega")):
        m = rx.match(t)
        if not m:
            continue
        course, name = J._student_or_ask(m.group(1), "RECUPERACIÓN")
        if not name:
            return True
        if kind == "entrega":
            r = salon.recup_delivered(course, name)
            J.reply(f"Anotado: {name} entregó la recuperación. Cuando la califiques, di «{name.split()[0]} sacó 3,5 en la recuperación»."
                    if r else f"{name} no tiene una recuperación abierta en {course}.", "RECUPERACIÓN")
        else:
            nota = float(m.group(2).replace(" ", "."))          # «3,5» llega como «3 5» (sin signos)
            r = salon.recup_result(course, name, nota)
            if not r:
                J.reply(f"{name} no tiene una recuperación abierta en {course}.", "RECUPERACIÓN")
                return True
            seguimiento.add(course, name, "Recuperación", nota, origen="recuperacion")
            J.reply(f"{name}: {str(nota).replace('.', ',')} en la recuperación, " + ("¡aprobó!" if r["estado"] == "aprobada" else "no aprobó todavía.")
                    + " Quedó en sus notas.", "RECUPERACIÓN")
        return True
    return False


# ============================================================================ 3. CALENDARIO ESCOLAR
_CAL_NEXT = re.compile(r"\b(?:cuando es el|cual es el) (?:proximo )?festivo\b|\bproximo festivo\b|\bque festivos hay\b(?:\s+(?:en|este)\s+(.+))?")
_CAL_CLASS = re.compile(r"\b(?:hay|habra) clases?\b\s+(.+?)$|\bes festivo\b\s*(.*)$|\b(.+?)\s+es festivo$|^(.+?)\s+(?:hay|habra) clases?$")
_CAL_ADD = re.compile(r"^(?:jarvis\s+)?(?:anota|agrega|pon|registra|apunta)?\s*(?:en el calendario(?: escolar)?\s+)?((?:semana de |la semana de )?(?:receso|vacaciones|"
                      r"cierre|entrega|reunion|izada|consejo|comite|escuela de padres|jornada|semana institucional|semana de desarrollo|evaluaciones finales|"
                      r"entrega de notas|entrega de boletines)\b.*?)\s+(?:el|del|los dias del|desde el)\s+(.+)$")
_CAL_LIST = re.compile(r"\bque hay en el calendario escolar\b|\b(?:mi |el )?calendario escolar\b$|\bque viene en el colegio\b|\bproximas fechas del colegio\b")
_CAL_DEL = re.compile(r"^(?:jarvis\s+)?(?:borra|quita|elimina)\s+del calendario(?: escolar)?\s+(?:el|la|los|las)?\s*(.+)$")


def _orig_words(text, frag):
    """Las palabras de lo que dijiste (con tildes) que corresponden al trozo normalizado."""
    ow = re.findall(r"\w+", str(text))
    nw = [J.normalize(w) for w in ow]
    fw = frag.split()
    for i in range(len(nw) - len(fw) + 1):
        if nw[i:i + len(fw)] == fw:
            return " ".join(ow[i:i + len(fw)])
    return frag


def school_calendar_voice(text, t):
    today = datetime.date.today()
    m = _CAL_NEXT.search(t)
    if m:
        nxt = festivos.next_holidays(today, 3)
        J.reply("Próximos festivos: " + "; ".join(f"{name}, {festivos.spoken(d, today)}" for d, name in nxt) + ".", "CALENDARIO")
        return True
    m = _CAL_ADD.match(t)
    if m:
        what = _orig_words(text, m.group(1).strip())
        rng = festivos.parse_range("del " + m.group(2) if not m.group(2).startswith("del") else m.group(2), today) or \
            festivos.parse_range(t, today)
        d = None if rng else festivos.parse_date(m.group(2), today)
        if not (rng or d):
            J.reply("¿Qué fecha? Por ejemplo: «entrega de notas a coordinación el 20 de noviembre» o «receso del 6 al 10 de octubre».",
                    "CALENDARIO")
            return True
        a, b = rng if rng else (d, d)
        ev = festivos.add_event(what[0].upper() + what[1:], a, b)
        warn = [f"{festivos.spoken(x, today)} es festivo ({festivos.holiday(x)})" for x in (a, b) if festivos.holiday(x)]
        J.reply(f"Anotado en el calendario escolar: {festivos.describe(ev, today)}." + (" Ojo: " + " y ".join(warn) + "." if warn else "")
                + " Te aviso con tiempo.", "CALENDARIO")
        return True
    m = _CAL_DEL.match(t)
    if m:
        ev = festivos.remove_event(m.group(1))
        J.reply(f"Borré del calendario: {ev['titulo']}." if ev else "No encontré eso en el calendario escolar.", "CALENDARIO")
        return True
    if _CAL_LIST.search(t):
        evs = festivos.events_between(today, today + datetime.timedelta(days=45))
        hol = [(d, n) for d, n in festivos.next_holidays(today, 6) if d <= today + datetime.timedelta(days=45)]
        parts = [festivos.describe(e, today) for e in evs] + [f"festivo de {n} {festivos.spoken(d, today)}" for d, n in hol]
        J.reply("En las próximas semanas: " + "; ".join(parts) + "." if parts else
                "No hay nada en las próximas semanas. Agrega fechas: «entrega de notas a coordinación el 20 de noviembre».", "CALENDARIO")
        return True
    m = _CAL_CLASS.search(t)
    if m:
        frag = next((g for g in m.groups() if g), "") or "hoy"
        d = festivos.parse_date(frag, today)
        if not d:
            return False
        why = festivos.no_class(d)
        evs = [e["titulo"] for e in festivos.events_between(d, d) if e["tipo"] != "receso"]
        J.reply((f"{festivos.spoken(d, today)[0].upper() + festivos.spoken(d, today)[1:]} no hay clase: {why}." if why else
                 f"Sí, {festivos.spoken(d, today)} hay clase.") + (f" Además: {', '.join(evs)}." if evs else ""), "CALENDARIO")
        return True
    return False


def date_warning(d):
    """Para agendar: «Ojo: ese día es festivo (…)» o ""."""
    try:
        why = festivos.no_class(d)
    except Exception:
        return ""
    return f" Ojo: ese día {why}." if why and d.weekday() < 5 else ""


# ============================================================================ 7. DETECTOR DE COPIA
_COPY = re.compile(r"\b(?:hay|detecta|busca|revisa si hay|revisa)\s+(?:la\s+)?(?:copia|copiados?|plagio|trabajos? (?:iguales|copiados))\b"
                   r"(?:\s+(?:en|entre)\s+(?:las\s+|los\s+)?(entregas|trabajos|programas|archivos)?(?:\s+(?:de|del)\s+(.+))?)?|\bse copiaron\b(?:\s+(?:en|de)\s+(.+))?")


def _copy_report(title, pairs, total):
    from docx import Document
    doc = Document()
    doc.add_heading(f"Detector de copia: {title}", 1)
    doc.add_paragraph(f"{total} trabajos comparados · {datetime.date.today():%d/%m/%Y}. El porcentaje es la parte del trabajo más corto que "
                      "aparece igual en el otro. Parecido no siempre es copia: revisa las partes iguales antes de decidir.")
    gs = copia.groups(pairs)
    if gs:
        doc.add_heading("Grupos casi iguales", 2)
        for g in gs:
            doc.add_paragraph(", ".join(g), style="List Bullet")
    doc.add_heading("Pares", 2)
    if not pairs:
        doc.add_paragraph("Ningún par se parece demasiado.")
    for p in pairs:
        doc.add_heading(f"{p['a']} y {p['b']}: {p['parecido']} % ({p['nivel']})", 3)
        for part in p["partes"]:
            doc.add_paragraph("«" + part + "»", style="List Bullet")
    folder = os.path.join(J.settings["output_dir"], "Copia")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, re.sub(r'[<>:"/\\|?*]+', " ", f"Copia {title} {datetime.datetime.now():%Y-%m-%d %H%M}.docx"))
    doc.save(path)
    J.generated_files.add(path)
    return path


def copy_check_files(its):
    docs = {}
    code = all(str(i["nombre"]).lower().endswith(J.codigo.CODE_EXTS) for i in its)
    for it in its:
        try:
            docs[it["nombre"]] = adjuntos.text_of(it, 400000)
        except Exception:
            docs[it["nombre"]] = ""
    pairs = copia.compare(docs, code=code)
    path = _copy_report("archivos subidos", pairs, len([d for d in docs.values() if d.strip()]))
    return copia.spoken(pairs, len(docs)) + " Informe en Documentos › Jarvis › Copia.", path


def copy_voice(text, t):
    m = _COPY.search(t)
    if not m:
        return False
    target = (m.group(2) or m.group(3) or "").strip()
    rec = adjuntos.recent(1800)
    if not target and len(rec) >= 2 and m.group(1) != "entregas":
        J.reply(f"Comparo los {len(rec)} archivos que subiste…", "COPIA")
        J.start_job("Buscando copia", lambda: J.notify(copy_check_files(rec)[0], "COPIA"), "copia")
        return True
    course = J._resolve_course(target) if target else ""
    tasks = [x for x in entregas.data.get("tareas", {}).values() if not course or aula.course_key(x["curso"].split(" · ")[0]) == aula.course_key(course)]
    if not tasks:
        J.reply("No tengo entregas para comparar" + (f" de {course}" if course else "") + ". Abre unas entregas («recibe los programas de 8A») o sube "
                "varios trabajos con el clip y di «detecta copia».", "COPIA")
        return True
    task = max(tasks, key=lambda x: x.get("creado", ""))
    docs = {}
    for est, subs in (task.get("entregas") or {}).items():
        last = subs[-1] if isinstance(subs, list) and subs else subs
        if isinstance(last, dict) and (last.get("texto") or last.get("codigo")) and last.get("tipo", "codigo") != "foto":
            docs[est] = last.get("texto") or last.get("codigo")
    pairs = copia.compare(docs, code=True)
    path = _copy_report(f"entregas {task['curso']}", pairs, len(docs))
    J.reply(copia.spoken(pairs, len(docs)) + " Te dejé el informe en Documentos › Jarvis › Copia.", "COPIA")
    J._open_doc(path)
    return True


# ============================================================================ 8. JUEGOS PARA IMPRIMIR
_GAME = re.compile(r"\b(?:haz|hazme|crea|creame|genera|prepara|preparame|arma|armame|imprime|dame)?\s*(?:un|una|unas)?\s*"
                   r"(bingo|domino|parejas|juego de parejas|memoria|memorama|concentrese)\s+(?:de|con|sobre)\s+(.+?)(?:\s+(?:para|de)\s+(\d{1,2}\s*[a-z]?|\S+\s*\d+))?$")


def make_game(game, tema, curso=""):
    topic = juegos.topic_of(tema)
    n = {"bingo": 30, "domino": 24, "parejas": 18}[game]
    grade = aula.grade_of(curso) if curso else 0
    pairs = juegos.generate(topic, n, level=2 if (grade or 0) >= 8 else 1) if topic else []
    if not topic:
        raw = J.ai_chat([{"role": "user", "content": juegos.ai_prompt(tema, n + 6, f"{grade}°" if grade else "")}], json_mode=True, max_tokens=3000)
        pairs = juegos.ai_validate(J._extract_json(raw), n)
    if len(pairs) < (24 if game == "bingo" else 8):
        raise ValueError(f"solo salieron {len(pairs)} ejercicios distintos de «{tema}»; prueba otro tema o el dominó")
    folder = os.path.join(J.settings["output_dir"], "Juegos")
    os.makedirs(folder, exist_ok=True)
    title = f"{juegos.GAMES[game]} de {tema}"
    path = os.path.join(folder, re.sub(r'[<>:"/\\|?*]+', " ", f"{title}{' ' + curso if curso else ''} {datetime.datetime.now():%Y-%m-%d %H%M}.pdf"))
    ncards = max(len(aula.students(curso)), 10) if curso else 30
    juegos.build_pdf(game, pairs, path, title, curso, n_cards=ncards)
    J.generated_files.add(path)
    return path, len(pairs), ncards


def game_voice(text, t):
    m = _GAME.search(t)
    if not m:
        return False
    game = juegos.game_of(m.group(1)) or "parejas"
    tema = m.group(2).strip()
    curso = J._resolve_course(m.group(3)) if m.group(3) else (aula.data.get("activo", "") if game == "bingo" else "")
    if not juegos.topic_of(tema) and J.state.get("ai") != "ok":
        J.reply("Sin IA solo puedo hacer juegos de aritmética: tablas, enteros, fracciones, potencias, raíces, porcentajes o ecuaciones.", "JUEGOS")
        return True
    J.reply(f"Preparo el {juegos.GAMES[game].lower()} de {tema}…", "JUEGOS")

    def work():
        try:
            path, n, nc = make_game(game, tema, curso)
        except Exception as e:
            J.notify(f"No pude hacer el juego: {str(e)[:150]}", "JUEGOS")
            return
        opened = J._open_doc(path)
        J.notify(f"Listo el {juegos.GAMES[game].lower()} de {tema}" + (f": {nc} cartones y la hoja del profe" if game == "bingo" else f" con {n} ejercicios") +
                 (". Lo abrí para imprimir." if opened else ". Está en Documentos › Jarvis › Juegos."), "JUEGOS")
    if getattr(J._tl, "capture", None) is not None:
        work()
    else:
        J.start_job("Preparando el juego", work, "juego")
    return True


# ============================================================================ 2. DIFICULTAD DE LAS PREGUNTAS
_DIF_ASK = re.compile(r"\bque tan dificiles son (?:mis |las )?preguntas(?:\s+(?:de|sobre)\s+(.+))?$|\bdificultad de (?:mis |las )?preguntas(?:\s+(?:de|sobre)\s+(.+))?$")
_DIF_EXAM = re.compile(r"\b(?:examen|evaluacion|quiz|prueba)\s+equilibrad[oa]\s+(?:de|sobre)\s+(.+?)(?:\s+(?:de|con)\s+(\d+)\s+preguntas)?$")


def difficulty_voice(text, t):
    m = _DIF_ASK.search(t)
    if m:
        n = banco.refresh_stats(list(examenes.data.get("examenes", {}).values()))
        tema = (m.group(1) or m.group(2) or "").strip()
        c = banco.difficulty_counts(tema)
        total = sum(c.values())
        if not total:
            J.reply(f"No tengo preguntas{' de ' + tema if tema else ''} en el banco todavía.", "BANCO")
            return True
        J.reply(f"De {total} preguntas{' de ' + tema if tema else ''}: {c['fácil']} fáciles, {c['media']} medias y {c['difícil']} difíciles, según lo que "
                f"respondieron tus estudiantes en las evaluaciones con hoja; {c['sin datos']} aún sin datos (necesitan al menos {banco.MIN_N} respuestas)."
                + ("" if n else " Todavía no hay evaluaciones corregidas con preguntas del banco."), "BANCO")
        return True
    m = _DIF_EXAM.search(t)
    if m:
        banco.refresh_stats(list(examenes.data.get("examenes", {}).values()))
        tema, n = m.group(1).strip(), int(m.group(2) or 10)
        quiz = banco.build_balanced(tema, n)
        if not quiz:
            J.reply(f"Necesito al menos {n} preguntas de {tema} en el banco (tengo {banco.count(tema)}).", "BANCO")
            return True
        lv = quiz.pop("niveles")
        J.remember_quiz(quiz)
        path = aula.build_docx("quiz", quiz, J.settings["output_dir"], J.Document, J.settings["aula_docente"], J.settings["aula_institucion"],
                               aula.data.get("activo", ""))
        J.generated_files.add(path)
        opened = J._open_doc(path)
        J.reply(f"Listo el examen equilibrado de {tema}: {lv['fácil']} fáciles, {lv['media']} medias y {lv['difícil']} difíciles"
                + (f", y {n - sum(lv.values())} sin datos todavía" if n - sum(lv.values()) else "") + ", de la más fácil a la más difícil."
                + (" Lo abrí." if opened else ""), "BANCO")
        return True
    return False


# ============================================================================ AVISOS DIARIOS
def _school_worker():
    time.sleep(120)
    last = ""
    while True:
        try:
            now = datetime.datetime.now()
            if 6 <= now.hour <= 20 and last != now.date().isoformat():
                last = now.date().isoformat()
                for msg in festivos.to_warn(now.date()):
                    J.notify(msg, "CALENDARIO")
                for c, e, left in salon.recup_to_warn(now.date()):
                    J.notify(f"Recuperación de {e} ({c}): " + ("vence hoy." if left == 0 else "vence en 2 días." if left == 2 else
                                                              "se venció ayer sin entrega.") + " Cuando la entregue, di «{} entregó la recuperación».".format(
                        e.split()[0]), "RECUPERACIÓN")
        except Exception as ex:
            J.note_error("COLEGIO", ex)
        time.sleep(1800)


def school_start():
    festivos.configure(J.CONFIG_DIR)
    salon.configure(J.CONFIG_DIR)
    threading.Thread(target=_school_worker, daemon=True, name="colegio").start()


def brief_school(today=None):
    """Para el resumen de la mañana."""
    today = today or datetime.date.today()
    out = []
    why = festivos.no_class(today)
    if why and today.weekday() < 5:
        out.append(f"Hoy no hay clase: {why}.")
    evs = festivos.events_between(today, today + datetime.timedelta(days=3))
    if evs:
        out.append("En el colegio: " + "; ".join(festivos.describe(e, today) for e in evs[:3]) + ".")
    return out


__all__ = ['_CAL_ADD', '_CAL_CLASS', '_CAL_DEL', '_CAL_LIST', '_CAL_NEXT', '_COPY', '_DIF_ASK', '_DIF_EXAM', '_GAME', '_RC_DONE', '_RC_HOW', '_RC_NOTE',
           '_RC_WHO', '_copy_report', '_school_worker', 'brief_school', 'school_calendar_voice', 'copy_check_files', 'copy_voice', 'date_warning',
           'difficulty_voice', 'game_voice', 'make_game', 'period_vals', 'recovery_track_voice', 'register_plans', 'school_start']
