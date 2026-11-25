"""12.55: Jarvis más rápido y avisos al celular cuando no estás frente al computador.

  · Frases ya entendidas: cuando la IA traduce una frase tuya a una orden de Jarvis y funciona, la guarda; la próxima vez
    esa misma frase va directo, sin preguntarle a la IA (de segundos a milisegundos). «olvida las frases aprendidas».
  · Respuestas al instante, sin la IA: «gracias», «buenas noches», «qué recordatorios tengo», «lee mis correos»,
    «cuántos perdieron en 9A», «habla más despacio / más rápido».
  · Avisos al celular cuando no estás: lo proactivo, lo que necesita tu atención y tus recordatorios llegan por Telegram
    (o WhatsApp) solo si llevas un rato sin usar el computador, con un tope al día y respetando las horas de silencio.
    «avísame al celular cuando no esté» · «no me mandes avisos al celular» · «¿qué me mandaste al celular hoy?»

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import json
import os
import random
import re
import threading
import time

import proactivo
from nucleo import J

# ============================================================================ FRASES YA ENTENDIDAS
R55_MEMO_MAX = 400
r55_memo = {"data": None}
_r55_lock = threading.Lock()


def _r55_memo_path():
    return os.path.join(J.CONFIG_DIR, "frases_entendidas.json")


def _r55_memo():
    if r55_memo["data"] is None:
        try:
            with open(J._r55_memo_path(), encoding="utf-8") as f:
                d = json.load(f)
            r55_memo["data"] = {str(k): v for k, v in d.items() if isinstance(v, dict) and v.get("orden")} if isinstance(d, dict) else {}
        except (OSError, ValueError):
            r55_memo["data"] = {}
    return r55_memo["data"]


def _r55_memo_save():
    try:
        os.makedirs(J.CONFIG_DIR, exist_ok=True)
        tmp = J._r55_memo_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(J._r55_memo(), f, ensure_ascii=False, indent=1)
        os.replace(tmp, J._r55_memo_path())
    except OSError as e:
        J.log_terminal(f"Frases entendidas: no pude guardar ({e}).", "AVISO")


def _r55_memo_on():
    return bool(J.settings.get("nl_memo", True)) and not J.priv.get("on")


def r55_memo_put(t, orden):
    """Guarda «frase → orden» cuando la traducción funcionó (nunca en modo privado ni para algo delicado)."""
    if not J._r55_memo_on() or not t or not orden or J.nl_risky(orden, t) or len(t) > 160:
        return
    with _r55_lock:
        d = J._r55_memo()
        d[t] = {"orden": str(orden)[:200], "n": int((d.get(t) or {}).get("n", 0)) + 1, "t": int(time.time())}
        if len(d) > R55_MEMO_MAX:                      # se quedan las más usadas y recientes
            for k in sorted(d, key=lambda k: (d[k].get("n", 0), d[k].get("t", 0)))[:len(d) - R55_MEMO_MAX]:
                d.pop(k, None)
        J._r55_memo_save()


def r55_memo_drop(t):
    with _r55_lock:
        if J._r55_memo().pop(t, None) is not None:
            J._r55_memo_save()


def r55_memo_try(text, t):
    """Si ya entendió esta frase antes, la hace directo. → True si quedó atendida."""
    if getattr(J._tl, "nl_pass", False) or not J._r55_memo_on():
        return False
    hit = J._r55_memo().get(t)
    if not hit:
        return False
    J._tl.nl_tried = t
    orden = hit["orden"]
    J.log_terminal(f"«{text.strip()}» ya la conocía: «{orden}» (sin preguntarle a la IA).", "COMPRENSIÓN")
    if J.nl_run(orden):
        with _r55_lock:
            hit.update(n=int(hit.get("n", 0)) + 1, t=int(time.time()))
        return True
    J.r55_memo_drop(t)                                 # ya no funciona (cambió algo): la olvida y sigue como siempre
    return False


_R55_FORGET = re.compile(r"^(?:olvida|borra)(?: todas)? (?:las )?frases (?:aprendidas|entendidas|que (?:aprendiste|entendiste))$")
_R55_COUNT = re.compile(r"^(?:cuantas|que) frases (?:has aprendido|aprendiste|entendiste|conoces ya|ya conoces)$")


# ============================================================================ RESPUESTAS AL INSTANTE (SIN LA IA)
_R55_THANKS = re.compile(r"^(?:ok |listo |perfecto |vale |bueno )?(?:muchas |mil )?gracias(?: jarvis| amigo| parcero| hermano| de verdad| por todo)?$|"
                         r"^(?:perfecto|excelente|listo|genial|super|chevere|bacano|muy bien)(?: jarvis)?(?: gracias)?$")
_R55_BYE = re.compile(r"^(?:buenas noches|hasta manana|chao|adios|hasta luego|nos vemos)(?: jarvis)?$")
_R55_THANKS_ANS = ("Con gusto.", "A la orden.", "Para eso estoy.", "Con mucho gusto.")
_R55_ALIASES = (
    (re.compile(r"^(?:que|cuales) (?:recordatorios|pendientes|alarmas) (?:tengo|hay|me quedan)$|^(?:mis|lee(?:me)? mis|dime mis) recordatorios$"),
     lambda m: "qué tengo pendiente"),
    (re.compile(r"^(?:lee(?:me)?|abre|mira) (?:mis|el|mi) (?:correos?|emails?|mails?)$|^revisa mis (?:correos|emails|mails)$|^mis correos$"),
     lambda m: "revisa mi correo"),
    (re.compile(r"^(?:cuanto|cuantos dias) (?:falta|faltan|queda|quedan) para (?:el )?(?:proximo |siguiente )?(?:puente|festivo|dia festivo|lunes festivo)(?: festivo)?$"),
     lambda m: "qué día cae el próximo festivo"),                                                     # 12.57
    (re.compile(r"^cuantos (?:estudiantes |alumnos |ninos |chicos )?(?:perdieron|pierden|van perdiendo|estan perdiendo|reprobaron|van mal)"
                r"(?: (?:en|de) (.+))?$"),
     lambda m: "quiénes van perdiendo" + (f" en {m.group(1)}" if m.group(1) else "")),
)
_R55_SLOWER = re.compile(r"^(?:habla(?:me)? )?(?:mas (?:despacio|lento|pausado)|un poco mas (?:despacio|lento))(?: por favor)?$|"
                         r"^(?:habla|hablame) (?:mas )?(?:despacio|lento)$|^estas hablando (?:muy )?rapido$")
_R55_FASTER = re.compile(r"^(?:habla(?:me)? )?(?:mas rapido|un poco mas rapido)(?: por favor)?$|^(?:habla|hablame) (?:mas )?rapido$|"
                         r"^estas hablando (?:muy )?(?:lento|despacio)$")


def _r55_rate(step):
    lo, hi = J.RANGES.get("tts_rate", (-50, 50))
    old = int(J.settings.get("tts_rate", 0))
    new = max(lo, min(hi, old + step))
    if new == old:
        J.reply("Ya estoy hablando lo más " + ("despacio" if step < 0 else "rápido") + " que puedo.", "VOZ")
        return
    J.settings["tts_rate"] = new
    J.save_settings_file()
    J.reply(("Hablo más despacio." if step < 0 else "Hablo más rápido.") + " Si quieres otro ajuste, dímelo de nuevo.", "VOZ")


def rapido55_voice(text, t):
    if _R55_FORGET.match(t):
        with _r55_lock:
            n = len(J._r55_memo())
            J._r55_memo().clear()
            J._r55_memo_save()
        J.reply(f"Listo, olvidé las {n} frases que ya entendía. Las volveré a aprender a medida que me hables." if n else
                "Todavía no tenía frases aprendidas.", "COMPRENSIÓN")
        return True
    if _R55_COUNT.match(t):
        n = len(J._r55_memo())
        J.reply(f"Ya entiendo al instante {n} frases tuyas que antes tenía que preguntarle a la IA." if n else
                "Todavía ninguna: cuando la IA me traduzca una frase tuya y funcione, la guardo para ir directo la próxima vez.", "COMPRENSIÓN")
        return True
    if _R55_SLOWER.match(t):
        J._r55_rate(-15)
        return True
    if _R55_FASTER.match(t):
        J._r55_rate(15)
        return True
    if _R55_THANKS.match(t):
        J.reply(random.choice(_R55_THANKS_ANS), "JARVIS")
        return True
    if _R55_BYE.match(t) and not J.rutinas.find(t):    # si tienes una rutina «buenas noches», manda ella
        name = J.settings["address_name"].strip()
        night = t.startswith(("buenas noches", "hasta manana"))
        J.reply(("Buenas noches" if night else "Hasta luego") + (f", {name}" if name else "") + (". Que descanses." if night else "."), "JARVIS")
        return True
    for rx, to in (() if getattr(J._tl, "nl_pass", False) else _R55_ALIASES):     # (una orden ya traducida no se vuelve a traducir)
        m = rx.match(t)
        if m:
            J.nl_run(to(m))
            return True
    if r55_away_voice(text, t):
        return True
    return False


# ============================================================================ AVISOS AL CELULAR CUANDO NO ESTÁS
r55_away = {"day": None, "n": 0, "sent": []}


def r55_phone_ready():
    return J.telegram_ready() or J.whatsapp_ready()


def r55_idle():
    """Segundos sin usarte: ni teclado ni ratón, ni hablarle o escribirle a Jarvis."""
    try:
        idle = float(J._idle_seconds())
    except Exception:
        idle = 0.0
    last = J._ag.get("last_user") or 0
    if last:
        idle = min(idle, max(0.0, time.time() - last))
    return idle


def r55_is_away():
    return J.r55_idle() >= int(J.settings["phone_away_min"]) * 60


def r55_away_send(text, important=False, now=None):
    """Manda el aviso al celular si no estás frente al computador. important (un recordatorio tuyo): sin tope ni silencio.
    → True si salió hacia el celular."""
    now = now or datetime.datetime.now()
    if not J.settings["phone_away"] or not J.r55_phone_ready() or not J.r55_is_away():
        return False
    if r55_away["day"] != now.date():
        r55_away.update(day=now.date(), n=0, sent=[])
    if not important:
        if r55_away["n"] >= int(J.settings["phone_away_max"]):
            return False
        if proactivo.in_quiet(now, J.settings.get("proactive_quiet", "")):
            return False
        r55_away["n"] += 1
    r55_away["sent"].append((now.strftime("%H:%M"), str(text)[:200]))
    threading.Thread(target=J.phone_send, args=(str(text),), daemon=True, name="aviso-celular").start()
    return True


_R55_AWAY_ON = re.compile(r"^(?:jarvis )?(?:avisame|escribeme|mandame (?:los )?avisos|manda(?:me)? lo importante) (?:al|por el|en el) (?:celular|telefono|movil|telegram|whatsapp)"
                          r"(?: cuando no (?:este|estoy)(?: (?:en|frente a)l? (?:computador|pc|equipo))?| si no estoy| cuando salga| lo importante)?$|"
                          r"^(?:activa|enciende|prende) (?:los )?avisos al (?:celular|telefono|movil)$")
_R55_AWAY_OFF = re.compile(r"^(?:jarvis )?(?:no me (?:mandes|envies|escribas)|deja de (?:mandarme|enviarme|escribirme)|ya no me mandes) "
                           r"(?:los )?(?:avisos|mensajes|nada)? ?(?:al|por el|en el) (?:celular|telefono|movil|telegram|whatsapp)$|"
                           r"^(?:desactiva|apaga|quita) (?:los )?avisos al (?:celular|telefono|movil)$")
_R55_AWAY_LIST = re.compile(r"^(?:que|cuales avisos) me (?:mandaste|enviaste|escribiste) al (?:celular|telefono|movil|telegram)(?: hoy)?$")


def r55_away_voice(text, t):
    if _R55_AWAY_ON.match(t):
        J.settings["phone_away"] = True
        J.save_settings_file()
        if not J.r55_phone_ready():
            J.reply("Listo, lo dejé activado, pero aún no tengo cómo llegarte al celular: conecta Telegram en Ajustes, "
                    "sección Cuentas y mensajes, y desde ahí te escribo.", "CELULAR")
            return True
        J.reply(f"Listo. Cuando lleves {J.settings['phone_away_min']} minutos sin usar el computador, te mando al celular "
                f"lo importante y tus recordatorios; como mucho {J.settings['phone_away_max']} avisos al día y nada en las horas de silencio. "
                "Si estás frente al computador, te aviso aquí.", "CELULAR")
        return True
    if _R55_AWAY_OFF.match(t):
        J.settings["phone_away"] = False
        J.save_settings_file()
        J.reply("Listo, ya no te mando avisos al celular cuando no estés. Te sigo avisando aquí en el computador.", "CELULAR")
        return True
    if _R55_AWAY_LIST.match(t):
        today = datetime.date.today()
        sent = r55_away["sent"] if r55_away["day"] == today else []
        if not sent:
            J.reply("Hoy no te he mandado nada al celular.", "CELULAR")
        else:
            J.reply(f"Hoy te mandé {len(sent)} al celular: " + "; ".join(f"a las {h}, {x}" for h, x in sent[-6:]) + ".", "CELULAR")
        return True
    return False


__all__ = ['R55_MEMO_MAX', '_R55_ALIASES', '_R55_AWAY_LIST', '_R55_AWAY_OFF', '_R55_AWAY_ON', '_R55_BYE', '_R55_COUNT', '_R55_FASTER',
           '_R55_FORGET', '_R55_SLOWER', '_R55_THANKS', '_R55_THANKS_ANS', '_r55_lock', '_r55_memo', '_r55_memo_on', '_r55_memo_path',
           '_r55_memo_save', '_r55_rate', 'r55_away', 'r55_away_send', 'r55_away_voice', 'r55_idle', 'r55_is_away', 'r55_memo',
           'r55_memo_drop', 'r55_memo_put', 'r55_memo_try', 'r55_phone_ready', 'rapido55_voice']
