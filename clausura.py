"""12.65: diplomas y menciones de honor, salidas pedagógicas, proyectos transversales y cronograma de evaluaciones.
Lógica pura, sin Jarvis.
"""
import datetime
import re
import unicodedata


def norm(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


# ============================================================================ DIPLOMAS
MOTIVOS = {
    "excelencia": "por su excelencia académica",
    "companero": "por ser el mejor compañero y su espíritu de servicio",
    "superacion": "por su esfuerzo y superación personal",
    "liderazgo": "por su liderazgo y compromiso",
    "convivencia": "por su aporte a la sana convivencia",
    "asistencia": "por su puntualidad y asistencia",
    "deporte": "por su desempeño deportivo",
    "arte": "por su talento artístico",
}


def motivo_of(text):
    t = norm(text)
    for k, rx in (("companero", r"companer|servicio"), ("superacion", r"superacion|esfuerzo|mejoro|progreso"),
                  ("liderazgo", r"liderazgo|lider"), ("convivencia", r"convivencia"), ("asistencia", r"asistencia|puntualidad"),
                  ("deporte", r"deport"), ("arte", r"arte|artistic|music|danza")):
        if re.search(rx, t):
            return MOTIVOS[k]
    m = re.search(r"\bpor (?:su |el |la )?(.{4,80})$", t)
    if m and not re.search(r"\bexcelencia|mejores? promedio|primer puesto", t):
        return "por " + m.group(1)
    return MOTIVOS["excelencia"]


def top_students(avgs, n=3, min_avg=4.0):
    """avgs: {estudiante: promedio}. → [(estudiante, promedio)] los n mejores con al menos min_avg (empates incluidos)."""
    rows = sorted(((e, a) for e, a in avgs.items() if a is not None and a >= min_avg), key=lambda x: (-x[1], x[0]))
    if len(rows) <= n:
        return rows
    cut = rows[n - 1][1]
    return [r for r in rows if r[1] >= cut]


PUESTOS = ("Primer puesto", "Segundo puesto", "Tercer puesto")


# ============================================================================ SALIDAS PEDAGÓGICAS
SALIDA_NORMA = ("Directiva Ministerial 55 del 18 de diciembre de 2014 del MEN (orientaciones para la planeación, desarrollo y "
                "evaluación de las salidas escolares)")
SALIDA_CHECK = (
    "Aprobación del rector y del consejo académico (con su acta)",
    "Aviso a la secretaría de educación con la anticipación que pida tu entidad territorial",
    "Autorización escrita y firmada de los padres o acudientes de cada estudiante",
    "Ficha médica de cada estudiante (alergias, medicamentos, EPS)",
    "Póliza de accidentes escolares vigente y la lista de clínicas que la atienden",
    "Transporte habilitado: tarjeta de operación, SOAT, revisión técnico-mecánica y póliza del vehículo",
    "Si hay operador turístico: Registro Nacional de Turismo y póliza de responsabilidad civil",
    "Acompañantes suficientes (docentes y padres) y lista de teléfonos de emergencia",
    "Botiquín, plan de emergencia y punto de encuentro",
    "Lista de asistencia al salir y al regresar",
)


def salida_prompt(lugar, curso, fecha, objetivo=""):
    return (f"Eres un docente colombiano. Planea una salida pedagógica a «{lugar}» con el curso {curso}" +
            (f" el {fecha}" if fecha else "") + (f", con este objetivo: {objetivo}" if objetivo else "") + ". "
            "Responde en español, texto plano, con estas secciones: OBJETIVO PEDAGÓGICO (relacionado con el área y los DBA); "
            "ANTES DE LA SALIDA (actividad de preparación en clase); DURANTE (itinerario por horas y una guía de observación "
            "de 5 preguntas para los estudiantes); DESPUÉS (actividad de cierre y cómo se evalúa, con criterios); "
            "RECOMENDACIONES DE SEGURIDAD (específicas del lugar). Sé concreto y realista.")


def autorizacion_text(colegio, lugar, curso, fecha, salida="", regreso="", costo="", docente=""):
    return (f"Yo, ______________________________, identificado(a) con C.C. ______________, padre, madre o acudiente del "
            f"estudiante ______________________________ del curso {curso}, AUTORIZO su participación en la salida pedagógica a "
            f"{lugar}, organizada por {colegio or 'la institución educativa'}, el día {fecha or '__________'}"
            + (f", con salida a las {salida}" if salida else "") + (f" y regreso aproximado a las {regreso}" if regreso else "") + ". "
            + (f"Costo por estudiante: {costo}. " if costo else "")
            + "Declaro que conozco el objetivo, el itinerario y las condiciones de la salida, que la información médica que "
            "entrego es verídica y que mi hijo(a) cumplirá las normas del Manual de Convivencia durante la actividad."
            + (f" Docente responsable: {docente}." if docente else ""))


# ============================================================================ PROYECTOS TRANSVERSALES
PROYECTOS = {
    "ambiental": ("Proyecto Ambiental Escolar (PRAE)", "Ley 115 de 1994, art. 14, literal c; Decreto 1743 de 1994"),
    "sexualidad": ("Educación para la sexualidad y construcción de ciudadanía", "Ley 115 de 1994, art. 14, literal e; Ley 1620 de 2013"),
    "democracia": ("Educación para la justicia, la paz, la democracia y los valores humanos", "Ley 115 de 1994, art. 14, literal d"),
    "tiempo libre": ("Aprovechamiento del tiempo libre, recreación y deporte", "Ley 115 de 1994, art. 14, literal b"),
    "paz": ("Cátedra de la Paz", "Ley 1732 de 2014"),
    "movilidad": ("Educación en seguridad vial y movilidad segura", "Ley 1503 de 2011"),
    "vida saludable": ("Estilos de vida saludable", "Ley 1355 de 2009"),
}


def proyecto_of(text):
    t = norm(text)
    for k, rx in (("ambiental", r"ambient|prae|ecolog|reciclaj"), ("sexualidad", r"sexual|pescc|afectiv"),
                  ("democracia", r"democra|gobierno escolar|personer|valores"), ("tiempo libre", r"tiempo libre|recreaci|deport"),
                  ("paz", r"\bpaz\b|catedra de la paz"), ("movilidad", r"vial|movilidad|transito"),
                  ("vida saludable", r"saludable|nutrici|alimentaci")):
        if re.search(rx, t):
            return k
    return ""


def proyecto_prompt(key, colegio="", contexto=""):
    name, norma = PROYECTOS[key]
    return (f"Eres un docente colombiano experto en proyectos pedagógicos transversales. Formula el proyecto «{name}» "
            f"({norma}) para {colegio or 'una institución educativa'}" + (f". Contexto: {contexto}" if contexto else "") + ". "
            "Responde en español, texto plano, con estas secciones en este orden: TÍTULO; JUSTIFICACIÓN; MARCO LEGAL; "
            "DIAGNÓSTICO (qué averiguar y cómo, con una encuesta corta); OBJETIVO GENERAL; OBJETIVOS ESPECÍFICOS (3 a 5); "
            "POBLACIÓN; METODOLOGÍA; CRONOGRAMA (una actividad por mes de febrero a noviembre, con responsable y grados); "
            "RECURSOS; INDICADORES DE EVALUACIÓN (medibles); EVIDENCIAS (qué guardar de cada actividad). Concreto y realizable.")


def informe_prompt(key, evidencias):
    name, _ = PROYECTOS[key]
    lst = "\n".join(f"- {e['fecha']}: {e['texto']}" for e in evidencias[-60:])
    return (f"Escribe el informe final de gestión del proyecto «{name}» con estas evidencias registradas durante el año:\n{lst}\n"
            "Secciones: RESUMEN; ACTIVIDADES REALIZADAS (por fecha); LOGROS; DIFICULTADES; RECOMENDACIONES PARA EL PRÓXIMO AÑO. "
            "Usa solo lo que está en las evidencias; si falta información, dilo. Español, texto plano.")


# ============================================================================ CRONOGRAMA DE EVALUACIONES
DAYS = ("lunes", "martes", "miercoles", "jueves", "viernes")


def schedule(slots, start, weeks=2, per_day_max=2, holidays=()):
    """slots: [(curso, asignatura, día 0-4)] (cuándo ves cada curso). Reparte UNA evaluación por curso y asignatura en las
    clases de esas semanas: ningún curso con dos el mismo día y tú con a lo sumo per_day_max por día (para calificar).
    → [{"fecha", "curso", "asignatura"}] y [(curso, asignatura)] los que no cupieron."""
    start = start - datetime.timedelta(days=start.weekday())
    dates = [start + datetime.timedelta(days=w * 7 + d) for w in range(weeks) for d in range(5)]
    dates = [d for d in dates if d not in set(holidays)]
    by_pair = {}
    for c, a, d in slots:
        by_pair.setdefault((c, a), set()).add(d)
    out, missing = [], []
    load, course_days = {}, set()
    for (c, a), days in sorted(by_pair.items(), key=lambda kv: (len(kv[1]), kv[0])):     # los que ves menos, primero
        placed = False
        for dt in sorted((x for x in dates if x.weekday() in days), key=lambda x: (load.get(x, 0), x)):
            if load.get(dt, 0) >= per_day_max or (c, dt) in course_days:
                continue
            out.append({"fecha": dt, "curso": c, "asignatura": a})
            load[dt] = load.get(dt, 0) + 1
            course_days.add((c, dt))
            placed = True
            break
        if not placed:
            missing.append((c, a))
    return sorted(out, key=lambda x: (x["fecha"], x["curso"])), missing
