"""Alertas de sismos con datos del USGS (gratis, sin clave, se actualiza cada minuto).

Solo arma direcciones, interpreta el GeoJSON, calcula distancias y redacta la frase;
jarvis.py hace las peticiones y decide cuándo avisar.

Dos niveles:
  · 2 (alerta): sismo fuerte y cerca de ti  -> tono urgente
  · 1 (aviso):  sismo notable en la región   -> tono suave
"""
import datetime
import math

# Feeds del USGS (magnitud 2.5+ de la última hora; y los significativos del día por si acaso)
FEED_BASE = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary"
FEEDS = [f"{FEED_BASE}/2.5_hour.geojson", f"{FEED_BASE}/significant_day.geojson"]
# Caja aproximada de Colombia (si no hay ciudad puesta, solo avisa de sismos aquí)
CO_BOX = (-4.5, 13.5, -82.0, -66.0)       # lat_min, lat_max, lon_min, lon_max


def parse(geojson):
    out = []
    for f in (geojson or {}).get("features", []):
        p = f.get("properties") or {}
        g = f.get("geometry") or {}
        c = g.get("coordinates") or [None, None, None]
        if p.get("mag") is None or c[0] is None:
            continue
        out.append({"id": f.get("id", ""), "mag": float(p["mag"]), "place": p.get("place") or "",
                    "lon": float(c[0]), "lat": float(c[1]), "depth": float(c[2] or 0),
                    "time": int(p.get("time") or 0), "tz": p.get("tz")})
    return out


def haversine(lat1, lon1, lat2, lon2):
    """Distancia en km entre dos puntos."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(min(1.0, math.sqrt(a)))


def _in_box(lat, lon, box=CO_BOX):
    return box[0] <= lat <= box[1] and box[2] <= lon <= box[3]


def level(q, user=None, min_mag=4.5):
    """Nivel de alerta para el sismo q (0 = no avisar).
    user = (lat, lon) del usuario, o None (entonces solo cuentan los de la caja de Colombia)."""
    mag = q["mag"]
    dist = haversine(user[0], user[1], q["lat"], q["lon"]) if user else None
    if dist is not None:
        if mag >= 5.0 and dist <= 300:
            return 2
        if mag >= 6.5 and dist <= 700:
            return 2
        if mag >= min_mag and dist <= 600:
            return 1
        if mag >= 6.0 and dist <= 1500:
            return 1
        return 0
    # sin ubicación: solo sismos dentro de Colombia
    if not _in_box(q["lat"], q["lon"]):
        return 0
    if mag >= 5.0:
        return 2
    if mag >= min_mag:
        return 1
    return 0


def _ago(time_ms, now=None):
    if not time_ms:
        return ""
    now = now or datetime.datetime.now().timestamp()
    mins = int((now - time_ms / 1000) / 60)
    if mins < 1:
        return "hace un momento"
    if mins == 1:
        return "hace un minuto"
    if mins < 60:
        return f"hace {mins} minutos"
    return "hace más de una hora"


def _place_es(place):
    """«23 km SW of City, Country» -> algo legible en español."""
    place = (place or "").strip()
    dirs = {"N": "al norte", "S": "al sur", "E": "al este", "W": "al oeste", "NE": "al noreste",
            "NW": "al noroeste", "SE": "al sureste", "SW": "al suroeste", "NNE": "al norte", "NNW": "al norte",
            "ENE": "al este", "ESE": "al este", "SSE": "al sur", "SSW": "al sur", "WNW": "al oeste", "WSW": "al oeste"}
    import re
    m = re.match(r"^\s*(\d+)\s*km\s+([NSEW]+)\s+of\s+(.+)$", place)
    if m:
        return f"a {m.group(1)} kilómetros {dirs.get(m.group(2), '')} de {m.group(3)}".replace("  ", " ")
    if place.lower().startswith("near "):
        return "cerca de " + place[5:]
    return "en " + place if place else ""


def describe(q, lvl, user=None, now=None):
    """Frase hablada del sismo."""
    mag = q["mag"]
    lugar = _place_es(q["place"])
    cuando = _ago(q["time"], now)
    dist = haversine(user[0], user[1], q["lat"], q["lon"]) if user else None
    fuerza = ("fuerte" if mag >= 6 else "moderado" if mag >= 5 else "leve")
    inicio = "Atención: sismo" if lvl >= 2 else "Aviso: temblor"
    txt = f"{inicio} de magnitud {mag:.1f}, {fuerza}, {lugar}".rstrip(", ")
    if cuando:
        txt += f", {cuando}"
    txt += "."
    if dist is not None:
        txt += f" A unos {int(round(dist / 10) * 10)} kilómetros de ti."
    if lvl >= 2:
        txt += (" Si lo sientes, aléjate de ventanas y objetos que puedan caer, y ubícate en un punto seguro. "
                "Con tus estudiantes, mantén la calma y sigan el protocolo de evacuación.")
    return txt


def short(q):
    """Una línea para el registro."""
    return f"M{q['mag']:.1f} {q['place']}".strip()
