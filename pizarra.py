"""Pizarra inteligente (12.0). Lógica pura, sin Jarvis.

La pizarra son páginas con trazos (coordenadas de 0 a 1, en proporción 16:9) y tarjetas de fórmulas reconocidas.
Aquí: guardar y deshacer trazos, leer lo que la IA reconoció de la letra matemática, verificar la cuenta con SymPy,
muestrear la gráfica de una función y pasar las páginas a un PDF para los apuntes.
"""
import math
import os
import re
import threading

import verificar

MAX_STROKES = 4000
MAX_POINTS = 3000
COLORS = {"blanco": "#ecf0f1", "amarillo": "#ffdd55", "azul": "#58c4dd", "verde": "#83c167", "rojo": "#fc6255", "rosa": "#ff80ab"}

_lock = threading.Lock()


def new_board():
    return {"pages": [{"strokes": [], "items": []}], "page": 0, "ver": 0}


def _num(v, lo=0.0, hi=1.0):
    try:
        x = float(v)
        return max(lo, min(hi, x)) if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def clean_points(pts, limit=MAX_POINTS):
    out = []
    for p in (pts or [])[:limit]:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            x, y = _num(p[0], -0.05, 1.05), _num(p[1], -0.05, 1.05)
            if x is not None and y is not None:
                out.append([round(x, 4), round(y, 4)])
    return out


def _color(c):
    c = str(c or "")
    return c if re.fullmatch(r"#[0-9a-fA-F]{6}", c) else COLORS["blanco"]


def add_points(b, sid, pts, color="", width=3, page=None):
    """Agrega puntos a un trazo (lo crea si no existe). Así el lápiz del celular manda el trazo por partes."""
    pts = clean_points(pts)
    if not pts:
        return None
    with _lock:
        pg = b["pages"][b["page"] if page is None else max(0, min(len(b["pages"]) - 1, int(page)))]
        sid = str(sid)[:40]
        st = next((s for s in reversed(pg["strokes"][-40:]) if s["id"] == sid), None)
        if st is None:
            if len(pg["strokes"]) >= MAX_STROKES:
                return None
            b["seq"] = b.get("seq", 0) + 1
            st = {"id": sid, "c": _color(color), "w": max(1, min(30, int(_num(width, 1, 30) or 3))), "p": [], "n": b["seq"]}
            pg["strokes"].append(st)
        room = MAX_POINTS - len(st["p"])
        st["p"].extend(pts[:max(0, room)])
        b["ver"] += 1
        return st


def undo(b):
    with _lock:
        pg = b["pages"][b["page"]]
        if pg["items"] and (not pg["strokes"] or pg["items"][-1].get("n", 0) > pg["strokes"][-1].get("n", 0)):
            pg["items"].pop()
        elif pg["strokes"]:
            pg["strokes"].pop()
        b["ver"] += 1


def erase(b, sid):
    with _lock:
        pg = b["pages"][b["page"]]
        n = len(pg["strokes"])
        pg["strokes"] = [s for s in pg["strokes"] if s["id"] != str(sid)]
        pg["items"] = [i for i in pg["items"] if i["id"] != str(sid)]
        b["ver"] += 1
        return n != len(pg["strokes"])


def clear_page(b):
    with _lock:
        b["pages"][b["page"]] = {"strokes": [], "items": []}
        b["ver"] += 1


def go_page(b, where):
    with _lock:
        if where == "nueva":
            b["pages"].append({"strokes": [], "items": []})
            b["page"] = len(b["pages"]) - 1
        elif where == "siguiente":
            b["page"] = min(len(b["pages"]) - 1, b["page"] + 1)
        elif where == "anterior":
            b["page"] = max(0, b["page"] - 1)
        b["ver"] += 1


def add_item(b, item):
    """Una tarjeta de fórmula reconocida en la página actual."""
    with _lock:
        b["seq"] = b.get("seq", 0) + 1
        item = dict(item, n=b["seq"], id=str(item.get("id") or f"f{b['seq']}"))
        b["pages"][b["page"]]["items"].append(item)
        del b["pages"][b["page"]]["items"][:-60]
        b["ver"] += 1
        return item


