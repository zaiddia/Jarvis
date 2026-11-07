"""Revisar el PROCEDIMIENTO escrito a mano, no solo la respuesta (12.0). Lógica pura, sin Jarvis.

La IA con visión transcribe cada renglón del desarrollo del estudiante. SymPy comprueba cada paso contra el anterior
(¿es equivalente?), así se sabe en qué renglón exacto se equivocó; la IA solo explica ese error en palabras y le pone
una categoría de una lista fija. Con las categorías se arma el mapa de errores del curso («12 estudiantes fallan al
despejar») y el refuerzo justo para ese error.

Las expresiones se leen con la lista cerrada de símbolos de verificar.py (nunca se ejecuta texto libre).
"""
import datetime
import json
import os
import re
import threading

import verificar

CATEGORIAS = {
    "signo": "cambian el signo al pasar un término al otro lado",
    "despeje": "fallan al despejar (usan la operación que no es)",
    "distributiva": "aplican mal la propiedad distributiva",
    "fracciones": "se equivocan operando fracciones",
    "potencias": "confunden las propiedades de las potencias",
    "aritmetica": "cometen errores en las cuentas",
    "jerarquia": "no respetan el orden de las operaciones",
    "factorizacion": "factorizan mal",
    "terminos": "suman términos que no son semejantes",
    "otro": "cometen otros errores",
}
CORTO = {"signo": "el signo al trasponer", "despeje": "despejar", "distributiva": "la distributiva", "fracciones": "las fracciones",
         "potencias": "las potencias", "aritmetica": "las cuentas", "jerarquia": "el orden de las operaciones", "factorizacion": "factorizar",
         "terminos": "los términos semejantes", "otro": "otros errores"}

_lock = threading.Lock()
_path = None
data = {"cursos": {}}               # curso -> [{"fecha", "estudiante", "tema", "categoria", "detalle", "paso", "ok"}]


# ============================================================================ GUARDAR
def configure(config_dir):
    global _path
    _path = os.path.join(config_dir, "mapa_errores.json")
    load()


def load():
    data["cursos"] = {}
    if _path and os.path.exists(_path):
        try:
            with open(_path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d.get("cursos"), dict):
                data["cursos"] = d["cursos"]
        except (OSError, ValueError):
            pass


def save():
    if not _path:
        return
    with _lock:
        tmp = _path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _path)


def record(curso, estudiante, res, tema="", fecha=None):
    """Anota el resultado de una revisión en el mapa de errores del curso."""
    curso = curso or "Sin curso"
    fecha = fecha or datetime.date.today().isoformat()
    lst = data["cursos"].setdefault(curso, [])
    lst[:] = [e for e in lst if not (e["estudiante"] == estudiante and e["fecha"] == fecha and e["tema"] == (tema or res.get("problema", "")[:80]))]
    err = res.get("error")
    lst.append({"fecha": fecha, "estudiante": estudiante or "(sin nombre)", "tema": tema or res.get("problema", "")[:80],
                "categoria": err["categoria"] if err else "", "detalle": err["explicacion"][:240] if err else "",
                "paso": err["paso"] if err else 0, "ok": not err and res.get("respuesta_ok") is not False})
    del lst[:-800]
    save()


def error_map(curso, days=60, today=None):
    """{"total": revisados (estudiantes), "bien": n, "categorias": [(cat, n_estudiantes, [nombres])]} de los últimos días."""
    today = today or datetime.date.today()
    since = (today - datetime.timedelta(days=days)).isoformat()
    lst = [e for e in data["cursos"].get(curso, []) if e["fecha"] >= since]
    est = {e["estudiante"] for e in lst}
    by = {}
    for e in lst:
        if e["categoria"]:
            by.setdefault(e["categoria"], set()).add(e["estudiante"])
    cats = sorted(((c, len(s), sorted(s)) for c, s in by.items()), key=lambda x: -x[1])
    bien = sum(1 for s in est if all(e["ok"] for e in lst if e["estudiante"] == s))
    return {"total": len(est), "bien": bien, "categorias": cats}


def spoken_map(curso, m):
    if not m["total"]:
        return f"Todavía no he revisado procedimientos de {curso}. Tómale foto a un desarrollo y dime «revisa el procedimiento de Juan»."
    if not m["categorias"]:
        return f"En {curso} revisé {m['total']} estudiante{'s' if m['total'] != 1 else ''} y ninguno tuvo errores en el procedimiento."
    parts = [f"{n} {'estudiantes' if n != 1 else 'estudiante'} {CATEGORIAS.get(c, c) if n != 1 else _sing(CATEGORIAS.get(c, c))}"
             for c, n, _ in m["categorias"][:4]]
    top = m["categorias"][0][0]
    return (f"Mapa de errores de {curso} ({m['total']} revisados): " + "; ".join(parts) + ". "
            f"Si quieres, «prepara el refuerzo del error más común de {curso}» y hago un taller justo sobre {CORTO.get(top, top)}.")


