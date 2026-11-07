"""Videos animados de matemáticas al estilo 3Blue1Brown (12.0). Lógica pura, sin Jarvis.

La IA escribe el guion como una lista de escenas con un vocabulario CERRADO de dibujos (triángulo rectángulo con sus
cuadrados, gráfica de una función, recta numérica, fracción, círculo, rectángulo, polígono, ángulo, barras y pasos de
álgebra). Este módulo los anima él mismo, fotograma a fotograma, con un estilo inspirado en Manim (fondo oscuro, trazos
que se dibujan, fórmulas que se escriben), los narra con la voz que se le pase y los une en un MP4 con subtítulos.

Nunca se ejecuta código escrito por la IA: lo que no está en el vocabulario se ignora. Las funciones de las gráficas
se leen con la lista cerrada de símbolos de verificar.py.
"""
import math
import os
import re
import subprocess
import wave

W, H, FPS = 1280, 720, 30
SS = 2                                    # se dibuja al doble y se reduce: bordes suaves
BG = (14, 17, 22)
C = {"azul": (88, 196, 221), "amarillo": (255, 221, 85), "verde": (131, 193, 103), "rojo": (252, 98, 85), "morado": (154, 114, 172),
     "naranja": (255, 134, 47), "blanco": (236, 240, 241), "gris": (110, 122, 135), "rosa": (255, 128, 171)}
SIDE = ["azul", "verde", "amarillo"]
VISUALS = ("triangulo_rectangulo", "grafica", "recta_numerica", "fraccion", "circulo", "rectangulo", "poligono", "angulo", "barras", "pasos")
MAX_SCENES = 14


# ============================================================================ GUION (IA)
def prompt(tema, grado="", minutos=2.0, asignatura="Matemáticas"):
    n = max(3, min(MAX_SCENES, round(minutos * 60 / 17)))
    palabras = int(minutos * 140)
    return f"""Eres un profesor que hace videos de matemáticas al estilo de 3Blue1Brown: primero la intuición, luego el dibujo, \
luego la fórmula; preguntas al espectador («¿qué crees que pasa si…?») y un cierre que lo resume todo.
Escribe el guion de un video de {minutos:g} minutos sobre: {tema}. Público: estudiantes de {grado or 'bachillerato'} ({asignatura}), \
en español de Colombia, claro y cercano. Unas {palabras} palabras de narración en total, repartidas en {n} escenas.

Responde SOLO un JSON:
{{"titulo": "título corto del video",
 "escenas": [{{"titulo": "título de la escena (máx. 6 palabras)",
   "narracion": "lo que dice la voz en esta escena (2 a 4 frases). Fórmulas en palabras o con $…$",
   "visual": un dibujo de la lista de abajo o null,
   "formulas": ["fórmulas que aparecen escritas, en texto plano: a^2 + b^2 = c^2"],
   "puntos": ["ideas clave cortas (máx. 7 palabras) que aparecen una a una"]}}]}}

Dibujos posibles (usa SOLO estos, con estos campos; números sencillos):
- {{"tipo": "triangulo_rectangulo", "a": 3, "b": 4, "etiquetas": ["a", "b", "c"], "cuadrados": true}}
- {{"tipo": "grafica", "funcion": "x^2 - 4", "xmin": -4, "xmax": 4, "puntos": [[2, 0], [-2, 0]]}}   (función de x: + - * / ^ sqrt sin cos)
- {{"tipo": "recta_numerica", "min": -5, "max": 5, "marcas": [-3, 2]}}
- {{"tipo": "fraccion", "partes": 8, "sombreadas": 3}}
- {{"tipo": "circulo", "etiqueta": "r"}}
- {{"tipo": "rectangulo", "base": "b", "altura": "h"}}
- {{"tipo": "poligono", "lados": 6}}
- {{"tipo": "angulo", "grados": 60}}
- {{"tipo": "barras", "etiquetas": ["A", "B", "C"], "valores": [3, 5, 2]}}
- {{"tipo": "pasos", "lineas": ["2x + 3 = 7", "2x = 4", "x = 2"]}}   (cada línea se transforma en la siguiente; deben ser correctas)
Cada escena tiene al menos un dibujo, una fórmula o un punto. La primera escena engancha con una pregunta; la última resume."""


def _txt(v, n=300):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def _num(v, d, lo=-1e6, hi=1e6):
    try:
        x = float(str(v).replace(",", "."))
        return d if math.isnan(x) else max(lo, min(hi, x))
    except (TypeError, ValueError):
        return d


