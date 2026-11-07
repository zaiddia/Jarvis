"""Dos cerebros (12.1): lo simple lo contesta un modelo rápido y lo difícil el modelo potente. Lógica pura, sin Jarvis.

  · classify(texto) → "rapido" o "profundo", por la forma de la petición (sin gastar una llamada a la IA).
  · El modelo rápido puede pasar la pregunta al potente si no está seguro: responde solo ESCALAR.
  · fast_model_for(...) escoge el modelo rápido de la misma cuenta cuando no lo pusiste en Ajustes.
"""
import re
import unicodedata

ESCALATE = "ESCALAR"
FAST_RULE = (f" Responde breve y directo. Si la pregunta necesita razonamiento largo, planear, analizar datos, comparar en detalle o "
             f"escribir un documento, o si no estás seguro de la respuesta, responde SOLO la palabra {ESCALATE} (nada más).")

_DEEP = re.compile(
    r"\b(?:planea|planeame|planifica|disena|disename|analiza|analizame|compara|comparame|evalua|argumenta|justifica|demuestra|"
    r"redacta|escribe(?:me)? (?:un|una) (?:ensayo|informe|carta|correo|documento|proyecto|propuesta)|elabora|desarrolla|"
    r"paso a paso|en detalle|detalladamente|a fondo|profundiza|ventajas y desventajas|pros y contras|estrategia|"
    r"por que (?:crees|piensas)|que opinas|como podria|como puedo mejorar|ayudame a (?:pensar|decidir|planear|organizar)|"
    r"resuelve|resuelveme|soluciona|deriva|integra|probabilidad de|optimiza|corrige este|revisa este|traduce este texto)\b")
_FAST = re.compile(
    r"^(?:hola|buenos dias|buenas tardes|buenas noches|gracias|ok|vale|chao|adios|como estas|que tal)\b|"
    r"\b(?:cuanto es|que hora|que dia|capital de|cuantos (?:anos|dias|metros|litros|gramos)|como se dice|como se escribe|sinonimo de|"
    r"antonimo de|que significa|quien (?:es|fue|invento|escribio|descubrio|pinto)|cuando (?:fue|nacio|murio|es)|donde (?:queda|esta)|"
    r"convierte|cuantas? \w+ (?:tiene|hay en)|define|definicion de)\b")


def norm(text):
    t = unicodedata.normalize("NFD", str(text or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


def classify(text):
    """→ "rapido" | "profundo"."""
    t = norm(text)
    words = len(t.split())
    if _DEEP.search(t) or words > 40 or t.count("?") > 1 or t.count(",") >= 4:
        return "profundo"
    if _FAST.search(t) or words <= 12:
        return "rapido"
    return "profundo"


def escalated(answer):
    """¿El modelo rápido pidió pasar la pregunta al potente?"""
    a = str(answer or "").strip().strip("*.\"' ").upper()
    return a.startswith(ESCALATE) and len(a) < len(ESCALATE) + 12


# Modelos rápidos preferidos (si existen en la cuenta), del más rápido al menos rápido.
_FAST_HINTS = ("flash-lite", "flash-8b", "lite", "mini", "haiku", "nano", "small", "8b", "flash", "instant", "turbo")


def fast_model_for(main, available):
    """El modelo rápido de la lista de la cuenta («gemini-3.8-flash-lite» para «gemini-3.8-pro»…). "" si no hay uno mejor."""
    main_l = str(main or "").lower()
    cands = [m for m in available if m and m.lower() != main_l and not re.search(r"embed|tts|image|vision|audio|live|realtime|guard|moderat",
                                                                                   m.lower())]
    if any(_has(main_l, h) for h in _FAST_HINTS[:7]):
        return ""                                          # el principal ya es rápido: no hace falta otro
    fam = re.split(r"[-_]", main_l)[0]                     # misma familia (gemini, gpt, claude, deepseek…)
    for h in _FAST_HINTS:
        same = [m for m in cands if _has(m.lower(), h) and m.lower().startswith(fam)]
        if same:
            return sorted(same, key=lambda m: (-_ver(m), len(m)))[0]
    return ""


def _has(name, hint):
    """«mini» como parte del nombre (gpt-5-mini), no dentro de otra palabra (gemini)."""
    return bool(re.search(rf"(?:^|[-_.:/]){re.escape(hint)}(?:$|[-_.:])", name))


def _ver(name):
    m = re.search(r"(\d+(?:\.\d+)?)", name)
    return float(m.group(1)) if m else 0.0
