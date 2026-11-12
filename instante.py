"""Respuestas al instante (12.20): cosas que no necesitan a la IA y por eso salen en milisegundos, con o sin internet.

Lógica pura (sin Jarvis): recibe el texto normalizado (sin tildes ni signos) y devuelve la respuesta o None.
  hora mundial · cuenta de días y fechas · edad · conversor de unidades · dados, números y sorteos ·
  contraseñas · deletrear · chistes, datos curiosos y frases · repetir
"""
import datetime
import random
import re
import secrets
import string
import unicodedata

try:
    from zoneinfo import ZoneInfo
except Exception:                                      # pragma: no cover
    ZoneInfo = None

def norm(text):
    """Minúsculas y sin tildes, pero conserva . , / % - (hacen falta para «2,5 millas», «km/h» y las listas)."""
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s/.,%:+-]", " ", t)
    t = re.sub(r"(?<!\d)[.,]|[.,](?!\d)", " ", t)       # puntos y comas que no son decimales
    return re.sub(r"\s+", " ", t).strip()


# ============================================================================ HORA EN OTRO LUGAR
# lugar → (zona, diferencia fija con UTC por si el equipo no trae la base de zonas)
PLACES = {
    "tokio": ("Asia/Tokyo", 9), "japon": ("Asia/Tokyo", 9), "pekin": ("Asia/Shanghai", 8), "beijing": ("Asia/Shanghai", 8),
    "china": ("Asia/Shanghai", 8), "shanghai": ("Asia/Shanghai", 8), "seul": ("Asia/Seoul", 9), "corea": ("Asia/Seoul", 9),
    "india": ("Asia/Kolkata", 5.5), "nueva delhi": ("Asia/Kolkata", 5.5), "dubai": ("Asia/Dubai", 4), "moscu": ("Europe/Moscow", 3),
    "rusia": ("Europe/Moscow", 3), "estambul": ("Europe/Istanbul", 3), "turquia": ("Europe/Istanbul", 3), "israel": ("Asia/Jerusalem", 2),
    "madrid": ("Europe/Madrid", 1), "espana": ("Europe/Madrid", 1), "barcelona": ("Europe/Madrid", 1), "paris": ("Europe/Paris", 1),
    "francia": ("Europe/Paris", 1), "roma": ("Europe/Rome", 1), "italia": ("Europe/Rome", 1), "berlin": ("Europe/Berlin", 1),
    "alemania": ("Europe/Berlin", 1), "amsterdam": ("Europe/Amsterdam", 1), "suiza": ("Europe/Zurich", 1), "londres": ("Europe/London", 0),
    "inglaterra": ("Europe/London", 0), "reino unido": ("Europe/London", 0), "lisboa": ("Europe/Lisbon", 0), "portugal": ("Europe/Lisbon", 0),
    "nueva york": ("America/New_York", -5), "miami": ("America/New_York", -5), "washington": ("America/New_York", -5),
    "orlando": ("America/New_York", -5), "toronto": ("America/Toronto", -5), "chicago": ("America/Chicago", -6),
    "houston": ("America/Chicago", -6), "texas": ("America/Chicago", -6), "denver": ("America/Denver", -7),
    "los angeles": ("America/Los_Angeles", -8), "california": ("America/Los_Angeles", -8), "san francisco": ("America/Los_Angeles", -8),
    "ciudad de mexico": ("America/Mexico_City", -6), "mexico": ("America/Mexico_City", -6), "guatemala": ("America/Guatemala", -6),
    "costa rica": ("America/Costa_Rica", -6), "panama": ("America/Panama", -5), "bogota": ("America/Bogota", -5),
    "colombia": ("America/Bogota", -5), "medellin": ("America/Bogota", -5), "cali": ("America/Bogota", -5), "quito": ("America/Guayaquil", -5),
    "ecuador": ("America/Guayaquil", -5), "lima": ("America/Lima", -5), "peru": ("America/Lima", -5), "caracas": ("America/Caracas", -4),
    "venezuela": ("America/Caracas", -4), "la paz": ("America/La_Paz", -4), "bolivia": ("America/La_Paz", -4),
    "santiago": ("America/Santiago", -4), "chile": ("America/Santiago", -4), "buenos aires": ("America/Argentina/Buenos_Aires", -3),
    "argentina": ("America/Argentina/Buenos_Aires", -3), "montevideo": ("America/Montevideo", -3), "uruguay": ("America/Montevideo", -3),
    "sao paulo": ("America/Sao_Paulo", -3), "brasil": ("America/Sao_Paulo", -3), "rio de janeiro": ("America/Sao_Paulo", -3),
    "la habana": ("America/Havana", -5), "cuba": ("America/Havana", -5), "republica dominicana": ("America/Santo_Domingo", -4),
    "puerto rico": ("America/Puerto_Rico", -4), "sidney": ("Australia/Sydney", 10), "sydney": ("Australia/Sydney", 10),
    "australia": ("Australia/Sydney", 10), "nueva zelanda": ("Pacific/Auckland", 12), "egipto": ("Africa/Cairo", 2),
    "el cairo": ("Africa/Cairo", 2), "sudafrica": ("Africa/Johannesburg", 2), "hawai": ("Pacific/Honolulu", -10),
    "canada": ("America/Toronto", -5), "estados unidos": ("America/New_York", -5), "singapur": ("Asia/Singapore", 8),
    "tailandia": ("Asia/Bangkok", 7), "bangkok": ("Asia/Bangkok", 7), "hong kong": ("Asia/Hong_Kong", 8),
}
_PLACE_NAMES = {"tokio": "Tokio", "japon": "Japón", "pekin": "Pekín", "seul": "Seúl", "moscu": "Moscú", "espana": "España", "paris": "París",
                "berlin": "Berlín", "ciudad de mexico": "Ciudad de México", "mexico": "México", "panama": "Panamá", "bogota": "Bogotá",
                "medellin": "Medellín", "peru": "Perú", "turquia": "Turquía", "sudafrica": "Sudáfrica", "hawai": "Hawái", "canada": "Canadá",
                "republica dominicana": "República Dominicana"}
_HORA_EN = re.compile(r"\bque hora (?:es|son|sera|seran)(?: ahora| ahorita)? en (?:la |el |los |las )?(.+?)\s*$|"
                      r"\bhora (?:actual )?(?:en|de) (?:la |el |los |las )?(.+?)\s*$")


