"""12.1: memoria que se ordena sola.

Cada noche (desde las 10 p. m., o al prender si no se hizo) Jarvis repasa lo que le dijiste en el día y guarda en tu
perfil los datos duraderos que no había atrapado: tus cursos, tus preferencias, lo que te funciona. Cada dato guarda
la cita textual de dónde salió (si la cita no aparece de verdad en la conversación, no se guarda), y si contradice algo
que ya sabía, te pregunta antes de cambiarlo. «¿Qué aprendiste de mí?» lo cuenta; «olvida que…» lo borra.
La lógica está en consolidar.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import re
import threading
import time

import consolidar
import perfil
import recuerdos
from nucleo import J

mem_night = {"busy": False, "learned": []}


def consolidate(day=None):
    """Repasa la conversación de ese día. → [datos guardados], [cambios por aprobar]."""
    day = day or datetime.date.today()
    lines = consolidar.user_lines(recuerdos.load(since=day, until=day))
    if len(lines) < 3:
        return [], []
    known = [f["texto"] for f in perfil.facts]
    raw = J.ai_chat([{"role": "user", "content": consolidar.prompt(lines, known)}], json_mode=True, max_tokens=1200)
    items = consolidar.clean(J._extract_json(raw), lines, known)
    saved, asked = [], []
    for it in items:
        fuente = f"{day.isoformat()}: «{it['cita']}»"
        if it["reemplaza"]:
            old = it["reemplaza"]

            def ok(it=it, old=old, fuente=fuente):
                for f in list(perfil.facts):
                    if f["texto"] == old:
                        perfil.delete(f["id"])
                f = perfil.add(it["dato"])
                if f:
                    f["fuente"] = fuente
                    perfil.save()
                J.reply(f"Actualicé lo que sé de ti: «{it['dato']}».", "MEMORIA")
            J.request_approval("memoria", f"¿Cambio «{old}» por «{it['dato']}»?", f"Lo dijiste el {fuente}", on_ok=ok, on_no=lambda: None,
                               ttl=24 * 3600, quiet=True)
            asked.append(it)
            continue
        f = perfil.add(it["dato"])
        if f:
            f["fuente"] = fuente
            saved.append(it)
    if saved:
        perfil.save()
    mem_night["learned"] = saved
    return saved, asked


def memory_tick(now=None):
    now = now or datetime.datetime.now()
    if not J.settings.get("memory_consolidate", True) or mem_night["busy"] or J.state.get("ai") != "ok":
        return None
    last = J.settings.get("memory_last", "")
    today, yesterday = now.date(), now.date() - datetime.timedelta(days=1)
    if now.hour >= 22 and last != today.isoformat():
        day = today
    elif now.hour < 22 and last < yesterday.isoformat():
        day = yesterday                                  # el equipo estuvo apagado en la noche: lo hace ahora
    else:
        return None
    mem_night["busy"] = True
    try:
        saved, asked = consolidate(day)
    except Exception as e:
        J.note_error("MEMORIA", e)
        saved, asked = [], []
    finally:
        mem_night["busy"] = False
    J.settings["memory_last"] = day.isoformat()
    try:
        J.save_settings_file()
    except OSError:
        pass
    if saved or asked:
        J.notice_add(f"Aprendí {len(saved)} cosa{'s' if len(saved) != 1 else ''} de ti" +
                     (f" y tengo {len(asked)} cambio{'s' if len(asked) != 1 else ''} por aprobar" if asked else "") +
                     ". «¿Qué aprendiste de mí?»", "aviso", "MEMORIA")
    return day


def _memory_worker():
    time.sleep(300)
    while True:
        try:
            J.memory_tick()
        except Exception as e:
            J.note_error("MEMORIA", e)
        time.sleep(1800)


_MN_ASK = re.compile(r"\bque (?:aprendiste|has aprendido) de mi\b|\bque aprendiste (?:anoche|ayer)\b")
_MN_NOW = re.compile(r"\b(?:ordena|organiza|repasa)\s+(?:tu\s+)?memoria\b")


def memory_night_voice(text, t):
    if _MN_NOW.search(t):
        if J.state.get("ai") != "ok":
            J.reply("Para ordenar la memoria necesito la IA conectada.", "MEMORIA")
            return True
        J.reply("Repaso lo que hablamos hoy…", "MEMORIA")

        def work():
            try:
                saved, asked = consolidate()
            except Exception as e:
                J.notify(f"No pude ordenar la memoria: {getattr(e, 'why', e)}", "MEMORIA")
                return
            if not saved and not asked:
                J.notify("Repasé lo de hoy y no encontré nada nuevo que guardar sobre ti.", "MEMORIA")
                return
            if saved:
                J.notify("Guardé: " + "; ".join(i["dato"] for i in saved) + ".", "MEMORIA")
            if asked:
                J.notify(f"Y hay {len(asked)} dato{'s' if len(asked) != 1 else ''} que contradice lo que sabía: te lo dejé para aprobar.", "MEMORIA")
        J.start_job("Ordenando la memoria", work, "memoria")
        return True
    if _MN_ASK.search(t):
        recent = [f for f in perfil.facts if f.get("fuente")][:6]
        if not recent:
            J.reply("Aún no he aprendido nada nuevo por mi cuenta. Cada noche repaso lo que hablamos; también puedes decir «ordena tu memoria».",
                    "MEMORIA")
            return True
        J.reply("Esto aprendí de lo que me has dicho: " + "; ".join(f"{f['texto']} (lo dijiste el {f['fuente'].split(':')[0]})" for f in recent) +
                ". Si algo está mal, di «olvida que …».", "MEMORIA")
        return True
    return False


def memory_night_start():
    threading.Thread(target=J._memory_worker, daemon=True, name="memoria-noche").start()


__all__ = ['_MN_ASK', '_MN_NOW', '_memory_worker', 'consolidar', 'consolidate', 'mem_night', 'memory_night_start', 'memory_night_voice',
           'memory_tick']
