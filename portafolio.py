"""12.53: portafolio de evidencias del docente. Junta lo que Jarvis te ayudó a hacer en el año (planeaciones, guías,
evaluaciones, informes, actas, videos…) y lo organiza por las competencias de la evaluación de desempeño (Decreto 1278 de
2002, Guía 31 del MEN): académica, administrativa y comunitaria. Funciones puras: clasificar, filtrar por fechas y el
índice. Verifica siempre con el protocolo de evaluación vigente de tu entidad territorial.
"""
import datetime
import os
import re

EXTS = (".docx", ".pdf", ".pptx", ".xlsx", ".mp4", ".png", ".html", ".mp3")
SKIP = re.compile(r"respaldo|backup|copia de seguridad|\.part$|~\$", re.I)
AREAS = [
    ("Académica · Planeación y organización", r"plan|planeaci|malla|secuencia|unidad|clase de|diario de clase|horario"),
    ("Académica · Pedagógica y didáctica", r"gu[ií]a|taller|material|presentaci|video|pel[ií]cula|cine|infograf|podcast|herramienta|juego|lectura|"
                                           r"refuerzo|nivelaci|piar|ajuste"),
    ("Académica · Evaluación del aprendizaje", r"quiz|evaluaci|examen|prueba|r[uú]brica|icfes|saber|calificaci|notas|retroalimentaci|escritura|"
                                              r"versiones|hoja de respuestas|resultados"),
    ("Administrativa · Seguimiento de procesos", r"bolet[ií]n|informe|consolidado|zeti|planilla|asistencia|acta|resumen|recuperaci|"
                                                r"plan de mejoramiento|riesgo"),
    ("Comunitaria · Familias y convivencia", r"acudiente|padres|famil|convivencia|citaci|situaci[oó]n|registro de situ|carta|circular|"
                                            r"reuni[oó]n|comit[eé]"),
]
OTHER = "Otras evidencias"


def area_of(path):
    s = os.path.basename(os.path.dirname(path)) + " " + os.path.basename(path)
    s = s.lower()
    for name, rx in AREAS:
        if re.search(rx, s):
            return name
    return OTHER


def collect(root, since, until=None, limit=400):
    """[(ruta, fecha, área)] de los archivos de Jarvis entre esas fechas (los más recientes primero)."""
    until = until or datetime.date.today()
    out = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not SKIP.search(d) and not d.startswith(".")]
        for fn in fns:
            if not fn.lower().endswith(EXTS) or SKIP.search(fn):
                continue
            p = os.path.join(dp, fn)
            try:
                d = datetime.date.fromtimestamp(os.path.getmtime(p))
            except OSError:
                continue
            if since <= d <= until:
                out.append((p, d, area_of(p)))
    out.sort(key=lambda x: x[1], reverse=True)
    return out[:limit]


def by_area(items):
    groups = {name: [] for name, _ in AREAS}
    groups[OTHER] = []
    for it in items:
        groups[it[2]].append(it)
    return {k: v for k, v in groups.items() if v}


def reflection_prompt(groups, docente="", year=None):
    lines = []
    for area, items in groups.items():
        names = "; ".join(os.path.splitext(os.path.basename(p))[0][:70] for p, _d, _a in items[:15])
        lines.append(f"- {area} ({len(items)} evidencias): {names}")
    return ("Eres un docente colombiano preparando su portafolio de evidencias para la evaluación anual de desempeño "
            f"(Decreto 1278){' de ' + str(year) if year else ''}. Estas son tus evidencias agrupadas por competencia:\n"
            + "\n".join(lines) + "\nPara cada competencia escribe una reflexión pedagógica en primera persona de 3 a 4 frases: "
            "qué hiciste, por qué y qué impacto buscaste en los estudiantes. No inventes resultados ni cifras. "
            "Responde SOLO con JSON: {\"reflexiones\": {\"<competencia>\": str}, \"presentacion\": str}")


def year_start(today=None):
    today = today or datetime.date.today()
    return datetime.date(today.year, 1, 1)
