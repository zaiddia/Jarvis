"""Modo Código (12.11): revisar, explicar y mejorar código, pensado para Tecnología e Informática. Lógica pura.

Primero una revisión SEGURA sin ejecutar nada: los errores de sintaxis reales (Python, JSON, HTML) con su línea exacta.
Después la IA explica qué hace, encuentra errores de lógica, sugiere mejoras, da el código corregido y arma ejercicios.
El código nunca se ejecuta.
"""
import ast
import html.parser
import json
import re

LANGS = {".py": "Python", ".pyw": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".ts": "TypeScript", ".html": "HTML", ".htm": "HTML",
         ".css": "CSS", ".java": "Java", ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".cs": "C#", ".php": "PHP",
         ".sql": "SQL", ".sh": "Bash", ".bat": "Batch", ".ps1": "PowerShell", ".ino": "Arduino", ".kt": "Kotlin", ".go": "Go",
         ".rb": "Ruby", ".rs": "Rust", ".pde": "Processing", ".json": "JSON", ".xml": "XML", ".sb3": "Scratch"}
CODE_EXTS = tuple(e for e in LANGS if e not in (".sb3",))
MAX_CHARS = 24000


def lang_of(name="", code=""):
    """El lenguaje por la extensión o, si se pegó en el chat, por cómo se ve."""
    m = re.search(r"(\.[a-z0-9]+)$", str(name).lower())
    if m and m.group(1) in LANGS:
        return LANGS[m.group(1)]
    c = str(code)
    if re.search(r"<!doctype html|<html|<body|<div|<p>|<head", c, re.I):
        return "HTML"
    if re.search(r"^\s*(?:def |class |import |from \S+ import |print\(|for \w+ in |while .+:|if .+:\s*$|elif )", c, re.M):
        return "Python"
    if re.search(r"#include\s*<|int main\s*\(", c):
        return "C++" if re.search(r"cout|std::|iostream", c) else "C"
    if re.search(r"public static void main|System\.out\.print", c):
        return "Java"
    if re.search(r"void setup\s*\(\)|void loop\s*\(\)|digitalWrite|pinMode", c):
        return "Arduino"
    if re.search(r"\bfunction\b|=>|\bconst \w+ =|\blet \w+ =|console\.log|document\.", c):
        return "JavaScript"
    if re.search(r"^\s*(?:SELECT|INSERT|UPDATE|CREATE TABLE)\b", c, re.I | re.M):
        return "SQL"
    if re.search(r"^\s*[.#]?[\w-]+\s*\{[^}]*:[^}]*\}", c, re.M):
        return "CSS"
    return "código"


def looks_like_code(text):
    t = str(text or "")
    lines = [ln for ln in t.splitlines() if ln.strip()]
    sym = len(re.findall(r"[{}();=<>\[\]:]", t))
    return (len(lines) >= 2 and sym >= 3) or bool(re.search(r"\b(?:def|print|function|console\.log|#include|public static|<html|SELECT)\b", t))


