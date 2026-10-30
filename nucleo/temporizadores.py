"""Temporizadores, alarmas e informe de la mañana.

Parte de Jarvis (antes dentro de jarvis.py). Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import diario
import os
import re
import schedule
import skills
import threading
import time

from nucleo import J


# =============================================================================
# TEMPORIZADORES DE CLASE (cuenta regresiva visible en el HUD)
# =============================================================================
timers = {}                       # id -> {"label", "end", "total"}
timers_lock = threading.Lock()
_timer_seq = 0


def _spoken_duration(seconds):
    m, s = divmod(int(round(seconds)), 60)
    h, m = divmod(m, 60)
    partes = []
    if h:
        partes.append(f"{h} hora" + ("s" if h != 1 else ""))
    if m:
        partes.append(f"{m} minuto" + ("s" if m != 1 else ""))
    if s and not h:
        partes.append(f"{s} segundo" + ("s" if s != 1 else ""))
    return " y ".join(partes) or "0 segundos"


def parse_duration(t):
    """Extrae segundos de «de/por/en 15 minutos», «media hora», «hora y media»."""
    if re.search(r"\b(?:una )?hora y media\b", t):
        return 5400
    if re.search(r"\bmedia hora\b", t):
        return 1800
    total = 0
    found = False
    for m in re.finditer(rf"(\d+|{J._NUM_ALT})\s*(segundos?|minutos?|horas?)", t):
        raw = m.group(1)
        qty = int(raw) if raw.isdigit() else J.NUM_WORDS.get(raw, 0)
        total += qty * J._UNIT_SECONDS[m.group(2)[:3]]
        found = True
    return total if found else None


def _timers_snapshot():
    now = time.time()
    with J.timers_lock:
        return [{"id": i, "label": d["label"], "total": d["total"],
                 "remaining": max(0, round(d["end"] - now))}
                for i, d in sorted(J.timers.items(), key=lambda kv: kv[1]["end"])]


def _emit_timers():
    J.socketio.emit("timers", {"timers": J._timers_snapshot()})


def add_timer(seconds, label=""):
    J._timer_seq += 1
    tid = J._timer_seq
    with J.timers_lock:
        J.timers[tid] = {"label": label.strip(), "end": time.time() + seconds, "total": seconds}
    J._emit_timers()
    diario.log("temporizador", f"{J._spoken_duration(seconds)}" + (f" para {label.strip()}" if label.strip() else ""))
    return tid


def cancel_timers(label=""):
    label = J.normalize(label)
    with J.timers_lock:
        if not label or label in ("todos", "todo", "el temporizador", "los temporizadores"):
            n = len(J.timers)
            J.timers.clear()
        else:
            ids = [i for i, d in J.timers.items() if label in J.normalize(d["label"])]
            for i in ids:
                del J.timers[i]
            n = len(ids)
    J._emit_timers()
    return n


def _timers_worker():
    while True:
        time.sleep(1)
        now = time.time()
        due = []
        with J.timers_lock:
            for i, d in list(J.timers.items()):
                if d["end"] <= now:
                    due.append(d)
                    del J.timers[i]
        if due:
            J._emit_timers()
        for d in due:
            J.hud_show()
            J.play_sound(J.resolve_alarm_sound())
            lbl = f" de {d['label']}" if d["label"] else ""
            J.alert(f"¡Tiempo{lbl}! Terminó el temporizador de {J._spoken_duration(d['total'])}.", "TIMER")
        if J.timers:
            J._emit_timers()        # refresca la cuenta regresiva cada segundo mientras haya alguno


def send_whatsapp_message(phone, message):
    """Abre WhatsApp Web en el navegador y envía el mensaje (requiere sesión iniciada)."""
    try:
        J.log_terminal(f"Enviando mensaje a {phone}...", "WHATSAPP")
        skills.send_whatsapp(phone, message)
        J.reply("Mensaje de WhatsApp enviado.", "WHATSAPP")
    except Exception as e:
        J.log_terminal(f"Error al enviar mensaje por WhatsApp: {e}", "ERROR")


STEAM_DEFAULT = {
    "ciencia": "Fundamentos teóricos y fenómenos observables relacionados.",
    "tecnologia": "Herramientas digitales, sensores y software integrados.",
    "ingenieria": "Proceso de diseño, prototipado y resolución de problemas técnicos.",
    "arte": "Diseño estético, visualización conceptual y ergonomía.",
    "matematicas": "Modelos cuantitativos, fórmulas y análisis estadístico.",
}
STEAM_SECTIONS = [
    ("1. Ciencia (Science)", "ciencia"),
    ("2. Tecnología (Technology)", "tecnologia"),
    ("3. Ingeniería (Engineering)", "ingenieria"),
    ("4. Arte (Arts)", "arte"),
    ("5. Matemáticas (Mathematics)", "matematicas"),
]


def _steam_content(topic):
    if not J.settings["steam_use_ai"]:
        return J.STEAM_DEFAULT
    prompt = (
        f"Escribe el contenido de un proyecto educativo STEAM sobre '{topic}'. "
        "Responde SOLO con un objeto JSON con las claves ciencia, tecnologia, "
        "ingenieria, arte y matematicas. Cada valor es un párrafo de 2 a 4 "
        "oraciones en español, concreto y aplicable en el aula."
    )
    try:
        data = J._extract_json(J.ai_chat([{"role": "user", "content": prompt}], json_mode=True))
        return {k: (str(data.get(k) or "").strip() or v) for k, v in J.STEAM_DEFAULT.items()}
    except Exception as e:
        J.log_terminal(f"La IA no pudo redactar el contenido, uso la plantilla base: {e}", "AVISO")
        return J.STEAM_DEFAULT


def generate_steam_doc(topic):
    if J.Document is None:
        J.reply("No puedo crear documentos: falta instalar python-docx.", "ERROR")
        return
    J.reply(f"Generando el documento STEAM sobre {topic}.", "OFFICE")
    content = J._steam_content(topic)
    doc = J.Document()
    doc.add_heading(f"Proyecto Educativo STEAM: {topic}", level=0)
    doc.add_paragraph(f"Generado por Jarvis el {J.fecha_hablada(datetime.date.today())}.")
    for heading, key in J.STEAM_SECTIONS:
        doc.add_heading(heading, level=1)
        doc.add_paragraph(content[key])
    out_dir = J.settings["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    slug = re.sub(r"[^\w]+", "_", J.normalize(topic)).strip("_")[:40] or "general"
    path = os.path.join(out_dir, f"STEAM_{slug}_{datetime.datetime.now():%Y%m%d_%H%M}.docx")
    doc.save(path)
    J.log_terminal(f"Documento guardado en: {path}", "OFFICE")
    J.push_chat("jarvis", f"Documento listo: {os.path.basename(path)}", "OFFICE")
    J.speak("El documento de planificación STEAM está listo en tu carpeta de salida.")


def calculate_life_path_number(day, month, year):
    def reduce_sum(n):
        while n > 9 and n not in (11, 22, 33, 44):
            n = sum(int(d) for d in str(n))
        return n

    total = reduce_sum(reduce_sum(day) + reduce_sum(month) + reduce_sum(year))
    meanings = {
        1: "Liderazgo, individualidad, ambición e iniciativa.",
        2: "Diplomacia, cooperación, sensibilidad y empatía.",
        3: "Creatividad, autoexpresión, optimismo y comunicación.",
        4: "Disciplina, trabajo estructurado, constancia y método.",
        5: "Libertad, versatilidad, aventura y adaptabilidad.",
        6: "Responsabilidad, protección, familia y armonía comunitaria.",
        7: "Introspección, análisis intelectual, búsqueda mística.",
        8: "Poder material, gestión ejecutiva, éxito financiero.",
        9: "Humanitarismo, altruismo, vocación universal.",
        11: "Número Maestro: alta intuición, inspiración e iluminación.",
        22: "Número Maestro: el gran constructor, materialización de grandes obras.",
        33: "Número Maestro: amor universal incondicional y guía espiritual.",
        44: "Número Maestro: gran capacidad de resolución y perseverancia material.",
    }
    return total, meanings.get(total, "Vibración numérica singular.")


def morning_report():
    hoy = J.fecha_hablada(datetime.date.today())
    hora = datetime.datetime.now().strftime("%H:%M")
    ia = "operativo" if J.check_ai() else "sin conexión o sin modelo; revisa los ajustes"
    saludo = f"Buenos días, {J.settings['address_name'].strip()}." if J.settings["address_name"].strip() else "Buenos días."
    J.reply(f"{saludo} Hoy es {hoy}, son las {hora}. El modelo de inteligencia artificial está {ia}.", "RUTINA")
    if J.settings["morning_weather"] and J.settings["weather_city"].strip():
        J.reply(J.weather_text(), "CLIMA")
    J.notes_today_summary(speak_it=True)
    if J.settings["morning_news"]:
        J.reply(J.news_text(), "NOTICIAS")
    if J.settings["telegram_alerts"] and J.settings["telegram_remote"]:
        resumen = [f"☀️ Buenos días. Hoy es {hoy}."]
        if J.settings["weather_city"].strip():
            resumen.append(J.weather_text())
        lines = J.agenda("hoy") if "agenda" in vars(J) else []
        if lines:
            resumen.append("Hoy tienes: " + "; ".join(lines[:8]) + ".")
        threading.Thread(target=J.telegram_send, args=("\n\n".join(resumen),), daemon=True).start()


def reschedule():
    schedule.clear("morning")
    if J.settings["morning_enabled"]:
        schedule.every().day.at(J.settings["morning_time"]).do(J.morning_report).tag("morning")


def schedule_worker():
    while True:
        schedule.run_pending()
        time.sleep(15)


__all__ = [
    'STEAM_DEFAULT',
    'STEAM_SECTIONS',
    '_emit_timers',
    '_spoken_duration',
    '_steam_content',
    '_timer_seq',
    '_timers_snapshot',
    '_timers_worker',
    'add_timer',
    'calculate_life_path_number',
    'cancel_timers',
    'generate_steam_doc',
    'morning_report',
    'parse_duration',
    'reschedule',
    'schedule_worker',
    'send_whatsapp_message',
    'timers',
    'timers_lock',
]
