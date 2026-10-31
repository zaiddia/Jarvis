"""9.7: alertas tempranas (antes del riesgo), ficha del estudiante en el HUD y celebraciones.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import re
import threading
import time

import aula
import compromisos
import informes
import seguimiento
import tendencias
from nucleo import J


# ============================================================================ ALERTAS TEMPRANAS Y CELEBRACIONES
_seen = {"keys": set()}


def early_alerts(today=None):
    return tendencias.scan(seguimiento.data, aula.data.get("asistencia", {}), today)


_EA_RE = re.compile(r"\b(?:alertas tempranas|quien (?:viene|va) bajando|quienes (?:vienen|van) bajando|quien esta faltando mucho|"
                    r"quienes estan faltando|a quien debo felicitar|quien ha mejorado|quienes han mejorado|tendencias de (?:mis )?estudiantes)\b")


def early_voice(text, t):
    if not _EA_RE.search(t):
        return False
    al = J.early_alerts()
    _seen["keys"].update(a["k"] for a in al)
    if re.search(r"\b(?:felicitar|mejorado)\b", t):
        al = [a for a in al if a["tipo"] == "mejora"]
        if not al:
            J.reply("Por ahora nadie tiene una mejora marcada en sus últimas notas.", "SEGUIMIENTO")
            return True
    J.reply(tendencias.spoken(al), "SEGUIMIENTO")
    return True


def early_tick(now=None):
    """Una vez al día (desde las 3 p. m.): avisa de las tendencias nuevas y propone felicitar a quien mejoró."""
    now = now or datetime.datetime.now()
    if not J.settings["early_alerts"] or now.hour < 15 or now.weekday() >= 5:
        return []
    if J.settings["early_last"] == now.date().isoformat():
        return []
    J.settings["early_last"] = now.date().isoformat()
    try:
        J.save_settings_file()
    except OSError:
        pass
    new = [a for a in J.early_alerts(now.date()) if a["k"] not in _seen["keys"]]
    _seen["keys"].update(a["k"] for a in new)
    bad = [a for a in new if a["tipo"] != "mejora"]
    if bad:
        msg = "Alerta temprana: " + "; ".join(f"{a['estudiante']} ({a['curso']}) {a['detalle']}" for a in bad[:4]) + \
              ". Puede ser buen momento para hablar con ellos o con su familia."
        J.notice_add(msg, "aviso", "SEGUIMIENTO")
        J.push_chat("jarvis", msg, "SEGUIMIENTO")
    for a in [a for a in new if a["tipo"] == "mejora"][:3]:
        J.propose_praise(a)
    return new


def propose_praise(a):
    """Celebración: propone anotar una felicitación en el observador (con tu aprobación)."""
    texto = f"Felicitación: {a['detalle']}. ¡Sigue así!"
    J.request_approval("observador", f"Felicitar a {a['estudiante']} ({a['curso']})", texto,
                       on_ok=lambda: (informes.add(a["curso"], a["estudiante"], texto, tipo="positiva"),
                                      J.reply(f"Anoté la felicitación de {a['estudiante']} en el observador.", "SEGUIMIENTO")),
                       on_no=lambda: None, ttl=24 * 3600,
                       say=f"{a['estudiante']} de {a['curso']} {a['detalle']}. ¿Anoto una felicitación en su observador? Di «sí» o «no».")


# ============================================================================ FICHA DEL ESTUDIANTE
_CARD_RE = re.compile(r"^(?:muestrame|muestra|abre|dame|ensename|ver)\s+(?:la\s+)?(?:ficha\s+(?:de|del estudiante)\s+|a\s+)(.+)$|"
                      r"^ficha\s+de\s+(.+)$")


def student_card(course, name):
    notas = sorted(seguimiento.data.get(course, {}).get(name, []), key=lambda n: n.get("fecha", ""))
    avg = seguimiento.average(course, name)
    faltas = [d for d, ns in aula.data.get("asistencia", {}).get(course, {}).items() if name in ns]
    al = [a for a in J.early_alerts() if a["curso"] == course and a["estudiante"] == name]
    first = name.split()[0].lower()
    comp = [x["texto"] for x in compromisos.pending() if first in x["texto"].lower()][:3]
    return {"curso": course, "nombre": name, "promedio": avg, "desempeno": informes.performance(avg),
            "notas": [{"a": n["actividad"][:40], "n": n["nota"], "f": n.get("fecha", "")} for n in notas[-12:]],
            "fallas": len(faltas), "ultimas_fallas": sorted(faltas)[-3:],
            "observador": [{"f": x["fecha"], "t": x["tipo"], "x": x["texto"][:160]} for x in informes.entries(course, name)[-4:]],
            "alertas": [a["detalle"] for a in al], "compromisos": comp,
            "anio": J.year_status(course, name),
            "riesgo": bool(seguimiento.at_risk(course, [name], {name: len(faltas)}, J.settings["risk_grade"], J.settings["risk_absences"]))}


def card_voice(text, t):
    m = _CARD_RE.match(t)
    if not m:
        return False
    who = (m.group(1) or m.group(2) or "").strip()
    if re.match(r"^(?:el|la|los|las|mi|tu|un|una)\b|\b(?:pantalla|calendario|agenda|clima|tablero|proyector|ajustes|horario)\b", who):
        return False
    if "ficha" not in t:                               # «muéstrame a …»: solo si de verdad es un estudiante
        course, name, _c = J._split_student(who)
        if not (course and name and (name in seguimiento.data.get(course, {}) or name in aula.students(course))):
            return False
    else:
        course, name = J._student_or_ask(who, "FICHA")
        if not name:
            return True
    c = J.student_card(course, name)
    J.socketio.emit("student_card", c)
    avg = str(c["promedio"]).replace(".", ",") if c["promedio"] is not None else "sin notas"
    J.reply(f"{name}, {course}: promedio {avg}" + (f" ({c['desempeno']})" if c["desempeno"] else "") + f", {c['fallas']} falla"
            f"{'s' if c['fallas'] != 1 else ''}" + (f", {len(c['observador'])} anotaciones recientes" if c["observador"] else "") +
            (". Ojo: " + c["alertas"][0] if c["alertas"] else "") + ". La ficha está en el HUD.", "FICHA")
    return True


def _early_worker():
    time.sleep(600)
    while True:
        try:
            J.early_tick()
        except Exception as e:
            J.note_error("SEGUIMIENTO", e)
        time.sleep(900)


def students_plus_start():
    threading.Thread(target=J._early_worker, daemon=True, name="alertas-tempranas").start()


__all__ = ['_CARD_RE', '_EA_RE', '_early_worker', '_seen', 'card_voice', 'early_alerts', 'early_tick', 'early_voice', 'propose_praise',
           'student_card', 'students_plus_start']
