"""Rutinas con nombre: varias órdenes de Jarvis seguidas con una sola frase.

    «modo clase»  ->  activa el videobeam · volumen al 40 · silencia las notificaciones ·
                      abre el tablero · decir Modo clase listo

Cada paso es una orden normal de Jarvis (la misma frase que dirías), más dos extras:
    esperar 5          pausa 5 segundos
    decir <texto>      Jarvis lo dice en voz alta

Desde la 6.8 una rutina también puede lanzarse sola («cuando»):
    07:30            todos los días a esa hora
    07:30 lun-vie    de lunes a viernes (también «sab,dom», «martes y jueves», «fines de semana»…)
    al iniciar       al arrancar Jarvis (normalmente, al encender el equipo)
    al volver        al volver al equipo tras 10 minutos o más sin usarlo

Se guardan en rutinas.json (carpeta de configuración). jarvis.py las ejecuta.
"""
import datetime
import copy
import difflib
import json
import os
import re
import threading
import unicodedata

_lock = threading.Lock()
_path = None
routines = []        # [{"nombre": str, "frases": [str], "pasos": [str], "cuando": str}]

DEFAULTS = [
    {"nombre": "Modo clase",
     "frases": ["modo clase", "empieza la clase", "empecemos la clase", "vamos a empezar la clase"],
     "pasos": ["activa el videobeam", "esperar 2", "volumen al 40", "silencia las notificaciones",
               "abre el tablero", "decir Modo clase listo. ¡Buena clase!"]},
    {"nombre": "Fin de clase",
     "frases": ["fin de clase", "terminamos la clase", "se acabó la clase", "termina la clase"],
     "pasos": ["pon el videobeam en solo pc", "activa las notificaciones", "volumen al 30",
               "decir Clase terminada. Buen trabajo."]},
    {"nombre": "Modo planeación",
     "frases": ["modo planeación", "voy a planear", "modo planificación", "voy a preparar clases"],
     "pasos": ["silencia las notificaciones", "abre word", "abre documentos",
               "decir Listo para planear. Si quieres, pídeme un quiz o un taller."]},
]


def normalize(text):
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "rutinas.json")
    load()


def load():
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, list):
            routines[:] = [_clean(r) for r in d if isinstance(r, dict) and r.get("nombre")]
            return
    except FileNotFoundError:
        routines[:] = copy.deepcopy(DEFAULTS)         # primera vez: rutinas de ejemplo
        save()
        return
    except (ValueError, OSError, TypeError):
        pass


def save():
    if not _path:
        return
    os.makedirs(os.path.dirname(_path), exist_ok=True)
    tmp = _path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(routines, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path)


def _clean(r):
    when = parse_when(r.get("cuando", ""))
    return {"nombre": str(r.get("nombre", "")).strip()[:60],
            "frases": [str(x).strip()[:80] for x in (r.get("frases") or []) if str(x).strip()][:10],
            "pasos": [str(x).strip()[:300] for x in (r.get("pasos") or []) if str(x).strip()][:40],
            "cuando": when["text"] if when else ""}


# ----------------------------------------------------------------------------- cuándo se lanza sola

_DAYS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
_CLOCK = re.compile(r"(?P<h>\d{1,2})(?:[:.h](?P<m>\d{2}))?\s*(?P<ap>a\.?\s?m\b\.?|p\.?\s?m\b\.?|de la manana|de la tarde|de la noche|de la madrugada)?")


def _day_index(w):
    w = normalize(w)
    if len(w) < 3:
        return -1
    if w.startswith("mi"):
        return 2
    for i, d in enumerate(_DAYS):
        if w.startswith(d):
            return i
    return -1


def _days_text(days):
    if days == [True] * 5 + [False] * 2:
        return "lun-vie"
    if days == [False] * 5 + [True] * 2:
        return "sab,dom"
    return ",".join(d for d, on in zip(_DAYS, days) if on)


def parse_when(text):
    """«7:30 de lunes a viernes» → {"kind": "hora", "at": (7, 30), "days": [...], "text": "07:30 lun-vie"};
    «al iniciar» → {"kind": "inicio", …}; «al volver» → {"kind": "volver", …}. None si está vacío o no se entiende."""
    w = unicodedata.normalize("NFD", str(text or "").lower())
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    w = re.sub(r"[^\w\s:.,-]", " ", w)          # conserva «07:30», «lun-vie», «sab,dom»
    w = re.sub(r"\s+", " ", w).strip()
    if not w:
        return None
    if re.search(r"\b(?:al )?(?:iniciar|inicio|encender|arrancar|arranque|prender|empezar)\b", w):
        return {"kind": "inicio", "text": "al iniciar"}
    if re.search(r"\b(?:al |cuando )?(?:volver|vuelva|vuelvo|regresar|regrese|regreso|vuelta|llegue|llego)\b", w):
        return {"kind": "volver", "text": "al volver"}
    m = _CLOCK.search(w)
    if not m:
        return None
    h, mi = int(m.group("h")), int(m.group("m") or 0)
    ap = (m.group("ap") or "").replace(" ", "").replace(".", "")
    if (ap.startswith("p") or "tarde" in ap or "noche" in ap) and h < 12:
        h += 12
    if (ap.startswith("a") or "madrugada" in ap or "manana" in ap or "noche" in ap) and h == 12:
        h = 0                                     # «12 de la noche» = 00:00
    if h > 23 or mi > 59:
        return None
    rest = (w[:m.start()] + " " + w[m.end():]).strip()
    days = [True] * 7
    if re.search(r"entre semana|laborables|lunes a viernes|lun\s*-\s*vie|dias de trabajo|dias habiles", rest):
        days = [True] * 5 + [False] * 2
    elif re.search(r"fin(?:es)? de semana|sab(?:ado)?s?\s*(?:,|y)\s*dom", rest):
        days = [False] * 5 + [True] * 2
    else:
        rng = re.search(r"\b([a-z]{3,9})\s*(?:-|\ba\b)\s*([a-z]{3,9})\b", rest)
        a, b = (_day_index(rng.group(1)), _day_index(rng.group(2))) if rng else (-1, -1)
        if a >= 0 and b >= 0:
            days, i = [False] * 7, a
            while True:
                days[i] = True
                if i == b:
                    break
                i = (i + 1) % 7
        else:
            listed = sorted({i for i in (_day_index(x) for x in re.findall(r"[a-z]{3,9}", rest)) if i >= 0})
            if listed and "todos los dias" not in rest and "diario" not in rest:
                days = [i in listed for i in range(7)]
    t = f"{h:02d}:{mi:02d}" + ("" if all(days) else " " + _days_text(days))
    return {"kind": "hora", "at": (h, mi), "days": days, "text": t}


