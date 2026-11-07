"""Respuestas interactivas (12.1): en vez de un párrafo, una mini aplicación en el HUD. Lógica pura, sin Jarvis.

La IA describe el panel con un vocabulario CERRADO: deslizadores, resultados que se recalculan con una fórmula,
una tabla que se ordena y botones que lanzan órdenes de Jarvis. Las fórmulas solo pueden usar números, los
deslizadores del panel, + − × ÷ ^ ( ) y min, max, round, abs, sqrt: se leen con un analizador propio (aquí y en el
HUD), nunca se ejecuta código.
"""
import math
import re

_FUNCS = {"min": min, "max": max, "round": lambda x, n=0: round(x, int(n)), "abs": abs, "sqrt": math.sqrt}
_TOK = re.compile(r"\s*(?:(\d+(?:[.,]\d+)?)|([a-zA-Z_]\w*)|(\*\*|[-+*/^(),]))")

WANT = re.compile(r"\b(?:que pasa(?:ria)? si|y si (?:sube|baja|cambia|saca|fuera|pongo|tuviera)|cuanto (?:necesit\w*|tendria que|deberia) sacar|"
                  r"simula(?:me)?|simulador|calculadora (?:de|para)|compara(?:me)? (?:los|las|a|el|la)|haz(?:me)? una tabla|"
                  r"cuanto (?:me|le|les) (?:da|queda|falta)|con que nota (?:pasa|aprueba)|que nota necesit\w*)\b")


def wants(text_norm):
    return bool(WANT.search(text_norm))


def prompt(question, ctx=""):
    return f"""El usuario (un docente) preguntó: «{question}».
Responde con un PANEL INTERACTIVO para el HUD, no con un párrafo. Responde SOLO un JSON:
{{"titulo": "corto",
 "resumen": "1 o 2 frases con la respuesta para decir en voz alta (con los valores iniciales)",
 "controles": [{{"id": "nota3", "etiqueta": "Nota del periodo 3", "min": 1, "max": 5, "paso": 0.1, "valor": 3}}],
 "resultados": [{{"etiqueta": "Definitiva", "formula": "nota1*0.3 + nota2*0.3 + nota3*0.4", "decimales": 1, "meta": 3.0}}],
 "constantes": [{{"id": "nota1", "valor": 3.2}}],
 "tabla": {{"columnas": ["…"], "filas": [["…"]]}},
 "botones": [{{"texto": "texto corto", "orden": "una orden para Jarvis en español"}}]}}
Reglas: las fórmulas solo usan números, los id de controles y constantes, + - * / ^ ( ) y min, max, round, abs, sqrt. \
Hasta 4 controles, 4 resultados, 3 botones; «tabla» y «botones» son opcionales; «meta» es opcional (pinta verde si el \
resultado la alcanza). Usa los datos reales del contexto si los hay.{(' Contexto: ' + ctx) if ctx else ''}"""


# ============================================================================ FÓRMULAS (analizador propio)
def tokens(expr):
    pos, out = 0, []
    s = str(expr or "")
    while pos < len(s):
        if s[pos].isspace():
            pos += 1
            continue
        m = _TOK.match(s, pos)
        if not m or m.end() == pos:
            raise ValueError(f"símbolo no permitido: «{s[pos]}»")
        num, name, op = m.groups()
        out.append(("n", float(num.replace(",", "."))) if num else ("v", name) if name else ("o", "^" if op == "**" else op))
        pos = m.end()
    return out


