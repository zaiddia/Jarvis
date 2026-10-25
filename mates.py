"""
Matemáticas offline para Jarvis (con SymPy).

resolver(texto) -> cadena para leer en voz alta, o None si no parece algo matemático.
Entiende tanto texto ya simbólico ("2x+3=7") como dictado ("dos equis mas tres igual siete").
No usa la IA: los resultados son exactos y al instante.
"""

import re
import unicodedata

try:
    import sympy
    from sympy import symbols, Eq, solve, diff, integrate, factor, simplify, expand, sqrt, nsimplify, N
    from sympy.parsing.sympy_parser import (parse_expr, standard_transformations,
                                            implicit_multiplication_application, convert_xor)
    _TRANSFORM = standard_transformations + (implicit_multiplication_application, convert_xor)
    SYMPY_OK = True
except Exception:
    SYMPY_OK = False


# Palabras habladas -> símbolo (se aplican como texto completo, respetando límites de palabra)
WORDS = [
    (r"\bpor ciento\b", "%"), (r"\bal cuadrado\b", "^2"), (r"\bal cubo\b", "^3"),
    (r"\belevado a la\b", "^"), (r"\belevado a\b", "^"), (r"\braiz cuadrada de\b", "sqrt"),
    (r"\braiz de\b", "sqrt"), (r"\bmas\b", "+"), (r"\bmenos\b", "-"),
    (r"\bmultiplicado por\b", "*"), (r"\bpor\b", "*"), (r"\bdividido entre\b", "/"),
    (r"\bdividido por\b", "/"), (r"\bentre\b", "/"), (r"\bsobre\b", "/"),
    (r"\bigual a\b", "="), (r"\bigual\b", "="), (r"\bmayor que\b", ">"), (r"\bmenor que\b", "<"),
    (r"\babre parentesis\b", "("), (r"\bcierra parentesis\b", ")"),
    (r"\bequis\b", "x"), (r"\bye\b", "y"), (r"\bzeta\b", "z"), (r"\bpi\b", "pi"),
    (r"\bcoma\b", "."), (r"\bpunto\b", "."),
]
NUM_WORDS = {
    "cero": "0", "uno": "1", "una": "1", "un": "1", "dos": "2", "tres": "3", "cuatro": "4",
    "cinco": "5", "seis": "6", "siete": "7", "ocho": "8", "nueve": "9", "diez": "10",
    "once": "11", "doce": "12", "trece": "13", "catorce": "14", "quince": "15",
    "veinte": "20", "treinta": "30", "cuarenta": "40", "cincuenta": "50", "cien": "100",
    "mil": "1000", "medio": "0.5",
}

CMD_RE = r"(?:calcula(?:r)?|cuanto es|cuanto da|cuanto vale|resuelve|resolver|ecuacion|" \
         r"deriva(?:da)?|integra(?:l)?|factoriza(?:r)?|simplifica(?:r)?|desarrolla(?:r)?|" \
         r"expande(?:r)?|evalua(?:r)?|resultado de|a cuanto equivale)"
TRIGGER_RE = re.compile(rf"\b{CMD_RE}\b")


def _strip_accents(t):
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def looks_math(text):
    t = _strip_accents(text)
    if TRIGGER_RE.search(t):
        return True
    # «15% de 240», «2x+3=7», «3 por 4»
    if re.search(r"\d\s*(?:%|por ciento)\s+de\b", t):
        return True
    return False


def _to_symbolic(t):
    """Convierte el texto (español o simbólico) en una cadena que SymPy entiende."""
    t = _strip_accents(t)
    t = TRIGGER_RE.sub(" ", t)                       # quita el verbo (calcula, resuelve…)
    # 1) operadores y funciones habladas (incluye «raiz de», «elevado a», «por ciento»)
    for pat, rep in WORDS:
        t = re.sub(pat, rep, t)
    # 2) números en palabras -> dígitos
    t = re.sub(r"\b[a-z]+\b", lambda m: NUM_WORDS.get(m.group(0), m.group(0)), t)
    # 3) quita artículos sobrantes (no «a»/«de», que ya se consumieron arriba)
    t = re.sub(r"\b(?:el|la|los|las|del)\b", " ", t)
    t = t.replace("×", "*").replace("÷", "/").replace("−", "-").replace(",", ".")
    t = re.sub(r"\s+", " ", t).strip(" .")
    return t


