"""Libro guía del curso (11.5): el PDF (o Word o texto) del libro de texto o del plan de área que TÚ subes en Ajustes.

Se guarda su texto por páginas en tu equipo y, cuando Jarvis prepara material, planea o hace una guía viva, busca las
páginas que hablan del tema y las usa como base (con su número de página). Solo usa los libros que subiste; no busca
nada en tus carpetas. Lógica pura.
"""
import json
import math
import os
import re
import threading
import unicodedata
import uuid

try:
    import pypdf                                       # import aquí arriba: así el ejecutable lo incluye
except ImportError:                                    # pragma: no cover
    pypdf = None

_lock = threading.Lock()
_dir = None
index = {"libros": {}}            # {id: {"nombre", "asignatura", "paginas", "archivo"}}
_cache = {}
MAX_BYTES = 18_000_000
STOP = set("el la los las de del y o u a en un una unos unas que por para con sin se su sus al lo es son como mas más este esta estos estas "
           "ese esa cada entre sobre tambien también muy cual cuál cuando donde qué que hay ser ha han".split())


def configure(config_dir):
    global _dir
    _dir = os.path.join(config_dir, "libros")
    os.makedirs(_dir, exist_ok=True)
    load()


def load():
    global index
    _cache.clear()
    try:
        with open(os.path.join(_dir, "indice.json"), encoding="utf-8") as f:
            d = json.load(f)
        index = d if isinstance(d, dict) and "libros" in d else {"libros": {}}
    except (OSError, ValueError, TypeError):
        index = {"libros": {}}


def _save_index():
    if not _dir:
        return
    with _lock:
        tmp = os.path.join(_dir, "indice.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(_dir, "indice.json"))


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", "".join(c for c in t if unicodedata.category(c) != "Mn"))).strip()


def extract(data, filename):
    """Bytes del archivo → [texto de cada página]. Lanza ValueError con un mensaje claro."""
    name = filename.lower()
    if len(data) > MAX_BYTES:
        raise ValueError("el archivo es muy grande (máximo 18 MB)")
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        if pypdf is None:
            raise ValueError("falta la librería pypdf (actualiza Jarvis)")
        import io
        try:
            reader = pypdf.PdfReader(io.BytesIO(data))
            pages = [(p.extract_text() or "") for p in reader.pages[:900]]
        except Exception as e:
            raise ValueError(f"no pude leer el PDF ({str(e)[:80]})")
        if sum(len(p.strip()) for p in pages) < 200:
            raise ValueError("el PDF no trae texto (parece escaneado como imagen)")
        return [re.sub(r"[ \t]+", " ", p).strip() for p in pages]
    if name.endswith(".docx"):
        import io
        from docx import Document
        doc = Document(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs)
    elif name.endswith((".txt", ".md")):
        text = data.decode("utf-8", "replace")
    else:
        raise ValueError("sube un PDF, un Word (.docx) o un texto (.txt)")
    words = text.split()
    return [" ".join(words[i:i + 450]) for i in range(0, len(words), 450)] or [""]


def add_book(nombre, asignatura, pages, archivo=""):
    bid = uuid.uuid4().hex[:8]
    with open(os.path.join(_dir, f"{bid}.json"), "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False)
    index["libros"][bid] = {"nombre": str(nombre)[:120] or "Libro guía", "asignatura": str(asignatura)[:60], "paginas": len(pages),
                            "archivo": os.path.basename(archivo)[:120]}
    _save_index()
    return bid


def remove(bid):
    if bid in index["libros"]:
        index["libros"].pop(bid)
        _cache.pop(bid, None)
        try:
            os.remove(os.path.join(_dir, f"{bid}.json"))
        except OSError:
            pass
        _save_index()
        return True
    return False


def _pages(bid):
    if bid not in _cache:
        try:
            with open(os.path.join(_dir, f"{bid}.json"), encoding="utf-8") as f:
                _cache[bid] = json.load(f)
        except (OSError, ValueError):
            _cache[bid] = []
    return _cache[bid]


def _terms(t):
    return [w for w in norm(t).split() if len(w) > 2 and w not in STOP]


def search(query, asignatura="", k=4):
    """Las páginas que más hablan del tema (BM25 sencillo). → [{"libro", "pagina", "texto", "score"}]."""
    q = _terms(query)
    if not q:
        return []
    cands = []
    for bid, meta in index["libros"].items():
        if asignatura and meta.get("asignatura") and norm(meta["asignatura"]).split()[0] not in norm(asignatura) \
                and norm(asignatura).split()[0] not in norm(meta["asignatura"]):
            continue
        pages = _pages(bid)
        docs = [_terms(p) for p in pages]
        n = len(docs) or 1
        avg = sum(len(d) for d in docs) / n or 1
        df = {w: sum(1 for d in docs if w in d) for w in set(q)}
        for i, d in enumerate(docs):
            if not d:
                continue
            tf = {}
            for w in d:
                if w in df:
                    tf[w] = tf.get(w, 0) + 1
            s = sum(math.log(1 + (n - df[w] + .5) / (df[w] + .5)) * tf[w] * 2.2 / (tf[w] + 1.2 * (.25 + .75 * len(d) / avg)) for w in tf)
            if s > 0:
                cands.append({"libro": meta["nombre"], "pagina": i + 1, "texto": pages[i], "score": s})
    return sorted(cands, key=lambda c: -c["score"])[:k]


def context(query, asignatura="", k=3, chars=1600):
    hits = search(query, asignatura, k)
    if not hits:
        return ""
    parts = [f"«{h['libro']}», p. {h['pagina']}: {h['texto'][:chars]}" for h in hits]
    return (" Usa como base el libro guía del curso (respeta su enfoque, sus ejemplos y su vocabulario, y menciona la página cuando "
            "la uses):\n" + "\n---\n".join(parts) + "\n")
