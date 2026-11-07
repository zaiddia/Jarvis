"""Casa inteligente con Home Assistant (12.9). Lógica pura: qué aparato nombraste y qué servicio llamar.

«Enciende la luz de la sala», «apaga el ventilador», «luz del cuarto al 40 %», «¿está prendida la luz de la cocina?».
Se conecta a TU Home Assistant (en tu red) con un token que creas en tu perfil de Home Assistant.
"""
import difflib
import re
import unicodedata

DOMAINS = ("light", "switch", "fan", "cover", "media_player", "climate", "scene", "script", "input_boolean", "vacuum", "lock")
ON_WORDS = r"(?:enciende|prende|activa|abre|pon)"
OFF_WORDS = r"(?:apaga|desactiva|cierra)"
_ARTS = r"(?:el|la|los|las|mi|mis)\s+"
NOT_HOME = re.compile(r"\b(?:equipo|pc|computador|portatil|pantalla|monitor|microfono|videobeam|proyector|notificaciones|wifi|wi fi|"
                      r"bluetooth|ia|inteligencia|motor|copiloto|camara|modo|ahorro|plan|musica|cancion|radio|volumen|sonido|"
                      r"presentacion|diapositiva|temporizador|alarma|jarvis|voz|subtitulos|tablero|pizarra)\b")


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%]", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


def parse(t):
    """→ {"accion": on|off|estado, "nombre", "brillo"} o None. t normalizado."""
    t = norm(t)
    m = re.match(rf"^(?:jarvis\s+)?{ON_WORDS}\s+(?:{_ARTS})?(.+?)(?:\s+al?\s+(\d{{1,3}})\s*%?)?$", t)
    if m:
        return {"accion": "on", "nombre": m.group(1), "brillo": int(m.group(2)) if m.group(2) else None}
    m = re.match(rf"^(?:jarvis\s+)?{OFF_WORDS}\s+(?:{_ARTS})?(.+)$", t)
    if m:
        return {"accion": "off", "nombre": m.group(1), "brillo": None}
    m = re.match(rf"^(?:jarvis\s+)?(?:pon\s+)?(?:{_ARTS})?((?:luz|luces|lampara|bombillo)\b.*?)\s+al?\s+(\d{{1,3}})\s*%?$", t)
    if m:
        return {"accion": "on", "nombre": m.group(1), "brillo": int(m.group(2))}
    m = re.match(rf"^(?:jarvis\s+)?(?:esta|estan)\s+(?:prendid[oa]s?|encendid[oa]s?|apagad[oa]s?|abiert[oa]s?|cerrad[oa]s?)\s+(?:{_ARTS})?(.+)$", t)
    if m:
        return {"accion": "estado", "nombre": m.group(1), "brillo": None}
    return None


def entities(states):
    """De /api/states: [{"id","nombre","dominio","estado"}] de los aparatos que se pueden manejar."""
    out = []
    for s in states or []:
        eid = str(s.get("entity_id", ""))
        dom = eid.split(".", 1)[0]
        if dom not in DOMAINS:
            continue
        name = (s.get("attributes") or {}).get("friendly_name") or eid.split(".", 1)[-1].replace("_", " ")
        out.append({"id": eid, "nombre": str(name), "dominio": dom, "estado": str(s.get("state", ""))})
    return out


def match(ents, name, cutoff=0.72):
    """El aparato que nombraste (o None si no hay uno claro)."""
    n = norm(name)
    if not n or NOT_HOME.search(n):
        return None
    best, score = None, 0.0
    for e in ents:
        cand = norm(e["nombre"])
        s = 1.0 if cand == n else difflib.SequenceMatcher(None, n, cand).ratio()
        if n in cand.split() or (len(n) > 3 and (n in cand or cand in n)):
            s = max(s, 0.86)
        if s > score:
            best, score = e, s
    return best if score >= cutoff else None


def service(e, accion, brillo=None):
    """(dominio, servicio, datos) para la API de Home Assistant."""
    dom = e["dominio"]
    data = {"entity_id": e["id"]}
    if dom == "cover":
        return dom, "open_cover" if accion == "on" else "close_cover", data
    if dom == "lock":
        return dom, "unlock" if accion == "on" else "lock", data
    if dom in ("scene", "script"):
        return dom, "turn_on", data
    if dom == "vacuum":
        return dom, "start" if accion == "on" else "return_to_base", data
    if dom == "light" and brillo is not None and accion == "on":
        data["brightness_pct"] = max(1, min(100, int(brillo)))
    return dom, "turn_on" if accion == "on" else "turn_off", data


def spoken_state(e):
    st = e["estado"]
    word = {"on": "encendida" if e["dominio"] == "light" else "encendido", "off": "apagada" if e["dominio"] == "light" else "apagado",
            "open": "abierta", "closed": "cerrada", "locked": "con seguro", "unlocked": "sin seguro",
            "unavailable": "sin conexión"}.get(st, st)
    return f"{e['nombre']}: {word}."
