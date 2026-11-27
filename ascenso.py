"""12.69: preparación para el concurso de ascenso y reubicación docente (Decreto Ley 1278 de 2002). Lógica pura.

Qué evalúa la prueba pedagógica (docentes de aula): contexto de la práctica, reflexión y planeación, praxis pedagógica y
ambiente de aula. Es escrita y basada en casos: situaciones de una institución con la mejor decisión pedagógica.
Los cinco instrumentos suman 100 puntos y se aprueba con más de 80: prueba pedagógica 45, experiencia 20, zona 15,
movimientos en el escalafón 15 y autoevaluación 5 (según el esquema vigente y el proyecto de resolución publicado).

Las preguntas de los simulacros las escribe la IA: son práctica, no preguntas oficiales.
"""
import random
import re

COMPETENCIAS = {
    "contexto": "Contexto de la práctica (social, económico, cultural, institucional y profesional)",
    "planeacion": "Reflexión y planeación",
    "praxis": "Praxis pedagógica (interacción y procesos didácticos)",
    "ambiente": "Ambiente de aula",
}
_ALIAS = [("contexto", r"contexto"), ("planeacion", r"planea|reflexi"), ("praxis", r"praxis|didactic|interacci"),
          ("ambiente", r"ambiente|convivencia|clima")]
PASS = 80


def competence_in(t):
    for k, rx in _ALIAS:
        if re.search(rx, t or ""):
            return k
    return ""


def prompt(n, area="", competencia="", nivel=""):
    comp = COMPETENCIAS.get(competencia, "")
    return (f"Escribe {n} preguntas de práctica para la prueba pedagógica escrita del concurso de ascenso y reubicación docente "
            "de Colombia (Decreto Ley 1278 de 2002), para un docente de aula"
            + (f" de {area}" if area else "") + (f" de {nivel}" if nivel else "") + ".\n"
            "La prueba es basada en casos: cada pregunta describe en 3 a 6 frases una situación realista de una institución educativa "
            "colombiana (oficial, con sus retos de contexto) y pide la MEJOR decisión pedagógica. "
            + (f"Todas sobre la competencia «{comp}». " if comp else
               "Reparte las preguntas entre: " + "; ".join(COMPETENCIAS.values()) + ". ")
            + "Cuatro opciones (A-D) plausibles; solo una es la mejor según la evidencia pedagógica, el enfoque de derechos, la "
              "evaluación formativa, la inclusión (Decreto 1421 de 2017), la convivencia escolar (Ley 1620 de 2013) y la autonomía "
              "institucional (PEI, SIEE). Evita opciones absurdas, trampas de palabras y datos que cambien con el tiempo. La explicación "
              "dice por qué la correcta es la mejor y por qué las otras no, en máximo 60 palabras.\n"
              "Responde SOLO con JSON: {\"preguntas\": [{\"competencia\": \"contexto|planeacion|praxis|ambiente\", \"caso\": str, "
              "\"pregunta\": str, \"opciones\": {\"A\": str, \"B\": str, \"C\": str, \"D\": str}, \"correcta\": \"A|B|C|D\", "
              "\"explicacion\": str}]}")


def _s(v, n):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def clean(d, n=None, seed=None):
    """Valida las preguntas y baraja la posición de la correcta (la IA tiende a ponerla siempre en la misma letra)."""
    rnd = random.Random(seed)
    out = []
    for q in (d or {}).get("preguntas") or []:
        if not isinstance(q, dict):
            continue
        ops = q.get("opciones") or {}
        if isinstance(ops, list):
            ops = dict(zip("ABCD", ops))
        ops = {k.upper(): _s(v, 400) for k, v in ops.items() if str(k).upper() in "ABCD" and _s(v, 400)}
        ok = str(q.get("correcta", "")).strip().upper()[:1]
        if len(ops) != 4 or ok not in ops or not _s(q.get("caso"), 1500):
            continue
        texts = [ops[k] for k in "ABCD"]
        if len(set(t.lower() for t in texts)) < 4:
            continue
        right = ops[ok]
        rnd.shuffle(texts)
        comp = str(q.get("competencia", "")).lower()
        comp = comp if comp in COMPETENCIAS else competence_in(comp) or "praxis"
        out.append({"competencia": comp, "caso": _s(q["caso"], 1500), "pregunta": _s(q.get("pregunta"), 400) or "¿Qué es lo más adecuado?",
                    "opciones": dict(zip("ABCD", texts)), "correcta": "ABCD"[texts.index(right)],
                    "explicacion": _s(q.get("explicacion"), 600)})
    if not out:
        raise ValueError("la IA no dio preguntas válidas")
    return out[:n] if n else out


