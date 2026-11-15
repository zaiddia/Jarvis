"""12.36: la base de datos de las habilidades del MODO DOCENTE (lógica pura, sin dependencias).

Cada habilidad: id, nombre, categoría, qué hace, frases que funcionan (probadas: tests/test_1236.py comprueba que cada
una la atiende su módulo), qué produce, qué necesita, el manejador (la función que la atiende) y desde qué versión.
Sirve para tres cosas:
  1. Separar los roles: los manejadores de esta lista solo atienden en modo docente o si la frase habla del colegio
     («7A», «mis estudiantes», «la clase»…). En modo general no se meten.
  2. Mostrarla: «¿qué puedo hacer en modo docente?», la página /docente (con buscador) y «exporta el catálogo docente».
  3. La comprensión de lenguaje natural la usa como ejemplos cuando estás en modo docente.
"""
import re
import unicodedata

CATEGORIAS = [
    ("planeacion", "Planeación", "Planear el año, el periodo, la semana y cada clase."),
    ("material", "Material de clase", "Quices, talleres, guías, rúbricas, lecturas, presentaciones y videos."),
    ("aula", "En el salón", "Lista, grupos, sorteos, tablero, proyector y clase en vivo."),
    ("evaluacion", "Evaluación y notas", "Calificar con foto o en pantalla, Forms, notas por asignatura, recuperaciones."),
    ("estudiantes", "Estudiantes y familias", "Ficha, alertas tempranas, observador, informes y boletines."),
    ("saber", "Pruebas Saber (ICFES)", "Preguntas tipo Saber, simulacros, perfil y plan de cada estudiante."),
    ("practica", "Práctica y tutoría", "Tutor en el celular, ruta de dominio, tarjetas, guías vivas y retos."),
    ("plataformas", "Classroom y plataformas", "Google Classroom, Forms y entregas."),
    ("gestion", "Gestión docente", "Calendario escolar, reuniones de área, kit para colegas, cierre de periodo."),
    ("inclusion", "Inclusión", "Ajustes razonables (PIAR) y lectura en niveles."),
]

