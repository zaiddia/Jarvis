"""12.38: lo automático del modo docente, pensado para varios grados y varios cursos.

1. Formatos del colegio: subes tu formato (Word) al chat y dices «usa este formato para los planes de clase de séptimo»;
   desde ahí lo que haga esa habilidad sale sobre ese formato (encabezado, logo, márgenes, estilos). Puede ser uno para
   todos, uno por grado o uno por curso (gana el más específico). Solo usa archivos que TÚ subes al chat.
2. Respaldo semanal de notas y asistencia: cada viernes, un Excel con una hoja por curso y un resumen por grado.
3. Cierre de periodo completo: después del consolidado, te propone los boletines de cada curso y los planes de
   recuperación de los cursos con estudiantes en riesgo (cada cosa espera tu «sí»; nada se envía solo).
4. Resumen docente del viernes: por grado y por curso, lo visto, lo pendiente y quién va en riesgo; en Word y un mensaje
   corto a tu WhatsApp (o al chat).
5. La clase de mañana lista: en la noche, con tu horario, deja preparado el plan de las clases del día siguiente que aún
   no tengan material; los cursos del mismo grado, materia y tema comparten un solo plan.
"""
import datetime
import json
import os
import re
import shutil
import threading
import time

import aula
import catalogo_docente as C
import diarioclase
import festivos
import horario
import proyectos
import semana
import seguimiento
from nucleo import J

_da = {"lock": threading.Lock()}


def _da_cfg(name):
    return os.path.join(J.CONFIG_DIR, name)


def _da_load(name, default):
    try:
        with open(_da_cfg(name), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, type(default)) else default
    except (OSError, ValueError):
        return default


def _da_save(name, d):
    tmp = _da_cfg(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _da_cfg(name))


def _da_mark(key, value):
    J.settings[key] = value
    try:
        J.save_settings_file()
    except OSError:
        pass


def all_courses():
    return sorted(set(aula.data.get("cursos", {})) | set(seguimiento.data), key=aula.course_sort_key)


def by_grade(courses):
    """[(«Grado 7°» o «Otros», [cursos])] en orden."""
    out = {}
    for c in courses:
        g = semana.grade_key(c)
        out.setdefault(f"Grado {g}°" if g else "Otros cursos", []).append(c)
    return sorted(out.items(), key=lambda kv: (semana.grade_key(kv[1][0]) or 99))


# ============================================================================ 1. FORMATOS DEL COLEGIO
_GRADE_W = r"(?:primero|segundo|tercero|cuarto|quinto|sexto|septimo|octavo|noveno|decimo|once|undecimo|\d{1,2}\s?°?)"


def parse_scope(t):
    """«… de 7A» → ("c:7A", "7A"); «… de séptimo» / «de los séptimos» / «grado 7» → ("g7", "grado 7°"); nada → ("todos", "todos los cursos")."""
    cs = J.courses_in(t)
    if len(cs) == 1:
        return f"c:{cs[0]}", cs[0]
    m = re.search(rf"\b(?:de|para|en)\s+(?:los\s+|las\s+)?(?:grado\s+)?({_GRADE_W})s?\b(?!\s*[a-f]\b)", t) or re.search(rf"\bgrado\s+({_GRADE_W})\b", t)
    if m:
        g = semana.grade_key(m.group(1).replace("°", "").strip())
        if g:
            return f"g{g}", f"grado {g}°"
    return "todos", "todos los cursos"


def formats_list():
    return _da_load("formatos.json", [])


def template_for(sid, courses=()):
    """La ruta del formato para esa habilidad y esos cursos: el del curso, si no el del grado, si no el general."""
    fs = [f for f in formats_list() if f["sid"] == sid and os.path.exists(f["ruta"])]
    if not fs:
        return ""
    courses = list(courses or [])
    for c in courses[:1] if len(courses) == 1 else []:
        hit = next((f for f in fs if f["scope"] == f"c:{c}"), None)
        if hit:
            return hit["ruta"]
    grades = {semana.grade_key(c) for c in courses}
    if len(grades) == 1 and None not in grades:
        g = grades.pop()
        hit = next((f for f in fs if f["scope"] == f"g{g}"), None)
        if hit:
            return hit["ruta"]
    hit = next((f for f in fs if f["scope"] == "todos"), None)
    return hit["ruta"] if hit else ""


