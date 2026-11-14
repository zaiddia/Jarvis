"""Clima (Open-Meteo, gratis y sin clave) y noticias (RSS: Google Noticias Colombia, BBC Mundo…).

Solo arma direcciones, interpreta respuestas y redacta frases; jarvis.py hace las peticiones.
"""
import datetime
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GNEWS = "https://news.google.com/rss"
DEFAULT_FEEDS = [f"{GNEWS}?hl=es-419&gl=CO&ceid=CO:es-419", "https://feeds.bbci.co.uk/mundo/rss.xml"]

# Códigos del tiempo (OMM) en palabras
WMO = {0: "despejado", 1: "mayormente despejado", 2: "parcialmente nublado", 3: "nublado",
       45: "con niebla", 48: "con niebla", 51: "con llovizna ligera", 53: "con llovizna", 55: "con llovizna fuerte",
       56: "con llovizna helada", 57: "con llovizna helada", 61: "con lluvia ligera", 63: "con lluvia",
       65: "con lluvia fuerte", 66: "con lluvia helada", 67: "con lluvia helada", 71: "con nieve ligera",
       73: "con nieve", 75: "con nieve fuerte", 77: "con granizo menudo", 80: "con chubascos ligeros",
       81: "con chubascos", 82: "con aguaceros fuertes", 85: "con chubascos de nieve", 86: "con chubascos de nieve",
       95: "con tormenta eléctrica", 96: "con tormenta y granizo", 99: "con tormenta fuerte y granizo"}


def geo_url(city):
    return f"{GEO_URL}?" + urllib.parse.urlencode({"name": city, "count": 1, "language": "es", "format": "json"})


def parse_geo(d):
    r = (d or {}).get("results") or []
    if not r:
        return None
    r = r[0]
    place = ", ".join(x for x in (r.get("name"), r.get("admin1"), r.get("country")) if x)
    return {"lat": r["latitude"], "lon": r["longitude"], "name": r.get("name", ""), "place": place}


def forecast_url(lat, lon):
    return f"{FORECAST_URL}?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 3,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,uv_index_max",
        "hourly": "precipitation_probability"})


def _r(x):
    return int(round(float(x)))


def describe(d, name, day=0):
    """Frase hablada del clima de hoy (day=0) o mañana (day=1), con recomendaciones."""
    daily = d.get("daily") or {}
    code = (daily.get("weather_code") or [None] * 3)[day]
    tmax = (daily.get("temperature_2m_max") or [None] * 3)[day]
    tmin = (daily.get("temperature_2m_min") or [None] * 3)[day]
    rain = (daily.get("precipitation_probability_max") or [None] * 3)[day]
    uv = (daily.get("uv_index_max") or [None] * 3)[day]
    parts = []
    if day == 0 and d.get("current"):
        c = d["current"]
        estado = WMO.get(c.get("weather_code"), "")
        txt = f"En {name} hay {_r(c['temperature_2m'])} grados"
        if estado:
            txt += f", {estado}"
        if c.get("apparent_temperature") is not None and abs(c["apparent_temperature"] - c["temperature_2m"]) >= 3:
            txt += f", con sensación de {_r(c['apparent_temperature'])}"
        if c.get("relative_humidity_2m") is not None:
            txt += f", y humedad del {_r(c['relative_humidity_2m'])} por ciento"
        parts.append(txt + ".")
        if tmax is not None:
            parts.append(f"Hoy la máxima será de {_r(tmax)} y la mínima de {_r(tmin)} grados.")
    else:
        when = "Mañana" if day == 1 else "Ese día"
        estado = WMO.get(code, "")
        parts.append(f"{when} en {name}: {estado + ', ' if estado else ''}entre {_r(tmin)} y {_r(tmax)} grados.")
    if rain is not None:
        if rain >= 60:
            hora = _rain_hour(d, day)
            parts.append(f"Hay {_r(rain)} por ciento de probabilidad de lluvia{(' desde ' + hora) if hora else ''}: "
                         "lleva paraguas.")
        elif rain >= 30:
            parts.append(f"Puede llover ({_r(rain)} por ciento): mejor lleva algo para la lluvia.")
        else:
            parts.append("No se espera lluvia.")
    tips = []
    if uv is not None and uv >= 8:
        tips.append("el sol estará muy fuerte: usa bloqueador y gorra, y recuerda a los estudiantes hidratarse")
    elif uv is not None and uv >= 6:
        tips.append("el sol estará fuerte: usa bloqueador")
    if tmax is not None and tmax >= 30:
        tips.append("hará calor: toma bastante agua")
    if tmin is not None and tmin <= 10:
        tips.append("en la mañana hará frío: abrígate")
    if tips:
        parts.append("Además, " + "; ".join(tips) + ".")
    return " ".join(parts)


def _rain_hour(d, day):
    h = d.get("hourly") or {}
    times, probs = h.get("time") or [], h.get("precipitation_probability") or []
    target = (datetime.date.today() + datetime.timedelta(days=day)).isoformat()
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H")
    for t, p in zip(times, probs):
        if t.startswith(target) and (day > 0 or t[:13] >= now) and p is not None and p >= 50:
            hh = int(t[11:13])
            periodo = "de la mañana" if hh < 12 else "de la tarde" if hh < 19 else "de la noche"
            return f"{'la' if hh % 12 == 1 else 'las'} {hh % 12 or 12} {periodo}"
    return ""


