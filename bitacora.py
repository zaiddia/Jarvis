"""«Lo que hice hoy» (11.8): lo que Jarvis hizo, solo o por orden tuya, con «deshacer» cuando se puede. Vive en la
memoria mientras Jarvis está abierto (no guarda datos de estudiantes en otro archivo). Lógica pura.
"""
import datetime
import itertools
import threading
import time

_lock = threading.RLock()
_ids = itertools.count(1)
entries = []                    # [{"id", "t", "hora", "texto", "tipo", "n", "deshecho", "puede"}]
_undo = {}                      # id → [funciones para deshacer]
_groups = {}                    # id → clave de grupo
MAX = 300
GROUP_SECONDS = 4


def add(texto, tipo="accion", undo=None, group=None, group_text=None, now=None):
    """Anota una acción. Las seguidas del mismo grupo (p. ej. 35 notas de un formulario) se juntan en una.
    group_text(n) da el texto del grupo con n acciones. → la entrada."""
    now = now or time.time()
    with _lock:
        last = entries[-1] if entries else None
        if group and last and _groups.get(last["id"]) == group and now - last["t"] < GROUP_SECONDS and not last["deshecho"]:
            last["n"] += 1
            last["t"] = now
            if group_text:
                last["texto"] = group_text(last["n"])
            if undo:
                _undo.setdefault(last["id"], []).append(undo)
                last["puede"] = True
            return last
        e = {"id": next(_ids), "t": now, "hora": datetime.datetime.fromtimestamp(now).strftime("%H:%M"), "texto": str(texto)[:200], "tipo": tipo,
             "n": 1, "deshecho": False, "puede": bool(undo)}
        entries.append(e)
        if undo:
            _undo[e["id"]] = [undo]
        if group:
            _groups[e["id"]] = group
        while len(entries) > MAX:
            old = entries.pop(0)
            _undo.pop(old["id"], None)
            _groups.pop(old["id"], None)
        return e


def undo(eid):
    """Deshace una acción. → (ok, mensaje)."""
    with _lock:
        e = next((x for x in entries if x["id"] == eid), None)
        if not e:
            return False, "Esa acción ya no está en la lista."
        if e["deshecho"]:
            return False, "Eso ya lo había deshecho."
        fns = _undo.get(eid)
        if not fns:
            return False, "Eso no se puede deshacer desde aquí."
        errs = 0
        for fn in reversed(fns):
            try:
                fn()
            except Exception:
                errs += 1
        e["deshecho"] = True
        e["puede"] = False
        _undo.pop(eid, None)
    return errs == 0, ("Deshecho: " if errs == 0 else "Lo deshice en parte: ") + e["texto"][:1].lower() + e["texto"][1:]


def last_undoable(max_age=3600, now=None):
    now = now or time.time()
    with _lock:
        return next((e for e in reversed(entries) if e["puede"] and not e["deshecho"] and now - e["t"] < max_age), None)


def today(now=None):
    d = datetime.date.fromtimestamp(now or time.time())
    with _lock:
        return [dict(e) for e in entries if datetime.date.fromtimestamp(e["t"]) == d]


def spoken(items):
    if not items:
        return "Hoy todavía no he hecho nada por ti."
    done = [e for e in items if not e["deshecho"]]
    head = f"Hoy hice {len(done)} cosa{'s' if len(done) != 1 else ''}"
    last = "; ".join(f"{e['hora']}, {e['texto'][:1].lower() + e['texto'][1:]}" for e in done[-5:])
    return head + (f". Lo último: {last}." if last else ".") + " En el HUD, en «Lo que hice hoy», puedes deshacer lo que se pueda."


def clear():
    with _lock:
        entries.clear()
        _undo.clear()
        _groups.clear()
