"""La memoria buscable de Jarvis (7.4): «¿qué te dije la semana pasada sobre el examen de 7A?».

Guarda lo que hablan (tus frases y sus respuestas, sin lo que suene a contraseña o clave) en un historial
por meses, y lo busca:
  · por palabras, con un buscador BM25 que entiende tildes, plurales y palabras parecidas;
  · por significado, si hay un modelo de «embeddings» (Gemini u Ollama): entonces «prueba» encuentra
    «examen» y «el paseo» encuentra «la salida pedagógica». jarvis.py pasa la función embed.
  · con fechas: «ayer», «la semana pasada», «el mes pasado», «en octubre», «el lunes».
"""
import datetime
import hashlib
import json
import math
import os
import re
import threading
import unicodedata

_lock = threading.Lock()
_dir = None
enabled = True
keep_days = 180

STOP = set("""a al algo como con contra cual cuando de del desde donde dos e el ella ellas ellos en entre era es esa
ese eso esta este esto estos fue ha hay la las le les lo los mas me mi mis muy ni no nos o os para pero por que
quien se sea ser si sin sobre son su sus te ti tu tus un una uno unos y ya yo eh pues bueno dije dijiste dijo
hablamos hable conte contaste te recuerdas acuerdas cosa cosas jarvis oye semana pasada pasado ayer hoy mes""".split())

_SECRET = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[correo]"),
    (re.compile(r"\b(?:sk|pk|rk|ghp|gho|xai|gsk|AIza)[-_A-Za-z0-9]{12,}\b"), "[clave]"),
    (re.compile(r"\b[A-Za-z0-9_-]{32,}\b"), "[código]"),
    (re.compile(r"(?i)\b(contrase(?:ñ|n)a|password|clave|pin|cvv|c[oó]digo de seguridad)\b(\s*(?:es|era|:)?\s*)\S+"), r"\1\2[oculto]"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[número]"),
]


def configure(config_dir, on=True, days=180):
    global _dir, enabled, keep_days
    _dir = os.path.join(config_dir, "historial")
    enabled, keep_days = bool(on), int(days)


def redact(text):
    out = str(text)
    for rx, rep in _SECRET:
        out = rx.sub(rep, out)
    return out


def norm(text):
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w\s]", " ", t)


