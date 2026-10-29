"""Habilidades instalables: un archivo .json por habilidad, que se comparte y se instala en un clic.

    {
      "nombre": "Wikipedia",
      "descripcion": "Abre el artículo de Wikipedia de un tema",
      "autor": "Profe Ana",
      "frases": ["abre wikipedia de {tema}", "busca {tema} en wikipedia"],
      "accion": "abrir",                       # abrir | decir | ia | pasos
      "url": "https://es.wikipedia.org/wiki/{tema}"
    }

Acciones:
    abrir   abre una dirección web (solo http/https; lo dicho va codificado en la dirección)
    decir   dice un texto («Hoy es {fecha}, son las {hora}»)
    ia      le pide algo a la IA con lo dicho («Traduce al {idioma}: {texto}»)
    pasos   varias órdenes normales de Jarvis, como una rutina (las delicadas nunca se ejecutan)

En las frases, {nombre} es un hueco: lo que digas ahí se usa en la acción. Se guardan en la carpeta
«habilidades» de la configuración. Este módulo no ejecuta nada: jarvis.py lo hace con sus reglas.
"""
import datetime
import json
import os
import re
import threading
import unicodedata
import urllib.parse

_lock = threading.Lock()
_dir = None
skills = []          # [{"nombre", "descripcion", "autor", "frases", "accion", "texto", "url", "pasos", "archivo"}]
ACTIONS = ("abrir", "decir", "ia", "pasos")
MAX_FILE = 64 * 1024
MAX_SKILLS = 100

EXAMPLES = [
    {"nombre": "Wikipedia", "descripcion": "Abre el artículo de Wikipedia de un tema", "autor": "Jarvis",
     "frases": ["abre wikipedia de {tema}", "busca {tema} en wikipedia", "wikipedia {tema}"],
     "accion": "abrir", "url": "https://es.wikipedia.org/wiki/Especial:Buscar?search={tema}"},
    {"nombre": "Traductor", "descripcion": "Traduce una frase a otro idioma", "autor": "Jarvis",
     "frases": ["como se dice {texto} en {idioma}", "traduce {texto} al {idioma}"],
     "accion": "ia", "texto": "Traduce al {idioma} esta frase y dime solo la traducción, con su pronunciación si ayuda: «{texto}»"},
    {"nombre": "Modo concentración", "descripcion": "Silencia las notificaciones y pone 25 minutos de trabajo", "autor": "Jarvis",
     "frases": ["modo concentracion", "quiero concentrarme", "modo enfoque"],
     "accion": "pasos", "pasos": ["silencia las notificaciones", "pon un temporizador de 25 minutos para concentrarme",
                                  "decir Modo concentración: 25 minutos sin distracciones. Te aviso al terminar."]},
    {"nombre": "Dato del día", "descripcion": "Un dato curioso para empezar la clase", "autor": "Jarvis",
     "frases": ["dato del dia", "dame un dato curioso de {tema}", "dato curioso"],
     "accion": "ia", "texto": "Dame un dato curioso, cierto y sorprendente{ sobre {tema}}, en dos frases, para contarlo en clase."},
]


def normalize(text):
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s{}]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", normalize(name)).strip("-")
    return (s or "habilidad")[:50]


def validate(d):
    """Comprueba y limpia una habilidad. Lanza ValueError con un mensaje claro."""
    if not isinstance(d, dict):
        raise ValueError("El archivo no es una habilidad de Jarvis (debe ser un objeto JSON).")
    nombre = str(d.get("nombre", "")).strip()[:60]
    if not nombre:
        raise ValueError("A la habilidad le falta el «nombre».")
    frases = [str(f).strip()[:120] for f in (d.get("frases") or []) if str(f).strip()][:12]
    if not frases:
        raise ValueError("La habilidad necesita al menos una frase en «frases».")
    accion = str(d.get("accion", "")).strip().lower()
    if accion not in ACTIONS:
        raise ValueError(f"«accion» debe ser una de: {', '.join(ACTIONS)}.")
    out = {"nombre": nombre, "descripcion": str(d.get("descripcion", "")).strip()[:200],
           "autor": str(d.get("autor", "")).strip()[:60], "frases": frases, "accion": accion}
    if accion == "abrir":
        url = str(d.get("url", "")).strip()
        if not re.match(r"https?://[^\s]+$", url):
            raise ValueError("Para «abrir», la «url» debe empezar por http:// o https://.")
        out["url"] = url[:500]
    elif accion in ("decir", "ia"):
        texto = str(d.get("texto", "")).strip()
        if not texto:
            raise ValueError(f"Para «{accion}» hace falta el «texto».")
        out["texto"] = texto[:1500]
    else:
        pasos = [str(p).strip()[:300] for p in (d.get("pasos") or []) if str(p).strip()][:30]
        if not pasos:
            raise ValueError("Para «pasos» hace falta la lista «pasos».")
        out["pasos"] = pasos
    return out