def clean_visual(v):
    if not isinstance(v, dict):
        return None
    t = _txt(v.get("tipo"), 30).lower().replace(" ", "_")
    if t not in VISUALS:
        return None
    if t == "triangulo_rectangulo":
        et = [(_txt(x, 8) or d) for x, d in zip(list(v.get("etiquetas") or []) + ["", "", ""], ["a", "b", "c"])]
        return {"tipo": t, "a": _num(v.get("a"), 3, 0.5, 50), "b": _num(v.get("b"), 4, 0.5, 50), "etiquetas": et[:3],
                "cuadrados": bool(v.get("cuadrados", True))}
    if t == "grafica":
        f = _txt(v.get("funcion"), 80)
        f = re.sub(r"^\s*(?:y|f\s*\(\s*x\s*\))\s*=\s*", "", f)
        if not f:
            return None
        a, b = _num(v.get("xmin"), -5, -100, 100), _num(v.get("xmax"), 5, -100, 100)
        if b - a < 0.5:
            a, b = -5, 5
        pts = []
        for p in (v.get("puntos") or [])[:6]:
            if isinstance(p, (list, tuple)) and len(p) == 2:
                pts.append((_num(p[0], 0), _num(p[1], 0)))
        return {"tipo": t, "funcion": f, "xmin": a, "xmax": b, "puntos": pts}
    if t == "recta_numerica":
        a, b = int(_num(v.get("min"), -5, -50, 50)), int(_num(v.get("max"), 5, -50, 50))
        if b - a < 2:
            a, b = -5, 5
        if b - a > 24:
            b = a + 24
        return {"tipo": t, "min": a, "max": b, "marcas": [_num(x, 0, a, b) for x in (v.get("marcas") or [])[:6]]}
    if t == "fraccion":
        n = int(_num(v.get("partes"), 4, 1, 24))
        return {"tipo": t, "partes": n, "sombreadas": int(_num(v.get("sombreadas"), 1, 0, n))}
    if t == "circulo":
        return {"tipo": t, "etiqueta": _txt(v.get("etiqueta"), 8) or "r"}
    if t == "rectangulo":
        return {"tipo": t, "base": _txt(v.get("base"), 10) or "b", "altura": _txt(v.get("altura"), 10) or "h"}
    if t == "poligono":
        return {"tipo": t, "lados": int(_num(v.get("lados"), 5, 3, 12))}
    if t == "angulo":
        return {"tipo": t, "grados": _num(v.get("grados"), 60, 1, 359)}
    if t == "barras":
        vals = [_num(x, 0, 0, 1e6) for x in (v.get("valores") or [])[:8]]
        if not vals or max(vals) <= 0:
            return None
        et = [_txt(x, 10) for x in (v.get("etiquetas") or [])][:len(vals)]
        return {"tipo": t, "valores": vals, "etiquetas": et + [""] * (len(vals) - len(et))}
    if t == "pasos":
        ls = [_txt(x, 50) for x in (v.get("lineas") or []) if _txt(x, 50)][:6]
        return {"tipo": t, "lineas": ls} if ls else None
    return None


def clean(d):
    """El guion de la IA, validado: {"titulo", "escenas": [{titulo, narracion, visual, formulas, puntos}]}."""
    if not isinstance(d, dict):
        raise ValueError("el guion no es un JSON")
    out = []
    for s in (d.get("escenas") or [])[:MAX_SCENES]:
        if not isinstance(s, dict):
            continue
        sc = {"titulo": _txt(s.get("titulo"), 60), "narracion": _txt(s.get("narracion"), 900), "visual": clean_visual(s.get("visual")),
              "formulas": [_txt(f, 60) for f in (s.get("formulas") or []) if _txt(f, 60)][:3],
              "puntos": [_txt(p, 60) for p in (s.get("puntos") or []) if _txt(p, 60)][:4]}
        if sc["narracion"] and (sc["visual"] or sc["formulas"] or sc["puntos"] or sc["titulo"]):
            out.append(sc)
    if not out:
        raise ValueError("el guion no trae escenas")
    return {"titulo": _txt(d.get("titulo"), 80) or out[0]["titulo"] or "Video", "escenas": out}


# ============================================================================ TEXTO
_FONT_CACHE = {}
_FONTS = {
    "bold": ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
    "regular": ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf"],
    "math": ["C:/Windows/Fonts/cambria.ttc", "C:/Windows/Fonts/times.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
             "/System/Library/Fonts/Supplemental/Times New Roman.ttf"],
}


