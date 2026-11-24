"""12.39: lo que Jarvis hace solo, en un solo lugar y cambiable por voz.

- Tareas para más tarde: «esta noche a las 2 investiga los mejores portátiles para docentes», «mañana a las 6 haz un
  proyecto…». Solo investigaciones y proyectos (nada que actúe en tu PC). Si el equipo estaba apagado a esa hora, se hace
  al volver mientras aún tenga sentido (hasta 6 horas tarde); si no, se salta y queda anotado.
- Horas de silencio: «no me hables sin que te pregunte entre las 11 de la noche y las 6 de la mañana». En ese rato no
  dice avisos que nadie pidió (los guarda y te los cuenta luego); lo que pusiste a una hora a propósito —alarmas,
  recordatorios, medicamentos, citas— sí suena. Si estás hablando con Jarvis, te contesta normal.
- «¿Qué tengo programado?»: rutinas con hora, proyectos que se repiten, lo automático del colegio y de la mañana,
  las tareas para más tarde y las horas de silencio, con su próxima vez.
- Cambiarlo por voz: «pasa el reporte de la mañana a las 6:45», «apaga la clase de mañana», «activa el resumen docente».
"""
import datetime
import json
import os
import re
import threading
import time

import hogar
import proactivo
import proyectos
import rutinas
from nucleo import J

LATE = 6 * 3600                              # una tarea programada aún vale si el equipo vuelve hasta 6 h tarde
_ag = {"lock": threading.Lock(), "last_user": 0.0}
CHOSEN = {"ALARMA", "TEMPORIZADOR", "RECORDATORIO", "MEDICAMENTOS", "CITAS", "SISMO", "RECORDATORIOS"}
DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _ag_path():
    return os.path.join(J.CONFIG_DIR, "programadas.json")


def scheduled():
    try:
        with open(_ag_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _ag_save(items):
    tmp = _ag_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _ag_path())


# ============================================================================ TAREAS PARA MÁS TARDE
_WHEN = re.compile(r"^(?:jarvis[ ,]+)?(?:por favor\s+)?(?P<dia>esta noche|hoy|esta tarde|ma[nñ]ana|pasado ma[nñ]ana|el (?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo))?"
                   r"\s*,?\s*a las (?P<h>\d{1,2})(?:(?::| y )(?P<m>\d{2}|media|cuarto))?\s*(?P<ap>de la ma[nñ]ana|de la tarde|de la noche|de la madrugada|am|pm)?"
                   r"\s*,?\s*(?P<orden>.+)$")


def parse_later(t, now=None):
    """«esta noche a las 2 investiga X» → (datetime, «investiga X») o None. Solo investigaciones y proyectos."""
    now = now or datetime.datetime.now()
    m = _WHEN.match(t)
    if not m:
        return None
    orden = m.group("orden").strip(" ,.")
    on = J.normalize(orden)
    if not (J._RESEARCH_RE.search(on) or proyectos.is_project(on) or proyectos.is_project(on, general=True)):
        return None
    h = int(m.group("h"))
    mi = {"media": 30, "cuarto": 15}.get(m.group("m") or "", None)
    mi = int(m.group("m")) if mi is None and m.group("m") else (mi or 0)
    ap, dia = hogar.norm(m.group("ap") or ""), hogar.norm(m.group("dia") or "")
    if h > 23 or mi > 59:
        return None
    if ap in ("de la tarde", "pm") and h < 12:
        h += 12
    elif ap == "de la noche" and 6 <= h < 12:
        h += 12
    elif ap in ("de la manana", "am", "de la madrugada") and h == 12:
        h = 0
    elif not ap and dia in ("esta tarde",) and h < 12:
        h += 12
    elif not ap and dia == "esta noche" and 6 <= h < 12:
        h += 12
    day = now.date()
    if dia == "manana":
        day += datetime.timedelta(days=1)
    elif dia == "pasado manana":
        day += datetime.timedelta(days=2)
    elif dia.startswith("el "):
        wd = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"].index(dia[3:])
        day += datetime.timedelta(days=(wd - now.weekday()) % 7 or 7)
    when = datetime.datetime.combine(day, datetime.time(h, mi))
    if dia == "esta noche" and h < 6:                      # «esta noche a las 2» = la madrugada que viene
        when += datetime.timedelta(days=1)
    if when <= now and not dia.startswith("el "):
        when += datetime.timedelta(days=1)
    return when, orden


