"""Gráficas y figuras para el material de clase (11.0): funciones, plano cartesiano, triángulos, círculos, rectángulos,
barras y tortas, dibujadas con Pillow (sin internet ni librerías extra) para meterlas en el Word.

La IA describe la figura con un pequeño JSON («grafica») y aquí se dibuja. Las expresiones de las funciones se leen
con una lista cerrada de símbolos (x, números, + - * / ^, paréntesis, sin, cos, tan, sqrt, log, exp, abs, pi).
"""
import math
import os
import re
import tempfile

TYPES = ("funcion", "plano", "triangulo", "circulo", "rectangulo", "barras", "torta")
W, H = 900, 620
_FUNCS = {"sin": math.sin, "cos": math.cos, "tan": math.tan, "sqrt": math.sqrt, "log": math.log10, "ln": math.log, "exp": math.exp,
          "abs": abs, "pi": math.pi, "e": math.e, "sen": math.sin}
PROMPT = (' Si una pregunta o ejercicio se entiende mejor con una figura (función, plano cartesiano, triángulo, círculo, rectángulo, '
          'diagrama de barras o de torta), agrega en ese elemento un campo «grafica» (máximo uno de cada tres elementos), con UNA de '
          'estas formas: {"tipo": "funcion", "expr": "x^2 - 4", "expr2": "", "xmin": -5, "xmax": 5} | {"tipo": "plano", "puntos": '
          '[[2, 3, "A"], [-1, 4, "B"]], "unir": true} | {"tipo": "triangulo", "vertices": ["A", "B", "C"], "lados": {"AB": "5 cm", '
          '"BC": "3 cm", "CA": "4 cm"}, "angulos": {"A": "37°"}, "recto": "C"} | {"tipo": "circulo", "radio": "4 cm"} | {"tipo": '
          '"rectangulo", "base": "8 cm", "altura": "3 cm"} | {"tipo": "barras" o "torta", "titulo": "…", "etiquetas": ["…"], '
          '"valores": [3, 5]}. Escribe las funciones con x, ^, *, sqrt, sin, cos, tan, log. No pongas en la figura la respuesta.')


# ----------------------------------------------------------------------------- expresiones seguras
_TOK = re.compile(r"\s*(?:(\d+(?:[.,]\d+)?)|([a-z]+)|(\*\*|[-+*/^(),]))")


def compile_expr(expr):
    """«2x^2 - 3sin(x)» → función f(x). Lanza ValueError si tiene algo fuera de la lista."""
    s = str(expr or "").lower().replace("·", "*").replace("−", "-").replace("²", "^2").replace("³", "^3").strip()
    s = re.sub(r"^\s*(?:y|f\s*\(\s*x\s*\))\s*=\s*", "", s)
    if not s or len(s) > 80:
        raise ValueError("expresión vacía o muy larga")
    toks, pos = [], 0
    while pos < len(s):
        m = _TOK.match(s, pos)
        if not m or m.end() == pos:
            raise ValueError(f"símbolo no permitido en «{expr}»")
        num, name, op = m.groups()
        if name and name != "x" and name not in _FUNCS:
            raise ValueError(f"«{name}» no está permitido")
        toks.append(repr(float(num.replace(",", "."))) if num else name or ("**" if op in ("^", "**") else op))   # floats: 9^9^9 no cuelga
        pos = m.end()
    out = []
    for t in toks:                                     # multiplicación implícita: 2x, 3(x+1), x(x-1), 2sin(x), (x+1)(x-1)
        if out:
            p = out[-1]
            left = re.match(r"[\d.]+$", p) or p in ("x", ")", "pi", "e")
            if left and (t in ("x", "(") or t in _FUNCS):
                out.append("*")
        out.append(t)
    code = " ".join(out)
    env = {"__builtins__": {}}
    env.update(_FUNCS)
    try:
        f = eval(compile("lambda x: " + code, "<expr>", "eval"), env)        # solo números, x y la lista cerrada
        f(1.0)
    except ZeroDivisionError:
        pass
    except Exception as e:
        raise ValueError(f"no entendí la expresión «{expr}»: {e}")
    return f


