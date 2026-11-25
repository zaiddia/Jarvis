"""12.56: que Jarvis suene a persona y no a robot. Lógica pura, sin Jarvis.

  · tone_of(respuesta) → el tono con que conviene decirla (alegre, calmado, ánimo, serio) y TONE_STYLE, la indicación
    para la voz de Gemini.
  · mood_of(lo que dijo la persona) → si suena cansada, estresada, frustrada, triste o contenta, y mood_rule(), la
    indicación para la IA (primero un gesto humano breve, luego la ayuda). Con señales de crisis, CRISIS_RULE.
  · vary(respuesta) → las confirmaciones fijas («Hecho.», «Listo.») dichas de formas distintas.
  · spoken_list(texto) → «Tienes: a; b; c.» dicho como se habla: «a, luego b, y por último c».
  · needs_check(pregunta) → si la respuesta trae datos que cambian (quién ocupa un cargo, precios, resultados, «hoy»)
    y conviene confirmarla con una búsqueda; facts_rule() le dice a la IA cómo usar lo encontrado.
"""
import random
import re
import unicodedata


def norm(text):
    t = unicodedata.normalize("NFD", str(text or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%$]", " ", t)).strip()


# ============================================================================ TONO DE LA VOZ
TONE_STYLE = {
    "alegre": "con alegría sincera y una sonrisa en la voz",
    "calmado": "con calma y suavidad, despacio y con cuidado",
    "animo": "con calidez y ánimo, como quien apoya a un amigo",
    "serio": "con serenidad y claridad, sin dramatizar",
}
BASE_STYLE = "natural, cálido y conversacional, a buen ritmo, con acento latinoamericano"

_ALEGRE = re.compile(r"\b(?:felicidades|felicitaciones|que bien|excelente|genial|buenisim[oa]|buena noticia|buenas noticias|lo lograste|"
                     r"lo logro|ganaste|gano|aprobo|aprobaron|aprobaste|feliz cumpleanos|que alegria|bien hecho|perfecto)\b")
_CALMADO = re.compile(r"\b(?:lo siento|lo lamento|lamento|que pena|siento mucho|perdon|disculpa|no pude|no logre|fallo|se cayo|"
                      r"tranquil[oa]|respira|no te preocupes)\b")
_ANIMO = re.compile(r"\b(?:animo|tu puedes|vas bien|vamos|lo vas a lograr|un paso a la vez|descansa|date un respiro|cuidate)\b")
_SERIO = re.compile(r"\b(?:urgente|atencion|cuidado|alerta|peligro|se vencio|vencido|vence hoy|emergencia|sismo|riesgo)\b")


def tone_of(text):
    """→ "alegre" | "calmado" | "animo" | "serio" | ""."""
    t = norm(text)
    if _SERIO.search(t):
        return "serio"
    if _CALMADO.search(t):
        return "calmado"
    if _ANIMO.search(t):
        return "animo"
    if _ALEGRE.search(t):
        return "alegre"
    return ""


def voice_style(text, base=BASE_STYLE):
    """La indicación de estilo para la voz de Gemini según lo que va a decir."""
    tone = tone_of(text)
    base = (base or "").strip().rstrip(".")
    return (base + ", " + TONE_STYLE[tone]) if tone and base else (TONE_STYLE[tone] if tone else base)


# ============================================================================ CÓMO ESTÁ LA PERSONA
_CRISIS = re.compile(r"\b(?:me quiero morir(?! de)|quiero morir(?:me)?(?! de)|no quiero (?:seguir )?vivir|quitarme la vida|matarme(?! (?:estudiando|trabajando|de|con))|suicid\w*|"
                     r"acabar con (?:todo|mi vida)|ya no aguanto (?:mas )?(?:la vida|vivir)|hacerme dano|no vale la pena vivir)\b")
_MOODS = (
    ("cansado", re.compile(r"\b(?:estoy (?:muy |super |re |tan )?(?:cansad[oa]|agotad[oa]|muert[oa] de cansancio|rendid[oa]|molid[oa])|"
                           r"que cansancio|no doy mas|dia (?:tan |muy )?(?:pesado|largo|duro|agotador)|no he dormido|dormi (?:muy )?mal|"
                           r"tengo sueno|sin energia)\b")),
    ("estresado", re.compile(r"\b(?:estoy (?:muy |super |re |tan )?(?:estresad[oa]|agobiad[oa]|abrumad[oa]|ansios[oa]|colapsad[oa])|"
                             r"que estres|tengo (?:mucho|demasiado) (?:trabajo|que hacer)|no me alcanza el tiempo|me tiene loc[oa]|"
                             r"estoy a full|voy tarde con todo)\b")),
    ("frustrado", re.compile(r"\b(?:no me sale|no funciona|otra vez lo mismo|ya lo intente|no entiendo nada|me tiene harto|"
                             r"estoy (?:harto|harta|aburrid[oa] de esto|frustrad[oa])|que rabia|que fastidio|que mamera|odio esto|"
                             r"nada me sale)\b")),
    ("triste", re.compile(r"\b(?:estoy (?:muy |un poco |tan )?(?:triste|desanimad[oa]|deprimid[oa]|bajonead[oa]|sol[oa])|me siento (?:mal|sol[oa]|triste)|"
                          r"tuve un mal dia|fue un mal dia|se murio|fallecio|perdi a)\b")),
    ("contento", re.compile(r"\b(?:estoy (?:muy |super |re |tan )?(?:feliz|content[oa]|emocionad[oa]|orgullos[oa])|que alegria|"
                            r"me fue (?:muy )?bien|lo logre|lo logramos|me ascendieron|me aprobaron|buenas noticias|gane)\b")),
)
MOOD_RULE = {
    "cansado": "La persona suena cansada. Empieza con una frase corta y humana que lo reconozca (sin exagerar ni dar sermones) y "
               "luego ayúdale de la forma más simple posible. Si viene al caso, sugiere una pausa.",
    "estresado": "La persona suena estresada o con mucha carga. Primero una frase breve y tranquila que lo reconozca; luego ayúdale "
                 "a ordenar: lo más urgente primero, en pasos cortos.",
    "frustrado": "La persona suena frustrada. Reconócelo en pocas palabras, sin culparla, y ve directo a una solución concreta "
                 "o a un camino distinto al que ya intentó.",
    "triste": "La persona suena triste o pasó por algo difícil. Responde con calidez y respeto, sin minimizar ni dar consejos "
              "que no pidió; pregunta con suavidad si quiere hablar o si prefiere que le ayudes con algo.",
    "contento": "La persona está contenta por algo. Alégrate con ella de forma sincera y breve antes de seguir.",
}
CRISIS_RULE = ("IMPORTANTE: la persona podría estar pensando en hacerse daño. Responde con mucha calidez y sin juzgar, dile que "
               "no está sola y que vale la pena hablar con alguien ahora mismo: la Línea 106 de salud mental (Colombia) o el "
               "123 si hay peligro inmediato, y una persona de confianza cerca. Pregúntale cómo está y quédate en la conversación. "
               "No des información que pueda usarse para hacerse daño.")


def mood_of(text):
    """→ "crisis" | "cansado" | "estresado" | "frustrado" | "triste" | "contento" | ""."""
    t = norm(text)
    if _CRISIS.search(t):
        return "crisis"
    for name, rx in _MOODS:
        if rx.search(t):
            return name
    return ""


HUMAN_RULE = (" Habla como una persona cercana, no como un sistema: varía tus frases, no empieces con «Claro» ni «Como asistente», "
              "no repitas la pregunta y, si encaja, una pizca de calidez o humor.")


def mood_rule(text):
    m = mood_of(text)
    if m == "crisis":
        return HUMAN_RULE + " " + CRISIS_RULE
    return HUMAN_RULE + ((" " + MOOD_RULE[m]) if m else "")


# ============================================================================ CONFIRMACIONES VARIADAS
VARIANTS = {
    "hecho": ("Hecho.", "Listo, ya quedó.", "Ya está.", "Ahí está.", "Listo."),
    "listo": ("Listo.", "Listo, ya quedó.", "Ya está.", "Hecho."),
    "cancelado": ("Cancelado.", "Listo, lo cancelé.", "Vale, no lo hago."),
    "vale, lo dejo": ("Vale, lo dejo.", "Listo, lo dejamos así.", "Está bien, no lo hago."),
    "hecho, profesor": ("Hecho, profesor.", "Listo, profesor.", "Ya quedó, profesor."),
}


def vary(text, rnd=random):
    """«Hecho.» → una de varias formas naturales. El resto del texto, igual."""
    s = str(text or "")
    key = norm(s)
    if key in VARIANTS and len(s) < 30:
        return rnd.choice(VARIANTS[key])
    return s


# ============================================================================ LISTAS DICHAS COMO SE HABLA
_LIST = re.compile(r"([^.:!?]{0,120}:\s+)([^.!?]+?;[^.!?]+?)([.!?]|$)")


def _join_spoken(items):
    items = [i.strip(" ,") for i in items if i.strip(" ,")]
    if len(items) < 2:
        return ", ".join(items)
    if len(items) == 2:
        return f"{items[0]}, y {items[1]}"
    if len(items) == 3:
        return f"{items[0]}, luego {items[1]}, y por último {items[2]}"
    return ", ".join(items[:-1]) + f", y por último {items[-1]}"


def spoken_list(text):
    """«Tienes 3 pendientes: a; b; c.» → «Tienes 3 pendientes: a, luego b, y por último c.» (solo para la voz)."""
    def rep(m):
        items = m.group(2).split(";")
        if len(items) < 2 or any(len(i) > 140 for i in items):
            return m.group(0)
        return m.group(1) + _join_spoken(items) + m.group(3)
    return _LIST.sub(rep, str(text or ""))


# ============================================================================ RESPUESTAS VERIFICADAS
_CHECK = re.compile(
    r"\b(?:quien es (?:el|la) (?:actual |nuev[oa] )?(?:presidente|presidenta|ministr[oa]|alcalde|alcaldesa|gobernador|gobernadora|rector|"
    r"director|directora|ceo|jefe|dueno|lider|entrenador|tecnico|campeon|papa)|quien (?:gano|va ganando|ganara)|"
    r"(?:actualmente|hoy en dia|sigue siendo|todavia (?:es|existe|vive|esta)|aun (?:es|existe|vive)|(?:el|la) actual)\b|"
    r"(?:cuanto (?:cuesta|vale|cuestan|valen)|que precio|a cuanto esta)|"
    r"(?:resultado|marcador) (?:del|de la|de los)|como (?:quedo|va|van) (?:el|la|los) (?:partido|juego|seleccion|elecciones?)|"
    r"(?:ultim[oa]s?|mas recientes?|nuev[oa]s?) (?:noticias?|version|modelo|ley|reforma|decreto|resolucion)|"
    r"(?:esta|este) (?:semana|mes|ano)|hoy|ayer|ahora mismo|en este momento|"
    r"(?:salario minimo|uvt|smmlv|tasa de interes|inflacion|trm)|(?:20[2-3]\d))\b")
_NO_CHECK = re.compile(r"\b(?:como estas|que tal|hola|gracias|buenos dias|buenas tardes|buenas noches|que hora|que dia es|fecha de hoy|mi |mis |tengo |recuerdame|cuentame un|chiste|poema|cuento|historia de|"
                       r"escribe|redacta|traduce|que significa|explicame|como se dice)\b")


def needs_check(question):
    """¿La respuesta depende de datos que cambian con el tiempo y conviene confirmarla con una búsqueda?"""
    t = norm(question)
    if len(t.split()) < 3 or len(t) > 300:
        return False
    return bool(_CHECK.search(t)) and not _NO_CHECK.search(t)


FACTS_RULE = (" Para esta pregunta se buscó en internet (resultados abajo). Úsalos para los datos que cambian con el tiempo "
              "(quién ocupa un cargo, precios, resultados, fechas recientes): si confirman la respuesta, dila con naturalidad y "
              "menciona de dónde viene en pocas palabras («según El Tiempo…»). Si no la confirman o se contradicen, dilo con "
              "honestidad («no lo pude confirmar») en vez de adivinar. No leas enlaces en voz alta.")


def facts_text(results, n=5):
    """Los resultados de la búsqueda como texto compacto: título, fuente y resumen."""
    out = []
    for r in (results or [])[:n]:
        title = str(r.get("titulo") or "").strip()
        snip = str(r.get("resumen") or "").strip()
        src = str(r.get("fuente") or "").strip()
        if title or snip:
            out.append(f"- {title} ({src}): {snip[:300]}")
    return "\n".join(out)