def _fmt_hora(dt):
    h = dt.hour % 12 or 12
    franja = "de la madrugada" if dt.hour < 6 else "de la mañana" if dt.hour < 12 else "de la tarde" if dt.hour < 19 else "de la noche"
    return f"{h}:{dt.minute:02d} {franja}"


def place_time(place, now_utc=None):
    """→ (datetime local de ese lugar, nombre para decir) o None."""
    key = place.strip()
    if key not in PLACES:
        key = next((k for k in sorted(PLACES, key=len, reverse=True) if re.search(rf"\b{re.escape(k)}\b", key)), None)
        if not key:
            return None
    zone, offset = PLACES[key]
    now_utc = now_utc or datetime.datetime.now(datetime.timezone.utc)
    dt = None
    if ZoneInfo is not None:
        try:
            dt = now_utc.astimezone(ZoneInfo(zone))
        except Exception:
            dt = None
    if dt is None:
        dt = now_utc.astimezone(datetime.timezone(datetime.timedelta(hours=offset)))
    return dt, _PLACE_NAMES.get(key, key.title())


def world_time(t, now_utc=None, here=None):
    m = _HORA_EN.search(t)
    if not m:
        return None
    got = place_time((m.group(1) or m.group(2) or ""), now_utc)
    if not got:
        return None
    dt, name = got
    here = here or datetime.datetime.now()
    day = ""
    if dt.date() > here.date():
        day = " de mañana"
    elif dt.date() < here.date():
        day = " de ayer"
    return f"En {name} son las {_fmt_hora(dt)}{day}."


# ============================================================================ FECHAS
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
         "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MES_NOMBRE = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
FIESTAS = {"navidad": (12, 25), "nochebuena": (12, 24), "ano nuevo": (1, 1), "fin de ano": (12, 31), "nochevieja": (12, 31),
           "halloween": (10, 31), "san valentin": (2, 14), "dia de la independencia": (7, 20), "reyes": (1, 6),
           "dia de las velitas": (12, 7), "amor y amistad": (9, 20), "dia de la mujer": (3, 8), "dia del trabajo": (5, 1)}
_FECHA = r"(\d{1,2}) de (" + "|".join(MESES) + r")(?: (?:de|del) (\d{4}))?"
_NUM_FECHA = r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?"


def _parse_date(s, today, future=True):
    """Fecha en el texto → date (si no trae año: la próxima, o la de este año si future=False)."""
    m = re.search(_FECHA, s)
    if m:
        d, mo, y = int(m.group(1)), MESES[m.group(2)], m.group(3)
    else:
        m = re.search(_NUM_FECHA, s)
        if not m:
            for name, (mo, d) in FIESTAS.items():
                if re.search(rf"\b{name}\b", s):
                    y = None
                    break
            else:
                return None
        else:
            d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        if y:
            return datetime.date(int(y), mo, d)
        dt = datetime.date(today.year, mo, d)
        if future and dt < today:
            dt = datetime.date(today.year + 1, mo, d)
        return dt
    except ValueError:
        return None


def _plural(n, uno, varios):
    return f"{n} {uno if n == 1 else varios}"


def _fecha_txt(d):
    return f"{DIAS[d.weekday()]} {d.day} de {MES_NOMBRE[d.month]} de {d.year}"


_FALTAN = re.compile(r"\bcuant[oa]s? (dias|semanas|meses)? ?(?:faltan?|quedan?|hay)(?: de aqui)? (?:para|hasta|a)\b|\bcuanto falta para\b")
_CAE = re.compile(r"\bque dia (?:de la semana )?(?:cae|es|sera|fue|cayo|era)\b|\bque dia de la semana\b")
_ENTRE = re.compile(r"\bcuantos dias hay entre\b|\bdias entre\b")
_EDAD = re.compile(r"\b(?:que edad|cuantos anos) (?:tengo|tiene|tendria|tendre|cumplo|cumple)\b.*\b(?:naci|nacio|nacido|nacida)\b|"
                   r"\b(?:naci|nacio)\b.*\b(?:que edad|cuantos anos)\b")
_EN_DIAS = re.compile(r"\bque (?:fecha|dia) (?:es|sera|cae) (?:en|dentro de) (\d{1,4}) (dias|semanas)\b|\b(?:en|dentro de) (\d{1,4}) (dias|semanas) que (?:fecha|dia)\b")
_HACE_DIAS = re.compile(r"\bque (?:fecha|dia) (?:fue|era) hace (\d{1,4}) (dias|semanas)\b")


