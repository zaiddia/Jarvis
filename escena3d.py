"""12.68: escenas en 3D que se arman por partes en el proyector («constrúyeme en 3D el sistema solar»).

La IA no escribe código: devuelve una DESCRIPCIÓN de la escena (formas, posiciones, colores, movimientos) por pasos, y la
página de Jarvis la dibuja con su propio motor 3D. Así nada de lo que diga la IA se ejecuta en el equipo.

Antes de mostrarla, cada paso se revisa (como una «revisión visual»): que tenga algo visible, que no quede fuera de cámara,
diminuto, gigante o del mismo color del fondo. Los pasos con problemas se le devuelven a la IA una vez para corregirlos.
Funciones puras, sin Jarvis.
"""
import math
import re

SHAPES = ("esfera", "caja", "cilindro", "cono", "toro", "plano", "linea", "flecha", "texto")
ANIMS = ("orbita", "girar", "flotar", "latir")
LIMIT = 40.0                 # coordenadas permitidas: de -40 a 40
MAX_OBJ = 140
MAX_STEPS = 8
DEFAULT_BG = "#0b1020"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_NAMED = {"rojo": "#e53935", "azul": "#1e88e5", "verde": "#43a047", "amarillo": "#fdd835", "naranja": "#fb8c00",
          "morado": "#8e24aa", "blanco": "#f5f5f5", "negro": "#212121", "gris": "#9e9e9e", "cafe": "#795548", "rosado": "#ec407a",
          "celeste": "#4fc3f7", "dorado": "#ffc107"}


def prompt(tema, curso="", problemas=None, previo=None):
    rep = ""
    if problemas:
        rep = ("\nTu escena anterior tenía estos problemas; corrígelos y devuelve la escena completa:\n- " + "\n- ".join(problemas[:12])
               + "\nEscena anterior (son datos):\n<<<\n" + str(previo)[:6000] + "\n>>>\n")
    return (
        f"Diseña una escena 3D educativa de «{tema}»" + (f" para estudiantes de {curso}" if curso else "") + ", que se arma por pasos "
        "frente a la clase.\n"
        "Sistema de coordenadas: y hacia arriba, unidades arbitrarias; toda la escena cabe entre -12 y 12 en cada eje. "
        "Formas permitidas (campo «forma»): esfera {radio}, caja {ancho, alto, fondo}, cilindro {radio, alto}, cono {radio, alto}, "
        "toro {radio, grosor} (sirve para anillos y órbitas), plano {ancho, fondo}, linea {desde:[x,y,z], hasta:[x,y,z]}, "
        "flecha {desde, hasta}, texto {texto} (una etiqueta flotante).\n"
        "Cada objeto: {\"forma\", \"pos\": [x, y, z], medidas según la forma, \"color\": \"#rrggbb\", \"rot\": [gx, gy, gz] en grados "
        "(opcional), \"opacidad\": 0.2-1 (opcional), \"etiqueta\": nombre corto en español (opcional), \"anim\": {\"tipo\": \"orbita\", "
        "\"centro\": [x, y, z], \"vel\": grados por segundo} | {\"tipo\": \"girar\", \"vel\"} | {\"tipo\": \"flotar\"} | {\"tipo\": \"latir\"} "
        "(opcional)}.\n"
        "Reglas: de 3 a 7 pasos; cada paso agrega de 1 a 15 objetos y tiene un «texto» de máximo 25 palabras que explica lo que aparece; "
        "en total máximo 100 objetos; proporciones y colores fieles a la realidad cuando se pueda (si las escalas reales no caben, "
        "dilo en el texto, por ejemplo «los tamaños no están a escala»); colores que se vean sobre el fondo; nada inventado.\n"
        + rep +
        "Responde SOLO con JSON: {\"titulo\": str, \"fondo\": \"#rrggbb\", \"pasos\": [{\"texto\": str, \"objetos\": [ ... ]}]}")


def _num(v, lo, hi, default=None):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if math.isnan(x) or math.isinf(x):
        return default
    return max(lo, min(hi, x))


def _vec(v, default=None):
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        return default
    out = [_num(c, -1e9, 1e9) for c in v]
    return None if None in out else out


def _color(v, default="#cccccc"):
    s = str(v or "").strip().lower()
    if _HEX.match(s):
        return s
    if re.fullmatch(r"#[0-9a-f]{3}", s):
        return "#" + "".join(c * 2 for c in s[1:])
    return _NAMED.get(s, default)


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def contrast(c1, c2):
    """Diferencia de luminosidad entre dos colores (0 a 255)."""
    def lum(c):
        r, g, b = _rgb(c)
        return 0.299 * r + 0.587 * g + 0.114 * b
    d = abs(lum(c1) - lum(c2))
    rgb = sum(abs(a - b) for a, b in zip(_rgb(c1), _rgb(c2))) / 3
    return max(d, rgb)