H = [
    # ------------------------------------------------------------------ planeación
    dict(id="semana", cat="planeacion", nombre="La semana lista", handler="week_voice", v="9.8",
         que="Arma la semana de clases según tu horario: plan, material y lo pendiente de cada curso.",
         frases=["prepárame la semana"], produce="Word por curso + resumen", necesita="Tu horario de clases"),
    dict(id="planeacion_anual", cat="planeacion", nombre="Planeación del año", handler="planning_voice", v="10.8",
         que="Planeación anual por grado y asignatura alineada a los DBA; te dice si vas al día y se reajusta.",
         frases=["haz la planeación del año de matemáticas de séptimo", "¿voy al día con la planeación de 7A?"],
         produce="Word / Excel", necesita="IA conectada"),
    dict(id="plan_clase", cat="planeacion", nombre="Plan de clase", handler="aula_voice", v="7.0",
         que="Plan de clase con objetivo, momentos, actividades y evaluación.",
         frases=["haz un plan de clase sobre fracciones equivalentes para séptimo"], produce="Word", necesita="IA conectada"),
    dict(id="malla", cat="planeacion", nombre="Malla curricular del periodo", handler="aula_voice", v="8.2",
         que="Semanas del periodo con tema, DBA, desempeño, actividades y evaluación.",
         frases=["haz la malla curricular de matemáticas de octavo"], produce="Word", necesita="IA conectada"),
    dict(id="diario", cat="planeacion", nombre="Diario de clase", handler="class_diary_voice", v="8.8",
         que="Anota lo que viste en cada clase y te dice qué temas faltan del periodo.",
         frases=["en 7A vimos fracciones equivalentes", "¿qué temas me faltan de 7A?"], produce="Registro por curso",
         necesita="Tus cursos"),
    dict(id="ensayo", cat="planeacion", nombre="Ensayo de clase", handler="rehearsal_voice", v="12.0",
         que="Ensayas la clase con estudiantes simulados que se equivocan como los tuyos; al final, informe.",
         frases=["ensaya la clase de factorización con 9A"], produce="Informe en Word", necesita="IA conectada"),
    # ------------------------------------------------------------------ material
    dict(id="quiz", cat="material", nombre="Evaluación / quiz", handler="aula_voice", v="7.0",
         que="Evaluación de opción múltiple con clave y explicación.",
         frases=["crea un quiz de 10 preguntas sobre fracciones para séptimo"], produce="Word con clave", necesita="IA conectada"),
    dict(id="taller", cat="material", nombre="Taller o guía", handler="aula_voice", v="7.0",
         que="Taller con explicación, ejemplo resuelto y ejercicios graduados con solucionario.",
         frases=["hazme un taller sobre ecuaciones lineales para octavo"], produce="Word", necesita="IA conectada"),
    dict(id="rubrica", cat="material", nombre="Rúbrica", handler="aula_voice", v="7.0",
         que="Rúbrica con niveles Superior, Alto, Básico y Bajo.",
         frases=["haz una rúbrica para evaluar una exposición de noveno"], produce="Word", necesita="IA conectada"),
    dict(id="desde_enlace", cat="material", nombre="Material desde un enlace o texto", handler="link_material_voice", v="9.3",
         que="Quiz, taller o lectura nivelada a partir de un artículo o un texto que pegas.",
         frases=["haz un quiz con este artículo https://es.wikipedia.org/wiki/Fracción"], produce="Word", necesita="IA conectada"),
    dict(id="video_mate", cat="material", nombre="Video animado de matemáticas", handler="video_anim_voice", v="12.0",
         que="Video estilo 3Blue1Brown con voz y subtítulos, verificado con SymPy.",
         frases=["hazme un video de 2 minutos que explique el teorema de Pitágoras para noveno"], produce="MP4 + QR",
         necesita="IA conectada"),
    dict(id="juego_mate", cat="material", nombre="Juegos de matemáticas para imprimir", handler="game_voice", v="12.12",
         que="Bingo, dominó o lotería de matemáticas listos para imprimir.",
         frases=["haz un bingo de fracciones para 7A"], produce="PDF", necesita="—"),
    dict(id="solucionario", cat="material", nombre="Solucionario paso a paso", handler="solver_voice", v="11.3",
         que="Solución paso a paso verificada con SymPy del último material o de un ejercicio.",
         frases=["haz el solucionario del taller"], produce="Word", necesita="Un material reciente"),
    # ------------------------------------------------------------------ en el salón
    dict(id="curso", cat="aula", nombre="Curso activo", handler="aula_voice", v="7.0",
         que="Cambia el curso con el que trabajas (lista, notas, material).",
         frases=["usa el curso 7A"], produce="—", necesita="Tus listas de curso"),
    dict(id="asistencia", cat="aula", nombre="Llamar a lista", handler="aula_voice", v="7.0",
         que="Asistencia por voz: llamas a lista, marcas a quien falta y la guardas.",
         frases=["llama a lista", "guarda la asistencia"], produce="Excel en Asistencia", necesita="Lista del curso"),
    dict(id="asistencia_qr", cat="aula", nombre="Asistencia con QR", handler="salon_voice", v="12.12",
         que="QR que cambia cada 30 s; cada celular marca a un solo estudiante.",
         frases=["toma asistencia con QR de 9A"], produce="Asistencia en el Aula", necesita="Lista del curso"),
    dict(id="grupos", cat="aula", nombre="Grupos y parejas", handler="aula_voice", v="7.0",
         que="Arma grupos al azar con los presentes.", frases=["haz grupos de 4", "haz parejas"], produce="En el tablero",
         necesita="Lista del curso"),
    dict(id="sorteo", cat="aula", nombre="Sorteo de estudiantes", handler="aula_voice", v="7.0",
         que="Ruleta sin repetir hasta que pasen todos.", frases=["escoge un estudiante", "¿quién pasa?"],
         produce="En el tablero", necesita="Lista del curso"),
    dict(id="semaforo", cat="aula", nombre="Semáforo de ruido", handler="aula_voice", v="7.0",
         que="Semáforo que reacciona al ruido del salón.", frases=["activa el semáforo de ruido"], produce="En el tablero",
         necesita="Micrófono"),
    dict(id="tablero_aula", cat="aula", nombre="Tablero del aula", handler="aula_voice", v="7.0",
         que="El tablero para el videobeam: ruleta, grupos, asistencia y temporizador.", frases=["abre el tablero del aula"],
         produce="Ventana para proyectar", necesita="—"),
    dict(id="clase_vivo", cat="aula", nombre="Clase en vivo", handler="live_class_voice", v="9.6",
         que="Conduce la clase en el proyector con el plan: momentos, preguntas y cierre.",
         frases=["empieza la clase de fracciones con 7A"], produce="En el proyector", necesita="IA conectada"),
    dict(id="ticket", cat="aula", nombre="Ticket de salida", handler="ticket_voice", v="9.6",
         que="Pregunta de cierre que responden desde el celular; ves quién entendió.",
         frases=["haz el ticket de salida"], produce="Resultados en el HUD", necesita="Celulares de los estudiantes"),
    dict(id="quiz_vivo", cat="aula", nombre="Quiz en vivo en el proyector", handler="live_quiz_voice", v="8.8",
         que="El último quiz, pregunta por pregunta en el proyector.", frases=["proyecta el quiz en vivo"],
         produce="En el proyector", necesita="Un quiz reciente"),
    dict(id="modo_examen", cat="aula", nombre="Modo examen", handler="salon_voice", v="12.12",
         que="Bloquea práctica, retos y juegos en los celulares; el proyector muestra solo el reloj.",
         frases=["modo examen 45 minutos", "termina el examen"], produce="—", necesita="—"),
    dict(id="coevaluacion", cat="aula", nombre="Coevaluación", handler="salon_voice", v="12.12",
         que="Cada estudiante valora a su grupo con 4 criterios; el promedio queda como nota de «Ser».",
         frases=["abre la coevaluación de 9A", "cierra la coevaluación"], produce="Nota de Ser", necesita="Grupos armados"),
    dict(id="tutor_socratico", cat="aula", nombre="Modo tutor socrático", handler="tutor_voice", v="9.4",
         que="En clase, Jarvis guía con preguntas en vez de dar la respuesta.", frases=["activa el modo tutor"],
         produce="—", necesita="—"),
    # ------------------------------------------------------------------ evaluación y notas
    dict(id="revisar", cat="evaluacion", nombre="Revisar trabajos", handler="review_voice", v="7.0",
         que="Revisa un taller o examen mostrado a la cámara o en pantalla, con nota y comentarios.",
         frases=["revisa el taller de Juan", "califica este examen en la pantalla"], produce="Nota + retroalimentación",
         necesita="Cámara o pantalla"),
    dict(id="hojas", cat="evaluacion", nombre="Calificar con el celular", handler="sheets_voice", v="10.5",
         que="Hojas de respuesta impresas que se califican con una foto; notas y análisis de la evaluación.",
         frases=["haz las hojas de respuesta de 7A"], produce="PDF + notas", necesita="Un quiz y la lista"),
    dict(id="forms", cat="plataformas", nombre="Quiz en Google Forms", handler="forms_voice", v="8.1",
         que="Pasa el último quiz a Forms y trae las notas de vuelta.", frases=["pasa el quiz a Forms"],
         produce="Formulario de Google", necesita="Google conectado"),
    dict(id="asignaturas", cat="evaluacion", nombre="Asignaturas y notas por área", handler="subject_voice", v="10.4",
         que="Notas aparte por asignatura en el mismo grupo.", frases=["¿qué asignaturas tengo en 7A?"],
         produce="—", necesita="Tus asignaturas"),
    dict(id="recuperaciones", cat="evaluacion", nombre="Recuperaciones", handler="recovery_track_voice", v="12.12",
         que="Quién debe recuperar, planes con fecha límite y seguimiento de entregas y notas.",
         frases=["¿quiénes deben recuperar?", "¿cómo van las recuperaciones?"], produce="Planes en Word + seguimiento",
         necesita="Notas del periodo"),
    dict(id="copia", cat="evaluacion", nombre="Detector de copia", handler="copy_voice", v="12.12",
         que="Compara las entregas y señala las que se parecen demasiado.", frases=["¿hay copia en las entregas de 8A?"],
         produce="Informe", necesita="Entregas"),
    dict(id="dificultad", cat="evaluacion", nombre="Dificultad de las preguntas", handler="difficulty_voice", v="12.12",
         que="Qué tan difíciles resultaron las preguntas del banco según los resultados.",
         frases=["¿qué tan difíciles son mis preguntas de fracciones?"], produce="—", necesita="Exámenes calificados"),
    dict(id="banco", cat="evaluacion", nombre="Banco de preguntas", handler="bank_voice", v="7.8",
         que="Las preguntas de tus quices quedan guardadas para reusarlas.", frases=["¿cuántas preguntas tengo en el banco?"],
         produce="—", necesita="Quices hechos"),
    # ------------------------------------------------------------------ estudiantes y familias
    dict(id="ficha", cat="estudiantes", nombre="Ficha del estudiante", handler="card_voice", v="9.7",
         que="Todo de un estudiante en el HUD: notas, asistencia, observaciones y alertas.",
         frases=["ficha de Ana Gómez"], produce="En el HUD", necesita="Lista del curso"),
    dict(id="alertas", cat="estudiantes", nombre="Alertas tempranas", handler="early_voice", v="9.7",
         que="Quién va en riesgo antes de que pierda: notas bajando, faltas, entregas.",
         frases=["alertas tempranas", "¿quién viene bajando?"], produce="—", necesita="Notas y asistencia"),
    dict(id="observador", cat="estudiantes", nombre="Observador e informes para padres", handler="family_voice", v="8.2",
         que="Anotaciones del observador e informe para la familia (uno o todo el curso).",
         frases=["anota en el observador de Juan que no trajo el taller", "haz el informe para los padres de Ana Gómez"],
         produce="Word", necesita="Lista del curso"),
    dict(id="boletines", cat="estudiantes", nombre="Boletines del periodo", handler="boletin_voice", v="12.8",
         que="Un PDF por estudiante con todas tus asignaturas y los mensajes de WhatsApp listos (nada se envía solo).",
         frases=["haz los boletines de 7A"], produce="PDF por estudiante", necesita="Notas del periodo"),
    dict(id="seguimiento", cat="estudiantes", nombre="Seguimiento por estudiante", handler="student_voice", v="7.8",
         que="Cómo va un estudiante en tareas y notas.", frases=["¿cómo va Ana Gómez?"], produce="—", necesita="Notas"),
    # ------------------------------------------------------------------ Saber
    dict(id="saber_preguntas", cat="saber", nombre="Preguntas tipo Saber", handler="aula_voice", v="8.2",
         que="Preguntas con contexto y competencia, estilo ICFES (sin copiar preguntas reales).",
         frases=["haz 8 preguntas tipo saber de matemáticas para once"], produce="Word", necesita="IA conectada"),
    dict(id="simulacro", cat="saber", nombre="Simulacros Saber 11 y 9", handler="saber_voice", v="10.6",
         que="Simulacros por competencia con hoja de respuestas, perfil y plan de estudio por estudiante.",
         frases=["haz un simulacro saber 11 de matemáticas para 11A"], produce="PDF + informe", necesita="Lista del curso"),
    # ------------------------------------------------------------------ práctica y tutoría
    dict(id="tutor", cat="practica", nombre="Tutor en el celular", handler="practice_voice", v="10.7",
         que="Práctica a la medida desde un QR, con pistas que no dan la respuesta y niveles que se ajustan.",
         frases=["abre la práctica de fracciones para 7A"], produce="QR para los estudiantes", necesita="Lista del curso"),
    dict(id="dominio", cat="practica", nombre="Ruta de dominio y tarjetas", handler="mastery_voice", v="11.2",
         que="No avanza de tema hasta dominar; tarjetas con repaso espaciado exportables a Anki o Quizlet.",
         frases=["¿cómo va la ruta de dominio de 7A?"], produce="—", necesita="Práctica en uso"),
    dict(id="guia_viva", cat="practica", nombre="Guía viva por QR y podcast", handler="live_guide_voice", v="11.4",
         que="Explicación, ejemplo, figura, laboratorio, tarjetas y mini quiz por QR; podcast de repaso con dos voces.",
         frases=["haz una guía viva de fracciones para 7A"], produce="QR + audio", necesita="IA conectada"),
    dict(id="reto", cat="practica", nombre="Reto de la semana y entregas de código", handler="challenge_voice", v="11.1",
         que="Reto matemático con puntos, insignias y ranking; revisión de entregas de programación.",
         frases=["lanza el reto de la semana"], produce="Ranking en el proyector", necesita="—"),
    # ------------------------------------------------------------------ plataformas
    dict(id="classroom", cat="plataformas", nombre="Google Classroom", handler="classroom_voice", v="7.8",
         que="Tareas, entregas y quién no ha entregado en Classroom.", frases=["¿quién no ha entregado en Classroom?"],
         produce="—", necesita="Google conectado"),
    dict(id="retro_entregas", cat="plataformas", nombre="Retroalimentación de entregas", handler="feedback_voice", v="8.1",
         que="Comentarios para cada entrega de Classroom, esperando tu aprobación.",
         frases=["revisa las entregas del taller en Classroom"], produce="Borradores", necesita="Google conectado"),
    dict(id="horario", cat="gestion", nombre="Horario de clases", handler="schedule_voice", v="8.1",
         que="Tu horario de clases (y con él, el modo docente automático).", frases=["¿qué clase tengo ahora?"],
         produce="—", necesita="—"),
    # ------------------------------------------------------------------ gestión
    dict(id="calendario_escolar", cat="gestion", nombre="Calendario escolar", handler="school_calendar_voice", v="12.12",
         que="Festivos de Colombia, recesos y entregas de notas.", frases=["¿mañana hay clase?", "¿qué hay en el calendario escolar?"],
         produce="—", necesita="—"),
    dict(id="reunion_area", cat="gestion", nombre="Reuniones de área", handler="meeting_voice", v="10.0",
         que="Agenda y acta de lo que dictas, punto por punto.", frases=["empieza la reunión de área"], produce="Acta en Word",
         necesita="—"),
    dict(id="kit", cat="gestion", nombre="Kit para colegas", handler="kit_voice", v="10.0",
         que="Exporta lo que le enseñaste a Jarvis para que un colega lo importe.", frases=["exporta mi kit para colegas"],
         produce="Archivo .zip", necesita="—"),
    dict(id="cierre", cat="gestion", nombre="Cierre de periodo", handler="period_voice", v="9.8",
         que="Notas, pendientes y reportes del cierre de periodo.", frases=["cierra el periodo de 7A"], produce="Reportes",
         necesita="Notas del periodo"),
    # ------------------------------------------------------------------ inclusión
    dict(id="piar", cat="inclusion", nombre="Ajustes razonables (PIAR)", handler="aula_voice", v="8.2",
         que="Ajustes razonables para un estudiante según su diagnóstico o barrera.",
         frases=["haz los ajustes razonables para un estudiante con TDAH en séptimo"], produce="Word", necesita="IA conectada"),
    dict(id="lectura_niveles", cat="inclusion", nombre="Lectura en tres niveles", handler="aula_voice", v="9.3",
         que="La misma lectura en nivel básico, intermedio y avanzado con vocabulario y preguntas.",
         frases=["haz una lectura nivelada sobre el ciclo del agua para sexto"], produce="Word", necesita="IA conectada"),
]