class _Tags(html.parser.HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr", "!doctype"}

    def __init__(self):
        super().__init__()
        self.stack, self.problems = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for t, ln in self.stack[i + 1:]:
                    self.problems.append({"linea": ln, "problema": f"la etiqueta <{t}> no se cerró antes de </{tag}>"})
                del self.stack[i:]
                return
        self.problems.append({"linea": self.getpos()[0], "problema": f"</{tag}> cierra una etiqueta que no estaba abierta"})


def syntax_check(code, lang):
    """Errores de sintaxis REALES, sin ejecutar nada. → [{"linea", "problema"}]."""
    code = str(code or "")
    out = []
    if lang == "Python":
        try:
            ast.parse(code)
        except SyntaxError as e:
            msg = {"invalid syntax": "sintaxis inválida", "expected ':'": "falta «:» al final de la línea",
                   "unexpected indent": "sangría (espacios) de más", "unindent does not match any outer indentation level":
                   "la sangría no coincide con la de arriba", "unterminated string literal": "una cadena de texto sin cerrar (falta una comilla)",
                   "EOL while scanning string literal": "una cadena de texto sin cerrar (falta una comilla)",
                   "expected an indented block": "falta la sangría del bloque (los espacios al inicio)"}
            raw = str(e.msg)
            out.append({"linea": e.lineno or 0, "problema": next((v for k, v in msg.items() if raw.startswith(k)), raw)})
        if "\t" in code and re.search(r"^ +\S", code, re.M):
            out.append({"linea": next(i for i, ln in enumerate(code.splitlines(), 1) if ln.startswith("\t")),
                        "problema": "mezcla tabuladores y espacios en la sangría"})
    elif lang == "JSON":
        try:
            json.loads(code)
        except json.JSONDecodeError as e:
            out.append({"linea": e.lineno, "problema": f"JSON inválido: {e.msg}"})
    elif lang == "HTML":
        p = _Tags()
        try:
            p.feed(code)
            p.close()
        except Exception:
            pass
        out += p.problems[:8]
        out += [{"linea": ln, "problema": f"la etiqueta <{t}> nunca se cerró"} for t, ln in p.stack
                if t not in ("html", "body", "head", "p", "li", "tr", "td", "th", "option")][:8]
    elif lang in ("JavaScript", "Java", "C", "C++", "C#", "Arduino", "CSS", "PHP", "Kotlin", "Go", "Rust", "TypeScript"):
        clean = re.sub(r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`", "", code, flags=re.S)
        for o, c, one, many in (("{", "}", "una llave", "llaves"), ("(", ")", "un paréntesis", "paréntesis"), ("[", "]", "un corchete", "corchetes")):
            d = clean.count(o) - clean.count(c)
            if d:
                kind = "de cierre" if d > 0 else "de apertura"
                out.append({"linea": 0, "problema": (f"falta {one} {kind}" if abs(d) == 1 else f"faltan {abs(d)} {many} {kind}") + f" ({o}{c})"})
    return out


def numbered(code):
    return "\n".join(f"{i:>3}| {ln}" for i, ln in enumerate(str(code).splitlines(), 1))


def review_prompt(code, lang, name="", findings=(), goal="revisar"):
    found = "".join(f"\n- línea {f['linea']}: {f['problema']}" for f in findings) or " ninguno"
    focus = {"explicar": "Lo más importante es EXPLICAR qué hace, paso a paso, para alguien que está aprendiendo.",
             "corregir": "Lo más importante es encontrar y CORREGIR los errores."}.get(goal, "Revisa todo: qué hace, errores y mejoras.")
    return (f"Eres un docente de Tecnología e Informática en Colombia revisando código {lang}" + (f" del archivo «{name}»" if name else "") +
            f". {focus} No ejecutes nada. Errores de sintaxis ya encontrados por el analizador:{found}\n"
            "Responde SOLO JSON: {\"resumen\": \"qué hace el programa, 2 a 4 frases sencillas\", "
            "\"errores\": [{\"linea\": n, \"problema\": \"qué está mal\", \"arreglo\": \"cómo arreglarlo\"}], "
            "\"mejoras\": [\"sugerencia concreta\"], \"nivel\": \"principiante|intermedio|avanzado\", "
            "\"pasos\": [\"explicación paso a paso de lo que hace, en orden\"], \"corregido\": \"el código completo corregido (o \\\"\\\" si no hay errores)\"}. "
            "Incluye los errores de sintaxis de la lista y los de lógica que veas (división por cero, variables sin definir, bucles infinitos, "
            "condiciones al revés, entradas sin convertir a número…). Máximo 8 errores y 6 mejoras. En español.\n\n"
            f"Código (con número de línea):\n{numbered(code[:MAX_CHARS])}")


def review_validate(d, findings=()):
    d = d if isinstance(d, dict) else {}
    errs = []
    for e in (d.get("errores") or [])[:10]:
        if isinstance(e, dict) and str(e.get("problema") or "").strip():
            try:
                ln = int(e.get("linea") or 0)
            except (TypeError, ValueError):
                ln = 0
            errs.append({"linea": ln, "problema": str(e["problema"]).strip()[:300], "arreglo": str(e.get("arreglo") or "").strip()[:400]})
    for f in findings:                                   # lo que encontró el analizador nunca se pierde
        if not any(e["linea"] == f["linea"] and f["linea"] for e in errs):
            errs.insert(0, {"linea": f["linea"], "problema": f["problema"], "arreglo": ""})
    return {"resumen": str(d.get("resumen") or "").strip()[:900], "errores": errs,
            "mejoras": [str(x).strip()[:300] for x in (d.get("mejoras") or []) if str(x).strip()][:6],
            "nivel": str(d.get("nivel") or "").strip()[:20], "pasos": [str(x).strip()[:400] for x in (d.get("pasos") or []) if str(x).strip()][:12],
            "corregido": str(d.get("corregido") or "").strip()[:MAX_CHARS]}


def exercises_prompt(code, lang, curso=""):
    return (f"Con este código {lang}, crea 4 ejercicios para estudiantes de colegio" + (f" de {curso}" if curso else "") +
            ": 1) predecir la salida, 2) encontrar el error (dale una versión con un error), 3) modificarlo (un cambio pequeño), "
            "4) ampliarlo (un reto). Para cada uno: enunciado claro y la respuesta para el docente. "
            "Responde SOLO JSON: {\"ejercicios\": [{\"tipo\": str, \"enunciado\": str, \"codigo\": str, \"respuesta\": str}]}. En español.\n\n"
            f"Código:\n{str(code)[:MAX_CHARS]}")


def exercises_validate(d):
    out = []
    for e in ((d or {}).get("ejercicios") or [])[:6] if isinstance(d, dict) else []:
        if isinstance(e, dict) and str(e.get("enunciado") or "").strip():
            out.append({k: str(e.get(k) or "").strip()[:3000] for k in ("tipo", "enunciado", "codigo", "respuesta")})
    return out


def spoken(r, name, lang, nlines):
    """Lo que se dice en el chat (el informe completo va en Word)."""
    parts = [f"Revisé {('«' + name + '»') if name else 'tu código'} ({lang}, {nlines} línea{'s' if nlines != 1 else ''})."]
    if r["resumen"]:
        parts.append(r["resumen"])
    if r["errores"]:
        parts.append("Errores: " + "; ".join((f"línea {e['linea']}: " if e["linea"] else "") + e["problema"] for e in r["errores"][:4])
                     + ("…" if len(r["errores"]) > 4 else "") + ".")
    else:
        parts.append("No encontré errores.")
    if r["mejoras"]:
        parts.append("Para mejorarlo: " + r["mejoras"][0])
    return " ".join(parts)
