"""Fórmulas en las respuestas (11.8). En el chat se dibujan con KaTeX a partir de $…$; aquí se pasan a palabras para
la voz («x al cuadrado más 3 x») y a texto plano para Word o el celular («x² + 3x»). Lógica pura.
"""
import re

_SEG = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)|(?<![\\\w$])\$(?!\s)([^$\n]{1,400}?)(?<!\s)\$(?![\w$])", re.S)
_SUP = str.maketrans("0123456789+-()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾ⁿ")
_GREEK = {"alpha": "alfa", "beta": "beta", "gamma": "gamma", "delta": "delta", "theta": "teta", "pi": "pi", "lambda": "lambda", "mu": "mu",
          "sigma": "sigma", "omega": "omega", "phi": "fi", "epsilon": "épsilon", "Delta": "delta", "Sigma": "sumatoria", "infty": "infinito"}
_GREEK_SYM = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "theta": "θ", "pi": "π", "lambda": "λ", "mu": "μ", "sigma": "σ", "omega": "ω",
              "phi": "φ", "epsilon": "ε", "Delta": "Δ", "Sigma": "Σ", "infty": "∞"}
_OPS_SPEECH = [(r"\\cdot|\\times", " por "), (r"\\div", " dividido entre "), (r"\\pm", " más o menos "), (r"\\leq?|≤", " menor o igual que "),
               (r"\\geq?|≥", " mayor o igual que "), (r"\\neq|≠", " diferente de "), (r"\\approx|≈", " aproximadamente "), (r"\\to|\\rightarrow", " tiende a "),
               (r"\\sin", " seno de "), (r"\\cos", " coseno de "), (r"\\tan", " tangente de "), (r"\\log", " logaritmo de "), (r"\\ln", " logaritmo natural de "),
               (r"\\lim", " límite "), (r"\\sum", " sumatoria "), (r"\\int", " integral de "), (r"\\%", " por ciento"), (r"\\degree|\^\\circ|°", " grados")]
_OPS_PLAIN = [(r"\\cdot", "·"), (r"\\times", "×"), (r"\\div", "÷"), (r"\\pm", "±"), (r"\\leq?", "≤"), (r"\\geq?", "≥"), (r"\\neq", "≠"), (r"\\approx", "≈"),
              (r"\\to|\\rightarrow", "→"), (r"\\(sin|cos|tan|log|ln|lim)\b", r"\1"), (r"\\sum", "Σ"), (r"\\int", "∫"), (r"\\%", "%"), (r"\^\\circ|\\degree", "°")]


def segments(text):
    """[(es_formula, texto)] separando las fórmulas $…$, $$…$$, \\(…\\) y \\[…\\]."""
    out, last = [], 0
    for m in _SEG.finditer(str(text or "")):
        if m.start() > last:
            out.append((False, text[last:m.start()]))
        out.append((True, next(g for g in m.groups() if g is not None)))
        last = m.end()
    if last < len(str(text or "")):
        out.append((False, text[last:]))
    return out


def _braced(s, i):
    """El contenido entre llaves que empieza en s[i] == '{'. → (contenido, índice después)."""
    if i >= len(s) or s[i] != "{":
        return (s[i] if i < len(s) else ""), i + 1
    depth, j = 0, i
    while j < len(s):
        depth += {"{": 1, "}": -1}.get(s[j], 0)
        if depth == 0:
            return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


def _expand(s, frac, sqrt, root):
    out, i = [], 0
    while i < len(s):
        if s.startswith(("\\frac", "\\dfrac", "\\tfrac"), i):
            i = s.index("frac", i) + 4
            a, i = _braced(s, i)
            b, i = _braced(s, i)
            out.append(frac(_expand(a, frac, sqrt, root), _expand(b, frac, sqrt, root)))
        elif s.startswith("\\sqrt", i):
            i += 5
            n = ""
            if i < len(s) and s[i] == "[":
                k = s.index("]", i)
                n, i = s[i + 1:k], k + 1
            a, i = _braced(s, i)
            a = _expand(a, frac, sqrt, root)
            out.append(root(n, a) if n else sqrt(a))
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _simple(x):
    return bool(re.fullmatch(r"\s*[\w.,]+\s*", x))


