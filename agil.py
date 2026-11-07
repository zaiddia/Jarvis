"""Jarvis más ágil (12.1). Lógica pura, sin Jarvis.

  · Cero silencio: la frase corta que Jarvis dice al instante cuando la IA va a tardar («A ver…», «Voy con eso…»).
  · Fin de turno: ¿la frase quedó completa o la persona sigue hablando («haz un quiz de… eh…»)?
  · Órdenes encadenadas: «pon un temporizador de 10 minutos, abre la pizarra y muéstrales el QR» → tres órdenes.
"""
import random
import re
import unicodedata


def norm(text):
    t = unicodedata.normalize("NFD", str(text or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s,;:%¿?¡!.-]", " ", t)).strip()


# ============================================================================ CERO SILENCIO
# Pocas frases fijas por tipo: se generan una vez y quedan en la caché de la voz, así suenan al instante.
ACKS = {
    "pregunta": ["A ver…", "Déjame pensarlo…", "Buena pregunta…", "Mmm, te cuento…"],
    "calculo": ["Calculo…", "Hago la cuenta…"],
    "pedido": ["Voy con eso…", "Dame un segundo…", "Ya mismo…"],
    "explicar": ["Te explico…", "Va, te lo explico…"],
    "buscar": ["Lo busco…", "Déjame revisar…"],
}
_KIND_RX = [
    ("calculo", r"\b(?:cuanto es|calcula|cuantos? (?:son|hay|da)|porcentaje|promedio|suma|resta|multiplica|divide)\b|\d+\s*[-+*/x%]\s*\d+"),
    ("explicar", r"\b(?:explica|explicame|por que|como funciona|que significa|define|diferencia entre)\b"),
    ("buscar", r"\b(?:busca|buscame|investiga|encuentra|que dice|que paso con)\b"),
    ("pregunta", r"^\s*¿|\?\s*$|^(?:que|quien|quienes|cual|cuales|como|cuando|donde|cuanto|cuanta|cuantos|cuantas)\b"),
]


def ack_kind(text):
    t = norm(text)
    for k, rx in _KIND_RX:
        if re.search(rx, t):
            return k
    return "pedido"


def ack_for(text, rnd=None, last=None):
    """La frase de espera para esta orden (sin repetir la última)."""
    opts = ACKS[ack_kind(text)]
    rnd = rnd or random
    choices = [o for o in opts if o != last] or opts
    return rnd.choice(choices)


def all_acks():
    return [a for v in ACKS.values() for a in v]


# ============================================================================ FIN DE TURNO
# Si la frase termina en una de estas palabras, casi seguro que la persona no ha terminado.
_DANGLING = {"de", "del", "a", "al", "para", "por", "con", "sin", "sobre", "en", "entre", "hasta", "desde", "hacia", "y", "o", "u", "e",
             "ni", "pero", "que", "porque", "pues", "como", "cuando", "donde", "si", "el", "la", "los", "las", "un", "una", "unos", "unas",
             "lo", "le", "les", "mi", "mis", "tu", "tus", "su", "sus", "este", "esta", "estos", "estas", "ese", "esa", "aquel",
             "eh", "ehh", "em", "emm", "mmm", "mm", "este", "osea", "o sea", "bueno", "entonces", "digo", "tipo", "cuyo", "cuya",
             "muy", "mas", "menos", "tan", "le", "se", "me", "te", "nos", "pon", "ponme", "haz", "hazme", "abre", "busca", "dime", "crea"}
_FILLER_END = re.compile(r"(?:\b(?:eh+|em+|m{2,}|este|o sea|bueno|entonces|digo)\s*)$")


def incomplete(text):
    """¿Parece que la persona sigue hablando? → True si la frase quedó colgando."""
    t = norm(text).rstrip(" .,;:")
    if not t or t.endswith(("?", "!")):
        return False
    if text.rstrip().endswith((",", "…", "...")):
        return True
    if _FILLER_END.search(t):
        return True
    words = t.split()
    if len(words) < 2:
        return words[0] in {"pon", "ponme", "haz", "hazme", "abre", "busca", "dime", "crea", "muestra", "lanza"} if words else False
    return words[-1] in _DANGLING


def merge(first, second):
    """Une las dos partes de la frase, quitando muletillas del final de la primera."""
    a = re.sub(r"[\s,]*\b(?:eh+|em+|m{2,}|este|o sea|bueno|digo)\s*[.…]*\s*$", "", first.strip(), flags=re.I).rstrip(" ,…")
    return (a + " " + second.strip()).strip()


# ============================================================================ ÓRDENES ENCADENADAS
# Solo se parte la frase cuando cada trozo empieza con un verbo de mando y es una orden completa.
_VERBS = (r"pon|ponme|ponle|abre|abreme|cierra|cierrame|proyecta|muestra|muestrame|muestrales|ensena|ensenales|lanza|lanzame|activa|desactiva|"
          r"apaga|enciende|prende|sube|baja|silencia|inicia|empieza|comienza|arranca|para|deten|pausa|reanuda|cancela|quita|borra|limpia|"
          r"reproduce|busca|buscame|abre|recuerdame|avisame|agenda|anota|apunta|manda|mandale|envia|enviale|escoge|elige|haz|hazme|crea|"
          r"creame|prepara|preparame|genera|guarda|exporta|sube|minimiza|maximiza|cambia|llama|lee|leeme|traduce|dime|reconoce|revisa")
_START = re.compile(rf"^(?:jarvis\s+)?(?:luego\s+|despues\s+|tambien\s+|y\s+)?(?:{_VERBS})\b")
# «pon 10 preguntas», «haz 3 ejercicios»: es parte del pedido anterior, no otra orden
_PART_OF_PREV = re.compile(r"^(?:pon|ponle|haz|hazle|agrega|incluye|anade|dale)\s+(?:\d+|un|una|dos|tres|cuatro|cinco|diez)\s+"
                           r"(?:preguntas?|ejercicios?|puntos?|opciones?|problemas?|minutos? de|imagen|imagenes|ejemplos?)\b")
_SEP = re.compile(r"\s*(?:,|;|\by luego\b|\by despu[eé]s\b|\bluego\b|\bdespu[eé]s\b|\by tambi[eé]n\b|\by\b)\s+", re.I)
_NEVER = re.compile(r"[:\"«»]|^(?:jarvis\s+)?(?:escribe|teclea|dicta|recuerda que|anota que|apunta que|dile|mandale un mensaje|envia un mensaje|"
                    r"escribele|responde|contesta)\b")


def split(text, max_parts=4):
    """Las órdenes de la frase. → [frase] si es una sola (lo normal), o la lista de órdenes."""
    raw = str(text or "").strip()
    t = norm(raw)
    if _NEVER.search(t) or len(t) > 260:
        return [raw]
    pieces = [p for p in _SEP.split(raw) if p and p.strip()]
    if len(pieces) < 2:
        return [raw]
    out = []
    for p in pieces:
        p = re.sub(r"^(?:luego|despu[eé]s|tambi[eé]n)\s+", "", p.strip(" .,;"), flags=re.I)
        n = norm(p)
        if out and (not _START.match(n) or _PART_OF_PREV.match(n) or len(n.split()) < 2):
            out[-1] = out[-1] + " y " + p                  # no es otra orden: sigue la anterior
        elif not out and not _START.match(n):
            return [raw]
        else:
            out.append(p)
    if len(out) < 2 or len(out) > max_parts:
        return [raw]
    return out
