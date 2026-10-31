"""Programa Saber 11 y Saber 9 (10.6): simulacros por competencia, evolución del curso y de cada estudiante.

Cada sesión (un simulacro con hoja de respuestas o un mini simulacro desde el celular) guarda, por estudiante, qué
preguntas acertó y la competencia de cada pregunta. Con eso: el perfil por competencia, la evolución semana a semana
y la competencia más floja de cada uno. Son datos de estudiantes: se cifran con los demás si lo activaste.
"""
import datetime
import os
import re
import threading
import unicodedata

import datos

COMP = {
    11: ["Interpretación y representación", "Formulación y ejecución", "Argumentación"],
    9: ["Comunicación, representación y modelación", "Razonamiento y argumentación", "Planteamiento y resolución de problemas"],
}
COMPONENTES = {11: "estadística, geometría, álgebra y cálculo (contenidos genéricos y no genéricos)",
               9: "numérico-variacional, geométrico-métrico y aleatorio"}
_KEYS = {11: [("interpret", "represent"), ("formul", "ejecu", "resol"), ("argument", "razon", "justific")],
         9: [("comunic", "represent", "model"), ("razon", "argument"), ("plante", "resol", "problem")]}

_lock = threading.Lock()
_path = None
data = {"cursos": {}}
locked = False


def _plain(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "saber.json")
    load()


def load():
    global data, locked
    try:
        d = datos.read_json(_path)
        data, locked = (d if isinstance(d, dict) and isinstance(d.get("cursos"), dict) else {"cursos": {}}), False
    except datos.DataLocked:
        data, locked = {"cursos": {}}, True
    except (OSError, ValueError, TypeError):
        data = {"cursos": {}}


def save():
    if not _path or locked:
        return
    try:
        datos.write_json(_path, data)
    except OSError:
        pass


def level_of(grade):
    """11 para 10° y 11°; 9 para 6° a 9°."""
    return 11 if (grade or 0) >= 10 else 9


def canonical(comp, level):
    """«formulación» → «Formulación y ejecución» (o la primera si no se reconoce)."""
    t = _plain(comp)
    for name, keys in zip(COMP[level], _KEYS[level]):
        if any(k in t for k in keys):
            return name
    return COMP[level][0]


def add_session(curso, level, titulo, fuente, comps, answers, fecha=None):
    """answers: {estudiante: [True/False/None por pregunta]}; comps: competencia de cada pregunta."""
    with _lock:
        c = data["cursos"].setdefault(curso, {"nivel": level, "sesiones": []})
        c["nivel"] = level
        c["sesiones"].append({"fecha": (fecha or datetime.date.today()).isoformat(), "titulo": str(titulo)[:120], "fuente": fuente,
                              "comps": [canonical(x, level) for x in comps], "est": {k: list(v) for k, v in answers.items()}})
        del c["sesiones"][:-60]
        save()
    return c["sesiones"][-1]


def _pct(ok, tot):
    return round(100 * ok / tot) if tot else None


def session_comp(ses, level):
    """% de acierto del curso por competencia en una sesión."""
    out = {}
    for comp in COMP[level]:
        ok = tot = 0
        for ans in ses["est"].values():
            for i, a in enumerate(ans):
                if i < len(ses["comps"]) and ses["comps"][i] == comp:
                    tot += 1
                    ok += 1 if a else 0
        out[comp] = _pct(ok, tot)
    return out


def evolution(curso):
    c = data["cursos"].get(curso)
    if not c:
        return []
    return [{"fecha": s["fecha"], "titulo": s["titulo"], "fuente": s["fuente"], "n": len(s["est"]),
             "comp": session_comp(s, c["nivel"])} for s in c["sesiones"]]


def profile(curso, last=6):
    """{estudiante: {competencia: %}} con las últimas sesiones."""
    c = data["cursos"].get(curso)
    if not c:
        return {}
    acc = {}
    for s in c["sesiones"][-last:]:
        for est, ans in s["est"].items():
            for i, a in enumerate(ans):
                if i >= len(s["comps"]):
                    continue
                d = acc.setdefault(est, {}).setdefault(s["comps"][i], [0, 0])
                d[1] += 1
                d[0] += 1 if a else 0
    return {e: {k: _pct(*v) for k, v in comps.items()} for e, comps in acc.items()}


def weakest(prof):
    vals = [(v, k) for k, v in prof.items() if v is not None]
    return min(vals)[1] if vals else None


def trend(evo, comp):
    pts = [e["comp"].get(comp) for e in evo if e["comp"].get(comp) is not None]
    if len(pts) < 2:
        return None
    return pts[-1] - pts[0]