def add_later(when, orden):
    with _ag["lock"]:
        items = scheduled()
        it = {"id": max([x["id"] for x in items] + [0]) + 1, "cuando": when.isoformat(timespec="minutes"), "orden": orden,
              "creada": datetime.datetime.now().isoformat(timespec="minutes"), "estado": "pendiente"}
        items.append(it)
        _ag_save(items)
    return it


def when_text(when, now=None):
    now = now or datetime.datetime.now()
    d = when.date()
    day = "hoy" if d == now.date() else "mañana" if d == now.date() + datetime.timedelta(days=1) else f"el {DAYS[d.weekday()]} {d.day}"
    return f"{day} a las {when:%H:%M}"


def later_tick(now=None):
    """Lo que toca. Lo que se pasó de la hora más de LATE se salta (y queda anotado). → órdenes lanzadas."""
    now = now or datetime.datetime.now()
    ran = []
    with _ag["lock"]:
        items = scheduled()
        changed = False
        for it in items:
            if it.get("estado") != "pendiente":
                continue
            when = datetime.datetime.fromisoformat(it["cuando"])
            if when > now:
                continue
            changed = True
            if (now - when).total_seconds() > LATE:
                it["estado"] = "saltada"
                J.log_terminal(f"Tarea programada para {it['cuando']} saltada: el equipo estuvo apagado demasiado tiempo («{it['orden']}»).", "AGENDA")
                continue
            it["estado"], it["hecha"] = "lanzada", now.isoformat(timespec="minutes")
            ran.append(it["orden"])
        if changed:
            keep = (now - datetime.timedelta(days=14)).isoformat()
            _ag_save([x for x in items if x.get("estado") == "pendiente" or x.get("cuando", "") >= keep])
    for o in ran:
        J.log_terminal(f"Empiezo lo que me dejaste programado: «{o}».", "AGENDA")
        J.submit_command(o)
    return ran


def _ag_worker():
    time.sleep(60)
    while True:
        for fn in (J.later_tick, J.study_tick, J.watch_tick, J.nuevas52_tick, J.colegio53_tick):   # 12.40: práctica y precios · 12.52: páginas
            try:
                fn()
            except Exception as e:
                J.note_error("AGENDA", e)
        time.sleep(60)


def agenda_start():
    threading.Thread(target=J._ag_worker, daemon=True, name="agenda").start()


# ============================================================================ HORAS DE SILENCIO
def note_user_activity():
    _ag["last_user"] = time.time()


def in_quiet_hours(now=None):
    return bool(J.settings.get("proactive_quiet")) and proactivo.in_quiet(now or datetime.datetime.now(), J.settings["proactive_quiet"])


def quiet_holds(origin, now=None):
    """¿Las horas de silencio guardan este aviso? No: si lo pusiste a una hora a propósito, o si estás hablando con Jarvis."""
    if not J.in_quiet_hours(now):
        return False
    if str(origin).upper() in CHOSEN:
        return False
    return time.time() - _ag["last_user"] > 600


def _hh(text):
    """«las 11 de la noche» → "23:00"; «las 6 de la mañana» → "06:00"."""
    t = hogar.norm(text)
    m = re.search(r"(\d{1,2})(?:(?::| y | )(\d{2}|media)\b)?\s*(de la manana|de la tarde|de la noche|de la madrugada|am|pm)?", t)
    if not m:
        return ""
    h, mi = int(m.group(1)), 30 if m.group(2) == "media" else int(m.group(2) or 0)
    ap = m.group(3) or ""
    if ap in ("de la tarde", "pm") and h < 12 or ap == "de la noche" and 6 <= h < 12:
        h += 12
    if ap in ("de la manana", "am", "de la madrugada") and h == 12 or ap == "de la noche" and h == 12:
        h = 0
    return f"{h:02d}:{mi:02d}" if h <= 23 and mi <= 59 else ""


_QH_SET = re.compile(r"\b(?:no me hables|no me digas nada|no me avises|no hables|silencio|horas? de silencio)\b.*?\b(?:entre|de|desde)\s+(?:las\s+)?(.+?)\s+(?:y|a|hasta)\s+(?:las\s+)?(.+)$")
_QH_OFF = re.compile(r"\b(?:quita|elimina|desactiva|apaga|borra)\w*\s+(?:las\s+)?horas? de silencio\b")
_QH_ASK = re.compile(r"\b(?:cuales son|que|a que hora son|tengo)\s+(?:mis\s+|las\s+)?horas? de silencio\b")


