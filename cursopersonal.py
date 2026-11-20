"""12.40: tu profesor particular de lo que quieras aprender (inglés, guitarra, Excel, cocina…). Lógica pura.

Un curso = un plan de lecciones cortas (15 minutos por defecto), lo que ya hiciste, los días que practicaste (racha) y
tarjetas de repaso con repetición espaciada (cajas de Leitner: lo que sabes vuelve cada vez más tarde; lo que fallas,
mañana).
"""
import datetime
import json
import re
import unicodedata

BOXES = [0, 1, 3, 7, 16, 35]          # días hasta el próximo repaso según la caja
LANGS = {"ingles": "inglés", "frances": "francés", "portugues": "portugués", "aleman": "alemán", "italiano": "italiano",
         "japones": "japonés", "chino": "chino mandarín", "coreano": "coreano", "ruso": "ruso"}
LANG_CODE = {"inglés": "English", "francés": "French", "portugués": "Portuguese", "alemán": "German", "italiano": "Italian",
             "japonés": "Japanese", "chino mandarín": "Mandarin Chinese", "coreano": "Korean", "ruso": "Russian"}


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()


def slug(tema):
    return re.sub(r"[^a-z0-9]+", "-", norm(tema)).strip("-")[:40] or "curso"


def language_of(tema):
    """«inglés para viajar» → "inglés"; «guitarra» → ""."""
    w = norm(tema).split()
    for k, v in LANGS.items():
        if k in w:
            return v
    return ""


_LEVEL = re.compile(r"\b(?:desde cero|de cero|principiante|basico|intermedio|avanzado|nivel (?:a1|a2|b1|b2|c1|c2|basico|intermedio|avanzado))\b")


def level_in(t):
    m = _LEVEL.search(norm(t))
    if not m:
        return "principiante"
    x = m.group(0).replace("nivel ", "")
    return {"desde cero": "principiante", "de cero": "principiante", "basico": "básico"}.get(x, x.upper() if len(x) == 2 else x)


def minutes_in(t):
    m = re.search(r"\b(\d{1,2})\s*(?:minutos|min)\s+(?:al|diarios|cada|por)\b|\b(?:de|unos)\s+(\d{1,2})\s*minutos\b", norm(t))
    n = int(m.group(1) or m.group(2)) if m else 15
    return max(5, min(60, n))


def new_course(tema, nivel="principiante", meta="", minutos=15, hora="19:00", today=None):
    today = today or datetime.date.today()
    return {"tema": tema.strip(), "nivel": nivel, "meta": meta.strip(), "minutos": minutos, "hora": hora, "creado": today.isoformat(),
            "plan": [], "hechas": [], "dias": [], "tarjetas": [], "aviso": "", "aciertos": 0, "intentos": 0}


def plan_prompt(c):
    lang = language_of(c["tema"])
    extra = (f" Es un idioma: mezcla vocabulario útil, gramática sencilla, pronunciación y frases para la vida real; "
             f"cada lección debe poder practicarse hablando.") if lang else " Si es algo práctico (un instrumento, un programa, cocina), cada lección incluye algo para hacer con las manos."
    return ("Eres un profesor particular paciente. Arma un plan de 24 lecciones cortas para aprender «" + c["tema"] + f"», nivel "
            f"{c['nivel']}, de {c['minutos']} minutos cada una" + (f", con esta meta: {c['meta']}" if c["meta"] else "") + "." + extra +
            " Van de lo más básico a lo más útil, una idea nueva por lección, y cada 6 lecciones una de repaso. En español. "
            'Responde SOLO con JSON: {"plan": [{"titulo": "…", "objetivo": "…"}]}')


def parse_plan(text):
    try:
        m = re.search(r"\{.*\}", str(text), re.S)
        d = json.loads(m.group(0) if m else text)
    except Exception:
        return []
    out = []
    for x in (d.get("plan") or [])[:40]:
        if isinstance(x, dict) and str(x.get("titulo") or "").strip():
            out.append({"titulo": str(x["titulo"]).strip()[:120], "objetivo": str(x.get("objetivo") or "").strip()[:240]})
    return out


def next_lesson(c):
    """Número (1…) de la siguiente lección sin hacer, o 0 si ya terminó el plan."""
    done = set(c.get("hechas") or [])
    for i in range(1, len(c.get("plan") or []) + 1):
        if i not in done:
            return i
    return 0


def lesson_prompt(c, n):
    item = c["plan"][n - 1]
    lang = language_of(c["tema"])
    prev = "; ".join(x["titulo"] for x in c["plan"][max(0, n - 4):n - 1])
    lang_rule = (f" Los ejemplos y ejercicios van en {lang} con su traducción; incluye cómo se pronuncia lo difícil (escrito como "
                 "suena en español).") if lang else ""
    return (f"Eres un profesor particular paciente. Lección {n} de {len(c['plan'])} del curso «{c['tema']}» (nivel {c['nivel']}, "
            f"{c['minutos']} minutos): «{item['titulo']}» — {item['objetivo']}." + (f" Lo anterior: {prev}." if prev else "") + lang_rule +
            " Explica en español sencillo y corto (máximo 120 palabras), con 2 o 3 ejemplos. Luego 4 ejercicios cortos que se puedan "
            "responder en una línea (con la respuesta correcta y una pista que no la regale), 4 tarjetas de repaso (frente y reverso) "
            "y una práctica para hacer por tu cuenta (qué hacer y por cuántos minutos). Responde SOLO con JSON: "
            '{"explicacion": "…", "ejemplos": ["…"], "ejercicios": [{"pregunta": "…", "respuesta": "…", "pista": "…"}], '
            '"tarjetas": [{"frente": "…", "reverso": "…"}], "practica": "…"}')


