"""Hojas de respuesta que se califican con una foto (10.5). Lógica pura: dibuja las hojas y las lee.

Cada hoja (A4, 150 ppp) tiene cuatro cuadros negros en las esquinas (para enderezar la foto), una barra de 24
casillas con el código de la evaluación y el número del estudiante (14 + 7 bits + 3 de control) y la cuadrícula de
burbujas (hasta 50 preguntas de 2 a 5 opciones). Para leerla: se buscan los cuatro cuadros, se endereza la foto y se
mide qué tan rellena está cada burbuja. Sin internet y sin IA. Necesita OpenCV (opencv-python-headless) y numpy.
"""
import os

W, H = 1240, 1754
F = 70                                                # lado de los cuadros de las esquinas
M = 60                                                # margen hasta los cuadros
CORNERS = [(M + F / 2, M + F / 2), (W - M - F / 2, M + F / 2), (W - M - F / 2, H - M - F / 2), (M + F / 2, H - M - F / 2)]
ID_Y, ID_X0, ID_CELL, ID_GAP, ID_N = 430, 190, 30, 8, 24
GRID_Y, ROW_H, PER_COL = 560, 44, 25
COL_X = (150, 680)
BUB_R, BUB_DX, BUB_X0 = 15, 62, 90                    # radio, separación y desplazamiento de la primera burbuja
LETTERS = "ABCDE"
MAX_Q = 50


def id_bits(code, student):
    """14 bits del código + 7 del estudiante + 3 de control (suma de unos módulo 8)."""
    code, student = (int(code) & 0x3FFF) or 1, int(student) & 0x7F
    bits = [(code >> (13 - i)) & 1 for i in range(14)] + [(student >> (6 - i)) & 1 for i in range(7)]
    chk = sum(bits) % 8
    return bits + [(chk >> (2 - i)) & 1 for i in range(3)]


def decode_bits(bits):
    if len(bits) != ID_N:
        return None
    code = int("".join(map(str, bits[:14])), 2)
    student = int("".join(map(str, bits[14:21])), 2)
    chk = int("".join(map(str, bits[21:])), 2)
    return (code, student) if code and sum(bits[:21]) % 8 == chk else None      # código 0 = hoja sin leer


def bubble_xy(q, opt):
    """Centro de la burbuja (pregunta q desde 0, opción opt desde 0)."""
    col, row = divmod(q, PER_COL)
    return COL_X[col] + BUB_X0 + opt * BUB_DX, GRID_Y + row * ROW_H + ROW_H / 2


def id_cell(i):
    x = ID_X0 + i * (ID_CELL + ID_GAP)
    return x, ID_Y, x + ID_CELL, ID_Y + ID_CELL


