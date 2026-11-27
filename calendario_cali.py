"""12.70: calendario académico oficial de las instituciones educativas oficiales de Cali. Lógica pura.

2027: Resolución No. 4143.0.21.0.05592 de 2026 de la Secretaría de Educación Distrital (cali.gov.co). 40 semanas lectivas:
primer semestre (21) del 25 de enero al 27 de junio de 2027 y segundo (19) del 19 de julio al 5 de diciembre de 2027.
"""
import datetime

D = datetime.date
CALI = {
    2027: {
        "resolucion": "Resolución No. 4143.0.21.0.05592 de 2026",
        "inicio_clases": D(2027, 1, 25),
        "semestres": [(D(2027, 1, 25), D(2027, 6, 27), 21), (D(2027, 7, 19), D(2027, 12, 5), 19)],
        "receso": [(D(2027, 1, 11), D(2027, 1, 24)), (D(2027, 3, 22), D(2027, 3, 28)), (D(2027, 6, 28), D(2027, 7, 18)),
                   (D(2027, 10, 4), D(2027, 10, 10)), (D(2027, 12, 6), D(2028, 1, 9))],
        "desarrollo": [(D(2027, 1, 11), D(2027, 1, 24)), (D(2027, 3, 22), D(2027, 3, 28)), (D(2027, 10, 4), D(2027, 10, 10)),
                       (D(2027, 12, 6), D(2027, 12, 12))],
        "vacaciones_docentes": [(D(2027, 6, 28), D(2027, 7, 18)), (D(2027, 12, 13), D(2028, 1, 9))],
        "regreso_docentes": D(2027, 1, 11),
    },
}


def events(year):
    """Los eventos para el calendario escolar de Jarvis: [(título, desde, hasta)]."""
    c = CALI.get(year)
    if not c:
        return []
    out = [(f"Inicio de clases {year}", c["inicio_clases"], c["inicio_clases"])]
    for a, b in c["desarrollo"]:
        out.append(("Semana de desarrollo institucional", a, b))
    for a, b in c["receso"]:
        if (a, b) not in c["desarrollo"]:
            out.append(("Receso estudiantil", a, b))
    for a, b in c["vacaciones_docentes"]:
        out.append(("Vacaciones de docentes", a, b))
    for i, (a, b, n) in enumerate(c["semestres"], 1):
        out.append((f"Fin del {'primer' if i == 1 else 'segundo'} semestre ({n} semanas)", b, b))
    return out


def return_date(today):
    """El próximo regreso de los docentes después de unas vacaciones que ya empezaron o están por empezar."""
    for y in sorted(CALI):
        c = CALI[y]
        cands = [c["regreso_docentes"]] + [b + datetime.timedelta(days=1) for _a, b in c["vacaciones_docentes"]]
        for d in sorted(cands):
            if d > today:
                return d
    return None


__all__ = ["CALI", "events", "return_date"]
