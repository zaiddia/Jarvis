"""Solucionario paso a paso verificado (11.3). Lógica pura, sin Jarvis.

La IA escribe la solución paso a paso de cada problema y, junto a ella, una «verificación» que una máquina puede
comprobar (la ecuación y su solución, la expresión y su valor, la derivada…). SymPy la comprueba: si la IA se
equivocó, se corrige el resultado antes de que llegue al estudiante. Las expresiones se leen con una lista cerrada de
símbolos (nunca se ejecuta texto libre).
"""
import datetime
import os
import re

TYPES = ("ecuacion", "expresion", "simplificar", "derivada", "integral", "sistema", "ninguna")
_ALLOWED = {"x", "y", "z", "a", "b", "c", "n", "t", "m", "k", "sqrt", "sin", "cos", "tan", "log", "ln", "exp", "pi", "e", "abs", "sen"}
_TOK = re.compile(r"[a-z]+|\d+(?:[.,]\d+)?|\*\*|[-+*/^(),=<>\s]")       # sin «.» suelto: nada de atributos


def _safe(s):
    s = str(s or "").lower().replace("·", "*").replace("−", "-").replace("²", "^2").replace("³", "^3").replace("√", "sqrt").strip()
    s = s.replace("sen(", "sin(").replace("ln(", "log(")
    if not s or len(s) > 160:
        raise ValueError("vacía o muy larga")
    pos = 0
    while pos < len(s):
        m = _TOK.match(s, pos)
        if not m:
            raise ValueError(f"símbolo no permitido: «{s[pos]}»")
        tok = m.group(0)
        if tok.isalpha() and tok not in _ALLOWED:
            raise ValueError(f"«{tok}» no está permitido")
        pos = m.end()
    return re.sub(r"(\d),(\d)", r"\1.\2", s)


def _parse(s):
    from sympy.parsing.sympy_parser import convert_xor, implicit_multiplication_application, parse_expr, standard_transformations
    tr = standard_transformations + (implicit_multiplication_application, convert_xor)
    return parse_expr(_safe(s), transformations=tr, evaluate=True)


def _pretty(s):
    """3*x**2 + 2 → 3x² + 2 (para leerlo en el solucionario)."""
    s = str(s).replace("**2", "²").replace("**3", "³").replace("**", "^")
    return re.sub(r"(\d)\*([a-z(])", r"\1\2", s).replace("sqrt", "√")


def _values(res, var):
    """«x = 2, x = -3», «x=2 o x=-3», «2 y -3», «{2, -3}» → {valores sympy}."""
    if re.search(r"\b(?:no tiene|ninguna|sin solucion|sin solución|no hay)\b", str(res).lower()):
        return set()
    t = re.sub(r"\b[a-z]\s*=\s*", "", str(res).lower().replace(" o ", ",").replace(" y ", ",").replace("{", "").replace("}", "").replace(";", ","))
    out = set()
    for part in t.split(","):
        part = part.strip()
        if part:
            out.add(_parse(part))
    return out


def _eq(a, b):
    import sympy
    d = sympy.simplify(a - b)
    if d == 0:
        return True
    try:
        return abs(complex(sympy.N(d))) < 1e-9
    except (TypeError, ValueError):
        return False


