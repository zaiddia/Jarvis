"""12.66: reclamos y derechos de petición, extracto bancario, plan para salir de deudas, «¿esto es verdad?», exámenes de
laboratorio y profesor de inglés. Lógica pura, sin Jarvis.
"""
import datetime
import math
import re
import unicodedata


def norm(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


# ============================================================================ RECLAMOS Y DERECHOS DE PETICIÓN
# (clave, patrón de la entidad, a quién se escala si no responde, cómo)
SECTORS = (
    ("magisterio", r"fomag|magisterio|salud del magisterio|fondo de prestaciones|horus|sumimedical|fiduprevisora|ips del magisterio",
     "la Superintendencia Nacional de Salud (Supersalud), que vigila al Fomag, en supersalud.gov.co, con el radicado del Fomag",
     "Los docentes están en el régimen especial del magisterio: el reclamo va al Fomag (y con copia a la IPS que te atiende), no a una "
     "EPS. Si está en riesgo tu salud o tu vida, no esperes: puedes poner una acción de tutela (te ayudo a redactarla)."),
    ("salud", r"\beps\b|sura|sanitas|nueva eps|compensar|famisanar|salud total|coomeva|coosalud|mutual ser|savia|aliansalud|ips|hospital|clinica|medic|examen|cita|cirugia|autoriza",
     "la Superintendencia Nacional de Salud (Supersalud), en supersalud.gov.co",
     "Si está en riesgo tu salud o tu vida, no tienes que esperar: puedes poner una acción de tutela (te ayudo a redactarla)."),
    ("telecom", r"\bclaro\b|movistar|\btigo\b|\bwom\b|\betb\b|une\b|internet|celular|plan de datos|linea telefonica|television",
     "la Superintendencia de Industria y Comercio (SIC), en sic.gov.co, con el número de radicado de tu reclamo",
     "En telecomunicaciones, si la empresa no te responde en 15 días hábiles, opera el silencio administrativo positivo: se entiende a tu favor."),
    ("servicios", r"\bepm\b|emcali|enel|codensa|vanti|gases|acueducto|energia|luz|agua|gas natural|aseo|air-e|afinia|celsia",
     "la Superintendencia de Servicios Públicos Domiciliarios (Superservicios), en superservicios.gov.co",
     "En servicios públicos, si la empresa no te responde en 15 días hábiles, opera el silencio administrativo positivo: se entiende a tu favor."),
    ("banco", r"banco|bancolombia|davivienda|bbva|av villas|colpatria|scotiabank|nequi|daviplata|tarjeta de credito|credito|fondo de pensiones|porvenir|proteccion|colfondos|seguro",
     "el Defensor del Consumidor Financiero de la entidad y luego la Superintendencia Financiera, en superfinanciera.gov.co",
     ""),
    ("publica", r"alcaldia|gobernacion|secretaria|ministerio|registraduria|sisben|icbf|colpensiones|dian|transito|policia|personeria|entidad publica",
     "la Personería de tu municipio o la Procuraduría (procuraduria.gov.co)",
     "Si no te responden, puedes poner una acción de tutela por violación del derecho de petición."),
    ("consumo", r".",
     "la Superintendencia de Industria y Comercio (SIC), en sic.gov.co, con la copia de tu reclamo",
     "Si es por la garantía de un producto, la ley te da derecho a reparación, cambio o devolución del dinero (Ley 1480 de 2011)."),
)
DAYS_TO_ANSWER = 15            # Ley 1755 de 2015, art. 14: peticiones en 15 días hábiles (información y documentos, 10)


def sector_of(text):
    t = norm(text)
    for key, rx, escala, nota in SECTORS:
        if re.search(rx, t):
            return key, escala, nota
    return SECTORS[-1][0], SECTORS[-1][2], SECTORS[-1][3]


def business_deadline(start, n, holidays=()):
    """La fecha en que vence un plazo de n días hábiles contados desde el día siguiente a start (sin sábados, domingos ni festivos)."""
    d, left, hol = start, n, set(holidays)
    while left > 0:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5 and d not in hol:
            left -= 1
    return d


def letter_prompt(kind, entidad, hechos, nombre="", ciudad=""):
    doc = {"peticion": "un DERECHO DE PETICIÓN (artículo 23 de la Constitución y Ley 1755 de 2015)",
           "tutela": "una ACCIÓN DE TUTELA (artículo 86 de la Constitución y Decreto 2591 de 1991), como borrador para revisar",
           "queja": "una QUEJA ante la superintendencia que corresponda, como persona natural"}[kind]
    return (f"Redacta {doc} en Colombia, dirigido a «{entidad}», por estos hechos que cuenta el usuario: «{hechos}». "
            f"Peticionario: {nombre or '[NOMBRE COMPLETO]'}, cédula [NÚMERO], {ciudad or '[CIUDAD]'}, correo y teléfono [DATOS]. "
            "Estructura: ciudad y fecha; destinatario; referencia; HECHOS numerados (solo los que contó; deja [entre corchetes] lo "
            "que falte, como fechas o números de radicado); PETICIONES concretas y numeradas; FUNDAMENTOS DE DERECHO (solo normas "
            "que conozcas con seguridad); ANEXOS sugeridos; NOTIFICACIONES; firma. Español formal y claro, texto plano. "
            + ("Es un docente afiliado al régimen especial de salud del magisterio: dirígelo al FONDO NACIONAL DE PRESTACIONES SOCIALES "
               "DEL MAGISTERIO (FOMAG), con copia a la IPS que lo atiende [NOMBRE DE LA IPS], y menciona que es afiliado al régimen "
               "del magisterio (Ley 91 de 1989). " if sector_of(f"{entidad} {hechos}")[0] == "magisterio" else "")
            + ("Incluye el juramento de no haber presentado otra tutela por los mismos hechos y pide medida provisional si hay "
               "urgencia en salud. " if kind == "tutela" else "")
            + "No inventes hechos ni números.")


# ============================================================================ EXTRACTO BANCARIO
def statement_prompt():
    return ("Este es el extracto de una cuenta o tarjeta de crédito de Colombia. Analízalo para el dueño, en español y texto "
            "plano, con estas secciones:\n"
            "RESUMEN: periodo, total gastado, pagos, saldo y, si es tarjeta, pago mínimo, pago total y fecha límite.\n"
            "EN QUÉ SE TE VA LA PLATA: totales por categoría (mercado, restaurantes, transporte, servicios, compras en línea, "
            "suscripciones, salud, educación, efectivo, otros), de mayor a menor.\n"
            "COBROS A REVISAR: cuota de manejo, seguros que pudo no pedir, intereses y su tasa, comisiones, avances, "
            "suscripciones (Netflix, Spotify, apps…), cobros repetidos el mismo día o por el mismo valor, compras en el exterior "
            "y movimientos que parezcan raros. Cita fecha, comercio y valor.\n"
            "CUÁNTO PUEDES AHORRAR AL MES: con acciones concretas (cancelar, pedir que quiten la cuota de manejo, pagar el total "
            "de la tarjeta para no pagar intereses).\n"
            "Si ves un cobro que el dueño quizá no reconoce, dile que llame a su banco por la línea oficial. Usa solo lo que está "
            "en el extracto; no inventes valores.")


# ============================================================================ DEUDAS
def monthly_rate(rate, kind="mensual"):
    """La tasa en % (mensual o efectiva anual) → tasa mensual en fracción."""
    r = float(rate) / 100.0
    return (1 + r) ** (1 / 12) - 1 if kind == "ea" else r


def simulate(debts, extra=0.0, strategy="avalancha", lump=0.0, max_months=600):
    """debts: [{"nombre", "saldo", "tasa" (mensual, fracción), "cuota"}]. Paga todas las cuotas y lo que sobra (extra y lo
    que liberan las ya pagadas) va a la deuda que toca según la estrategia. lump: abono único el primer mes (la prima).
    → {"meses", "intereses", "orden": [(nombre, mes en que queda paga)], "imposible": bool}."""
    ds = [dict(d, saldo=float(d["saldo"])) for d in debts if float(d["saldo"]) > 0]
    budget = sum(float(d["cuota"]) for d in ds) + float(extra)
    key = (lambda d: -d["tasa"]) if strategy == "avalancha" else (lambda d: d["saldo"])
    total_int, done, month = 0.0, [], 0
    while ds and month < max_months:
        month += 1
        for d in ds:
            i = d["saldo"] * d["tasa"]
            total_int += i
            d["saldo"] += i
        avail = budget + (lump if month == 1 else 0.0)
        for d in ds:                                   # cuotas mínimas
            pay = min(float(d["cuota"]), d["saldo"], avail)
            d["saldo"] -= pay
            avail -= pay
        for d in sorted(ds, key=key):                  # lo que sobra, a la que toca
            if avail <= 0:
                break
            pay = min(avail, d["saldo"])
            d["saldo"] -= pay
            avail -= pay
        for d in [d for d in ds if d["saldo"] <= 0.5]:
            done.append((d["nombre"], month))
            ds.remove(d)
        if month == 24 and ds and sum(d["saldo"] for d in ds) >= sum(float(x["saldo"]) for x in debts) * 1.05:
            return {"meses": None, "intereses": total_int, "orden": done, "imposible": True}
    return {"meses": month if not ds else None, "intereses": round(total_int), "orden": done, "imposible": bool(ds)}


# ============================================================================ «¿ESTO ES VERDAD?»
def factcheck_prompt():
    return ("Eres un verificador de datos colombiano, serio e imparcial. El usuario te muestra una cadena, noticia o afirmación "
            "y pregunta si es verdad. Usa los resultados de búsqueda que vienen abajo (y lo que sepas con seguridad). Responde en "
            "español, texto plano:\n"
            "1) Veredicto en la primera línea: FALSO, ENGAÑOSO, SIN PRUEBAS, CIERTO o NO SE PUDO VERIFICAR, y por qué en una frase.\n"
            "2) Qué dicen las fuentes, nombrándolas (medios serios, entidades oficiales, verificadores como ColombiaCheck, "
            "AFP Factual o La Silla Vacía).\n"
            "3) «Para el grupo:» un mensaje corto y respetuoso (2 o 3 frases) para responder en el chat de la familia.\n"
            "Si los resultados no alcanzan para decidir, di NO SE PUDO VERIFICAR; no adivines. En temas políticos, sé neutral: "
            "verifica el dato, no opines sobre personas o partidos.")


# ============================================================================ EXÁMENES DE LABORATORIO
def lab_prompt():
    return ("Estos son resultados de exámenes de laboratorio de una persona en Colombia. Explícaselos a ella, en español sencillo "
            "y texto plano:\n"
            "1) Para cada valor: qué mide (en una frase), su resultado y si está dentro del rango de referencia QUE TRAE EL "
            "MISMO INFORME (no uses otros rangos).\n"
            "2) LO QUE ESTÁ FUERA DE RANGO: qué puede significar en general, sin diagnosticar.\n"
            "3) PREGUNTAS PARA TU MÉDICO: 3 a 5.\n"
            "No diagnostiques, no recomiendes medicamentos ni cambios de tratamiento. Si un valor está muy alterado, di con calma "
            "que conviene consultar pronto, y si hay señales de urgencia, que vaya a urgencias. Termina con: «Esto es una "
            "explicación general; quien interpreta tus exámenes es tu médico».")


# ============================================================================ PROFESOR DE INGLÉS
LEVELS = {"basico": "A1-A2 (básico)", "intermedio": "B1-B2 (intermedio)", "avanzado": "C1 (avanzado)"}


def tutor_rule(level="basico", topic=""):
    lv = LEVELS.get(level, LEVELS["basico"])
    return (f" MODO PROFESOR DE INGLÉS (nivel {lv}). Conversa en inglés con el usuario, de forma natural y amable, sobre "
            + (f"«{topic}»" if topic else "su día, sus gustos o lo que él quiera") + ". Habla despacio y con frases cortas si es "
            "nivel básico. Después de cada respuesta del usuario: si cometió un error, corrígelo con suavidad diciendo la forma "
            "correcta una vez («You can say: …») y sigue la conversación con una pregunta. Si el usuario habla en español o dice "
            "que no entiende, explícale en español en una frase y vuelve al inglés. No des clases largas; que hable él más que tú.")


def review_prompt(transcript):
    return ("Esta es una práctica de conversación en inglés entre un estudiante hispanohablante y su tutor:\n" + transcript[-12000:] +
            "\n\nEscribe en español un repaso corto para el estudiante: ERRORES (máximo 8: lo que dijo → la forma correcta → por qué, "
            "en una línea); PALABRAS Y FRASES NUEVAS (máximo 10, con traducción); PARA LA PRÓXIMA (2 consejos concretos). Texto plano.")
