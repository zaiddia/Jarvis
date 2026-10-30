"""Crear eventos en tu calendario (7.7): «agenda una reunión con los padres de Juan el jueves a las 3».

Sin pedirte permisos de Google ni de Microsoft: la IA entiende la fecha y la hora, y Jarvis
  · abre Google Calendar con el evento ya escrito (tú solo pulsas «Guardar»), o
  · crea un archivo .ics que se abre en Outlook o en el Calendario de Windows.
Además, si quieres, Jarvis te lo recuerda antes.
"""
import datetime
import json
import os
import re
import urllib.parse
import uuid


def parse_prompt(text, today=None):
    today = today or datetime.date.today()
    return (f"Hoy es {today.isoformat()} ({['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'][today.weekday()]}). "
            f"Extrae el evento de esta frase: «{text}».\nResponde SOLO con JSON: "
            '{"titulo": "…", "fecha": "AAAA-MM-DD", "hora": "HH:MM" o "", "duracion_min": 60, "lugar": "…" o "", '
            '"descripcion": "…" o ""}. Si no dice la hora, deja "hora" vacía (evento de todo el día). '
            "Interpreta «el jueves» como el próximo jueves, «mañana», «pasado mañana», etc.")


def validate(d):
    if not isinstance(d, dict):
        raise ValueError("no entendí el evento")
    titulo = str(d.get("titulo") or "").strip()[:120]
    try:
        fecha = datetime.date.fromisoformat(str(d.get("fecha") or "")[:10])
    except ValueError:
        raise ValueError("no entendí la fecha")
    hora = str(d.get("hora") or "").strip()
    if hora and not re.fullmatch(r"\d{1,2}:\d{2}", hora):
        hora = ""
    try:
        dur = max(10, min(12 * 60, int(d.get("duracion_min") or 60)))
    except (TypeError, ValueError):
        dur = 60
    if not titulo:
        raise ValueError("no entendí qué es el evento")
    return {"titulo": titulo, "fecha": fecha.isoformat(), "hora": hora, "duracion_min": dur,
            "lugar": str(d.get("lugar") or "").strip()[:120], "descripcion": str(d.get("descripcion") or "").strip()[:500]}


def _span(ev):
    d = datetime.date.fromisoformat(ev["fecha"])
    if not ev["hora"]:
        return d, d + datetime.timedelta(days=1), True
    h, m = map(int, ev["hora"].split(":"))
    start = datetime.datetime(d.year, d.month, d.day, h, m)
    return start, start + datetime.timedelta(minutes=ev["duracion_min"]), False


def google_url(ev):
    a, b, allday = _span(ev)
    fmt = (lambda x: x.strftime("%Y%m%d")) if allday else (lambda x: x.strftime("%Y%m%dT%H%M%S"))
    q = {"action": "TEMPLATE", "text": ev["titulo"], "dates": f"{fmt(a)}/{fmt(b)}", "ctz": "America/Bogota"}
    if ev["lugar"]:
        q["location"] = ev["lugar"]
    if ev["descripcion"]:
        q["details"] = ev["descripcion"]
    return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(q)


def _esc(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics(ev, now=None):
    a, b, allday = _span(ev)
    now = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    if allday:
        dt = f"DTSTART;VALUE=DATE:{a:%Y%m%d}\r\nDTEND;VALUE=DATE:{b:%Y%m%d}"
    else:
        dt = f"DTSTART:{a:%Y%m%dT%H%M%S}\r\nDTEND:{b:%Y%m%dT%H%M%S}"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Jarvis//ES", "BEGIN:VEVENT", f"UID:{uuid.uuid4()}@jarvis",
             f"DTSTAMP:{now}", dt, f"SUMMARY:{_esc(ev['titulo'])}"]
    if ev["lugar"]:
        lines.append(f"LOCATION:{_esc(ev['lugar'])}")
    if ev["descripcion"]:
        lines.append(f"DESCRIPTION:{_esc(ev['descripcion'])}")
    lines += ["BEGIN:VALARM", "TRIGGER:-PT30M", "ACTION:DISPLAY", f"DESCRIPTION:{_esc(ev['titulo'])}", "END:VALARM",
              "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


def save_ics(ev, folder):
    os.makedirs(folder, exist_ok=True)
    name = re.sub(r'[<>:"/\\|?*]+', " ", ev["titulo"]).strip()[:60] or "evento"
    path = os.path.join(folder, f"{ev['fecha']} {name}.ics")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(ics(ev))
    return path


def spoken(ev):
    d = datetime.date.fromisoformat(ev["fecha"])
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
             "noviembre", "diciembre"]
    txt = f"«{ev['titulo']}» el {dias[d.weekday()]} {d.day} de {meses[d.month - 1]}"
    if ev["hora"]:
        h, m = map(int, ev["hora"].split(":"))
        txt += f" a las {h}:{m:02d}"
    if ev["lugar"]:
        txt += f" en {ev['lugar']}"
    return txt


_TRIGGER = re.compile(r"^(?:jarvis\s+)?(?:agenda(?:me|r)?|crea(?:me)? (?:un|una) (?:evento|cita|reunion)|"
                      r"pon(?:me|lo)? en (?:mi|el) calendario|anota en (?:mi|el) calendario|a[nñ]ade (?:a|en) (?:mi|el) calendario|"
                      r"programa(?:me)? una (?:reunion|cita))\b")


def is_event(t):
    return bool(_TRIGGER.search(t)) and not re.search(r"\b(?:que|qué) tengo\b", t)


def dumps(ev):
    return json.dumps(ev, ensure_ascii=False)