# los manejadores que solo son del colegio (los que se apagan en modo general si la frase no habla del colegio)
SCHOOL_ONLY = sorted({h["handler"] for h in H} - {"aula_voice", "week_voice", "solver_voice", "video_anim_voice", "game_voice"})
# aula_voice se filtra por dentro (lo del salón sí es del colegio; un quiz o un taller sirven en cualquier modo)

_SCHOOL_RX = re.compile(
    r"\b(?:cursos?|grados?|estudiantes?|alumn[oa]s?|clases?(?! de (?:baile|yoga|cocina|ingles|guitarra|piano|natacion|musica|pilates|zumba|manejo|conduccion|pintura|futbol|danza|gimnasio))|colegio|salon|aula|periodo|boletin(?:es)?|planeador|plan de clase|"
    r"malla|dba|icfes|saber (?:11|9|once|noveno)|tipo saber|piar|ajustes razonables|classroom|asistencia|recuperacion(?:es)?|"
    r"nivelacion|acudientes?|padres de familia|rector(?:ia)?|coordinador[a]?|coordinacion|docentes?|profes?|maestr[oa]s?|sexto|"
    r"septimo|octavo|noveno|decimo|undecimo|primaria|bachillerato|preescolar|observador|simulacro|coevaluacion|tablero del aula|"
    r"semaforo de ruido|ticket de salida|reunion de area|calendario escolar)\b"
    r"|\b(?:[1-9]|1[01])[a-f]\b|\b(?:[6-9]|1[01])\s?(?:°|º)")


