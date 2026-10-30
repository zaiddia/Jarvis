"""Elegir herramientas por significado (7.5): la IA solo ve las acciones que tienen que ver con lo que pides.

Con 35 acciones propias, decenas de conectores MCP y habilidades de la comunidad, mandarle todo a la IA en cada
orden la vuelve lenta y la confunde. Aquí se puntúa cada herramienta contra la frase:
  · por palabras (BM25 con tildes, plurales y palabras parecidas, el mismo de la memoria buscable);
  · por significado, si hay modelo de embeddings (Gemini u Ollama): «está muy oscuro» encuentra «brillo».
y se quedan las mejores, más unas pocas que siempre van. Los vectores de las herramientas se guardan, así que
solo la frase se calcula cada vez.
"""
import hashlib
import json
import os
import threading

import recuerdos

_lock = threading.Lock()
_cache = {}            # tag -> {hash: vector}
_cache_dir = None


def configure(cache_dir):
    global _cache_dir
    _cache_dir = cache_dir


def _h(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _load(tag):
    if tag in _cache:
        return _cache[tag]
    data = {}
    if _cache_dir:
        try:
            with open(os.path.join(_cache_dir, f"vectores-herramientas-{tag}.json"), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
    _cache[tag] = data
    return data


def _save(tag):
    if not _cache_dir:
        return
    try:
        os.makedirs(_cache_dir, exist_ok=True)
        p = os.path.join(_cache_dir, f"vectores-herramientas-{tag}.json")
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(_cache.get(tag, {}), f)
        os.replace(p + ".tmp", p)
    except OSError:
        pass


def rank(query, items, embed=None, tag=""):
    """items: [(id, texto)]. Devuelve [(puntuación 0..1, id)] de mejor a peor."""
    if not items:
        return []
    q = recuerdos.tokens(query)
    lex = recuerdos.bm25(q, [recuerdos.tokens(t) for _, t in items])
    top = max(lex) if lex else 0
    scores = [s / top if top else 0.0 for s in lex]
    if embed and tag:
        try:
            with _lock:
                cache = _load(tag)
                missing = [(i, t) for i, (_, t) in enumerate(items) if _h(t) not in cache]
            if missing:
                vecs = embed([t for _, t in missing]) or []
                with _lock:
                    for (_, t), v in zip(missing, vecs):
                        cache[_h(t)] = [round(x, 5) for x in v]
                    _save(tag)
            qv = (embed([query]) or [None])[0]
            if qv:
                for i, (_, t) in enumerate(items):
                    v = cache.get(_h(t))
                    if v:
                        sem = max(0.0, min(1.0, (recuerdos.cosine(qv, v) - 0.40) / 0.45))
                        scores[i] = 0.35 * scores[i] + 0.65 * sem
        except Exception:
            pass
    return sorted(((round(s, 4), items[i][0]) for i, s in enumerate(scores)), key=lambda x: -x[0])


def choose(query, items, k=20, always=(), embed=None, tag=""):
    """Los ids que verá la IA: los «always» que existan y las k mejores (sin repetir), en el orden original."""
    ids = [i for i, _ in items]
    keep = [i for i in always if i in ids]
    for score, i in rank(query, items, embed, tag):
        if len(keep) >= k + len(always):
            break
        if i not in keep and score > 0:
            keep.append(i)
    picks = len(keep) - len([i for i in always if i in ids])
    if picks < k:                                       # pocas pistas: completa con las primeras
        keep += [i for i in ids if i not in keep][: k - picks]
    wanted = set(keep)
    return [i for i in ids if i in wanted]
