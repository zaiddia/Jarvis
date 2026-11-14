"""12.27: Jarvis entiende lenguaje natural, no solo sus frases de siempre.

Antes: si la frase no calzaba con una de sus reglas, la IA solo podía elegir entre unas 38 acciones y 72 órdenes del PC;
el resto de lo que sabe hacer (la guía tiene cientos de frases) era invisible para ella, y lo que sonaba a pregunta
(«¿me ayudas con…?») iba directo a una charla.

Ahora, cuando ninguna regla la reconoce, la IA «traduce» lo que dijiste a la orden de Jarvis que corresponde —con tus
datos: horas, montos, nombres— y esa orden pasa por el camino de siempre. Así sirve cualquier habilidad que ya existe:
  «oye, mañana tengo que llevar el carro al taller temprano, no me dejes olvidarlo» → «recuérdame mañana a las 7 llevar el carro al taller»
  «lo del súper ayer fueron como 85 lucas» → «gasté 85 mil en mercado»
Si no está seguro entre dos cosas, pregunta en una línea con las dos órdenes completas. Si la orden traducida borra,
apaga, envía o paga algo que tú no dijiste con esas palabras, te pide permiso primero. Las preguntas de saber
(«¿qué es…?», «¿por qué…?») siguen yendo directo a la IA, sin este paso.
"""
import json
import re

import guia
import selector
from nucleo import J

NL_K = 24                                                  # ejemplos que ve la IA (los más parecidos a tu frase)…
_KNOW = re.compile(r"^(?:jarvis\s+)?(?:que es(?! mejor| peor| mas barato| mas caro)|que son|que significa|que fue|quien es|quien fue|quienes son|por que|porque|como funciona|"
                   r"como se (?:dice|escribe|hace|calcula|pronuncia)|explica|explicame|define|definicion de|diferencia entre|"
                   r"cual es (?:la|el) (?:capital|diferencia|significado|origen)|cuando (?:fue|nacio|murio|empezo|termino)|"
                   r"donde (?:queda|esta ubicad)|cuentame (?:sobre|de|acerca)|hablame (?:de|sobre)|que opinas|que piensas)\b")
_CHAT = re.compile(r"^(?:hola|buenas|buenos dias|buenas tardes|buenas noches|gracias|muchas gracias|ok|vale|listo|jaja\w*|"
                   r"como estas|que tal|chao|adios|hasta luego|te quiero|eres genial|bien|muy bien|perfecto)\b(?:\s+jarvis)?$")
_RISKY = re.compile(r"\b(?:borra\w*|elimina\w*|apaga\w*|reinicia\w*|desinstala\w*|formatea\w*|cierra\w*|envia\w*|manda\w*|"
                    r"publica\w*|paga\w*|vacia\w*|cancela\w*|bloquea\w*|suspende\w*|transfiere\w*|desconecta\w*|restaura\w*)\b")
nl_state = {"last": None}                                  # lo último que entendió (para el registro y las pruebas)


def nl_examples(text, k=NL_K):
    """Las frases de Jarvis más parecidas a lo que dijiste (de la guía y de las órdenes del asistente)."""
    seen, items = set(), []
    for cat in J.guide():
        for g in cat["grupos"]:
            exs = [e["t"] for e in g["ejemplos"] if e["probar"]]
            for e in exs:
                if e not in seen:
                    seen.add(e)
                    items.append((e, f"{re.sub(r'[(][0-9.]+[)]', '', g['nombre'])}: {e}"))
    for o in J.ASSISTANT_ORDERS:
        if o not in seen:
            seen.add(o)
            items.append((o, o))
    tag = ""
    try:
        tag = J.memory_embed_tag()
    except Exception:
        pass
    return selector.choose(text, items, k=k, embed=J.memory_embed if tag else None, tag="nl-" + tag if tag else "")


def nl_catalog(text):
    """Lo que ve la IA: las más parecidas a tu frase y, debajo, una frase de cada habilidad (así no se le escapa ninguna
    aunque no haya palabras en común: «85 lucas en el súper» no comparte palabras con «gasté 20 mil en almuerzo»)."""
    near = nl_examples(text)
    general = J.current_mode() == "general"
    rest = []
    for cat in J.guide():
        if general and cat["id"] == "colegio":
            continue
        for g in cat["grupos"]:
            exs = [e["t"] for e in g["ejemplos"] if e["probar"]]
            if exs and not set(exs) & set(near):
                rest.append(exs[0])
    return near, rest


def nl_prompt(text, examples, more=()):
    ex = "\n".join(f"- {e}" for e in examples)
    return ("Eres la parte de Jarvis que entiende lo que la persona quiere. Jarvis es un asistente de voz en español (Colombia) "
            "que hace cosas en el PC y en la vida diaria, y las reconoce con frases como estas:\n" + ex + "\n"
            + (("Otras cosas que sabe hacer (una frase de cada una): " + " · ".join(more) + "\n") if more else "") + "\n"
            f"La persona dijo: «{text}»\n\n"
            "Si pide que Jarvis HAGA algo que se parece a una de esas frases, reescríbelo como una orden corta en ese estilo, con "
            "los datos de la persona (horas, montos, nombres, lugares). Conserva «hoy», «mañana», «el viernes», «en 10 minutos» "
            "tal cual. No inventes datos que la persona no dijo. Si dice «lucas» o «barras», son miles de pesos.\n"
            "Si es una pregunta de saber, una charla o algo que esas frases no cubren, no lo conviertas.\n"
            "Si dudas entre dos órdenes, pide aclarar con las dos completas.\n"
            'Responde SOLO con JSON: {"tipo": "orden" | "pregunta" | "charla" | "aclarar", "orden": "…", '
            '"opciones": ["…", "…"], "seguro": true}')