def check(v):
    """→ {"ok": True|False|None, "correcto": texto (si se pudo calcular), "nota": str}. None = no se pudo verificar."""
    import sympy
    if not isinstance(v, dict):
        return {"ok": None, "correcto": "", "nota": "sin verificación"}
    tipo = str(v.get("tipo", "")).lower().strip()
    expr, res = str(v.get("expr", "")), str(v.get("resultado", ""))
    if tipo not in TYPES or tipo == "ninguna" or not expr:
        return {"ok": None, "correcto": "", "nota": "sin verificación automática"}
    try:
        x = sympy.Symbol(str(v.get("variable") or "x"))
        if tipo == "ecuacion":
            if "=" not in expr:
                raise ValueError("la ecuación no tiene «=»")
            lhs, rhs = expr.split("=", 1)
            sols = set(sympy.solve(sympy.Eq(_parse(lhs), _parse(rhs)), x))
            real = {s for s in sols if s.is_real is not False}
            got = _values(res, x)
            ok = len(got) == len(real) and all(any(_eq(g, s) for s in real) for g in got)
            correct = ", ".join(f"{x} = {_pretty(sympy.nsimplify(s))}" for s in sorted(real, key=lambda s: complex(sympy.N(s)).real)) or "no tiene solución real"
            return {"ok": ok, "correcto": correct, "nota": "ecuación resuelta con SymPy"}
        if tipo == "sistema":
            eqs = [e for e in re.split(r"[;\n]", expr) if "=" in e]
            syms = sorted({str(s) for e in eqs for s in _parse(e.split("=")[0] + "-(" + e.split("=")[1] + ")").free_symbols})
            S = [sympy.Symbol(s) for s in syms]
            sol = sympy.solve([sympy.Eq(_parse(e.split("=")[0]), _parse(e.split("=")[1])) for e in eqs], S, dict=True)
            if not sol:
                return {"ok": None, "correcto": "", "nota": "el sistema no tiene solución única"}
            want = sol[0]
            got = {}
            for m in re.finditer(r"\b([a-z])\s*=\s*([-+\d./ ]+)", res.lower()):
                got[m.group(1)] = _parse(m.group(2))
            ok = all(str(k) in got and _eq(got[str(k)], val) for k, val in want.items())
            return {"ok": ok, "correcto": ", ".join(f"{k} = {_pretty(sympy.nsimplify(val))}" for k, val in want.items()), "nota": "sistema resuelto con SymPy"}
        e = _parse(expr)
        if tipo == "expresion":
            val = sympy.nsimplify(sympy.simplify(e))
            r = _parse(res.split("=")[-1])
            return {"ok": _eq(r, val), "correcto": _pretty(val), "nota": "operación calculada con SymPy"}
        if tipo == "simplificar":
            r = _parse(res.split("=")[-1])
            return {"ok": _eq(e, r), "correcto": _pretty(sympy.factor(sympy.simplify(e))), "nota": "expresiones comparadas con SymPy"}
        if tipo == "derivada":
            d = sympy.diff(e, x)
            r = _parse(res.split("=")[-1])
            return {"ok": _eq(d, r), "correcto": _pretty(sympy.simplify(d)), "nota": "derivada calculada con SymPy"}
        if tipo == "integral":
            r = _parse(res.split("=")[-1].replace("+ c", "").replace("+c", ""))
            return {"ok": _eq(sympy.diff(r, x), e), "correcto": _pretty(sympy.integrate(e, x)) + " + C", "nota": "integral comprobada derivando con SymPy"}
    except Exception as ex:                             # algo que no se deja leer: no se marca como error de la IA
        return {"ok": None, "correcto": "", "nota": f"no se pudo verificar ({str(ex)[:60]})"}
    return {"ok": None, "correcto": "", "nota": "sin verificación"}


def prompt(problemas, grado="", asignatura="Matemáticas"):
    lista = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(problemas))
    return (f"Eres docente de {asignatura}{(' de grado ' + grado) if grado else ''} en Colombia. Resuelve paso a paso cada problema, como "
            "para el solucionario del docente: pasos cortos y numerados, cada uno con la operación y el porqué; texto plano sin LaTeX "
            "(usa x², √9, 3/4). Para cada problema agrega «verificacion», una forma que una máquina pueda comprobar: "
            '{"tipo": "ecuacion", "expr": "2*x + 3 = 7", "resultado": "x = 2"} | {"tipo": "expresion", "expr": "3/4 + 1/2", "resultado": "5/4"} | '
            '{"tipo": "simplificar", "expr": "(x^2 - 1)/(x - 1)", "resultado": "x + 1"} | {"tipo": "derivada", "expr": "x^3", "resultado": "3*x^2"} | '
            '{"tipo": "integral", "expr": "2*x", "resultado": "x^2"} | {"tipo": "sistema", "expr": "x + y = 5; x - y = 1", "resultado": "x = 3, y = 2"} | '
            '{"tipo": "ninguna"} (si no es algebraico: un razonamiento, una tabla, una gráfica). Usa solo x, y, números, + - * / ^, paréntesis, '
            "sqrt, sin, cos, tan, log, pi.\nProblemas:\n" + lista +
            '\nResponde SOLO con JSON: {"soluciones": [{"problema": str, "pasos": [str], "respuesta": str, "verificacion": {…}}]}')


