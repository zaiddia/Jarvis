"""Guía de lo que Jarvis sabe hacer (12.16): grupos con ejemplos, búsqueda y «¿qué puedes hacer con …?». Lógica pura."""
import re
import unicodedata

CATEGORIES = [
    ("colegio", "Colegio y clases", "🎓"), ("material", "Material y documentos", "📄"), ("pc", "El PC y las ventanas", "🖥"),
    ("dia", "Mi día", "📅"), ("dinero", "Dinero", "💰"), ("info", "Información y web", "🌐"), ("comunica", "Mensajes y celular", "💬"),
    ("casa", "Casa y música", "🏠"), ("jarvis", "Jarvis mismo", "⚙"),
]
# Palabras del nombre del grupo → categoría (el primero que coincide)
_RULES = [
    ("dinero", r"gasto|pago|dolar|cripto|presupuesto|suscrip|recibo|cuentas"),
    ("dia", r"vencim|medicam|cita|cumple|menu|viaje|mi dia|recordatorio|temporizador|rutina|lista|personal|calendario|diario|concentraci"),
    ("material", r"documento|material|boletin|presentacion|excel|generador|audio|word"),
    ("colegio", r"aula|clase|salon|recuperac|escolar|revisar trabajo|tablero|matemat|dictado|codigo"),
    ("pc", r"pc|ventana|pesta|program|mantenim|energia|navegador|pantalla|aplicacion|leer en voz|vision|medico"),
    ("info", r"web|busca|clima|noticia|sismo|internet|instante"),
    ("comunica", r"mensaj|telegram|celular|correo|whatsapp|famil"),
    ("casa", r"casa|musica|spotify|audio y musica|radio"),
]
EXTRA = [
    ("Cuentas y calendario al instante (12.21)", ["¿cuánto es el IVA de 250.000?", "80.000 con el 20% de descuento", "divide una cuenta de 180.000 entre 4 con propina",
                                                  "cuota de un préstamo de 10 millones a 24 meses al 1,8% mensual", "interés compuesto de 2 millones al 10% anual por 3 años",
                                                  "regla de tres: si 5 cuadernos cuestan 20.000, ¿cuánto cuestan 8?", "¿cuántos días hábiles faltan para el 15 de diciembre?",
                                                  "festivos de diciembre"]),
    ("Bienestar y casa (12.21)", ["hazme una pausa activa", "respiración de 2 minutos", "termina la pausa", "modo cocina arroz con pollo", "siguiente paso",
                                  "los ingredientes", "cuéntame un cuento de dragones para un niño de 6 años"]),
    ("Radio, QR e inglés (12.21)", ["pon la emisora Caracol", "pon una emisora de salsa", "apaga la radio", "crea un QR de https://mi-pagina.com",
                                    "crea un QR del wifi Casa con clave 12345678", "palabra del día en inglés", "quiz de inglés", "practiquemos inglés"]),
    ("Al instante, sin IA (12.20)", ["¿qué hora es en Tokio?", "¿cuántos días faltan para Navidad?", "¿qué día cae el 20 de diciembre?",
                                     "convierte 5 millas a kilómetros", "¿cuánto son 80 grados Fahrenheit en Celsius?", "tira un dado",
                                     "dime un número al azar entre 1 y 50", "escoge entre pizza, sushi o tacos", "deletrea murciélago",
                                     "cuéntame un chiste", "dime un dato curioso", "dame una frase motivadora", "genera una contraseña segura"]),
    ("Internet y videos (12.20)", ["mide la velocidad de internet", "¿cuál es mi IP?", "resume este video https://youtu.be/…",
                                   "¿cómo se dice buenos días en inglés?", "traduce al francés: ¿dónde queda la estación?"]),
    ("Generador de documentos (12.14)", ["abre el generador de documentos", "hazme un acta en PDF de la reunión de padres",
                                         "redacta una circular en Word sobre la salida pedagógica"]),
    ("Mis aplicaciones (12.14)", ["abre mis aplicaciones", "(di la frase de cualquier tarjeta, por ejemplo «abre el campus»)",
                                  "abre música en Chrome"]),
    ("Vencimientos (12.15)", ["el SOAT se vence el 15 de marzo", "¿qué se me vence este mes?", "ya renové el SOAT", "¿cuándo declaro renta?"]),
    ("Recibos (12.15)", ["(sube la foto con el clip y pulsa «Registrar recibo»)", "registra el recibo", "exporta mis gastos del mes a Excel"]),
    ("Medicamentos (12.15)", ["recuérdame tomar losartán a las 8 de la mañana y a las 8 de la noche", "ya me la tomé",
                              "¿qué medicamentos tengo?", "compré 30 pastillas de losartán"]),
    ("Citas médicas (12.15)", ["tengo cita con el odontólogo el 20 a las 3 de la tarde", "¿qué citas tengo?"]),
    ("Cumpleaños (12.15)", ["el cumpleaños de mi mamá es el 3 de mayo", "¿qué cumpleaños vienen?", "escríbele un mensaje de cumpleaños a mi mamá",
                            "ideas de regalo para Ana de 100 mil", "importa los cumpleaños de mis contactos"]),
    ("Presupuesto (12.15)", ["mi presupuesto de comida es de 800 mil", "¿cómo voy con el presupuesto?", "¿qué suscripciones tengo?",
                             "resumen del mes"]),
    ("Menú y mercado (12.15)", ["arma el menú de la semana para 3 personas", "¿qué cocino con arroz, pollo y tomate?"]),
    ("Documentos en audio (12.15)", ["convierte este PDF en audio", "(o pega el enlace: «convierte en audio https://…»)"]),
    ("Médico del PC (12.15)", ["revisa mi PC", "abre el médico del PC", "¿cómo está la batería?"]),
    ("Viajes (12.15)", ["me voy a Cartagena del 20 al 24 de noviembre", "mi vuelo sale a las 6 de la mañana", "mis viajes"]),
    ("Mi día (12.15)", ["abre mi día"]),
    ("Compartir con la familia (12.16)", ["mándale la lista del mercado a mi esposa", "compártele el menú a mi mamá",
                                          "avísale a mi hermana del cumpleaños de mamá"]),
    ("No molestar (12.16)", ["no me molestes por una hora", "modo no molestar", "ya puedes hablar", "¿qué me perdí?"]),
    ("Guía y autoprueba (12.16)", ["abre la guía", "¿qué puedes hacer con el presupuesto?", "haz la autoprueba"]),
]