def nl_parse(raw):
    """Lo que devolvió la IA, ya limpio. → {"tipo", "orden", "opciones", "seguro"}."""
    try:
        d = J._extract_json(raw) if not isinstance(raw, dict) else raw
    except Exception:
        d = None
    if not isinstance(d, dict):
        return {"tipo": "pregunta", "orden": "", "opciones": [], "seguro": False}
    tipo = str(d.get("tipo") or "").strip().lower()
    tipo = tipo if tipo in ("orden", "pregunta", "charla", "aclarar") else "pregunta"
    orden = re.sub(r"\s+", " ", str(d.get("orden") or "")).strip(" «»\"'.")[:300]
    ops = [re.sub(r"\s+", " ", str(o)).strip(" «»\"'.")[:200] for o in (d.get("opciones") or []) if str(o).strip()][:3]
    if tipo == "orden" and not orden:
        tipo = "pregunta"
    if tipo == "aclarar" and len(ops) < 2:
        tipo, orden = ("orden", ops[0] if ops else orden) if (ops or orden) else ("pregunta", "")
    return {"tipo": tipo, "orden": orden, "opciones": ops, "seguro": d.get("seguro") is not False}


def nl_should_try(text, t):
    if not J.settings.get("nl_understand", True) or getattr(J._tl, "nl_pass", False):
        return False
    if J.state.get("ai") != "ok" or len(t.split()) < 2 or _KNOW.match(t) or _CHAT.match(t):
        return False
    return True


def nl_risky(orden, t):
    """¿La orden traducida hace algo delicado que la persona no dijo con esas palabras?"""
    for m in _RISKY.finditer(J.normalize(orden)):
        if m.group(0)[:5] not in t:
            return True
    return False


def nl_run(orden):
    """Pasa la orden traducida por el camino de siempre. → True si alguna regla la atendió."""
    J._tl.nl_pass, J._tl.nl_missed = True, False
    try:
        J.process_command(orden)
        return not J._tl.nl_missed
    finally:
        J._tl.nl_pass, J._tl.nl_missed = False, False


def nl_understand(text, t):
    """La capa de comprensión. → True si ya quedó atendido; False para seguir con la IA de siempre."""
    if not nl_should_try(text, t):
        return False
    ack = J.ack_start(text)
    old = getattr(J._tl, "fast_model", "")
    J._tl.fast_model = J.fast_model()                     # el modelo rápido: esto es solo entender, no responder
    try:
        raw = J.ai_chat([{"role": "user", "content": nl_prompt(text, *nl_catalog(text))}], json_mode=True, max_tokens=220)
    except Exception as e:
        J.log_terminal(f"Comprensión: no pude preguntarle a la IA ({getattr(e, 'why', e)}); sigo como siempre.", "COMPRENSIÓN")
        return False
    finally:
        J._tl.fast_model = old
        ack.done()
    d = nl_parse(raw)
    nl_state["last"] = dict(d, frase=text)
    if d["tipo"] == "aclarar":
        J.reply("¿Cuál de estas? " + " o ".join(f"«{o}»" for o in d["opciones"]) + ". Dímela así y la hago.", "COMPRENSIÓN")
        return True
    if d["tipo"] != "orden" or J.normalize(d["orden"]) == t:
        return False
    orden = d["orden"]
    J.log_terminal(f"Entendí «{text.strip()}» como «{orden}».", "COMPRENSIÓN")
    if not d["seguro"] or nl_risky(orden, t):
        J.request_approval("orden", f"¿Hago «{orden}»?", f"Lo entendí de: «{text.strip()}»",
                           on_ok=lambda: nl_run(orden) or J.reply(f"No supe hacer «{orden}».", "COMPRENSIÓN"),
                           on_no=lambda: J.reply("Vale, no lo hago. Dímelo con otras palabras.", "COMPRENSIÓN"),
                           say=f"Entendí: {orden}. ¿Lo hago? Di «sí» o «no».")
        return True
    if not getattr(J._tl, "remote", False):
        J.card("tip", "Entendí", orden, "🧠", secs=6)
    if nl_run(orden):
        return True
    J.log_terminal(f"«{orden}» tampoco la reconocí; lo respondo con la IA.", "COMPRENSIÓN")
    return False


__all__ = ['NL_K', '_CHAT', '_KNOW', '_RISKY', 'nl_catalog', 'nl_examples', 'nl_parse', 'nl_prompt', 'nl_risky', 'nl_run', 'nl_should_try',
           'nl_state', 'nl_understand']