def norm(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def school_explicit(text, courses=()):
    """¿La frase habla del colegio? (cursos como «7A», «mis estudiantes», «la clase», «el periodo», un curso tuyo…)."""
    t = norm(text)
    if _SCHOOL_RX.search(t):
        return True
    return any(re.search(rf"\b{re.escape(norm(c))}\b", t) for c in courses if c)


def by_cat():
    out = []
    for cid, name, desc in CATEGORIAS:
        items = [h for h in H if h["cat"] == cid]
        if items:
            out.append({"id": cid, "nombre": name, "desc": desc, "habilidades": items})
    return out


def search(q):
    words = [w for w in norm(q).split() if len(w) > 2]
    if not words:
        return list(H)
    scored = []
    for h in H:
        name = norm(h["nombre"])
        hay = norm(" ".join([h["que"], " ".join(h["frases"]), h["produce"], h["necesita"]]))
        s = sum(3 if w[:5] in name else 1 if w[:5] in hay else 0 for w in words)
        if s:
            scored.append((s, h))
    return [h for s, h in sorted(scored, key=lambda x: -x[0])]


def examples():
    """Las frases (para la comprensión de lenguaje natural en modo docente)."""
    return [(f"{h['nombre']}: {f}", f) for h in H for f in h["frases"]]