def font(kind, size):
    from PIL import ImageFont
    key = (kind, size)
    if key not in _FONT_CACHE:
        f = None
        for p in _FONTS.get(kind, []) + _FONTS["regular"]:
            if os.path.exists(p):
                try:
                    f = ImageFont.truetype(p, size)
                    break
                except OSError:
                    continue
        _FONT_CACHE[key] = f or ImageFont.load_default(size)
    return _FONT_CACHE[key]


_SUP = str.maketrans("0123456789-+n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺ⁿ")


def pretty(f):
    """«a^2 + b^2 = c^2» → «a² + b² = c²», «sqrt(x)» → «√x», «3*x» → «3·x»."""
    s = str(f or "")
    if "\\" in s or "$" in s:
        import mathtext
        s = mathtext.to_plain(s.strip("$"))
    s = re.sub(r"\^\(?(-?\d+|n)\)?", lambda m: m.group(1).translate(_SUP), s)
    s = re.sub(r"sqrt\s*\(([^()]*)\)", lambda m: "√" + (m.group(1) if re.fullmatch(r"\w+", m.group(1)) else f"({m.group(1)})"), s)
    s = re.sub(r"(?<=\d)\s*\*\s*(?=[a-zA-Z(])", "", s).replace("*", "·").replace("-", "−")
    return s


def wrap(text, fnt, width):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if fnt.getlength(test) <= width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def subtitle_chunks(text, dur):
    """Trozos de unas 9 palabras con su tiempo, proporcional a las letras. → [(inicio, fin, texto)]."""
    words = str(text).split()
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= 9 or (len(cur) >= 5 and re.search(r"[.,;:?!]$", w)):
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    total = sum(len(c) for c in chunks) or 1
    out, t = [], 0.0
    for c in chunks:
        d = dur * len(c) / total
        out.append((t, t + d, c))
        t += d
    return out


def srt_time(s):
    ms = int(round(s * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


# ============================================================================ DIBUJO
def ease(p):
    p = max(0.0, min(1.0, p))
    return p * p * (3 - 2 * p)


def _prog(t, a, b):
    return ease((t - a) / (b - a)) if b > a else (1.0 if t >= a else 0.0)


def _col(name, alpha=1.0):
    r, g, b = C.get(name, C["blanco"])
    return (r, g, b, int(255 * max(0, min(1, alpha))))


def _poly_partial(pts, p):
    """Los puntos de la poligonal recorrida hasta la fracción p de su largo."""
    if p >= 1:
        return pts
    segs = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    goal, acc, out = sum(segs) * p, 0.0, [pts[0]]
    for i, L in enumerate(segs):
        if acc + L >= goal:
            k = (goal - acc) / L if L else 0
            out.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * k, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * k))
            return out
        acc += L
        out.append(pts[i + 1])
    return out


class Canvas:
    """Un fotograma al doble de tamaño. Las coordenadas que recibe son las del video (1280×720)."""

    def __init__(self):
        from PIL import Image, ImageDraw
        self.img = Image.new("RGB", (W * SS, H * SS), BG)
        self.d = ImageDraw.Draw(self.img, "RGBA")

    def line(self, pts, color, width=4, p=1.0):
        pts = _poly_partial([(x * SS, y * SS) for x, y in pts], p)
        if len(pts) >= 2:
            self.d.line(pts, fill=color, width=int(width * SS), joint="curve")

    def poly(self, pts, fill=None, outline=None, width=4):
        P = [(x * SS, y * SS) for x, y in pts]
        if fill:
            self.d.polygon(P, fill=fill)
        if outline:
            self.d.line(P + [P[0]], fill=outline, width=int(width * SS), joint="curve")

    def circle(self, cx, cy, r, fill=None, outline=None, width=4):
        self.d.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], fill=fill, outline=outline, width=int(width * SS))

    def arc(self, cx, cy, r, a0, a1, color, width=4):
        if a1 - a0 > 0.5:
            self.d.arc([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], a0, a1, fill=color, width=int(width * SS))

    def pieslice(self, cx, cy, r, a0, a1, fill):
        if a1 - a0 > 0.2:
            self.d.pieslice([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], a0, a1, fill=fill)

    def text(self, x, y, s, size, color, kind="regular", anchor="la", reveal=1.0):
        if reveal <= 0 or not s:
            return
        f = font(kind, size * SS)
        if reveal < 1:
            n = max(1, int(round(len(s) * reveal)))
            full_w = f.getlength(s)
            part = s[:n]
            # «se escribe»: aparece letra a letra, con el lugar final ya reservado
            if anchor[0] == "m":
                x0 = x * SS - full_w / 2
                self.d.text((x0, y * SS), part, font=f, fill=color, anchor="l" + anchor[1])
                return
            self.d.text((x * SS, y * SS), part, font=f, fill=color, anchor=anchor)
            return
        self.d.text((x * SS, y * SS), s, font=f, fill=color, anchor=anchor)

    def width(self, s, size, kind="regular"):
        return font(kind, size * SS).getlength(s) / SS

    def frame(self):
        return self.img.reduce(SS)