def current_template():
    sid = J.recent_skill()
    return template_for(sid, J._dd.get("cursos") or []) if sid else ""


def _clear_body(doc):
    body = doc.element.body
    for child in list(body):
        if not child.tag.endswith("}sectPr"):
            body.remove(child)
    return doc


def templated_document_factory(orig):
    """Envuelve docx.Document: sin argumentos y con un formato para la habilidad en uso, el documento nuevo parte del
    formato (encabezado, pie, logo, márgenes y estilos), con el cuerpo vacío."""
    if orig is None or getattr(orig, "templated", False):
        return orig

    def Document(*a, **k):
        if a or k:
            return orig(*a, **k)
        p = ""
        try:
            p = J.current_template()
        except Exception:
            pass
        if p:
            try:
                return _clear_body(orig(p))
            except Exception as e:
                J.log_terminal(f"No pude usar el formato «{os.path.basename(p)}»: {e}", "FORMATOS")
        return orig()
    Document.templated = True
    Document.original = orig
    return Document


_FMT_SET = re.compile(r"\b(?:usa|usar|utiliza|toma|guarda|pon|deja)\w*\s+(?:este|esta|ese|esa|el|mi)\s+(?:formato|plantilla|archivo|documento)"
                      r"\s+(?:del colegio\s+)?(?:como (?:formato|plantilla)\s+)?(?:para|de|en)\s+(.+)$")
_FMT_LIST = re.compile(r"\bque formatos (?:tengo|hay|guardaste|tienes)\b|\b(?:mis|los) formatos (?:del colegio|guardados)\b")
_FMT_DEL = re.compile(r"\b(?:quita|borra|elimina|olvida)\w*\s+(?:el\s+)?formato\s+(?:de|del|para)\s+(.+)$")


def _sing(w):
    return re.sub(r"(?:es|s)$", "", w) if len(w) > 4 else w


def _skill_from(q):
    """La habilidad del catálogo que nombra la frase («los planes de clase» → Plan de clase, no Planeación del año)."""
    q = re.sub(r"\b(?:los|las|el|la|mis|tus|de|del|para)\b", " ", C.norm(q))
    qw = {_sing(w) for w in q.split() if len(w) > 2}
    if not qw:
        return None
    best, score = None, 0
    for h in C.H:
        nw = {_sing(w) for w in C.norm(h["nombre"]).replace("/", " ").split() if len(w) > 2}
        s = 3 * len(qw & nw) - 0.5 * len(nw - qw)
        if qw & nw and s > score:
            best, score = h, s
    if best:
        return best
    hits = C.search(q)
    return hits[0] if hits else None


