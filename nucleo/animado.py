"""9.9: personalidad según el momento (clase, jornada, tiempo libre), color del día del reactor y retrospectiva del año.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import re
import threading
import time

import animo
import aula
import banco
import clasevivo
import compromisos
import diarioclase
import horario
import informes
import lecciones
import proyectos
import retro
import seguimiento
from nucleo import J


# ============================================================================ PERSONALIDAD SEGÚN EL MOMENTO
persona = {"manual": "", "mode": "", "until": 0.0}


def persona_now(now=None):
    now = now or datetime.datetime.now()
    if persona["manual"] and time.time() < persona["until"]:
        return persona["manual"]
    persona["manual"] = ""
    if not J.settings["persona_auto"]:
        return ""
    return animo.auto_mode(now, bool(horario.now_class(now)), J.settings["attention_from"], J.settings["attention_to"])


def persona_ctx():
    if J.tutor["on"]:                                  # el modo tutor manda en clase
        return ""
    m = J.persona_now()
    if m != persona["mode"]:
        persona["mode"] = m
        try:
            J.socketio.emit("persona", {"mode": m, "label": animo.MODES[m][0] if m else ""})
        except Exception:
            pass
    return animo.MODES[m][1] if m else ""


_PERS_ASK = re.compile(r"\ben que (?:modo|personalidad) (?:estas|andas)\b|\bque personalidad tienes\b")


def persona_voice(text, t):
    if _PERS_ASK.search(t):
        m = J.persona_now()
        J.reply((f"Ahora estoy en modo {animo.MODES[m][0]}" if m else "Ahora no tengo una personalidad especial") +
                (" (lo pusiste tú)." if persona["manual"] else " (cambia solo con tu horario)." if J.settings["persona_auto"] else ".") +
                " Dime «ponte relajado», «ponte serio», «personalidad de clase» o «personalidad automática».", "PERSONALIDAD")
        return True
    m = animo.parse_set(t)
    if not m:
        return False
    if m == "auto":
        persona.update(manual="", until=0)
        J.settings["persona_auto"] = True
        J.reply("Listo: mi personalidad vuelve a cambiar sola: breve en clase, concentrado en la jornada y relajado en tu tiempo libre.",
                "PERSONALIDAD")
    else:
        persona.update(manual=m, until=time.time() + 3 * 3600)
        J.reply({"clase": "Modo clase: respuestas breves y claras para los estudiantes.",
                 "jornada": "Modo concentrado: voy al grano.",
                 "relajado": "Modo relajado activado. 😌 Sin afanes."}[m] + " Durante las próximas 3 horas.", "PERSONALIDAD")
    J.persona_ctx()
    return True


# ============================================================================ COLOR DEL DÍA
_mood = {"t": 0.0, "mood": "tranquilo", "why": ""}


def day_mood_now(force=False):
    if not J.settings["orb_day_color"]:
        return "tranquilo", ""
    if not force and time.time() - _mood["t"] < 60:
        return _mood["mood"], _mood["why"]
    try:
        items = J.attention_items()
    except Exception:
        items = []
    today = datetime.date.today().isoformat()
    cel = ""
    if J.settings.get("period_closed") == today:
        cel = "cerraste el periodo"
    else:
        pos = [x for c in informes.data.values() for es in c.values() for x in es if x.get("fecha") == today and x.get("tipo") == "positiva"]
        if pos:
            cel = f"{len(pos)} felicitación{'es' if len(pos) != 1 else ''} hoy"
    m, why = animo.day_mood(items, cel)
    if m != _mood["mood"]:
        try:
            J.socketio.emit("day_mood", {"mood": m, "why": why, "label": animo.LABELS[m]})
        except Exception:
            pass
    _mood.update(t=time.time(), mood=m, why=why)
    return m, why


def mood_accent():
    """El color del reactor para el orbe de la barra de tareas (hex)."""
    m, _ = J.day_mood_now()
    rgb = animo.MOODS.get(m)
    return animo.hexrgb(rgb) if rgb else "%02x%02x%02x" % J.THEMES.get(J.settings["theme"], J.THEMES["cyan"])[1]


@J.socketio.on("day_mood")
def handle_day_mood(data=None):
    m, why = J.day_mood_now()
    pm = J.persona_now()
    return {"mood": m, "why": why, "label": animo.LABELS[m], "persona": animo.MODES[pm][0] if pm else ""}


_MOOD_ASK = re.compile(r"\bcomo (?:viene|va|pinta) (?:mi|el) dia\b|\bpor que (?:el reactor|estas|te pusiste) (?:esta )?(?:de )?(?:color )?"
                       r"(?:naranja|ambar|amarillo|rojo|coral|verde)\b")


def mood_voice(text, t):
    if not _MOOD_ASK.search(t):
        return False
    m, why = J.day_mood_now(force=True)
    J.reply({"tranquilo": "Viene un día tranquilo: todo en orden. 💙", "cargado": f"Viene un día cargado: {why}. Pregúntame «¿qué necesita "
             "mi atención?» y lo vemos por partes.", "urgente": f"Hay algo urgente: {why}.",
             "celebracion": f"¡Hoy es día de celebrar: {why}! 🎉"}[m], "JARVIS")
    return True


# ============================================================================ RETROSPECTIVA DEL AÑO
def year_stats(year=None):
    year = year or datetime.date.today().year
    try:
        hist = J.aprobaciones.history(days=366)
        appr = sum(1 for e in hist if e.get("evento") == "aprobada" and str(e.get("ts", ""))[:4] == str(year))
    except Exception:
        appr = 0
    return retro.compute(year, seguimiento.data, informes.data, diarioclase.data.get("registro", {}), proyectos.load_all(),
                         clasevivo.data.get("actividades", []), compromisos.data.get("items", []), len(lecciones.items), appr,
                         len(banco.items))


def year_retro(say=True):
    s = J.year_stats()
    carta = ""
    if J.state.get("ai") == "ok" and (s["n_temas"] or s["notas"]):
        try:
            carta = J.ai_chat([{"role": "user", "content": retro.letter_prompt(s, J.settings["address_name"])}],
                              max_tokens=600).strip()
        except Exception:
            carta = ""
    path = ""
    if J.Document is not None and (s["n_temas"] or s["notas"] or s["proyectos"]):
        path = retro.build_docx(s, J.settings["output_dir"], J.Document, carta, J.settings["aula_docente"], J.settings["aula_institucion"])
        J.generated_files.add(path)
        J._open_doc(path)
    if say:
        J.notify(retro.spoken(s) + (" Te dejé tu retrospectiva en Documentos, Jarvis, Retrospectiva." if path else ""), "RETROSPECTIVA")
    return s, path


_RETRO_RE = re.compile(r"\b(?:retrospectiva|resumen|balance)\s+(?:de mi |del |de este |mi )?(?:ano|año)(?: escolar)?\b|\bmi ano con jarvis\b|"
                       r"\bcomo me fue (?:este|en el) ano\b|\bmi (?:ano|año) en cifras\b")


def retro_voice(text, t):
    if not _RETRO_RE.search(t):
        return False
    J.reply("Repaso tu año…", "RETROSPECTIVA")
    if getattr(J._tl, "capture", None) is not None:
        J.year_retro()
    else:
        J.start_job("Preparando tu retrospectiva del año", J.year_retro, "retro")
    return True


def retro_tick(now=None):
    """A fin de año escolar (desde el 25 de noviembre, entre semana) propone una vez la retrospectiva."""
    now = now or datetime.datetime.now()
    if now.month != 12 and not (now.month == 11 and now.day >= 25) or now.weekday() >= 5 or not (9 <= now.hour < 18):
        return False
    if J.settings["retro_year"] == str(now.year):
        return False
    J.settings["retro_year"] = str(now.year)
    try:
        J.save_settings_file()
    except OSError:
        pass
    s = J.year_stats(now.year)
    if not (s["n_temas"] or s["notas"]):
        return False
    J.request_approval("retro", f"Tu retrospectiva de {now.year}", retro.spoken(s), on_ok=lambda: J.year_retro(), on_no=lambda: None,
                       ttl=7 * 24 * 3600, say=f"Se acaba el año escolar. ¿Te preparo tu retrospectiva de {now.year}, con lo que enseñaste, "
                                              "tus estudiantes que más avanzaron y lo que mejor funcionó? Di «sí» o «no».")
    return True


def _mood_worker():
    time.sleep(90)
    while True:
        try:
            J.day_mood_now(force=True)
            J.persona_ctx()
            J.retro_tick()
        except Exception as e:
            J.note_error("ÁNIMO", e)
        time.sleep(120)


def mood_start():
    threading.Thread(target=J._mood_worker, daemon=True, name="animo").start()


__all__ = ['_MOOD_ASK', '_PERS_ASK', '_RETRO_RE', '_mood', '_mood_worker', 'day_mood_now', 'handle_day_mood', 'mood_accent', 'mood_start',
           'mood_voice', 'persona', 'persona_ctx', 'persona_now', 'persona_voice', 'retro_tick', 'retro_voice', 'year_retro', 'year_stats']
