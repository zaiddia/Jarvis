"""12.53: reglas automáticas «si pasa esto, haz aquello» para el aula. Funciones puras: entender la regla dicha a tu
manera y decidir si un hecho la cumple.

    «si alguien saca menos de 3 en un quiz, prepárale un refuerzo y avísame»   → nota_baja (umbral 3) · refuerzo + avisar
    «si un estudiante falta 3 veces seguidas, recuérdame llamar al acudiente»   → fallas (3 seguidas) · recordar acudiente
    «cuando alguien saque 5, felicítalo»                                        → nota_alta (umbral 5) · felicitar
"""
import re

MAX_RULES = 20
_NUM = {"uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5}


def _n(w, default):
    w = (w or "").strip().replace(",", ".")
    if w in _NUM:
        return float(_NUM[w])
    try:
        return float(w)
    except ValueError:
        return default


_LOW = re.compile(r"\b(?:si|cuando|cada vez que)\s+(?:alguien|algun estudiante|un estudiante|uno de mis estudiantes|algun alumno)\s+"
                  r"(?:saca|saque|obtiene|obtenga|tiene|tenga)\s+(?:menos de|por debajo de|bajo)\s+(\d(?:[.,]\d)?|uno|dos|tres|cuatro)"
                  r"(?:\s+en\s+(?:un|una|el|la|cualquier)?\s*(quiz|evaluacion|examen|taller|prueba|nota))?")
_HIGH = re.compile(r"\b(?:si|cuando|cada vez que)\s+(?:alguien|algun estudiante|un estudiante)\s+(?:saca|saque|obtiene|obtenga)\s+"
                   r"(?:un\s+)?(5|cinco|4[.,]5|4[.,]8)\b")
_ABS = re.compile(r"\b(?:si|cuando|cada vez que)\s+(?:alguien|algun estudiante|un estudiante)\s+(?:falta|falte)\s+"
                  r"(\d|dos|tres|cuatro|cinco)\s+(?:veces|dias|clases)(?:\s+(seguid[oa]s|en total|en el periodo))?")


def parse(t):
    """→ regla {"evento", "umbral", "acciones", "filtro"} o None si la frase no es una regla."""
    acts = []
    if re.search(r"\brefuerzo|taller de refuerzo|actividad de refuerzo|nivelacion\b", t):
        acts.append("refuerzo")
    if re.search(r"\bacudiente|padres|familia|mama|papa\b", t):
        acts.append("acudiente")
    if re.search(r"\bfelicit\w*|reconoc\w*|felicidades\b", t):
        acts.append("felicitar")
    if re.search(r"\bavis\w*|dime|recuerd\w*|notifica\w*|alerta\w*\b", t) or not acts:
        acts.append("avisar")
    m = _LOW.search(t)
    if m:
        return {"evento": "nota_baja", "umbral": _n(m.group(1), 3.0), "filtro": (m.group(2) or "").replace("nota", ""), "acciones": acts}
    m = _HIGH.search(t)
    if m:
        return {"evento": "nota_alta", "umbral": _n(m.group(1), 5.0), "filtro": "", "acciones": [a for a in acts if a != "refuerzo"] or ["avisar"]}
    m = _ABS.search(t)
    if m:
        return {"evento": "fallas", "umbral": _n(m.group(1), 3.0), "filtro": "total" if (m.group(2) or "").startswith(("en t", "en e")) else "seguidas",
                "acciones": [a for a in acts if a != "refuerzo"] or ["avisar"]}
    return None


def describe(r):
    ev = {"nota_baja": f"si alguien saca menos de {r['umbral']:g}" + (f" en un {r['filtro']}" if r.get("filtro") else ""),
          "nota_alta": f"si alguien saca {r['umbral']:g} o más",
          "fallas": f"si alguien falta {r['umbral']:g} veces " + ("seguidas" if r.get("filtro") == "seguidas" else "en el periodo")}[r["evento"]]
    ac = {"avisar": "te aviso", "refuerzo": "le preparo un refuerzo", "acudiente": "te recuerdo escribirle al acudiente (con el mensaje listo)",
          "felicitar": "te recuerdo felicitarlo"}
    return ev + ": " + ", ".join(ac[a] for a in r["acciones"])


def grade_matches(r, nota, actividad=""):
    if r["evento"] == "nota_baja":
        if r.get("filtro") and r["filtro"] not in actividad.lower():
            return False
        return nota < r["umbral"]
    if r["evento"] == "nota_alta":
        return nota >= r["umbral"]
    return False


def streak(days_with_absence, class_days):
    """Faltas seguidas al final: class_days son los días con clase (ordenados); days_with_absence, los que faltó."""
    n = 0
    for d in reversed(class_days):
        if d in days_with_absence:
            n += 1
        else:
            break
    return n
