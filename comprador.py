"""12.40: comprador inteligente. Lógica pura.

«Quiero comprar un portátil de unos 2 millones para trabajar y ver películas» → busca en tiendas de Colombia, saca de
cada página el producto, su precio y las especificaciones con las PALABRAS EXACTAS de la página (comprobadas con código,
como en la investigación), descarta lo que no se pudo comprobar o se sale del presupuesto, y arma una comparación con pros,
contras y una recomendación para el uso que dijiste.
"""
import datetime
import json
import re
import unicodedata

import confianza
import investigar

STORES = [("Alkosto", "alkosto.com"), ("Ktronix", "ktronix.com"), ("Éxito", "exito.com"), ("Falabella", "falabella.com.co"),
          ("Mercado Libre", "mercadolibre.com.co"), ("Panamericana", "panamericana.com.co"), ("Homecenter", "homecenter.com.co"),
          ("Olímpica", "olimpica.com")]
BUDGET_SLACK = 1.10                 # hasta 10 % por encima del presupuesto todavía se muestra (marcado)


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()


_NUMW = {"un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
         "medio": 0.5}


def money(text):
    """«2 millones», «1,5 millones», «un millón y medio», «800 mil», «$2.199.900», «2'500.000» → pesos (int) o 0."""
    t = norm(text).replace("’", "'")
    m = re.search(r"(\d+(?:[.,]\d+)?|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s*(?:millon(?:es)?|palos?|melones?)"
                  r"(?:\s+y\s+medio)?(?:\s+(?:y\s+)?(\d{1,3})\s*mil)?", t)
    if m:
        n = _NUMW.get(m.group(1)) or float(m.group(1).replace(",", "."))
        v = n * 1_000_000 + (500_000 if "y medio" in m.group(0) else 0) + (int(m.group(2)) * 1000 if m.group(2) else 0)
        return int(v)
    m = re.search(r"(\d{1,3}(?:[.,]\d{3})*|\d+)\s*(?:mil|lucas)\b", t)
    if m:
        return int(re.sub(r"[.,]", "", m.group(1))) * 1000
    m = re.search(r"\$\s*(\d{1,3}(?:[.,'\s]\d{3})+|\d{4,})", t) or re.search(r"\b(\d{1,3}(?:[.'’]\d{3}){1,3})\b", t)
    if m:
        return int(re.sub(r"[^\d]", "", m.group(1)))
    return 0


def cop(n):
    return "$" + f"{int(n):,}".replace(",", ".") if n else "—"


_BUY = re.compile(r"^(?:jarvis[ ,]+)?(?:oye[ ,]+)?(?:quiero|voy a|necesito|pienso|me gustaria|quisiera|estoy pensando en)\s+comprar(?:me)?\s+(.+)$|"
                  r"^(?:jarvis[ ,]+)?(?:ayudame|me ayudas)\s+a\s+(?:comprar|escoger|elegir)\s+(.+)$|"
                  r"^(?:jarvis[ ,]+)?(?:que|cual|cuales)\s+(.+?)\s+(?:me recomiendas|recomiendas|compro|me compro|vale la pena comprar)(?:\s+(.+))?$|"
                  r"^(?:jarvis[ ,]+)?(?:compara|comparame|busca|buscame)\s+(?:los\s+)?precios\s+(?:de\s+)?(.+?)\s+(?:en|entre)\s+(?:las\s+)?tiendas\b(.*)$")
_CHEAP = re.compile(r"\b(?:leche|pan|huevos?|arroz|mercado|comida|almuerzo|domicilio|tinto|cafe|gaseosa|frutas?|verduras?|carne|pollo)\b")


def parse_request(t):
    """→ {"producto", "presupuesto", "uso"} o None. Pide algo que valga la pena comparar (con presupuesto, o un uso)."""
    t = norm(t)
    m = _BUY.match(t)
    if not m:
        return None
    rest = " ".join(g for g in m.groups() if g).strip(" ?.!")
    if _CHEAP.search(rest) and not re.search(r"\b(?:cafetera|nevera|licuadora|freidora|horno|estufa)\b", rest):
        return None
    budget = money(rest)
    uso = ""
    mu = re.search(r"\b(?:para|que sirva para|que me sirva para)\s+(.+)$", rest)
    if mu:
        uso = mu.group(1).strip()
        rest = rest[:mu.start()].strip()
    prod = re.sub(r"\b(?:(?:de|por|con|que cueste|que valga|hasta|maximo|como mucho|unos?|alrededor de|mas o menos)\s+)+"
                  r"(?:\$\s*)?[\d.,']+\s*(?:millon(?:es)?|mil|pesos|lucas|palos?)?(?:\s+y\s+medio)?(?:\s+(?:de\s+)?pesos)?\b", "", rest)
    prod = re.sub(r"\b(?:de|por|hasta)\s+(?:un|una|dos|tres|cuatro|cinco)\s+millon(?:es)?(?:\s+y\s+medio)?\b", "", prod)
    prod = re.sub(r"^(?:un|una|unos|unas|el|la|los|las|mi|un nuevo|una nueva)\s+", "", prod).strip(" ,.")
    prod = re.sub(r"\s+(?:nuevo|nueva)$", "", prod)
    if not prod or len(prod) < 3 or len(prod.split()) > 10:
        return None
    if not budget and not uso and not m.group(3) and not m.group(5):
        return None                                          # «quiero comprar un carro» sin más: no es para comparar todavía
    return {"producto": prod, "presupuesto": budget, "uso": uso}


