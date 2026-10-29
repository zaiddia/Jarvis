"""Memoria que aprende sola: cosas que el usuario cuenta de sí mismo o sus gustos, sin
tener que decir «recuerda». Jarvis las guarda y las tiene en cuenta al responder.

Es determinista (no inventa): solo guarda una frase cuando empieza por un giro claro de
preferencia o dato personal («trabajo en…», «prefiero…», «soy profe de…», «mi colegio es…»).
Se ven y se borran en Ajustes › Memoria.
"""
import json
import os
import re
import threading
import unicodedata

_lock = threading.Lock()
_path = None
facts = []        # [{"id": str, "texto": str, "fecha": "YYYY-MM-DD"}]
MAX = 200

# Giros con los que una frase es claramente un dato o preferencia del usuario.
_LEADS = [
    r"trabajo en", r"trabajo como", r"soy (?:profe|profesor|profesora|docente|maestr[oa]) de",
    r"soy de", r"vivo en", r"mi colegio es", r"mi colegio se llama", r"mi institucion es",
    r"enseno", r"dicto (?:clase|clases)? ?(?:de|en)?", r"doy clase[s]? de", r"mi curso es",
    r"mis estudiantes", r"mi grado es", r"mi materia es", r"mi area es",
    r"prefiero", r"me gusta que", r"no me gusta que", r"odio que", r"me molesta que",
    r"siempre (?:uso|hago|empiezo)", r"normalmente", r"por lo general",
    r"mi correo es", r"mi numero es", r"mi cumpleanos es", r"mi aniversario es",
    r"recuerda siempre que", r"ten en cuenta que", r"para que sepas",
    # v6.8: su gente, sus mascotas y sus gustos («mi hermana se llama Ana», «me gusta el vallenato»)
    r"mis? (?:" + "|".join([
        "esposa", "esposo", "mujer", "marido", "novia", "novio", "pareja", "hijo", "hija", "hijos", "hijas",
        "hermano", "hermana", "hermanos", "hermanas", "mama", "papa", "madre", "padre", "padres", "abuela", "abuelo",
        "abuelos", "tio", "tia", "primo", "prima", "sobrino", "sobrina", "suegra", "suegro", "cunado", "cunada",
        "amigo", "amiga", "mejor amigo", "mejor amiga", "jefe", "jefa", "coordinador", "coordinadora", "rector", "rectora",
        "perro", "perra", "gato", "gata", "mascota", "mascotas", "color favorito", "comida favorita", "plato favorito",
        "equipo", "cancion favorita", "grupo favorito", "artista favorito", "cantante favorito", "pelicula favorita",
        "serie favorita", "libro favorito", "deporte favorito", "bebida favorita", "carro", "moto", "barrio", "ciudad",
        "signo"]) + r")(?: [a-z]+){0,2} (?:se llama|se llaman|es|son|cumple|cumplen|nacio|vive|viven|trabaja)",
    r"(?:no )?me (?:gusta|gustan|encanta|encantan|fascina|fascinan)(?! que)", r"odio (?!que)",
    r"tengo (?:un|una|dos|tres|cuatro) (?:perro|perra|perros|gato|gata|gatos|hijo|hija|hijos|hijas|hermano|hermana|"
    r"hermanos|hermanas|mascota|mascotas|nieto|nieta|nietos)",
    r"soy (?:alergic[oa]|vegetarian[oa]|vegan[oa]|diabetic[oa]|intolerante|celiac[oa]|hincha|fan) ",
]
_LEAD_RE = re.compile(r"^(?:oye |mira |jarvis |por favor )?(?:que )?(" + "|".join(_LEADS) + r")\b", re.I)
_FORGET_RE = re.compile(r"^(?:oye |jarvis )?(?:olvida(?:te)?|borra|elimina|quita)\b.*?\b"
                        r"(?:que |lo de |eso de )?(.+)$", re.I)
# Cosas que NO son datos del perfil aunque empiecen parecido (órdenes, recordatorios)
_NOT = re.compile(r"\b(?:recuerdame|recordatorio|alarma|avisame|manda|abre|cierra|pon|busca|reproduce|"
                  r"temporizador|cronometro|(?<!se )llama)\b", re.I)
# «me gusta esto», «me gusta esta canción»: habla de lo que tiene delante, no de un gusto suyo.
_DEICTIC = re.compile(r"^(?:no )?me (?:gusta|gustan|encanta|encantan|fascina|fascinan) (?:esto|eso|esta|este|estas|estos|asi|aqui|mucho|cuando|como|lo que)\b")