def when_spoken(text):
    """Para decirlo: «a las 7:30 de lunes a viernes», «al iniciar el equipo»."""
    w = parse_when(text)
    if not w:
        return ""
    if w["kind"] == "inicio":
        return "al iniciar el equipo"
    if w["kind"] == "volver":
        return "cuando vuelves al equipo"
    h, mi = w["at"]
    d = _days_text(w["days"])
    days = " todos los días" if all(w["days"]) else " de lunes a viernes" if d == "lun-vie" else " los fines de semana" if d == "sab,dom" else f" ({d})"
    return f"a las {h}:{mi:02d}" + days


def due(now, last_runs):
    """Rutinas con hora que tocan ahora (en sus 10 minutos siguientes, por si el equipo estaba dormido)
    y no se han lanzado hoy. last_runs: {nombre: "AAAA-MM-DD"}."""
    out = []
    today = now.date().isoformat()
    for r in routines:
        w = parse_when(r.get("cuando", ""))
        if not w or w["kind"] != "hora" or not w["days"][now.weekday()] or last_runs.get(r["nombre"]) == today:
            continue
        start = now.replace(hour=w["at"][0], minute=w["at"][1], second=0, microsecond=0)
        if start <= now < start + datetime.timedelta(minutes=10):
            out.append(r)
    return out


def with_kind(kind):
    return [r for r in routines if (parse_when(r.get("cuando", "")) or {}).get("kind") == kind]


def parse_lines(text):
    return [l.strip(" -•\t") for l in str(text or "").splitlines() if l.strip(" -•\t")]


def upsert(nombre, frases_text, pasos_text, old=None, cuando=""):
    nombre = str(nombre or "").strip()[:60]
    if not nombre:
        raise ValueError("Ponle un nombre a la rutina.")
    pasos = parse_lines(pasos_text)
    if not pasos:
        raise ValueError("Escribe al menos un paso (una orden por línea).")
    frases = [f.strip() for f in re.split(r"[,\n]", str(frases_text or "")) if f.strip()]
    if str(cuando or "").strip() and not parse_when(cuando):
        raise ValueError("No entendí cuándo debe lanzarse. Usa por ejemplo 07:30, 07:30 lun-vie, al iniciar o al volver.")
    if normalize(nombre) not in [normalize(f) for f in frases]:
        frases.insert(0, nombre)
    new = _clean({"nombre": nombre, "frases": frases, "pasos": pasos, "cuando": cuando})
    with _lock:
        key = normalize(old or nombre)
        for i, r in enumerate(routines):
            if normalize(r["nombre"]) == key:
                routines[i] = new
                break
        else:
            routines.append(new)
        save()
    return new


def delete(nombre):
    with _lock:
        routines[:] = [r for r in routines if normalize(r["nombre"]) != normalize(nombre)]
        save()


def restore_defaults():
    with _lock:
        names = {normalize(r["nombre"]) for r in routines}
        for d in DEFAULTS:
            if normalize(d["nombre"]) not in names:
                routines.append(copy.deepcopy(d))
        save()


_PREFIX = re.compile(r"^(?:jarvis |por favor )?(?:activa(?:r)?|inicia(?:r)?|ejecuta(?:r)?|pon(?:er)?|lanza(?:r)?|"
                     r"arranca(?:r)?|haz|corre)?\s*(?:el |la )?(?:rutina(?: de| del)? )?(?:el |la )?")


def find(t):
    """La rutina que corresponde a lo dicho («modo clase», «activa la rutina de fin de clase»)."""
    t = normalize(t)
    core = _PREFIX.sub("", t).strip()
    for cand in (t, core):
        for r in routines:
            for f in [r["nombre"], *r["frases"]]:
                if cand == normalize(f):
                    return r
    # tolera pequeñas diferencias de reconocimiento («modo clases»)
    best, score = None, 0.0
    for r in routines:
        for f in [r["nombre"], *r["frases"]]:
            s = difflib.SequenceMatcher(None, core, normalize(f)).ratio()
            if s > score:
                best, score = r, s
    return best if score >= 0.88 and len(core) >= 6 else None


def step_kind(step):
    """('esperar', segundos) | ('decir', texto) | ('orden', texto)"""
    s = step.strip()
    m = re.match(r"^(?:espera|esperar|pausa)\s+(\d{1,3})\s*(?:s|seg|segundos?)?\.?$", normalize(s))
    if m:
        return "esperar", min(int(m.group(1)), 300)
    m = re.match(r"^(?:decir|di|dice)\s*:?\s+(.+)$", s, re.I)
    if m:
        return "decir", m.group(1).strip()
    return "orden", s