def _sing(s):
    return (s.replace("cambian", "cambia").replace("fallan", "falla").replace("aplican", "aplica").replace("se equivocan", "se equivoca")
            .replace("confunden", "confunde").replace("cometen", "comete").replace("respetan", "respeta").replace("factorizan", "factoriza")
            .replace("suman", "suma").replace("usan", "usa"))


# ============================================================================ COMPROBAR PASO A PASO
def _split_eq(s):
    s = str(s).replace("≡", "=").replace("==", "=")
    if s.count("=") != 1:
        return None
    l, r = s.split("=")
    return (l.strip(), r.strip()) if l.strip() and r.strip() else None


def _clean_line(s):
    s = str(s or "").strip()
    s = re.sub(r"^(?:paso\s*\d+\s*[:.)-]|\d+\s*[.)]\s+|[⇒→⟹]|=>|->)\s*", "", s, flags=re.I).strip()
    return s.replace("÷", "/").replace("×", "*").replace(":", "/") if not re.search(r"[a-z]{4,}", s.lower()) else s


_MULTI = re.compile(r"^\s*([a-z])\s*=\s*[^=]+(?:\s*(?:,|;|\bo\b|\by\b)\s*(?:[a-z]\s*=\s*)?[^=,;]+)+$")


def _sol_line(s):
    """«x = 2 o x = 3», «x = 2, x = -3» → (variable, {valores}) o None."""
    s = _clean_line(s)
    if s.count("=") < 1 or not _MULTI.match(s) or not re.search(r"(?:,|;|\bo\b|\by\b)", s):
        return None
    import sympy
    var = s.strip()[0]
    try:
        return sympy.Symbol(var), verificar._values(s, sympy.Symbol(var))
    except Exception:
        return None


def equivalent(a, b):
    """¿Son equivalentes dos renglones (dos ecuaciones o dos expresiones)? → True | False | None (no se sabe)."""
    import sympy
    a, b = _clean_line(a), _clean_line(b)
    sl = _sol_line(b)
    if sl and _split_eq(a):                               # de «(x − 2)(x − 3) = 0» a «x = 2 o x = 3»
        try:
            x, got = sl
            ea = _split_eq(a)
            want = {q for q in sympy.solve(verificar._parse(ea[0]) - verificar._parse(ea[1]), x) if q.is_real is not False}
            return len(got) == len(want) and all(any(verificar._eq(g, w) for w in want) for g in got)
        except Exception:
            return None
    ea, eb = _split_eq(a), _split_eq(b)
    try:
        if ea and eb:
            da = verificar._parse(ea[0]) - verificar._parse(ea[1])
            db = verificar._parse(eb[0]) - verificar._parse(eb[1])
            syms = sorted(da.free_symbols | db.free_symbols, key=str)
            if not syms:                                  # «4 = 4», «8 = 8»
                return bool(sympy.simplify(da) == 0) == bool(sympy.simplify(db) == 0) if sympy.simplify(da) == 0 or sympy.simplify(db) == 0 \
                    else None
            if sympy.simplify(da) == 0 and sympy.simplify(db) == 0:
                return True
            if sympy.simplify(db) != 0:
                ratio = sympy.simplify(da / db)
                if ratio != 0 and not ratio.free_symbols:
                    return True
            if len(syms) == 1:
                x = syms[0]
                sa = {s for s in sympy.solve(da, x) if s.is_real is not False}
                sb = {s for s in sympy.solve(db, x) if s.is_real is not False}
                return len(sa) == len(sb) and all(any(verificar._eq(p, q) for q in sb) for p in sa)
            return False if _numeric_differs(da, db, syms) else None
        if not ea and not eb:
            return bool(verificar._eq(verificar._parse(a), verificar._parse(b)))
        if ea and not eb and b and a:                     # «2x + 3 = 7» seguido de «x = 2» ya trae «=»; esto es un valor suelto
            return None
    except Exception:
        return None
    return None


def _numeric_differs(da, db, syms):
    """Varias variables: se prueban puntos donde una se anula y la otra no."""
    import random
    import sympy
    rnd = random.Random(7)
    for _ in range(12):
        vals = {s: sympy.Rational(rnd.randint(-9, 9), rnd.randint(1, 4)) for s in syms}
        za, zb = sympy.simplify(da.subs(vals)) == 0, sympy.simplify(db.subs(vals)) == 0
        if za != zb:
            return True
    return False


