"""12.74: qué IA hace cada trabajo, y a quién pasar si una falla. Lógica pura.

  · Código (generar, revisar, corregir): la mejor para programar entre las que tienes con clave.
  · Si tu IA se llena o se cae: una cadena de respaldos (nunca se queda parado), la de tu PC de última.
  · La que acaba de fallar descansa un momento: las siguientes preguntas van directo a la que sí responde (más rápido).
  · Generar código: el pedido → código, y el analizador lo revisa; si tiene errores, la IA lo corrige sola.
"""
import re
import time

# Las que programan mejor primero. (proveedor, modelo; "" = el que tengas elegido para ese proveedor)
CODE_RANK = (("anthropic", ""), ("chatgpt", ""), ("deepseek", ""), ("nvidia", "moonshotai/kimi-k3.1-pro"), ("kimi", ""),
             ("zai", "glm-4.7-flash"), ("iteracompute", ""), ("mistral", ""), ("openrouter", ""), ("gemini", ""), ("groq", ""))
STRONG_CODERS = ("anthropic", "chatgpt", "deepseek", "kimi")
# Después de los de siempre (BACKUP_ORDER), los demás que tengan clave; los de servidores en China, al final y solo sin
# nombres de estudiantes; y la IA de tu PC de última
EXTRA_BACKUP = ("deepseek", "anthropic", "chatgpt", "kimi", "mistral", "groq", "openrouter", "xai")
CN_BACKUP = ("zai", "sensenova")
DOWN_SECS = {"quota": 120, "server": 90, "balance": 3600, "key": 3600, "perm": 3600, "region": 6 * 3600}

_CODE_WORDS = re.compile(r"```|\b(?:codigo|programa|script|funcion|clase|python|javascript|html|css|java|arduino|sql|c\+\+|depura|"
                         r"compila|sintaxis|algoritmo|bucle|variable)\b", re.I)


def is_code(messages, flag=False):
    """¿Es un trabajo de programar? (lo marca quien llama, o lo delata un bloque de código en lo último que escribiste)."""
    if flag:
        return True
    last = ""
    for m in reversed(messages or []):
        if m.get("role") == "user":
            c = m.get("content")
            last = c if isinstance(c, str) else " ".join(p.get("text", "") for p in c if isinstance(p, dict))
            break
    return "```" in last and bool(_CODE_WORDS.search(last))


def code_choice(current, keys, want="auto"):
    """(proveedor, modelo) para programar, o None si la tuya ya es buena (o no hay otra). keys: proveedores con clave."""
    if want == "off":
        return None
    if want not in ("auto", "") and want in keys:
        return (want, "") if want != current else None
    if current in STRONG_CODERS:
        return None
    for pid, model in CODE_RANK:
        if pid in keys:
            return None if pid == current and not model else (pid, model)
    return None


def backup_chain(current, keys, first="", has_names=False, local=False, want="auto"):
    """[proveedores] en el orden en que se piden ayuda si la tuya falla."""
    if want == "off":
        return []
    out = [first] if first and first != current else []
    for pid in EXTRA_BACKUP + (() if has_names else CN_BACKUP):
        if pid in keys and pid != current and pid not in out:
            out.append(pid)
    if local and current != "motor":
        out.append("motor")
    return out


def down_until(kind, now=None):
    return (time.time() if now is None else now) + DOWN_SECS.get(kind, 60)


# ============================================================================ GENERAR CÓDIGO
_LANG_WORDS = (("Python", r"\bpython\b|\bpy\b"), ("JavaScript", r"\bjavascript\b|\bjs\b"), ("HTML", r"\bhtml\b|pagina web|\bweb\b"),
               ("Arduino", r"\barduino\b"), ("Java", r"\bjava\b"), ("C++", r"c\+\+|\bcpp\b"), ("C", r"\ben c\b|\blenguaje c\b"),
               ("SQL", r"\bsql\b|consulta"), ("CSS", r"\bcss\b"), ("Scratch", r"\bscratch\b"), ("PSeInt", r"\bpseint\b|pseudocodigo"))
EXT = {"Python": ".py", "JavaScript": ".js", "HTML": ".html", "Arduino": ".ino", "Java": ".java", "C++": ".cpp", "C": ".c", "SQL": ".sql",
       "CSS": ".css", "Scratch": ".txt", "PSeInt": ".psc"}


def lang_from(desc, default="Python"):
    low = str(desc or "").lower()
    for name, rx in _LANG_WORDS:
        if re.search(rx, low):
            return name
    return default


def gen_prompt(desc, lang, curso=""):
    return (f"Eres un programador experto y docente de Tecnología e Informática en Colombia. Escribe un programa en {lang} que haga "
            f"esto: «{str(desc).strip()[:2000]}»" + (f". Es para estudiantes de {curso}" if curso else "") +
            ". Que funcione a la primera, claro y comentado en español, con nombres de variables en español, validando las entradas "
            "y sin librerías raras. Responde SOLO JSON: {\"codigo\": \"el programa completo\", \"explicacion\": \"qué hace y cómo, "
            "3 a 5 frases sencillas\", \"como_probarlo\": [\"entrada de ejemplo → salida esperada\"], \"nombre\": \"nombre_de_archivo\"}.")


def fix_prompt(code, lang, findings):
    found = "".join(f"\n- línea {f['linea']}: {f['problema']}" for f in findings)
    return (f"Este programa {lang} tiene estos errores de sintaxis encontrados por el analizador:{found}\n"
            "Corrígelo sin cambiar lo que hace. Responde SOLO JSON: {\"codigo\": \"el programa completo corregido\"}.\n\n"
            f"Código:\n{str(code)[:24000]}")


def gen_validate(d, lang):
    d = d if isinstance(d, dict) else {}
    code = re.sub(r"^```[\w+-]*\n|\n?```\s*$", "", str(d.get("codigo") or "").strip())
    name = re.sub(r"\.\w{1,5}$", "", str(d.get("nombre") or "programa").strip())
    name = re.sub(r"[^\w\-]+", "_", name)[:40].strip("_") or "programa"
    return {"codigo": code[:24000], "explicacion": str(d.get("explicacion") or "").strip()[:1200],
            "como_probarlo": [str(x).strip()[:300] for x in (d.get("como_probarlo") or []) if str(x).strip()][:6],
            "nombre": name + EXT.get(lang, ".txt"), "lenguaje": lang}


__all__ = ["CODE_RANK", "STRONG_CODERS", "EXTRA_BACKUP", "CN_BACKUP", "DOWN_SECS", "EXT", "is_code", "code_choice", "backup_chain",
           "down_until", "lang_from", "gen_prompt", "fix_prompt", "gen_validate"]