def dates(t, today=None):
    today = today or datetime.date.today()
    m = _EN_DIAS.search(t)
    if m:
        n, unit = int(m.group(1) or m.group(3)), (m.group(2) or m.group(4))
        d = today + datetime.timedelta(days=n * (7 if unit == "semanas" else 1))
        return f"En {n} {unit.replace('dias', 'días')} será {_fecha_txt(d)}."
    m = _HACE_DIAS.search(t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        d = today - datetime.timedelta(days=n * (7 if unit == "semanas" else 1))
        return f"Hace {n} {unit.replace('dias', 'días')} fue {_fecha_txt(d)}."
    if _ENTRE.search(t):
        ds = [x for x in (_parse_date(p, today, future=False) for p in re.split(r"\s+y\s+(?:el\s+)?", t.split("entre", 1)[-1], maxsplit=1)) if x]
        if len(ds) == 2:
            n = abs((ds[1] - ds[0]).days)
            return f"Entre el {ds[0].day} de {MES_NOMBRE[ds[0].month]} y el {ds[1].day} de {MES_NOMBRE[ds[1].month]} hay {_plural(n, 'día', 'días')}."
        return None
    if _EDAD.search(t):
        born = _parse_date(t, today, future=False)
        if born is None:
            m = re.search(r"\b(?:en|de|del) (19\d{2}|20\d{2})\b", t)
            if not m:
                return None
            years = today.year - int(m.group(1))
            return f"Quien nació en {m.group(1)} tiene {years - 1} o {years} años, según si ya cumplió este año."
        if not re.search(r"\b(19|20)\d{2}\b", t):
            return None
        years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        nxt = datetime.date(today.year, born.month, born.day) if (born.month, born.day) != (2, 29) else datetime.date(today.year, 3, 1)
        if nxt < today:
            nxt = nxt.replace(year=today.year + 1)
        left = (nxt - today).days
        tail = " ¡Hoy es el cumpleaños!" if left == 0 else f" Faltan {_plural(left, 'día', 'días')} para el próximo cumpleaños."
        return f"Son {years} años.{tail}"
    m = _FALTAN.search(t)
    if m:
        d = _parse_date(t[m.end():] if m.end() < len(t) else t, today) or _parse_date(t, today)
        if d is None:
            return None
        n = (d - today).days
        what = next((k for k in FIESTAS if re.search(rf"\b{k}\b", t)), None)
        label = {"ano nuevo": "Año Nuevo", "fin de ano": "fin de año", "san valentin": "San Valentín"}.get(what, what.capitalize() if what else f"el {d.day} de {MES_NOMBRE[d.month]}")
        if n == 0:
            return f"¡{label[0].upper() + label[1:]} es hoy!"
        unit = m.group(1)
        if unit == "semanas":
            w, r = divmod(n, 7)
            return f"Para {label} faltan {_plural(w, 'semana', 'semanas')}" + (f" y {_plural(r, 'día', 'días')}" if r else "") + f" ({_fecha_txt(d)})."
        if unit == "meses":
            mo = (d.year - today.year) * 12 + d.month - today.month - (d.day < today.day)
            return f"Para {label} faltan unos {_plural(mo, 'mes', 'meses')} ({_plural(n, 'día', 'días')}; cae {_fecha_txt(d)})."
        return f"Para {label} faltan {_plural(n, 'día', 'días')}: cae {_fecha_txt(d)}."
    if _CAE.search(t):
        past = bool(re.search(r"\b(?:fue|cayo|era)\b", t))
        d = _parse_date(t, today, future=not past)
        if d is None:
            return None
        verb = "fue" if d < today else "es" if d == today else "cae"
        return f"El {d.day} de {MES_NOMBRE[d.month]} de {d.year} {verb} {DIAS[d.weekday()]}."
    return None


_HASTA = re.compile(r"\bcuanto (?:tiempo )?falta para (?:las|la) (\d{1,2})(?::(\d{2}))?(?: y (media|cuarto))?(?: (?:de la |del )?(manana|tarde|noche|mediodia|madrugada))?\s*$")


def until_hour(t, now=None):
    """«¿cuánto falta para las 5 de la tarde?» → horas y minutos hasta esa hora (hoy o mañana)."""
    m = _HASTA.search(t)
    if not m:
        return None
    now = now or datetime.datetime.now()
    h, mi = int(m.group(1)), int(m.group(2) or 0) + {"media": 30, "cuarto": 15}.get(m.group(3) or "", 0)
    part = m.group(4)
    if h > 23 or mi > 59:
        return None
    if part in ("tarde", "noche") and h < 12:
        h += 12
    elif part in ("manana", "madrugada") and h == 12:
        h = 0
    elif part is None and h <= 12:                      # sin «de la tarde»: la próxima vez que el reloj marque esa hora
        cands = [c for c in (h % 12, h % 12 + 12)]
        nowm = now.hour * 60 + now.minute
        h = min(cands, key=lambda c: (c * 60 + mi - nowm) % 1440)
    target = now.replace(hour=h, minute=mi, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    mins = int((target - now).total_seconds() // 60)
    hh, mm = divmod(mins, 60)
    parts = ([_plural(hh, "hora", "horas")] if hh else []) + ([_plural(mm, "minuto", "minutos")] if mm or not hh else [])
    return f"Para las {_fmt_hora(target)}{' de mañana' if target.date() > now.date() else ''} faltan {' y '.join(parts)}."


# ============================================================================ UNIDADES
# unidad → (magnitud, factor a la unidad base, singular, plural)
_U = {}


def _add(kind, factor, sing, plur, *names):
    for n in names:
        _U[n] = (kind, factor, sing, plur)


_add("long", 0.001, "milímetro", "milímetros", "milimetro", "milimetros", "mm")
_add("long", 0.01, "centímetro", "centímetros", "centimetro", "centimetros", "cm")
_add("long", 1, "metro", "metros", "metro", "metros", "m")
_add("long", 1000, "kilómetro", "kilómetros", "kilometro", "kilometros", "km")
_add("long", 0.0254, "pulgada", "pulgadas", "pulgada", "pulgadas")
_add("long", 0.3048, "pie", "pies", "pie", "pies")
_add("long", 0.9144, "yarda", "yardas", "yarda", "yardas")
_add("long", 1609.344, "milla", "millas", "milla", "millas")
_add("peso", 0.001, "gramo", "gramos", "gramo", "gramos", "g")
_add("peso", 1, "kilo", "kilos", "kilo", "kilos", "kilogramo", "kilogramos", "kg")
_add("peso", 1000, "tonelada", "toneladas", "tonelada", "toneladas")
_add("peso", 0.45359237, "libra", "libras", "libra", "libras", "lb")
_add("peso", 0.028349523, "onza", "onzas", "onza", "onzas", "oz")
_add("peso", 12.5, "arroba", "arrobas", "arroba", "arrobas")
_add("vol", 0.001, "mililitro", "mililitros", "mililitro", "mililitros", "ml")
_add("vol", 1, "litro", "litros", "litro", "litros", "l")
_add("vol", 3.785411784, "galón", "galones", "galon", "galones")
_add("vol", 0.24, "taza", "tazas", "taza", "tazas")
_add("vol", 0.015, "cucharada", "cucharadas", "cucharada", "cucharadas")
_add("vol", 0.005, "cucharadita", "cucharaditas", "cucharadita", "cucharaditas")
_add("vol", 1000, "metro cúbico", "metros cúbicos", "metro cubico", "metros cubicos")
_add("tiempo", 1, "segundo", "segundos", "segundo", "segundos")
_add("tiempo", 60, "minuto", "minutos", "minuto", "minutos")
_add("tiempo", 3600, "hora", "horas", "hora", "horas")
_add("tiempo", 86400, "día", "días", "dia", "dias")
_add("tiempo", 604800, "semana", "semanas", "semana", "semanas")
_add("tiempo", 31557600, "año", "años", "ano", "anos")
_add("vel", 1, "kilómetro por hora", "kilómetros por hora", "kilometro por hora", "kilometros por hora", "km/h", "kmh")
_add("vel", 1.609344, "milla por hora", "millas por hora", "milla por hora", "millas por hora", "mph")
_add("vel", 3.6, "metro por segundo", "metros por segundo", "metro por segundo", "metros por segundo", "m/s")
_add("vel", 1.852, "nudo", "nudos", "nudo", "nudos")
_add("datos", 1, "byte", "bytes", "byte", "bytes")
_add("datos", 1e3, "kilobyte", "kilobytes", "kilobyte", "kilobytes", "kb")
_add("datos", 1e6, "mega", "megas", "mega", "megas", "megabyte", "megabytes", "mb")
_add("datos", 1e9, "giga", "gigas", "giga", "gigas", "gigabyte", "gigabytes", "gb")
_add("datos", 1e12, "tera", "teras", "tera", "teras", "terabyte", "terabytes", "tb")
_add("area", 1, "metro cuadrado", "metros cuadrados", "metro cuadrado", "metros cuadrados", "m2")
_add("area", 10000, "hectárea", "hectáreas", "hectarea", "hectareas")
_add("area", 1e6, "kilómetro cuadrado", "kilómetros cuadrados", "kilometro cuadrado", "kilometros cuadrados", "km2")
_add("area", 6400, "fanegada", "fanegadas", "fanegada", "fanegadas")
_add("area", 4046.8564224, "acre", "acres", "acre", "acres")
_TEMP = {"celsius": "C", "centigrados": "C", "grados celsius": "C", "grados centigrados": "C", "c": "C",
         "fahrenheit": "F", "grados fahrenheit": "F", "farenheit": "F", "grados farenheit": "F", "f": "F",
         "kelvin": "K", "grados kelvin": "K", "k": "K"}
_TEMP_NAME = {"C": "grados Celsius", "F": "grados Fahrenheit", "K": "kelvin"}
_UNIT_ALT = "|".join(sorted((re.escape(u) for u in list(_U) + list(_TEMP)), key=len, reverse=True))
_NUMW = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
         "medio": 0.5, "media": 0.5, "cien": 100, "mil": 1000}
_CONV = re.compile(r"(?:^|\b)(?:convierte|convertir|convierteme|pasa|pasame|cuanto (?:es|son|equivale|equivalen)|cuant[oa]s? .{0,40}? (?:hay|son|tiene|tienen|equivalen) en|a cuanto equivalen?|equivalencia de)?\s*"
                   r"(-?\d+(?:[.,]\d+)?|" + "|".join(_NUMW) + r")\s*(?:grados? )?(" + _UNIT_ALT + r")\s+(?:a|en|son cuant[oa]s?|cuant[oa]s? .{0,12}? son|equivalen? a)\s+(?:grados? )?(" + _UNIT_ALT + r")\b")
_CONV2 = re.compile(r"\bcuant[oa]s? (" + _UNIT_ALT + r") (?:hay|son|tiene|tienen|caben|equivalen)(?: en| a)? (-?\d+(?:[.,]\d+)?|" + "|".join(_NUMW) + r")\s*(?:grados? )?(" + _UNIT_ALT + r")\b")


def _num(x):
    if x in _NUMW:
        return float(_NUMW[x])
    return float(x.replace(",", "."))


def _say_num(v):
    if abs(v) >= 100 or v == int(v):
        s = f"{v:,.0f}" if abs(v - round(v)) < 0.005 else f"{v:,.1f}"
    elif abs(v) >= 1:
        s = f"{v:,.2f}".rstrip("0").rstrip(".")
    else:
        s = f"{v:.4f}".rstrip("0").rstrip(".") or "0"
    return s.replace(",", " ").replace(".", ",").replace(" ", ".")


def convert(value, src, dst):
    """→ número convertido, o None si no son de la misma magnitud."""
    if src in _TEMP or dst in _TEMP:
        if src not in _TEMP or dst not in _TEMP:
            return None
        a, b = _TEMP[src], _TEMP[dst]
        c = value if a == "C" else (value - 32) * 5 / 9 if a == "F" else value - 273.15
        return c if b == "C" else c * 9 / 5 + 32 if b == "F" else c + 273.15
    if src not in _U or dst not in _U or _U[src][0] != _U[dst][0]:
        return None
    return value * _U[src][1] / _U[dst][1]


def _unit_name(u, v):
    if u in _TEMP:
        return _TEMP_NAME[_TEMP[u]]
    return _U[u][2] if abs(v) == 1 else _U[u][3]


def units(t):
    m = _CONV.search(t)
    if m:
        value, src, dst = _num(m.group(1)), m.group(2), m.group(3)
    else:
        m = _CONV2.search(t)
        if not m:
            return None
        dst, value, src = m.group(1), _num(m.group(2)), m.group(3)
    if len(src) == 1 and len(dst) == 1 and not (src in _TEMP and dst in _TEMP):
        return None                                    # «5 m a l»: letras sueltas que no cuadran
    out = convert(value, src, dst)
    if out is None:
        return None
    return f"{_say_num(value)} {_unit_name(src, value)} son {_say_num(out)} {_unit_name(dst, out)}."


# ============================================================================ AZAR
_DADO = re.compile(r"\b(?:lanza|tira|tirame|lanzame|echa)\s+(un|una|dos|tres|cuatro|cinco|\d)?\s*dados?(?: de (\d{1,3}) caras)?\b")
_AZAR = re.compile(r"\bnumero (?:al azar|aleatorio|cualquiera)(?: (?:entre|del?) (?:el )?(\d{1,9}) (?:y|al?) (?:el )?(\d{1,9}))?|"
                   r"\b(?:dime|dame|escoge|elige|di) un numero (?:entre|del?) (?:el )?(\d{1,9}) (?:y|al?) (?:el )?(\d{1,9})\b")
_ELIGE = re.compile(r"^(?:jarvis )?(?:escoge|elige|decide|sortea|selecciona)(?:me)?(?: tu| al azar| uno| una)*(?: entre| de)?:?\s+(.+)$")


def chance(t, raw=None, rng=None):
    rng = rng or random
    m = _DADO.search(t)
    if m:
        n = {"un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5}.get(m.group(1) or "un") or int(m.group(1))
        sides = int(m.group(2) or 6)
        if not (1 <= n <= 9 and 2 <= sides <= 100):
            return None
        rolls = [rng.randint(1, sides) for _ in range(n)]
        if n == 1:
            return f"Salió {rolls[0]}."
        return f"Salieron {', '.join(map(str, rolls[:-1]))} y {rolls[-1]}: suman {sum(rolls)}."
    m = _AZAR.search(t)
    if m:
        a, b = (m.group(1) or m.group(3)), (m.group(2) or m.group(4))
        lo, hi = (int(a), int(b)) if a and b else (1, 100)
        if lo > hi:
            lo, hi = hi, lo
        return f"El {rng.randint(lo, hi)}." + ("" if a and b else " (Entre 1 y 100.)")
    m = _ELIGE.match(t)
    if m:
        src = raw if raw else m.group(1)
        mm = re.search(r"(?:escoge|elige|decide|sortea|selecciona)(?:me)?(?: tú| tu| al azar| uno| una)*(?: entre| de)?:?\s+(.+)$", src, re.I)
        body = (mm.group(1) if mm else m.group(1)).strip(" .?!¿¡")
        opts = [o.strip() for o in re.split(r"\s*,\s*|\s+o\s+|\s+u\s+|\s+y\s+", body) if o.strip()]
        if len(opts) < 2:                              # dictado por voz: «pizza sushi o tacos» llega sin comas
            head, _, last = body.rpartition(" o ")
            opts = head.split() + [last] if head and last else opts
        if len(opts) < 2 or any(len(o.split()) > 5 for o in opts):
            return None
        return f"Escojo: {rng.choice(opts)}."
    return None


# ============================================================================ CONTRASEÑAS
_PASS = re.compile(r"\b(?:genera|generame|crea|creame|dame|inventa|sugiere|sugiereme)\s+(?:una\s+)?(?:nueva\s+)?(?:contrasena|clave|password)(?:\s+(?:segura|fuerte|aleatoria|dificil))?"
                   r"(?:\s+de\s+(\d{1,2})\s+(?:caracteres|letras|digitos))?")


def password(t):
    """→ (contraseña, largo) o None. Nunca se dice en voz alta: solo se muestra."""
    m = _PASS.search(t)
    if not m:
        return None
    n = min(max(int(m.group(1) or 16), 8), 40)
    simple = bool(re.search(r"\bsin simbolos\b|\bsolo letras y numeros\b", t))
    sets = [string.ascii_lowercase, string.ascii_uppercase, string.digits] + ([] if simple else ["!@#$%&*-_+=?"])
    drop = "lIO0o1"                                    # sin letras que se confunden al copiarla a mano
    pools = ["".join(c for c in s if c not in drop) for s in sets]
    chars = [secrets.choice(p) for p in pools] + [secrets.choice("".join(pools)) for _ in range(n - len(pools))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars), n


# ============================================================================ DELETREAR Y REPETIR
_SPELL = re.compile(r"^(?:jarvis )?(?:deletrea|deletreame|como se deletrea|como se escribe)(?: la palabra)?\s+(.+)$")
_REPEAT = re.compile(r"^(?:jarvis )?(?:repite|di|dime)(?: despues de mi| conmigo| lo siguiente| esto)[:,]?\s+(.+)$")


def spell(t, raw=None):
    m = _SPELL.match(t)
    if not m:
        return None
    word = m.group(1).strip()
    if raw:
        mm = re.search(r"(?:deletrea|deletréame|deletreame|c[oó]mo se deletrea|c[oó]mo se escribe)(?: la palabra)?\s+(.+)$", raw, re.I)
        if mm:
            word = mm.group(1).strip(" .?!¿¡\"«»")
    if not word or len(word) > 40 or len(word.split()) > 3:
        return None
    letters = [("espacio" if c == " " else c.upper()) for c in word]
    return f"{word}: " + ", ".join(letters) + "."


def repeat(t, raw=None):
    m = _REPEAT.match(t)
    if not m:
        return None
    if raw:
        mm = re.search(r"(?:despu[eé]s de m[ií]|conmigo|lo siguiente|esto)[:,]?\s+(.+)$", raw, re.I)
        if mm:
            return mm.group(1).strip()
    return m.group(1).strip()


# ============================================================================ CHISTES, DATOS Y FRASES (sin internet)
CHISTES = [
    "¿Qué le dice un cero a un ocho? Bonito cinturón.",
    "¿Por qué el libro de matemáticas estaba triste? Porque tenía demasiados problemas.",
    "¿Cuál es el colmo de un electricista? Que su esposa se llame Luz y sus hijos le sigan la corriente.",
    "¿Qué hace una abeja en el gimnasio? Zumba.",
    "¿Cómo se despiden los químicos? Ácido un placer.",
    "¿Qué le dijo un techo a otro techo? Techo de menos.",
    "¿Por qué los pájaros no usan Facebook? Porque ya tienen Twitter.",
    "¿Cuál es el café más peligroso del mundo? El ex-preso.",
    "Hay diez tipos de personas: las que entienden binario y las que no.",
    "¿Qué le dice el número tres al treinta? Para ser como yo, tienes que ser sincero.",
    "¿Cuál es el animal más antiguo? La cebra, porque está en blanco y negro.",
    "¿Qué hace un pez? Nada.",
    "—Doctor, veo elefantes azules por todas partes. —¿Ya vio a un psicólogo? —No, solo elefantes azules.",
    "¿Por qué la escoba está feliz? Porque ba-rriendo.",
    "¿Cómo se dice pañuelo en japonés? Saka-moko.",
    "¿Qué le dice una impresora a otra? ¿Esa hoja es tuya o es impresión mía?",
    "¿Por qué el programador confunde Halloween con Navidad? Porque 31 en octal es 25 en decimal.",
    "Mi contraseña era «incorrecta». Así, cuando me equivoco, el computador me la recuerda.",
    "¿Qué le dice un jardinero a otro? Nos vemos cuando podamos.",
    "¿Cuál es el colmo de un matemático? Tener muchos problemas y no poder resolverlos en casa.",
    "¿Por qué el tomate no toma café? Porque toma-té.",
    "El wifi y yo tenemos una relación complicada: a veces siento que no hay conexión.",
    "¿Qué le dijo un semáforo a otro? No me mires, que me estoy cambiando.",
    "Fui a comprar camuflaje, pero no encontré ninguno.",
]
DATOS = [
    "La miel no se daña: se ha encontrado miel de hace tres mil años en tumbas egipcias y todavía se podía comer.",
    "Un día en Venus dura más que un año en Venus: gira tan despacio que tarda más en dar una vuelta sobre sí mismo que alrededor del Sol.",
    "Los pulpos tienen tres corazones y sangre azul.",
    "El corazón de una ballena azul es tan grande como un carro pequeño.",
    "Colombia es el segundo país con más biodiversidad del mundo y el primero en especies de aves.",
    "La luz del Sol tarda unos ocho minutos y veinte segundos en llegar a la Tierra.",
    "Los plátanos son ligeramente radiactivos porque tienen potasio, pero tendrías que comer millones para que hiciera efecto.",
    "El cero como número se usó por primera vez en la India, hace unos mil quinientos años.",
    "Hay más formas de barajar un mazo de 52 cartas que átomos en la Tierra.",
    "El cerebro humano gasta más o menos la misma energía que un bombillo de 20 vatios.",
    "Las abejas pueden reconocer rostros humanos.",
    "El río Amazonas no tiene ningún puente que lo cruce en todo su recorrido principal.",
    "Un rayo es unas cinco veces más caliente que la superficie del Sol.",
    "La palabra «algoritmo» viene del nombre del matemático persa Al-Juarismi.",
    "El primer computador programable, el ENIAC, pesaba unas 27 toneladas.",
    "Caño Cristales, en Colombia, es conocido como el río de los cinco colores.",
    "Los koalas tienen huellas dactilares casi idénticas a las humanas.",
    "El signo igual se inventó en 1557: Robert Recorde escogió dos rayas paralelas porque «no hay dos cosas más iguales».",
    "En Júpiter y Saturno podría llover diamantes.",
    "El primer mensaje de texto de la historia, en 1992, decía «Feliz Navidad».",
    "Las hormigas no tienen pulmones: respiran por pequeños agujeros en su cuerpo.",
    "Un googol es un uno seguido de cien ceros; de ahí salió el nombre de Google.",
]
FRASES = [
    "No tienes que ser grande para empezar, pero tienes que empezar para ser grande.",
    "El éxito es la suma de pequeños esfuerzos repetidos día tras día.",
    "Lo que haces hoy puede mejorar todos tus mañanas.",
    "Enseñar es dejar una huella en la vida de una persona para siempre.",
    "No cuentes los días; haz que los días cuenten.",
    "La disciplina es el puente entre las metas y los logros.",
    "Cada experto fue alguna vez un principiante.",
    "El mejor momento para plantar un árbol fue hace veinte años. El segundo mejor es hoy.",
    "Hazlo con miedo, pero hazlo.",
    "La constancia vence lo que la dicha no alcanza.",
    "Un pequeño progreso cada día suma grandes resultados.",
    "No se trata de ser el mejor, sino de ser mejor que ayer.",
    "Quien se atreve a enseñar nunca debe dejar de aprender.",
    "Las cosas difíciles toman tiempo; las imposibles, un poco más.",
    "Cree que puedes y ya estarás a medio camino.",
    "El cansancio de hoy es la fuerza de mañana.",
]
_FUN = (
    (re.compile(r"\b(?:cuentame|dime|echame|echate|sabes|hazme reir con|tirate)\s+(?:un|otro|algun)\s+chiste\b|^(?:jarvis )?(?:un|otro) chiste\b|\bhazme reir\b"), "chiste"),
    (re.compile(r"\b(?:dime|cuentame|dame|sabes)\s+(?:un|otro|algun)\s+dato (?:curioso|interesante|random)\b|^(?:jarvis )?(?:un|otro) dato curioso\b|\bsorprendeme con (?:un dato|algo)\b|\bcuriosidad del dia\b"), "dato"),
    (re.compile(r"\b(?:dame|dime|regalame|necesito)\s+(?:una|otra|alguna)\s+frase (?:motivadora|motivacional|inspiradora|de motivacion|de animo|del dia|bonita)\b|"
                r"^(?:jarvis )?(?:una |otra )?frase (?:motivadora|motivacional|inspiradora|del dia)\b|\bmotivame\b|\bdame animo\b"), "frase"),
)
_last = {"chiste": [], "dato": [], "frase": []}


_FUN_TOPIC = re.compile(r"\b(?:chiste|dato(?: curioso| interesante)?|frase(?: \w+)?)\s+(?:de|del|sobre|acerca|para|con)\s+\w")


def fun(t, rng=None):
    """→ (tipo, texto) sin repetir los últimos. Con tema («un chiste de gatos») no: eso lo inventa la IA."""
    rng = rng or random
    if _FUN_TOPIC.search(t) and not re.search(r"\bfrase (?:de motivacion|de animo|del dia)\b", t):
        return None
    for rx, kind in _FUN:
        if rx.search(t):
            bank = {"chiste": CHISTES, "dato": DATOS, "frase": FRASES}[kind]
            fresh = [x for x in bank if x not in _last[kind]] or bank
            pick = rng.choice(fresh)
            _last[kind].append(pick)
            del _last[kind][:-max(4, len(bank) - 4)]
            return kind, pick
    return None


# ============================================================================ TODO JUNTO
def answer(t, raw=None, today=None, now_utc=None, rng=None):
    """Texto normalizado → (etiqueta, respuesta) o None. No incluye contraseñas (van aparte: no se dicen)."""
    r = world_time(t, now_utc)
    if r:
        return "HORA", r
    r = units(t)
    if r:
        return "CONVERSOR", r
    r = dates(t, today) or until_hour(t)
    if r:
        return "FECHAS", r
    r = chance(t, raw, rng)
    if r:
        return "AZAR", r
    r = spell(t, raw)
    if r:
        return "DELETREO", r
    r = repeat(t, raw)
    if r:
        return "REPITO", r
    f = fun(t, rng)
    if f:
        return {"chiste": "CHISTE", "dato": "DATO CURIOSO", "frase": "FRASE"}[f[0]], f[1]
    return None


# ============================================================================ 12.21: CALCULADORA DE PLATA
_AMT = r"(\d[\d.,]*)\s*(mil(?:lon(?:es)?)?|millon(?:es)?|k|m)?(?:\s+de)?(?:\s+pesos)?"
_PCT = r"(\d+(?:[.,]\d+)?)\s*(?:%|por ciento)"


def _amount(num, mult=None):
    """«250.000», «10 millones», «250 mil», «1,5 millones» → número."""
    s = num.strip(".,")
    if mult and re.fullmatch(r"\d+[.,]\d{1,2}", s):
        v = float(s.replace(",", "."))                 # 1,5 millones
    elif re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", s):
        v = float(re.sub(r"[.,]", "", s))              # 250.000
    else:
        v = float(s.replace(",", "."))
    k = {"mil": 1e3, "k": 1e3, "millon": 1e6, "millones": 1e6, "m": 1e6}.get(mult or "", 1)
    return v * k


def pesos(v):
    return "$" + f"{round(v):,}".replace(",", ".")


def _pct(x):
    return float(x.replace(",", "."))


_IVA = re.compile(rf"\b(?:cuanto es |calcula |saca(?:le)? |cual es )?(?:el |la )?iva (?:de|a|para|del?)\s+{_AMT}|\b{_AMT}\s+(mas|con|sin|menos) (?:el )?iva\b")
_DESC = re.compile(rf"\b{_AMT}\s+(?:con|menos)\s+(?:un |el )?(?:descuento del? )?{_PCT}(?: de descuento)?|\b(?:descuento del? {_PCT}|(?:el |un )?{_PCT} de descuento) (?:a|de|sobre|en)\s+{_AMT}")
_PROP = re.compile(rf"\b(?:divide|reparte|dividir|repartir|parte)\s+(?:una |la )?(?:cuenta|factura)?\s*(?:de\s+)?{_AMT}\s+entre\s+(\d{{1,2}}|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)(?: personas?)?(.*)$")
_PREST = re.compile(rf"\b(?:cuota|cuanto pago|cuanto quedaria pagando|credito|prestamo)\b.*?\b{_AMT}.*?\b(?:a|en|por)\s+(\d{{1,3}})\s+(meses|anos|cuotas).*?\b{_PCT}(?:\s+(mensual|anual|efectivo anual|ea|mes vencido|mv|nominal anual))?"
                    rf"|\b(?:cuota|cuanto pago|credito|prestamo)\b.*?\b{_AMT}.*?\b{_PCT}(?:\s+(mensual|anual|efectivo anual|ea|mes vencido|mv))?.*?\b(?:a|en|por)\s+(\d{{1,3}})\s+(meses|anos|cuotas)")
_INT = re.compile(rf"\binteres (simple|compuesto)\b.*?\b{_AMT}.*?\b{_PCT}(?:\s+(mensual|anual))?.*?\b(?:por|en|durante|a)\s+(\d{{1,3}})\s+(meses|anos)")
_R3 = re.compile(r"\b(?:regla de tres|si)\b.*?\b(\d+(?:[.,]\d+)?)\s+(.{1,40}?)\s+(?:cuestan?|valen?|pesan?|rinden?|son|equivalen? a|necesitan?|gastan?|tardan?|hacen?)\s+(\d[\d.,]*)\b.*?\bcuanto\w*\s+(?:.{0,30}?)(\d+(?:[.,]\d+)?)\s*$")
_NP = {"dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}


def _g(v):
    return f"{v:g}".replace(".", ",")


def money(t, iva_pct=19.0):
    m = _IVA.search(t)
    if m:
        if m.group(1):
            base = _amount(m.group(1), m.group(2))
            iva = base * iva_pct / 100
            return f"El IVA del {_g(iva_pct)} % de {pesos(base)} es {pesos(iva)}. Con IVA queda en {pesos(base + iva)}."
        total, how = _amount(m.group(3), m.group(4)), m.group(5)
        if how in ("mas", "con"):
            return f"{pesos(total)} más IVA del {_g(iva_pct)} % son {pesos(total * (1 + iva_pct / 100))} (el IVA es {pesos(total * iva_pct / 100)})."
        base = total / (1 + iva_pct / 100)
        return f"{pesos(total)} sin el IVA del {_g(iva_pct)} % son {pesos(base)} (el IVA era {pesos(total - base)})."
    m = _DESC.search(t)
    if m:
        base = _amount(m.group(1), m.group(2)) if m.group(1) else _amount(m.group(6), m.group(7))
        p = _pct(m.group(3) or m.group(4) or m.group(5))
        if p >= 100:
            return None
        return f"Con el {_g(p)} % de descuento, {pesos(base)} queda en {pesos(base * (1 - p / 100))}. Te ahorras {pesos(base * p / 100)}."
    m = _PROP.search(t)
    if m:
        total, n, rest = _amount(m.group(1), m.group(2)), _NP.get(m.group(3)) or int(m.group(3)), m.group(4) or ""
        if n < 2:
            return None
        tip = 0.0
        mp = re.search(_PCT, rest)
        if mp:
            tip = _pct(mp.group(1))
        elif re.search(r"\bpropina\b", rest):
            tip = 10.0
        full = total * (1 + tip / 100)
        extra = f" con el {_g(tip)} % de propina ({pesos(full)} en total)" if tip else ""
        return f"{pesos(total)}{extra} entre {n}: cada uno pone {pesos(full / n)}."
    m = _PREST.search(t)
    if m:
        if m.group(1):
            amt, n, unit, p, kind = _amount(m.group(1), m.group(2)), int(m.group(3)), m.group(4), _pct(m.group(5)), m.group(6)
        else:
            amt, p, kind, n, unit = _amount(m.group(7), m.group(8)), _pct(m.group(9)), m.group(10), int(m.group(11)), m.group(12)
        months = n * 12 if unit == "anos" else n
        kind = kind or ("mensual" if p <= 4 else "anual")
        i = p / 100 if kind in ("mensual", "mes vencido", "mv") else (1 + p / 100) ** (1 / 12) - 1
        if months < 1 or months > 480:
            return None
        cuota = amt / months if i == 0 else amt * i / (1 - (1 + i) ** -months)
        total = cuota * months
        rate = f"{_g(p)} % mensual" if kind in ("mensual", "mes vencido", "mv") else f"{_g(p)} % efectivo anual ({i * 100:.2f} % mensual)".replace(".", ",")
        return (f"Préstamo de {pesos(amt)} a {months} meses al {rate}: cuota fija de {pesos(cuota)} al mes. "
                f"En total pagas {pesos(total)}, de los cuales {pesos(total - amt)} son intereses. Es un cálculo aproximado: no incluye seguros ni cuotas de manejo.")
    m = _INT.search(t)
    if m:
        kind, amt, p, per, n, unit = m.group(1), _amount(m.group(2), m.group(3)), _pct(m.group(4)), m.group(5), int(m.group(6)), m.group(7)
        per = per or "anual"
        periods = n if (unit == "meses") == (per == "mensual") else (n * 12 if per == "mensual" else n / 12)
        final = amt * (1 + p / 100 * periods) if kind == "simple" else amt * (1 + p / 100) ** periods
        return (f"Con interés {kind} del {_g(p)} % {per}, {pesos(amt)} en {n} {'años' if unit == 'anos' else 'meses'} se convierten en {pesos(final)}: "
                f"{pesos(final - amt)} de intereses.")
    m = _R3.search(t)
    if m:
        a, what, b, c = _pct(m.group(1)), m.group(2).strip(), _amount(m.group(3)), _pct(m.group(4))
        if a == 0:
            return None
        x = b * c / a
        return f"Regla de tres: si {_say_num(a)} {what} son {_say_num(b)}, entonces {_say_num(c)} son {_say_num(x)}."
    return None


# ============================================================================ 12.21: DÍAS HÁBILES Y FESTIVOS DEL MES
_HABILES = re.compile(r"\bcuantos dias habiles (?:faltan|quedan|hay)\b|\bdias habiles (?:para|hasta|entre|de aqui a)\b")
_FEST_MES = re.compile(r"\b(?:que |cuales (?:son )?(?:los )?)?festivos (?:hay |tiene |trae )?(?:en |de |del )(?:mes de )?(" + "|".join(MESES) + r"|este mes|el proximo mes|este ano|el ano|ano)\b|"
                       r"\b(?:cuantos|que) festivos (?:quedan|faltan|hay)(?: (?:este|en el|en este) ano)?\b")


def workdays(t, today=None, holidays=None):
    """holidays(año) → {fecha: nombre} (lo pasa Jarvis: los festivos de Colombia)."""
    today = today or datetime.date.today()
    if holidays is None:
        return None
    if _HABILES.search(t):
        if "entre" in t:
            ds = [x for x in (_parse_date(p, today, future=False) for p in re.split(r"\s+y\s+(?:el\s+)?", t.split("entre", 1)[-1], maxsplit=1)) if x]
            if len(ds) != 2:
                return None
            a, b = sorted(ds)
        else:
            a, b = today, _parse_date(t, today)
            if b is None:
                return None
        n, fest, d = 0, [], a + datetime.timedelta(days=1)
        while d <= b and (b - a).days < 800:
            name = holidays(d.year).get(d)
            if d.weekday() < 5 and not name:
                n += 1
            elif d.weekday() < 5 and name:
                fest.append(name)
            d += datetime.timedelta(days=1)
        tail = f" Ya descontando {_plural(len(fest), 'festivo', 'festivos')} ({', '.join(fest[:3])})." if fest else ""
        start = "De hoy" if a == today else f"Del {a.day} de {MES_NOMBRE[a.month]}"
        return f"{start} al {_fecha_txt(b)} hay {_plural(n, 'día hábil', 'días hábiles')}, de lunes a viernes.{tail}"
    m = _FEST_MES.search(t)
    if m:
        which = m.group(1)
        if which in MESES or which in ("este mes", "el proximo mes"):
            mo = MESES.get(which) or (today.month if which == "este mes" else today.month % 12 + 1)
            y = today.year + (1 if (which == "el proximo mes" and today.month == 12) or (which in MESES and mo < today.month) else 0)
            hs = [(d, n) for d, n in holidays(y).items() if d.month == mo]
            if not hs:
                return f"En {MES_NOMBRE[mo]} de {y} no hay festivos."
            return f"Festivos de {MES_NOMBRE[mo]} de {y}: " + "; ".join(f"{DIAS[d.weekday()]} {d.day}, {n}" for d, n in hs) + "."
        hs = [(d, n) for d, n in holidays(today.year).items() if d >= today]
        if not hs:
            return "Este año ya no quedan festivos."
        return (f"Este año quedan {_plural(len(hs), 'festivo', 'festivos')}: "
                + "; ".join(f"{DIAS[d.weekday()]} {d.day} de {MES_NOMBRE[d.month]}, {n}" for d, n in hs[:8]) + ".")
    return None


# ============================================================================ 12.21: INGLÉS SIN INTERNET
WORDS = [("achieve", "lograr", "She worked hard to achieve her goals."), ("borrow", "pedir prestado", "Can I borrow your pen?"),
         ("challenge", "reto", "Learning a language is a challenge."), ("deadline", "fecha límite", "The deadline is next Friday."),
         ("improve", "mejorar", "I want to improve my English."), ("schedule", "horario", "What is your schedule today?"),
         ("although", "aunque", "Although it rained, we went out."), ("however", "sin embargo", "It is cheap; however, it is good."),
         ("reliable", "confiable", "He is a reliable friend."), ("attempt", "intento", "This is my second attempt."),
         ("advice", "consejo", "Let me give you some advice."), ("available", "disponible", "Are you available tomorrow?"),
         ("behavior", "comportamiento", "His behavior was excellent."), ("purpose", "propósito", "What is the purpose of this meeting?"),
         ("knowledge", "conocimiento", "Knowledge is power."), ("to realize", "darse cuenta", "I realized I was wrong."),
         ("actually", "en realidad", "Actually, I prefer tea."), ("eventually", "con el tiempo", "Eventually, he found a job."),
         ("to attend", "asistir", "I will attend the class."), ("library", "biblioteca", "The library opens at eight."),
         ("to remind", "recordarle a alguien", "Remind me to call my mother."), ("to afford", "poder pagar", "I can't afford a new car."),
         ("to avoid", "evitar", "Avoid sugary drinks."), ("enough", "suficiente", "We have enough time."),
         ("to share", "compartir", "Please share your screen."), ("skill", "habilidad", "Reading is an important skill."),
         ("to manage", "arreglárselas, administrar", "She manages a small team."), ("issue", "problema, asunto", "We need to solve this issue."),
         ("to require", "requerir", "This job requires patience."), ("to suggest", "sugerir", "I suggest we start now."),
         ("grateful", "agradecido", "I am grateful for your help."), ("to struggle", "luchar, costar trabajo", "I struggle with pronunciation."),
         ("goal", "meta", "My goal is to speak fluently."), ("homework", "tarea", "Did you finish your homework?"),
         ("to hand in", "entregar", "Hand in your essay on Monday."), ("to figure out", "resolver, entender", "I can't figure out this problem."),
         ("to look forward to", "esperar con ilusión", "I look forward to seeing you."), ("to run out of", "quedarse sin", "We ran out of milk."),
         ("to get along", "llevarse bien", "I get along with my neighbors."), ("to give up", "rendirse", "Never give up."),
         ("worth", "que vale la pena", "The book is worth reading."), ("busy", "ocupado", "I am busy this afternoon."),
         ("weather", "clima", "The weather is nice today."), ("to hope", "esperar (desear)", "I hope you feel better."),
         ("to wait", "esperar (aguardar)", "Wait for me at the door."), ("embarrassed", "avergonzado", "I was embarrassed by my mistake."),
         ("sensible", "sensato", "That is a sensible decision."), ("fabric", "tela", "This fabric is very soft."),
         ("to assist", "ayudar", "Can I assist you?"), ("currently", "actualmente", "I am currently studying.")]
_WORD_DAY = re.compile(r"\bpalabra del dia(?: en ingles)?\b|\b(?:ensename|dime|dame) (?:una|otra) palabra (?:nueva )?en ingles\b|\bvocabulario (?:de|en) ingles\b")


def word_of_day(t, today=None, rng=None):
    if not _WORD_DAY.search(t):
        return None
    today = today or datetime.date.today()
    i = rng.randrange(len(WORDS)) if rng is not None and "otra" in t else today.toordinal() % len(WORDS)
    en, es, ex = WORDS[i]
    return en, es, ex
