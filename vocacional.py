"""12.54: orientación vocacional para once. Un test de intereses (seis tipos de intereses vocacionales, al estilo del
modelo RIASEC de Holland) que los estudiantes responden en el celular, su perfil, áreas de carreras afines y rutas para
seguir estudiando en Colombia. Es una orientación, no un diagnóstico. Funciones puras.
"""
import re

TYPES = {
    "R": ("Práctico", "le gusta trabajar con las manos, máquinas, herramientas, plantas o animales, y ver resultados concretos",
          "ingenierías mecánica, civil y agronómica; mecatrónica; electricidad; agropecuaria; tecnologías en mantenimiento y construcción; deportes"),
    "I": ("Investigador", "le gusta entender cómo funcionan las cosas, resolver problemas, experimentar y analizar datos",
          "medicina, biología, química, física, matemáticas, ingeniería de sistemas, ciencia de datos, ciencias ambientales"),
    "A": ("Artístico", "le gusta crear, imaginar, expresarse con imágenes, música, palabras o movimiento",
          "diseño gráfico e industrial, artes plásticas, música, arquitectura, comunicación audiovisual, literatura, danza, animación"),
    "S": ("Social", "le gusta ayudar, enseñar, cuidar, escuchar y trabajar con personas",
          "licenciaturas (docencia), psicología, enfermería, trabajo social, fisioterapia, fonoaudiología, pedagogía infantil"),
    "E": ("Emprendedor", "le gusta liderar, convencer, organizar proyectos, negociar y asumir retos",
          "administración, negocios internacionales, mercadeo, derecho, ciencia política, emprendimiento, gestión turística"),
    "C": ("Organizado", "le gusta el orden, los datos, los procesos claros, los números y que las cosas queden bien hechas",
          "contaduría, economía, finanzas, gestión documental, logística, estadística, tecnologías en gestión administrativa"),
}

QUESTIONS = [
    ("R", "Arreglar o armar aparatos, muebles o bicicletas"), ("R", "Trabajar al aire libre con plantas, animales o la tierra"),
    ("R", "Manejar herramientas o máquinas"), ("R", "Construir algo que se pueda tocar y usar"), ("R", "Hacer deporte o actividades físicas exigentes"),
    ("I", "Resolver problemas de matemáticas o lógica"), ("I", "Hacer experimentos y averiguar el porqué de las cosas"),
    ("I", "Leer sobre ciencia, el cuerpo humano o el universo"), ("I", "Analizar datos o información para sacar conclusiones"),
    ("I", "Programar o entender cómo funciona la tecnología"),
    ("A", "Dibujar, diseñar o tomar fotografías"), ("A", "Tocar un instrumento, cantar o componer"), ("A", "Escribir historias, poemas o guiones"),
    ("A", "Actuar, bailar o hacer videos creativos"), ("A", "Decorar o imaginar cómo se vería un lugar"),
    ("S", "Explicarle algo a un compañero hasta que lo entienda"), ("S", "Escuchar y aconsejar a amigos con problemas"),
    ("S", "Cuidar a niños, adultos mayores o personas enfermas"), ("S", "Participar en voluntariados o ayudar a la comunidad"),
    ("S", "Trabajar en equipo con muchas personas"),
    ("E", "Liderar un grupo o un proyecto"), ("E", "Convencer a otros de una idea"), ("E", "Vender algo o montar un negocio"),
    ("E", "Organizar eventos o actividades"), ("E", "Hablar en público o debatir"),
    ("C", "Organizar información en tablas o carpetas"), ("C", "Llevar cuentas, presupuestos o inventarios"),
    ("C", "Seguir instrucciones precisas y revisar que todo esté bien"), ("C", "Usar Excel u hojas de cálculo"),
    ("C", "Planear mi tiempo y cumplir los plazos"),
]
SCALE = 4          # 0 nada · 1 poco · 2 algo · 3 bastante · 4 mucho


def score(answers):
    """answers: [0..4] en el orden de QUESTIONS → {"R": 0..100, …}."""
    tot = {k: 0 for k in TYPES}
    cnt = {k: 0 for k in TYPES}
    for (k, _q), a in zip(QUESTIONS, answers):
        try:
            a = max(0, min(SCALE, int(a)))
        except (TypeError, ValueError):
            continue
        tot[k] += a
        cnt[k] += 1
    return {k: round(100 * tot[k] / (SCALE * cnt[k])) if cnt[k] else 0 for k in TYPES}


def top(profile, n=3):
    return [k for k, _v in sorted(profile.items(), key=lambda kv: (-kv[1], "RIASEC".index(kv[0])))][:n]


def code(profile):
    return "".join(top(profile, 3))


def describe(profile):
    t = top(profile, 3)
    first = TYPES[t[0]]
    return (f"Tu perfil es {first[0].lower()}: {first[1]}. También te va lo {TYPES[t[1]][0].lower()} y lo {TYPES[t[2]][0].lower()}. "
            f"Áreas para explorar: {first[2]}.")


def report_prompt(nombre, profile, extra=""):
    t = top(profile, 3)
    perfil = "; ".join(f"{TYPES[k][0]} {profile[k]} %" for k in t)
    return (
        f"Eres orientador vocacional de un colegio en Colombia. Un estudiante de grado once ({nombre}) hizo un test de intereses "
        f"(modelo RIASEC). Sus intereses más altos: {perfil}." + (f" Información adicional del docente: {extra[:600]}." if extra else "")
        + "\nEscribe una orientación cálida y realista en español para él: qué dicen sus intereses, 5 carreras o programas afines "
          "(mezcla profesionales, tecnológicos y técnicos), qué puede hacer este año para explorarlos (charlas, visitas, cursos "
          "cortos) y las rutas para estudiar en Colombia: universidades públicas, el SENA, instituciones técnicas y tecnológicas, y "
          "apoyos como becas y créditos. No inventes nombres de becas, fechas ni puntajes: di que los consulte en las páginas "
          "oficiales (SNIES para programas, Sofía Plus del SENA, ICETEX y la oficina de admisiones de cada universidad). Recuerda "
          "que es una orientación y que sus intereses pueden cambiar.\n"
          "Responde SOLO con JSON: {\"mensaje\": str, \"carreras\": [{\"nombre\": str, \"tipo\": str, \"por_que\": str}], "
          "\"este_anio\": [str], \"rutas\": [str]}")


def norm_name(t):
    import unicodedata
    t = unicodedata.normalize("NFD", str(t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def match_student(typed, names):
    """El nombre que escribió el estudiante → el de la lista del curso (o el escrito, si no hay lista)."""
    q = norm_name(typed)
    if not q:
        return ""
    if not names:
        return re.sub(r"\s+", " ", typed).strip()[:60]
    full = [n for n in names if norm_name(n) == q]
    if full:
        return full[0]
    parts = q.split()
    cands = [n for n in names if all(p in norm_name(n).split() for p in parts)]
    return cands[0] if len(cands) == 1 else ""