def clean(spec):
    """Comprueba la descripción de la figura. → dict limpio o None."""
    if not isinstance(spec, dict):
        return None
    t = str(spec.get("tipo", "")).lower().strip()
    t = {"función": "funcion", "funciones": "funcion", "cartesiano": "plano", "triángulo": "triangulo", "círculo": "circulo",
         "circunferencia": "circulo", "rectángulo": "rectangulo", "barra": "barras", "pastel": "torta", "circular": "torta"}.get(t, t)
    if t not in TYPES:
        return None
    out = {"tipo": t}
    num = lambda v, d: float(v) if isinstance(v, (int, float)) and math.isfinite(v) else d
    if t == "funcion":
        try:
            compile_expr(spec.get("expr"))
            out["expr"] = str(spec["expr"])[:80]
            if spec.get("expr2"):
                compile_expr(spec["expr2"])
                out["expr2"] = str(spec["expr2"])[:80]
        except (ValueError, KeyError):
            return None
        out["xmin"], out["xmax"] = num(spec.get("xmin"), -5.0), num(spec.get("xmax"), 5.0)
        if out["xmax"] - out["xmin"] < 0.5 or out["xmax"] - out["xmin"] > 400:
            out["xmin"], out["xmax"] = -5.0, 5.0
    elif t == "plano":
        pts = []
        for p in (spec.get("puntos") or [])[:12]:
            if isinstance(p, (list, tuple)) and len(p) >= 2 and all(isinstance(v, (int, float)) for v in p[:2]):
                pts.append([float(p[0]), float(p[1]), str(p[2])[:6] if len(p) > 2 else ""])
        if not pts:
            return None
        out.update(puntos=pts, unir=bool(spec.get("unir")))
    elif t == "triangulo":
        v = [str(x)[:4] for x in (spec.get("vertices") or ["A", "B", "C"])][:3]
        out.update(vertices=v + ["A", "B", "C"][len(v):], lados={str(k)[:4]: str(x)[:14] for k, x in (spec.get("lados") or {}).items()},
                   angulos={str(k)[:4]: str(x)[:10] for k, x in (spec.get("angulos") or {}).items()}, recto=str(spec.get("recto") or "")[:4])
    elif t == "circulo":
        out.update(radio=str(spec.get("radio") or "r")[:14], diametro=bool(spec.get("diametro")))
    elif t == "rectangulo":
        out.update(base=str(spec.get("base") or "b")[:14], altura=str(spec.get("altura") or "h")[:14])
    else:
        et = [str(x)[:18] for x in (spec.get("etiquetas") or [])][:10]
        va = [float(x) for x in (spec.get("valores") or []) if isinstance(x, (int, float)) and x >= 0][:10]
        if not et or len(et) != len(va) or not any(va):
            return None
        out.update(etiquetas=et, valores=va, titulo=str(spec.get("titulo") or "")[:60])
    return out


