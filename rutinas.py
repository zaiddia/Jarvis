"""Rutinas con nombre: varias órdenes de Jarvis seguidas con una sola frase.

    «modo clase»  ->  activa el videobeam · volumen al 40 · silencia las notificaciones ·
                      abre el tablero · decir Modo clase listo

Cada paso es una orden normal de Jarvis (la misma frase que dirías), más dos extras:
    esperar 5          pausa 5 segundos
    decir <texto>      Jarvis lo dice en voz alta

Se guardan en rutinas.json (carpeta de configuración). jarvis.py las ejecuta.
"""
import copy
import difflib
import json
import os
import re
import threading
import unicodedata

_lock = threading.Lock()
_path = None
routines = []        # [{"nombre": str, "frases": [str], "pasos": [str]}]

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
    return {"nombre": str(r.get("nombre", "")).strip()[:60],
            "frases": [str(x).strip()[:80] for x in (r.get("frases") or []) if str(x).strip()][:10],
            "pasos": [str(x).strip()[:300] for x in (r.get("pasos") or []) if str(x).strip()][:40]}


def parse_lines(text):
    return [l.strip(" -•\t") for l in str(text or "").splitlines() if l.strip(" -•\t")]


def upsert(nombre, frases_text, pasos_text, old=None):
    nombre = str(nombre or "").strip()[:60]
    if not nombre:
        raise ValueError("Ponle un nombre a la rutina.")
    pasos = parse_lines(pasos_text)
    if not pasos:
        raise ValueError("Escribe al menos un paso (una orden por línea).")
    frases = [f.strip() for f in re.split(r"[,\n]", str(frases_text or "")) if f.strip()]
    if normalize(nombre) not in [normalize(f) for f in frases]:
        frases.insert(0, nombre)
    new = _clean({"nombre": nombre, "frases": frases, "pasos": pasos})
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
