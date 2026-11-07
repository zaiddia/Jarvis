"""Detector de copia (12.12): compara los trabajos de un curso y avisa cuáles se parecen demasiado. Lógica pura.

Cada trabajo se parte en fragmentos de 5 palabras seguidas; dos trabajos se parecen tanto como fragmentos comparten. En
código, se ignoran los comentarios y los nombres de las variables (cambiarle el nombre a todo no esconde la copia). No
dice «copió»: muestra cuánto se parecen y qué partes son iguales, para que el docente decida.
"""
import difflib
import re
import unicodedata

K = 5
HIGH, MID = 0.55, 0.35
KEYWORDS = set("""and as assert break class continue def del elif else except false finally for from global if import in is lambda none
nonlocal not or pass raise return true try while with yield print input int float str len range list dict set function var let const
new this null undefined switch case default do void public private static int char double long bool boolean string include return main
cout cin printf scanf endl std using namespace setup loop digitalwrite pinmode delay serial algoritmo finalgoritmo escribir leer si
entonces sino finsi mientras hacer finmientras para hasta finpara segun finsegun definir como entero real caracter logico""".split())


def norm_words(text):
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.findall(r"\w+", t)


def code_tokens(code):
    """El código sin comentarios, con los textos y los nombres propios reemplazados (cambiar nombres no esconde la copia)."""
    c = re.sub(r"(?m)#.*$|//.*$", " ", str(code))
    c = re.sub(r"/\*.*?\*/|\"\"\".*?\"\"\"|'''.*?'''", " ", c, flags=re.S)
    c = re.sub(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", " TXT ", c)
    out = []
    for tok in re.findall(r"[A-Za-z_]\w*|\d+|[^\s\w]", c):
        low = tok.lower()
        out.append(low if (low in KEYWORDS or not re.match(r"[a-z_]", low) or low == "txt") else "ID")
    return out


def shingles(tokens, k=K):
    return {" ".join(tokens[i:i + k]) for i in range(max(0, len(tokens) - k + 1))}


def similarity(a_tokens, b_tokens, k=K):
    """0 a 1: parte de los fragmentos que comparten (sobre el trabajo más corto: copiar una parte también cuenta)."""
    sa, sb = shingles(a_tokens, k), shingles(b_tokens, k)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


def shared_parts(a_words, b_words, min_len=8, top=3):
    """Los trozos iguales más largos (para mostrarle al docente). → [texto]."""
    sm = difflib.SequenceMatcher(None, a_words, b_words, autojunk=False)
    blocks = sorted((b for b in sm.get_matching_blocks() if b.size >= min_len), key=lambda b: -b.size)[:top]
    return [" ".join(a_words[b.a:b.a + b.size])[:400] for b in blocks]


def shared_lines(a_code, b_code, top=5):
    """En código: las líneas de A que tienen la misma estructura que alguna de B (aunque cambien los nombres)."""
    b_norm = {" ".join(code_tokens(ln)) for ln in str(b_code).splitlines() if len(code_tokens(ln)) >= 4}
    out = []
    for ln in str(a_code).splitlines():
        tk = code_tokens(ln)
        if len(tk) >= 4 and " ".join(tk) in b_norm and ln.strip() not in out:
            out.append(ln.strip()[:200])
    return out[:top]


def compare(docs, code=False):
    """docs: {nombre: texto}. → [{"a","b","parecido" (0-100),"nivel","partes"}] de los pares que se parecen, del más alto al más bajo."""
    names = [n for n, t in docs.items() if str(t or "").strip()]
    toks = {n: (code_tokens(docs[n]) if code else norm_words(docs[n])) for n in names}
    words = {n: norm_words(docs[n]) for n in names}
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if len(toks[a]) < K * 2 or len(toks[b]) < K * 2:
                continue
            s = similarity(toks[a], toks[b])
            if s >= MID:
                out.append({"a": a, "b": b, "parecido": round(s * 100), "nivel": "muy parecidos" if s >= HIGH else "revisar",
                            "partes": shared_lines(docs[a], docs[b]) if code else shared_parts(words[a], words[b])})
    return sorted(out, key=lambda r: -r["parecido"])


def groups(pairs, min_level="muy parecidos"):
    """Los grupos de trabajos casi iguales entre sí (si A~B y B~C, son un grupo de 3)."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for p in pairs:
        if p["nivel"] == min_level:
            parent[find(p["a"])] = find(p["b"])
    g = {}
    for x in list(parent):
        g.setdefault(find(x), set()).add(x)
    return sorted((sorted(v) for v in g.values() if len(v) > 1), key=len, reverse=True)


def spoken(pairs, total):
    if total < 2:
        return "Necesito al menos dos trabajos para comparar."
    hi = [p for p in pairs if p["nivel"] == "muy parecidos"]
    mid = [p for p in pairs if p["nivel"] == "revisar"]
    if not pairs:
        return f"Comparé {total} trabajos: ninguno se parece demasiado a otro."
    txt = f"Comparé {total} trabajos. "
    if hi:
        txt += "Muy parecidos: " + "; ".join(f"{p['a']} y {p['b']} ({p['parecido']} %)" for p in hi[:5]) + ". "
    if mid:
        txt += f"Para revisar: {len(mid)} par{'es' if len(mid) != 1 else ''} más. "
    return txt + "Ojo: parecido no siempre es copia (pudieron estudiar juntos o seguir el mismo ejemplo); revisa las partes iguales en el informe."
