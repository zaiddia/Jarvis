"""12.52: estilos de respuesta, «lo clave primero» y «piénsalo bien / rápido». Funciones puras."""
import re

STYLES = {
    "normal": "",
    "breve": " ESTILO BREVE: responde en una sola frase corta (dos como mucho), sin saludo ni relleno.",
    "amable": " ESTILO AMABLE: cálido y cercano, con una palabra de ánimo cuando venga al caso, sin exagerar.",
    "divertido": " ESTILO DIVERTIDO: con humor ligero y alguna comparación graciosa, sin perder la exactitud ni burlarte de nadie.",
    "formal": " ESTILO FORMAL: trato de usted, lenguaje profesional y preciso, sin bromas.",
}
NAMES = {"normal": "normal", "breve": "breve", "amable": "amable", "divertido": "divertido", "formal": "formal"}

KEY_FIRST = (" Si la respuesta necesita más de tres frases, la PRIMERA frase dice lo principal (la conclusión o el dato que "
             "buscan) y después va el detalle.")

_STYLE = re.compile(r"^(?:jarvis\s+)?(?:(?:activa|pon|ponte|usa|cambia a|pasa a|quiero)\s+(?:el\s+)?)?(?:modo|estilo)\s+"
                    r"(breve|corto|amable|carinoso|divertido|chistoso|gracioso|formal|serio|normal|de siempre)\b"
                    r"|^(?:jarvis\s+)?(?:se|sé|habla)\s+(?:mas\s+)?(breve|corto|amable|divertido|formal)\b")
_ALIAS = {"corto": "breve", "carinoso": "amable", "chistoso": "divertido", "gracioso": "divertido", "serio": "formal",
          "de siempre": "normal"}

_DEEP = re.compile(r"^(?:jarvis\s*,?\s+)?(?:pienso?alo bien|piensalo bien|piensa bien|piensalo a fondo|piensa a fondo|"
                   r"a fondo|con calma|analizalo bien|razonalo bien)\s*[:,.]?\s+(.{6,})$")
_FAST = re.compile(r"^(?:jarvis\s*,?\s+)?(?:rapido|rapidito|en corto|en una frase|resumido)\s*[:,.]\s*(.{3,})$")


def style_from(t):
    """«modo breve» / «sé más amable» → nombre del estilo o "" si la frase no es eso."""
    m = _STYLE.search(t)
    if not m:
        return ""
    w = (m.group(1) or m.group(2) or "").strip()
    return _ALIAS.get(w, w) if _ALIAS.get(w, w) in STYLES else ""


def rule(style):
    return STYLES.get(style or "normal", "") + KEY_FIRST


def deep_question(t):
    m = _DEEP.match(t)
    return m.group(1).strip() if m else ""


def fast_question(t):
    m = _FAST.match(t)
    return m.group(1).strip() if m else ""


def deep_prompt(question):
    return ("Piensa esta pregunta con calma y a fondo antes de responder: considera alternativas, revisa tu razonamiento "
            "y da una respuesta clara y práctica. Empieza por la conclusión en una frase y luego explica. "
            "Español, sin markdown pesado.\n\nPregunta: " + question)