def _box_fit(pts, box, pad=40):
    """Escala y centra unos puntos (y hacia arriba) dentro de la caja (x0, y0, x1, y1). → función de transformación."""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    w, h = (max(xs) - min(xs)) or 1, (max(ys) - min(ys)) or 1
    bw, bh = box[2] - box[0] - 2 * pad, box[3] - box[1] - 2 * pad
    k = min(bw / w, bh / h)
    ox = box[0] + pad + (bw - w * k) / 2 - min(xs) * k
    oy = box[1] + pad + (bh - h * k) / 2 + max(ys) * k
    return lambda x, y: (ox + x * k, oy - y * k), k


def draw_visual(cv, v, box, p, fn=None):
    """Dibuja el visual en la caja con avance p (0..1)."""
    t = v["tipo"]
    white = _col("blanco")
    if t == "triangulo_rectangulo":
        a, b = v["a"], v["b"]
        pts = [(0, 0), (b, 0), (0, a)]
        sides = [((0, 0), (b, 0), "azul", 0.35), ((0, a), (0, 0), "verde", 0.5), ((b, 0), (0, a), "amarillo", 0.65)]
        ext = list(pts)
        if v["cuadrados"]:
            for (x0, y0), (x1, y1), _col_name, _start in sides:
                ext += [(x1 + (y1 - y0), y1 - (x1 - x0)), (x0 + (y1 - y0), y0 - (x1 - x0))]
        T, _k = _box_fit(ext, box, 30)
        P = [T(*q) for q in pts]
        # 1) el triángulo se dibuja; 2) aparecen los cuadrados de cada lado; 3) las etiquetas
        cv.line(P + [P[0]], white, 4, _prog(p, 0, 0.35))
        al = _prog(p, 0.3, 0.38)
        if al > 0:
            q = 18
            cv.line([(P[0][0] + q, P[0][1]), (P[0][0] + q, P[0][1] - q), (P[0][0], P[0][1] - q)], _col("blanco", al), 2)
        if v["cuadrados"]:
            for (x0, y0), (x1, y1), col, start in sides:
                al = _prog(p, start, start + 0.15)
                if al <= 0:
                    continue
                dx, dy = x1 - x0, y1 - y0
                nx, ny = dy, -dx                                  # hacia afuera del triángulo
                quad = [T(x0, y0), T(x1, y1), T(x1 + nx, y1 + ny), T(x0 + nx, y0 + ny)]
                cv.poly(quad, fill=_col(col, 0.28 * al), outline=_col(col, al), width=3)
        al = _prog(p, 0.75, 0.9)
        if al > 0:
            la, lb, lc = v["etiquetas"]
            mid = lambda u, w: ((u[0] + w[0]) / 2, (u[1] + w[1]) / 2)
            cx_, cy_ = mid(P[0], P[1])
            cv.text(cx_, cy_ + 16, lb, 30, _col("azul", al), "math", "mt")
            cx_, cy_ = mid(P[0], P[2])
            cv.text(cx_ - 16, cy_, la, 30, _col("verde", al), "math", "rm")
            cx_, cy_ = mid(P[1], P[2])
            cv.text(cx_ + 14, cy_ - 10, lc, 30, _col("amarillo", al), "math", "lb")
        return
    if t == "grafica":
        a, b = v["xmin"], v["xmax"]
        xs = [a + (b - a) * i / 240 for i in range(241)]
        ys = []
        for x in xs:
            try:
                y = float(fn(x)) if fn else float("nan")
            except Exception:
                y = float("nan")
            ys.append(y if math.isfinite(y) else float("nan"))
        good = [y for y in ys if not math.isnan(y)]
        lo, hi = (min(good + [0]), max(good + [0])) if good else (-5, 5)
        lo, hi = max(lo, -60), min(hi, 60)
        if hi - lo < 1:
            lo, hi = lo - 1, hi + 1
        x0, y0, x1, y1 = box[0] + 40, box[1] + 30, box[2] - 30, box[3] - 40
        X = lambda x: x0 + (x - a) / (b - a) * (x1 - x0)
        Y = lambda y: y1 - (y - lo) / (hi - lo) * (y1 - y0)
        ax = _prog(p, 0, 0.25)
        grid = _col("azul", 0.18 * ax)
        for gx in range(math.ceil(a), math.floor(b) + 1):
            cv.line([(X(gx), y0), (X(gx), y1)], grid, 1)
        step = max(1, round((hi - lo) / 8))
        for gy in range(math.ceil(lo / step) * step, int(hi) + 1, step):
            cv.line([(x0, Y(gy)), (x1, Y(gy))], grid, 1)
        if lo <= 0 <= hi:
            cv.line([(x0, Y(0)), (x1, Y(0))], _col("blanco", ax), 2)
        if a <= 0 <= b:
            cv.line([(X(0), y1), (X(0), y0)], _col("blanco", ax), 2)
        seg, segs = [], []
        for x, y in zip(xs, ys):
            if math.isnan(y) or not (lo - (hi - lo) <= y <= hi + (hi - lo)):
                if len(seg) > 1:
                    segs.append(seg)
                seg = []
            else:
                seg.append((X(x), Y(max(lo - 1, min(hi + 1, y)))))
        if len(seg) > 1:
            segs.append(seg)
        pc = _prog(p, 0.25, 0.75)
        total = sum(len(s) for s in segs) or 1
        done = 0
        for s in segs:
            share = len(s) / total
            local = max(0.0, min(1.0, (pc - done) / share)) if share else 0
            if local > 0:
                cv.line(s, _col("amarillo"), 5, local)
            done += share
        al = _prog(p, 0.75, 0.9)
        for (px, py) in v["puntos"]:
            if a <= px <= b and lo <= py <= hi:
                cv.circle(X(px), Y(py), 8 * al, fill=_col("rojo", al))
                cv.text(X(px) + 12, Y(py) - 10, f"({_fmt(px)}, {_fmt(py)})", 22, _col("rojo", al), "math", "lb")
        cv.text(x1, y0 - 8, "y = " + pretty(v["funcion"]), 28, _col("amarillo", _prog(p, 0.6, 0.8)), "math", "rb")
        return
    if t == "recta_numerica":
        a, b = v["min"], v["max"]
        x0, x1, yy = box[0] + 40, box[2] - 40, (box[1] + box[3]) / 2
        X = lambda x: x0 + (x - a) / (b - a) * (x1 - x0)
        cv.line([(x0 - 10, yy), (x1 + 10, yy)], white, 3, _prog(p, 0, 0.3))
        al = _prog(p, 0.2, 0.45)
        for k in range(a, b + 1):
            cv.line([(X(k), yy - 10), (X(k), yy + 10)], _col("blanco", al), 2)
            cv.text(X(k), yy + 20, str(k).replace("-", "−"), 22, _col("blanco", al), "math", "mt")
        for i, m in enumerate(v["marcas"]):
            al = _prog(p, 0.5 + i * 0.08, 0.6 + i * 0.08)
            cv.circle(X(m), yy, 11 * al, fill=_col("amarillo", al))
            cv.text(X(m), yy - 22, _fmt(m), 26, _col("amarillo", al), "math", "mb")
        return
    if t == "fraccion":
        n, k = v["partes"], v["sombreadas"]
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        r = min(box[2] - box[0], box[3] - box[1]) / 2 - 50
        cv.circle(cx, cy, r, outline=_col("blanco", _prog(p, 0, 0.2)), width=4)
        for i in range(k):
            al = _prog(p, 0.4 + i * 0.4 / max(1, k), 0.5 + i * 0.4 / max(1, k))
            cv.pieslice(cx, cy, r - 2, -90 + 360 * i / n, -90 + 360 * (i + 1) / n, _col("azul", 0.75 * al))
        al = _prog(p, 0.1, 0.4)
        for i in range(n):
            ang = math.radians(-90 + 360 * i / n)
            cv.line([(cx, cy), (cx + r * math.cos(ang), cy + r * math.sin(ang))], _col("blanco", al), 3)
        cv.text(cx, cy + r + 20, f"{k}/{n}", 38, _col("amarillo", _prog(p, 0.8, 0.95)), "math", "mt")
        return
    if t == "circulo":
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        r = min(box[2] - box[0], box[3] - box[1]) / 2 - 50
        pc = _prog(p, 0, 0.5)
        cv.arc(cx, cy, r, -90, -90 + 360 * pc, _col("azul"), 5)
        al = _prog(p, 0.5, 0.7)
        cv.circle(cx, cy, 6 * al, fill=_col("blanco", al))
        cv.line([(cx, cy), (cx + r, cy)], _col("amarillo", al), 4, al)
        cv.text(cx + r / 2, cy - 12, v["etiqueta"], 32, _col("amarillo", _prog(p, 0.65, 0.85)), "math", "mb")
        return
    if t == "rectangulo":
        x0, y0 = box[0] + 70, box[1] + 70
        x1, y1 = box[2] - 70, box[3] - 70
        pts = [(x0, y1), (x1, y1), (x1, y0), (x0, y0), (x0, y1)]
        cv.poly(pts[:-1], fill=_col("azul", 0.2 * _prog(p, 0.4, 0.7)))
        cv.line(pts, _col("azul"), 5, _prog(p, 0, 0.45))
        al = _prog(p, 0.6, 0.85)
        cv.text((x0 + x1) / 2, y1 + 14, v["base"], 32, _col("amarillo", al), "math", "mt")
        cv.text(x0 - 14, (y0 + y1) / 2, v["altura"], 32, _col("verde", al), "math", "rm")
        return
    if t == "poligono":
        n = v["lados"]
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        r = min(box[2] - box[0], box[3] - box[1]) / 2 - 50
        pts = [(cx + r * math.cos(math.radians(-90 + 360 * i / n)), cy + r * math.sin(math.radians(-90 + 360 * i / n))) for i in range(n)]
        cv.poly(pts, fill=_col("morado", 0.25 * _prog(p, 0.5, 0.8)))
        cv.line(pts + [pts[0]], _col("morado"), 5, _prog(p, 0, 0.5))
        al = _prog(p, 0.5, 0.8)
        for q in pts:
            cv.circle(q[0], q[1], 7 * al, fill=_col("blanco", al))
        cv.text(cx, cy, f"{n} lados", 30, _col("blanco", _prog(p, 0.75, 0.9)), "regular", "mm")
        return
    if t == "angulo":
        g = v["grados"]
        L = min(box[2] - box[0] - 160, (box[3] - box[1] - 80) / max(0.35, math.sin(math.radians(min(g, 90)))))
        cx, cy = box[0] + 80 + (L * 0.5 if g > 90 else 0), box[3] - 40
        cv.line([(cx, cy), (cx + L, cy)], white, 4, _prog(p, 0, 0.25))
        gg = g * _prog(p, 0.25, 0.7)
        end = (cx + L * math.cos(math.radians(-gg)), cy + L * math.sin(math.radians(-gg)))
        if gg > 0:
            cv.line([(cx, cy), end], _col("azul"), 4)
            cv.arc(cx, cy, 70, -gg, 0, _col("amarillo"), 4)
        cv.text(cx + 90 * math.cos(math.radians(-g / 2)), cy + 90 * math.sin(math.radians(-g / 2)), f"{_fmt(g)}°", 32,
                _col("amarillo", _prog(p, 0.7, 0.85)), "math", "lm")
        return
    if t == "barras":
        vals, et = v["valores"], v["etiquetas"]
        n = len(vals)
        x0, y0, x1, y1 = box[0] + 40, box[1] + 40, box[2] - 30, box[3] - 50
        cv.line([(x0, y1), (x1, y1)], white, 3, _prog(p, 0, 0.2))
        bw = (x1 - x0) / n * 0.6
        top = max(vals)
        for i, val in enumerate(vals):
            al = _prog(p, 0.15 + i * 0.5 / n, 0.35 + i * 0.5 / n)
            h = (y1 - y0) * val / top * al
            bx = x0 + (x1 - x0) * (i + 0.2) / n
            if h > 1:
                cv.poly([(bx, y1), (bx + bw, y1), (bx + bw, y1 - h), (bx, y1 - h)], fill=_col(list(C)[i % 6], 0.85))
            cv.text(bx + bw / 2, y1 - h - 8, _fmt(val), 24, _col("blanco", al), "math", "mb")
            cv.text(bx + bw / 2, y1 + 10, et[i], 22, _col("gris", _prog(p, 0.1, 0.3)), "regular", "mt")
        return
    if t == "pasos":
        ls = [pretty(x) for x in v["lineas"]]
        n = len(ls)
        cx = (box[0] + box[2]) / 2
        gap = min(80, (box[3] - box[1] - 40) / max(1, n))
        top = (box[1] + box[3]) / 2 - gap * (n - 1) / 2
        for i, s in enumerate(ls):
            st = i / n * 0.9
            al = _prog(p, st, st + 0.6 / n)
            last = i == n - 1
            cv.text(cx, top + i * gap, s, 40 if last else 36, _col("amarillo" if last else "blanco", max(al, 0)), "math", "mm", reveal=al)
            if i and al > 0:
                cv.text(cx - cv.width(s, 36, "math") / 2 - 40, top + i * gap, "⇒", 28, _col("gris", al), "math", "rm")
        return


