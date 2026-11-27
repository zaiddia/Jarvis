"""12.69: simulaciones PhET (Universidad de Colorado) en el video beam, en español. Lógica pura.

Gratuitas y de código abierto; las HTML5 son un solo archivo que Jarvis guarda la primera vez para usarlas sin internet.
Dirección: https://phet.colorado.edu/sims/html/<sim>/latest/<sim>_es.html
"""
import re
import unicodedata

BASE = "https://phet.colorado.edu/sims/html/{s}/latest/{s}_{lang}.html"
PAGE = "https://phet.colorado.edu/es/simulations/{s}"

# sim → (nombre en español, área, palabras con que se pide)
SIMS = {
    "fractions-intro": ("Fracciones: introducción", "matemáticas", r"fracciones?(?! equivalentes| mixt)|fraccionarios?"),
    "fractions-equality": ("Fracciones equivalentes", "matemáticas", r"fracciones equivalentes|equivalencia de fracciones"),
    "fractions-mixed-numbers": ("Números mixtos", "matemáticas", r"numeros mixtos|fracciones mixtas"),
    "build-a-fraction": ("Construye una fracción", "matemáticas", r"construye una fraccion|construir fracciones"),
    "area-model-multiplication": ("Modelo de área: multiplicación", "matemáticas", r"modelo de area|multiplicacion con areas?"),
    "area-model-algebra": ("Modelo de área: álgebra", "matemáticas", r"productos notables|multiplicar polinomios|algebra con areas?"),
    "arithmetic": ("Aritmética", "matemáticas", r"aritmetica|tablas de multiplicar"),
    "function-builder": ("Constructor de funciones", "matemáticas", r"constructor de funciones|maquina de funciones"),
    "graphing-lines": ("Graficando líneas", "matemáticas", r"graficando lineas|pendiente de la recta|ecuacion de la recta"),
    "graphing-slope-intercept": ("Pendiente e intercepto", "matemáticas", r"pendiente e? intercepto|pendiente y corte"),
    "graphing-quadratics": ("Graficando cuadráticas", "matemáticas", r"cuadraticas?|parabolas? de phet"),
    "equality-explorer": ("Explorador de igualdades", "matemáticas", r"igualdades?|ecuaciones con balanza|balanza de ecuaciones|despejar"),
    "expression-exchange": ("Intercambio de expresiones", "matemáticas", r"expresiones algebraicas|terminos semejantes"),
    "unit-rates": ("Tasas unitarias", "matemáticas", r"tasas? unitarias?|precio por unidad"),
    "ratio-and-proportion": ("Razones y proporciones", "matemáticas", r"razones? y proporciones?|proporcionalidad"),
    "number-line-integers": ("Recta numérica: enteros", "matemáticas", r"recta numerica|numeros enteros|negativos"),
    "make-a-ten": ("Hacer diez", "matemáticas", r"hacer diez|sumar con decenas"),
    "plinko-probability": ("Probabilidad de Plinko", "matemáticas", r"plinko|distribucion binomial|campana de gauss"),
    "center-and-variability": ("Centro y variabilidad", "matemáticas", r"media mediana|mediana|variabilidad|medidas de tendencia"),
    "mean-share-and-balance": ("Media: repartir y equilibrar", "matemáticas", r"\bpromedio\b|\bla media\b"),
    "trig-tour": ("Tour trigonométrico", "matemáticas", r"trigonometri|seno y coseno|circulo unitario de phet"),
    "curve-fitting": ("Ajuste de curvas", "matemáticas", r"ajuste de curvas?|regresion"),
    "vector-addition": ("Suma de vectores", "matemáticas", r"vectores?"),
    "calculus-grapher": ("Graficador de cálculo", "matemáticas", r"derivadas?|integral(?:es)?|calculo"),
    "quadrilateral": ("Cuadriláteros", "matemáticas", r"cuadrilateros?"),
    "area-builder": ("Constructor de áreas", "matemáticas", r"constructor de areas?|areas? y perimetros? de phet"),
    "projectile-motion": ("Movimiento de proyectiles", "física", r"proyectil|tiro parabolico|lanzamiento"),
    "energy-skate-park-basics": ("Pista de patinaje: energía", "física", r"patinaje|energia (?:cinetica|potencial|mecanica)"),
    "forces-and-motion-basics": ("Fuerzas y movimiento", "física", r"fuerzas? y movimiento|fuerzas?|leyes de newton"),
    "friction": ("Fricción", "física", r"friccion|rozamiento"),
    "gravity-and-orbits": ("Gravedad y órbitas", "física", r"gravedad|orbitas?"),
    "my-solar-system": ("Mi sistema solar", "física", r"sistema solar de phet|mi sistema solar"),
    "keplers-laws": ("Leyes de Kepler", "física", r"kepler"),
    "wave-on-a-string": ("Onda en una cuerda", "física", r"ondas? en una cuerda|ondas?"),
    "circuit-construction-kit-dc": ("Kit de construcción de circuitos", "física", r"circuitos?|bombillo|corriente electrica"),
    "ohms-law": ("Ley de Ohm", "física", r"ley de ohm|\bohm\b"),
    "balancing-act": ("Ley del equilibrio", "física", r"equilibrio|palanca|balancin"),
    "pendulum-lab": ("Laboratorio de péndulo", "física", r"pendulo"),
    "hookes-law": ("Ley de Hooke", "física", r"hooke|resortes?"),
    "faradays-law": ("Ley de Faraday", "física", r"faraday|induccion"),
    "coulombs-law": ("Ley de Coulomb", "física", r"coulomb|cargas electricas"),
    "geometric-optics": ("Óptica geométrica", "física", r"optica|lentes?|espejos?"),
    "bending-light": ("Refracción de la luz", "física", r"refraccion|doblar la luz"),
    "color-vision": ("Visión del color", "física", r"vision del color|colores de la luz"),
    "energy-forms-and-changes": ("Formas y cambios de energía", "física", r"formas de energia|transformacion de la energia|cambios de energia"),
    "density": ("Densidad", "física", r"densidad"),
    "buoyancy": ("Flotabilidad", "física", r"flotabilidad|flotacion|arquimedes|empuje"),
    "balloons-and-static-electricity": ("Globos y electricidad estática", "física", r"electricidad estatica|globos"),
    "states-of-matter-basics": ("Estados de la materia", "química", r"estados de la materia|solido liquido|cambios de estado"),
    "gas-properties": ("Propiedades de los gases", "química", r"gases|presion y temperatura"),
    "build-an-atom": ("Construye un átomo", "química", r"atomos?|protones|electrones"),
    "isotopes-and-atomic-mass": ("Isótopos y masa atómica", "química", r"isotopos?|masa atomica"),
    "molecule-shapes": ("Geometría molecular", "química", r"geometria molecular|forma de las moleculas"),
    "build-a-molecule": ("Construye una molécula", "química", r"moleculas?"),
    "ph-scale": ("Escala de pH", "química", r"\bph\b|acidos? y bases?"),
    "concentration": ("Concentración", "química", r"concentracion"),
    "molarity": ("Molaridad", "química", r"molaridad"),
    "balancing-chemical-equations": ("Balanceo de ecuaciones químicas", "química", r"balanceo|ecuaciones quimicas"),
    "reactants-products-and-leftovers": ("Reactivos, productos y sobrantes", "química", r"reactivos?|reactivo limite"),
    "natural-selection": ("Selección natural", "biología", r"seleccion natural|evolucion"),
    "gene-expression-essentials": ("Expresión génica", "biología", r"expresion genica|genes?|adn"),
    "neuron": ("Neurona", "biología", r"neuronas?|impulso nervioso"),
    "greenhouse-effect": ("Efecto invernadero", "ciencias de la tierra", r"efecto invernadero|calentamiento global|cambio climatico"),
}


def norm(t):
    t = "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def find(spoken):
    """«la simulación de fracciones» → «fractions-intro» (o "" si no hay)."""
    q = norm(spoken)
    if q in SIMS:
        return q
    for slug, (name, _area, rx) in SIMS.items():
        if norm(name) == q:
            return slug
    for slug, (_name, _area, rx) in SIMS.items():
        if re.search(rf"\b(?:{rx})", q):
            return slug
    return ""


def url(slug, lang="es"):
    return BASE.format(s=slug, lang=lang)


def by_area(area=""):
    a = norm(area)
    return [(s, v[0]) for s, v in SIMS.items() if not a or norm(v[1]).startswith(a[:5])]


__all__ = ["BASE", "PAGE", "SIMS", "norm", "find", "url", "by_area"]
