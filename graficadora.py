"""12.69: graficadora libre para el video beam. Lógica pura.

«Grafica y = a x² + b x + c» → la función en el plano y cada letra (a, b, c…) es un deslizador. Las expresiones se leen con
una lista CERRADA de símbolos (x, números, letras de parámetros, + − × ÷ ^, paréntesis, sin, cos, tan, sqrt, abs, log, ln,
exp, pi, e): nunca se ejecuta texto como código, ni aquí ni en la página.
"""
import re
import unicodedata

FUNCS = ("sqrt", "sin", "cos", "tan", "abs", "log", "ln", "exp")
PARAMS = "abcdhkmnpqrst"
MAX_FUNCS = 3
_TOKEN = re.compile(r"\s*(\d+(?:\.\d+)?|sqrt|sin|cos|tan|abs|log|ln|exp|pi|[a-z]|[-+*/^()])")


def _plain(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")


_WORDS = [(r"\bal cuadrado\b", "^2"), (r"\bal cubo\b", "^3"), (r"\belevad[oa] a la\b|\belevad[oa] a\b|\belevad[oa]\b", "^"),
          (r"\braiz cuadrada de\b|\braiz de\b|\braiz\b", "sqrt "), (r"\bvalor absoluto de\b", "abs "), (r"\bseno de\b|\bseno\b|\bsen\b", "sin "),
          (r"\bcoseno de\b|\bcoseno\b", "cos "), (r"\btangente de\b|\btangente\b", "tan "), (r"\blogaritmo natural de\b", "ln "),
          (r"\blogaritmo de\b", "log "), (r"\bmas\b", "+"), (r"\bmenos\b", "-"),
          (r"\bdividido (?:entre|por)\b|\bentre\b|\bsobre\b", "/"), (r"\bpor\b|\bveces\b", "*"), (r"\babre parentesis\b", "("), (r"\bcierra parentesis\b", ")"),
          (r"\bpi\b", "pi"), (r"\bcero\b", "0"), (r"\buno\b", "1"), (r"\bdos\b", "2"), (r"\btres\b", "3"), (r"\bcuatro\b", "4"),
          (r"\bcinco\b", "5"), (r"\bseis\b", "6"), (r"\bsiete\b", "7"), (r"\bocho\b", "8"), (r"\bnueve\b", "9"), (r"\bdiez\b", "10"),
          (r"\bmedio\b", "0.5")]


def from_speech(text):
    """«y igual a x al cuadrado más 2x menos 3» / «f(x) = 2x³−x» → «x^2+2x-3» (sin validar aún)."""
    t = str(text or "").replace("²", "^2").replace("³", "^3").replace("·", "*").replace("×", "*").replace("÷", "/").replace("−", "-")
    t = _plain(t)
    t = re.sub(r"^\s*(?:y|f\s*\(?\s*x\s*\)?|f de x)\s*(?:=|igual a|es igual a|es)\s*", "", t)
    for rx, rep in _WORDS:
        t = re.sub(rx, f" {rep} ", t)
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)
    return re.sub(r"\s+", " ", t).strip()


def tokens(expr):
    pos, out = 0, []
    s = str(expr or "").strip()
    while pos < len(s):
        m = _TOKEN.match(s, pos)
        if not m:
            raise ValueError(f"no entiendo «{s[pos:pos + 8].strip()}»")
        out.append(m.group(1))
        pos = m.end()
        while pos < len(s) and s[pos] == " ":
            pos += 1
    return out


def _atom_end(tk):
    return tk not in ("+", "-", "*", "/", "^", "(") and tk not in FUNCS


def _atom_start(tk):
    return tk not in ("+", "-", "*", "/", "^", ")")