def to_speech(f):
    """Una fórmula LaTeX dicha en palabras."""
    s = _expand(f, lambda a, b: f" {a} sobre {b} " if _simple(a) and _simple(b) else f" la fracción {a}, sobre {b}, ",
                lambda a: f" raíz de {a} ", lambda n, a: f" raíz {'cúbica' if n.strip() == '3' else 'de índice ' + n} de {a} ")
    for k, v in _GREEK.items():
        s = re.sub(rf"\\{k}\b", f" {v} ", s)
    for rx, v in _OPS_SPEECH:
        s = re.sub(rx, v, s)
    s = re.sub(r"\^\{?2\}?", " al cuadrado ", s)
    s = re.sub(r"\^\{?3\}?", " al cubo ", s)
    s = re.sub(r"\^\{([^{}]+)\}|\^(\S)", lambda m: f" a la {m.group(1) or m.group(2)} ", s)
    s = re.sub(r"_\{([^{}]+)\}|_(\w)", lambda m: f" sub {m.group(1) or m.group(2)} ", s)
    s = s.replace("=", " igual a ").replace("+", " más ").replace("<", " menor que ").replace(">", " mayor que ")
    s = re.sub(r"(?<=[\w)\s])-(?=[\w(\s])", " menos ", s).replace("-", " menos ")
    s = re.sub(r"\\left|\\right|\\[,;:!]|\\quad|\\text|\\mathrm|\\displaystyle|[{}\\]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def to_plain(f):
    """Una fórmula LaTeX en texto plano legible (x² + 3x, √9, 3/4)."""
    s = _expand(f, lambda a, b: f"{a}/{b}" if _simple(a) and _simple(b) else f"({a})/({b})",
                lambda a: f"√{a}" if _simple(a) else f"√({a})", lambda n, a: f"{'∛' if n.strip() == '3' else n + '√'}({a})")
    for k, v in _GREEK_SYM.items():
        s = re.sub(rf"\\{k}\b", v, s)
    for rx, v in _OPS_PLAIN:
        s = re.sub(rx, v, s)
    s = re.sub(r"\^\{([0-9+\-n()]+)\}|\^([0-9n])", lambda m: (m.group(1) or m.group(2)).translate(_SUP), s)
    s = re.sub(r"\^\{([^{}]+)\}", r"^(\1)", s)
    s = re.sub(r"\\left|\\right|\\[,;:!]|\\quad|\\displaystyle|\\text|\\mathrm", " ", s)
    s = s.replace("{", "").replace("}", "").replace("\\", "")
    return re.sub(r"[ \t]+", " ", s).strip()


def speech(text):
    """El texto con sus fórmulas dichas en palabras."""
    return "".join(to_speech(t) if f else t for f, t in segments(text))


def plain(text):
    """El texto con sus fórmulas en texto plano."""
    return "".join(to_plain(t) if f else t for f, t in segments(text))


def has_math(text):
    return any(f for f, _ in segments(text))


def graphable(text):
    """La primera función que se puede graficar en la respuesta («y = 2x + 1», «f(x) = x^2 − 4»), o ""."""
    for f, t in segments(text):
        src = to_plain(t) if f else t
        m = re.search(r"\b(?:y|f\s*\(\s*x\s*\)|g\s*\(\s*x\s*\))\s*=\s*([0-9x+\-*/^().,²³√ ]*x[0-9x+\-*/^().,²³√ ]*)", src)
        if m and len(m.group(1).strip()) >= 2:
            return "y = " + m.group(1).strip().rstrip(".,")
    return ""
