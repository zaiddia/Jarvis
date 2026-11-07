"""Boletines del periodo para las familias (12.8): un PDF por estudiante, listo para enviar por WhatsApp o imprimir.

Cada boletín trae, por asignatura, la valoración del periodo como la calcula Zeti (Conocer, Hacer, Ser y
Autoevaluación con sus actividades), el desempeño, las fallas, cómo va el año (periodos anteriores y lo que le falta
para aprobar), las anotaciones del observador y un comentario del docente con recomendaciones para la casa. El
comentario lo redacta la IA solo con esos datos; si no hay IA, Jarvis lo escribe con reglas a partir de las notas.
Lógica pura (sin Jarvis): datos → hoja → PDF.
"""
import datetime
import json
import os
import re

import zeti

LEVEL_COLORS = {"Superior": (22, 150, 90), "Alto": (30, 110, 200), "Básico": (210, 140, 20), "Bajo": (200, 50, 50), "": (120, 130, 140)}
TIPS = {
    "conocer": "Repasar con él o ella, 20 minutos al día, los temas vistos en clase y pedirle que le explique un ejercicio.",
    "hacer": "Revisar cada semana que los talleres y trabajos queden completos y se entreguen a tiempo.",
    "ser": "Conversar sobre su participación, puntualidad y responsabilidad en clase, y reconocer sus avances.",
    "auto": "Animarle a valorar con sinceridad su propio trabajo y a fijarse una meta para el próximo periodo.",
    "fallas": "Procurar que asista a todas las clases y, si falta, que se ponga al día con un compañero.",
    "bien": "Seguir acompañando su buen ritmo con un horario fijo de estudio en casa.",
}


def _fmt(x):
    return "" if x is None else f"{x:.1f}".replace(".", ",")


def sheet(curso, estudiante, notas, fallas=0, observador=(), year=None, weights=None, since="", materia="", periodo=1):
    """La hoja del boletín de un estudiante en una asignatura (todo lo que se imprime, ya calculado)."""
    w = weights or zeti.WEIGHTS
    ns = [n for n in notas or [] if n.get("nota") is not None and str(n.get("fecha", "")) >= (since or "")]
    v = zeti.valoracion(ns, w)
    bd = zeti.by_dim(ns)
    dims = []
    for d, label, _ in zeti.DIMS:
        if not w.get(d):
            continue
        dims.append({"id": d, "dim": label, "peso": w[d], "nota": v["dims"].get(d),
                     "actividades": [(a, zeti.rhu(x, 1)) for a, x in bd.get(d, [])]})
    y = year or {}
    return {"estudiante": estudiante, "curso": curso, "materia": materia, "periodo": int(periodo or 1),
            "val": v["val"], "letra": v["letra"], "desempeno": zeti.performance(v["val"]), "dims": dims, "faltan": v["faltan"],
            "fallas": int(fallas or 0), "n_notas": len(ns),
            "observador": [{"fecha": x.get("fecha", ""), "tipo": x.get("tipo", ""), "texto": str(x.get("texto", ""))[:300]}
                           for x in list(observador or [])[-4:]],
            "previos": list(y.get("previos") or []), "vf_proy": y.get("vf_proy"), "vra": y.get("vra"),
            "aprobo": bool(y.get("aprobo")), "pierde": bool(y.get("pierde"))}


def _facts_for_ai(s):
    return {"estudiante": s["estudiante"], "materia": s["materia"], "periodo": s["periodo"], "valoracion": s["val"],
            "desempeno": s["desempeno"], "por_dimension": {d["dim"]: d["nota"] for d in s["dims"] if d["nota"] is not None},
            "sin_notas_en": [d["dim"] for d in s["dims"] if d["nota"] is None], "fallas": s["fallas"],
            "observador": [x["texto"] for x in s["observador"]], "necesita_para_aprobar_el_ano": s["vra"],
            "en_riesgo_de_perder_el_ano": s["pierde"]}


def comment_prompt(sheets, docente="", institucion=""):
    lines = [f"id {i}: " + json.dumps(_facts_for_ai(s), ensure_ascii=False) for i, s in enumerate(sheets)]
    return ("Eres un docente de un colegio en Colombia que escribe el comentario del boletín del periodo para la familia. "
            "Para cada estudiante, con SOLO estos datos (no inventes notas, hechos ni diagnósticos): un comentario de 2 o 3 "
            "frases (máximo 380 caracteres), cálido y claro, que empiece por una fortaleza y diga con respeto qué debe "
            "mejorar; y 2 recomendaciones concretas para apoyar desde la casa (máximo 140 caracteres cada una). Trato de "
            "«usted» a la familia; al estudiante, por su nombre. "
            + (f"Docente: {docente}. " if docente else "") + (f"Institución: {institucion}. " if institucion else "")
            + "\nDatos:\n" + "\n".join(lines)
            + '\n\nDevuelve SOLO JSON: {"comentarios": [{"id": 0, "comentario": str, "recomendaciones": [str, str]}]}')