def normalize(text):
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "perfil.json")
    load()


def load():
    try:
        with open(_path, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, list):
            facts[:] = [x for x in d if isinstance(x, dict) and x.get("texto")][:MAX]
    except (FileNotFoundError, ValueError, OSError, TypeError):
        facts[:] = []


def save():
    if not _path:
        return
    os.makedirs(os.path.dirname(_path), exist_ok=True)
    tmp = _path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path)


def _clean(texto):
    texto = re.sub(r"\s+", " ", str(texto)).strip().strip(" .,;:")
    # quita un «jarvis» o muletilla al principio
    texto = re.sub(r"^(?:oye|mira|jarvis|por favor)[, ]+", "", texto, flags=re.I).strip()
    return texto[:200]


def detect(text):
    """Si la frase es un dato/preferencia del usuario, devuelve el texto a guardar; si no, None."""
    t = normalize(text)
    if len(t) < 6 or _NOT.search(t) or t.endswith("?") or "?" in text:
        return None
    if not _LEAD_RE.match(t) or _DEICTIC.match(t):
        return None
    if re.match(r"^(?:no )?me (?:gusta|gustan|encanta|encantan|fascina|fascinan)$", t):
        return None
    return _clean(text)


# «De qué trata» un dato, para que uno nuevo sobre lo mismo sustituya al viejo:
# «mi hermana se llama Laura» corrige a «mi hermana se llama Ana»; «vivo en Cali» a «vivo en Medellín».
_TOPIC_RE = re.compile(r"^(?P<t>(?:mis?|el|la|los|las) [a-z ]{2,40}?) (?:se llama|se llaman|es|son|esta|estan|queda|quedan|"
                       r"cumple|cumplen|nacio|vive|viven|trabaja)\b")
_TOPIC_LEADS = ("vivo en", "trabajo en", "trabajo como", "mi colegio es", "mi colegio se llama", "mi institucion es",
                "mi curso es", "mi grado es", "mi materia es", "mi area es", "mi correo es", "mi numero es", "soy de")


def topic(texto):
    t = normalize(texto)
    m = _TOPIC_RE.match(t)
    if m:
        return m.group("t")
    for p in _TOPIC_LEADS:
        if t.startswith(p + " "):
            return p
    return ""


_STOP = {"que", "como", "cual", "cuales", "donde", "cuando", "quien", "quienes", "para", "porque", "esta", "estan",
         "este", "esto", "eso", "tengo", "tiene", "dije", "dijo", "sabes", "recuerdas", "acuerdas", "llama", "llaman",
         "deje", "puse", "sobre", "algo", "tambien", "pero", "jarvis", "dime", "sabe"}


def _words(t):
    return [w for w in re.findall(r"[a-z0-9]+", normalize(t)) if len(w) > 3 and w not in _STOP]


def _near(a, b):
    return a == b or (len(a) > 4 and len(b) > 4 and a[:5] == b[:5])


_SECOND = {"mi": "tu", "mis": "tus", "me": "te", "yo": "tú", "soy": "eres", "estoy": "estás", "vivo": "vives",
           "trabajo": "trabajas", "tengo": "tienes", "prefiero": "prefieres", "odio": "odias", "llamo": "llamas",
           "dicto": "dictas", "enseno": "enseñas", "enseño": "enseñas", "conmigo": "contigo"}


def to_second_person(texto):
    """«Mi hermana se llama Ana» → «Tu hermana se llama Ana» (para decírselo al usuario)."""
    out = []
    for i, w in enumerate(str(texto).split()):
        core = w.strip(",.;:")
        low = core.lower()
        if low in ("trabajo", "dicto", "enseno", "enseño") and i > 0:
            out.append(w)                          # «mi trabajo es…»: sustantivo, no verbo
            continue
        to = _SECOND.get(low)
        if to:
            if core[:1].isupper():
                to = to[:1].upper() + to[1:]
            w = w.replace(core, to)
        out.append(w)
    return " ".join(out)


_ASK_RE = re.compile(r"\b(?:como|cual|cuales|quien|quienes|donde|cuando|que)\b")
_MINE_RE = re.compile(r"\b(?:mi|mis|deje|puse)\b|\bme (?:gusta|gustan|encanta|encantan)\b")