def answer_letter(t):
    """«la b», «opción c», «respuesta d», «a» → letra; si no, ""."""
    m = re.fullmatch(r"(?:jarvis\s+)?(?:es\s+)?(?:la\s+|el\s+)?(?:opcion\s+|respuesta\s+|letra\s+)?([abcd])(?:\s+es la (?:correcta|respuesta))?", (t or "").strip())
    return m.group(1).upper() if m else ""


def spoken_question(q, i, n):
    ops = " ".join(f"{k}: {v}" for k, v in q["opciones"].items())
    return f"Pregunta {i} de {n}, sobre {COMPETENCIAS[q['competencia']].split(' (')[0].lower()}. {q['caso']} {q['pregunta']} {ops}"


def summary(results):
    """results: [{"competencia", "ok": bool}] → (aciertos, total, {comp: (bien, total)}, la más floja)"""
    by = {}
    for r in results:
        b, t = by.get(r["competencia"], (0, 0))
        by[r["competencia"]] = (b + bool(r["ok"]), t + 1)
    good = sum(1 for r in results if r["ok"])
    weak = min(by, key=lambda k: by[k][0] / by[k][1]) if by else ""
    return good, len(results), by, weak


# ---------------------------------------------------------------- puntos de los otros instrumentos
def experience_points(years):
    if years is None or years < 3:
        return None
    return 14 if years <= 6 else 16 if years <= 10 else 18 if years <= 14 else 20


ZONES = [("rural de dificil acceso", 15, r"dificil acceso"), ("rural", 14, r"\brural\b"),
         ("urbana de municipio no certificado", 13, r"no certificad"), ("urbana de municipio o distrito certificado", 12, r"urbana|certificad|ciudad|cali|distrito")]


def zone_points(t):
    for name, pts, rx in ZONES:
        if re.search(rx, t or ""):
            return name, pts
    return "", None


def moves_points(n):
    if n is None or n < 0:
        return None
    return max(7, 15 - 2 * n)


_NUMS = {"ningun": 0, "ninguno": 0, "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
         "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
         "veinte": 20}


def _num(w):
    return int(w) if w.isdigit() else _NUMS.get(w)


def parse_points(t):
    """«8 años, zona urbana de Cali, ningún ascenso» → (años, (zona, pts), movimientos)"""
    y = re.search(r"\b(\d{1,2}|" + "|".join(_NUMS) + r")\s+anos?\b", t or "")
    mv = re.search(r"\b(\d|ningun|ninguno|cero|un|uno|una|dos|tres|cuatro)\s+(?:ascensos?|reubicacion(?:es)?|movimientos?)\b", t or "")
    return (_num(y.group(1)) if y else None), zone_points(t), (_num(mv.group(1)) if mv else None)


def needed_text(years, zone, moves, auto=5):
    e, (zname, z), m = experience_points(years), zone, moves_points(moves)
    if e is None:
        return "Para concursar necesitas al menos tres años de servicio efectivo desde la posesión en período de prueba."
    if z is None or m is None:
        return ""
    base = e + z + m + auto
    need = PASS - base
    txt = (f"Con {years} años de servicio sumas {e} puntos, la zona {zname} da {z}, "
           f"{'ningún movimiento previo' if moves == 0 else str(moves) + ' movimiento' + ('s' if moves != 1 else '') + ' previos'} "
           f"da {m} y la autoevaluación hasta {auto}: en total {base} de 55. ")
    if need >= 45:
        return txt + "Para pasar de 80 necesitarías la prueba pedagógica casi perfecta: es muy difícil este año."
    pct = round(100 * (need + 0.01) / 45)
    return txt + (f"Para pasar de 80 necesitas más de {need} de los 45 puntos de la prueba pedagógica, es decir, alrededor del "
                  f"{pct} % de la prueba.")


__all__ = ["COMPETENCIAS", "PASS", "competence_in", "prompt", "clean", "answer_letter", "spoken_question", "summary",
           "experience_points", "ZONES", "zone_points", "moves_points", "parse_points", "needed_text"]