# ----------------------------------------------------------------------------- dibujar
def _font(size, bold=False):
    from PIL import ImageFont
    for name in (("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("arial.ttf", "DejaVuSans.ttf")):
        for d in ("", "C:/Windows/Fonts/", "/usr/share/fonts/truetype/dejavu/"):
            try:
                return ImageFont.truetype(d + name, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _nice_step(span):
    raw = span / 10
    p = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    for m in (1, 2, 5, 10):
        if raw <= m * p:
            return m * p
    return 10 * p


def _axes(d, xmin, xmax, ymin, ymax, box, xticks=True):
    x0, y0, x1, y1 = box
    sx = lambda x: x0 + (x - xmin) / (xmax - xmin) * (x1 - x0)
    sy = lambda y: y1 - (y - ymin) / (ymax - ymin) * (y1 - y0)
    f = _font(16)
    for step, axis in ((_nice_step(xmax - xmin), "x"), (_nice_step(ymax - ymin), "y")):
        lo, hi = (xmin, xmax) if axis == "x" else (ymin, ymax)
        v = math.ceil(lo / step) * step
        while v <= hi + 1e-9:
            if axis == "x" and not xticks:
                pass
            elif axis == "x":
                d.line([sx(v), y0, sx(v), y1], fill=(225, 228, 235), width=1)
            else:
                d.line([x0, sy(v), x1, sy(v)], fill=(225, 228, 235), width=1)
            v += step
    ax_y = sy(0) if ymin <= 0 <= ymax else y1
    ax_x = sx(0) if xmin <= 0 <= xmax else x0
    d.line([x0, ax_y, x1, ax_y], fill=(40, 40, 40), width=2)
    d.line([ax_x, y0, ax_x, y1], fill=(40, 40, 40), width=2)
    for step, axis in ((_nice_step(xmax - xmin), "x"), (_nice_step(ymax - ymin), "y")):
        lo, hi = (xmin, xmax) if axis == "x" else (ymin, ymax)
        v = math.ceil(lo / step) * step
        while v <= hi + 1e-9:
            if abs(v) > 1e-9:
                lbl = (f"{v:g}").replace(".", ",")
                if axis == "x" and not xticks:
                    pass
                elif axis == "x":
                    d.line([sx(v), ax_y - 4, sx(v), ax_y + 4], fill=(40, 40, 40), width=2)
                    d.text((sx(v) - 6 * len(lbl) / 2, ax_y + 6), lbl, font=f, fill=(70, 70, 70))
                else:
                    d.line([ax_x - 4, sy(v), ax_x + 4, sy(v)], fill=(40, 40, 40), width=2)
                    d.text((ax_x + 7, sy(v) - 9), lbl, font=f, fill=(70, 70, 70))
            v += step
    if xticks:
        d.text((x1 - 14, ax_y - 26), "x", font=_font(20, True), fill=(40, 40, 40))
        d.text((ax_x + 8, y0 - 2), "y", font=_font(20, True), fill=(40, 40, 40))
    return sx, sy


def _draw_function(spec):
    from PIL import Image, ImageDraw
    fs = [compile_expr(spec["expr"])] + ([compile_expr(spec["expr2"])] if spec.get("expr2") else [])
    xmin, xmax = spec["xmin"], spec["xmax"]
    xs = [xmin + (xmax - xmin) * i / 600 for i in range(601)]
    series = []
    for f in fs:
        ys = []
        for x in xs:
            try:
                y = f(x)
                ys.append(y if isinstance(y, (int, float)) and math.isfinite(y) and abs(y) < 1e6 else None)
            except (ValueError, ZeroDivisionError, OverflowError):
                ys.append(None)
        series.append(ys)
    vals = sorted(y for s in series for y in s if y is not None)
    if not vals:
        raise ValueError("la función no tiene valores en ese intervalo")
    lo, hi = vals[int(len(vals) * .02)], vals[int(len(vals) * .98) - 1]
    if hi - lo < 1:
        lo, hi = lo - 1, hi + 1
    pad = (hi - lo) * .12
    ymin, ymax = min(lo - pad, -0.5 if lo > 0 else lo - pad), max(hi + pad, 0.5 if hi < 0 else hi + pad)
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    sx, sy = _axes(d, xmin, xmax, ymin, ymax, (50, 30, W - 30, H - 40))
    colors = [(30, 90, 200), (200, 60, 40)]
    for k, ys in enumerate(series):
        pts = []
        for x, y in zip(xs, ys):
            if y is None or not ymin <= y <= ymax:
                if len(pts) > 1:
                    d.line(pts, fill=colors[k], width=4)
                pts = []
            else:
                pts.append((sx(x), sy(y)))
        if len(pts) > 1:
            d.line(pts, fill=colors[k], width=4)
        lbl = "y = " + (spec["expr"] if k == 0 else spec["expr2"])
        d.text((60, 36 + 26 * k), lbl, font=_font(20, True), fill=colors[k])
    return im


def _draw_plane(spec):
    from PIL import Image, ImageDraw
    xs = [p[0] for p in spec["puntos"]] + [0]
    ys = [p[1] for p in spec["puntos"]] + [0]
    xmin, xmax = min(xs) - 1.5, max(xs) + 1.5
    ymin, ymax = min(ys) - 1.5, max(ys) + 1.5
    span = max((xmax - xmin) * H / W, ymax - ymin)     # misma escala en x y en y, centrado
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    sx, sy = _axes(d, cx - span * W / H / 2, cx + span * W / H / 2, cy - span / 2, cy + span / 2, (50, 30, W - 30, H - 40))
    pts = [(sx(p[0]), sy(p[1])) for p in spec["puntos"]]
    if spec["unir"] and len(pts) > 1:
        d.line(pts + ([pts[0]] if len(pts) > 2 else []), fill=(30, 90, 200), width=3)
    for (x, y), p in zip(pts, spec["puntos"]):
        d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=(200, 60, 40))
        if p[2]:
            d.text((x + 10, y - 28), f"{p[2]}", font=_font(22, True), fill=(20, 20, 20))
    return im


def _draw_triangle(spec):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    A, B, C = spec["vertices"]
    if spec["recto"]:
        P = {spec["recto"]: (220, 500)}
        others = [v for v in (A, B, C) if v != spec["recto"]] or [A, B]
        P[others[0]] = (720, 500)
        P[others[1] if len(others) > 1 else B] = (220, 140)
    else:
        P = {A: (160, 500), B: (740, 500), C: (480, 130)}
    poly = [P[A], P[B], P[C]]
    d.polygon(poly, outline=(30, 90, 200), width=4)
    cx, cy = sum(p[0] for p in poly) / 3, sum(p[1] for p in poly) / 3
    fb, fs = _font(26, True), _font(22)
    for v, (x, y) in P.items():
        dx, dy = x - cx, y - cy
        n = math.hypot(dx, dy) or 1
        d.text((x + dx / n * 22 - 8, y + dy / n * 22 - 14), v, font=fb, fill=(20, 20, 20))
    if spec["recto"] and spec["recto"] in P:
        x, y = P[spec["recto"]]
        d.rectangle([x, y - 34, x + 34, y], outline=(40, 40, 40), width=2)
    for name, txt in spec["lados"].items():
        a, b = (name[:1], name[1:2]) if len(name) >= 2 else (None, None)
        if a in P and b in P:
            (x1, y1), (x2, y2) = P[a], P[b]
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            dx, dy = mx - cx, my - cy
            n = math.hypot(dx, dy) or 1
            d.text((mx + dx / n * 30 - 6 * len(txt), my + dy / n * 30 - 12), txt, font=fs, fill=(200, 60, 40))
    for v, txt in spec["angulos"].items():
        if v in P:
            x, y = P[v]
            d.text((x + (cx - x) * .22 - 10, y + (cy - y) * .22 - 10), txt, font=fs, fill=(30, 130, 60))
    d.text((W - 200, H - 36), "(no está a escala)", font=_font(16), fill=(120, 120, 120))
    return im


def _draw_circle(spec):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    cx, cy, r = W / 2, H / 2, 230
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(30, 90, 200), width=4)
    d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(20, 20, 20))
    if spec.get("diametro"):
        d.line([cx - r, cy, cx + r, cy], fill=(200, 60, 40), width=3)
        d.text((cx - 40, cy - 34), f"d = {spec['radio']}", font=_font(24, True), fill=(200, 60, 40))
    else:
        d.line([cx, cy, cx + r, cy], fill=(200, 60, 40), width=3)
        d.text((cx + r / 2 - 40, cy - 34), f"r = {spec['radio']}", font=_font(24, True), fill=(200, 60, 40))
    return im