def _fmt(expr):
    """Formatea un resultado de SymPy para leerlo: exacto y, si aplica, decimal."""
    try:
        val = nsimplify(expr) if expr.free_symbols == set() else expr
    except Exception:
        val = expr
    s = str(val).replace("**", "^").replace("*", " por ").replace("sqrt", "raíz de ")
    try:
        if expr.free_symbols == set():
            num = float(N(expr))
            if abs(num - round(num)) < 1e-9:
                return str(int(round(num)))
            dec = round(num, 4)
            if str(val) not in (str(dec), str(int(num)) if num == int(num) else None):
                return f"{s} (aproximadamente {dec})"
            return str(dec)
    except Exception:
        pass
    return s


def _percent(t):
    """Maneja «15% de 240» / «15 por ciento de 240»."""
    m = re.search(r"([\d.]+)\s*(?:%|por ciento)\s+de\s+([\d.]+)", _strip_accents(t))
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        r = a / 100 * b
        r = int(r) if r == int(r) else round(r, 4)
        return f"El {m.group(1)} por ciento de {m.group(2)} es {r}."
    return None


def resolver(text):
    if not SYMPY_OK:
        return "Para hacer cálculos necesito la librería SymPy instalada."
    t = _strip_accents(text)

    pr = _percent(t)
    if pr:
        return pr

    kind = "eval"
    if re.search(r"\bderiva", t):
        kind = "deriv"
    elif re.search(r"\bintegra", t):
        kind = "integ"
    elif re.search(r"\bfactoriza", t):
        kind = "factor"
    elif re.search(r"\b(?:simplifica)", t):
        kind = "simpl"
    elif re.search(r"\b(?:desarrolla|expande)", t):
        kind = "expand"
    elif re.search(r"\b(?:resuelve|resolver|ecuacion)\b", t) or "=" in _to_symbolic(t):
        kind = "solve"

    expr_str = _to_symbolic(t)
    if not expr_str or not re.search(r"[\d x-z]", expr_str):
        return "No entendí la operación. Prueba, por ejemplo: cuánto es 15 por 4."

    x, y, z = symbols("x y z")
    local = {"x": x, "y": y, "z": z, "sqrt": sqrt, "pi": sympy.pi, "e": sympy.E}
    try:
        if kind == "solve":
            if "=" in expr_str:
                izq, der = expr_str.split("=", 1)
                eq = Eq(parse_expr(izq, local, _TRANSFORM), parse_expr(der, local, _TRANSFORM))
            else:
                eq = Eq(parse_expr(expr_str, local, _TRANSFORM), 0)
            inc = sorted(eq.free_symbols, key=lambda s: s.name) or [x]
            sols = solve(eq, inc[0])
            if not sols:
                return "Esa ecuación no tiene solución real."
            nombre = inc[0].name
            partes = ", ".join(_fmt(s) for s in sols)
            if len(sols) == 1:
                return f"{nombre} igual a {partes}."
            return f"{nombre} puede ser {partes}."

        expr = parse_expr(expr_str, local, _TRANSFORM)
        if kind == "deriv":
            return f"La derivada es {_fmt(diff(expr, x))}."
        if kind == "integ":
            return f"La integral es {_fmt(integrate(expr, x))} más una constante."
        if kind == "factor":
            return f"Factorizado queda {_fmt(factor(expr))}."
        if kind == "simpl":
            return f"Simplificado es {_fmt(simplify(expr))}."
        if kind == "expand":
            return f"Desarrollado es {_fmt(expand(expr))}."
        res = _fmt(simplify(expr))
        return f"El resultado es {res}."
    except Exception:
        return "No pude resolver esa operación. Revisa cómo la dijiste."
