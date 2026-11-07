"""Dólar, euro y criptomonedas (12.11). Lógica pura: fuentes, lectura de respuestas y conversiones.

- TRM oficial de Colombia (Superintendencia Financiera, datos abiertos del Gobierno: datos.gov.co).
- Euro y otras monedas: open.er-api.com (tasas de referencia del día, sin clave).
- Bitcoin y Ethereum: CoinGecko (sin clave).
«¿A cómo está el dólar?», «¿cuánto son 50 dólares en pesos?», «convierte 200 mil pesos a dólares», «precio del bitcoin».
"""
import re
import unicodedata

TRM_URL = "https://www.datos.gov.co/resource/32sa-8pi3.json?$limit=1&$order=vigenciadesde%20DESC"
FX_URL = "https://open.er-api.com/v6/latest/USD"
CRYPTO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd,cop"

CUR = {"dolar": "USD", "dolares": "USD", "usd": "USD", "dolar americano": "USD", "verdes": "USD", "euro": "EUR", "euros": "EUR", "eur": "EUR",
       "peso": "COP", "pesos": "COP", "cop": "COP", "bitcoin": "BTC", "bitcoins": "BTC", "btc": "BTC", "ethereum": "ETH", "eth": "ETH"}
NAMES = {"USD": "dólares", "EUR": "euros", "COP": "pesos", "BTC": "bitcoin", "ETH": "ethereum"}
_CUR_RX = r"(dolares|dolar americano|dolar|usd|verdes|euros|euro|eur|pesos|peso|cop|bitcoins|bitcoin|btc|ethereum|eth)"


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s.,$]", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


def parse_trm(data):
    """datos.gov.co → (valor, vigente desde, vigente hasta) o None."""
    try:
        row = (data or [])[0]
        return float(row["valor"]), str(row.get("vigenciadesde", ""))[:10], str(row.get("vigenciahasta", ""))[:10]
    except (IndexError, KeyError, TypeError, ValueError):
        return None


def parse_fx(data):
    """open.er-api → {moneda: unidades por 1 USD}."""
    if not isinstance(data, dict) or data.get("result") not in (None, "success"):
        return {}
    return {k: float(v) for k, v in (data.get("rates") or {}).items() if isinstance(v, (int, float))}


def parse_crypto(data):
    out = {}
    for cid, sym in (("bitcoin", "BTC"), ("ethereum", "ETH")):
        d = (data or {}).get(cid) or {}
        if d.get("usd"):
            out[sym] = {"USD": float(d["usd"]), "COP": float(d.get("cop") or 0)}
    return out


def cop_per(cur, trm, fx=None, crypto=None):
    """Cuántos pesos vale 1 unidad de esa moneda. None si no se sabe."""
    if cur == "COP":
        return 1.0
    if cur == "USD":
        return trm
    if cur in ("BTC", "ETH"):
        c = (crypto or {}).get(cur) or {}
        return c.get("COP") or (c.get("USD", 0) * trm if c.get("USD") and trm else None)
    rate = (fx or {}).get(cur)
    return trm / rate if rate and trm else None


def convert(amount, src, dst, trm, fx=None, crypto=None):
    a, b = cop_per(src, trm, fx, crypto), cop_per(dst, trm, fx, crypto)
    if not a or not b:
        return None
    return amount * a / b


def parse_amount(text):
    """«50», «1.500», «200 mil», «1,5 millones», «2 mil 500» → número (acepta decimales con coma o punto)."""
    t = norm(text).replace("$", "")
    m = re.search(r"(\d+(?:[.,]\d+)*)\s*(mil millones|millones|millon|mil|k)?", t)
    if not m:
        return 1.0 if re.search(r"\bun\b|\buna\b", t) else None
    num, unit = m.group(1), m.group(2)
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", num):
        val = float(num.replace(".", ""))
    elif re.fullmatch(r"\d{1,3}(?:,\d{3})+", num):
        val = float(num.replace(",", ""))
    else:
        val = float(num.replace(",", "."))
    mult = {"mil": 1e3, "k": 1e3, "millon": 1e6, "millones": 1e6, "mil millones": 1e9}.get(unit or "", 1)
    return val * mult


def parse_conversion(t):
    """«cuánto son 50 dólares en pesos», «convierte 200 mil pesos a dólares», «50 euros a pesos» → (cantidad, de, a) o None."""
    t = norm(t)
    m = re.search(rf"(?:cuanto (?:son|es|serian|seria|valen|vale)|convierte(?:me)?|pasa(?:me)?|cambia(?:me)?|a cuanto (?:equivalen|equivale))?\s*"
                  rf"(\$?\s*[\d.,]+\s*(?:mil millones|millones|millon|mil|k)?|un|una)\s+(?:de\s+)?{_CUR_RX}\s+(?:a|en)\s+{_CUR_RX}\b", t)
    if not m:
        return None
    amt = parse_amount(m.group(1))
    src, dst = CUR[m.group(2)], CUR[m.group(3)]
    if amt is None or src == dst:
        return None
    return amt, src, dst


def asks_rate(t):
    """«¿a cómo está el dólar?», «precio del euro», «la TRM», «cuánto vale el bitcoin» → moneda o ""."""
    t = norm(t)
    if re.search(r"\btrm\b|\btasa (?:representativa|de cambio)\b", t):
        return "USD"
    m = re.search(rf"\b(?:a como (?:esta|amanecio|cerro|quedo)|como (?:esta|va|amanecio)|cuanto (?:esta|vale|cuesta|va)|precio (?:del?|de la)|"
                  rf"valor (?:del?|de la)|cotizacion (?:del?|de la))\s+(?:el\s+|la\s+)?{_CUR_RX}\b", t)
    if m and CUR[m.group(1)] != "COP":
        return CUR[m.group(1)]
    if re.fullmatch(rf"(?:el\s+)?{_CUR_RX}(?:\s+hoy)?", t) and CUR.get(re.sub(r"^el\s+|\s+hoy$", "", t)) not in (None, "COP"):
        return CUR[re.sub(r"^el\s+|\s+hoy$", "", t)]
    return ""


def fmt(v, cur):
    """Cantidad legible: pesos con punto de miles, dólares/euros con 2 decimales, cripto con 6."""
    if cur == "COP":
        return "$" + f"{round(v):,}".replace(",", ".") + " pesos" if abs(v) >= 1 else f"{v:.4f}".replace(".", ",") + " pesos"
    if cur in ("BTC", "ETH"):
        return f"{v:.6f}".rstrip("0").rstrip(".").replace(".", ",") + " " + NAMES[cur]
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {NAMES.get(cur, cur)}"


def foreign_expense(text):
    """«gasté 50 dólares en un curso» → (50, "USD", "un curso") o None."""
    t = norm(text)
    m = re.match(rf"^(?:jarvis[ ,]+)?(?:gaste|me gaste|pague|compre)\s+(\$?\s*[\d.,]+\s*(?:mil|k)?)\s+{_CUR_RX}\s+(?:en|de|por|para)\s+(.+)$", t)
    if not m or CUR[m.group(2)] == "COP":
        return None
    amt = parse_amount(m.group(1))
    return (amt, CUR[m.group(2)], m.group(3).strip(" .")) if amt else None
