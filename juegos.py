"""Juegos de matemáticas para imprimir (12.12): bingo, dominó y parejas (memoria), en PDF. Lógica pura.

Los ejercicios de aritmética se generan aquí mismo (sin IA, siempre correctos y con respuestas distintas): tablas,
enteros, fracciones, potencias, raíces, porcentajes y ecuaciones. Para otros temas, la IA propone las parejas
(pregunta → respuesta corta) y Jarvis revisa que las respuestas no se repitan.
"""
import math
import random
import re
import unicodedata
from fractions import Fraction

TOPICS = {
    "multiplicacion": r"multiplicaci|tablas?\b|producto",
    "enteros": r"entero|negativ|suma.*resta|resta.*suma|positivo",
    "fracciones": r"fracci|quebrad",
    "potencias": r"potencia|exponente|cuadrado|cubo",
    "raices": r"raic|radicac|raiz",
    "porcentajes": r"porcentaj|por ciento|%",
    "ecuaciones": r"ecuaci|despej|incognita",
    "division": r"divisi|cociente",
}
GAMES = {"bingo": "Bingo", "domino": "Dominó", "parejas": "Parejas (memoria)"}


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def topic_of(text):
    t = norm(text)
    return next((k for k, rx in TOPICS.items() if re.search(rx, t)), "")


def game_of(text):
    t = norm(text)
    if "domino" in t:
        return "domino"
    if re.search(r"pareja|memoria|memorama|concentrese", t):
        return "parejas"
    return "bingo" if "bingo" in t else ""