def with_accents(text, sub):
    """El trozo del texto original (con tildes) que corresponde a «sub» (sin tildes). Si no se encuentra, sub."""
    low = unicodedata.normalize("NFC", str(text)).lower()
    i = norm(low).find(sub)
    return low[i:i + len(sub)] if i >= 0 and len(norm(low)) == len(low) else sub


def queries(req, stores=STORES[:5]):
    p = req["producto"]
    qs = [f"{p} precio site:{dom}" for _name, dom in stores]
    qs.append(f"mejor {p} {req['uso'] or 'calidad precio'} {datetime.date.today().year} reseña Colombia")
    return qs


def store_of(url):
    h = investigar.host(url) if hasattr(investigar, "host") else url
    for name, dom in STORES:
        if dom in str(h):
            return name
    return ""


def extract_prompt(req, sources):
    blocks = []
    for i, s in enumerate(sources, 1):
        if s.get("leida"):
            blocks.append(f"[{i}] {s['titulo']} — {s['fuente']}\n" + confianza.wrap(s.get("texto", "")[:3500], f"PÁGINA {i}"))
    return ("Vas a sacar los PRODUCTOS que se venden en estas páginas de tiendas, para alguien que busca «" + req["producto"] + "»" +
            (f" para {req['uso']}" if req["uso"] else "") + ".\n\n" + "\n\n".join(blocks) +
            "\n\nPara cada producto concreto (marca y modelo) que aparezca con su precio: el nombre, el número de la página, el precio "
            "en pesos, una CITA_PRECIO (de 3 a 25 palabras copiadas LETRA POR LETRA de la página donde está ese precio) y las "
            "especificaciones clave con una CITA_SPECS copiada igual (si no hay, déjala vacía). No inventes nada que no esté en la "
            "página. Máximo 12 productos. Responde SOLO con JSON:\n"
            '{"productos": [{"nombre": "…", "fuente": 1, "precio": 2199900, "cita_precio": "…", "specs": "…", "cita_specs": "…"}]}' + confianza.RULE)


def parse_products(text, n_sources):
    try:
        m = re.search(r"\{.*\}", str(text), re.S)
        d = json.loads(m.group(0) if m else text)
    except Exception:
        return []
    out = []
    for x in (d.get("productos") or [])[:20]:
        if not isinstance(x, dict):
            continue
        try:
            f = int(x.get("fuente"))
        except (TypeError, ValueError):
            continue
        price = x.get("precio")
        price = int(price) if isinstance(price, (int, float)) else money(str(price or ""))
        name = str(x.get("nombre") or "").strip()[:140]
        if name and 1 <= f <= n_sources and price > 0:
            out.append({"nombre": name, "fuente": f, "precio": price, "cita_precio": str(x.get("cita_precio") or "").strip()[:300],
                        "specs": str(x.get("specs") or "").strip()[:400], "cita_specs": str(x.get("cita_specs") or "").strip()[:400]})
    return out


def _digits(s):
    return re.sub(r"\D", "", str(s))


def price_in_page(price, page):
    """¿Aparece ese precio en la página (con puntos, comas o espacios)?"""
    d = str(int(price))
    for m in re.finditer(r"\d[\d.,'\s]{2,14}\d", page):
        if _digits(m.group(0)) == d or _digits(m.group(0)).startswith(d) and len(_digits(m.group(0))) == len(d) + 2:
            return True
    return False