def _fmt(x):
    x = float(x)
    return (str(int(x)) if x == int(x) else f"{x:.2f}".rstrip("0").replace(".", ",")).replace("-", "−")


def draw_scene(cv, sc, t, dur, fn=None, idx=0, total=1, header=""):
    """Un fotograma de la escena en el segundo t (de dur)."""
    fade = min(1.0, t / 0.35, (dur - t) / 0.35) if dur > 0.8 else 1.0
    fade = max(0.0, fade)
    # título
    if header:
        cv.text(40, 30, header, 18, _col("gris", 0.9), "regular", "la")
    if sc["titulo"]:
        rv = _prog(t, 0.0, 0.7)
        cv.text(W / 2, 78, sc["titulo"], 44, _col("azul", fade), "bold", "mm", reveal=rv)
        wv = cv.width(sc["titulo"], 44, "bold") * rv
        cv.line([(W / 2 - wv / 2, 108), (W / 2 + wv / 2, 108)], _col("azul", 0.5 * fade), 2)
    has_v = sc["visual"] is not None
    side = sc["formulas"] or sc["puntos"]
    vbox = (40, 125, 700 if side else W - 40, 600)
    sbox = (720 if has_v else 140, 140, W - 40 if has_v else W - 140, 600)
    if has_v:
        vp = _prog(t, 0.3, 0.3 + max(2.5, min(5.0, dur * 0.45)))
        draw_visual(cv, sc["visual"], vbox, vp, fn)
    items = [("f", f) for f in sc["formulas"]] + [("p", p) for p in sc["puntos"]]
    if items:
        n = len(items)
        start, end = (dur * 0.3 if has_v else 0.6), dur * 0.8
        gap = 78 if n <= 4 else 60
        y = (sbox[1] + sbox[3]) / 2 - gap * (n - 1) / 2
        cx = (sbox[0] + sbox[2]) / 2
        for i, (k, s) in enumerate(items):
            a = start + (end - start) * i / n
            al = _prog(t, a, a + 0.9)
            if al <= 0:
                continue
            if k == "f":
                cv.text(cx, y + i * gap, pretty(s), 40 if has_v else 52, _col("amarillo", fade), "math", "mm", reveal=al)
            else:
                fnt = font("regular", 30 * SS)
                lines = wrap(s, fnt, (sbox[2] - sbox[0] - 40) * SS)
                cv.circle(sbox[0] + 22, y + i * gap, 6, fill=_col("verde", al * fade))
                cv.text(sbox[0] + 40, y + i * gap, lines[0], 30, _col("blanco", al * fade), "regular", "lm")
    if total > 1:                                        # barrita de avance del video
        cv.line([(0, H - 3), (W * (idx + 1) / total, H - 3)], _col("azul", 0.7), 3)


