"""12.70: cerrar el año escolar y modo vacaciones.

  1. «Cierra el año 2026»: guarda todo (copia completa de Jarvis, Excel de notas y asistencia y un resumen por curso en Word,
     en Documentos › Jarvis › Cierre del año 2026), deja los cursos sin estudiantes, notas ni asistencia para las listas
     nuevas, pone el calendario oficial 2027 de Cali en el calendario escolar y la planeación (primer día de clases, 40
     semanas, periodo 1) y en enero te recuerda cargar las listas. Pide tu «sí» antes de vaciar nada.
     «Cierra el año sin borrar nada»: lo mismo, pero sin vaciar los cursos.
  2. «Activa el modo vacaciones» (hasta el regreso de los docentes según el calendario de Cali) o «… hasta el 11 de enero»:
     no hay avisos del colegio (clases, preparación, recuperaciones, evaluaciones, convivencia…) y unos días antes del regreso
     te avisa. Lo personal (pagos, citas, pico y placa, recordatorios) sigue igual. «Desactiva el modo vacaciones» ·
     «¿estoy de vacaciones?».
Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import json
import os
import re
import shutil
import threading

import aula
import calendario_cali as CC
import festivos
import horario
import seguimiento
from nucleo import J

SCHOOL_ORIGINS = {"AULA", "CLASE", "HORARIO", "CALENDARIO", "RECUPERACIÓN", "RECUPERACIONES", "EVALUACIONES", "CONVIVENCIA", "REGLAS",
                  "CLASSROOM", "PLATAFORMA", "ENTREGAS", "TENDENCIAS", "ALERTA TEMPRANA", "COMISIÓN", "PLANEACIÓN", "SABER", "ICFES",
                  "TURNO DE NOCHE", "SEMANA LISTA", "DIARIO DE CLASE", "QUIZ", "OBSERVADOR", "INFORMES", "ESTUDIANTES", "DOCENTE",
                  "SEGUIMIENTO", "CRONOGRAMA", "COLEGIO", "FORMS", "CLASE DE MAÑANA", "RESUMEN DOCENTE"}
year_job = {"busy": False}


# ============================================================================ MODO VACACIONES
def vacation_until():
    v = J.settings.get("vacation_until", "")
    try:
        d = datetime.date.fromisoformat(v) if v else None
    except ValueError:
        return None
    return d if d and d > datetime.date.today() else None


def vacation_on():
    return vacation_until() is not None


def _vac_apply():
    """El horario no tiene clases mientras dure: se apagan los avisos de clase, la preparación y el turno de noche."""
    horario.off_until = vacation_until()


def vac_intercept(text, origin):
    """Lo llama notify: True si es un aviso automático del colegio y estás de vacaciones (va al registro, no se dice)."""
    if not vacation_on() or str(origin).upper() not in SCHOOL_ORIGINS:
        return False
    if getattr(J._tl, "in_job", False) or getattr(J._tl, "cmd_text", None):   # lo que tú pediste sí se dice
        return False
    J.log_terminal(f"(de vacaciones, sin aviso) {text}", origin)
    return True


def vacation_set(until):
    J.settings["vacation_until"] = until.isoformat() if until else ""
    J.settings["vacation_warned"] = ""
    J.save_settings_file()
    _vac_apply()


def vacation_tick(now=None):
    """Tres días antes del regreso avisa una vez; el día del regreso se apaga solo."""
    now = now or datetime.datetime.now()
    v = J.settings.get("vacation_until", "")
    if not v:
        return
    try:
        until = datetime.date.fromisoformat(v)
    except ValueError:
        return
    if now.date() >= until:
        if now.hour >= 6:
            had_lists = bool(J.settings.get("year_reminder"))
            J.settings["year_reminder"] = ""
            vacation_set(None)
            J.notify(f"¡Bienvenido de vacaciones! Hoy, {J.fecha_hablada(now.date())}, vuelven los avisos del colegio." +
                     (" Cuando tengas las listas de este año, pégalas en Ajustes › Aula y colegio (una por curso)." if
                      had_lists else ""), "VACACIONES")
        return
    if (until - now.date()).days <= 3 and now.hour >= 9 and J.settings.get("vacation_warned") != v:
        J.settings["vacation_warned"] = v
        J.save_settings_file()
        J.notify(f"Se acaban las vacaciones: vuelves el {J.fecha_hablada(until)}. Te dejo los avisos del colegio listos para ese día.",
                 "VACACIONES")


_VAC_ON = re.compile(r"^(?:jarvis\s+)?(?:activa|pon|ponte en|entra en|inicia)\s+(?:el\s+)?modo vacaciones(?:\s+hasta\s+(?:el\s+)?(.+))?$|"
                     r"^(?:jarvis\s+)?(?:ya\s+)?(?:me fui|sali|salgo|me voy) (?:a |de )?vacaciones(?:\s+hasta\s+(?:el\s+)?(.+))?$")
_VAC_OFF = re.compile(r"^(?:jarvis\s+)?(?:desactiva|quita|apaga|termina|sal del)\s+(?:el\s+)?modo vacaciones$|"
                      r"^(?:jarvis\s+)?(?:ya\s+)?(?:volvi|regrese) de vacaciones$|^(?:jarvis\s+)?se acabaron las vacaciones$")
_VAC_ASK = re.compile(r"^(?:jarvis\s+)?(?:estoy|sigo) de vacaciones$|^(?:jarvis\s+)?(?:hasta cuando|cuando se acaban) (?:son )?(?:las|mis) vacaciones$|"
                      r"^(?:jarvis\s+)?cuando (?:vuelvo|regreso) al colegio$")


def _vac_voice(text, t):
    m = None if _VAC_ASK.match(t) else _VAC_ON.match(t)
    if m:
        today = datetime.date.today()
        spoken = (m.group(1) or m.group(2) or "").strip()
        until = festivos.parse_date(spoken, today) if spoken else CC.return_date(today)
        if spoken and not until:
            J.reply("No entendí la fecha; dímela así: «activa el modo vacaciones hasta el 11 de enero».", "VACACIONES")
            return True
        if not until or until <= today:
            J.reply("¿Hasta cuándo? Dime «activa el modo vacaciones hasta el 11 de enero».", "VACACIONES")
            return True
        vacation_set(until)
        J.reply(f"¡Felices vacaciones! Hasta el {J.fecha_hablada(until)} no te doy avisos del colegio: ni clases, ni preparación, ni "
                "recuperaciones. Lo personal sigue igual (pagos, citas, recordatorios). Tres días antes te aviso que vuelves." +
                ("" if spoken else " La fecha es el regreso de los docentes del calendario oficial de Cali."), "VACACIONES")
        return True
    if _VAC_OFF.match(t):
        was = vacation_on()
        vacation_set(None)
        J.reply("Listo, vuelven los avisos del colegio." if was else "No estabas en modo vacaciones.", "VACACIONES")
        return True
    if _VAC_ASK.match(t):
        u = vacation_until()
        nxt = CC.return_date(datetime.date.today())
        J.reply(f"Sí: estás de vacaciones hasta el {J.fecha_hablada(u)}." if u else
                ("No tienes activado el modo vacaciones." + (f" Según el calendario de Cali, los docentes vuelven el {J.fecha_hablada(nxt)}."
                                                              if nxt else "")), "VACACIONES")
        return True
    return False


# ============================================================================ CERRAR EL AÑO
def _year_folder(year):
    p = os.path.join(J.settings["output_dir"], f"Cierre del año {year}")
    os.makedirs(p, exist_ok=True)
    return p


def year_summary_doc(year, folder):
    """Word con cada curso: estudiantes, promedio del curso y cuántos quedaron por debajo del mínimo."""
    doc = J.Document()
    doc.add_heading(f"Resumen del año {year}", 0)
    risk = float(J.settings.get("risk_grade", 3.0))
    courses = sorted(set(aula.data.get("cursos", {})) | set(seguimiento.data), key=aula.course_sort_key)
    tb = doc.add_table(rows=1, cols=4)
    tb.style = "Table Grid"
    for i, h in enumerate(("Curso", "Estudiantes", "Promedio del curso", f"Por debajo de {str(risk).replace('.', ',')}")):
        tb.cell(0, i).text = h
    for c in courses:
        names = set(aula.students(c)) | set(seguimiento.data.get(c, {}))
        avgs = [seguimiento.average(c, n) for n in seguimiento.data.get(c, {}) if seguimiento.data[c][n]]
        avgs = [a for a in avgs if a is not None]
        row = tb.add_row().cells
        row[0].text, row[1].text = c, str(len(names))
        row[2].text = str(round(sum(avgs) / len(avgs), 1)).replace(".", ",") if avgs else "-"
        row[3].text = str(sum(1 for a in avgs if a < risk))
    doc.add_paragraph()
    doc.add_paragraph("En esta carpeta también quedan la copia completa de Jarvis (para restaurar cualquier dato desde Ajustes › Datos y "
                      "copias) y el Excel con las notas y la asistencia de cada curso.")
    path = os.path.join(folder, f"Resumen del año {year}.docx")
    doc.save(path)
    return path


def year_archive(year):
    """Copia completa + Excel + resumen en la carpeta del cierre. → {"carpeta", "archivos"}"""
    folder = _year_folder(year)
    files = []
    res = J.make_backup("cierre", upload=False)
    dst = os.path.join(folder, f"Copia completa de Jarvis {year}.zip")
    shutil.copyfile(res["path"], dst)
    files.append(dst)
    try:
        x = J.backup_xlsx(J.settings["output_dir"])
        if x:
            dst = os.path.join(folder, f"Notas y asistencia {year}.xlsx")
            shutil.copyfile(x, dst)
            files.append(dst)
    except Exception as e:
        J.note_error("CIERRE", e)
    files.append(year_summary_doc(year, folder))
    return {"carpeta": folder, "archivos": files}


def year_reset():
    """Vacía estudiantes, notas, asistencia y pendientes de los cursos (los nombres de los cursos se quedan)."""
    for c in list(aula.data.get("cursos", {})):
        aula.data["cursos"][c] = []
    aula.data["asistencia"] = {}
    aula.data["pendientes"] = {}
    aula.save()
    seguimiento.data.clear()
    seguimiento.save()


def year_setup(next_year):
    """El calendario oficial (si lo tengo) en el calendario escolar y en la planeación. → cuántos eventos se agregaron."""
    c = CC.CALI.get(next_year)
    added = 0
    if c:
        have = {(e["titulo"], e["desde"]) for e in festivos.data.get("eventos", [])}
        for title, a, b in CC.events(next_year):
            if (title, a.isoformat()) not in have:
                festivos.add_event(title, a, b)
                added += 1
        J.settings["year_start"] = c["inicio_clases"].isoformat()
        J.settings["school_weeks"] = sum(n for _a, _b, n in c["semestres"])
        J.settings["year_reminder"] = c["regreso_docentes"].isoformat()
    J.settings["period_current"] = 1
    J.save_settings_file()
    return added


_YEAR = re.compile(r"^(?:jarvis\s+)?(?:cierra|cerremos|cerrar|termina|terminemos|finaliza)\s+(?:el\s+)?(?:ano|ano escolar|ano lectivo)"
                   r"(?:\s+(?:escolar|lectivo))?(?:\s+(\d{4}))?(.*)$")


def _year_voice(text, t):
    m = _YEAR.match(t)
    if not m:
        return False
    year = int(m.group(1) or datetime.date.today().year)
    keep = bool(re.search(r"\bsin (?:borrar|vaciar|tocar)\b", m.group(2) or ""))
    if year_job["busy"]:
        J.reply("Ya estoy cerrando el año.", "CIERRE")
        return True
    try:
        locked = J.students_locked()
    except Exception:
        locked = []
    if locked and not keep:
        J.reply("Los datos de estudiantes están cifrados con otra clave: primero ábrelos (Ajustes › Aula y colegio › Datos de "
                "estudiantes) para no perder nada.", "CIERRE")
        return True
    n_courses = len(aula.data.get("cursos", {}))
    n_grades = sum(len(v) for v in seguimiento.data.values())

    def work():
        year_job["busy"] = True
        try:
            arc = J.year_archive(year)
            if not keep:
                J.year_reset()
            added = J.year_setup(year + 1)
        except Exception as e:
            J.notify(f"No pude cerrar el año: {e}. No borré nada que no estuviera guardado.", "CIERRE")
            return
        finally:
            year_job["busy"] = False
        c = CC.CALI.get(year + 1)
        J.notify(f"Listo el cierre del {year}. Guardé la copia completa, el Excel de notas y asistencia y el resumen por curso en "
                 f"Documentos, Jarvis, Cierre del año {year}." +
                 ("" if keep else f" Los {n_courses} cursos quedaron sin estudiantes ni notas, listos para las listas nuevas.") +
                 (f" Puse el calendario {year + 1} de Cali ({added} fechas): las clases empiezan el {J.fecha_hablada(c['inicio_clases'])} y "
                  f"los docentes vuelven el {J.fecha_hablada(c['regreso_docentes'])}; ese día te recuerdo cargar las listas." if c else
                  f" Aún no tengo el calendario oficial {year + 1}: cuando salga, dime el primer día de clases.") +
                 ("" if vacation_on() else " ¿Activo el modo vacaciones? Di «activa el modo vacaciones»."), "CIERRE")
        if J.settings.get("aula_open_docs", True):
            J._open_doc(arc["carpeta"])

    if keep:
        J.reply(f"Cierro el {year} sin borrar nada: guardo todo y preparo el calendario {year + 1}…", "CIERRE")
        J.start_job("Cerrando el año", work, "cierre")
        return True
    J.request_approval("cierre", f"Cerrar el año {year}",
                       f"Guardo todo ({n_courses} cursos, {n_grades} estudiantes con notas) y dejo los cursos sin estudiantes, notas ni "
                       "asistencia para las listas nuevas.",
                       on_ok=lambda: (J.reply("Cierro el año: primero guardo todo…", "CIERRE"), J.start_job("Cerrando el año", work, "cierre")),
                       on_no=lambda: J.reply("Vale, no cierro el año. Si quieres solo guardar todo, di «cierra el año sin borrar nada».",
                                             "CIERRE"), ttl=1800,
                       say=f"Voy a guardar todo el {year} y dejar los cursos vacíos para las listas nuevas. ¿Sigo? Di «sí» o «no».")
    return True


def year_reminder_tick(now=None):
    """El día que vuelven los docentes, un recordatorio (si no estás en modo vacaciones, que avisa por su cuenta)."""
    now = now or datetime.datetime.now()
    v = J.settings.get("year_reminder", "")
    if not v or now.hour < 7 or v > now.date().isoformat() or vacation_on() or J.settings.get("vacation_until"):
        return
    J.settings["year_reminder"] = ""
    J.save_settings_file()
    J.notify("Hoy vuelven los docentes al colegio. Cuando tengas las listas del año, pégalas en Ajustes › Aula y colegio "
             "(una lista por curso).", "CIERRE")


def ano70_tick(now=None):
    vacation_tick(now)
    year_reminder_tick(now)


def ano70_voice(text, t):
    return _vac_voice(text, t) or _year_voice(text, t)


def ano70_start():
    _vac_apply()


__all__ = ['SCHOOL_ORIGINS', '_VAC_ASK', '_VAC_OFF', '_VAC_ON', '_YEAR', '_vac_apply', '_vac_voice', '_year_folder', '_year_voice',
           'ano70_start', 'ano70_tick', 'ano70_voice', 'vac_intercept', 'vacation_on', 'vacation_set', 'vacation_tick', 'vacation_until',
           'year_archive', 'year_job', 'year_reminder_tick', 'year_reset', 'year_setup', 'year_summary_doc']