def formats_voice(text, t):
    m = _FMT_SET.search(t)
    if m:
        import adjuntos
        rest = re.sub(rf"\s+(?:de|para|en)\s+(?:los\s+|las\s+)?(?:grado\s+)?(?:{_GRADE_W}s?|\d{{1,2}}\s?[a-f])\b.*$", "", m.group(1))
        h = _skill_from(rest)
        if not h:
            J.reply("¿Para qué habilidad es el formato? Por ejemplo: «usa este formato para los planes de clase».", "FORMATOS")
            return True
        docs = [i for i in adjuntos.recent(1800) if i["ext"] == ".docx"]
        if not docs:
            J.reply(f"Súbeme el formato en Word (.docx) con el botón del clip o arrastrándolo al chat, y luego dime "
                    f"«usa este formato para {h['nombre'].lower()}».", "FORMATOS")
            return True
        scope, label = parse_scope(t)
        it = docs[-1]
        folder = os.path.join(_da_cfg("formatos"), h["id"])
        os.makedirs(folder, exist_ok=True)
        dest = os.path.join(folder, re.sub(r"[^\w-]", "_", scope) + ".docx")
        shutil.copyfile(it["ruta"], dest)
        with _da["lock"]:
            fs = [f for f in formats_list() if not (f["sid"] == h["id"] and f["scope"] == scope)]
            fs.append({"sid": h["id"], "scope": scope, "nombre": it["nombre"], "ruta": dest, "fecha": time.strftime("%Y-%m-%d")})
            _da_save("formatos.json", fs)
        J.reply(f"Listo: «{it['nombre']}» queda como formato de «{h['nombre']}» para {label}. Desde ahora lo que haga esa "
                "habilidad sale sobre ese formato (encabezado, logo, márgenes y estilos).", "FORMATOS")
        return True
    if _FMT_LIST.search(t):
        fs = formats_list()
        if not fs:
            J.reply("Aún no tengo formatos tuyos. Súbeme uno en Word y dime «usa este formato para los planes de clase» "
                    "(o «… de séptimo», «… de 7A»).", "FORMATOS")
            return True
        names = {h["id"]: h["nombre"] for h in C.H}
        parts = [f"{names.get(f['sid'], f['sid'])} ({'todos' if f['scope'] == 'todos' else f['scope'].replace('c:', '').replace('g', 'grado ') + ('°' if f['scope'].startswith('g') else '')}): {f['nombre']}"
                 for f in fs]
        J.reply(f"Tengo {len(fs)} formato{'s' if len(fs) != 1 else ''}: " + "; ".join(parts) + ".", "FORMATOS")
        return True
    m = _FMT_DEL.search(t)
    if m:
        h = _skill_from(re.sub(rf"\s+(?:de|para|en)\s+(?:los\s+)?(?:grado\s+)?(?:{_GRADE_W}s?|\d{{1,2}}\s?[a-f])\b.*$", "", m.group(1)))
        if not h:
            return False
        scope, label = parse_scope(t)
        with _da["lock"]:
            fs = formats_list()
            keep = [f for f in fs if not (f["sid"] == h["id"] and f["scope"] == scope)]
            _da_save("formatos.json", keep)
        J.reply(f"Quité el formato de «{h['nombre']}» para {label}." if len(keep) < len(fs) else
                f"No tenía un formato de «{h['nombre']}» para {label}.", "FORMATOS")
        return True
    return False


# ============================================================================ 2. RESPALDO SEMANAL DE NOTAS Y ASISTENCIA
def _sheet_title(c, used):
    base = re.sub(r"[\[\]:*?/\\]", "-", str(c))[:28] or "Curso"
    name, i = base, 2
    while name in used:
        name, i = f"{base[:25]} ({i})", i + 1
    used.add(name)
    return name