def configure(config_dir):
    global _dir
    _dir = os.path.join(config_dir, "habilidades")
    first = not os.path.isdir(_dir)
    os.makedirs(_dir, exist_ok=True)
    if first:
        for e in EXAMPLES:
            _write(e)
    load()


def _write(d):
    path = os.path.join(_dir, _slug(d["nombre"]) + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def load():
    """Lee la carpeta. Devuelve los errores [(archivo, motivo)] de las que no valen."""
    errors, out = [], []
    if not _dir or not os.path.isdir(_dir):
        skills[:] = []
        return errors
    for name in sorted(os.listdir(_dir)):
        if not name.lower().endswith(".json"):
            continue
        p = os.path.join(_dir, name)
        try:
            if os.path.getsize(p) > MAX_FILE:
                raise ValueError("el archivo es demasiado grande")
            with open(p, encoding="utf-8") as f:
                d = validate(json.load(f))
            d["archivo"] = name
            out.append(d)
        except (ValueError, OSError) as e:
            errors.append((name, str(e)))
        if len(out) >= MAX_SKILLS:
            break
    with _lock:
        skills[:] = out
    return errors


def install(text):
    """Instala (o actualiza) una habilidad a partir del contenido de su .json."""
    if len(text.encode("utf-8")) > MAX_FILE:
        raise ValueError("El archivo es demasiado grande para ser una habilidad.")
    try:
        d = json.loads(text)
    except ValueError:
        raise ValueError("El archivo no es un JSON válido.")
    d = validate(d)
    with _lock:
        if not any(normalize(s["nombre"]) == normalize(d["nombre"]) for s in skills) and len(skills) >= MAX_SKILLS:
            raise ValueError(f"Ya hay {MAX_SKILLS} habilidades instaladas.")
        _write(d)
    load()
    return d


def delete(nombre):
    with _lock:
        for s in skills:
            if normalize(s["nombre"]) == normalize(nombre):
                try:
                    os.remove(os.path.join(_dir, s["archivo"]))
                except OSError:
                    pass
    load()


def export(nombre):
    for s in skills:
        if normalize(s["nombre"]) == normalize(nombre):
            return json.dumps({k: v for k, v in s.items() if k != "archivo"}, ensure_ascii=False, indent=2)
    return None


def _pattern(frase):
    """«busca {tema} en wikipedia» → regex con el grupo «tema»."""
    parts = re.split(r"(\{\w+\})", normalize(frase))
    rx = ""
    for p in parts:
        m = re.fullmatch(r"\{(\w+)\}", p)
        rx += rf"(?P<{m.group(1)}>.+?)" if m else re.escape(p)
    return re.compile(r"^(?:jarvis |oye |por favor )*" + rx + r"$")


def match(text):
    """(habilidad, {hueco: valor}) para lo dicho, o None. Gana la frase más larga (la más concreta)."""
    t = normalize(text)
    best = None
    for s in skills:
        for f in s["frases"]:
            try:
                m = _pattern(f).match(t)
            except re.error:
                continue
            if m:
                fixed = len(re.sub(r"\{\w+\}", "", f))
                if best is None or fixed > best[2]:
                    best = (s, {k: v.strip() for k, v in m.groupdict().items()}, fixed)
    return (best[0], best[1]) if best else None


def fill(template, values, url=False):
    """Pone los valores en la plantilla. «{ sobre {tema}}» es opcional: desaparece si no hay tema."""
    now = datetime.datetime.now()
    vals = {"fecha": now.strftime("%d/%m/%Y"), "hora": now.strftime("%H:%M"), **{k: v for k, v in values.items() if v}}

    def opt(m):
        inner = m.group(1)
        keys = re.findall(r"\{(\w+)\}", inner)
        return inner if keys and all(k in vals for k in keys) else ""
    out = re.sub(r"\{([^{}]*\{\w+\}[^{}]*)\}", opt, template)
    return re.sub(r"\{(\w+)\}", lambda m: (urllib.parse.quote(vals.get(m.group(1), ""), safe="") if url
                                           else vals.get(m.group(1), "")), out)


def snapshot():
    return [{k: v for k, v in s.items()} for s in skills]