def check_chain(lines, problema=""):
    """Comprueba cada renglón contra el anterior. → [{"paso": n (1 = primer renglón), "de", "a", "ok", "expr"}].
    El primer renglón se compara con el enunciado si es una ecuación o expresión."""
    out = []
    prev = _clean_line(problema) if problema and (_split_eq(_clean_line(problema)) or _parses(_clean_line(problema))) else ""
    for i, ln in enumerate(lines):
        cur = _clean_line(ln)
        if not cur or not _parses(cur):
            out.append({"paso": i + 1, "de": prev, "a": ln, "ok": None, "expr": False})
            continue
        if cur.startswith("=") and prev:                  # «= 3x + 6»: sigue la misma expresión
            base = _split_eq(prev)[1] if _split_eq(prev) else prev
            ok = equivalent(base, cur[1:])
            out.append({"paso": i + 1, "de": prev, "a": ln, "ok": ok, "expr": True})
            prev = cur[1:].strip()
            continue
        ok = equivalent(prev, cur) if prev else None
        out.append({"paso": i + 1, "de": prev, "a": ln, "ok": ok, "expr": True})
        if ok is not False:
            prev = cur
        else:
            prev = cur                                  # sigue desde lo que escribió (para no culpar los pasos siguientes)
    return out


def _parses(s):
    s = s[1:] if s.startswith("=") else s
    if _sol_line(s):
        return True
    try:
        e = _split_eq(s)
        if e:
            verificar._parse(e[0])
            verificar._parse(e[1])
        else:
            verificar._parse(s)
        return True
    except Exception:
        return False


def first_error(chk):
    return next((c for c in chk if c["ok"] is False), None)


def guess_category(de, a):
    """Una categoría sin la IA, por la forma de los dos renglones (para cuando la IA no está o no responde bien)."""
    import sympy
    try:
        ea, eb = _split_eq(_clean_line(de)), _split_eq(_clean_line(a))
        if ea and eb:
            L, R = verificar._parse(ea[0]), verificar._parse(ea[1])
            da = sympy.expand(L - R)
            db = sympy.expand(verificar._parse(eb[0]) - verificar._parse(eb[1]))
            cands = [da - 2 * t for t in sympy.Add.make_args(L)] + [da + 2 * t for t in sympy.Add.make_args(R)]
            for c in cands:                               # un término que cambió de lado sin cambiar de signo
                c = sympy.expand(c)
                if c != 0 and db != 0:
                    k = sympy.simplify(db / c)
                    if k != 0 and not k.free_symbols:
                        return "signo"
            if any(isinstance(q, sympy.Rational) and not q.is_integer for q in sympy.preorder_traversal(da)):
                return "fracciones"
            return "despeje"
        if "(" in de and "(" not in a:
            return "distributiva"
        if "^" in de or "²" in de:
            return "potencias"
        return "aritmetica"
    except Exception:
        return "otro"


# ============================================================================ PROMPTS
def read_prompt(que="", grado="", estudiante=""):
    return f"""Esta foto es el desarrollo escrito a mano de un ejercicio de matemáticas de {estudiante or 'un estudiante'} \
({grado or 'bachillerato'}).{(' El ejercicio era: ' + que + '.') if que else ''}
Transcribe EXACTAMENTE lo que escribió, renglón por renglón y en su orden, SIN corregir nada (si se equivocó, copia el error tal cual).
Responde SOLO un JSON:
{{"legible": true,
 "problema": "el enunciado o la ecuación de partida (si se ve), en texto plano",
 "pasos": ["cada renglón del desarrollo como expresión en texto plano: 2x + 3 = 7, luego 2x = 7 - 3 …"],
 "respuesta": "la respuesta final que dio (o vacío)",
 "nota_lectura": "algo que no se lee bien (o vacío)"}}
Texto plano: ^ para potencias, sqrt() para raíces, / para fracciones, * para multiplicar si hace falta. Un renglón por elemento. \
Si la foto no es un desarrollo de matemáticas o no se lee, "legible": false."""


def explain_prompt(problema, de, a, paso, grado=""):
    cats = ", ".join(f"«{k}» ({v})" for k, v in CATEGORIAS.items())
    return f"""Un estudiante de {grado or 'bachillerato'} resolvía: {problema or '(sin enunciado)'}.
En su paso {paso} pasó de «{de}» a «{a}», y eso NO es equivalente (lo comprobó SymPy).
Explícale al docente, en UNA frase corta y concreta, qué error cometió (por ejemplo: «en el paso 3 cambió el signo al pasar el 4: \
debía restar 4 en los dos lados»). Luego clasifícalo en UNA de estas categorías: {cats}.
Responde SOLO un JSON: {{"explicacion": "…", "categoria": "signo", "renglon_correcto": "cómo debía quedar ese renglón"}}"""


