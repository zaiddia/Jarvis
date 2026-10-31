"""10.6: programa Saber 11 y Saber 9. Simulacros por competencia con hoja de respuestas, mini simulacros desde el celular,
perfil y plan de estudio de cada estudiante, tablero de evolución e informe para coordinación.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import html
import os
import re
import urllib.parse
import webbrowser

import aula
import banco
import examenes
import saber
import ticket
from nucleo import J


def _level(course, t=""):
    m = re.search(r"\bsaber\s+(9|11|once|nueve)\b", t)
    if m:
        return 11 if m.group(1) in ("11", "once") else 9
    return saber.level_of(aula.grade_of(course) or 11)


def _comp_rule(level):
    return (f" Es un simulacro Saber {level} de Matemáticas. En «competencia» usa EXACTAMENTE uno de estos nombres y reparte las preguntas "
            f"entre los tres: {'; '.join(saber.COMP[level])}. Cubre los componentes {saber.COMPONENTES[level]}.")


# ============================================================================ SIMULACRO CON HOJA DE RESPUESTAS
def make_simulacro(course, n, level, tema=""):
    g = aula.grade_of(course) or (11 if level == 11 else 9)
    req = f"simulacro Saber {level} de matemáticas de {n} preguntas" + (f" sobre {tema}" if tema else "")
    prompt = aula.build_prompt("saber", req, n, f"{g}° (curso {course})") + _comp_rule(level) + J.lessons_ctx()
    m = None
    for _ in range(2):
        try:
            m = aula.validate("saber", J._extract_json(J.ai_chat([{"role": "user", "content": prompt}], json_mode=True, max_tokens=12000)), req)
            break
        except (ValueError, TypeError):
            continue
    if not m:
        raise ValueError("la IA no devolvió el simulacro bien")
    for q in m["preguntas"]:
        q["competencia"] = saber.canonical(q.get("competencia", ""), level)
    m["titulo"] = m.get("titulo") or f"Simulacro Saber {level}"
    banco.add_quiz(m)
    booklet = ""
    if J.Document is not None:
        booklet = aula.build_docx("saber", m, J.settings["output_dir"], J.Document, J.settings["aula_docente"], J.settings["aula_institucion"], course)
        J.generated_files.add(booklet)
    ex = J.exam_from_quiz(m, course, m["titulo"])
    ex["tipo"] = "saber"
    ex["nivel"] = level
    examenes.save()
    sheets = J.make_sheets(ex)
    return m, ex, booklet, sheets


_SIM_RE = re.compile(r"\b(?:haz|hazme|prepara|preparame|genera|generame|crea|creame|arma|armame)\s+(?:un\s+|el\s+)?simulacro\s+"
                     r"(?:tipo\s+)?(?:saber|icfes)\b")
_MINI_RE = re.compile(r"\b(?:lanza|abre|empieza|inicia|haz|hazme|pon)\s+(?:el\s+|un\s+)?mini\s*-?\s*simulacro\b")
_SB_ASK = re.compile(r"\bcomo (?:va|vamos|van|viene)\s+(?:el\s+)?(.+?)\s+en\s+(?:el\s+)?(?:saber|icfes)\b|\bcomo va(?:mos)? en (?:el )?saber\b|"
                     r"\b(?:tablero|evolucion) (?:del? )?(?:saber|icfes)\b")
_SB_PLAN = re.compile(r"\bplan(?:es)? (?:de estudio )?(?:saber|icfes)\b|\bplan(?:es)? de estudio (?:para el|del)? ?(?:saber|icfes)\b")
_SB_REP = re.compile(r"\binforme (?:del? )?(?:saber|icfes)\b")


def _sb_course(t):
    cm = J._COURSE_IN.search(t)
    return J._resolve_course(cm.group(1) if cm else "")


def saber_voice(text, t):
    if _SIM_RE.search(t):
        course = _sb_course(t)
        if not course:
            J.reply("¿Para qué curso? Por ejemplo: «haz un simulacro Saber de 20 preguntas para 11A».", "SABER")
            return True
        nm = re.search(r"\b(\d{1,2})\s+preguntas\b", t)
        n = max(5, min(40, int(nm.group(1)) if nm else 20))
        lvl = _level(course, t)
        tm = re.search(r"\bsobre\s+(.+?)(?:\s+(?:para|de)\s+(?:grado\s+)?\d|$)", t)
        if J.state.get("ai") != "ok":
            J.reply("Para crear el simulacro necesito la IA conectada.", "SABER")
            return True
        J.reply(f"Preparo el simulacro Saber {lvl} de {n} preguntas para {course}, con su hoja de respuestas…", "SABER")

        def work():
            try:
                m, ex, booklet, sheets = make_simulacro(course, n, lvl, tm.group(1).strip() if tm else "")
            except Exception as e:
                J.notify(f"No me salió el simulacro: {getattr(e, 'why', e)}. Inténtalo otra vez.", "SABER")
                return
            J._open_doc(booklet or sheets)
            per = {}
            for q in m["preguntas"]:
                per[q["competencia"]] = per.get(q["competencia"], 0) + 1
            J.notify(f"Listo el simulacro «{m['titulo']}»: {len(m['preguntas'])} preguntas (" + ", ".join(f"{v} de {k}" for k, v in per.items()) +
                     f"), el cuadernillo en Word y las hojas de respuesta de {course}. Cuando lo presenten: «califica las hojas».", "SABER")
        if getattr(J._tl, "capture", None) is not None:
            work()
        else:
            J.start_job("Preparando el simulacro Saber", work, "saber")
        return True
    if _MINI_RE.search(t):
        if J._need_lan():
            return True
        course = _sb_course(t) or aula.data.get("activo", "")
        lvl = _level(course, t)
        qs = [q for q in banco.items if q.get("competencia")]
        if J.state.get("ai") != "ok" and len(qs) < 5:
            J.reply("Para el mini simulacro necesito la IA conectada (o preguntas Saber en tu banco).", "SABER")
            return True
        J.reply(f"Preparo el mini simulacro Saber {lvl} de 5 preguntas para {course}…", "SABER")

        def work():
            try:
                g = aula.grade_of(course) or lvl
                req = "mini simulacro Saber de 5 preguntas cortas para responder en el celular"
                raw = J.ai_chat([{"role": "user", "content": aula.build_prompt("saber", req, 5, f"{g}°") + _comp_rule(lvl) +
                                  " Contextos muy cortos (máximo 2 frases), que se lean bien en un celular."}], json_mode=True, max_tokens=5000)
                m = aula.validate("saber", J._extract_json(raw), req)
            except Exception:
                m = None
            pool = m["preguntas"] if m else qs[-5:]
            preguntas = [{"enunciado": ((q.get("contexto") or "") + " " + q["enunciado"]).strip()[:700], "opciones": list(q["opciones"])[:4],
                          "respuesta": "abcd".find(str(q.get("respuesta", "a"))[:1]),
                          "competencia": saber.canonical(q.get("competencia", ""), lvl)} for q in pool[:5]]
            ticket.open_ticket(preguntas, "saber", f"Mini simulacro Saber {lvl}", course)
            ticket.state["nivel"] = lvl
            J._open_projector()
            J.socketio.emit("ticket", {"open": True, "url": J.ticket_url(), "tipo": "saber", "tema": f"Mini simulacro Saber {lvl}", "n": 0})
            J.notify("Mini simulacro abierto: en el proyector está el código QR para responder desde el celular. Al terminar: «cierra el ticket».",
                     "SABER")
        if getattr(J._tl, "capture", None) is not None:
            work()
        else:
            J.start_job("Preparando el mini simulacro", work, "saber")
        return True
    if _SB_PLAN.search(t):
        course = _sb_course(t)
        if not course or course not in saber.data["cursos"]:
            J.reply("Primero necesito al menos un simulacro calificado de ese curso.", "SABER")
            return True
        J.reply(f"Preparo el plan de estudio Saber de cada estudiante de {course}…", "SABER")
        if getattr(J._tl, "capture", None) is not None:
            J.saber_plans(course)
        else:
            J.start_job("Preparando los planes Saber", lambda: J.saber_plans(course), "saber")
        return True
    if _SB_REP.search(t):
        course = _sb_course(t)
        if not course or course not in saber.data["cursos"] or J.Document is None:
            J.reply("No tengo simulacros de ese curso todavía.", "SABER")
            return True
        path = saber.report_docx(course, J.settings["output_dir"], J.Document, J.settings["aula_institucion"], J.settings["aula_docente"])
        J.generated_files.add(path)
        J._open_doc(path)
        J.reply(f"Listo el informe Saber de {course} para coordinación, con la evolución por competencia y cada estudiante.", "SABER")
        return True
    m = _SB_ASK.search(t)
    if m:
        course = J._resolve_course((m.group(1) or "").strip()) if m.group(1) else (next(iter(saber.data["cursos"]), "") if len(saber.data["cursos"]) == 1 else _sb_course(t))
        if not course:
            J.reply("¿De qué curso? Por ejemplo: «¿cómo va 11A en el Saber?».", "SABER")
            return True
        J.reply(saber.spoken(course) + (" Te abro el tablero." if course in saber.data["cursos"] else ""), "SABER")
        if course in saber.data["cursos"]:
            try:
                webbrowser.open(J.URL + "/saber/" + urllib.parse.quote(course))
            except Exception:
                pass
        return True
    return False


# ============================================================================ REGISTRAR SESIONES
def saber_from_exam(ex):
    if ex.get("tipo") != "saber" or not ex["resultados"]:
        return None
    lvl = ex.get("nivel") or saber.level_of(aula.grade_of(ex["curso"]))
    comps = [q.get("competencia", "") for q in ex["preguntas"]] or [saber.COMP[lvl][0]] * len(ex["clave"])
    answers = {r["nombre"]: [bool(x) if x is not None else False for x in r["detalle"]] for r in ex["resultados"].values()
               if not r["nombre"].startswith("Hoja sin nombre")}
    return saber.add_session(ex["curso"], lvl, ex["titulo"], "hoja", comps, answers)


def saber_from_ticket():
    st = ticket.state
    if st.get("tipo") != "saber" or not st["respuestas"]:
        return None
    course = st.get("curso") or ""
    lvl = st.get("nivel") or saber.level_of(aula.grade_of(course))
    names = aula.students(course)
    answers = {}
    for r in st["respuestas"].values():
        who = (aula.find_student(r["nombre"], names)[0] if names else None) or r["nombre"].title()
        answers[who] = [a == q["respuesta"] for a, q in zip(r["r"], st["preguntas"])]
    return saber.add_session(course, lvl, st.get("tema") or "Mini simulacro", "celular", [q.get("competencia", "") for q in st["preguntas"]], answers)


# ============================================================================ PLANES DE ESTUDIO
def saber_plans(course):
    c = saber.data["cursos"][course]
    lvl = c["nivel"]
    prof = saber.profile(course)
    if not prof or J.state.get("ai") != "ok" or J.Document is None:
        J.notify("Para los planes necesito simulacros calificados, la IA conectada y python-docx.", "SABER")
        return ""
    weak_by = {e: sorted((v, k) for k, v in p.items() if v is not None)[:2] for e, p in prof.items()}
    comps = sorted({k for lst in weak_by.values() for _, k in lst})
    g = aula.grade_of(course) or lvl
    d = J._extract_json(J.ai_chat([{"role": "user", "content": saber.plan_prompt(lvl, g, comps)}], json_mode=True, max_tokens=8000))
    by = {saber.canonical(x.get("nombre", ""), lvl): x for x in d.get("competencias") or []}
    doc = J.Document()
    doc.add_heading(f"Plan de estudio Saber {lvl} · {course}", 0)
    doc.add_paragraph("Cada estudiante trabaja sus dos competencias más flojas según sus últimos simulacros.")
    for est in sorted(weak_by):
        doc.add_page_break()
        doc.add_heading(f"Para: {est}", 1)
        doc.add_paragraph("Tu perfil: " + "; ".join(f"{k}: {v} %" for k, v in prof[est].items() if v is not None))
        for v, comp in weak_by[est]:
            x = by.get(comp) or {}
            doc.add_heading(f"{comp} ({v} %)", 2)
            doc.add_paragraph(str(x.get("que_evalua", ""))[:600])
            for s_ in (x.get("estrategias") or [])[:3]:
                doc.add_paragraph(str(s_)[:300], style="List Bullet")
            for j, q in enumerate((x.get("practica") or [])[:3], 1):
                doc.add_paragraph(f"{j}. {str(q.get('contexto', ''))[:400]} {str(q.get('enunciado', ''))[:300]}")
                for L, o in zip("ABCD", (q.get("opciones") or [])[:4]):
                    doc.add_paragraph(f"   {L}) {str(o)[:200]}")
    doc.add_page_break()
    doc.add_heading("Respuestas de la práctica (para el docente)", 1)
    for comp, x in by.items():
        doc.add_paragraph(f"{comp}: " + ", ".join(f"{j}) {str(q.get('respuesta', '')).upper()}" for j, q in enumerate((x.get('practica') or [])[:3], 1)))
    folder = os.path.join(J.settings["output_dir"], "Saber")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r"[^\w -]", " ", course).strip()
    path = os.path.join(folder, f"Planes Saber {lvl} {safe} - {datetime.date.today():%Y-%m-%d}.docx")
    doc.save(path)
    J.generated_files.add(path)
    J._open_doc(path)
    J.notify(f"Listos los planes de estudio Saber de {len(weak_by)} estudiantes de {course}, cada uno con sus dos competencias más flojas.", "SABER")
    return path


# ============================================================================ TABLERO (en este equipo)
@J.app.route("/saber/<path:curso>")
def saber_board(curso):
    from flask import abort
    c = saber.data["cursos"].get(curso)
    if not c:
        abort(404)
    lvl = c["nivel"]
    evo = saber.evolution(curso)
    svg, legend = saber.chart_svg(evo, lvl)
    prof = saber.profile(curso)
    cell = lambda v: "—" if v is None else f'<b class="{"lo" if v < 50 else "mid" if v < 70 else "hi"}">{v}%</b>'
    rows = "".join(f"<tr><td>{html.escape(e)}</td>" + "".join(f"<td>{cell(prof[e].get(k))}</td>" for k in saber.COMP[lvl]) +
                   f"<td>{html.escape(saber.weakest(prof[e]) or '—')}</td></tr>" for e in sorted(prof))
    heads = "".join(f"<th>{html.escape(k)}</th>" for k in saber.COMP[lvl])
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Saber {lvl} · {html.escape(curso)}</title><style>
:root{{--bg:#03060c;--card:#071320;--line:#1d3344;--text:#e6f6ff;--muted:#7d95ab;--a:#2ee6ff}}
body{{margin:0;padding:20px 16px 40px;background:var(--bg);color:var(--text);font-family:system-ui,"Segoe UI",sans-serif}}
h1{{font-size:20px;color:var(--a);margin:0 0 4px}}p.s{{color:var(--muted);margin:0 0 16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:16px;max-width:900px}}
.chart{{width:100%;height:auto}}.grid{{stroke:#1d3344}}.ax{{fill:var(--muted);font-size:11px}}
.lg{{display:inline-flex;align-items:center;gap:6px;margin-right:14px;font-size:13px}}.lg i{{width:12px;height:12px;border-radius:3px;display:inline-block}}
table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left}}
th{{color:var(--muted);font-weight:600}}.lo{{color:#ff6b6b}}.mid{{color:#ffb547}}.hi{{color:#3dff9a}}
</style></head><body><h1>Preparación Saber {lvl} · {html.escape(curso)}</h1>
<p class="s">{len(evo)} simulacros · {html.escape(saber.spoken(curso))}</p>
<div class="card">{svg}<div>{legend}</div></div>
<div class="card"><table><thead><tr><th>Estudiante</th>{heads}<th>Por reforzar</th></tr></thead><tbody>{rows}</tbody></table></div>
</body></html>"""


def saber_start():
    saber.configure(J.CONFIG_DIR)


__all__ = ['_MINI_RE', '_SB_ASK', '_SB_PLAN', '_SB_REP', '_SIM_RE', '_comp_rule', '_sb_course', '_level', 'make_simulacro', 'saber',
           'saber_board', 'saber_from_exam', 'saber_from_ticket', 'saber_plans', 'saber_start', 'saber_voice']
