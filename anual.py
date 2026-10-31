"""Planeación del año completo (10.8). Lógica pura, sin Jarvis.

Para cada curso y asignatura: los periodos del año (con los pesos de Zeti) y, en cada uno, los temas semana a semana
alineados con los DBA y los Estándares del MEN (o con el plan de área de tu institución si lo pegas). Se compara con
lo que vas registrando en el diario de clase para saber si vas al día, adelantado o atrasado, y se reajusta.
"""
import datetime
import os
import re
import threading

_lock = threading.Lock()
_path = None
data = {"planes": {}}           # {clave: {"grado", "asignatura", "creado", "periodos": [{"n", "semanas": [{"semana", "tema", "dba", "evaluacion"}]}]}}


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "planeacion_anual.json")
    load()


def load():
    import json
    global data
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        data = d if isinstance(d, dict) and isinstance(d.get("planes"), dict) else {"planes": {}}
    except (OSError, ValueError, TypeError):
        data = {"planes": {}}


def save():
    import json
    if not _path:
        return
    try:
        with _lock:
            tmp = _path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, _path)
    except OSError:
        pass


def split_weeks(total, weights):
    """40 semanas con pesos 34/33/33 → [14, 13, 13]."""
    raw = [total * w / sum(weights) for w in weights]
    out = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: -(raw[i] - out[i]))[:total - sum(out)]:
        out[i] += 1
    return out


def week_now(year_start, total, today=None):
    """Semana escolar de hoy (1…total) o None si no ha empezado / ya terminó."""
    today = today or datetime.date.today()
    try:
        start = datetime.date.fromisoformat(year_start)
    except (TypeError, ValueError):
        return None
    n = (today - start).days // 7 + 1
    return n if 1 <= n <= total else None


def period_of(week, weeks_per_period):
    """(periodo 1…, semana dentro del periodo 1…)."""
    acc = 0
    for i, n in enumerate(weeks_per_period):
        if week <= acc + n:
            return i + 1, week - acc
        acc += n
    return len(weeks_per_period), weeks_per_period[-1]


def year_prompt(grado, asignatura, weeks_per_period, plan_area=""):
    total = sum(weeks_per_period)
    per = ", ".join(f"periodo {i + 1}: {n} semanas" for i, n in enumerate(weeks_per_period))
    return (f"Eres un docente experto en Colombia. Haz la planeación anual de {asignatura} para grado {grado} ({total} semanas de clase; "
            f"{per}). Para cada semana: el tema (corto y concreto), el DBA o estándar básico de competencias del MEN que se trabaja y la "
            "evaluación sugerida (corta). Progresión lógica de lo simple a lo complejo; en cada periodo deja la última semana para "
            "evaluación y refuerzo. "
            + (f"Usa como base el plan de área de la institución (respeta sus temas y su orden):\n«{plan_area[:4000]}»\n" if plan_area else
               "Basado en los DBA y los Estándares Básicos de Competencias vigentes para ese grado. ") +
            'Responde SOLO con JSON: {"periodos": [{"n": 1, "semanas": [{"semana": 1, "tema": str, "dba": str, "evaluacion": str}]}]}')


def validate(d, weeks_per_period):
    if not isinstance(d, dict) or not isinstance(d.get("periodos"), list):
        raise ValueError("la planeación no trae periodos")
    out = []
    for i, n in enumerate(weeks_per_period):
        p = d["periodos"][i] if i < len(d["periodos"]) and isinstance(d["periodos"][i], dict) else {"semanas": []}
        sem = [s for s in (p.get("semanas") or []) if isinstance(s, dict) and str(s.get("tema", "")).strip()][:n]
        if not sem:
            raise ValueError(f"el periodo {i + 1} viene vacío")
        while len(sem) < n:                            # si faltan semanas: refuerzo
            sem.append({"tema": "Refuerzo y evaluación del periodo", "dba": "", "evaluacion": ""})
        out.append({"n": i + 1, "semanas": [{"semana": j + 1, "tema": str(s["tema"]).strip()[:160], "dba": str(s.get("dba", "")).strip()[:300],
                                             "evaluacion": str(s.get("evaluacion", "")).strip()[:200]} for j, s in enumerate(sem)]})
    return out


def put(key, grado, asignatura, periodos):
    with _lock:
        data["planes"][key] = {"grado": grado, "asignatura": asignatura, "creado": datetime.date.today().isoformat(), "periodos": periodos}
    save()


def status(plan, period, week_in_period, covered_fn):
    """Cómo va: tema de esta semana, cuántos temas del periodo van vistos frente a los que deberían."""
    if not plan or period > len(plan["periodos"]):
        return None
    sem = plan["periodos"][period - 1]["semanas"]
    expected = min(len(sem), max(0, week_in_period - 1))           # los de las semanas ya pasadas
    seen = [s for s in sem if covered_fn(s["tema"])]
    pending = [s for s in sem if not covered_fn(s["tema"])]
    now = sem[min(len(sem), max(1, week_in_period)) - 1]
    return {"semana": week_in_period, "tema_semana": now["tema"], "vistos": len(seen), "esperados": expected,
            "diferencia": len(seen) - expected, "pendientes": [s["tema"] for s in pending], "semanas_restantes": max(0, len(sem) - week_in_period + 1)}


def replan_prompt(grado, asignatura, pendientes, weeks_left):
    return (f"Soy docente de {asignatura}, grado {grado}, en Colombia. Me quedan {weeks_left} semanas del periodo y estos temas pendientes: "
            f"{'; '.join(pendientes)}. Reorganízalos en exactamente {weeks_left} semanas: junta los que se puedan trabajar juntos, prioriza "
            "lo esencial (lo que necesitan para el siguiente periodo y para las pruebas Saber) y di qué se podría dejar como trabajo autónomo. "
            'Responde SOLO con JSON: {"semanas": [{"tema": str, "nota": str}], "autonomo": [str]}')


def docx(key, plan, out_dir, Document, docente="", institucion=""):
    doc = Document()
    doc.add_heading(f"Planeación anual · {plan['asignatura']} · {key.split(' · ')[0]}", 0)
    if institucion or docente:
        doc.add_paragraph(" · ".join(x for x in (institucion, docente) if x))
    for p in plan["periodos"]:
        doc.add_heading(f"Periodo {p['n']}", 1)
        tb = doc.add_table(rows=1, cols=4)
        tb.style = "Table Grid"
        for c, h in zip(tb.rows[0].cells, ("Semana", "Tema", "DBA / estándar", "Evaluación")):
            c.text = h
        for s in p["semanas"]:
            r = tb.add_row().cells
            r[0].text, r[1].text, r[2].text, r[3].text = str(s["semana"]), s["tema"], s["dba"], s["evaluacion"]
    folder = os.path.join(out_dir, "Planeación anual")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', " ", key).strip()
    path = os.path.join(folder, f"Planeación anual {safe} - {datetime.date.today():%Y}.docx")
    doc.save(path)
    return path