def spoken(curso):
    c = data["cursos"].get(curso)
    evo = evolution(curso)
    if not evo:
        return f"Aún no hay simulacros Saber de {curso}. Empieza con «haz un simulacro Saber de 20 preguntas para {curso}»."
    lvl = c["nivel"]
    last = evo[-1]
    parts = []
    for comp in COMP[lvl]:
        v = last["comp"].get(comp)
        if v is None:
            continue
        tr = trend(evo, comp)
        parts.append(f"{comp}: {v} %" + (f" ({'+' if tr > 0 else ''}{tr} desde el primero)" if tr is not None and tr != 0 else ""))
    prof = profile(curso)
    weak = {}
    for e, p in prof.items():
        w = weakest(p)
        if w:
            weak[w] = weak.get(w, 0) + 1
    t = f"{curso}, Saber {lvl}, {len(evo)} simulacro{'s' if len(evo) != 1 else ''}. En el último: " + "; ".join(parts) + "."
    if weak:
        comp, n = max(weak.items(), key=lambda x: x[1])
        t += f" La competencia más floja para más estudiantes ({n}) es {comp}."
    return t


def plan_prompt(level, grade, weak_comps):
    return (f"Eres un docente de matemáticas en Colombia que prepara a estudiantes de grado {grade} para la prueba Saber {level} del ICFES. "
            f"Para cada competencia de esta lista: {'; '.join(weak_comps)}, escribe: qué evalúa en palabras sencillas para el estudiante, "
            "3 estrategias concretas para mejorarla y 3 preguntas de práctica tipo Saber (con un contexto corto, 4 opciones y la respuesta). "
            f"Componentes de la prueba: {COMPONENTES[level]}. Texto plano, sin LaTeX. Responde SOLO con JSON: "
            '{"competencias": [{"nombre": str, "que_evalua": str, "estrategias": [str], "practica": [{"contexto": str, "enunciado": str, '
            '"opciones": [str, str, str, str], "respuesta": "a"|"b"|"c"|"d"}]}]}')


def chart_svg(evo, level, w=640, h=260):
    """Las líneas de evolución por competencia (para el tablero)."""
    colors = ["#2ee6ff", "#ffb547", "#b48cff"]
    pad = 36
    n = len(evo)
    xs = [pad + (i * (w - 2 * pad) / max(1, n - 1)) for i in range(n)] if n > 1 else [w / 2]
    y = lambda v: h - pad - (v / 100.0) * (h - 2 * pad)
    out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Evolución por competencia">']
    for v in (0, 50, 100):
        out.append(f'<line x1="{pad}" x2="{w - pad}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/><text x="4" y="{y(v) + 4:.1f}" class="ax">{v}%</text>')
    for k, comp in enumerate(COMP[level]):
        pts = [(xs[i], y(e["comp"][comp])) for i, e in enumerate(evo) if e["comp"].get(comp) is not None]
        if not pts:
            continue
        out.append(f'<polyline fill="none" stroke="{colors[k]}" stroke-width="2.5" points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + '"/>')
        out += [f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.5" fill="{colors[k]}"/>' for a, b in pts]
    for i, e in enumerate(evo):
        out.append(f'<text x="{xs[i]:.1f}" y="{h - 10}" class="ax" text-anchor="middle">{e["fecha"][5:]}</text>')
    out.append("</svg>")
    legend = "".join(f'<span class="lg"><i style="background:{colors[k]}"></i>{c}</span>' for k, c in enumerate(COMP[level]))
    return "".join(out), legend


def report_docx(curso, out_dir, Document, institucion="", docente=""):
    c = data["cursos"].get(curso)
    evo = evolution(curso)
    lvl = c["nivel"]
    doc = Document()
    doc.add_heading(f"Preparación Saber {lvl} · {curso}", 0)
    if institucion or docente:
        doc.add_paragraph(" · ".join(x for x in (institucion, docente) if x))
    doc.add_paragraph(f"Informe del {datetime.date.today():%d/%m/%Y}: {len(evo)} simulacros.")
    doc.add_heading("Evolución del curso por competencia (% de acierto)", 1)
    tb = doc.add_table(rows=1, cols=2 + len(COMP[lvl]))
    tb.style = "Table Grid"
    for cell, hd in zip(tb.rows[0].cells, ["Fecha", "Simulacro", *COMP[lvl]]):
        cell.text = hd
    for e in evo:
        r = tb.add_row().cells
        r[0].text, r[1].text = e["fecha"], f"{e['titulo']} ({e['n']} est.)"
        for i, comp in enumerate(COMP[lvl]):
            v = e["comp"].get(comp)
            r[2 + i].text = "—" if v is None else f"{v} %"
    prof = profile(curso)
    doc.add_heading("Estudiantes", 1)
    tb = doc.add_table(rows=1, cols=2 + len(COMP[lvl]))
    tb.style = "Table Grid"
    for cell, hd in zip(tb.rows[0].cells, ["Estudiante", *COMP[lvl], "Por reforzar"]):
        cell.text = hd
    for est in sorted(prof):
        r = tb.add_row().cells
        r[0].text = est
        for i, comp in enumerate(COMP[lvl]):
            v = prof[est].get(comp)
            r[1 + i].text = "—" if v is None else f"{v} %"
        r[-1].text = weakest(prof[est]) or "—"
    doc.add_heading("Lectura", 1)
    doc.add_paragraph(re.sub(r"\s+", " ", spoken(curso)))
    folder = os.path.join(out_dir, "Saber")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r"[^\w -]", " ", curso).strip()
    path = os.path.join(folder, f"Informe Saber {lvl} {safe} - {datetime.date.today():%Y-%m-%d}.docx")
    doc.save(path)
    return path