def quiet_voice(text, t):
    if _QH_OFF.search(t):
        J.apply_settings({"proactive_quiet": ""})
        J.reply("Listo: sin horas de silencio. Puedo avisarte a cualquier hora.", "AGENDA")
        return True
    if _QH_ASK.search(t):
        q = J.settings.get("proactive_quiet") or ""
        J.reply(f"Tus horas de silencio son de {q.replace('-', ' a ')}." if q else "No tienes horas de silencio.", "AGENDA")
        return True
    m = _QH_SET.search(t)
    if m and ("pregunt" in t or "silencio" in t or "por mi cuenta" in t or "sin que" in t or "no me hables" in t):
        a, b = _hh(m.group(1)), _hh(m.group(2))
        if not (a and b):
            return False
        J.apply_settings({"proactive_quiet": f"{a}-{b}"})
        J.reply(f"Listo: de {a} a {b} no te digo nada que no hayas pedido; lo guardo y te lo cuento después. Las alarmas, "
                "los recordatorios, los medicamentos y las citas sí suenan a su hora.", "AGENDA")
        return True
    return False


# ============================================================================ AGENDA: TODO JUNTO
# Lo automático de siempre: nombre, palabras con que lo dices, clave de encendido, clave de hora, cuándo
BUILTIN = [
    ("Reporte de la mañana", r"reporte de la manana|resumen de la manana|reporte matutino|buenos dias", "morning_enabled", "morning_time", "diario"),
    ("Resumen de la semana al celular", r"resumen (?:de la semana|semanal)(?! docente)", "weekly_summary", "weekly_hour", "weekly"),
    ("Semana lista (domingo)", r"semana lista|preparar la semana", "week_prep", "week_prep_hour", "domingo"),
    ("La clase de mañana lista", r"clase de manana|clases de manana", "night_prep", "night_prep_hour", "noches"),
    ("Resumen docente del viernes", r"resumen docente|resumen del viernes", "docente_friday", "docente_friday_hour", "viernes"),
    ("Respaldo de notas", r"respaldo (?:de notas|semanal)", "auto_backup", "docente_friday_hour", "viernes"),
    ("Cierre de periodo completo", r"cierre (?:de periodo )?completo", "close_followups", "", ""),
    ("Alertas tempranas", r"alertas tempranas", "early_alerts", "", ""),
]


def _bt_when(key_on, key_t, kind):
    s = J.settings
    if not s.get(key_on, False):
        return "apagado"
    v = s.get(key_t) if key_t else None
    hh = v if isinstance(v, str) else f"{int(v):02d}:00" if v is not None else ""
    if kind == "diario":
        return f"todos los días a las {hh}"
    if kind == "weekly":
        return f"los {s.get('weekly_day', 'viernes')} desde las {hh}"
    if kind == "domingo":
        return f"los domingos desde las {hh}"
    if kind == "noches":
        return f"de domingo a jueves desde las {hh}"
    if kind == "viernes":
        return f"los viernes desde las {hh}"
    return "encendido"


def agenda_items(now=None):
    """[(grupo, texto)] con todo lo que Jarvis hace solo."""
    now = now or datetime.datetime.now()
    out = []
    for name, _rx, on, tk, kind in BUILTIN:
        out.append(("Automático", f"{name}: {_bt_when(on, tk, kind)}"))
    for r in rutinas.routines:
        w = rutinas.when_spoken(r.get("cuando", ""))
        if w:
            out.append(("Rutinas", f"{r['nombre']}: {w}"))
    try:
        import automaticos
        for r in automaticos.data.get("recurrentes", []):
            dias = r.get("dias") or []
            dd = "todos los días" if len(dias) == 7 else ", ".join(DAYS[d] for d in dias)
            out.append(("Proyectos que se repiten", f"{r.get('pedido', '')[:80]}: {dd} a las {r.get('hora', '')}"))
    except Exception:
        pass
    for it in scheduled():
        if it.get("estado") == "pendiente":
            out.append(("Para más tarde", f"{it['id']}. {it['orden'][:90]}: {when_text(datetime.datetime.fromisoformat(it['cuando']), now)}"))
    q = J.settings.get("proactive_quiet") or ""
    out.append(("Horas de silencio", f"de {q.replace('-', ' a ')}" if q else "ninguna"))
    return out


def agenda_text(now=None):
    groups = {}
    for g, txt in agenda_items(now):
        groups.setdefault(g, []).append(txt)
    return "\n".join(f"{g}: " + "; ".join(v) + "." for g, v in groups.items())