def comment_validate(d, n):
    out = {}
    for r in (d or {}).get("comentarios") or []:
        try:
            i = int(r["id"])
        except (KeyError, ValueError, TypeError):
            continue
        txt = re.sub(r"\s+", " ", str(r.get("comentario") or "")).strip()
        if 0 <= i < n and txt:
            out[i] = {"comentario": txt[:520],
                      "recomendaciones": [str(x).strip()[:200] for x in (r.get("recomendaciones") or []) if str(x).strip()][:3]}
    return out


def first_name(name):
    parts = str(name).split()
    return parts[0] if parts else str(name)


def fallback_comment(s):
    """Sin IA: el comentario con reglas, a partir de las notas (siempre sale un boletín)."""
    nm = first_name(s["estudiante"])
    if s["val"] is None:
        return {"comentario": f"Aún no hay notas suficientes en este periodo para valorar el desempeño de {nm}. Le invito a "
                              "acercarse al colegio para conversar sobre su proceso.",
                "recomendaciones": [TIPS["conocer"], TIPS["hacer"]]}
    have = [d for d in s["dims"] if d["nota"] is not None and d["id"] != "auto"]
    best = max(have, key=lambda d: d["nota"]) if have else None
    worst = min(have, key=lambda d: d["nota"]) if have else None
    txt = f"En este periodo {nm} obtuvo una valoración de {_fmt(s['val'])}, con desempeño {s['desempeno'].lower()}."
    if best and worst and best["nota"] - worst["nota"] >= 0.3:
        txt += f" Se destaca en {best['dim']} ({_fmt(best['nota'])}) y necesita fortalecer {worst['dim']} ({_fmt(worst['nota'])})."
    elif s["val"] >= zeti.SCALE["alto"]:
        txt += " Ha trabajado de forma constante en todas las dimensiones; ¡felicitaciones!"
    elif best:
        txt += " Puede mejorar con más constancia en el estudio y en la entrega de los trabajos."
    if s["fallas"] >= 3:
        txt += f" Registra {s['fallas']} fallas, que afectan su proceso."
    if s["pierde"]:
        txt += " Con lo acumulado está en riesgo de no aprobar el año: es importante que trabajemos juntos."
    elif s["vra"] is not None:
        txt += f" Para aprobar el año necesita en promedio {_fmt(s['vra'])} en lo que queda."
    recs = []
    if worst and (worst["nota"] < zeti.SCALE["alto"] or s["val"] < zeti.SCALE["alto"]):
        recs.append(TIPS[worst["id"]])
    if s["fallas"] >= 3:
        recs.append(TIPS["fallas"])
    if len(recs) < 2:
        recs.append(TIPS["bien"] if s["val"] >= zeti.SCALE["alto"] else TIPS["hacer" if not recs or recs[0] != TIPS["hacer"] else "conocer"])
    return {"comentario": txt, "recomendaciones": recs[:2]}


def message(name, sheets, docente=""):
    """El texto para mandar con el PDF por WhatsApp."""
    bits = [f"{s['materia'] or 'la asignatura'}: {_fmt(s['val'])} ({s['desempeno']})" for s in sheets if s["val"] is not None]
    per = sheets[0]["periodo"] if sheets else 1
    return (f"Buen día, familia de {name}. Le comparto el boletín del periodo {per}"
            + (": " + "; ".join(bits) if bits else "") + ". Cualquier inquietud, con gusto la atiendo."
            + (f" — {docente}" if docente else ""))