def backup_xlsx(out_dir, today=None):
    """Una hoja por curso (estudiantes × actividades, promedio y faltas, con fórmulas) y un resumen por grado. → ruta o ""."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    today = today or datetime.date.today()
    courses = [c for c in all_courses() if aula.students(c) or seguimiento.data.get(c)]
    if not courses:
        return ""
    wb = Workbook()
    res = wb.active
    res.title = "Resumen"
    res.append(["Grado", "Curso", "Estudiantes", "Promedio del curso", f"Con promedio < {J.settings['risk_grade']}", "Faltas registradas"])
    head = PatternFill("solid", fgColor="0F768A")
    for c in res[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), head
    used = {"Resumen"}
    for grade, cs in by_grade(courses):
        for c in cs:
            names = list(aula.students(c)) + [n for n in seguimiento.data.get(c, {}) if n not in aula.students(c)]
            acts = []
            for n in names:
                for e in seguimiento.data.get(c, {}).get(n, []):
                    if e.get("actividad") not in acts:
                        acts.append(e.get("actividad") or "nota")
            ws = wb.create_sheet(_sheet_title(c, used))
            ws.append(["Estudiante"] + acts + ["Promedio", "Faltas"])
            for cell in ws[1]:
                cell.font, cell.fill = Font(bold=True, color="FFFFFF"), head
            ab = J._absences(c)
            for r, n in enumerate(names, 2):
                notes = {e.get("actividad") or "nota": e.get("nota") for e in seguimiento.data.get(c, {}).get(n, [])}
                row = [n] + [notes.get(a, None) for a in acts]
                last = get_column_letter(1 + len(acts)) if acts else "B"
                row.append(f'=IFERROR(AVERAGE(B{r}:{last}{r}),"")' if acts else "")
                row.append(ab.get(n, 0))
                ws.append(row)
            pc, fc = get_column_letter(len(acts) + 2), get_column_letter(len(acts) + 3)
            n_last = len(names) + 1
            ws.column_dimensions["A"].width = 30
            ws.freeze_panes = "B2"
            ref = "'" + ws.title.replace("'", "''") + "'"
            res.append([grade, c, len(names),
                        f'=IFERROR(AVERAGE({ref}!{pc}2:{pc}{n_last}),"")' if acts and names else "",
                        f'=COUNTIF({ref}!{pc}2:{pc}{n_last},"<"&{J.settings["risk_grade"]})' if acts and names else 0,
                        f"=SUM({ref}!{fc}2:{fc}{n_last})" if names else 0])
    for col, w in zip("ABCDEF", (14, 22, 12, 18, 18, 18)):
        res.column_dimensions[col].width = w
    folder = os.path.join(out_dir, "Respaldos docentes")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"Notas y asistencia - semana del {today - datetime.timedelta(days=today.weekday()):%Y-%m-%d}.xlsx")
    wb.save(path)
    return path


def run_backup(say=True):
    path = backup_xlsx(J.settings["output_dir"])
    if not path:
        if say:
            J.reply("No tengo cursos con estudiantes ni notas para respaldar.", "RESPALDO")
        return ""
    J.note_skill_direct("respaldo_notas", [])
    J.generated_files.add(path)
    n = len([c for c in all_courses() if aula.students(c) or seguimiento.data.get(c)])
    if say:
        J.reply(f"Respaldo listo: notas y asistencia de {n} curso{'s' if n != 1 else ''} (una hoja por curso y un resumen por grado), "
                "en Documentos › Jarvis › Respaldos docentes" + (" y en tu Drive docente." if J.gdrive_ready() else "."), "RESPALDO")
    return path


_GB_RE = re.compile(r"\b(?:haz|hazme|saca|genera|guarda)\w*\s+(?:el|un|una)\s+(?:respaldo|copia)\s+(?:semanal\s+)?de\s+(?:las\s+|mis\s+)?notas\b|"
                    r"\brespalda\w*\s+(?:las\s+|mis\s+)?notas\b")


def grades_backup_voice(text, t):
    if not _GB_RE.search(t):
        return False
    if getattr(J._tl, "capture", None) is not None:
        J.run_backup()
    else:
        J.start_job("Respaldo de notas", J.run_backup, "respaldo")
    return True


# ============================================================================ 3. CIERRE DE PERIODO COMPLETO
def close_followups():
    """Tras el consolidado: proponer boletines de todos los cursos y planes de recuperación de los cursos en riesgo."""
    if not J.settings.get("close_followups", True):
        return []
    courses = [c for c in all_courses() if seguimiento.data.get(c)]
    asked = []
    if courses:
        groups = "; ".join(f"{g}: {', '.join(cs)}" for g, cs in by_grade(courses))

        def go_bol():
            for c in courses:
                J.submit_command(f"haz los boletines de {c}")
        J.request_approval("boletines", f"Hacer los boletines de {len(courses)} curso{'s' if len(courses) != 1 else ''}", groups,
                           on_ok=go_bol, on_no=lambda: None, ttl=48 * 3600, quiet=True)
        asked.append("boletines")
    risk = []
    for c in courses:
        names = sorted(set(aula.students(c)) | set(seguimiento.data.get(c, {})))
        if seguimiento.at_risk(c, names, J._absences(c), J.settings["risk_grade"], J.settings["risk_absences"]):
            risk.append(c)
    if risk:
        def go_rec():
            for c in risk:
                J.submit_command(f"haz los planes de recuperación de {c}")
        J.request_approval("recuperaciones", f"Planes de recuperación de {', '.join(risk)}",
                           "Cursos con estudiantes en riesgo: " + ", ".join(risk), on_ok=go_rec, on_no=lambda: None, ttl=48 * 3600, quiet=True)
        asked.append("recuperaciones")
    if asked:
        msg = ("Para terminar el cierre te dejé por aprobar: " +
               " y ".join({"boletines": f"los boletines de {len(courses)} curso{'s' if len(courses) != 1 else ''}",
                           "recuperaciones": f"los planes de recuperación de {', '.join(risk)}"}[a] for a in asked) +
               ". Di «¿qué tengo por aprobar?» o «sí». Nada se envía a las familias sin que tú lo mandes.")
        J.notice_add(msg, "aviso", "CIERRE")
        J.push_chat("jarvis", msg, "CIERRE")
    return asked


# ============================================================================ 4. RESUMEN DOCENTE DEL VIERNES
def teacher_week(today=None):
    """[{grado, cursos: [{curso, vistos, pendientes, notas, riesgo}]}] de la semana (lunes a hoy)."""
    today = today or datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    courses = sorted(set(all_courses()) | set(semana.courses_of_week(horario.items)), key=aula.course_sort_key)
    out = []
    for grade, cs in by_grade(courses):
        rows = []
        for c in cs:
            seen = [e["tema"] for e in diarioclase.entries(c) if monday.isoformat() <= e["fecha"] <= today.isoformat()]
            p = diarioclase.pending(c)
            pend = [x["tema"] for x in (p[1] if p else [])][:5]
            grades = sum(1 for n, lst in seguimiento.data.get(c, {}).items() for e in lst if monday.isoformat() <= str(e.get("fecha", "")) <= today.isoformat())
            names = sorted(set(aula.students(c)) | set(seguimiento.data.get(c, {})))
            risk = [n for n, _ in seguimiento.at_risk(c, names, J._absences(c), J.settings["risk_grade"], J.settings["risk_absences"])]
            rows.append({"curso": c, "vistos": seen, "pendientes": pend, "notas": grades, "riesgo": risk})
        out.append({"grado": grade, "cursos": rows})
    return out


def teacher_week_text(data):
    n_c = sum(len(g["cursos"]) for g in data)
    seen = sum(len(c["vistos"]) for g in data for c in g["cursos"])
    risk = [f"{n} ({c['curso']})" for g in data for c in g["cursos"] for n in c["riesgo"]]
    parts = [f"📚 Semana docente: {n_c} curso{'s' if n_c != 1 else ''}, {seen} tema{'s' if seen != 1 else ''} visto{'s' if seen != 1 else ''}"]
    for g in data:
        ln = []
        for c in g["cursos"]:
            bit = c["curso"] + (f": {c['vistos'][-1]}" if c["vistos"] else ": sin registro en el diario")
            ln.append(bit)
        parts.append(f"• {g['grado']}: " + "; ".join(ln))
    if risk:
        parts.append(f"• En riesgo ({len(risk)}): " + ", ".join(risk[:10]) + ("…" if len(risk) > 10 else ""))
    return "\n".join(parts)


def teacher_week_docx(data, today=None):
    today = today or datetime.date.today()
    D = getattr(J.Document, "original", J.Document)
    if D is None:
        return ""
    doc = D()
    doc.add_heading(f"Resumen docente · semana del {today - datetime.timedelta(days=today.weekday()):%d/%m/%Y}", 0)
    if J.settings.get("aula_docente") or J.settings.get("aula_institucion"):
        doc.add_paragraph(" · ".join(x for x in (J.settings.get("aula_docente"), J.settings.get("aula_institucion")) if x))
    for g in data:
        doc.add_heading(g["grado"], 1)
        tb = doc.add_table(rows=1, cols=5)
        tb.style = "Table Grid"
        for i, h in enumerate(("Curso", "Visto esta semana", "Lo que sigue", "Notas puestas", "En riesgo")):
            tb.rows[0].cells[i].text = h
        for c in g["cursos"]:
            r = tb.add_row().cells
            r[0].text = c["curso"]
            r[1].text = "; ".join(c["vistos"]) or "—"
            r[2].text = "; ".join(c["pendientes"][:3]) or "—"
            r[3].text = str(c["notas"])
            r[4].text = ", ".join(c["riesgo"]) or "—"
    folder = os.path.join(J.settings["output_dir"], "Resúmenes docentes")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"Resumen docente - semana del {today - datetime.timedelta(days=today.weekday()):%Y-%m-%d}.docx")
    doc.save(path)
    return path


def run_friday(say=True, send=False):
    data = teacher_week()
    if not any(g["cursos"] for g in data):
        if say:
            J.reply("Aún no tengo cursos ni horario para el resumen docente.", "RESUMEN DOCENTE")
        return ""
    text = teacher_week_text(data)
    path = teacher_week_docx(data)
    if path:
        J.note_skill_direct("resumen_semana", [])
        J.generated_files.add(path)
    sent = J.phone_send(text) if send else False
    if say:
        J.reply(text + ("\n(El detalle por curso quedó en Word" + (", y en tu Drive docente" if J.gdrive_ready() else "") + ".)"), "RESUMEN DOCENTE")
    elif not sent:
        J.push_chat("jarvis", text, "RESUMEN DOCENTE")
    return text


_FR_RE = re.compile(r"\b(?:hazme|haz|dame|prepara|preparame)\s+(?:el\s+)?resumen docente(?:\s+de\s+(?:la|esta)\s+semana)?\b|"
                    r"\bresumen (?:de la semana )?por cursos\b|\bcomo (?:me fue|fue la semana) en (?:mis )?(?:cursos|clases)\b")


def friday_voice(text, t):
    if not _FR_RE.search(t):
        return False
    if getattr(J._tl, "capture", None) is not None:
        J.run_friday()
    else:
        J.start_job("Resumen docente", J.run_friday, "resumen-docente")
    return True


# ============================================================================ 5. LA CLASE DE MAÑANA LISTA
def prepared():
    return _da_load("preparado.json", {})


def mark_prepared(day, courses):
    with _da["lock"]:
        d = prepared()
        keep = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
        d = {k: v for k, v in d.items() if k >= keep}
        d[day.isoformat()] = sorted(set(d.get(day.isoformat(), [])) | set(courses))
        _da_save("preparado.json", d)


def mark_week_prepared(plan, monday):
    """Lo llama la semana lista: los cursos de su plan quedan preparados en sus días de clase."""
    courses = {c for p in plan.get("pasos", []) for c in (p.get("cursos") or [])}
    for x in horario.items:
        if x.get("curso") in courses and x["dia"] < 5:
            mark_prepared(monday + datetime.timedelta(days=x["dia"]), [x["curso"]])


def prepare_day(day, say=True):
    """Deja listo el plan de las clases de ese día que aún no tengan material. → plan o None."""
    if not horario.items:
        if say:
            J.reply("Para dejarte lista la clase de mañana necesito tu horario (Ajustes › Aula y colegio › Horario).", "CLASE DE MAÑANA")
        return None
    why = festivos.no_class(day)
    if why:
        if say:
            J.reply(f"El {semana.DIAS[day.weekday()]} {day.day} no hay clase: {why}.", "CLASE DE MAÑANA")
        return None
    done = set(prepared().get(day.isoformat(), []))
    items = [x for x in horario.items if x.get("curso") not in done]
    pasos, sin_tema = semana.day_plan(items, J.week_topic, day, proyectos.MAX_STEPS)
    if not pasos:
        if say:
            J.reply(("Tus clases de ese día ya tienen material." if done else "No sé qué tema toca: guarda la malla del periodo o anota "
                     "lo que ves en el diario de clase.") + (f" Sin tema: {', '.join(sin_tema)}." if sin_tema else ""), "CLASE DE MAÑANA")
        return None
    if J.state.get("ai") != "ok":
        if say:
            J.reply("Para preparar la clase necesito la IA conectada.", "CLASE DE MAÑANA")
        return None
    plan = {"nombre": f"Clases del {semana.DIAS[day.weekday()]} {day:%d/%m}", "pasos": pasos}
    courses = [c for p in pasos for c in p["cursos"]]
    mark_prepared(day, courses)
    J.note_skill_direct("plan_clase", [])
    st = proyectos.new("clase de mañana", plan, J.settings["output_dir"])
    J.run_project(st)
    msg = (f"Te dejo lista la clase del {semana.DIAS[day.weekday()]}: " + "; ".join(p["titulo"].replace("Clase de mañana ", "") for p in pasos) +
           (f". Sin tema: {', '.join(sin_tema)}" if sin_tema else "") + ".")
    if say:
        J.reply(msg, "CLASE DE MAÑANA")
    else:
        J.notice_add(msg, "aviso", "CLASE DE MAÑANA")
        J.push_chat("jarvis", msg, "CLASE DE MAÑANA")
    return plan


_NP_RE = re.compile(r"\b(?:prepara|preparame|alista|alistame|deja lista|dejame lista|deja listas|dejame listas)\s+(?:la|las|mi|mis)\s+clases?\s+de\s+(manana|hoy|pasado manana)\b")


def night_prep_voice(text, t):
    m = _NP_RE.search(t)
    if not m:
        return False
    today = datetime.date.today()
    day = today + datetime.timedelta(days={"hoy": 0, "manana": 1, "pasado manana": 2}[m.group(1)])
    J.prepare_day(day)
    return True


# ============================================================================ RELOJ
def auto_ticks(now=None):
    now = now or datetime.datetime.now()
    s = J.settings
    done = []
    today = now.date().isoformat()
    if J.current_mode() == "docente" or horario.items or aula.data.get("cursos"):
        if now.weekday() == 4 and now.hour >= s["docente_friday_hour"]:
            if s["auto_backup"] and s["auto_backup_last"] != today:
                _da_mark("auto_backup_last", today)
                if J.run_backup(say=False):
                    done.append("respaldo")
            if s["docente_friday"] and s["docente_friday_last"] != today:
                _da_mark("docente_friday_last", today)
                if J.run_friday(say=False, send=True):
                    done.append("resumen")
        tomorrow = now.date() + datetime.timedelta(days=1)
        if (s["night_prep"] and now.hour >= s["night_prep_hour"] and tomorrow.weekday() < 5 and s["night_prep_last"] != today
                and not J.project_run.get("busy")):
            _da_mark("night_prep_last", today)
            if J.prepare_day(tomorrow, say=False):
                done.append("clase de mañana")
    return done


__all__ = ['_GB_RE', '_FMT_DEL', '_FMT_LIST', '_FMT_SET', '_FR_RE', '_GRADE_W', '_NP_RE', '_da_cfg', '_clear_body', '_da', '_da_load', '_da_mark',
           '_da_save', '_sheet_title', '_sing', '_skill_from', 'all_courses', 'auto_ticks', 'grades_backup_voice', 'backup_xlsx', 'by_grade',
           'close_followups', 'current_template', 'formats_list', 'formats_voice', 'friday_voice', 'mark_prepared', 'mark_week_prepared',
           'night_prep_voice', 'parse_scope', 'prepare_day', 'prepared', 'run_backup', 'run_friday', 'teacher_week', 'teacher_week_docx',
           'teacher_week_text', 'template_for', 'templated_document_factory']