_AG_ASK = re.compile(r"\b(?:que|cuales?)\s+(?:tengo|tienes|hay)\s+(?:programad[oa]s?|agendad[oa]s?)\b|\bque haces (?:tu )?solo\b|"
                     r"\b(?:mi|la) agenda de (?:jarvis|automaticos?)\b|\bque tareas (?:programadas|para mas tarde) tengo\b")
_AG_CANCEL = re.compile(r"\b(?:cancela|borra|elimina|quita)\w*\s+(?:la\s+)?tarea (?:programada|para mas tarde)\s+(\d+)\b")
_AG_MOVE = re.compile(r"\b(?:pasa|cambia|mueve|pon|programa)\w*\s+(?:el\s+|la\s+|mi\s+)?(.+?)\s+(?:a|para)\s+las\s+(.+)$")
_AG_ONOFF = re.compile(r"\b(apaga|desactiva|quita|activa|enciende|prende|pon)\w*\s+(?:el\s+|la\s+|las\s+|mi\s+)?(.+)$")


def _builtin(name_text):
    for b in BUILTIN:
        if re.search(rf"\b(?:{b[1]})\b", name_text):
            return b
    return None


def agenda_voice(text, t):
    if _AG_ASK.search(t):
        J.reply("Esto es lo que hago solo:\n" + agenda_text(), "AGENDA")
        return True
    m = _AG_CANCEL.search(t)
    if m:
        with _ag["lock"]:
            items = scheduled()
            hit = next((x for x in items if str(x["id"]) == m.group(1) and x.get("estado") == "pendiente"), None)
            if hit:
                hit["estado"] = "cancelada"
                _ag_save(items)
        J.reply(f"Cancelé la tarea {m.group(1)}: «{hit['orden']}»." if hit else f"No tengo una tarea programada número {m.group(1)}.", "AGENDA")
        return True
    later = parse_later(text.strip().lower())
    if later:
        when, orden = later
        it = add_later(when, orden)
        J.reply(f"Listo: {when_text(when)} hago «{orden}» (tarea {it['id']}). Si el equipo está apagado a esa hora, la hago al "
                "encenderlo, hasta 6 horas después. Te aviso cuando esté.", "AGENDA")
        return True
    m = _AG_MOVE.search(t)
    if m:
        b = _builtin(m.group(1))
        if b and b[3]:
            hh = _hh(m.group(2))
            if not hh:
                return False
            if isinstance(J.DEFAULT_SETTINGS.get(b[3]), int):
                val = int(hh[:2])
                lo, hi = J.RANGES.get(b[3], (0, 23)) if hasattr(J, "RANGES") else (0, 23)
                val = max(int(lo), min(int(hi), val))
                J.apply_settings({b[3]: val, b[2]: True})
                extra = f" (en punto: este aviso va por horas)" if hh[3:] != "00" else ""
                J.reply(f"Listo: «{b[0]}» ahora es {_bt_when(b[2], b[3], b[4])}{extra}.", "AGENDA")
            else:
                J.apply_settings({b[3]: hh, b[2]: True})
                J.reply(f"Listo: «{b[0]}» ahora es {_bt_when(b[2], b[3], b[4])}.", "AGENDA")
            return True
    m = _AG_ONOFF.search(t)
    if m:
        b = _builtin(m.group(2))
        if b and len(m.group(2)) < 60:
            on = not m.group(1).startswith(("apag", "desact", "quit"))
            J.apply_settings({b[2]: on})
            J.reply(f"Listo: «{b[0]}» {'encendido' if on else 'apagado'}" + (f" ({_bt_when(b[2], b[3], b[4])})" if on and b[3] else "") + ".", "AGENDA")
            return True
    return False


__all__ = ['BUILTIN', 'CHOSEN', 'DAYS', 'LATE', '_AG_ASK', '_AG_CANCEL', '_AG_MOVE', '_AG_ONOFF', '_QH_ASK', '_QH_OFF', '_QH_SET', '_WHEN',
           '_ag', '_ag_path', '_ag_save', '_ag_worker', '_bt_when', '_builtin', '_hh', 'add_later', 'agenda_items', 'agenda_start',
           'agenda_text', 'agenda_voice', 'in_quiet_hours', 'later_tick', 'note_user_activity', 'parse_later', 'quiet_holds',
           'quiet_voice', 'scheduled', 'when_text']
