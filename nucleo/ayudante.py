"""12.26: Jarvis aprende de sus fallos y te enseña lo que sabe hacer.

  · «No era eso» (botón en cada respuesta del HUD): guarda en tu equipo la frase, quién la atendió y lo que respondió,
    en fallos.jsonl. Nada sale de tu PC; lo compartes tú si quieres que se corrija («abre el registro de fallos»).
  · Frase directa: si la IA tuvo que adivinar una orden y hay una habilidad con un ejemplo muy parecido, una vez al día
    te deja una tarjeta con la frase que va directo.
  · Habilidad del día: una línea en el resumen de la mañana con algo que aún no te ha mostrado (en modo general, nada
    del colegio).
"""
import datetime
import json
import os
import re
import threading
import time

import guia
from nucleo import J

FALLOS_MAX = 2000                     # líneas que se guardan como mucho (las más viejas se van)


def fallos_path():
    return os.path.join(J.CONFIG_DIR, "fallos.jsonl")


def fallo_add(said, reply, origin=""):
    """Anota un «no era eso». → el total de fallos guardados."""
    item = {"t": datetime.datetime.now().isoformat(timespec="seconds"), "frase": str(said or "")[:500],
            "origen": str(origin or "")[:40], "respuesta": str(reply or "")[:600], "version": J.VERSION,
            "modo": J.current_mode()}
    p = fallos_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    lines = []
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            lines = f.read().splitlines()[-(FALLOS_MAX - 1):]
    lines.append(json.dumps(item, ensure_ascii=False))
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(p + ".tmp", p)
    J.log_terminal(f"No era eso: «{item['frase'][:80]}» (lo atendió {item['origen'] or 'Jarvis'}).", "FALLOS")
    return len(lines)


def fallos_all():
    p = fallos_path()
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for ln in f:
            try:
                out.append(json.loads(ln))
            except ValueError:
                pass
    return out


@J.socketio.on("misheard")
def handle_misheard(data=None):
    d = data or {}
    if not str(d.get("said") or "").strip():
        return {"ok": False}
    n = fallo_add(d.get("said"), d.get("reply"), d.get("origin"))
    return {"ok": True, "n": n}


_F_OPEN = re.compile(r"\b(?:abre|abreme|muestrame|ensename|ver)\s+(?:el\s+)?(?:registro|archivo|lista)\s+de\s+(?:fallos|errores de comprension)\b")
_F_COUNT = re.compile(r"\bcuantos fallos\b|\bcuantas veces no (?:me )?entendiste\b")


def fallos_voice(text, t):
    if _F_OPEN.search(t):
        p = fallos_path()
        if not os.path.exists(p):
            J.reply("Aún no hay fallos anotados. Cuando una respuesta no sea lo que pediste, pulsa «No era eso» debajo de ella.", "FALLOS")
            return True
        if J.IS_WIN:
            try:
                os.startfile(p)
            except OSError:
                pass
        J.reply(f"Te abro el registro: {len(fallos_all())} fallos. Si me lo compartes, los corrijo en la próxima versión. "
                "Solo está en tu equipo.", "FALLOS")
        return True
    if _F_COUNT.search(t):
        n = len(fallos_all())
        J.reply(f"Tengo {n} fallo{'s' if n != 1 else ''} anotado{'s' if n != 1 else ''}." if n else "No tengo fallos anotados.", "FALLOS")
        return True
    return False


# ============================================================================ FRASE DIRECTA
def phrase_tip(text, now=None):
    """Tras una orden que tuvo que adivinar la IA: si la guía tiene una frase casi igual, la muestra (1 vez al día). → el tip o ''."""
    today = (now or datetime.datetime.now()).date().isoformat()
    if not J.settings.get("phrase_tips", True) or J.settings.get("tip_last") == today or getattr(J._tl, "remote", False):
        return ""
    hit = guia.best_example(J.guide(), text)
    if not hit:
        return ""
    name, ex = hit
    J.settings["tip_last"] = today
    try:
        J.save_settings_file()
    except OSError:
        pass
    tip = f"La próxima vez puedes decir «{ex}» y voy directo ({name})."

    def later():
        time.sleep(0 if not J.net.get("watch", True) else 4)       # después de la respuesta
        J.card("tip", "Atajo", tip, "💡", secs=14)
        J.log_terminal(tip, "TIP")
    threading.Thread(target=later, daemon=True).start()
    return tip


# ============================================================================ HABILIDAD DEL DÍA
def skill_of_day(now=None):
    """Una línea para el resumen de la mañana. → '' si está apagado o no hay qué mostrar."""
    if not J.settings.get("skill_of_day", True):
        return ""
    now = now or datetime.datetime.now()
    seen = list(J.settings.get("skill_day_seen") or [])
    pick = guia.daily_pick(J.guide(), seen, J.current_mode() == "general", now.timetuple().tm_yday)
    if not pick:
        return ""
    name, exs = pick
    J.settings["skill_day_seen"] = (seen + [name])[-300:]
    try:
        J.save_settings_file()
    except OSError:
        pass
    clean = re.sub(r"\s*\(\d+\.\d+(?:\.\d+)?\)", "", name)
    return f"Habilidad del día, {clean}: prueba a decir «{exs[0]}»." if exs else ""


__all__ = ['FALLOS_MAX', '_F_COUNT', '_F_OPEN', 'fallo_add', 'fallos_all', 'fallos_path', 'fallos_voice', 'handle_misheard',
           'phrase_tip', 'skill_of_day']