# ---------------------------------------------------------------- noticias
def topic_feed(topic):
    return f"{GNEWS}/search?" + urllib.parse.urlencode({"q": topic, "hl": "es-419", "gl": "CO", "ceid": "CO:es-419"})


def parse_rss(xml_text, limit=15):
    """[{título, fuente, fecha}] de un RSS o Atom."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for it in items[:limit * 2]:
        title = _text(it, "title") or _text(it, "{http://www.w3.org/2005/Atom}title")
        if not title:
            continue
        src = _text(it, "source")
        title = html.unescape(re.sub(r"<[^>]+>", "", title)).strip()
        if src and title.endswith(" - " + src):           # Google Noticias: «Titular - Medio»
            title = title[: -len(src) - 3].strip()
        elif not src and " - " in title and len(title.rsplit(" - ", 1)[1]) < 40:
            title, src = [x.strip() for x in title.rsplit(" - ", 1)]
        link = _text(it, "link")
        if not link:                                       # Atom: <link href="…"/>
            el = it.find("{http://www.w3.org/2005/Atom}link")
            link = el.get("href", "") if el is not None else ""
        link = link.strip() if link.strip().lower().startswith(("http://", "https://")) else ""
        out.append({"titulo": title, "fuente": src or "", "fecha": _text(it, "pubDate") or "", "link": link})
        if len(out) >= limit:
            break
    return out


def _text(el, tag):
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


def merge(lists, limit=8):
    """Une varias fuentes alternando y sin titulares repetidos."""
    seen, out = set(), []
    for i in range(max((len(x) for x in lists), default=0)):
        for lst in lists:
            if i < len(lst):
                key = re.sub(r"\W+", " ", lst[i]["titulo"].lower())[:60]
                if key not in seen:
                    seen.add(key)
                    out.append(lst[i])
    return out[:limit]


def persona():
    """Quién es Jarvis en este texto. modos.py lo cambia según el modo (12.26: no todo es del colegio)."""
    return "el asistente personal de una persona en Colombia"


def news_prompt(items, topic=""):
    lines = "\n".join(f"- {n['titulo']}" + (f" ({n['fuente']})" if n["fuente"] else "") for n in items)
    return (f"Eres Jarvis, {persona()}. Con estos titulares de hoy"
            + (f" sobre «{topic}»" if topic else "") + ", cuéntale en voz alta las noticias más importantes: "
            "entre 4 y 6, una o dos frases cada una, claras y neutrales, empezando por las de Colombia. No "
            "inventes nada que no esté en los titulares y nombra el medio cuando ayude. Sin listas ni markdown: "
            "es para escucharse. Termina sin preguntas.\n\nTitulares:\n" + lines)


def news_json_prompt(items, topic=""):
    """12.31: lo mismo, pero diciendo de qué titular sale cada noticia (para poner su fuente y su enlace)."""
    lines = "\n".join(f"{i}. {n['titulo']}" + (f" ({n['fuente']})" if n["fuente"] else "") for i, n in enumerate(items))
    return (f"Eres Jarvis, {persona()}. Con estos titulares de hoy" + (f" sobre «{topic}»" if topic else "") +
            ", escoge las 4 a 6 noticias más importantes (primero las de Colombia) y cuéntalas en una o dos frases claras y "
            "neutrales cada una, para escucharse (sin markdown). No inventes nada que no esté en el titular.\n"
            'Responde SOLO con JSON: {"noticias": [{"i": número del titular, "texto": "…"}]}\n\nTitulares:\n' + lines)


def news_parse(d, items):
    """[(texto, titular)] a partir del JSON de la IA (los índices que no existen se descartan)."""
    out = []
    for x in (d or {}).get("noticias") or []:
        try:
            i = int(x.get("i"))
        except (TypeError, ValueError, AttributeError):
            continue
        texto = re.sub(r"\s+", " ", str(x.get("texto") or "")).strip()
        if 0 <= i < len(items) and texto and all(i != j for _, j in out):
            out.append((texto, i))
    return [(t, items[i]) for t, i in out[:6]]


def news_rich(pairs, remote=False):
    """Lo que se ve en el chat: cada noticia con su fuente, que se toca para abrir la noticia (en Telegram, el enlace a la vista)."""
    lines = []
    for texto, it in pairs:
        src = it.get("fuente") or "Fuente"
        if it.get("link"):
            lines.append(f"- {texto} — {src}: {it['link']}" if remote else f"- {texto} — [{src}]({it['link']})")
        else:
            lines.append(f"- {texto}" + (f" — {src}" if it.get("fuente") else ""))
    return "\n".join(lines)


def news_spoken(pairs):
    return " ".join(f"{t}" + (f" Lo cuenta {it['fuente']}." if it.get("fuente") and it["fuente"].lower() not in t.lower() else "")
                    for t, it in pairs)


def headlines_spoken(items, n=5):
    if not items:
        return "No encontré noticias en este momento."
    tops = [f"{x['titulo']}" + (f", según {x['fuente']}" if x["fuente"] else "") for x in items[:n]]
    return "Estos son los titulares: " + ". ".join(tops) + "."
