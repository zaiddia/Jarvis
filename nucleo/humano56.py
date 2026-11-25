"""12.56: Jarvis más humano y más confiable.

  · Voz con emoción: con la voz de Gemini, el tono cambia según lo que dice (alegre, calmado, con ánimo, serio).
    «usa la voz con emoción» · «vuelve a la voz normal» · «pon la voz colombiana» · «voz de mujer» / «voz de hombre».
  · Voz colombiana por defecto (Gonzalo) en lugar de la de España (una sola vez; se puede cambiar).
  · Respuestas que suenan a persona: confirmaciones variadas y listas dichas como se hablan (humano.py).
  · Empatía: si lo que dices suena a cansancio, estrés, frustración, tristeza o alegría, la IA responde primero como
    persona y luego ayuda; con señales de crisis, con calidez y la Línea 106.
  · Respuestas verificadas: si la pregunta depende de datos que cambian (cargos, precios, resultados, «hoy»), Jarvis
    busca antes de responder y dice de dónde lo sacó, o que no lo pudo confirmar.

La lógica está en humano.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import re

import confianza
import humano
from nucleo import J

OLD_DEFAULT_VOICE = "es-ES-AlvaroNeural"
CO_VOICES = {"hombre": "es-CO-GonzaloNeural", "mujer": "es-CO-SalomeNeural"}
GEMINI_WARM = {"hombre": "Achird", "mujer": "Sulafat"}        # «Amigable» y «Cálida»


def hu56_migrate():
    """Una sola vez: quien tenía la voz de España que venía por defecto pasa a la colombiana."""
    s = J.settings
    if s.get("voice_co_done"):
        return False
    s["voice_co_done"] = True
    changed = s.get("tts_voice") == OLD_DEFAULT_VOICE
    if changed:
        s["tts_voice"] = CO_VOICES["hombre"]
    try:
        J.save_settings_file()
    except Exception:
        pass
    return changed


# ============================================================================ EN LAS INSTRUCCIONES DE LA IA
def human_ctx(prompt):
    """Lo que se añade a las instrucciones según cómo suena la persona (vacío si suena normal)."""
    if not J.settings.get("empathy", True):
        return ""
    return humano.mood_rule(prompt)


def facts_ctx(prompt):
    """Si la pregunta depende de datos que cambian, busca y devuelve el contexto con los resultados (vacío si no aplica)."""
    if not J.settings.get("verify_facts", True) or not humano.needs_check(prompt) or J.is_offline():
        return ""
    try:
        results = J._web_results(prompt)
    except Exception as e:
        J.log_terminal(f"Verificación: {e}", "AVISO")
        results = []
    txt = humano.facts_text(results)
    if not txt:
        return (" Para esta pregunta no se pudo buscar en internet: si depende de datos recientes, dilo con honestidad en vez "
                "de adivinar.")
    J.log_terminal(f"Verifiqué con {min(len(results), 5)} resultados de internet antes de responder.", "VERIFICAR")
    return humano.FACTS_RULE + confianza.RULE + "\n" + confianza.wrap(txt, "RESULTADOS DE INTERNET")


# ============================================================================ VOZ
_HU_EMO_ON = re.compile(r"^(?:jarvis )?(?:usa|pon|activa|quiero|cambia a) (?:la )?voz (?:con emocion|con emociones|expresiva|mas humana|mas natural|natural|de gemini)$|"
                        r"^(?:habla|hablame) (?:con (?:mas )?emocion|mas natural|como una persona|mas humano)$")
_HU_EMO_OFF = re.compile(r"^(?:jarvis )?(?:vuelve a|usa|pon) (?:la )?voz (?:normal|de siempre|anterior|rapida|sin emocion)$|^quita la voz con emocion$")
_HU_CO = re.compile(r"^(?:jarvis )?(?:pon|usa|cambia a|quiero) (?:la |una )?voz (?:colombiana|de colombia|paisa|rola|costena)$|^habla (?:como|en) colombiano$")
_HU_GENDER = re.compile(r"^(?:jarvis )?(?:pon|usa|cambia a|quiero) (?:la |una )?voz (?:de )?(mujer|femenina|hombre|masculina)$")


def _hu_voice_name():
    if J.settings["tts_backend"] == "gemini":
        return "la voz con emoción de Gemini"
    v = J.settings["tts_voice"]
    return next((label.split(" · ")[0] for code, label in J.SPANISH_VOICES if code == v), v)


def humano56_voice(text, t):
    if _HU_EMO_ON.match(t):
        if not J._gemini_for_stt():
            J.reply("Para hablar con emoción uso la voz de Gemini, y para eso necesito tu clave de Gemini en Ajustes, sección IA. "
                    "Mientras tanto sigo con la voz de siempre.", "VOZ")
            return True
        J.settings["tts_backend"] = "gemini"
        J.settings["tts_tone_auto"] = True
        J.save_settings_file()
        J.reply("Listo. Ahora hablo con la voz de Gemini y cambio el tono según lo que te digo: con alegría si es una buena "
                "noticia, con calma si es algo delicado. Si un día se agota el cupo gratis, vuelvo solo a la voz de siempre.", "VOZ")
        return True
    if _HU_EMO_OFF.match(t):
        J.settings["tts_backend"] = "edge"
        J.save_settings_file()
        J.reply(f"Listo, vuelvo a la voz de siempre ({_hu_voice_name()}).", "VOZ")
        return True
    m = _HU_GENDER.match(t)
    if m or _HU_CO.match(t):
        g = "mujer" if m and m.group(1) in ("mujer", "femenina") else "hombre" if m else (
            "mujer" if J.settings["tts_voice"] == CO_VOICES["mujer"] else "hombre")
        J.settings["tts_voice"] = CO_VOICES[g]
        if J.settings["tts_backend"] == "gemini":
            J.settings["gemini_tts_voice"] = GEMINI_WARM[g]
        J.save_settings_file()
        J.reply(f"¿Qué tal así? Ahora hablo con {_hu_voice_name()}.", "VOZ")
        return True
    return False


__all__ = ['CO_VOICES', 'GEMINI_WARM', 'OLD_DEFAULT_VOICE', '_HU_CO', '_HU_EMO_OFF', '_HU_EMO_ON', '_HU_GENDER', '_hu_voice_name',
           'facts_ctx', 'human_ctx', 'humano56_voice', 'hu56_migrate']