def _draw_rect(spec):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([170, 170, 730, 450], outline=(30, 90, 200), width=4)
    d.text((420, 462), spec["base"], font=_font(24, True), fill=(200, 60, 40))
    d.text((60, 296), spec["altura"], font=_font(24, True), fill=(200, 60, 40))
    return im


def _draw_bars(spec):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    vals, labels = spec["valores"], spec["etiquetas"]
    if spec["titulo"]:
        d.text((60, 14), spec["titulo"], font=_font(24, True), fill=(20, 20, 20))
    top = max(vals)
    _sx, sy = _axes(d, 0, len(vals), 0, top * 1.15, (70, 60, W - 30, H - 70), xticks=False)
    bw = (W - 100) / len(vals)
    pal = [(30, 90, 200), (200, 60, 40), (40, 150, 90), (230, 160, 30), (130, 80, 190), (40, 160, 190)]
    for i, (v, l) in enumerate(zip(vals, labels)):
        x0 = 70 + i * bw + bw * .18
        d.rectangle([x0, sy(v), x0 + bw * .64, sy(0)], fill=pal[i % len(pal)])
        d.text((x0, sy(0) + 22), l[:12], font=_font(17), fill=(40, 40, 40))
    return im


def _draw_pie(spec):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    if spec["titulo"]:
        d.text((40, 14), spec["titulo"], font=_font(24, True), fill=(20, 20, 20))
    total = sum(spec["valores"])
    pal = [(30, 90, 200), (200, 60, 40), (40, 150, 90), (230, 160, 30), (130, 80, 190), (40, 160, 190), (150, 150, 150)]
    a = -90.0
    box = [70, 80, 570, 580]
    for i, (v, l) in enumerate(zip(spec["valores"], spec["etiquetas"])):
        ang = 360 * v / total
        d.pieslice(box, a, a + ang, fill=pal[i % len(pal)], outline="white", width=3)
        a += ang
        d.rectangle([610, 110 + i * 44, 640, 140 + i * 44], fill=pal[i % len(pal)])
        d.text((652, 112 + i * 44), f"{l} ({v:g})".replace(".", ","), font=_font(20), fill=(30, 30, 30))
    return im


def render(spec, out_dir=None):
    """Dibuja la figura y devuelve la ruta del PNG (o None si no se pudo)."""
    spec = clean(spec)
    if not spec:
        return None
    fn = {"funcion": _draw_function, "plano": _draw_plane, "triangulo": _draw_triangle, "circulo": _draw_circle,
          "rectangulo": _draw_rect, "barras": _draw_bars, "torta": _draw_pie}[spec["tipo"]]
    try:
        im = fn(spec)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    fd, path = tempfile.mkstemp(suffix=".png", dir=out_dir)
    os.close(fd)
    im.save(path)
    return path


def add_to_docx(doc, spec, width_cm=8.5):
    """Inserta la figura en el Word (después del enunciado). True si la puso."""
    from docx.shared import Cm
    path = render(spec)
    if not path:
        return False
    try:
        doc.add_picture(path, width=Cm(width_cm))
        return True
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