def verify_products(products, sources, budget=0):
    """→ (comprobados, descartados). Un producto vale si su precio está en la página y la cita del precio también."""
    ok, bad, seen = [], [], set()
    for x in products:
        s = sources[x["fuente"] - 1]
        key = (norm(x["nombre"])[:60], x["precio"])
        if key in seen:
            continue
        seen.add(key)
        page = s.get("texto", "")
        if not s.get("leida"):
            bad.append(dict(x, motivo="solo había el resumen del buscador"))
            continue
        if not price_in_page(x["precio"], page) or (x["cita_precio"] and investigar.quote_support(x["cita_precio"], page) == "no"
                                                    and len(x["cita_precio"].split()) >= 4):
            bad.append(dict(x, motivo="el precio no está en la página"))
            continue
        if budget and x["precio"] > budget * BUDGET_SLACK:
            bad.append(dict(x, motivo=f"se pasa del presupuesto ({cop(x['precio'])})"))
            continue
        specs_ok = bool(x["cita_specs"]) and investigar.quote_support(x["cita_specs"], page) != "no"
        ok.append(dict(x, url=s["url"], tienda=store_of(s["url"]) or s.get("fuente", ""), specs=x["specs"] if specs_ok else "",
                       sobre=bool(budget and x["precio"] > budget)))
    ok.sort(key=lambda x: x["precio"])
    return ok, bad


def compare_prompt(req, products):
    lines = [f"{i}. {x['nombre']} — {cop(x['precio'])} en {x['tienda']}" + (f". Especificaciones (comprobadas): {x['specs']}" if x["specs"] else "")
             for i, x in enumerate(products, 1)]
    return ("Ayuda a escoger. La persona busca «" + req["producto"] + "»" + (f" para {req['uso']}" if req["uso"] else "") +
            (f", con un presupuesto de {cop(req['presupuesto'])}" if req["presupuesto"] else "") +
            ". Estos son los productos con precio comprobado en tiendas de Colombia hoy:\n" + "\n".join(lines) +
            "\n\nPara cada uno: 2 o 3 pros y 1 o 2 contras para ESE uso (basados en las especificaciones; si no hay especificaciones, "
            "dilo y no inventes), y una frase de para quién es. Luego el número del que más le conviene y por qué (2 frases), y 3 "
            "consejos para comprar (garantía, qué revisar, cuándo esperar una oferta). En español sencillo. Responde SOLO con JSON:\n"
            '{"productos": [{"n": 1, "pros": ["…"], "contras": ["…"], "para_quien": "…"}], "recomendado": 1, "por_que": "…", "consejos": ["…"]}')


def parse_compare(text, n):
    try:
        m = re.search(r"\{.*\}", str(text), re.S)
        d = json.loads(m.group(0) if m else text)
    except Exception:
        return None
    per = {}
    for x in d.get("productos") or []:
        try:
            k = int(x.get("n"))
        except (TypeError, ValueError, AttributeError):
            continue
        if 1 <= k <= n:
            per[k] = {"pros": [str(p) for p in (x.get("pros") or [])][:4], "contras": [str(p) for p in (x.get("contras") or [])][:3],
                      "para_quien": str(x.get("para_quien") or "")[:200]}
    try:
        rec = int(d.get("recomendado") or 0)
    except (TypeError, ValueError):
        rec = 0
    return {"por": per, "recomendado": rec if 1 <= rec <= n else 0, "por_que": str(d.get("por_que") or "")[:500],
            "consejos": [str(c) for c in (d.get("consejos") or [])][:5]}


def spoken(req, products, cmp_):
    if not products:
        return ""
    rec = products[cmp_["recomendado"] - 1] if cmp_ and cmp_.get("recomendado") else None
    cheap = products[0]
    out = f"Encontré {len(products)} {'opciones' if len(products) != 1 else 'opción'} con precio comprobado"
    out += f", desde {cop(cheap['precio'])} ({cheap['nombre']} en {cheap['tienda']})."
    if rec:
        out += f" Para lo que quieres, te recomiendo {rec['nombre']} por {cop(rec['precio'])} en {rec['tienda']}: {cmp_['por_que']}"
    return out


# ---------------------------------------------------------------- vigilar el precio de uno
def prices_in(page, near, spread=0.4):
    """Los precios de la página cerca del que ya conocemos (±40 %): para ver si bajó sin depender de la IA."""
    found = []
    for m in re.finditer(r"\$\s*(\d{1,3}(?:[.,'\s]\d{3})+)|(\d{1,3}(?:\.\d{3}){1,3})(?!\d)", page):
        v = int(_digits(m.group(1) or m.group(2)))
        if near * (1 - spread) <= v <= near * (1 + spread):
            found.append(v)
    return found


def current_price(page, last):
    """El precio actual más probable entre los cercanos al último conocido. 0 si no se encuentra."""
    cand = prices_in(page, last)
    return min(cand) if cand else 0                  # («antes $2.499.900, ahora $2.199.900»: el de ahora es el menor)