def draw_subtitle(cv, text):
    if not text:
        return
    fnt = font("regular", 28 * SS)
    lines = wrap(text, fnt, (W - 220) * SS)[:2]
    y = H - 34 - 34 * (len(lines) - 1)
    wmax = max(cv.width(l, 28) for l in lines)
    cv.d.rounded_rectangle([(W / 2 - wmax / 2 - 18) * SS, (y - 26) * SS, (W / 2 + wmax / 2 + 18) * SS, (H - 14) * SS], radius=10 * SS,
                           fill=(0, 0, 0, 165))
    for i, l in enumerate(lines):
        cv.text(W / 2, y + i * 34, l, 28, (255, 255, 255, 255), "regular", "mm")


# ============================================================================ AUDIO
def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        import shutil
        return shutil.which("ffmpeg") or ""


def _no_window():
    return 0x08000000 if os.name == "nt" else 0


def to_wav(src, dst, ffmpeg, rate=24000):
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", str(rate), "-sample_fmt", "s16", dst],
                   check=True, capture_output=True, creationflags=_no_window(), timeout=120)
    return dst


def wav_seconds(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate())


def build_audio(parts, durs, out, rate=24000):
    """Une los WAV de cada escena, cada uno al inicio de su escena y con silencio hasta completar su duración."""
    with wave.open(out, "wb") as o:
        o.setnchannels(1)
        o.setsampwidth(2)
        o.setframerate(rate)
        for p, d in zip(parts, durs):
            want = int(round(d * rate))
            got = 0
            if p and os.path.exists(p):
                with wave.open(p, "rb") as w:
                    if w.getframerate() == rate and w.getsampwidth() == 2 and w.getnchannels() == 1:
                        data = w.readframes(min(w.getnframes(), want))
                        o.writeframes(data)
                        got = len(data) // 2
            if want > got:
                o.writeframes(b"\x00\x00" * (want - got))
    return out


