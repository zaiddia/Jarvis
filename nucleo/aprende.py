"""7.4: Jarvis aprende tus costumbres, recuerda lo que hablaron y hace tareas programadas solo.

  · Aprender (aprendizaje.py): propone rutinas con lo que repites, horarios para lo que haces siempre a la
    misma hora, y corrige una rutina cuando cambias justo después lo que ella hizo.
  · Recordar (recuerdos.py): «¿qué te dije la semana pasada sobre el examen de 7A?», por palabras y, si hay
    modelo de embeddings (Gemini u Ollama), por significado.
  · Tareas (tareas.py): «cada lunes a las 6 resume mis pendientes y mándamelo al celular».
Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import json
import re
import threading
import time

import aprendizaje
import diario
import proactivo
import recuerdos
import rutinas
import skills
import tareas
from nucleo import J

# ============================================================================ 1. APRENDER DE TUS COSTUMBRES
learn_offer = {"kind": None, "data": None, "expires": 0.0}
learn_state = {"last_offer": 0.0, "day": "", "count": 0, "last_routine": None, "last_action": 0.0, "last_key": ""}
LEARN_MAX_PER_DAY = 3
LEARN_GAP = 3600


def action_key(name, args):
    return f"{name}:{json.dumps(args or {}, sort_keys=True, ensure_ascii=False)}"


def step_key(step):
    """La clave de un paso de rutina (o None si es «esperar», «decir» o no es una acción directa)."""
    kind, val = rutinas.step_kind(step)
    if kind != "orden":
        return None
    direct = skills.parse(val)
    return action_key(*direct) if direct else None


def learn_note(name, args):
    """Anota una acción que pediste tú (no las de rutinas, tareas, celular ni enlaces)."""
    tl = J._tl
    if not J.settings["learn_enabled"] or getattr(tl, "remote", False) or getattr(tl, "capture", None) is not None:
        return
    if J.routine_state["running"]:
        return
    text = getattr(tl, "cmd_text", None)
    if not text:
        return
    sk = skills.REGISTRY.get(name)
    if sk is not None and sk.dangerous:
        return
    key = action_key(name, args)
    aprendizaje.note(key, text)
    learn_state.update(last_action=time.time(), last_key=key)
    lr = learn_state["last_routine"]
    if lr and name != "rutina" and time.time() - lr["end"] < aprendizaje.CORRECTION_WINDOW:
        r = lr["r"]
        c = aprendizaje.find_correction([step_key(s) for s in r["pasos"]], r["pasos"], key, text)
        if c:
            learn_state["last_routine"] = None
            sid = f"corr:{r['nombre']}:{c['index']}:{key}"
            if sid not in aprendizaje.data["rechazadas"]:
                threading.Timer(3.5, lambda: J._offer("corregir", {"rutina": r["nombre"], **c, "id": sid},
                                                    f"Acabas de cambiar lo que hizo la rutina {r['nombre']}: «{c['old']}». "
                                                    f"¿Quieres que la próxima vez haga «{c['new']}»? Di sí o no.")).start()


def learn_routine_done(r):
    learn_state["last_routine"] = {"r": r, "end": time.time()}


def _offer(kind, data, text):
    learn_offer.update(kind=kind, data=data, expires=time.time() + 90)
    learn_state["last_offer"] = time.time()
    today = datetime.date.today().isoformat()
    if learn_state["day"] != today:
        learn_state.update(day=today, count=0)
    learn_state["count"] += 1
    J.reply(text, "APRENDE")


def _unique_name(name):
    names = {rutinas.normalize(r["nombre"]) for r in rutinas.routines}
    base, n = name, 2
    while rutinas.normalize(name) in names:
        name = f"{base} {n}"
        n += 1
    return name


_LEARN_NAME_RE = re.compile(r"^(?:(?:si|vale|claro|ok|dale)\s+)?(?:llamala|ponle de nombre|ponle|nombrala|que se llame|guardala como|con el nombre)\s+(.{2,40})$")


def learn_answer(t):
    """Respuesta a una propuesta de aprendizaje. True si la contestó."""
    kind, data = learn_offer["kind"], learn_offer["data"]
    if not kind or time.time() > learn_offer["expires"]:
        return False
    named = _LEARN_NAME_RE.search(t)
    yes = re.fullmatch(rf"{J.CONFIRM_RE}(?: .*)?", t) or named or re.fullmatch(r"(?:guardala|guardalo|si guardala|hazlo asi)", t)
    no = re.fullmatch(rf"(?:{J.DENY_RE}|nunca|no gracias|no me lo vuelvas a proponer)(?: .*)?", t)
    if not (yes or no):
        return False
    learn_offer.update(kind=None, data=None, expires=0)
    if no:
        aprendizaje.mark(data["id"], False)
        J.reply("Vale, no te lo vuelvo a proponer.", "APRENDE")
        return True
    try:
        if kind == "rutina":
            name = _unique_name(named.group(1).strip().capitalize() if named else aprendizaje.default_name(data["texts"]))
            rutinas.upsert(name, name, "\n".join(data["texts"]))
            J.reply(f"Listo, guardé la rutina «{name}» con {len(data['texts'])} pasos. Para lanzarla di «{name}». "
                    "La puedes cambiar en Ajustes, sección Rutinas.", "APRENDE")
        elif kind == "horario":
            h, m = data["at"]
            cuando = f"{h:02d}:{m:02d}" + (" lun-vie" if data["weekdays"] else "")
            name = _unique_name(named.group(1).strip().capitalize() if named else f"{data['text'][:30].capitalize()} a las {h}:{m:02d}")
            rutinas.upsert(name, name, data["text"], cuando=cuando)
            J.reply(f"Hecho: desde mañana lo hago solo {rutinas.when_spoken(cuando)}. Lo cambias en Ajustes, sección Rutinas.", "APRENDE")
        elif kind == "corregir":
            r = next((x for x in rutinas.routines if x["nombre"] == data["rutina"]), None)
            if r is None:
                J.reply("Esa rutina ya no existe.", "APRENDE")
                return True
            pasos = list(r["pasos"])
            if data["index"] < len(pasos) and pasos[data["index"]] == data["old"]:
                pasos[data["index"]] = data["new"]
            rutinas.upsert(r["nombre"], ", ".join(r["frases"]), "\n".join(pasos), old=r["nombre"], cuando=r.get("cuando", ""))
            J.reply(f"Corregido: la rutina {r['nombre']} ahora hará «{data['new']}».", "APRENDE")
        aprendizaje.mark(data["id"], True)
        diario.log("rutina", f"aprendida: {data.get('rutina') or data['id'][:40]}")
    except ValueError as e:
        J.reply(f"No pude guardarla: {e}", "APRENDE")
    return True


def learn_check(now=None):
    """¿Hay algo que proponer ahora? (lo llama el vigilante cada 30 s)."""
    if not J.settings["learn_enabled"] or learn_offer["kind"] and time.time() < learn_offer["expires"]:
        return None
    now_dt = datetime.datetime.now()
    now = now or time.time()
    if learn_state["day"] == now_dt.date().isoformat() and learn_state["count"] >= LEARN_MAX_PER_DAY:
        return None
    if now - learn_state["last_offer"] < LEARN_GAP or J.routine_state["running"]:
        return None
    since = now - learn_state["last_action"]
    if not 20 <= since <= 600:                          # justo después de que haces algo, no en frío
        return None
    if proactivo.in_quiet(now_dt, J.settings["proactive_quiet"]) or J.state.get("mode") != "idle":
        return None
    known = [[step_key(s) for s in r["pasos"]] for r in rutinas.routines]
    seq = aprendizaje.find_sequence(known_steps=known)
    if seq and seq["keys"][-1] == learn_state["last_key"]:
        J._offer("rutina", seq, f"Me he fijado en que, varios días, haces lo mismo seguido: {aprendizaje.spoken_steps(seq['texts'])}. "
                              "¿Quieres que lo guarde como una rutina para hacerlo con una sola frase? "
                              "Di «sí», «sí, llámala…» con el nombre que quieras, o «no».")
        return seq
    timed = {step_key(s) for r in rutinas.routines if (rutinas.parse_when(r.get("cuando", "")) or {}).get("kind") == "hora"
             for s in r["pasos"]}
    habit = aprendizaje.find_time_habit(scheduled_keys=timed)
    if habit and habit["key"] == learn_state["last_key"]:
        h, m = habit["at"]
        days = " de lunes a viernes" if habit["weekdays"] else ""
        J._offer("horario", habit, f"Casi siempre, hacia las {h}:{m:02d}{days}, me pides «{habit['text']}». "
                                 "¿Quieres que lo haga solo a esa hora? Di sí o no.")
        return habit
    return None


def _learn_worker():
    while True:
        time.sleep(30)
        try:
            J.learn_check()
        except Exception as e:
            J.log_terminal(f"Aprendizaje: {e}", "AVISO")


_LEARN_VOICE = re.compile(r"\b(?:olvida|borra) (?:mis costumbres|lo que has aprendido de mi|lo aprendido)\b")


def learn_voice(text, t):
    if _LEARN_VOICE.search(t):
        aprendizaje.clear()
        J.reply("Listo, olvidé tus costumbres. Empiezo a fijarme de nuevo.", "APRENDE")
        return True
    if re.search(r"\b(?:deja de|no) (?:aprender|fijarte en) (?:mis costumbres|lo que hago)\b", t):
        J.apply_settings({"learn_enabled": False})
        J.reply("Vale, dejo de fijarme en tus costumbres. Lo vuelves a activar en Ajustes, sección Memoria.", "APRENDE")
        return True
    return False


# ============================================================================ 2. MEMORIA BUSCABLE
_RECALL_RE = re.compile(
    r"\b(?:que te (?:dije|conte|pedi|comente|mencione)|que (?:hablamos|platicamos|conversamos)|de que hablamos|"
    r"cuando te (?:dije|hable|conte|pedi|pregunte)|busca en (?:mi memoria|tu memoria|el historial|lo que hablamos|"
    r"nuestras conversaciones)|(?:te )?(?:recuerdas|acuerdas) (?:lo que|cuando|que te|de lo que|de cuando|de que te)|"
    r"que me dijiste (?:sobre|de|acerca)|que me respondiste)\b")
_RECALL_STRIP = re.compile(
    r"^.*?\b(?:que te (?:dije|conte|pedi|comente|mencione)|que (?:hablamos|platicamos|conversamos)|de que hablamos|"
    r"cuando te (?:dije|hable|conte|pedi|pregunte)|busca en (?:mi memoria|tu memoria|el historial|lo que hablamos|"
    r"nuestras conversaciones)|(?:recuerdas|acuerdas) (?:lo que|cuando|que te|de lo que|de cuando|de que te)|"
    r"que me dijiste|que me respondiste)\b\s*(?:(?:sobre|de|del|acerca de|respecto a|lo de|la|el|los|las)\s+)*")

_embed_cache = {"ollama_model": None, "checked": 0.0}


def memory_embed_tag():
    if J.is_offline() or not J.settings["memory_semantic"]:
        return ""
    if J._gemini_for_stt():
        return "gemini"
    if J.settings["ai_provider"] == "ollama" and _ollama_embed_model():
        return "ollama-" + re.sub(r"[^\w.-]", "_", _ollama_embed_model())
    return ""


def _ollama_embed_model():
    if time.time() - _embed_cache["checked"] > 600:
        _embed_cache["checked"] = time.time()
        try:
            d = J._http("GET", J.settings["ollama_host"].rstrip("/") + "/api/tags", timeout=4)
            names = [m.get("name", "") for m in d.get("models", [])]
            _embed_cache["ollama_model"] = next((n for n in names if "embed" in n.lower()), None)
        except Exception:
            _embed_cache["ollama_model"] = None
    return _embed_cache["ollama_model"]


def memory_embed(texts):
    """Vectores de significado para el buscador, o None si no hay modelo."""
    tag = J.memory_embed_tag()
    if not tag or not texts:
        return None
    if tag == "gemini":
        g = J._gemini_for_stt()
        out = []
        for i in range(0, len(texts), 100):
            reqs = [{"model": "models/gemini-embedding-001", "content": {"parts": [{"text": t[:2000]}]},
                     "outputDimensionality": 256} for t in texts[i:i + 100]]
            d = J._http("POST", f"{J.GEMINI_BASE}/models/gemini-embedding-001:batchEmbedContents",
                        J._gemini_headers(g), {"requests": reqs}, timeout=30)
            out += [e.get("values") or [] for e in d.get("embeddings", [])]
        return out
    d = J._http("POST", J.settings["ollama_host"].rstrip("/") + "/api/embed",
                payload={"model": _ollama_embed_model(), "input": [t[:2000] for t in texts]}, timeout=60)
    return d.get("embeddings")


def recall(question, topic=None):
    tag = J.memory_embed_tag()
    return recuerdos.search(question, embed=J.memory_embed if tag else None, embed_tag=tag, topic=topic)


def recall_voice(text, t):
    if not _RECALL_RE.search(t):
        return False
    if not J.settings["history_enabled"]:
        J.reply("El historial de conversaciones está apagado. Lo enciendes en Ajustes, sección Memoria.", "MEMORIA")
        return True
    topic = _RECALL_STRIP.sub("", t).strip(" ?")
    hits = J.recall(text, topic=topic)
    if hits and J.state.get("ai") == "ok":
        try:
            kind, ans = J.ask_ai(recuerdos.prompt(text, hits))
            if kind == "chat" and ans:
                J.reply(ans, "MEMORIA")
                return True
        except Exception:
            pass
    J.reply(recuerdos.spoken(hits), "MEMORIA")
    return True


# ============================================================================ 6. TAREAS PROGRAMADAS
_TASK_LIST = re.compile(r"\b(?:que tareas (?:tengo )?programadas|mis tareas programadas|tareas programadas tengo|"
                        r"lista de (?:las )?tareas programadas|que tareas programaste)\b")
_TASK_DEL = re.compile(r"\b(?:borra|elimina|quita|cancela)\s+(?:la|esa|mi)?\s*tarea(?:s)?(?: programada)?\s*(.*)$")
_TASK_PAUSE = re.compile(r"\b(pausa|desactiva|detiene|deten|reanuda|activa)\s+(?:la|esa|mi)?\s*tarea(?: programada)?\s*(.*)$")


def telegram_ready():
    return bool(J.settings["telegram_token"].strip() and J.settings["telegram_chat"].strip())


def tasks_voice(text, t):
    if _TASK_LIST.search(t):
        if not tareas.tasks:
            J.reply("No tienes tareas programadas. Por ejemplo, di: cada lunes a las 6 de la tarde resume mis "
                    "pendientes y mándamelo al celular.", "TAREA")
        else:
            items = [f"{i + 1}, {tareas.spoken(x)}" + ("" if x.get("activa", True) else " (en pausa)")
                     for i, x in enumerate(tareas.tasks)]
            J.reply("Tus tareas programadas: " + "; ".join(items) + ".", "TAREA")
        return True
    m = _TASK_DEL.search(t)
    if m and "tarea" in t:
        x = tareas.find(m.group(1))
        if not x:
            J.reply("No encuentro esa tarea. Pregúntame «qué tareas tengo programadas».", "TAREA")
        else:
            tareas.remove(x["id"])
            J.reply(f"Borré la tarea: {x['orden']}.", "TAREA")
        return True
    m = _TASK_PAUSE.search(t)
    if m:
        x = tareas.find(m.group(2))
        if not x:
            J.reply("No encuentro esa tarea.", "TAREA")
        else:
            on = m.group(1) in ("reanuda", "activa")
            tareas.set_active(x["id"], on)
            J.reply(f"{'Reanudé' if on else 'Pausé'} la tarea: {x['orden']}.", "TAREA")
        return True
    p = tareas.parse_voice(text)
    if not p:
        return False
    try:
        x = tareas.add(p["orden"], p["cuando"], p["entrega"])
    except ValueError as e:
        J.reply(str(e), "TAREA")
        return True
    extra = ""
    if x["entrega"] != "voz" and not telegram_ready():
        extra = " Aún no tienes Telegram conectado: hasta que lo conectes (Ajustes, Integraciones), te lo diré en voz alta."
    J.reply(f"Listo, tarea programada {tareas.spoken(x)}.{extra}", "TAREA")
    diario.log("nota", f"tarea programada: {x['orden']}")
    return True


def run_task(task, why="a su hora"):
    """Hace la tarea (con las reglas del celular) y entrega lo que conteste."""
    J.log_terminal(f"Tarea programada ({why}): {task['orden']}", "TAREA")
    J._tl.via = "tarea"
    try:
        result = J.telegram_run(task["orden"])
    except Exception as e:
        result = f"No pude hacerla: {e}"
    finally:
        J._tl.via = None
    result = str(result or "Hecho.").strip()
    msg = f"Tarea programada «{task['orden']}»: {result}"
    diario.log("tarea", task["orden"])
    sent = False
    if task.get("entrega") in ("celular", "ambos") and telegram_ready():
        sent = J.telegram_send("🗓 " + msg)
    if task.get("entrega") in ("voz", "ambos") or not sent:
        J.reply(msg, "TAREA")
        J.orb_feed.update(alert_seq=J.orb_feed["alert_seq"] + 1, alert=msg[:300])
    else:
        J.log_terminal(f"Tarea enviada al celular: {task['orden']}", "TAREA")
    return msg


def _tasks_worker():
    first = True
    while True:
        try:
            now = datetime.datetime.now()
            todo = tareas.missed(now, hours=6) if first else tareas.due(now)
            first = False
            for task in todo:
                tareas.mark_done(task["id"], now.date())
                threading.Thread(target=J.run_task, args=(task, "pendiente desde antes" if task.get("_missed") else "a su hora"),
                                 daemon=True, name="tarea").start()
        except Exception as e:
            J.log_terminal(f"Tareas programadas: {e}", "AVISO")
        time.sleep(30)


@J.socketio.on("tasks_list")
def handle_tasks_list(data=None):
    return {"tasks": tareas.tasks, "telegram": telegram_ready()}


@J.socketio.on("tasks_add")
def handle_tasks_add(data=None):
    d = data or {}
    try:
        x = tareas.add(d.get("orden", ""), d.get("cuando", ""), d.get("entrega", "voz"))
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "task": x, "tasks": tareas.tasks, "spoken": tareas.spoken(x)}


@J.socketio.on("tasks_remove")
def handle_tasks_remove(data=None):
    tareas.remove(str((data or {}).get("id", "")))
    return {"ok": True, "tasks": tareas.tasks}


@J.socketio.on("tasks_toggle")
def handle_tasks_toggle(data=None):
    d = data or {}
    tareas.set_active(str(d.get("id", "")), bool(d.get("on")))
    return {"ok": True, "tasks": tareas.tasks}


@J.socketio.on("tasks_run")
def handle_tasks_run(data=None):
    x = next((t for t in tareas.tasks if t["id"] == str((data or {}).get("id", ""))), None)
    if x:
        threading.Thread(target=J.run_task, args=(x, "prueba"), daemon=True).start()
    return {"ok": bool(x)}


@J.socketio.on("history_clear")
def handle_history_clear(data=None):
    recuerdos.clear()
    return {"ok": True}


def learn_start():
    aprendizaje.configure(J.CONFIG_DIR)
    recuerdos.configure(J.CONFIG_DIR, J.settings["history_enabled"], J.settings["history_days"])
    recuerdos.purge()
    tareas.configure(J.CONFIG_DIR)
    for target in (J._learn_worker, J._tasks_worker):
        threading.Thread(target=target, daemon=True).start()


__all__ = [
    'LEARN_GAP', 'LEARN_MAX_PER_DAY', '_LEARN_VOICE', '_LEARN_NAME_RE', '_RECALL_RE', '_RECALL_STRIP', '_TASK_DEL', '_TASK_LIST',
    '_TASK_PAUSE', '_embed_cache', '_learn_worker', '_offer', '_ollama_embed_model', '_tasks_worker', '_unique_name',
    'action_key', 'handle_history_clear', 'handle_tasks_add', 'handle_tasks_list', 'handle_tasks_remove', 'handle_tasks_run',
    'handle_tasks_toggle', 'learn_answer', 'learn_check', 'learn_note', 'learn_offer', 'learn_routine_done', 'learn_start',
    'learn_state', 'learn_voice', 'memory_embed', 'memory_embed_tag', 'recall', 'recall_voice', 'run_task', 'step_key',
    'tasks_voice', 'telegram_ready',
]
