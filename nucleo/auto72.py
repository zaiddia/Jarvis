"""12.72: las funciones se encienden solas cuando las pides (sin ir a Ajustes).

  · Si pides algo que necesita una función apagada (el panel del celular para un QR, el diario, el historial, leer el correo…),
    Jarvis la enciende, lo dice en una frase y sigue con lo que pediste.
  · Por voz o escrito: «activa el turno de noche», «desactiva el copiloto», «avísame de los sismos», «enciende las noticias del
    reporte de la mañana», «¿qué funciones tengo apagadas?». Funciona con más de 60 funciones de Ajustes.
  · Lo que solo tú puedes poner (una clave, tu cuenta de Google, el token de Telegram) sigue en Ajustes: Jarvis te dice qué
    falta en una línea. Apagar la protección de datos de estudiantes o abrir Jarvis a otras IA pide tu «sí».
Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import os
import re
import time

from nucleo import J

# clave → (nombre para decirlo, palabras con que se pide)
FEATURES = {
    "mobile_enabled": ("el panel del celular", r"(?:el )?panel (?:del|en el|para el) celular|panel movil|panel del telefono"),
    "quake_alerts": ("los avisos de sismos", r"(?:los )?avisos? de (?:sismos|temblores|terremotos)|(?:los )?(?:sismos|temblores|terremotos)"),
    "morning_enabled": ("el reporte de la mañana", r"(?:el )?(?:reporte|resumen|informe) de la manana"),
    "morning_news": ("las noticias del reporte de la mañana", r"(?:las )?noticias (?:en|del|de) (?:el )?(?:reporte|resumen) de la manana|"
                                                              r"(?:las )?noticias de la manana"),
    "morning_weather": ("el clima del reporte de la mañana", r"(?:el )?clima (?:en|del) (?:el )?(?:reporte|resumen) de la manana"),
    "schedule_warn": ("el aviso antes de cada clase", r"(?:el )?aviso antes de (?:cada|mis|las) clases?"),
    "schedule_auto_course": ("el curso activo según el horario", r"(?:el )?curso activo (?:segun|por) (?:el )?horario"),
    "night_shift": ("el turno de noche", r"(?:el )?turno de noche"),
    "night_prep": ("la preparación de las clases en la noche", r"(?:la )?preparacion (?:de las clases )?(?:en|de) la noche"),
    "week_prep": ("la preparación de la semana", r"(?:la )?preparacion de la semana"),
    "inbox_drafts": ("los borradores de correo de la mañana", r"(?:los )?borradores de (?:los )?correos?"),
    "copilot_enabled": ("el copiloto", r"(?:el )?copiloto"),
    "copilot_speak": ("las sugerencias habladas del copiloto", r"(?:las )?sugerencias (?:habladas|en voz alta) del copiloto"),
    "drive_auto": ("subir el material a Drive", r"subir (?:todo )?(?:el |mi )?material a (?:mi )?drive|(?:la )?subida automatica a drive"),
    "drive_docente": ("el Drive docente", r"(?:el )?drive docente"),
    "windows_integration": ("la integración con Windows", r"(?:la )?integracion con windows|(?:el )?clic derecho"),
    "windows_toasts": ("las notificaciones de Windows", r"(?:las )?notificaciones de windows"),
    "hud_avatar": ("el rostro holográfico", r"(?:el )?(?:rostro|avatar|cara)(?: holografic[oa])?"),
    "hud_subtitles": ("los subtítulos del HUD", r"(?:los )?subtitulos(?: del hud)?"),
    "hud_cards": ("las tarjetas del HUD", r"(?:las )?tarjetas(?: holograficas| del hud)"),
    "hud_auto_hide": ("esconder el HUD en el borde", r"esconder el hud|(?:la )?pildora(?: del hud)?"),
    "diary_enabled": ("el diario", r"(?:el )?diario(?: de actividades)?"),
    "history_enabled": ("el historial de conversaciones", r"(?:el )?historial(?: de (?:las )?conversaciones)?"),
    "learn_enabled": ("aprender tus costumbres", r"aprender (?:mis|de mis) costumbres|(?:el )?aprendizaje de (?:mis )?costumbres"),
    "email_read": ("leer tu correo", r"leer (?:mi|el) correo|(?:la )?lectura (?:de|del) correo"),
    "proactive_enabled": ("los avisos proactivos", r"(?:los )?avisos proactivos|(?:lo )?proactivo"),
    "proactive_breaks": ("los recordatorios de pausas", r"(?:los )?recordatorios? de pausas?|(?:las )?pausas activas"),
    "proactive_rain": ("el aviso de lluvia", r"(?:el )?aviso de (?:lluvia|paraguas)"),
    "proactive_greeting": ("el saludo del día", r"(?:el )?saludo (?:del dia|de la manana)"),
    "battery_alerts": ("los avisos de batería", r"(?:los )?avisos? de (?:la )?bateria"),
    "weekly_summary": ("el resumen semanal", r"(?:el )?resumen (?:semanal|de la semana)"),
    "risk_alerts": ("el resumen de estudiantes en riesgo", r"(?:el )?resumen de (?:estudiantes en )?riesgo"),
    "early_alerts": ("las alertas tempranas", r"(?:las )?alertas tempranas"),
    "docente_friday": ("el resumen docente del viernes", r"(?:el )?resumen docente(?: del viernes)?"),
    "auto_backup": ("el respaldo de notas de los viernes", r"(?:el )?respaldo (?:de (?:las )?notas|semanal)"),
    "backup_auto": ("la copia de seguridad semanal", r"(?:la )?copia de seguridad(?: semanal| automatica)?"),
    "backup_drive": ("subir las copias a Drive", r"(?:subir )?(?:las )?copias a (?:mi )?drive"),
    "cloud_nightly": ("la copia cifrada de cada noche", r"(?:la )?copia (?:cifrada|de cada noche|nocturna)"),
    "telegram_remote": ("las órdenes por Telegram", r"(?:las )?ordenes (?:por|desde) telegram|(?:el )?control por telegram"),
    "telegram_alerts": ("los avisos por Telegram", r"(?:los )?avisos (?:por|a) telegram"),
    "whatsapp_alerts": ("los avisos por WhatsApp", r"(?:los )?avisos (?:por|a) whatsapp"),
    "attention_pulse": ("el pulso de atención", r"(?:el )?pulso de atencion"),
    "attention_weekend": ("el pulso de atención los fines de semana", r"(?:el )?pulso de atencion (?:los|el) fines? de semana"),
    "attention_phone": ("el pulso de atención al celular", r"(?:el )?pulso de atencion (?:al|en el) celular"),
    "phone_away": ("los avisos al celular cuando no estás", r"(?:los )?avisos al celular cuando no estoy"),
    "dnd_auto": ("el no molestar automático", r"(?:el )?no molestar automatico"),
    "startup_announce": ("el saludo al arrancar", r"(?:el )?saludo al (?:arrancar|iniciar|prender)"),
    "barge_in": ("interrumpirte mientras hablas", r"(?:poder )?interrumpirte"),
    "wake_word_enabled": ("la palabra de activación", r"(?:la )?palabra de activacion"),
    "persona_auto": ("la personalidad según el momento", r"(?:la )?personalidad (?:segun|por) el momento"),
    "orb_day_color": ("el color del reactor según el día", r"(?:el )?color del reactor"),
    "empathy": ("notar cómo estás", r"notar como estoy|(?:la )?empatia"),
    "verify_facts": ("confirmar los datos en internet", r"confirmar (?:los )?datos(?: en internet)?|(?:la )?verificacion de datos"),
    "instant_answers": ("las respuestas instantáneas", r"(?:las )?respuestas instantaneas"),
    "ack_enabled": ("las frases de espera", r"(?:las )?frases de espera"),
    "ack_still": ("el «sigo en eso»", r"(?:el )?sigo en eso"),
    "smart_tools": ("los datos exactos", r"(?:los )?datos exactos"),
    "smart_think": ("pensar más en lo difícil", r"pensar mas(?: en lo dificil)?"),
    "smart_review": ("la doble revisión", r"(?:la )?doble revision"),
    "smart_visual": ("mostrar gráficas y simulaciones", r"mostrar (?:las )?graficas(?: y simulaciones)?"),
    "smart_weekly": ("el autoexamen semanal", r"(?:el )?autoexamen(?: semanal)?"),
    "phrase_tips": ("los consejos de frases", r"(?:los )?consejos de frases"),
    "skill_of_day": ("la habilidad del día", r"(?:la )?habilidad del dia"),
    "live_search": ("buscar en internet en la conversación en vivo", r"buscar en internet en vivo"),
    "update_auto": ("buscar actualizaciones", r"buscar actualizaciones|(?:las )?actualizaciones automaticas"),
    "update_night": ("instalar actualizaciones de noche", r"(?:instalar )?(?:las )?actualizaciones de noche"),
    "protect_students": ("la protección de los datos de estudiantes", r"(?:la )?proteccion de (?:los )?datos de (?:los )?estudiantes|"
                                                                       r"(?:el )?cifrado de (?:las )?notas"),
    "privacy_students": ("ocultar los nombres de los estudiantes a la nube", r"ocultar (?:los )?nombres(?: de los estudiantes)?"),
    "mcp_server_enabled": ("dejar que otras IA usen Jarvis", r"(?:el )?servidor mcp|que otras ia usen jarvis"),
}
CONFIRM_OFF = {"protect_students", "privacy_students"}       # apagar esto pide tu «sí»
CONFIRM_ON = {"mcp_server_enabled"}                          # encender esto pide tu «sí»
OWN = {"night_shift", "copilot_enabled", "morning_enabled", "week_prep", "night_prep"}   # ya tenían su propia orden
IMPLIED = {"mobile_enabled", "diary_enabled", "history_enabled", "email_read", "quake_alerts"}   # se encienden solas al pedir algo
_said = {}
MOBILE_AUTO = os.environ.get("JARVIS_PRUEBAS") != "1"      # en las pruebas no se abre un servidor de verdad


def feature_missing(key):
    """Lo que solo tú puedes poner para que la función sirva ("" si nada)."""
    s = J.settings
    if key in ("telegram_remote", "telegram_alerts") and not (s.get("telegram_token", "").strip() and s.get("telegram_chat", "").strip()):
        return "conectar Telegram (el token de tu bot) en Ajustes › Cuentas y mensajes"
    if key == "whatsapp_alerts" and not (s.get("whatsapp_phone") and s.get("whatsapp_apikey")):
        return "tu número y la clave de CallMeBot en Ajustes › Cuentas y mensajes › WhatsApp"
    if key == "cloud_nightly" and not s.get("cloud_pass"):
        return "la clave de las copias en Ajustes › Datos y copias (y tu cuenta de Google conectada)"
    if key in ("drive_auto", "drive_docente", "backup_drive"):
        try:
            if not J.gdrive_ready():
                return "conectar tu cuenta de Google en Ajustes › Cuentas y mensajes"
        except Exception:
            pass
    if key == "email_read":
        try:
            if not J._mail_ready():
                return "tu correo y la contraseña de aplicación en Ajustes › Cuentas y mensajes › Correo"
        except Exception:
            pass
    return ""


def feature_set(key, on):
    """Enciende o apaga con los mismos efectos que el botón de Ajustes. → errores"""
    return J.apply_settings({key: bool(on)})


def feature_on(key, quiet=False):
    """Para lo que pediste: si la función está apagada (y se puede), la enciende y lo dice. → True si quedó encendida."""
    if J.settings.get(key):
        return True
    if key not in IMPLIED:
        return False
    errs = feature_set(key, True)
    if errs or not J.settings.get(key):
        return False
    J.log_terminal(f"Encendí {FEATURES[key][0]} porque lo pediste.", "AJUSTES")
    if not quiet and time.time() - _said.get(key, 0) > 60:
        _said[key] = time.time()
        J.reply(f"Encendí {FEATURES[key][0]} para esto; si no lo quieres, di «desactiva {FEATURES[key][0]}».", "AJUSTES")
    return True


def mobile_on():
    """El panel del celular encendido y escuchando. → True si quedó listo."""
    if J.mobile.get("server"):
        return True
    if not J.MOBILE_AUTO or not feature_on("mobile_enabled", quiet=True):
        return False
    if not J.mobile.get("server"):
        J.mobile_apply()                                # por si el hilo de Ajustes aún no lo abre
    for _ in range(30):
        if J.mobile.get("server"):
            break
        time.sleep(0.1)
    if J.mobile.get("server"):
        J.reply("Encendí el panel del celular: los celulares deben estar en la misma wifi que este computador.", "AJUSTES")
        return True
    return False


_ON = r"(?:activa(?:me)?|enciende(?:me)?|prende(?:me)?|habilita(?:me)?|pon(?:me)?|vuelve a (?:activar|encender|poner)|quiero)"
_OFF = r"(?:desactiva(?:me)?|apaga(?:me)?|deshabilita(?:me)?|quita(?:me)?|ya no quiero|no quiero)"
_A72_SET = re.compile(rf"^(?:jarvis\s+)?(?:(?P<on>{_ON})|(?P<off>{_OFF}))\s+(?P<what>.+?)$")
_A72_WARN = re.compile(r"^(?:jarvis\s+)?(?P<off>no )?(?:me )?avis(?:a|ame|arme|es) (?:de|cuando haya|si hay) (?P<what>(?:los )?(?:sismos|temblores|terremotos))$")
_A72_LIST = re.compile(r"^(?:jarvis\s+)?(?:que|cuales) funciones (?:tengo|estan|hay) (?:apagadas|desactivadas)$")


def feature_find(what):
    w = re.sub(r"^(?:el|la|los|las|lo)\s+", "", J.normalize(what)).strip()
    for key, (name, rx) in FEATURES.items():
        if re.fullmatch(rf"(?:el |la |los |las |lo )?(?:{rx})", w) or J.normalize(name) == J.normalize(what):
            return key
    return ""


def auto72_voice(text, t):
    if _A72_LIST.match(t):
        off = [FEATURES[k][0] for k in FEATURES if not J.settings.get(k) and k not in CONFIRM_ON]
        J.reply(("Tienes apagadas: " + ", ".join(off[:14]) + ("…" if len(off) > 14 else "") + ". Enciende cualquiera con «activa …»."
                 if off else "Tienes todo encendido."), "AJUSTES")
        return True
    m = _A72_SET.match(t) or _A72_WARN.match(t)
    if not m:
        return False
    key = feature_find(m.group("what"))
    if not key:
        return False
    on = not m.group("off")
    name = FEATURES[key][0]
    if bool(J.settings.get(key)) == on:
        J.reply(f"Eso ya está {'encendido' if on else 'apagado'}: {name}.", "AJUSTES")
        return True

    def go():
        errs = feature_set(key, on)
        if errs:
            J.reply(f"No pude cambiarlo: {errs[0]}.", "AJUSTES")
            return
        miss = feature_missing(key) if on else ""
        J.reply(f"Listo: {'encendí' if on else 'apagué'} {name}." + (f" Para que funcione falta {miss}." if miss else ""), "AJUSTES")
    if (on and key in CONFIRM_ON) or (not on and key in CONFIRM_OFF):
        J.request_approval("ajuste", f"{'Encender' if on else 'Apagar'} {name}", "Es un ajuste de seguridad.", on_ok=go,
                           on_no=lambda: J.reply("Vale, lo dejo como estaba.", "AJUSTES"), ttl=600,
                           say=f"¿Seguro que quieres {'encender' if on else 'apagar'} {name}? Di «sí» o «no».")
        return True
    go()
    return True


def auto72_early(text, t):
    """Antes que las demás reglas: «avísame de los sismos» (si no, parece un recordatorio) y «¿qué funciones tengo apagadas?»."""
    if _A72_WARN.match(t) or _A72_LIST.match(t):
        return auto72_voice(text, t)
    m = _A72_SET.match(t)
    if m and feature_find(m.group("what")) not in ("", *OWN):     # las que tienen su propia orden (más completa) van después
        return auto72_voice(text, t)
    return False


AUTO_RULE = (" Si el usuario pide una función de Jarvis que está apagada, no lo mandes a Ajustes: dile la orden para encenderla, por "
             "ejemplo «activa el turno de noche» o «activa los avisos de sismos» (Jarvis las enciende al instante). Solo manda a Ajustes "
             "lo que únicamente él puede poner: claves, cuentas, contraseñas o tokens.")


__all__ = ['MOBILE_AUTO', 'OWN', 'auto72_early', 'AUTO_RULE', 'CONFIRM_OFF', 'CONFIRM_ON', 'FEATURES', 'IMPLIED', '_A72_LIST', '_A72_SET', '_A72_WARN', '_said', 'auto72_voice',
           'feature_find', 'feature_missing', 'feature_on', 'feature_set', 'mobile_on']