def fix_prompt(problema, pasos, correcto):
    return ("En este solucionario hay un error: el resultado correcto (comprobado con un sistema de álgebra) es «" + correcto + "». "
            f"Problema: «{problema}». Pasos que se escribieron: {' | '.join(pasos)}. Reescribe los pasos correctos, cortos y numerados, "
            'que lleguen a ese resultado. Responde SOLO con JSON: {"pasos": [str], "respuesta": str}')


def clean(d, n=None):
    out = []
    for s in (d.get("soluciones") or [])[: n or 40] if isinstance(d, dict) else []:
        if isinstance(s, dict) and s.get("pasos"):
            out.append({"problema": str(s.get("problema", ""))[:600], "pasos": [str(p)[:500] for p in s["pasos"]][:15],
                        "respuesta": str(s.get("respuesta", ""))[:300], "verificacion": s.get("verificacion") if isinstance(s.get("verificacion"), dict) else {}})
    return out


def split_problems(text):
    """«2x+3=7; x^2-5x+6=0» o una lista numerada → [problemas]."""
    parts = re.split(r"\s*(?:;|\n|\b\d{1,2}[.)]\s+)\s*", str(text or ""))
    return [p.strip(" .") for p in parts if len(p.strip(" .")) >= 3][:30]


def docx(titulo, sols, out_dir, Document, curso="", docente=""):
    from docx.shared import Pt, RGBColor
    doc = Document()
    doc.add_heading(f"Solucionario · {titulo}", 0)
    if curso or docente:
        doc.add_paragraph(" · ".join(x for x in (curso, docente) if x))
    ok = sum(1 for s in sols if s.get("check", {}).get("ok"))
    fixed = sum(1 for s in sols if s.get("corregido"))
    doc.add_paragraph(f"{len(sols)} problemas · {ok} verificados con SymPy" + (f" · {fixed} corregidos por la verificación" if fixed else ""))
    for i, s in enumerate(sols, 1):
        p = doc.add_paragraph()
        r = p.add_run(f"{i}. {s['problema']}")
        r.bold = True
        for j, step in enumerate(s["pasos"], 1):
            sp = doc.add_paragraph(f"{j}) " + re.sub(r"^\s*(?:paso\s*)?\d+[.):]\s*", "", step, flags=re.I))
            sp.paragraph_format.left_indent = Pt(14)
        rp = doc.add_paragraph()
        rr = rp.add_run(f"Respuesta: {s['respuesta']}")
        rr.bold = True
        c = s.get("check", {})
        tag = doc.add_paragraph()
        t = tag.add_run(("✔ Verificado con SymPy" if c.get("ok") else ("⚠ Corregido por la verificación (la IA se había equivocado)" if s.get("corregido")
                         else "· " + (c.get("nota") or "sin verificación automática"))))
        t.font.size = Pt(9)
        t.font.color.rgb = RGBColor(0x1E, 0x8E, 0x3E) if c.get("ok") else (RGBColor(0xC0, 0x6A, 0x00) if s.get("corregido") else RGBColor(0x80, 0x80, 0x80))
    folder = os.path.join(out_dir, "Solucionarios")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', " ", titulo).strip()[:80] or "Solucionario"
    path = os.path.join(folder, f"Solucionario {safe} {datetime.date.today():%Y-%m-%d}.docx")
    doc.save(path)
    return path