def stem(w):
    """Raíz muy simple para el español: «exámenes»→«examen», «niños»→«nino», «calificaciones»→«calificacion»."""
    for suf in ("aciones", "iciones", "amientos", "imientos", "mente", "aciones", "ciones", "siones", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            if suf in ("aciones", "iciones", "ciones", "siones"):
                return w[: -len(suf)] + suf[:-2]       # …ciones → …cion
            return w[: -len(suf)]
    return w


def tokens(text):
    return [stem(w) for w in norm(text).split() if w not in STOP and len(w) > 1]


def log(role, text, now=None):
    """Anota una línea de la conversación. Nunca falla."""
    if not (enabled and _dir) or not str(text).strip():
        return
    now = now or datetime.datetime.now()
    item = {"ts": now.isoformat(timespec="seconds"), "r": "u" if role == "user" else "j", "x": redact(text).strip()[:600]}
    try:
        with _lock:
            os.makedirs(_dir, exist_ok=True)
            with open(os.path.join(_dir, now.strftime("%Y-%m") + ".jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    except OSError:
        pass


def load(since=None, until=None):
    """Las entradas guardadas (más viejas primero), opcionalmente entre dos fechas."""
    if not _dir or not os.path.isdir(_dir):
        return []
    out = []
    for name in sorted(os.listdir(_dir)):
        if not re.fullmatch(r"\d{4}-\d{2}\.jsonl", name):
            continue
        if since and name[:7] < since.strftime("%Y-%m"):
            continue
        if until and name[:7] > until.strftime("%Y-%m"):
            continue
        try:
            with open(os.path.join(_dir, name), encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                        d = datetime.datetime.fromisoformat(e["ts"])
                    except (ValueError, KeyError):
                        continue
                    if (since and d.date() < since) or (until and d.date() > until):
                        continue
                    e["dt"] = d
                    out.append(e)
        except OSError:
            continue
    return out


def purge(today=None):
    if not _dir or not os.path.isdir(_dir):
        return
    limit = (today or datetime.date.today()) - datetime.timedelta(days=keep_days)
    for name in os.listdir(_dir):
        if re.fullmatch(r"\d{4}-\d{2}\.jsonl", name) and name[:7] < limit.strftime("%Y-%m"):
            try:
                os.remove(os.path.join(_dir, name))
            except OSError:
                pass


def clear():
    if not _dir or not os.path.isdir(_dir):
        return
    for name in os.listdir(_dir):
        if name.endswith(".jsonl") or (name.startswith("vectores") and name.endswith(".json")):
            try:
                os.remove(os.path.join(_dir, name))
            except OSError:
                pass


# ----------------------------------------------------------------------------- fechas en la pregunta
_MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre"]
_WD = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def date_range(question, today=None):
    """(desde, hasta, texto) según lo que dice la pregunta; (None, None, "") si no habla de fechas."""
    t = norm(question)
    today = today or datetime.date.today()
    if re.search(r"\bantier\b|\banteayer\b", t):
        d = today - datetime.timedelta(days=2)
        return d, d, "anteayer"
    if re.search(r"\bayer\b", t):
        d = today - datetime.timedelta(days=1)
        return d, d, "ayer"
    if re.search(r"\bhoy\b|\besta manana\b|\besta tarde\b", t):
        return today, today, "hoy"
    if re.search(r"\b(?:la )?semana pasada\b", t):
        start = today - datetime.timedelta(days=today.weekday() + 7)
        return start, start + datetime.timedelta(days=6), "la semana pasada"
    if re.search(r"\besta semana\b", t):
        return today - datetime.timedelta(days=today.weekday()), today, "esta semana"
    if re.search(r"\b(?:el )?mes pasado\b", t):
        first = today.replace(day=1)
        last_prev = first - datetime.timedelta(days=1)
        return last_prev.replace(day=1), last_prev, "el mes pasado"
    if re.search(r"\beste mes\b", t):
        return today.replace(day=1), today, "este mes"
    m = re.search(r"\b(?:hace|en los ultimos) (\d{1,2}|un|una|dos|tres) (dia|dias|semana|semanas)\b", t)
    if m:
        n = {"un": 1, "una": 1, "dos": 2, "tres": 3}.get(m.group(1)) or int(m.group(1))
        days = n * (7 if m.group(2).startswith("semana") else 1)
        return today - datetime.timedelta(days=days + 1), today, f"hace {m.group(1)} {m.group(2)}"
    for i, name in enumerate(_MONTHS):
        if re.search(rf"\ben {name}\b|\bde {name}\b", t):
            year = today.year if i + 1 <= today.month else today.year - 1
            first = datetime.date(year, i + 1, 1)
            nxt = datetime.date(year + (i == 11), (i + 1) % 12 + 1, 1)
            return first, nxt - datetime.timedelta(days=1), f"en {name}"
    for i, name in enumerate(_WD):
        if re.search(rf"\bel {name}\b", t):
            back = (today.weekday() - i) % 7 or 7
            d = today - datetime.timedelta(days=back)
            return d, d, f"el {name}"
    return None, None, ""


# ----------------------------------------------------------------------------- búsqueda
def bm25(query_tokens, docs_tokens, k1=1.4, b=0.75):
    n = len(docs_tokens)
    if not n or not query_tokens:
        return [0.0] * n
    avg = sum(len(d) for d in docs_tokens) / n or 1
    df = {}
    for d in docs_tokens:
        for w in set(d):
            df[w] = df.get(w, 0) + 1
    scores = []
    for d in docs_tokens:
        tf = {}
        for w in d:
            tf[w] = tf.get(w, 0) + 1
        s = 0.0
        for q in set(query_tokens):
            f = tf.get(q, 0)
            if not f:
                # coincidencia parcial («calific» en «calificacion»): media puntuación
                f = 0.5 * sum(1 for w in tf if len(q) >= 5 and (w.startswith(q) or q.startswith(w)) and len(w) >= 5)
            if not f:
                continue
            idf = math.log(1 + (n - df.get(q, 0) + 0.5) / (df.get(q, 0) + 0.5))
            s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(d) / avg))
        scores.append(s)
    return scores


def cosine(a, b):
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    return num / (da * db) if da and db else 0.0


def _vec_cache_path(tag=""):
    if not _dir:
        return None
    return os.path.join(_dir, f"vectores-{re.sub(r'[^\w.-]', '_', tag) or 'x'}.json")


def _key(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]


def search(question, entries=None, embed=None, k=6, today=None, topic=None, embed_tag=""):
    """Lo más relacionado con la pregunta: [{"dt", "r", "x", "score"}] (mejor primero).
    embed(lista_de_textos) -> lista de vectores, o None si no hay; si falla, solo palabras."""
    d1, d2, _ = date_range(question, today)
    entries = load(d1, d2) if entries is None else [e for e in entries if not d1 or d1 <= e["dt"].date() <= d2]
    if not entries:
        return []
    topic = topic if topic is not None else question
    q = tokens(topic)
    docs = [tokens(e["x"]) for e in entries]
    lex = bm25(q, docs)
    top_lex = max(lex) if lex else 0
    scores = [s / top_lex if top_lex else 0 for s in lex]
    if embed and q:
        try:
            cache = {}
            path = _vec_cache_path(embed_tag)
            if path and os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    cache = json.load(f)
            # solo se calculan (y guardan) los vectores que faltan; como mucho 400 por pregunta
            cands = sorted(range(len(entries)), key=lambda i: -scores[i])[:400] if len(entries) > 400 else range(len(entries))
            missing = [i for i in cands if _key(entries[i]["x"]) not in cache]
            if missing:
                vecs = embed([entries[i]["x"] for i in missing])
                for i, v in zip(missing, vecs or []):
                    cache[_key(entries[i]["x"])] = [round(x, 5) for x in v]
                if path and vecs:
                    with open(path + ".tmp", "w", encoding="utf-8") as f:
                        json.dump(cache, f)
                    os.replace(path + ".tmp", path)
            qv = (embed([topic]) or [None])[0]
            if qv:
                for i in cands:
                    v = cache.get(_key(entries[i]["x"]))
                    if v:
                        sem = max(0.0, (cosine(qv, v) - 0.45) / 0.45)   # 0.45..0.9 → 0..1
                        scores[i] = 0.45 * scores[i] + 0.55 * min(1.0, sem)
        except Exception:
            pass
    # tu frase y la respuesta que le siguió son un mismo recuerdo: se muestra tu frase (con la respuesta)
    for i in range(len(entries) - 1):
        a, b = entries[i], entries[i + 1]
        if a["r"] == "u" and b["r"] == "j" and (b["dt"] - a["dt"]).total_seconds() < 120:
            scores[i] = max(scores[i], scores[i + 1])
            scores[i + 1] *= 0.6
    scores = [s * (1.0 if e["r"] == "u" else 0.9) for s, e in zip(scores, entries)]   # tus frases primero
    if not q and d1:                                   # «¿qué hablamos ayer?»: todo lo de ese día
        scores = [1.0 if e["r"] == "u" else 0.5 for e in entries]
    order = sorted(range(len(entries)), key=lambda i: (-scores[i], -entries[i]["dt"].timestamp()))
    out = []
    for i in order[: k * 3]:
        if scores[i] <= 0.12:
            break
        e = dict(entries[i])
        e["score"] = round(scores[i], 3)
        # contexto: lo que vino justo después (la respuesta a tu frase, o tu frase antes de la respuesta)
        if e["r"] == "u" and i + 1 < len(entries) and entries[i + 1]["r"] == "j":
            e["after"] = entries[i + 1]["x"]
        out.append(e)
        if len(out) >= k:
            break
    return out


def when_text(dt, today=None):
    today = today or datetime.date.today()
    d = dt.date()
    if d == today:
        return f"hoy a las {dt:%H:%M}"
    if d == today - datetime.timedelta(days=1):
        return f"ayer a las {dt:%H:%M}"
    if (today - d).days < 7:
        return f"el {_WD[d.weekday()]}"
    return f"el {d.day} de {_MONTHS[d.month - 1]}"


def spoken(hits, today=None):
    """Respuesta sin IA: lo que encontró, con fecha."""
    if not hits:
        return "No encuentro nada de eso en lo que hemos hablado."
    parts = []
    for h in hits[:3]:
        who = "me dijiste" if h["r"] == "u" else "te dije"
        parts.append(f"{when_text(h['dt'], today)} {who}: «{h['x'][:160]}»")
    return "Encontré esto. " + ". ".join(p[0].upper() + p[1:] for p in parts) + "."


def prompt(question, hits, today=None):
    lines = []
    for h in hits:
        who = "El usuario" if h["r"] == "u" else "Jarvis"
        lines.append(f"- {when_text(h['dt'], today)} ({h['dt']:%Y-%m-%d %H:%M}) {who}: {h['x']}"
                     + (f"\n  (Jarvis respondió: {h['after'][:200]})" if h.get("after") else ""))
    return ("Esto es lo que encontré en el historial de nuestras conversaciones:\n" + "\n".join(lines) +
            f"\n\nCon eso, responde en español, en una o dos frases y diciendo cuándo fue, a esta pregunta del usuario: "
            f"«{question}». Si no responde la pregunta, dilo con honestidad.")