def canonical(expr):
    """Valida y escribe la expresión con todos los «*» explícitos. → (expresión, [parámetros]). Lanza ValueError."""
    raw = tokens(expr)
    if not raw:
        raise ValueError("falta la función")
    fixed = []
    for i, tk in enumerate(raw):                                 # «raíz de x» → sqrt(x): un solo símbolo se envuelve
        fixed.append(tk)
        if fixed[-2:-1] and fixed[-2] in FUNCS and tk != "(" and (tk.replace(".", "").isdigit() or tk.isalpha()) and tk not in FUNCS:
            fixed[-1:] = ["(", tk, ")"]
    raw = fixed
    if len(raw) > 160:
        raise ValueError("la función es demasiado larga")
    out, params = [], []
    for i, tk in enumerate(raw):
        if tk.isalpha() and len(tk) == 1 and tk not in "xe":
            if tk not in PARAMS:
                raise ValueError(f"la letra «{tk}» no puede ser parámetro (usa a, b, c, d, h, k, m, n, p, q, r, s o t)")
            if tk not in params:
                params.append(tk)
        if out and _atom_end(out[-1]) and _atom_start(tk):
            out.append("*")                                      # 2x → 2*x · a(x+1) → a*(x+1) · )( → )*(
        out.append(tk)
        if tk in FUNCS and (i + 1 >= len(raw) or raw[i + 1] != "("):
            raise ValueError(f"después de {tk} van paréntesis, por ejemplo {tk}(x)")
    depth = 0
    for tk in out:
        depth += tk == "("
        depth -= tk == ")"
        if depth < 0:
            raise ValueError("sobra un paréntesis")
    if depth:
        raise ValueError("falta cerrar un paréntesis")
    if out[-1] in ("+", "-", "*", "/", "^") or out[0] in ("*", "/", "^"):
        raise ValueError("la función está incompleta")
    for a, b in zip(out, out[1:]):
        if a in ("+", "-", "*", "/", "^") and b in ("*", "/", "^", ")"):
            raise ValueError("hay dos operaciones seguidas")
    if "x" not in out and not params:
        pass                                                     # una constante también se puede graficar (recta horizontal)
    return "".join(out), params


def evaluate(expr, x, env=None):
    """Para las pruebas: evalúa la forma canónica con un analizador propio (sin eval)."""
    import math
    tk = tokens(expr)
    pos = [0]
    env = env or {}

    def peek():
        return tk[pos[0]] if pos[0] < len(tk) else None

    def take():
        pos[0] += 1
        return tk[pos[0] - 1]

    def e():
        v = t()
        while peek() in ("+", "-"):
            v = v + t() if take() == "+" else v - t()
        return v

    def t():
        v = u()
        while peek() in ("*", "/"):
            v = v * u() if take() == "*" else v / u()
        return v

    def u():
        if peek() == "-":
            take()
            return -u()
        if peek() == "+":
            take()
            return u()
        return p()

    def p():
        b = a()
        if peek() == "^":
            take()
            return b ** u()
        return b

    def a():
        k = take()
        if k == "(":
            v = e()
            take()
            return v
        if k in FUNCS:
            take()
            v = e()
            take()
            return {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "abs": abs, "log": math.log10,
                    "ln": math.log, "exp": math.exp}[k](v)
        if k == "x":
            return x
        if k == "pi":
            return math.pi
        if k == "e":
            return math.e
        if k.isalpha():
            return env.get(k, 1.0)
        return float(k)
    return e()


def parse_request(text):
    """Lo que viene después de «grafica»: varias funciones separadas por «;» o « y también ». → [(expresión, parámetros)]"""
    parts = [p for p in re.split(r";|\by tambien\b|\by la funcion\b", _plain(text)) if p.strip()][:MAX_FUNCS]
    out = []
    for p in parts:
        out.append(canonical(from_speech(p)))
    return out


def values_in(text):
    """«con a = 2 y b = -1» → {"a": 2.0, "b": -1.0}"""
    return {m.group(1): float(m.group(2).replace(",", ".")) for m in
            re.finditer(r"\b([abcdhkmnpqrst])\s*(?:=|igual a|vale)\s*(-?\d+(?:[.,]\d+)?)", _plain(text))}


__all__ = ["FUNCS", "PARAMS", "MAX_FUNCS", "from_speech", "tokens", "canonical", "evaluate", "parse_request", "values_in"]