def clean_read(d):
    if not isinstance(d, dict):
        raise ValueError("la lectura no es un JSON")
    pasos = [re.sub(r"\s+", " ", str(p)).strip()[:160] for p in (d.get("pasos") or []) if str(p).strip()][:25]
    return {"legible": bool(d.get("legible", bool(pasos))) and bool(pasos), "problema": str(d.get("problema") or "").strip()[:200],
            "pasos": pasos, "respuesta": str(d.get("respuesta") or "").strip()[:120], "nota_lectura": str(d.get("nota_lectura") or "").strip()[:200]}


def clean_explain(d, de, a, paso):
    d = d if isinstance(d, dict) else {}
    cat = str(d.get("categoria") or "").lower().strip().strip("«»")
    cat = cat if cat in CATEGORIAS else guess_category(de, a)
    exp = str(d.get("explicacion") or "").strip()[:300] or f"En el paso {paso} el renglón «{a}» no es equivalente al anterior «{de}»."
    return {"paso": paso, "de": de, "a": a, "categoria": cat, "explicacion": exp, "correcto": str(d.get("renglon_correcto") or "").strip()[:120]}


def final_check(problema, respuesta, pasos):
    """¿La respuesta final es la correcta? (si el enunciado es una ecuación). → (True|False|None, correcta)."""
    src = _clean_line(problema)
    if not _split_eq(src):
        return None, ""
    res = respuesta or (pasos[-1] if pasos else "")
    c = verificar.check({"tipo": "ecuacion", "expr": src, "resultado": res})
    return c["ok"], c["correcto"]


def spoken(res, estudiante=""):
    quien = estudiante or "El estudiante"
    if not res["legible"]:
        return "No alcanzo a leer el desarrollo en la foto. Prueba con más luz, la hoja derecha y más cerca."
    n = len(res["pasos"])
    err = res.get("error")
    if err:
        t = f"{quien}: {err['explicacion']}"
        if err.get("correcto"):
            t += f" Debía quedar: {err['correcto']}."
        return t + (f" Los pasos anteriores ({err['paso'] - 1}) están bien." if err["paso"] > 1 else "")
    if res.get("respuesta_ok") is False:
        return f"{quien}: los {n} pasos son coherentes, pero la respuesta final no es la correcta ({res.get('correcta')})."
    nv = sum(1 for c in res["chequeo"] if c["ok"])
    return f"{quien}: el procedimiento está bien. Revisé {n} paso{'s' if n != 1 else ''}" + (f" y verifiqué {nv} con SymPy." if nv else ".") + \
        (" La respuesta final es correcta." if res.get("respuesta_ok") else "")


def docx(res, image_path, out_dir, Document, estudiante="", curso="", docente=""):
    from docx.shared import Pt, RGBColor, Inches
    folder = os.path.join(out_dir, "Revisiones", "Procedimientos")
    os.makedirs(folder, exist_ok=True)
    doc = Document()
    doc.add_heading(f"Revisión del procedimiento{(' · ' + estudiante) if estudiante else ''}", 1)
    meta = " · ".join(x for x in (curso, docente, datetime.date.today().strftime("%d/%m/%Y")) if x)
    if meta:
        doc.add_paragraph(meta)
    if res["problema"]:
        doc.add_paragraph().add_run("Ejercicio: ").bold = True
        doc.paragraphs[-1].add_run(res["problema"])
    err = res.get("error")
    for c in res["chequeo"]:
        p = doc.add_paragraph(style="List Number")
        r = p.add_run(c["a"])
        r.font.size = Pt(12)
        mark = {True: "  ✔", False: "  ✘", None: ""}[c["ok"]]
        m = p.add_run(mark)
        m.bold = True
        m.font.color.rgb = RGBColor(0x2E, 0x8B, 0x57) if c["ok"] else RGBColor(0xC0, 0x39, 0x2B)
    if err:
        doc.add_heading("Dónde está el error", 2)
        doc.add_paragraph(err["explicacion"])
        if err.get("correcto"):
            doc.add_paragraph(f"Debía quedar: {err['correcto']}")
        doc.add_paragraph(f"Tipo de error: {CORTO.get(err['categoria'], err['categoria'])}.")
    elif res.get("respuesta_ok") is False:
        doc.add_paragraph(f"Los pasos son coherentes, pero la respuesta final no es la correcta: {res.get('correcta')}.")
    else:
        doc.add_paragraph("El procedimiento está bien.")
    if image_path and os.path.exists(image_path):
        try:
            doc.add_picture(image_path, width=Inches(4.5))
        except Exception:
            pass
    name = re.sub(r"[^\w\s-]", "", f"Procedimiento {estudiante or 'estudiante'} {datetime.datetime.now():%Y-%m-%d %H%M}").strip()
    path = os.path.join(folder, name + ".docx")
    doc.save(path)
    return path