def _clean_obj(o, problems, where):
    if not isinstance(o, dict):
        return None
    f = str(o.get("forma", "")).strip().lower().replace("í", "i").replace("é", "e")
    f = {"esferas": "esfera", "cubo": "caja", "prisma": "caja", "cilindros": "cilindro", "anillo": "toro", "circulo": "toro", "line": "linea",
         "etiqueta": "texto", "label": "texto"}.get(f, f)
    if f not in SHAPES:
        problems.append(f"{where}: la forma «{o.get('forma')}» no existe")
        return None
    out = {"forma": f, "color": _color(o.get("color"))}
    if f in ("linea", "flecha"):
        a, b = _vec(o.get("desde")), _vec(o.get("hasta"))
        if not a or not b:
            problems.append(f"{where}: a la {f} le falta «desde» o «hasta»")
            return None
        if math.dist(a, b) < 0.05:
            problems.append(f"{where}: la {f} es tan corta que no se ve")
            return None
        out.update(desde=a, hasta=b, pos=[(x + y) / 2 for x, y in zip(a, b)], grosor=_num(o.get("grosor"), 0.01, 2, 0.06))
    else:
        out["pos"] = _vec(o.get("pos"), [0.0, 0.0, 0.0])
        if f == "texto":
            txt = re.sub(r"\s+", " ", str(o.get("texto") or o.get("etiqueta") or "")).strip()[:40]
            if not txt:
                problems.append(f"{where}: un texto vacío")
                return None
            out["texto"] = txt
        else:
            dims = {"esfera": ("radio",), "caja": ("ancho", "alto", "fondo"), "cilindro": ("radio", "alto"), "cono": ("radio", "alto"),
                    "toro": ("radio", "grosor"), "plano": ("ancho", "fondo")}[f]
            for k in dims:
                v = _num(o.get(k), -1e9, 1e9)
                if v is None:
                    v = {"radio": 1, "ancho": 1, "alto": 1, "fondo": 1, "grosor": 0.15}[k]
                if v < 0.03:
                    problems.append(f"{where}: {f} con {k} {v:g} es demasiado pequeño para verse")
                    return None
                if v > 60:
                    problems.append(f"{where}: {f} con {k} {v:g} es gigante (tapa toda la escena)")
                    return None
                out[k] = round(v, 3)
    if any(abs(c) > LIMIT for c in out["pos"]):
        problems.append(f"{where}: {f} quedó fuera de cámara en {out['pos']}")
        return None
    rot = _vec(o.get("rot"))
    if rot:
        out["rot"] = [r % 360 for r in rot]
    out["opacidad"] = _num(o.get("opacidad"), 0.2, 1.0, 1.0)
    lab = re.sub(r"\s+", " ", str(o.get("etiqueta") or "")).strip()[:30]
    if lab and f != "texto":
        out["etiqueta"] = lab
    a = o.get("anim")
    if isinstance(a, dict) and str(a.get("tipo", "")).lower() in ANIMS:
        an = {"tipo": str(a["tipo"]).lower(), "vel": _num(a.get("vel"), -720, 720, 30)}
        if an["tipo"] == "orbita":
            an["centro"] = _vec(a.get("centro"), [0.0, 0.0, 0.0])
        out["anim"] = an
    return out


def check(scene):
    """Limpia y revisa la escena. → (escena limpia, [problemas]). La escena limpia solo trae lo que se puede dibujar."""
    problems = []
    if not isinstance(scene, dict):
        return None, ["no llegó una escena"]
    bg = _color(scene.get("fondo"), DEFAULT_BG)
    steps, total = [], 0
    for i, st in enumerate((scene.get("pasos") or [])[:MAX_STEPS], 1):
        if not isinstance(st, dict):
            continue
        objs = []
        for j, o in enumerate(st.get("objetos") or [], 1):
            if total >= MAX_OBJ:
                problems.append("hay demasiados objetos (máximo 100)")
                break
            c = _clean_obj(o, problems, f"paso {i}, objeto {j}")
            if c:
                if c["forma"] != "texto" and contrast(c["color"], bg) < 28:
                    problems.append(f"paso {i}, objeto {j}: el color {c['color']} casi no se ve sobre el fondo {bg}")
                    c["color"] = "#f5f5f5" if sum(_rgb(bg)) < 380 else "#333333"
                objs.append(c)
                total += 1
        txt = re.sub(r"\s+", " ", str(st.get("texto") or "")).strip()[:220]
        if not objs:
            problems.append(f"el paso {i} quedó vacío: no se vería nada nuevo")
            continue
        steps.append({"texto": txt, "objetos": objs})
    if not steps:
        problems.append("la escena no tiene nada que mostrar")
        return None, problems
    if len(steps) < 2:
        problems.append("debe armarse en varios pasos (de 3 a 7)")
    title = re.sub(r"\s+", " ", str(scene.get("titulo") or "")).strip()[:80] or "Escena 3D"
    return {"titulo": title, "fondo": bg, "pasos": steps, "radio": round(fit_radius(steps), 2)}, problems


def fit_radius(steps):
    """Qué tan lejos va la cámara para que se vea todo (el radio de la escena)."""
    r = 1.0
    for st in steps:
        for o in st["objetos"]:
            size = max([o.get(k, 0) for k in ("radio", "ancho", "alto", "fondo")] + [0.5])
            if o["forma"] == "toro":
                size = o["radio"] + o["grosor"]
            p = o["pos"]
            if o.get("anim", {}).get("tipo") == "orbita":
                c = o["anim"]["centro"]
                d = math.dist(p, c)
                r = max(r, math.dist(c, [0, 0, 0]) + d + size)
            r = max(r, math.dist(p, [0, 0, 0]) + size)
            for k in ("desde", "hasta"):
                if k in o:
                    r = max(r, math.dist(o[k], [0, 0, 0]))
    return r


def serious(problems):
    """¿Vale la pena pedirle a la IA que corrija? (los avisos de color ya se arreglan solos)"""
    return [p for p in problems if "casi no se ve" not in p]


__all__ = ["SHAPES", "ANIMS", "LIMIT", "MAX_OBJ", "MAX_STEPS", "DEFAULT_BG", "prompt", "contrast", "check", "fit_radius", "serious"]