# ----------------------------------------------------------------------------- dibujar
def _font(size, bold=False):
    from PIL import ImageFont
    for name in (("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("arial.ttf", "DejaVuSans.ttf")):
        for d in ("", "C:/Windows/Fonts/", "/usr/share/fonts/truetype/dejavu/"):
            try:
                return ImageFont.truetype(d + name, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def draw_sheet(code, student, n_q, n_opt, title="", course="", name="", institution="", fill=None):
    """Una hoja como imagen PIL. fill: {pregunta: opción} para pruebas (burbujas rellenas)."""
    from PIL import Image, ImageDraw
    n_q, n_opt = max(1, min(MAX_Q, n_q)), max(2, min(5, n_opt))
    im = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(im)
    for cx, cy in CORNERS:
        d.rectangle([cx - F / 2, cy - F / 2, cx + F / 2, cy + F / 2], fill=0)
    f_t, f_n, f_s, f_b = _font(34, True), _font(30, True), _font(22), _font(18, True)
    d.text((M + F + 30, M + 4), (institution or "Hoja de respuestas")[:60], font=f_s, fill=0)
    d.text((M + F + 30, M + 36), (title or "Evaluación")[:48], font=f_t, fill=0)
    d.text((150, 230), f"Estudiante: {name}" if name else "Estudiante: _______________________________", font=f_n, fill=0)
    d.text((150, 285), f"Curso: {course}" + (f"     N.º {student:02d}" if student else ""), font=f_s, fill=0)
    d.text((150, 330), "Rellena por completo un solo círculo por pregunta, con lápiz o lapicero oscuro. No dobles la hoja.",
           font=f_s, fill=0)
    d.text((150, 362), "Para calificar: foto de toda la hoja, derecha y con buena luz (que se vean los 4 cuadros negros).", font=f_s, fill=0)
    for i, b in enumerate(id_bits(code, student)):
        x0, y0, x1, y1 = id_cell(i)
        d.rectangle([x0, y0, x1, y1], fill=0 if b else 255, outline=0, width=2)
    d.text((ID_X0, ID_Y + ID_CELL + 6), f"Código {code:05d}-{student:02d}", font=_font(16), fill=0)
    for q in range(n_q):
        x, y = bubble_xy(q, 0)
        d.text((x - BUB_X0 + 4, y - 13), f"{q + 1:>2}", font=f_b, fill=0)
        for o in range(n_opt):
            bx, by = bubble_xy(q, o)
            d.ellipse([bx - BUB_R, by - BUB_R, bx + BUB_R, by + BUB_R], outline=0, width=2)
            if fill and fill.get(q) == o:
                d.ellipse([bx - BUB_R + 2, by - BUB_R + 2, bx + BUB_R - 2, by + BUB_R - 2], fill=30)
            else:
                d.text((bx - 6, by - 11), LETTERS[o], font=f_b, fill=110)
    return im


def sheets_pdf(path, code, students, n_q, n_opt, title="", course="", institution="", extra_blank=3):
    """PDF con una hoja por estudiante [(número, nombre)] y algunas en blanco (con el número 0 para escribir el nombre)."""
    pages = [draw_sheet(code, num, n_q, n_opt, title, course, name, institution).convert("RGB") for num, name in students]
    pages += [draw_sheet(code, 0, n_q, n_opt, title, course, "", institution).convert("RGB") for _ in range(extra_blank)]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    pages[0].save(path, "PDF", resolution=150, save_all=True, append_images=pages[1:])
    return path


# ----------------------------------------------------------------------------- leer
class ReadError(ValueError):
    pass


def _order(pts):
    import numpy as np
    pts = np.array(pts, dtype="float32")
    s, dlt = pts.sum(1), pts[:, 0] - pts[:, 1]
    return np.array([pts[s.argmin()], pts[dlt.argmax()], pts[s.argmax()], pts[dlt.argmin()]], dtype="float32")


def find_corners(gray):
    """Los centros de los 4 cuadros negros (en el orden: arriba-izq., arriba-der., abajo-der., abajo-izq.)."""
    import cv2
    import numpy as np
    h, w = gray.shape
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    binv = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 10)
    _, otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    cands = []
    for b in (otsu, binv):
        cnts, _ = cv2.findContours(b, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            area = cv2.contourArea(c)
            if area < h * w * 0.0004 or area > h * w * 0.02:
                continue
            x, y, cw, ch = cv2.boundingRect(c)
            if not 0.7 < cw / float(ch) < 1.4 or area / float(cw * ch) < 0.8:
                continue
            approx = cv2.approxPolyDP(c, 0.06 * cv2.arcLength(c, True), True)
            if len(approx) != 4:
                continue
            roi = gray[y:y + ch, x:x + cw]
            if roi.size == 0 or roi.mean() > 110:      # relleno de negro, no un contorno
                continue
            cands.append((x + cw / 2, y + ch / 2, area))
        if len(cands) >= 4:
            break
    if len(cands) < 4:
        raise ReadError("no veo los 4 cuadros negros de las esquinas: toma la foto de toda la hoja, derecha y con buena luz")
    big = max(a for _, _, a in cands)
    cands = [(x, y) for x, y, a in cands if a >= big * 0.35]
    if len(cands) < 4:
        raise ReadError("no veo los 4 cuadros negros de las esquinas: toma la foto de toda la hoja, derecha y con buena luz")
    quad = _order(cands)
    sides = [np.linalg.norm(quad[i] - quad[(i + 1) % 4]) for i in range(4)]
    if min(sides) < max(sides) * 0.45:
        raise ReadError("la hoja sale muy torcida o incompleta: tómala de frente")
    return quad


def warp(gray, quad):
    import cv2
    import numpy as np
    m = cv2.getPerspectiveTransform(quad, np.array(CORNERS, dtype="float32"))
    return cv2.warpPerspective(gray, m, (W, H), flags=cv2.INTER_LINEAR, borderValue=255)


def _ink(binv, cx, cy, r):
    import numpy as np
    y0, y1, x0, x1 = int(cy - r), int(cy + r) + 1, int(cx - r), int(cx + r) + 1
    roi = binv[max(0, y0):y1, max(0, x0):x1]
    if roi.size == 0:
        return 0.0
    yy, xx = np.ogrid[:roi.shape[0], :roi.shape[1]]
    mask = (yy - (cy - max(0, y0))) ** 2 + (xx - (cx - max(0, x0))) ** 2 <= r * r
    return float(roi[mask].mean() / 255.0) if mask.any() else 0.0


def read_image(data, n_q=None, n_opt=None):
    """Lee la foto (bytes o ruta). → {"code", "student", "answers": [opción|None|"multi"], "ink": [[…]]}."""
    import cv2
    import numpy as np
    if isinstance(data, (bytes, bytearray)):
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    else:
        img = cv2.imread(str(data), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ReadError("no pude abrir la imagen")
    scale = 1800.0 / max(img.shape)
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    quad = find_corners(img)
    ident = None
    for shift in range(4):                             # la foto puede venir de lado o al revés
        flat = warp(img, np.roll(quad, -shift, axis=0))
        binv = cv2.adaptiveThreshold(cv2.GaussianBlur(flat, (3, 3), 0), 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 41, 12)
        bits = []
        for i in range(ID_N):
            x0, y0, x1, y1 = id_cell(i)
            bits.append(1 if binv[y0 + 6:y1 - 5, x0 + 6:x1 - 5].mean() / 255.0 > 0.5 else 0)
        ident = decode_bits(bits)
        if ident is not None:
            break
    if ident is None:
        raise ReadError("no pude leer el código de la hoja: que no quede tapado ni con sombra")
    n_q = n_q or MAX_Q
    n_opt = n_opt or 5
    answers, inks = [], []
    for q in range(n_q):
        ink = [_ink(binv, *bubble_xy(q, o), BUB_R - 4) for o in range(n_opt)]
        inks.append([round(x, 2) for x in ink])
        order = sorted(range(n_opt), key=lambda o: -ink[o])
        top, second = ink[order[0]], ink[order[1]] if n_opt > 1 else 0.0
        if top < 0.42:
            answers.append(None)                       # en blanco
        elif second >= 0.42 and top - second < 0.25:
            answers.append("multi")                    # dos o más rellenas
        else:
            answers.append(order[0])
    return {"code": ident[0], "student": ident[1], "answers": answers, "ink": inks}


# ----------------------------------------------------------------------------- calificar
def grade(answers, key, scale_min=1.0, scale_max=5.0):
    """→ {"aciertos", "total", "nota", "detalle": [True/False/None…]} (nota lineal de 1,0 a 5,0)."""
    det = []
    for i, k in enumerate(key):
        a = answers[i] if i < len(answers) else None
        det.append(None if a is None else (a == k))
    ok = sum(1 for x in det if x)
    total = len(key)
    nota = round(scale_min + (scale_max - scale_min) * ok / total, 1) if total else None
    return {"aciertos": ok, "total": total, "nota": nota, "detalle": det}


def item_analysis(results, key, n_opt):
    """Por pregunta: % de acierto y la opción errada más escogida. results: [{"answers": […]}]."""
    out = []
    n = len(results)
    for q, k in enumerate(key):
        counts = [0] * n_opt
        blank = 0
        for r in results:
            a = r["answers"][q] if q < len(r["answers"]) else None
            if isinstance(a, int) and a < n_opt:
                counts[a] += 1
            else:
                blank += 1
        wrong = [(c, o) for o, c in enumerate(counts) if o != k]
        top_wrong = max(wrong) if wrong else (0, None)
        out.append({"q": q, "acierto": round(100 * counts[k] / n) if n else 0, "clave": k, "conteo": counts, "blanco": blank,
                    "distractor": top_wrong[1] if top_wrong[0] else None, "distractor_n": top_wrong[0]})
    return out
