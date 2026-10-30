"""Diario de Jarvis: lo que pasó cada día (tus órdenes, las rutinas, los avisos), solo en tu equipo.

Es la «memoria del día a día», entre la memoria permanente (perfil.py: quién eres, qué te gusta) y la
conversación reciente. Sirve para «¿qué hice ayer?», «resume mi semana» y para que la IA sepa qué
estás haciendo hoy. Se guarda en diario/AAAA-MM-DD.jsonl y se borra solo pasados N días.

Este módulo no habla ni llama a la IA: jarvis.py decide qué anotar y cómo contarlo.
"""
import datetime
import json
import os
import re
import threading
import unicodedata

_lock = threading.Lock()
_dir = None
enabled = True
keep_days = 30

# Tipos de entrada y cómo se cuentan
KINDS = {"orden": "órdenes", "rutina": "rutinas", "temporizador": "temporizadores", "recordatorio": "recordatorios",
         "nota": "notas", "aviso": "avisos", "habilidad": "habilidades", "busqueda": "búsquedas", "pregunta": "preguntas",
         "tarea": "tareas programadas"}

# Lo que nunca se anota (por si alguien dicta algo privado)
_PRIVATE = re.compile(r"\b(?:contrasena|password|clave|pin|tarjeta|cvv|codigo de seguridad)\b")


def _norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def configure(config_dir, on=True, days=30):
    global _dir, enabled, keep_days
    _dir = os.path.join(config_dir, "diario")
    enabled, keep_days = bool(on), max(1, int(days))


def _path(day):
    return os.path.join(_dir, f"{day.isoformat()}.jsonl")


def log(kind, text, now=None):
    """Anota una entrada. Nunca falla (el diario no debe estorbar a nada)."""
    if not (enabled and _dir) or not str(text).strip():
        return
    if _PRIVATE.search(_norm(text)):
        text = "(algo privado, no lo anoto)"
    now = now or datetime.datetime.now()
    line = json.dumps({"t": now.strftime("%H:%M"), "k": kind, "x": str(text).strip()[:240]}, ensure_ascii=False)
    try:
        with _lock:
            os.makedirs(_dir, exist_ok=True)
            with open(_path(now.date()), "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError:
        pass


def day(d):
    """Entradas de ese día: [{"t": "HH:MM", "k": tipo, "x": texto}]."""
    if not _dir:
        return []
    try:
        with open(_path(d), encoding="utf-8") as f:
            out = []
            for line in f:
                try:
                    e = json.loads(line)
                    if isinstance(e, dict) and e.get("x"):
                        out.append(e)
                except ValueError:
                    continue
            return out
    except OSError:
        return []


def days(d1, d2):
    out, d = [], d1
    while d <= d2:
        out += [dict(e, d=d.isoformat()) for e in day(d)]
        d += datetime.timedelta(days=1)
    return out


def purge(today=None):
    """Borra los días más viejos que keep_days."""
    if not _dir or not os.path.isdir(_dir):
        return 0
    limit = (today or datetime.date.today()) - datetime.timedelta(days=keep_days)
    n = 0
    for name in os.listdir(_dir):
        m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.jsonl", name)
        if m and datetime.date.fromisoformat(m.group(1)) < limit:
            try:
                os.remove(os.path.join(_dir, name))
                n += 1
            except OSError:
                pass
    return n


def clear():
    if not _dir or not os.path.isdir(_dir):
        return
    for name in os.listdir(_dir):
        if name.endswith(".jsonl"):
            try:
                os.remove(os.path.join(_dir, name))
            except OSError:
                pass


def stats(entries):
    c = {}
    for e in entries:
        c[e.get("k", "orden")] = c.get(e.get("k", "orden"), 0) + 1
    return c


_SINGULAR = {"órdenes": "orden", "rutinas": "rutina", "temporizadores": "temporizador", "recordatorios": "recordatorio",
             "notas": "nota", "avisos": "aviso", "habilidades": "habilidad", "búsquedas": "búsqueda", "preguntas": "pregunta",
             "tareas programadas": "tarea programada"}


def _plural(n, word):
    return f"{n} {word if n != 1 else _SINGULAR.get(word, word)}"


def spoken(entries, label="hoy"):
    """Resumen sin IA: cuántas cosas y cuáles destacan."""
    if not entries:
        return f"No tengo nada anotado de {label}."
    c = stats(entries)
    parts = []
    for k in ("orden", "pregunta", "rutina", "temporizador", "recordatorio", "nota", "habilidad", "aviso"):
        if c.get(k):
            parts.append(_plural(c[k], KINDS[k]))
    rut = [e["x"] for e in entries if e.get("k") == "rutina"]
    first, last = entries[0].get("t", ""), entries[-1].get("t", "")
    txt = f"{label.capitalize()}: " + ", ".join(parts) + (f", entre las {first} y las {last}" if first and last and first != last else "") + "."
    if rut:
        names = list(dict.fromkeys(rut))[:3]
        txt += " Rutinas: " + ", ".join(names) + "."
    return txt


def prompt(entries, label="ayer"):
    """Texto para que la IA haga un resumen humano."""
    lines = [f"{e.get('d', '')} {e.get('t', '')} [{e.get('k', '')}] {e.get('x', '')}".strip() for e in entries[-250:]]
    return (f"Este es el registro de lo que hice con mi asistente {label}. Hazme un resumen hablado, breve "
            "(4 a 6 frases), cálido y útil: qué hice, lo más importante, y si queda algo pendiente que deba "
            "recordar. No leas horas una por una ni repitas la lista.\n\n" + "\n".join(lines))


def today_context(max_items=8, now=None):
    """Para la IA: lo que el usuario ha estado haciendo hoy (lo más reciente)."""
    items = day((now or datetime.datetime.now()).date())
    items = [e for e in items if e.get("k") in ("orden", "rutina", "pregunta", "habilidad")][-max_items:]
    if not items:
        return ""
    return " Lo que el usuario ha hecho hoy contigo (lo más reciente): " + "; ".join(
        f"{e['t']} {e['x']}" for e in items) + "."
