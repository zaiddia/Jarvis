"""No molestar inteligente (12.16).

En clase (según tu horario o con la clase en vivo), en una videollamada (Zoom, Meet, Teams) o cuando lo pides
(«no me molestes por una hora»), los avisos no se dicen en voz alta: se guardan y te los cuenta al terminar.
Los medicamentos, las citas y las alarmas sí avisan, pero en silencio: en el HUD y en el celular.
"""
import datetime
import re
import threading
import time

import horario
from nucleo import J

dnd = {"until": 0.0, "queue": [], "was": "", "started": False}
CRITICAL = {"MEDICAMENTOS", "CITAS", "ALARMA", "SISMO", "TEMPORIZADOR", "RECORDATORIO"}
_CALL = re.compile(r"zoom (?:meeting|reunion|reunión)|reuni[oó]n de zoom|\bmeet\s*[-–]|google meet|microsoft teams.*(?:reuni[oó]n|meeting|llamada|call)|"
                   r"(?:reuni[oó]n|meeting|llamada|call).*microsoft teams|\bwebex\b|jitsi meet|whatsapp.*llamada", re.I)


def dnd_reason(now=None):
    """'no molestar', 'clase', 'videollamada' o ''."""
    now = now or datetime.datetime.now()
    if time.time() < dnd["until"]:
        return "no molestar"
    if not J.settings.get("dnd_auto", True):
        return ""
    try:
        if J.live_class.get("on") or horario.now_class(now):
            return "clase"
    except Exception:
        pass
    try:
        if _CALL.search(J._foreground_title() or ""):
            return "videollamada"
    except Exception:
        pass
    return ""


def dnd_status():
    r = dnd_reason()
    return {"motivo": r, "guardados": len(dnd["queue"]), "hasta": time.strftime("%H:%M", time.localtime(dnd["until"])) if r == "no molestar" else ""} if r else None


def dnd_intercept(text, origin):
    """Lo llama notify: True si el aviso se guardó o se mostró en silencio (no se dice en voz alta)."""
    r = dnd_reason()
    if not r:
        return False
    dnd["was"] = r
    J.log_terminal(text, origin)
    if origin in CRITICAL:
        J.push_chat("jarvis", text, origin)
        try:
            J.card("aviso", origin.capitalize(), text, "🔔", secs=25)
        except Exception:
            pass
        if J.settings.get("telegram_token") and J.settings.get("telegram_chat"):
            threading.Thread(target=J.telegram_send, args=("🔔 " + text,), daemon=True).start()
        return True
    dnd["queue"].append({"t": text, "o": origin, "h": time.strftime("%H:%M")})
    del dnd["queue"][:-40]
    return True


def dnd_flush(intro=None):
    q, dnd["queue"] = dnd["queue"], []
    if not q:
        return False
    head = intro or {"clase": "Mientras estabas en clase", "videollamada": "Mientras estabas en la videollamada"}.get(dnd["was"], "Mientras no te molesté")
    items = [x["t"] for x in q]
    msg = f"{head}: " + " ".join(items[:5]) + (f" Y {len(items) - 5} avisos más en el registro." if len(items) > 5 else "")
    J.reply(msg, "AVISOS")
    return True


def _dnd_worker():
    while True:
        try:
            if dnd["queue"] and not dnd_reason():
                time.sleep(4)                                  # que termine de salir de la llamada o de la clase
                if not dnd_reason():
                    dnd_flush()
        except Exception as e:
            J.note_error("NO MOLESTAR", e)
        time.sleep(20)


def dnd_start():
    if not dnd["started"]:
        dnd["started"] = True
        threading.Thread(target=_dnd_worker, daemon=True, name="no-molestar").start()


_DND_ON = re.compile(r"\bno me molestes(?:\s+(?:por|durante)\s+(?:(\d+|una|un|media|dos|tres)\s+(hora|horas|minutos?))|\s+hasta\s+las\s+(.+))?\b|"
                     r"\b(?:activa|pon|enciende)\s+(?:el\s+)?(?:modo\s+)?no molestar\b|^(?:jarvis\s+)?modo no molestar$")
_DND_OFF = re.compile(r"\bya (?:puedes|me puedes) (?:hablar|molestar|avisar)\b|\b(?:desactiva|quita|apaga)\s+(?:el\s+)?(?:modo\s+)?no molestar\b")
_DND_WHAT = re.compile(r"\bque (?:me perdi|avisos me perdi|paso mientras)\b|\b(?:dime|lee(?:me)?) los avisos (?:guardados|pendientes)\b")


def dnd_voice(text, t):
    m = _DND_ON.search(t)
    if m:
        mins = 60
        if m.group(1):
            n = {"una": 1, "un": 1, "media": 0.5, "dos": 2, "tres": 3}.get(m.group(1)) or float(m.group(1))
            mins = n * 60 if m.group(2).startswith("hora") else n
        elif m.group(3):
            import hogar
            hh = hogar.parse_time("a las " + m.group(3))
            if hh:
                now = datetime.datetime.now()
                end = now.replace(hour=int(hh[:2]), minute=int(hh[3:]), second=0)
                if end <= now:
                    end += datetime.timedelta(days=1)
                mins = (end - now).total_seconds() / 60
        dnd["until"] = time.time() + mins * 60
        J.reply(f"Listo: no te hablo hasta las {time.strftime('%H:%M', time.localtime(dnd['until']))}. Guardo los avisos y te los cuento después; "
                "los medicamentos y las alarmas te llegan en silencio. Di «ya puedes hablar» para terminar antes.", "AVISOS")
        return True
    if _DND_OFF.search(t):
        dnd["until"] = 0.0
        if not dnd_flush("Esto llegó mientras tanto"):
            J.reply("Listo, ya te puedo avisar.", "AVISOS")
        return True
    if _DND_WHAT.search(t):
        if not dnd_flush("Lo que te perdiste"):
            J.reply("No te perdiste nada.", "AVISOS")
        return True
    return False


__all__ = ['CRITICAL', '_CALL', '_DND_OFF', '_DND_ON', '_DND_WHAT', '_dnd_worker', 'dnd', 'dnd_flush', 'dnd_intercept', 'dnd_reason', 'dnd_start',
           'dnd_status', 'dnd_voice']