def snapshot(b, page=None):
    i = b["page"] if page is None else page
    pg = b["pages"][i]
    return {"ver": b["ver"], "page": i, "pages": len(b["pages"]), "strokes": pg["strokes"], "items": pg["items"]}


# ============================================================================ RECONOCER
def recognize_prompt():
    return """Esta imagen es una zona de una pizarra donde un docente escribió a mano con lápiz digital (trazos claros sobre fondo oscuro).
Reconoce lo que escribió. Responde SOLO un JSON:
{"latex": "lo escrito en LaTeX (sin $)", "plano": "en texto plano: 3/4 + 1/2 = 5/4, y = x^2 - 4",
 "tipo": "ecuacion" | "igualdad" (una cuenta con resultado, sin incógnita) | "funcion" (y = … o f(x) = …) | "expresion" | "texto",
 "texto": "si es texto (no matemáticas), lo que dice"}
Si no se entiende, "tipo": "texto" y "texto": ""."""


def clean_recognized(d):
    d = d if isinstance(d, dict) else {}
    tipo = str(d.get("tipo") or "").lower().strip()
    tipo = tipo if tipo in ("ecuacion", "igualdad", "funcion", "expresion", "texto") else "texto"
    return {"latex": str(d.get("latex") or "").strip().strip("$")[:300], "plano": re.sub(r"\s+", " ", str(d.get("plano") or "")).strip()[:200],
            "tipo": tipo, "texto": str(d.get("texto") or "").strip()[:200]}


def _sides(s):
    s = s.replace("≈", "=")
    if s.count("=") != 1:
        return None
    a, b = s.split("=")
    return (a.strip(), b.strip()) if a.strip() and b.strip() else None


def verify(rec):
    """→ {"ok": True|False|None, "nota": "…", "correcto": "…"} según el tipo."""
    import sympy
    plano = rec["plano"]
    try:
        if rec["tipo"] in ("igualdad", "expresion") and _sides(plano):
            a, b = _sides(plano)
            ea, eb = verificar._parse(a), verificar._parse(b)
            if not (ea.free_symbols or eb.free_symbols):
                ok = verificar._eq(ea, eb)
                val = verificar._pretty(sympy.nsimplify(sympy.simplify(ea)))
                return {"ok": ok, "nota": "La cuenta está bien." if ok else f"Ojo: da {val}.", "correcto": val}
            ok = verificar._eq(ea, eb)
            return {"ok": ok, "nota": "Las dos expresiones son iguales." if ok else "Las dos expresiones no son iguales.", "correcto": ""}
        if rec["tipo"] == "ecuacion" and _sides(plano):
            c = verificar.check({"tipo": "ecuacion", "expr": plano, "resultado": "x = 0", "variable": _var(plano)})
            if c["correcto"]:
                return {"ok": None, "nota": "Solución: " + c["correcto"], "correcto": c["correcto"]}
        if rec["tipo"] == "expresion" and plano:
            e = verificar._parse(plano)
            simp = sympy.factor(sympy.simplify(e)) if e.free_symbols else sympy.nsimplify(sympy.simplify(e))
            return {"ok": None, "nota": "= " + verificar._pretty(simp), "correcto": verificar._pretty(simp)}
    except Exception:
        pass
    return {"ok": None, "nota": "", "correcto": ""}


def _var(s):
    for v in "xyzabmntk":
        if re.search(rf"(?<![a-z]){v}(?![a-z])", s.lower()):
            return v
    return "x"


def function_of(rec):
    """La función de x para graficar («y = x^2 - 4» o «f(x) = …»), o ""."""
    m = re.match(r"^\s*(?:y|f\s*\(\s*x\s*\)|g\s*\(\s*x\s*\))\s*=\s*(.+)$", rec["plano"])
    if rec["tipo"] == "funcion" and m:
        return m.group(1)
    return m.group(1) if m and "x" in m.group(1) else ""


