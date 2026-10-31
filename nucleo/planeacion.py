"""10.8: la planeación del año completo para cada grado y asignatura, alineada a los DBA (o a tu plan de área), que
alimenta la semana lista y el diario de clase, te dice si vas al día y se reajusta si te atrasas.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import re

import anual
import asignaturas
import aula
import diarioclase
import horario
import zeti
from nucleo import J


def year_weeks():
    return anual.split_weeks(J.settings["school_weeks"], zeti.parse_period_weights(J.settings["zeti_period_weights"]))


def where_now(today=None):
    """(semana del año, periodo, semana del periodo) o (None, periodo actual, None) si no sé la fecha de inicio."""
    wpp = year_weeks()
    w = anual.week_now(J.settings["year_start"], sum(wpp), today)
    if w is None:
        return None, int(J.settings["period_current"]), None
    p, wp = anual.period_of(w, wpp)
    return w, p, wp


def plan_targets():
    """Las (clave, grado, asignatura) que hay que planear: cada curso con cada asignatura tuya."""
    out = []
    courses = set(aula.data.get("cursos", {})) | {x.get("curso", "") for x in horario.items if x.get("curso")}
    for c in sorted((c for c in courses if c), key=aula.course_sort_key):
        subs = J.subjects_for(c) or [J.settings["subject_current"] or "Matemáticas"]
        for s in subs:
            out.append((asignaturas.key(c, s, len(subs) >= 2), aula.grade_of(c) or "", s))
    return out


def _plan_area(subject):
    """El plan de área pegado en Ajustes que corresponde a esa asignatura (o todo si no se distingue)."""
    txt = J.settings["area_plan"].strip()
    if not txt:
        return ""
    blocks = re.split(r"\n(?=#|\w[^\n]{0,40}:\s*\n)", txt)
    k = asignaturas.norm(asignaturas.area_of(subject, J._subjects_text()) or subject)
    hit = [b for b in blocks if k.split()[0] in asignaturas.norm(b[:80])]
    return "\n".join(hit) if hit else txt


def plan_one(key, grado, asignatura):
    wpp = year_weeks()
    raw = J.ai_chat([{"role": "user", "content": anual.year_prompt(f"{grado}°" if grado else "bachillerato", asignatura, wpp, _plan_area(asignatura))
                      + J.lessons_ctx()}], json_mode=True, max_tokens=14000)
    periodos = anual.validate(J._extract_json(raw), wpp)
    anual.put(key, grado, asignatura, periodos)
    sync_malla(key)
    return periodos


def sync_malla(key, period=None):
    """La malla del periodo en curso pasa al diario de clase (así funcionan «¿qué temas me faltan?» y la semana lista)."""
    plan = anual.data["planes"].get(key)
    if not plan:
        return False
    p = period or where_now()[1]
    if p > len(plan["periodos"]):
        return False
    diarioclase.set_malla(key, {"titulo": f"Planeación anual · periodo {p}", "periodo": str(p), "semanas": plan["periodos"][p - 1]["semanas"]})
    return True


def plan_year(keys=None, extra=None):
    targets = [x for x in plan_targets() if not keys or x[0] in keys] + list(extra or [])
    done, docs = [], []
    for key, grado, asig in targets:
        try:
            plan_one(key, grado, asig)
        except Exception as e:
            J.log_terminal(f"Planeación anual de {key}: {getattr(e, 'why', e)}", "AVISO")
            continue
        done.append(key)
        if J.Document is not None:
            docs.append(anual.docx(key, anual.data["planes"][key], J.settings["output_dir"], J.Document, J.settings["aula_docente"],
                                   J.settings["aula_institucion"]))
            J.generated_files.add(docs[-1])
    if docs:
        J._open_doc(docs[0])
    J.notify((f"Lista la planeación anual de {len(done)} curso{'s' if len(done) != 1 else ''}: " + ", ".join(done) +
              ". La del periodo en curso ya está en tu diario de clase y la usa la semana lista del domingo. Está en Documentos, Jarvis, "
              "Planeación anual.") if done else "No pude hacer la planeación anual. Revisa que la IA esté conectada e inténtalo otra vez.",
             "PLANEACIÓN")
    return done


def plan_status(key):
    plan = anual.data["planes"].get(key)
    if not plan:
        return None
    w, p, wp = where_now()
    reg = diarioclase.entries(key) + (diarioclase.entries(key.split(" · ")[0]) if " · " in key else [])
    st = anual.status(plan, p, wp or 1, lambda tema: diarioclase.covered(tema, reg))
    return st and dict(st, periodo=p, semana_anio=w)


def plan_spoken(key, st):
    if not st:
        return f"No tengo la planeación anual de {key}. Dime «haz la planeación anual de {key}»."
    if st["semana_anio"] is None:
        head = f"{key}, periodo {st['periodo']}: "
        return head + f"llevas {st['vistos']} temas vistos; faltan {len(st['pendientes'])}. (Pon la fecha de inicio del año en Ajustes para saber en qué semana vas.)"
    d = st["diferencia"]
    estado = "vas al día" if d == 0 else (f"vas adelantado {d} tema{'s' if d != 1 else ''}" if d > 0 else f"vas atrasado {-d} tema{'s' if d != -1 else ''}")
    t = (f"{key}: semana {st['semana']} del periodo {st['periodo']}. Esta semana toca «{st['tema_semana']}». Llevas {st['vistos']} temas "
         f"vistos de {st['esperados']} esperados: {estado}.")
    if d < -1:
        t += f" Te quedan {st['semanas_restantes']} semanas para {len(st['pendientes'])} temas: si quieres, «reajusta la planeación de {key}»."
    return t


def replan(key):
    plan = anual.data["planes"].get(key)
    st = plan_status(key)
    if not (plan and st and st["pendientes"]):
        J.notify("No hay temas pendientes que reajustar.", "PLANEACIÓN")
        return None
    weeks = max(1, st["semanas_restantes"])
    raw = J.ai_chat([{"role": "user", "content": anual.replan_prompt(plan["grado"], plan["asignatura"], st["pendientes"], weeks)}], json_mode=True,
                    max_tokens=3000)
    d = J._extract_json(raw)
    sem = [s for s in (d.get("semanas") or []) if isinstance(s, dict) and s.get("tema")][:weeks]
    if not sem:
        J.notify("La IA no devolvió el reajuste. Inténtalo otra vez.", "PLANEACIÓN")
        return None
    p = st["periodo"]
    old = plan["periodos"][p - 1]["semanas"]
    start = len(old) - weeks
    plan["periodos"][p - 1]["semanas"] = old[:start] + [{"semana": start + i + 1, "tema": str(s["tema"])[:160], "dba": "",
                                                        "evaluacion": str(s.get("nota", ""))[:200]} for i, s in enumerate(sem)]
    anual.save()
    sync_malla(key, p)
    auto = [str(x) for x in (d.get("autonomo") or [])][:5]
    J.notify(f"Reajusté el periodo {p} de {key}: {len(st['pendientes'])} temas en {weeks} semanas. Desde ya: " +
             "; ".join(f"semana {start + i + 1}: {s['tema']}" for i, s in enumerate(sem[:4])) +
             (f". Como trabajo autónomo: {', '.join(auto)}." if auto else "."), "PLANEACIÓN")
    return sem


_PL_ALL = re.compile(r"\b(?:planea|planeame|planifica|organiza)\s+(?:todo\s+)?(?:mi|el)\s+ano(?: escolar)?\b|"
                     r"\b(?:haz|hazme|prepara|preparame|genera|arma)\s+(?:la\s+|mi\s+)?planeacion (?:anual|del ano)(?:\s+de\s+todos(?: mis cursos)?)?$")
_PL_ONE = re.compile(r"\b(?:haz|hazme|prepara|preparame|genera|arma)\s+(?:la\s+)?planeacion (?:anual|del ano)\s+(?:de|del|para)\s+(.+)$")
_PL_ST = re.compile(r"\bcomo voy con la planeacion(?:\s+(?:de|del|en)\s+(.+))?$|\bque (?:me )?toca esta semana(?:\s+en\s+(.+))?$|\bvoy (?:al dia|atrasad[oa])(?:\s+en\s+(.+))?")
_PL_RE = re.compile(r"\b(?:reajusta|reorganiza|reprograma|ajusta)\s+(?:la\s+)?planeacion(?:\s+(?:de|del|en)\s+(.+))?$")


def _key_for(spoken, t):
    c = J._resolve_course((spoken or "").strip())
    if not c:
        return None
    if c in anual.data["planes"]:
        return c
    k = J.grade_key(c, t, ask=False)
    if k in anual.data["planes"]:
        return k
    keys = [x for x in anual.data["planes"] if x.split(" · ")[0] == c.split(" · ")[0]]
    return keys[0] if len(keys) == 1 else (k or c)


def planning_voice(text, t):
    m = _PL_ONE.search(t)
    if m and not re.search(r"\btodos\b", m.group(1)):
        key = _key_for(m.group(1), t)
        tg = [x for x in plan_targets() if x[0] == key] or ([(key, aula.grade_of(key) or "", (key.split(" · ") + ["Matemáticas"])[1])] if key else [])
        if not tg:
            J.reply("¿De qué curso? Por ejemplo: «haz la planeación anual de 7A».", "PLANEACIÓN")
            return True
        if J.state.get("ai") != "ok":
            J.reply("Para la planeación anual necesito la IA conectada.", "PLANEACIÓN")
            return True
        J.reply(f"Preparo la planeación anual de {key} ({J.settings['school_weeks']} semanas, {len(year_weeks())} periodos)…", "PLANEACIÓN")
        known = tg[0][0] in {x[0] for x in plan_targets()}
        run = (lambda: J.plan_year([key])) if known else (lambda: J.plan_year(["\0"], extra=tg))
        if getattr(J._tl, "capture", None) is not None:
            run()
        else:
            J.start_job("Planeando el año", run, "planeacion")
        return True
    if _PL_ALL.search(t):
        tg = plan_targets()
        if not tg:
            J.reply("Necesito tus cursos (listas o horario) para planear el año.", "PLANEACIÓN")
            return True
        if J.state.get("ai") != "ok":
            J.reply("Para la planeación anual necesito la IA conectada.", "PLANEACIÓN")
            return True
        J.request_approval("proyecto", f"Planear el año: {len(tg)} cursos y asignaturas", "; ".join(k for k, _, _ in tg),
                           on_ok=lambda: J.start_job("Planeando el año", J.plan_year, "planeacion"), on_no=lambda: None, ttl=3600,
                           say=f"Planeo el año completo de {len(tg)} cursos y asignaturas (" + ", ".join(k for k, _, _ in tg[:6]) +
                               (f" y {len(tg) - 6} más" if len(tg) > 6 else "") + "), semana a semana con los DBA. Tarda unos minutos. ¿Lo hago? Di «sí» o «no».")
        return True
    m = _PL_RE.search(t)
    if m:
        key = _key_for(m.group(1) or "", t)
        if not key or key not in anual.data["planes"]:
            J.reply("No tengo la planeación anual de ese curso.", "PLANEACIÓN")
            return True
        J.reply(f"Reajusto lo que queda del periodo en {key}…", "PLANEACIÓN")
        if getattr(J._tl, "capture", None) is not None:
            J.replan(key)
        else:
            J.start_job("Reajustando la planeación", lambda: J.replan(key), "planeacion")
        return True
    m = _PL_ST.search(t)
    if m:
        spoken = next((g for g in m.groups() if g), "")
        key = _key_for(spoken, t)
        if not spoken and key not in anual.data["planes"] and anual.data["planes"]:
            parts = [J.plan_spoken(k, J.plan_status(k)) for k in sorted(anual.data["planes"], key=aula.course_sort_key)[:6]]
            J.reply(" ".join(parts), "PLANEACIÓN")
            return True
        J.reply(J.plan_spoken(key or spoken, J.plan_status(key) if key else None), "PLANEACIÓN")
        return True
    return False


def plan_attention():
    """Para «¿qué necesita mi atención?»: cursos donde vas atrasado 2 temas o más."""
    out = []
    if not J.settings["year_start"]:
        return out
    for k in sorted(anual.data["planes"], key=aula.course_sort_key)[:24]:
        st = J.plan_status(k)
        if st and st["semana_anio"] and st["diferencia"] <= -2:
            out.append({"k": f"pl:{k}:{st['periodo']}:{st['semana']}", "p": 3, "t": f"vas atrasado {-st['diferencia']} temas en {k}",
                        "cmd": f"¿cómo voy con la planeación de {k}?"})
    return out


def on_new_period(period):
    """Al pasar de periodo: la malla del nuevo periodo pasa al diario de clase de cada curso."""
    return sum(1 for k in anual.data["planes"] if sync_malla(k, period))


def planning_start():
    anual.configure(J.CONFIG_DIR)


__all__ = ['plan_attention', '_PL_ALL', '_PL_ONE', '_PL_RE', '_PL_ST', '_key_for', '_plan_area', 'anual', 'on_new_period', 'plan_one', 'plan_status', 'plan_targets',
           'plan_year', 'planning_start', 'planning_voice', 'replan', 'plan_spoken', 'sync_malla', 'where_now', 'year_weeks']