# ----------------------------------------------------------------------------- PDF
def safe(text):
    return re.sub(r"\s+", " ", re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", str(text))).strip()[:70] or "boletin"


def font_files():
    """Una letra con tildes y eñes: Arial de Windows, o DejaVu/Liberation en Linux. → (normal, negrita) o None."""
    cands = [(r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
             (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
             ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
             ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
             ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf")]
    windir = os.environ.get("WINDIR")
    if windir:
        cands.insert(0, (os.path.join(windir, "Fonts", "arial.ttf"), os.path.join(windir, "Fonts", "arialbd.ttf")))
    for reg, bold in cands:
        if os.path.exists(reg) and os.path.exists(bold):
            return reg, bold
    return None


_LATIN = str.maketrans({"…": "...", "·": "-", "—": "-", "–": "-", "→": "->", "“": '"', "”": '"', "‘": "'", "’": "'", "•": "-", "≥": ">=", "≤": "<="})


class _Doc:
    """Envoltura de fpdf2 con la letra que haya (si no hay TTF, Helvetica y solo caracteres latinos)."""

    def __init__(self, FPDF):
        self.pdf = FPDF(orientation="P", unit="mm", format="Letter")
        self.pdf.set_auto_page_break(True, margin=16)
        self.pdf.set_margins(16, 14, 16)
        ff = font_files()
        if ff:
            self.pdf.add_font("J", "", ff[0])
            self.pdf.add_font("J", "B", ff[1])
            self.family, self.uni = "J", True
        else:
            self.family, self.uni = "helvetica", False

    def t(self, s):
        s = str(s)
        return s if self.uni else s.translate(_LATIN).encode("latin-1", "replace").decode("latin-1")

    def font(self, size, bold=False, color=(30, 34, 40)):
        self.pdf.set_font(self.family, "B" if bold else "", size)
        self.pdf.set_text_color(*color)


def _page(d, s, txt, institucion, docente, fecha):
    p = d.pdf
    p.add_page()
    W = p.w - p.l_margin - p.r_margin
    # encabezado
    p.set_fill_color(14, 40, 66)
    p.rect(0, 0, p.w, 30, "F")
    p.set_xy(p.l_margin, 7)
    d.font(15, True, (255, 255, 255))
    p.cell(W * 0.7, 8, d.t(institucion or "Boletín del periodo"))
    d.font(10, False, (190, 220, 245))
    p.cell(W * 0.3, 8, d.t(f"Periodo {s['periodo']} · {fecha}"), align="R")
    p.set_xy(p.l_margin, 16)
    d.font(11, False, (190, 220, 245))
    p.cell(W, 7, d.t("Boletín del periodo" + (f" · {s['materia']}" if s["materia"] else "")))
    # estudiante + valoración
    p.set_xy(p.l_margin, 36)
    d.font(17, True)
    p.cell(W - 46, 9, d.t(s["estudiante"]))
    y0 = 36
    col = LEVEL_COLORS.get(s["desempeno"], LEVEL_COLORS[""])
    p.set_fill_color(*col)
    p.rect(p.l_margin + W - 42, y0, 42, 24, "F")
    p.set_xy(p.l_margin + W - 42, y0 + 2)
    d.font(22, True, (255, 255, 255))
    p.cell(42, 11, d.t(_fmt(s["val"]) or "—"), align="C")
    p.set_xy(p.l_margin + W - 42, y0 + 14)
    d.font(10, True, (255, 255, 255))
    p.cell(42, 7, d.t(s["desempeno"] or "Sin notas"), align="C")
    p.set_xy(p.l_margin, 46)
    d.font(10, False, (90, 100, 112))
    p.cell(W - 46, 6, d.t(f"Curso {s['curso']}" + (f"   ·   Docente: {docente}" if docente else "") + f"   ·   Fallas: {s['fallas']}"))
    p.set_y(66)
    # tabla de dimensiones
    d.font(11, True)
    p.cell(W, 7, d.t("Valoración por dimensión (como en Zeti)"), new_x="LMARGIN", new_y="NEXT")
    p.set_fill_color(232, 240, 248)
    d.font(9, True, (40, 50, 60))
    cw = [34, 14, 25, W - 73]
    for h, wd in zip(["Dimensión", "Peso", "Valoración", "Actividades del periodo"], cw):
        p.cell(wd, 7, d.t(h), border=0, fill=True)
    p.ln(7)
    for dm in s["dims"]:
        acts = ", ".join(f"{a} {_fmt(x)}" for a, x in dm["actividades"]) or "Sin notas todavía"
        d.font(9, False)
        y = p.get_y()
        p.set_xy(p.l_margin + cw[0] + cw[1] + cw[2], y + 1)
        p.multi_cell(cw[3], 5, d.t(acts[:420]), new_x="LMARGIN", new_y="NEXT")
        h = max(7, p.get_y() - y + 1)
        p.set_xy(p.l_margin, y)
        d.font(9, True)
        p.cell(cw[0], h, d.t(dm["dim"]))
        d.font(9, False)
        p.cell(cw[1], h, f"{dm['peso']} %")
        d.font(10, True, LEVEL_COLORS.get(zeti.performance(dm["nota"]), LEVEL_COLORS[""]))
        p.cell(cw[2], h, d.t(_fmt(dm["nota"]) or "—"))
        p.set_draw_color(220, 226, 232)
        p.line(p.l_margin, y + h, p.l_margin + W, y + h)
        p.set_y(y + h + 1)
    # el año
    if s["previos"] and any(v is not None for v in s["previos"]):
        p.ln(2)
        d.font(11, True)
        p.cell(W, 7, d.t("Cómo va el año"), new_x="LMARGIN", new_y="NEXT")
        d.font(10, False)
        bits = [f"Periodo {i + 1}: {_fmt(v) or '—'}" for i, v in enumerate(s["previos"])]
        if s["vf_proy"] is not None:
            bits.append(f"Acumulado con este periodo: {_fmt(s['vf_proy'])}")
        line = "   ·   ".join(bits)
        if s["aprobo"]:
            line += ".  Ya aprobó el año."
        elif s["vra"] is not None:
            line += f".  Necesita en promedio {_fmt(s['vra'])} en lo que queda del año para aprobar."
        p.multi_cell(W, 5.5, d.t(line), new_x="LMARGIN", new_y="NEXT")
    # observador
    if s["observador"]:
        p.ln(2)
        d.font(11, True)
        p.cell(W, 7, d.t("Observaciones"), new_x="LMARGIN", new_y="NEXT")
        d.font(9.5, False)
        for x in s["observador"]:
            p.multi_cell(W, 5, d.t(f"{x['fecha']} ({x['tipo']}): {x['texto']}"), new_x="LMARGIN", new_y="NEXT")
    # comentario
    p.ln(3)
    d.font(11, True)
    p.cell(W, 7, d.t("Comentario del docente"), new_x="LMARGIN", new_y="NEXT")
    d.font(10.5, False)
    p.multi_cell(W, 5.6, d.t(txt["comentario"]), new_x="LMARGIN", new_y="NEXT")
    if txt.get("recomendaciones"):
        p.ln(1.5)
        d.font(10.5, True)
        p.cell(W, 6, d.t("Para apoyar desde la casa"), new_x="LMARGIN", new_y="NEXT")
        d.font(10, False)
        for r in txt["recomendaciones"]:
            p.multi_cell(W, 5.4, d.t("• " + r), new_x="LMARGIN", new_y="NEXT")
    # firmas
    y = max(p.get_y() + 14, p.h - 40)
    if y > p.h - 22:
        p.add_page()
        y = 40
    p.set_draw_color(120, 130, 140)
    p.line(p.l_margin, y, p.l_margin + 70, y)
    p.line(p.l_margin + W - 70, y, p.l_margin + W, y)
    d.font(9, False, (90, 100, 112))
    p.set_xy(p.l_margin, y + 1)
    p.cell(70, 5, d.t(docente or "Docente"))
    p.set_xy(p.l_margin + W - 70, y + 1)
    p.cell(70, 5, d.t("Firma del acudiente"))
    p.set_auto_page_break(False)
    p.set_xy(p.l_margin, p.h - 14)
    d.font(7.5, False, (140, 150, 160))
    p.cell(W, 4, d.t("Documento informativo para la familia. La valoración oficial es la que queda registrada en la plataforma de la institución."),
           align="C")
    p.set_auto_page_break(True, margin=16)


def available():
    try:
        import fpdf  # noqa: F401
        return True
    except ImportError:
        return False


def build_pdf(pages, path, institucion="", docente="", fecha=None):
    """pages: [(hoja, texto)] → un PDF (una página por asignatura). Devuelve la ruta."""
    from fpdf import FPDF
    d = _Doc(FPDF)
    d.pdf.set_title(d.t(f"Boletín {pages[0][0]['estudiante']}" if pages else "Boletín"))
    d.pdf.set_author(d.t(docente or "Jarvis"))
    f = (fecha or datetime.date.today()).strftime("%d/%m/%Y")
    for s, txt in pages:
        _page(d, s, txt, institucion, docente, f)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    d.pdf.output(path)
    return path


def folder_name(curso, periodo, fecha=None):
    return safe(f"{curso} periodo {periodo} {(fecha or datetime.date.today()):%Y-%m-%d}")