def parse_lesson(text):
    try:
        m = re.search(r"\{.*\}", str(text), re.S)
        d = json.loads(m.group(0) if m else text)
    except Exception:
        return None
    ex = [{"pregunta": str(x.get("pregunta") or "").strip(), "respuesta": str(x.get("respuesta") or "").strip(),
           "pista": str(x.get("pista") or "").strip()} for x in (d.get("ejercicios") or []) if isinstance(x, dict)]
    ex = [x for x in ex if x["pregunta"] and x["respuesta"]][:6]
    cards = [{"frente": str(x.get("frente") or "").strip(), "reverso": str(x.get("reverso") or "").strip()}
             for x in (d.get("tarjetas") or []) if isinstance(x, dict)]
    cards = [x for x in cards if x["frente"] and x["reverso"]][:8]
    if not (str(d.get("explicacion") or "").strip() and ex):
        return None
    return {"explicacion": str(d["explicacion"]).strip(), "ejemplos": [str(x).strip() for x in (d.get("ejemplos") or []) if str(x).strip()][:4],
            "ejercicios": ex, "tarjetas": cards, "practica": str(d.get("practica") or "").strip()}


def _alts(ans):
    return [norm(a).strip(" .!?¡¿") for a in re.split(r"\s*(?:\||/| o )\s*", str(ans)) if a.strip()]


def quick_check(answer, expected):
    """True/False si se puede saber sin la IA (igual o casi igual a una de las respuestas válidas); None si hay que preguntarle."""
    a = norm(answer).strip(" .!?¡¿")
    if not a:
        return False
    alts = _alts(expected)
    if a in alts:
        return True
    import difflib
    best = max((difflib.SequenceMatcher(None, a, x).ratio() for x in alts), default=0)
    if best >= 0.88:
        return True
    return None


def check_prompt(c, question, expected, answer):
    return (f"Curso «{c['tema']}». Pregunta: «{question}». Respuesta correcta: «{expected}». El estudiante respondió: «{answer}». "
            "¿Está bien? Acepta respuestas equivalentes, sinónimos y errores de tildes o mayúsculas; no aceptes otra idea. "
            'Responde SOLO con JSON: {"bien": true, "comentario": "una frase corta y amable en español"}')


def parse_check(text):
    try:
        m = re.search(r"\{.*\}", str(text), re.S)
        d = json.loads(m.group(0) if m else text)
        return bool(d.get("bien")), str(d.get("comentario") or "").strip()[:300]
    except Exception:
        return None, ""


def add_cards(c, cards, today=None):
    today = today or datetime.date.today()
    have = {norm(x["frente"]) for x in c["tarjetas"]}
    n = max([x["id"] for x in c["tarjetas"]] + [0])
    for x in cards:
        if norm(x["frente"]) in have:
            continue
        n += 1
        have.add(norm(x["frente"]))
        c["tarjetas"].append({"id": n, "frente": x["frente"], "reverso": x["reverso"], "caja": 0,
                              "proxima": (today + datetime.timedelta(days=1)).isoformat()})


def due_cards(c, today=None):
    today = (today or datetime.date.today()).isoformat()
    return [x for x in c["tarjetas"] if x["proxima"] <= today]


def review(card, ok, today=None):
    """Caja de Leitner: bien → sube una caja (vuelve más tarde); mal → caja 0 (vuelve mañana)."""
    today = today or datetime.date.today()
    card["caja"] = min(len(BOXES) - 1, card["caja"] + 1) if ok else 0
    card["proxima"] = (today + datetime.timedelta(days=max(1, BOXES[card["caja"]]))).isoformat()
    return card


def mark_day(c, today=None):
    d = (today or datetime.date.today()).isoformat()
    if d not in c["dias"]:
        c["dias"].append(d)
        c["dias"] = sorted(c["dias"])[-400:]


def streak(c, today=None):
    """Días seguidos practicando, contando hoy (o ayer, si hoy aún no practicaste)."""
    today = today or datetime.date.today()
    days = set(c.get("dias") or [])
    d = today if today.isoformat() in days else today - datetime.timedelta(days=1)
    n = 0
    while d.isoformat() in days:
        n += 1
        d -= datetime.timedelta(days=1)
    return n


def progress(c, today=None):
    total = len(c.get("plan") or [])
    done = len(set(c.get("hechas") or []))
    mastered = sum(1 for x in c["tarjetas"] if x["caja"] >= 3)
    acc = round(100 * c["aciertos"] / c["intentos"]) if c.get("intentos") else None
    return {"lecciones": done, "total": total, "racha": streak(c, today), "dias": len(c.get("dias") or []),
            "tarjetas": len(c["tarjetas"]), "dominadas": mastered, "pendientes": len(due_cards(c, today)), "acierto": acc}


def conversation_rule(c):
    """La regla para conversar en el idioma (texto o voz en vivo)."""
    lang = language_of(c["tema"])
    name = LANG_CODE.get(lang, lang)
    return (f" PRÁCTICA DE CONVERSACIÓN EN {lang.upper()} (nivel {c['nivel']}): ahora eres un compañero de conversación paciente. "
            f"Habla SOLO en {name}, con frases cortas y sencillas para ese nivel, y termina cada turno con una pregunta para que la "
            f"persona siga hablando. Si la persona comete errores, después de tu respuesta agrega una línea en español que empiece por "
            f"«Corrección:» con la forma correcta y una explicación de máximo una frase. Si no comete errores, no agregues nada. "
            f"Si la persona habla en español o se queda sin palabras, ayúdale con la frase en {name} que quería decir. Temas: su día, "
            f"gustos, trabajo, viajes, comida, Colombia.")