def _frac(f):
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def _one(topic, rnd, level):
    """(ejercicio, respuesta) de ese tema."""
    big = level >= 2
    if topic == "multiplicacion":
        a, b = rnd.randint(2, 12 if not big else 15), rnd.randint(2, 12)
        return f"{a} × {b}", str(a * b)
    if topic == "division":
        b, q = rnd.randint(2, 12), rnd.randint(2, 30 if big else 25)
        return f"{b * q} ÷ {b}", str(q)
    if topic == "enteros":
        a, b = rnd.randint(-20, 20), rnd.randint(-20, 20)
        op = rnd.choice("+-×") if big else rnd.choice("+-")
        if op == "×":
            a, b = rnd.randint(-9, 9), rnd.randint(-9, 9)
            return f"({a}) × ({b})", str(a * b)
        return (f"({a}) + ({b})", str(a + b)) if op == "+" else (f"({a}) − ({b})", str(a - b))
    if topic == "fracciones":
        d1, d2 = rnd.choice([2, 3, 4, 5, 6, 8, 10]), rnd.choice([2, 3, 4, 5, 6, 8, 10])
        f1, f2 = Fraction(rnd.randint(1, d1 - 1) if d1 > 1 else 1, d1), Fraction(rnd.randint(1, d2 - 1) if d2 > 1 else 1, d2)
        kind = rnd.choice(["+", "×", "simp"] if big else ["+", "simp"])
        if kind == "simp":
            k, f = rnd.randint(2, 5), f1
            return f"Simplifica {f.numerator * k}/{f.denominator * k}", _frac(f)
        return (f"{_frac(f1)} + {_frac(f2)}", _frac(f1 + f2)) if kind == "+" else (f"{_frac(f1)} × {_frac(f2)}", _frac(f1 * f2))
    if topic == "potencias":
        sup = {2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶", 7: "⁷"}
        kind = rnd.random()
        if kind < 0.6:
            b, e = rnd.randint(2, 20), 2
        elif kind < 0.85:
            b, e = rnd.randint(2, 10), 3
        else:
            b, e = rnd.choice([2, 2, 3]), rnd.randint(4, 7)
        if b == 3 and e > 5:
            e = 4
        return f"{b}{sup[e]}", str(b ** e)
    if topic == "raices":
        if rnd.random() < 0.8 or not big:
            r = rnd.randint(2, 25)
            return f"√{r * r}", str(r)
        r = rnd.randint(2, 10)
        return f"∛{r ** 3}", str(r)
    if topic == "porcentajes":
        p = rnd.choice([10, 20, 25, 50, 75, 5, 15, 30, 40])
        n = rnd.choice([20, 40, 60, 80, 100, 120, 200, 300, 400, 500, 600, 800, 1000])
        return f"{p} % de {n}", str(int(n * p / 100)) if (n * p) % 100 == 0 else str(n * p / 100).replace(".", ",")
    if topic == "ecuaciones":
        x, a = rnd.randint(-12 if big else -6, 18), rnd.randint(2, 9)
        b = rnd.randint(-15, 15)
        c = a * x + b
        bs = f"+ {b}" if b >= 0 else f"− {-b}"
        return f"{a}x {bs} = {c}", f"x = {x}"
    return _one(rnd.choice(list(TOPICS)), rnd, level)


def generate(topic, n, seed=None, level=1):
    """n parejas (ejercicio, respuesta) con respuestas TODAS distintas. → lista (puede traer menos si el tema no da más)."""
    rnd = random.Random(seed)
    out, seen = [], set()
    tries = 0
    while len(out) < n and tries < n * 80:
        tries += 1
        q, a = _one(topic or "", rnd, level)
        if a not in seen:
            seen.add(a)
            out.append((q, a))
    return out


def ai_prompt(tema, n, grado=""):
    return (f"Crea {n} parejas para un juego de mesa de clase sobre «{tema}»" + (f" para grado {grado}" if grado else "") +
            ": cada una es una pregunta o ejercicio corto y su respuesta MUY corta (máximo 3 palabras o un número). Todas las respuestas "
            "deben ser distintas entre sí. Responde SOLO JSON: {\"parejas\": [{\"pregunta\": str, \"respuesta\": str}]}.")


def ai_validate(d, n):
    out, seen = [], set()
    for p in ((d or {}).get("parejas") or []) if isinstance(d, dict) else []:
        q, a = str(p.get("pregunta") or "").strip()[:90], str(p.get("respuesta") or "").strip()[:24]
        if q and a and norm(a) not in seen:
            seen.add(norm(a))
            out.append((q, a))
    return out[:n]


def bingo_cards(pairs, n_cards, seed=None, size=5):
    """Cartones: cada uno con size×size respuestas distintas (el centro «LIBRE»). Necesita al menos size²−1 respuestas."""
    rnd = random.Random(seed)
    answers = [a for _q, a in pairs]
    need = size * size - 1
    if len(answers) < need:
        raise ValueError(f"para el bingo necesito al menos {need} ejercicios con respuestas distintas")
    cards, seen = [], set()
    for _ in range(n_cards):
        for _t in range(50):
            pick = rnd.sample(answers, need)
            key = tuple(sorted(pick))
            if key not in seen:
                break
        seen.add(key)
        mid = need // 2
        cards.append(pick[:mid] + ["LIBRE"] + pick[mid:])
    return cards


def domino_tiles(pairs):
    """Fichas en cadena cerrada: cada ficha une la respuesta de un ejercicio con el ejercicio siguiente."""
    n = len(pairs)
    return [(pairs[i - 1][1], pairs[i][0]) for i in range(n)]


# ----------------------------------------------------------------------------- PDF
def build_pdf(game, pairs, path, titulo="", curso="", n_cards=30, seed=None):
    from fpdf import FPDF

    import boletin
    d = boletin._Doc(FPDF)
    p = d.pdf
    p.set_auto_page_break(False)
    W = p.w - p.l_margin - p.r_margin
    head = titulo or GAMES[game]

    def header(sub=""):
        p.add_page()
        p.set_xy(p.l_margin, 10)
        d.font(15, True, (14, 40, 66))
        p.cell(W, 8, d.t(head + (f" · {curso}" if curso else "")), new_x="LMARGIN", new_y="NEXT")
        if sub:
            d.font(9.5, False, (90, 100, 112))
            p.multi_cell(W, 5, d.t(sub), new_x="LMARGIN", new_y="NEXT")

    if game == "bingo":
        cards = bingo_cards(pairs, n_cards, seed)
        per_page = 2
        for i, card in enumerate(cards):
            if i % per_page == 0:
                header("Resuelve el ejercicio que dice tu profe y marca la respuesta si la tienes. Gana quien complete una línea (o el cartón).")
            top = 32 + (i % per_page) * 120
            cell = min(W / 5, 22)
            x0 = p.l_margin + (W - cell * 5) / 2
            d.font(11, True)
            p.set_xy(x0, top)
            p.cell(cell * 5, 7, d.t(f"BINGO  ·  Cartón {i + 1}"), align="C")
            for r in range(5):
                for c in range(5):
                    txt = card[r * 5 + c]
                    p.set_xy(x0 + c * cell, top + 9 + r * cell)
                    p.set_draw_color(30, 110, 200)
                    p.set_fill_color(232, 240, 248) if txt == "LIBRE" else p.set_fill_color(255, 255, 255)
                    d.font(9 if len(txt) > 6 else 13, True, (30, 34, 40))
                    p.cell(cell, cell, d.t(txt), border=1, align="C", fill=True)
        header("Para el profe: lee los ejercicios en desorden, en voz alta o en el tablero, y tacha los que ya salieron.")
        d.font(10.5)
        order = list(pairs)
        random.Random(seed).shuffle(order)
        col_w = W / 2
        for k, (q, a) in enumerate(order):
            col, row = k % 2, k // 2
            y = 30 + row * 6.2
            if y > p.h - 15:
                header("Para el profe (continuación)")
                y = 30
            p.set_xy(p.l_margin + col * col_w, y)
            p.cell(col_w, 6, d.t(f"{k + 1}. {q}   →   {a}"))
    elif game == "domino":
        tiles = domino_tiles(pairs)
        random.Random(seed).shuffle(tiles)              # en desorden: si salen en cadena, se resuelve sin pensar
        header("Recorta las fichas. Cada ficha une una respuesta con un ejercicio: pon al lado la ficha cuya respuesta resuelva el ejercicio. "
               "Si todo está bien, la cadena se cierra sola.")
        tw, th = W / 2 - 4, 22
        for k, (a, q) in enumerate(tiles):
            col, row = k % 2, (k // 2) % 10
            if k and k % 20 == 0:
                header("Dominó (continuación)")
            x, y = p.l_margin + col * (tw + 8), 34 + row * (th + 3)
            p.set_draw_color(120, 130, 140)
            p.rect(x, y, tw, th)
            p.line(x + tw / 2, y, x + tw / 2, y + th)
            d.font(13, True)
            p.set_xy(x, y)
            p.cell(tw / 2, th, d.t(a), align="C")
            d.font(11 if len(q) < 14 else 9)
            p.set_xy(x + tw / 2, y)
            p.cell(tw / 2, th, d.t(q), align="C")
    else:
        cards = [(q, "?") for q, _a in pairs] + [(a, "=") for _q, a in pairs]
        random.Random(seed).shuffle(cards)
        header("Recorta las tarjetas y ponlas boca abajo. Por turnos, voltea dos: si el ejercicio y su respuesta coinciden, te quedas con la pareja.")
        cw, ch = W / 4, 26
        for k, (txt, _kind) in enumerate(cards):
            if k and k % 36 == 0:
                header("Parejas (continuación)")
            col, row = k % 4, (k % 36) // 4
            x, y = p.l_margin + col * cw, 32 + row * ch
            p.set_draw_color(150, 160, 170)
            p.rect(x, y, cw, ch)
            d.font(14 if len(txt) < 8 else 11, True)
            p.set_xy(x, y)
            p.cell(cw, ch, d.t(txt), align="C")
        header("Para el profe: las parejas")
        d.font(10.5)
        for k, (q, a) in enumerate(pairs):
            p.set_xy(p.l_margin + (k % 2) * W / 2, 30 + (k // 2) * 6.2)
            p.cell(W / 2, 6, d.t(f"{q}  →  {a}"))
    p.output(path)
    return path


def check_pairs(pairs, topic):
    """Para los temas que genera Jarvis: verifica cada respuesta (por si acaso). → True si todas están bien."""
    for q, a in pairs:
        expr = q.replace("×", "*").replace("÷", "/").replace("−", "-")
        if topic in ("multiplicacion", "division", "enteros") and re.fullmatch(r"[\d\s()+\-*/]+", expr):
            if str(int(eval(expr, {"__builtins__": {}}))) != a:      # noqa: S307 — solo números y operadores, generados aquí
                return False
        if topic == "raices" and q.startswith("√") and int(math.isqrt(int(q[1:]))) != int(a):
            return False
    return True