def evaluate(expr, env):
    """Evalúa la fórmula con las variables de env. Lanza ValueError si usa algo no permitido."""
    toks = tokens(expr)
    i = [0]

    def peek():
        return toks[i[0]] if i[0] < len(toks) else ("e", "")

    def take():
        t = peek()
        i[0] += 1
        return t

    def expr_():
        v = term()
        while peek() in (("o", "+"), ("o", "-")):
            op = take()[1]
            v = v + term() if op == "+" else v - term()
        return v

    def term():
        v = power()
        while peek() in (("o", "*"), ("o", "/")):
            op = take()[1]
            r = power()
            v = v * r if op == "*" else (v / r if r else float("inf"))
        return v

    def power():
        v = unary()
        if peek() == ("o", "^"):
            take()
            return v ** power()
        return v

    def unary():
        if peek() == ("o", "-"):
            take()
            return -unary()
        if peek() == ("o", "+"):
            take()
            return unary()
        return atom()

    def atom():
        k, v = take()
        if k == "n":
            return v
        if k == "v":
            if peek() == ("o", "("):
                if v not in _FUNCS:
                    raise ValueError(f"función no permitida: {v}")
                take()
                args = [expr_()]
                while peek() == ("o", ","):
                    take()
                    args.append(expr_())
                if take() != ("o", ")"):
                    raise ValueError("falta «)»")
                return float(_FUNCS[v](*args))
            if v not in env:
                raise ValueError(f"no conozco «{v}»")
            return float(env[v])
        if (k, v) == ("o", "("):
            r = expr_()
            if take() != ("o", ")"):
                raise ValueError("falta «)»")
            return r
        raise ValueError("fórmula incompleta")

    r = expr_()
    if i[0] != len(toks):
        raise ValueError("sobra algo en la fórmula")
    return r


# ============================================================================ VALIDAR
_ID = re.compile(r"^[a-zA-Z_]\w{0,24}$")


def _txt(v, n=120):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def _num(v, d):
    try:
        x = float(str(v).replace(",", "."))
        return x if math.isfinite(x) else d
    except (TypeError, ValueError):
        return d


def clean(d):
    """El panel de la IA, validado (lo que no sirve se quita). Lanza ValueError si no queda nada útil."""
    if not isinstance(d, dict):
        raise ValueError("el panel no es un JSON")
    env, ctrls, consts = {}, [], []
    for c in (d.get("constantes") or [])[:12]:
        if isinstance(c, dict) and _ID.match(str(c.get("id", ""))) and c["id"] not in _FUNCS:
            consts.append({"id": c["id"], "valor": _num(c.get("valor"), 0.0)})
            env[c["id"]] = consts[-1]["valor"]
    for c in (d.get("controles") or [])[:4]:
        if not isinstance(c, dict) or not _ID.match(str(c.get("id", ""))) or c["id"] in _FUNCS:
            continue
        lo, hi = _num(c.get("min"), 0), _num(c.get("max"), 10)
        if hi <= lo:
            continue
        paso = abs(_num(c.get("paso"), (hi - lo) / 100)) or (hi - lo) / 100
        val = min(hi, max(lo, _num(c.get("valor"), lo)))
        ctrls.append({"id": c["id"], "etiqueta": _txt(c.get("etiqueta"), 40) or c["id"], "min": lo, "max": hi, "paso": paso, "valor": val})
        env[c["id"]] = val
    res = []
    for r in (d.get("resultados") or [])[:4]:
        if not isinstance(r, dict):
            continue
        f = _txt(r.get("formula"), 200)
        try:
            v = evaluate(f, env)
        except (ValueError, OverflowError, ZeroDivisionError, TypeError):
            continue
        item = {"etiqueta": _txt(r.get("etiqueta"), 40) or "Resultado", "formula": f, "decimales": int(min(4, max(0, _num(r.get("decimales"), 1)))),
                "valor": v}
        if r.get("meta") is not None:
            item["meta"] = _num(r.get("meta"), 0)
        res.append(item)
    tabla = None
    t = d.get("tabla")
    if isinstance(t, dict) and t.get("columnas") and t.get("filas"):
        cols = [_txt(c, 30) for c in t["columnas"]][:6]
        rows = [[_txt(x, 40) for x in r][:len(cols)] for r in t["filas"][:30] if isinstance(r, list)]
        if cols and rows:
            tabla = {"columnas": cols, "filas": rows}
    botones = [{"texto": _txt(b.get("texto"), 30), "orden": _txt(b.get("orden"), 200)} for b in (d.get("botones") or [])[:3]
               if isinstance(b, dict) and _txt(b.get("texto")) and _txt(b.get("orden"))]
    if not (res or tabla):
        raise ValueError("el panel no trae resultados ni tabla")
    return {"titulo": _txt(d.get("titulo"), 60) or "Panel", "resumen": _txt(d.get("resumen"), 400), "controles": ctrls, "constantes": consts,
            "resultados": res, "tabla": tabla, "botones": botones}
