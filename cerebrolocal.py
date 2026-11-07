"""Cerebro local (12.2): la mejor IA que cabe en TU computador, para trabajar sin internet ni clave. Lógica pura, sin Jarvis.

Primero se analiza si es posible (memoria, disco, Ollama) y qué modelo cabe; luego se descarga y se PRUEBA con tareas
reales de docente (un quiz en formato de datos, una cuenta, una respuesta en español) midiendo la velocidad. Solo se
deja si pasa: un modelo grande que tarda un minuto por respuesta no sirve en clase.
"""
import json
import re

GB = 1024 ** 3
# (nombre en Ollama, GB que ocupa más o menos, RAM mínima recomendada en GB). Del mejor al más liviano; si un nombre
# no existe en Ollama, se prueba el siguiente.
CANDIDATES = [
    ("gemma4:12b", 8.5, 16), ("gemma3:12b", 8.1, 16), ("qwen3:8b", 5.2, 12),
    ("gemma3:4b", 3.3, 8), ("qwen3:4b", 2.6, 8), ("llama3.2", 2.0, 6), ("gemma3:1b", 0.8, 4),
]
MIN_TPS = 5.0               # tokens por segundo: por debajo, una respuesta de 200 palabras tarda más de un minuto


def plan(ram_bytes, free_disk_bytes, ollama_ok, installed=()):
    """¿Es posible? → {"posible", "modelos" (a probar, en orden), "motivo", "ram", "disco"}."""
    ram, disk = ram_bytes / GB, free_disk_bytes / GB
    out = {"ram": round(ram, 1), "disco": round(disk, 1), "posible": False, "modelos": [], "motivo": ""}
    fits = [(n, size) for n, size, need in CANDIDATES if ram + 0.5 >= need]
    if not fits:
        out["motivo"] = f"tu equipo tiene {out['ram']} GB de memoria y hace falta al menos 4 GB para una IA local útil"
        return out
    have = [n for n, _ in fits if any(i == n or i.startswith(n + ":") or (":" not in n and i.split(":")[0] == n) for i in installed)]
    room = [n for n, size in fits if size + 2 <= disk or n in have]
    if not room:
        out["motivo"] = f"no hay espacio: quedan {out['disco']} GB libres y el modelo más pequeño que sirve necesita unos {fits[-1][1] + 2:.0f} GB"
        return out
    if not ollama_ok:
        out.update(motivo="falta Ollama (el programa que corre la IA en tu equipo)", modelos=room[:3], ollama=False)
        return out
    out.update(posible=True, modelos=room[:3])
    return out


def spoken_plan(p):
    if not p["posible"] and not p.get("modelos"):
        return f"No es posible por ahora: {p['motivo']}."
    head = f"Tu equipo tiene {str(p['ram']).replace('.', ',')} GB de memoria y {str(p['disco']).replace('.', ',')} GB libres. "
    best = p["modelos"][0]
    q = ("Con eso cabe un modelo de 12 mil millones de parámetros: hace bien quizzes, talleres y explicaciones; en razonamientos largos queda"
         " por debajo de la IA en línea." if "12b" in best else
         "Con eso cabe un modelo mediano: sirve para quizzes cortos y respuestas, pero se queda corto en planes largos." if any(s in best for s in ("8b", "4b"))
         else "Con eso solo cabe un modelo pequeño: sirve para respuestas cortas, no para materiales completos.")
    if not p["posible"]:
        return head + q + f" Pero {p['motivo']}. Di «instala Ollama» y luego «prepara la IA sin internet»."
    return head + q + f" Probaría {', '.join(p['modelos'])}, en ese orden, y dejo el primero que pase las pruebas. Di «prepara la IA sin internet»."


# ============================================================================ PRUEBAS CON TAREAS DE DOCENTE
TESTS = [
    {"id": "quiz", "prompt": "Crea un quiz de 2 preguntas de fracciones para grado 6. Responde SOLO un JSON: "
                             "{\"preguntas\": [{\"enunciado\": \"…\", \"opciones\": [\"a\", \"b\", \"c\", \"d\"], \"respuesta\": \"a\"}]}", "json": True},
    {"id": "cuenta", "prompt": "Un taller tiene 12 ejercicios y Juan hizo las tres cuartas partes. ¿Cuántos ejercicios hizo? Responde solo el número.",
     "json": False},
    {"id": "espanol", "prompt": "Explica en una sola frase, en español y para un estudiante de grado 7, qué es un número primo.", "json": False},
]


def grade(test_id, answer):
    """¿Pasó la prueba? → (True|False, nota)."""
    a = str(answer or "").strip()
    if test_id == "quiz":
        try:
            d = json.loads(a) if a.startswith("{") else json.loads(re.search(r"\{.*\}", a, re.S).group(0))
            qs = d.get("preguntas") or []
            ok = len(qs) >= 2 and all(len(q.get("opciones") or []) == 4 and str(q.get("respuesta", "")).strip().lower()[:1] in "abcd"
                                      and q.get("enunciado") for q in qs)
            return ok, "quiz en formato correcto" if ok else "el quiz no venía completo"
        except Exception:
            return False, "no devolvió un JSON válido"
    if test_id == "cuenta":
        nums = re.findall(r"\d+", a)
        return (bool(nums) and nums[0] == "9"), "cuenta bien" if nums and nums[0] == "9" else "se equivocó en la cuenta"
    if test_id == "espanol":
        t = a.lower()
        ok = len(a.split()) >= 6 and ("divisor" in t or "dividir" in t or "divisible" in t) and not re.search(r"\b(?:the|is|number)\b", t)
        return ok, "explica bien en español" if ok else "la explicación no fue clara o no fue en español"
    return False, ""


def verdict(results):
    """results: [{"modelo", "pruebas": [(id, ok, nota)], "tps": float|None, "error": ""}] → (modelo elegido o "", frase)."""
    good = []
    lines = []
    for r in results:
        if r.get("error"):
            lines.append(f"{r['modelo']}: no se pudo ({r['error']})")
            continue
        passed = sum(1 for _, ok, _ in r["pruebas"] if ok)
        tps = r.get("tps") or 0
        lines.append(f"{r['modelo']}: {passed} de {len(r['pruebas'])} pruebas, {tps:.0f} tokens por segundo".replace(".", ","))
        if passed >= len(r["pruebas"]) - 1 and r["pruebas"][0][1] and tps >= MIN_TPS:
            good.append(r["modelo"])
    if not good:
        return "", ("Probé: " + "; ".join(lines) + ". Ninguno fue a la vez correcto y rápido en tu equipo: sigo con el que tenías.")
    return good[0], ("Probé: " + "; ".join(lines) + f". Dejo {good[0]} como IA sin internet.")