def norm(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def category_of(name):
    n = norm(name)
    for cat, rx in _RULES:
        if re.search(rf"\b(?:{rx})", n):
            return cat
    return "jarvis"


def build(capabilities):
    """[{"id", "nombre", "icono", "grupos": [{"nombre", "ejemplos": [{"t", "probar"}]}]}] sin grupos repetidos."""
    seen, by = set(), {c[0]: [] for c in CATEGORIES}
    for name, examples in list(capabilities) + EXTRA:
        key = norm(re.sub(r"\(\d+\.\d+(?:\.\d+)?\)", "", name))
        if key in seen:
            continue
        seen.add(key)
        exs = [{"t": e, "probar": not e.startswith("(") and not re.search(r"«|…", e[:1])} for e in examples]
        by[category_of(name)].append({"nombre": name, "ejemplos": exs})
    return [{"id": c, "nombre": n, "icono": i, "grupos": by[c]} for c, n, i in CATEGORIES if by[c]]


def search(guide, query, limit=3):
    """Los grupos que mejor coinciden con la pregunta. → [(categoría, grupo)]."""
    words = [w for w in norm(query).split() if len(w) > 2 and w not in ("que", "con", "los", "las", "del", "para", "como", "puedes", "hacer", "sabes")]
    if not words:
        return []
    scored = []
    for cat in guide:
        for g in cat["grupos"]:
            hay = norm(g["nombre"] + " " + " ".join(e["t"] for e in g["ejemplos"]))
            s = sum(3 if re.search(rf"\b{re.escape(w)}", norm(g["nombre"])) else 1 for w in words if re.search(rf"\b{re.escape(w[:max(4, len(w) - 2)])}", hay))
            if s:
                scored.append((s, cat["nombre"], g))
    scored.sort(key=lambda x: -x[0])
    return [(c, g) for _, c, g in scored[:limit]]


def spoken(hits):
    if not hits:
        return ""
    parts = []
    for _cat, g in hits[:2]:
        exs = [e["t"] for e in g["ejemplos"] if e["probar"]][:3]
        name = re.sub(r"\s*\(\d+\.\d+(?:\.\d+)?\)", "", g["nombre"])
        parts.append(f"{name}: " + ", ".join(f"«{e}»" for e in exs))
    return "Con eso puedo ayudarte así. " + ". ".join(parts) + ". Todo está en la guía: di «abre la guía»."


def count(guide):
    return sum(len(g["ejemplos"]) for c in guide for g in c["grupos"])