# ============================================================================ RENDER
def scene_fn(v):
    """La función de x de una gráfica, leída con la lista cerrada de símbolos (nunca texto libre)."""
    if not v or v["tipo"] != "grafica":
        return None
    try:
        import sympy
        import verificar
        e = verificar._parse(v["funcion"])
        x = sympy.Symbol("x")
        if e.free_symbols - {x}:
            return None
        return sympy.lambdify(x, e, "math")
    except Exception:
        return None


def render(guion, out_path, synth=None, progress=None, fps=FPS, cancel=None, workdir=None):
    """Hace el MP4 (y el .srt al lado). synth(texto, ruta_sin_extension) → ruta de audio o None.
    → {"mp4", "srt", "segundos", "escenas", "voz": bool}"""
    import tempfile
    ff = ffmpeg_exe()
    if not ff:
        raise RuntimeError("falta el componente de video (imageio-ffmpeg)")
    tmp = workdir or tempfile.mkdtemp(prefix="jarvis_video_")
    scenes = guion["escenas"]
    wavs, durs = [], []
    voiced = 0
    for i, sc in enumerate(scenes):
        wav = None
        if synth:
            try:
                src = synth(sc["narracion"], os.path.join(tmp, f"voz{i}"))
                if src and os.path.exists(src):
                    wav = to_wav(src, os.path.join(tmp, f"voz{i}_24k.wav"), ff)
                    voiced += 1
            except Exception:
                wav = None
        talk = wav_seconds(wav) if wav else len(sc["narracion"].split()) / 2.5
        durs.append(round(max(4.0, talk + 0.9), 2))
        wavs.append(wav)
        if progress:
            progress(0.25 * (i + 1) / len(scenes), "voz")
    audio = build_audio(wavs, durs, os.path.join(tmp, "audio.wav"))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    cmd = [ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-i", audio, "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
           "-shortest", "-movflags", "+faststart", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=_no_window())
    srt, n_sub = [], 0
    t0 = 0.0
    total_frames = int(sum(durs) * fps)
    done = 0
    try:
        for i, (sc, dur) in enumerate(zip(scenes, durs)):
            fn = scene_fn(sc["visual"])
            subs = subtitle_chunks(sc["narracion"], max(0.5, dur - 0.9) if wavs[i] else dur)
            for a, b, txt in subs:
                n_sub += 1
                srt.append(f"{n_sub}\n{srt_time(t0 + a)} --> {srt_time(t0 + b)}\n{txt}\n")
            prev_key, prev_bytes = None, None
            for k in range(int(round(dur * fps))):
                if cancel and cancel():
                    raise RuntimeError("cancelado")
                t = k / fps
                sub = next((txt for a, b, txt in subs if a <= t < b), "")
                key = _frame_key(sc, t, dur, sub)
                if key is None or key != prev_key or prev_bytes is None:
                    cv = Canvas()
                    draw_scene(cv, sc, t, dur, fn, i, len(scenes), guion["titulo"])
                    draw_subtitle(cv, sub)
                    prev_bytes = cv.frame().tobytes()
                    prev_key = key
                proc.stdin.write(prev_bytes)
                done += 1
                if progress and done % (fps * 2) == 0:
                    progress(0.25 + 0.73 * done / max(1, total_frames), "video")
            t0 += dur
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "replace")
        if proc.wait(timeout=600) != 0 or not os.path.exists(out_path):
            raise RuntimeError(f"no se pudo armar el video ({err.strip()[:200]})")
    except BaseException:
        try:
            proc.kill()
        except Exception:
            pass
        raise
    srt_path = os.path.splitext(out_path)[0] + ".srt"
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt))
    if progress:
        progress(1.0, "listo")
    return {"mp4": out_path, "srt": srt_path, "segundos": round(sum(durs), 1), "escenas": len(scenes), "voz": voiced > 0}


def _frame_key(sc, t, dur, sub):
    """Cuando ya no se mueve nada, el fotograma es igual al anterior: se reutiliza (mucho más rápido). None = se dibuja."""
    settle = max(0.3 + max(2.5, min(5.0, dur * 0.45)), dur * 0.8 + 0.9, 0.7)
    if t > settle and t < dur - 0.35:
        return ("quieto", sub)
    return None


def safe_name(text):
    s = re.sub(r"[^\w\s-]", "", str(text), flags=re.U).strip()
    return re.sub(r"\s+", " ", s)[:70] or "Video"


__all__ = ["prompt", "clean", "clean_visual", "render", "pretty", "subtitle_chunks", "build_audio", "ffmpeg_exe", "safe_name", "VISUALS"]
