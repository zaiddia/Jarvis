"""Jarvis habla primero, con criterio: solo cuando de verdad ayuda y sin ser pesado.

Decide (no habla): jarvis.py le pasa los datos (hora, inactividad, batería, pronóstico, calendario, rutinas)
y este módulo dice qué aviso toca, si alguno. Reglas:
  · horas de silencio (por defecto 21:30–06:30) y un máximo de avisos al día;
  · al menos 15 minutos entre dos avisos «opcionales» (pausas, batería, lluvia, saludo);
  · cada aviso concreto se da una sola vez (la misma clase, la misma descarga de batería, la misma lluvia).

Avisos:
  saludo      el primer uso del día por la mañana: hora, clima y lo que tienes hoy
  pausa       llevas mucho rato seguido en el equipo sin descansar
  bateria     batería baja y sin cargador
  lluvia      va a llover a tu hora de salida
  rutina      un evento del calendario empieza pronto y tienes una rutina para eso («¿activo el modo clase?»)
"""
import datetime
import re
import unicodedata

GAP_MIN = 15


def _norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w\s]", " ", t)


def parse_range(text):
    """«21:30-06:30» → ((21, 30), (6, 30)); None si está vacío o mal."""
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*", str(text or ""))
    if not m:
        return None
    a, b = (int(m.group(1)), int(m.group(2))), (int(m.group(3)), int(m.group(4)))
    if a[0] > 23 or b[0] > 23 or a[1] > 59 or b[1] > 59:
        return None
    return a, b


def in_quiet(now, quiet):
    r = parse_range(quiet)
    if not r:
        return False
    cur = now.hour * 60 + now.minute
    a, b = r[0][0] * 60 + r[0][1], r[1][0] * 60 + r[1][1]
    return a <= cur < b if a < b else (cur >= a or cur < b)


def parse_hhmm(text):
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(text or ""))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return int(m.group(1)), int(m.group(2))


class State:
    """Lo que ya se avisó (para no repetir) y la actividad continua."""

    def __init__(self):
        self.day = None
        self.count = 0
        self.last_optional = None
        self.done = set()               # claves de avisos ya dados hoy
        self.active_since = None        # desde cuándo usas el equipo sin una pausa de 5 minutos
        self.break_warned = False
        self.max_idle = 0.0             # inactividad más larga desde el último uso (para el saludo)
        self.battery_warned = False

    def new_day(self, today):
        if self.day != today:
            self.day, self.count, self.done = today, 0, set()


def can_speak(st, now, cfg, optional=True):
    """¿Se puede avisar ahora? cfg: proactive_enabled, proactive_quiet, proactive_max."""
    st.new_day(now.date())
    if not cfg.get("proactive_enabled", True):
        return False
    if in_quiet(now, cfg.get("proactive_quiet", "")):
        return False
    if st.count >= int(cfg.get("proactive_max", 12)):
        return False
    if optional and st.last_optional and (now - st.last_optional).total_seconds() < GAP_MIN * 60:
        return False
    return True


def said(st, now, key, optional=True):
    st.count += 1
    st.done.add(key)
    if optional:
        st.last_optional = now


def activity(st, now, idle_seconds):
    """Llamar cada ~30 s con los segundos sin tocar teclado ni ratón."""
    if idle_seconds >= 300:                       # una pausa de 5 minutos reinicia la cuenta
        st.active_since, st.break_warned = None, False
    elif st.active_since is None:
        st.active_since = now - datetime.timedelta(seconds=idle_seconds)
    st.max_idle = max(st.max_idle, idle_seconds)


def break_due(st, now, cfg):
    if not cfg.get("proactive_breaks", True) or st.active_since is None or st.break_warned:
        return None
    mins = (now - st.active_since).total_seconds() / 60
    limit = int(cfg.get("proactive_break_min", 120))
    if mins < limit:
        return None
    st.break_warned = True
    h = limit // 60
    tiempo = f"{h} hora{'s' if h != 1 else ''}" if limit % 60 == 0 else f"{limit} minutos"
    return ("pausa", f"Llevas {tiempo} seguidas en el equipo. Buen momento para estirarte, tomar agua y "
                     "descansar la vista un par de minutos.")


def battery_due(st, percent, plugged, cfg):
    if percent is None or not cfg.get("proactive_battery", True):
        return None
    if plugged or percent > 30:
        st.battery_warned = False
        return None
    if percent <= 20 and not st.battery_warned:
        st.battery_warned = True
        return ("bateria", f"Batería al {int(percent)} por ciento y sin cargador. Conéctalo pronto.")
    return None


def greeting_due(st, now, idle_seconds, cfg, done_today=False):
    """El primer uso del día por la mañana tras mucho rato sin usar el equipo (≥ 4 h)."""
    if not cfg.get("proactive_greeting", True) or done_today or "saludo" in st.done:
        return False
    if not (5 <= now.hour < 12):
        return False
    if idle_seconds < 60 and st.max_idle >= 4 * 3600:
        st.max_idle = 0.0
        return True
    if idle_seconds < 60:
        st.max_idle = 0.0
    return False


def rain_due(st, now, leave, hourly, cfg):
    """hourly: [("AAAA-MM-DDTHH:00", probabilidad)]. Avisa una hora antes de la salida si llueve a esa hora."""
    hm = parse_hhmm(leave)
    if not hm or not cfg.get("proactive_rain", True) or "lluvia" in st.done:
        return None
    out_at = now.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    if not (out_at - datetime.timedelta(minutes=70) <= now <= out_at - datetime.timedelta(minutes=40)):
        return None
    day = now.date().isoformat()
    near = [p for t, p in hourly if t.startswith(day) and p is not None and abs(int(t[11:13]) - hm[0]) <= 1]
    if not near or max(near) < 50:
        return None
    return ("lluvia", f"A tu hora de salida ({hm[0]}:{hm[1]:02d}) hay {int(max(near))} por ciento de probabilidad "
                      "de lluvia. No olvides el paraguas.")


_STOP = {"modo", "de", "del", "la", "el", "los", "las", "fin", "rutina", "inicio", "empieza", "con", "y", "a", "en", "para"}


def routine_for_event(title, routines):
    """La rutina que encaja con un evento («Clase 7A» → «Modo clase»). Nunca una de «fin de…» ni una con hora propia."""
    words = {w for w in _norm(title).split() if len(w) >= 4 and w not in _STOP}
    best, score = None, 0
    for r in routines:
        name = _norm(r.get("nombre", ""))
        if name.startswith("fin ") or r.get("cuando"):
            continue
        keys = {w for w in name.split() if len(w) >= 4 and w not in _STOP}
        s = len(words & keys)
        if s > score:
            best, score = r, s
    return best if score else None