def answer(question):
    """Contesta con la memoria preguntas como «¿cómo se llama mi hermana?» o «¿qué música me gusta?». None si no sabe."""
    t = normalize(question)
    if not _ASK_RE.search(t) or not _MINE_RE.search(t):
        return None
    keys = _words(t)
    hit = None
    if keys:
        for fct in facts:                          # facts[0] es el más reciente
            fw = _words(fct["texto"])
            if all(any(_near(k, w) for w in fw) for k in keys):
                hit = fct
                break
    if hit:
        r = to_second_person(hit["texto"]).rstrip(".") + "."
        return r[:1].upper() + r[1:]
    if re.search(r"\bme (?:gusta|gustan|encanta|encantan)\b", t):
        likes = [f["texto"] for f in facts if re.search(r"\b(?:gusta|gustan|encanta|encantan|prefiero)\b", normalize(f["texto"]))][:4]
        if likes:
            return "Me has dicho que " + "; ".join(to_second_person(x).rstrip(".").lower() for x in likes) + "."
    m = re.search(r"\bcomo se llama (?:mi|el|la) ([a-z]+)", t)
    if m:
        return f"No me lo has dicho. Dime «mi {m.group(1)} se llama…» y lo recordaré."
    return None


def add(texto, now=None):
    import datetime
    texto = _clean(texto)
    if not texto:
        return None
    key = normalize(texto)
    tp = topic(texto)
    with _lock:
        for fct in facts:
            if normalize(fct["texto"]) == key:
                return fct
        if tp:                                     # un dato nuevo sobre lo mismo sustituye al viejo
            old = [f for f in facts if topic(f["texto"]) == tp]
            for f in old:
                facts.remove(f)
            corrected = bool(old)
        else:
            corrected = False
        import uuid
        fct = {"id": uuid.uuid4().hex[:8], "texto": texto,
               "fecha": (now or datetime.date.today()).isoformat() if hasattr(now or datetime.date.today(), "isoformat") else ""}
        fct["corrige"] = corrected
        facts.insert(0, fct)
        del facts[MAX:]
        save()
    return fct


def forget(text):
    """«olvida que trabajo en…»: borra lo que más se parezca. Devuelve el texto borrado o None."""
    m = _FORGET_RE.match(normalize(text))
    if not m:
        return None
    target = m.group(1).strip()
    if len(target) < 3:
        return None
    import difflib
    best, score = None, 0.0
    with _lock:
        for fct in facts:
            s = difflib.SequenceMatcher(None, target, normalize(fct["texto"])).ratio()
            if target in normalize(fct["texto"]):
                s = max(s, 0.9)
            if s > score:
                best, score = fct, s
        if best and score >= 0.5:
            facts.remove(best)
            save()
            return best["texto"]
    return None


def delete(fid):
    with _lock:
        before = len(facts)
        facts[:] = [f for f in facts if f["id"] != fid]
        if len(facts) != before:
            save()


def clear():
    with _lock:
        facts[:] = []
        save()


def relevant(question="", related=20, recent=12):
    """Lo que conviene que la IA tenga presente: lo relacionado con la pregunta y lo más reciente."""
    if len(facts) <= related + recent:
        return list(facts)
    q = _words(question)
    scored = []
    for i, f in enumerate(facts):
        n = sum(1 for w in _words(f["texto"]) if any(_near(w, x) for x in q))
        if n:
            scored.append((n, -i, f))
    rel = [f for _, _, f in sorted(scored, key=lambda x: (x[0], x[1]), reverse=True)[:related]]
    out = rel + [f for f in facts[:recent] if f not in rel]
    return out


def context_for_ai(limit=30, question=""):
    items = relevant(question) if question else facts[:limit]
    if not items:
        return ""
    return (" Lo que sabes del usuario por lo que te ha contado (tenlo en cuenta con naturalidad, "
            "no lo recites): " + "; ".join(f["texto"] for f in items) + ".")


def snapshot():
    return [{"id": f["id"], "texto": f["texto"], "fecha": f.get("fecha", "")} for f in facts]


def summary(n=4):
    """«¿Qué sabes de mí?»: unas cuantas cosas, dichas al usuario."""
    if not facts:
        return ("Aún no me has contado nada de ti. Dime, por ejemplo, «mi hermana se llama Ana» o "
                "«me gusta el vallenato», y lo recordaré.")
    some = "; ".join(to_second_person(f["texto"]).rstrip(".") for f in facts[:n])
    total = len(facts)
    return (f"Recuerdo {total} cosa{'s' if total != 1 else ''} de ti. Por ejemplo: {some}. "
            "Las ves todas en Ajustes, sección Memoria.")