def sample(fx, a=-6.0, b=6.0, n=160):
    """Puntos de la gráfica [[x, y|None]] (None donde no existe), leída con la lista cerrada de símbolos."""
    import sympy
    e = verificar._parse(fx)
    x = sympy.Symbol("x")
    if e.free_symbols - {x}:
        raise ValueError("la función tiene otras letras además de x")
    f = sympy.lambdify(x, e, "math")
    pts = []
    for i in range(n + 1):
        xv = a + (b - a) * i / n
        try:
            y = float(f(xv))
            pts.append([round(xv, 4), round(y, 4) if math.isfinite(y) and abs(y) < 1e6 else None])
        except Exception:
            pts.append([round(xv, 4), None])
    return pts


# ============================================================================ PDF
def render_pdf(b, path, title="Pizarra", W=1600, H=900):
    """Cada página a una imagen (trazos y fórmulas en texto) y todas a un PDF."""
    from PIL import Image, ImageDraw
    import animar
    pages = []
    for i, pg in enumerate(b["pages"]):
        if not pg["strokes"] and not pg["items"] and len(b["pages"]) > 1:
            continue
        im = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(im)
        for s in pg["strokes"]:
            pts = [(p[0] * W, p[1] * H) for p in s["p"]]
            col = _ink(s["c"])
            if len(pts) == 1:
                x, y = pts[0]
                r = s["w"] / 2 + 1
                d.ellipse([x - r, y - r, x + r, y + r], fill=col)
            elif pts:
                d.line(pts, fill=col, width=max(2, int(s["w"] * W / 1280)), joint="curve")
        for it in pg["items"]:
            x, y = it.get("x", 0.05) * W, it.get("y", 0.05) * H
            txt = animar.pretty(it.get("plano") or it.get("texto") or "")
            d.text((x, y), txt, font=animar.font("math", 34), fill=(20, 60, 140))
            if it.get("nota"):
                d.text((x, y + 42), it["nota"], font=animar.font("regular", 22), fill=(46, 139, 87) if it.get("ok") is not False else (192, 57, 43))
            g = it.get("graph")
            if g:
                _draw_graph(d, g, (x, y + 76, x + 420, y + 336))
        d.text((24, H - 36), f"{title} · página {i + 1}", font=animar.font("regular", 20), fill=(150, 150, 150))
        pages.append(im)
    if not pages:
        pages = [Image.new("RGB", (W, H), (255, 255, 255))]
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    pages[0].save(path, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])
    return path


def _ink(c):
    """En el PDF (fondo blanco) los colores claros se oscurecen para que se lean."""
    m = {"#ecf0f1": (25, 25, 25), "#ffdd55": (196, 140, 0), "#58c4dd": (20, 110, 170), "#83c167": (40, 130, 60), "#fc6255": (200, 50, 40),
         "#ff80ab": (200, 60, 120)}
    if c in m:
        return m[c]
    try:
        r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
        return (r // 2, g // 2, b // 2) if r + g + b > 600 else (r, g, b)
    except (ValueError, IndexError):
        return (25, 25, 25)


def _draw_graph(d, pts, box):
    x0, y0, x1, y1 = box
    good = [p for p in pts if p[1] is not None]
    if not good:
        return
    lo, hi = max(-50, min(p[1] for p in good)), min(50, max(p[1] for p in good))
    lo, hi = min(lo, 0), max(hi, 0)
    if hi - lo < 1:
        hi += 1
    a, b = pts[0][0], pts[-1][0]
    X = lambda v: x0 + (v - a) / (b - a) * (x1 - x0)
    Y = lambda v: y1 - (v - lo) / (hi - lo) * (y1 - y0)
    d.rectangle(box, outline=(200, 200, 200))
    if a <= 0 <= b:
        d.line([(X(0), y0), (X(0), y1)], fill=(160, 160, 160))
    d.line([(x0, Y(0)), (x1, Y(0))], fill=(160, 160, 160))
    seg = []
    for p in pts:
        if p[1] is None or not lo <= p[1] <= hi:
            if len(seg) > 1:
                d.line(seg, fill=(196, 140, 0), width=3)
            seg = []
        else:
            seg.append((X(p[0]), Y(p[1])))
    if len(seg) > 1:
        d.line(seg, fill=(196, 140, 0), width=3)
