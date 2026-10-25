"""Calendario de Jarvis: lee tus calendarios en formato iCal (solo lectura).

Sirve con Google Calendar («Dirección secreta en formato iCal»), Outlook («Publicar un
calendario», enlace ICS) y cualquier calendario que publique un enlace .ics.
Entiende eventos repetidos (p. ej. «Clase 7A todos los martes») y los pasa a tu hora local.

jarvis.py lo usa para «¿qué tengo hoy?», «¿cuál es mi próxima clase?» y los avisos previos.
"""
import datetime
import threading
import urllib.error
import urllib.parse
import urllib.request

_lock = threading.Lock()
cache = {"events": [], "fetched": 0.0, "errors": [], "urls": ()}
_notified = set()


def _local_tz():
    return datetime.datetime.now().astimezone().tzinfo


def clean_urls(text):
    out = []
    for line in str(text or "").replace(",", "\n").splitlines():
        u = line.strip().strip('"\'<>')
        if not u:
            continue
        if u.lower().startswith("webcal://"):
            u = "https://" + u[9:]
        out.append(u)
    return out


def _host(url):
    return urllib.parse.urlsplit(url).netloc or "el enlace"


def _friendly_error(url, e):
    host = _host(url)
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 404:
            return f"{host}: el enlace no existe (¿lo regeneraste? copia el nuevo)."
        if e.code in (401, 403):
            return f"{host}: no hay permiso. Usa la «dirección secreta», no la pública."
        return f"{host}: el servidor respondió con error {e.code}."
    if isinstance(e, urllib.error.URLError):
        return f"{host}: sin conexión ({e.reason})."
    if isinstance(e, ValueError):
        return f"{host}: ese enlace no es un calendario iCal (.ics)."
    return f"{host}: {e}"


def _to_local(v, tz):
    """date -> date (todo el día); datetime -> datetime local con zona."""
    if isinstance(v, datetime.datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=tz)
        return v.astimezone(tz)
    return v


def fetch(urls, now=None, days=32, timeout=20):
    """Descarga y expande los eventos de ayer a +days. Devuelve (eventos, errores)."""
    import icalendar
    import recurring_ical_events
    tz = _local_tz()
    now = now or datetime.datetime.now(tz)
    start = datetime.datetime.combine(now.date() - datetime.timedelta(days=1), datetime.time(), tz)
    end = datetime.datetime.combine(now.date() + datetime.timedelta(days=days), datetime.time(), tz)
    events, errors = [], []
    for i, url in enumerate(urls):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/5 (calendario)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read(20 * 1024 * 1024)
            if b"BEGIN:VCALENDAR" not in raw[:2000]:
                raise ValueError("no es iCal")
            cal = icalendar.Calendar.from_ical(raw)
            for ev in recurring_ical_events.of(cal).between(start, end):
                if str(ev.get("STATUS", "")).upper() == "CANCELLED":
                    continue
                s = _to_local(ev.get("DTSTART").dt, tz)
                e = _to_local(ev.get("DTEND").dt, tz) if ev.get("DTEND") else None
                todo_dia = not isinstance(s, datetime.datetime)
                if todo_dia and e is None:
                    e = s + datetime.timedelta(days=1)
                elif e is None:
                    e = s + datetime.timedelta(hours=1)
                events.append({"uid": str(ev.get("UID", "")), "titulo": str(ev.get("SUMMARY", "") or "(sin título)").strip(),
                               "lugar": str(ev.get("LOCATION", "") or "").strip(),
                               "inicio": s.isoformat(), "fin": e.isoformat(), "todo_el_dia": todo_dia, "cal": i})
        except Exception as ex:
            errors.append(_friendly_error(url, ex))
    events.sort(key=lambda x: (x["inicio"][:10], not x["todo_el_dia"], x["inicio"]))
    return events, errors


def refresh(urls, force=False, max_age=600):
    urls = tuple(urls)
    with _lock:
        fresh = cache["urls"] == urls and __import__("time").time() - cache["fetched"] < max_age
    if fresh and not force:
        return cache
    events, errors = fetch(urls) if urls else ([], [])
    with _lock:
        cache.update(events=events, errors=errors, urls=urls, fetched=__import__("time").time())
    return cache


def _start(ev):
    if ev["todo_el_dia"]:
        return datetime.date.fromisoformat(ev["inicio"][:10])
    return datetime.datetime.fromisoformat(ev["inicio"])


def on_day(day, events=None):
    """Eventos de ese día: los de todo el día que lo cubren y los que empiezan ese día."""
    out = []
    for ev in (cache["events"] if events is None else events):
        if ev["todo_el_dia"]:
            s = datetime.date.fromisoformat(ev["inicio"][:10])
            e = datetime.date.fromisoformat(ev["fin"][:10])
            if s <= day < max(e, s + datetime.timedelta(days=1)):
                out.append(ev)
        elif datetime.datetime.fromisoformat(ev["inicio"]).date() == day:
            out.append(ev)
    return out


def between(d1, d2, events=None):
    out, d = [], d1
    while d <= d2:
        for ev in on_day(d, events):
            if ev not in out:
                out.append(ev)
        d += datetime.timedelta(days=1)
    return out


def upcoming(now=None, limit=5, keyword="", events=None):
    """Próximos eventos con hora (incluye el que está en curso)."""
    now = now or datetime.datetime.now(_local_tz())
    out = []
    for ev in (cache["events"] if events is None else events):
        if ev["todo_el_dia"]:
            continue
        if datetime.datetime.fromisoformat(ev["fin"]) <= now:
            continue
        if keyword and keyword not in _norm(ev["titulo"] + " " + ev["lugar"]):
            continue
        out.append(ev)
    return out[:limit]


def _norm(t):
    import unicodedata
    t = unicodedata.normalize("NFD", str(t).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def as_note(ev):
    """Forma compatible con notas.when_spoken (para decir la fecha igual que las notas)."""
    s = _start(ev)
    if isinstance(s, datetime.datetime):
        return {"fecha": s.date().isoformat(), "hora": s.strftime("%H:%M")}
    return {"fecha": s.isoformat(), "hora": ""}


def what(ev):
    return ev["titulo"] + (f", en {ev['lugar']}" if ev["lugar"] else "")


def due_alerts(now=None, before_min=10):
    """Eventos que empiezan dentro de before_min minutos (cada uno se avisa una sola vez)."""
    if not before_min:
        return []
    now = now or datetime.datetime.now(_local_tz())
    out = []
    for ev in cache["events"]:
        if ev["todo_el_dia"]:
            continue
        s = datetime.datetime.fromisoformat(ev["inicio"])
        key = (ev["uid"], ev["inicio"])
        if key in _notified:
            continue
        if s - datetime.timedelta(minutes=before_min) <= now < s:
            _notified.add(key)
            out.append((ev, max(1, round((s - now).total_seconds() / 60))))
    return out


def context_for_ai(when_spoken, today=None):
    today = today or datetime.date.today()
    evs = between(today, today + datetime.timedelta(days=6))[:25]
    if not evs:
        return ""
    lines = [f"- {what(e)} ({when_spoken(as_note(e), today)})" for e in evs]
    return " Eventos del calendario del usuario en los próximos 7 días:\n" + "\n".join(lines)
