"""8.6: el plus del HUD — panel «Hoy», tarjetas de archivos, paleta de órdenes (Ctrl+K), sugerencias según el momento
y modo proyector para el salón.

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import collections
import datetime
import os
import re
import threading
import time

import aprobaciones
import aula
import calendario
import horario
import notas
import seguimiento
import zeti
from nucleo import J


# ============================================================================ ARCHIVOS RECIENTES (tarjetas en el chat)
class RecentFiles(set):
    """El conjunto de archivos que Jarvis generó (solo esos se pueden abrir desde las páginas), recordando el orden y
    avisando al HUD para que muestre la tarjeta del archivo."""

    def __init__(self, items=()):
        super().__init__(items)
        self.order = collections.deque(maxlen=40)

    def add(self, path):
        path = str(path)
        super().add(path)
        if path in self.order:
            self.order.remove(path)
        self.order.append(path)
        try:
            J.socketio.emit("file_card", file_card(path))
            J.on_new_file(path)                        # 8.7: subir a Drive, si lo activaste
        except Exception:
            pass


_IMG = (".png", ".jpg", ".jpeg", ".gif", ".webp")
_KINDS = {".docx": "Word", ".doc": "Word", ".pptx": "PowerPoint", ".xlsx": "Excel", ".csv": "Excel", ".pdf": "PDF",
          ".txt": "Texto", ".ics": "Evento", ".md": "Texto", ".html": "Página"}


def file_card(path):
    ext = os.path.splitext(path)[1].lower()
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    idx = list(J.generated_files.order).index(path) if path in getattr(J.generated_files, "order", ()) else -1
    return {"path": path, "name": os.path.basename(path), "folder": os.path.basename(os.path.dirname(path)),
            "kind": "Imagen" if ext in _IMG else _KINDS.get(ext, ext.lstrip(".").upper() or "Archivo"),
            "image": ext in _IMG, "size": size, "id": idx}


def _allowed(path):
    return path in J.generated_files and os.path.exists(path)


@J.socketio.on("file_open")
def handle_file_open(data=None):
    """Abre un archivo (o su carpeta) que Jarvis generó. Cualquier otra ruta se ignora."""
    d = data or {}
    path = str(d.get("path", ""))
    if not _allowed(path):
        return {"ok": False}
    target = os.path.dirname(path) if d.get("folder") else path
    try:
        if J.IS_WIN:
            if d.get("folder"):
                import subprocess
                subprocess.Popen(["explorer", "/select,", path])
            else:
                os.startfile(target)
        return {"ok": True}
    except OSError:
        return {"ok": False}


@J.app.route("/archivo/<int:idx>")
def recent_image(idx):
    """Miniatura de una imagen que Jarvis generó (solo las de la lista de recientes, solo imágenes)."""
    from flask import abort, send_file
    order = list(getattr(J.generated_files, "order", ()))
    if not (0 <= idx < len(order)):
        abort(404)
    path = order[idx]
    if os.path.splitext(path)[1].lower() not in _IMG or not _allowed(path):
        abort(404)
    return send_file(path, max_age=60)


# ============================================================================ TRABAJOS EN SEGUNDO PLANO (9.0)
jobs = {}                       # id → {"t": etiqueta, "start": hora}
_job_seq = [0]
_job_lock = threading.Lock()


def jobs_list():
    """Lo que Jarvis está haciendo ahora mismo (para la franja «Trabajando…» del HUD)."""
    now = time.time()
    out = [{"t": j["t"], "s": int(now - j["start"])} for j in list(jobs.values())]
    if J.project_run["busy"] and J.project_run.get("st"):
        pr = J._orb_project()
        out.append({"t": f"Proyecto «{pr['project_name']}» · {pr['project_done']}/{pr['project_total']} pasos", "s": -1})
    if J.upd["busy"]:
        out.append({"t": "Actualizando Jarvis", "s": -1})
    if J.check_state.get("busy"):
        out.append({"t": "Haciendo la prueba completa", "s": -1})
    return out


def _emit_jobs():
    try:
        J.socketio.emit("jobs", {"jobs": jobs_list()})
    except Exception:
        pass


def start_job(label, fn, name="trabajo"):
    """Corre fn en segundo plano y lo muestra en el HUD mientras dura."""
    with _job_lock:
        _job_seq[0] += 1
        jid = _job_seq[0]
        jobs[jid] = {"t": label, "start": time.time()}
    _emit_jobs()

    def run():
        try:
            fn()
        except Exception as e:                         # que un fallo no quede mudo: al registro de errores
            J.note_error(name.upper()[:40], e)
            J.log_terminal(f"{label}: falló ({e})", "ERROR")
        finally:
            jobs.pop(jid, None)
            _emit_jobs()
    t = threading.Thread(target=run, daemon=True, name=name)
    t.start()
    return t


# ============================================================================ CAMPANA DE AVISOS Y FAVORITOS (9.2)
notices = collections.deque(maxlen=50)
_notice_seq = [0]
_notice_seen = [0]


def notice_add(text, kind="aviso", origin=""):
    """Un aviso para la campana del HUD (recordatorios, aprobaciones, errores). Los repetidos seguidos no se duplican."""
    text = str(text).strip()
    if not text:
        return None
    if notices and notices[-1]["text"] == text and time.time() - notices[-1]["ts"] < 60:
        return None
    _notice_seq[0] += 1
    item = {"id": _notice_seq[0], "text": text[:300], "kind": kind, "origin": origin, "ts": time.time(),
            "hora": datetime.datetime.now().strftime("%H:%M")}
    notices.append(item)
    try:
        J.socketio.emit("notice", {**item, "unread": notices_unread()})
    except Exception:
        pass
    return item


def notices_unread():
    return sum(1 for n in notices if n["id"] > _notice_seen[0])


@J.socketio.on("notices")
def handle_notices(data=None):
    if (data or {}).get("seen"):
        _notice_seen[0] = _notice_seq[0]
    if (data or {}).get("clear"):
        notices.clear()
    return {"items": list(notices)[::-1], "unread": notices_unread()}


def favorites():
    return [x.strip() for x in J.settings["hud_favorites"].splitlines() if x.strip()][:20]


@J.socketio.on("favorite_toggle")
def handle_favorite_toggle(data=None):
    cmd = re.sub(r"\s+", " ", str((data or {}).get("cmd", ""))).strip()[:160]
    favs = favorites()
    if cmd:
        favs = [f for f in favs if f != cmd] if cmd in favs else (favs + [cmd])[-20:]
        J.apply_settings({"hud_favorites": "\n".join(favs)})
        J.settings["hud_favorites"] = "\n".join(favs)
    return {"favorites": favs}


def courses_summary():
    """Por curso: promedio, cuántos con notas y cuántos en cada desempeño (para la tarjeta «Cursos»)."""
    out = []
    for course in sorted(set(aula.data.get("cursos", {})) | set(seguimiento.data), key=aula.course_sort_key)[:24]:
        avgs = [a for a in (seguimiento.average(course, n) for n in seguimiento.data.get(course, {})) if a is not None]
        if not avgs:
            continue
        dist = {"Superior": 0, "Alto": 0, "Básico": 0, "Bajo": 0}
        for a in avgs:
            dist["Superior" if a >= zeti.SCALE["superior"] else "Alto" if a >= zeti.SCALE["alto"] else "Básico" if a >= zeti.SCALE["basico"] else "Bajo"] += 1
        out.append({"curso": course, "promedio": round(sum(avgs) / len(avgs), 1), "n": len(avgs), "dist": dist})
    return out


# ============================================================================ PANEL «HOY»
_weather = {"t": 0.0, "text": ""}


def _weather_short():
    if not J.settings["weather_city"].strip() or J.is_offline():
        return ""
    if time.time() - _weather["t"] > 1800:
        _weather["t"] = time.time()

        def work():
            txt = J.weather_text()
            if not txt.lower().startswith(("no ", "ahora no", "para darte")):
                _weather["text"] = re.split(r"(?<=[.!])\s", txt.strip(), maxsplit=1)[0][:160]
        threading.Thread(target=work, daemon=True, name="clima-hud").start()
    return _weather["text"]


def _mins_until(hhmm, now):
    h, m = map(int, hhmm.split(":"))
    return int((datetime.datetime.combine(now.date(), datetime.time(h, m)) - now).total_seconds() // 60)


def dashboard(now=None):
    """Todo lo del panel «Hoy» en un diccionario pequeño (sin llamadas lentas: lo lento va en caché)."""
    now = now or datetime.datetime.now()
    out = {"hora": now.strftime("%H:%M"), "fecha": now.strftime("%d/%m")}
    x = horario.now_class(now)
    nx, day = horario.next_class(now)
    prog = None
    if x:
        a, b = _mins_until(x["inicio"], now), _mins_until(x["fin"], now)
        prog = round(min(1.0, max(0.0, -a / max(1, b - a))), 3)
    out["clase"] = {"ahora": horario.label(x) if x else "", "hasta": x["fin"] if x else "", "progreso": prog,
                    "falta": _mins_until(x["fin"], now) if x else None,
                    "siguiente": horario.label(nx) if nx else "", "a_las": nx["inicio"] if nx else "",
                    "hoy": bool(nx and day == now.date()),
                    "en": _mins_until(nx["inicio"], now) if nx and day == now.date() else None}
    try:
        evs = calendario.upcoming(limit=3)
        out["agenda"] = []
        for e in evs:
            en = None
            if not e["todo_el_dia"] and e["inicio"][:10] == now.date().isoformat():
                en = int((datetime.datetime.fromisoformat(e["inicio"]).replace(tzinfo=None) - now).total_seconds() // 60)
            out["agenda"].append({"t": e["titulo"][:60], "h": e["inicio"][11:16], "d": e["inicio"][:10],
                                  "hoy": e["inicio"][:10] == now.date().isoformat(), "en": en})
    except Exception:
        out["agenda"] = []
    out["clima"] = _weather_short()
    pend = notas.pending()
    out["pendientes"] = [{"id": n.get("id"), "t": notas.what(n)[:80]} for n in pend[:6]]
    out["n_pendientes"] = len(pend)
    out["aprobar"] = [{"id": a["id"], "t": a["titulo"][:90]} for a in aprobaciones.pending()[:4]]
    pr = J._orb_project()
    st = J.project_run["st"] if J.project_run["busy"] else None
    out["proyecto"] = ({"nombre": pr["project_name"], "hechos": pr["project_done"], "total": pr["project_total"],
                        "pasos": [{"t": p.get("titulo", "")[:50], "e": p.get("estado", "")} for p in (st or {}).get("pasos", [])][:10]}
                       if pr["project_total"] else None)
    msgs = J.mail_cache.get("msgs") or []
    imp = [m for m in msgs if not m.get("masivo")]
    out["correos"] = {"n": len(imp), "de": [m["de_nombre"][:30] for m in imp[:3]]} if imp else None
    risk = []
    for course in sorted(set(aula.data.get("cursos", {})) | set(seguimiento.data), key=aula.course_sort_key)[:24]:
        names = sorted(set(aula.students(course)) | set(seguimiento.data.get(course, {})))
        r = seguimiento.at_risk(course, names, J._absences(course), J.settings["risk_grade"], J.settings["risk_absences"])
        if r:
            risk.append({"curso": course, "n": len(r), "nombres": [n for n, _ in r[:3]]})
    out["riesgo"] = risk
    out["trabajos"] = jobs_list()
    try:                                               # 9.3: lo que necesita tu atención (sin aprobaciones: tienen su tarjeta)
        out["atencion"] = [x for x in J.attention_items(now) if not x["k"].startswith("ap:")][:5]
    except Exception:
        out["atencion"] = []
    out["cursos"] = courses_summary()
    out["favoritos"] = favorites()
    out["avisos_sin_leer"] = notices_unread()
    out["sugerencias"] = suggestions(now, out)
    return out


def suggestions(now, d):
    """Botones rápidos según el momento: [{"t": texto del botón, "cmd": orden, "fill": True si hay que completarla}]."""
    s = []
    if J.live_class["on"]:                              # 9.6: durante la clase en vivo, sus controles
        s += [{"t": "Siguiente momento", "cmd": "siguiente momento", "kind": "aprobar"}, {"t": "5 minutos más", "cmd": "dame 5 minutos más"},
              {"t": "Termina la clase", "cmd": "termina la clase"}]
    if J.ticket.state["open"]:
        s.append({"t": f"Cerrar ticket ({len(J.ticket.state['respuestas'])})", "cmd": "cierra el ticket", "kind": "aprobar"})
    if J.live_quiz["on"]:                               # 8.8: durante el quiz en vivo, sus controles primero
        s += [{"t": "Mostrar respuesta", "cmd": "respuesta", "kind": "aprobar"}, {"t": "Siguiente", "cmd": "siguiente"},
              {"t": "Terminar quiz", "cmd": "termina el quiz"}]
    for a in d["aprobar"][:1]:
        s.append({"t": f"✓ Aprobar: {a['t'][:28]}", "cmd": f"sí {a['id']}", "kind": "aprobar"})
    c = d["clase"]
    if c["ahora"]:
        s += [{"t": "Llamar a lista", "cmd": "llama a lista"}, {"t": "Escoger estudiante", "cmd": "escoge un estudiante"},
              {"t": "Temporizador 10 min", "cmd": "pon un temporizador de 10 minutos"},
              {"t": "Modo proyector", "cmd": "modo proyector"}]
    elif c["en"] is not None and 0 <= c["en"] <= 40:
        s.append({"t": f"Preparar {c['siguiente'][:18]}", "cmd": "prepárame la próxima clase de ", "fill": True})
    if d["correos"]:
        s.append({"t": f"Correos importantes ({d['correos']['n']})", "cmd": "¿qué correos importantes tengo?"})
    if now.weekday() == 4 and now.hour >= 13:
        s.append({"t": "Resumen semanal", "cmd": "dame el resumen semanal"})
    if now.hour < 10:
        s.append({"t": "¿Qué tengo hoy?", "cmd": "¿qué tengo hoy?"})
    if d["riesgo"]:
        s.append({"t": f"En riesgo en {d['riesgo'][0]['curso']}", "cmd": f"¿quiénes están en riesgo en {d['riesgo'][0]['curso']}?"})
    s += [{"t": "Quiz en Forms…", "cmd": "haz un quiz de 10 preguntas de  en Forms", "fill": True},
          {"t": "Mis pendientes", "cmd": "¿qué tengo pendiente?"}]
    s += [{"t": "★ " + f[:30], "cmd": f, "kind": "fav", "fill": f.endswith(" ")} for f in favorites()]
    seen, out = {}, []
    for x in s:
        if x["cmd"] not in seen:
            seen[x["cmd"]] = x
            out.append(x)
        elif x.get("kind") == "fav" and seen[x["cmd"]].get("kind") != "aprobar":   # ya estaba: se marca como favorito
            seen[x["cmd"]].update(kind="fav", t="★ " + seen[x["cmd"]]["t"].lstrip("★ "))
    return out[:12]


@J.socketio.on("dashboard")
def handle_dashboard(data=None):
    return J.dashboard()


def _dashboard_worker():
    while True:
        time.sleep(30)
        try:
            J.socketio.emit("dashboard", J.dashboard())
        except Exception as e:
            J.note_error("HUD", e)


# ============================================================================ PALETA DE ÓRDENES (Ctrl+K)
@J.socketio.on("palette")
def handle_palette(data=None):
    """Ejemplos de todo lo que sabe hacer, más lo que tú has pedido últimamente (sin repetir)."""
    ex = [{"t": e, "g": g} for g, items in J.CAPABILITIES for e in items if not e.startswith("(")]
    recent, seen = [], set()
    for item in reversed(list(J.chat_buffer)):
        if item.get("role") == "user":
            k = J.normalize(item["text"])
            if k and k not in seen and len(item["text"]) < 160:
                seen.add(k)
                recent.append(item["text"])
        if len(recent) >= 12:
            break
    extra = ["pasa el quiz a Forms", "trae las notas del formulario", "dame el resumen semanal", "¿qué clase tengo ahora?",
             "prepárame la próxima clase de ", "anota en el observador de  que ", "haz el informe para los padres de ",
             "crea 10 preguntas tipo saber de ", "haz la malla curricular de ", "adapta el taller de  para un estudiante con ",
             "genera el informe de errores", "modo proyector", "exporta las notas de  para Zeti"]
    return {"recent": recent, "examples": [{"t": e, "g": "Nuevo"} for e in extra] + ex}


# ============================================================================ MODO PROYECTOR
_PROJ_RE = re.compile(r"\b(?:modo proyector|abre el proyector|pon(?:lo)? en (?:el )?(?:proyector|televisor|tv)|pantalla de (?:la )?clase|"
                      r"modo pantalla grande|abre la pantalla del salon)\b")
_PROJ_OFF = re.compile(r"\b(?:cierra|quita|apaga|sal del)\s+(?:el\s+)?(?:modo\s+)?proyector\b")


@J.app.route("/proyector")
def projector_page():
    from flask import render_template
    return render_template("proyector.html", version=J.VERSION)


def projector_state():
    x = horario.now_class()
    last = J.aula_ui.get("last") or {}
    order = list(getattr(J.generated_files, "order", ()))
    img = next((i for i in range(len(order) - 1, -1, -1) if os.path.splitext(order[i])[1].lower() in _IMG), -1)
    return {"clase": horario.label(x) if x else (aula.data.get("activo") or ""), "hasta": x["fin"] if x else "",
            "last": last if last.get("type") in ("pick", "groups") else None, "imagen": img,
            "institucion": J.settings["aula_institucion"], "timers": J._timers_snapshot(), "theme": J.settings["theme"]}


@J.socketio.on("projector_state")
def handle_projector_state(data=None):
    return J.projector_state()


def projector_voice(text, t):
    if _PROJ_OFF.search(t):
        J.socketio.emit("projector", {"close": True})
        J.reply("Cerré el modo proyector.", "PROYECTOR")
        return True
    if not _PROJ_RE.search(t):
        return False
    J._open_projector()
    J.reply("Abrí el modo proyector: llévalo al televisor y pulsa F11 para pantalla completa. Ahí verás el temporizador, "
            "el estudiante escogido, los grupos y las imágenes que te prepare.", "PROYECTOR")
    return True


def _open_projector():
    """En una ventana propia (que puedes llevar al televisor) o, si no hay ventanas propias, en el navegador."""
    url = f"{J.URL}/proyector"
    w = J.hud.get("proj_win")
    if w is not None:
        try:
            w.show()
            w.restore()
            return
        except Exception:
            J.hud["proj_win"] = None
    if J.webview is not None and J.hud.get("window") is not None:
        try:
            w = J.webview.create_window("Jarvis · Proyector", url, width=1280, height=720, min_size=(640, 360),
                                        background_color="#03060c")
            w.events.closed += lambda: J.hud.update(proj_win=None)
            J.hud["proj_win"] = w
            return
        except Exception as e:
            J.note_error("PROYECTOR", e)
    import webbrowser
    webbrowser.open(url)


J.generated_files = RecentFiles(J.generated_files)     # desde ya: cada archivo nuevo sale como tarjeta en el HUD


def hud_plus_start():
    threading.Thread(target=J._dashboard_worker, daemon=True, name="tablero").start()


__all__ = [
    'RecentFiles', '_IMG', '_notice_seen', '_notice_seq', 'courses_summary', 'favorites', 'handle_favorite_toggle', 'handle_notices', 'notice_add', 'notices', 'notices_unread', '_emit_jobs', '_job_lock', '_job_seq', 'jobs', 'jobs_list', 'start_job', '_KINDS', '_PROJ_OFF', '_PROJ_RE', '_allowed', '_dashboard_worker', '_mins_until',
    '_open_projector', '_weather', '_weather_short', 'dashboard', 'file_card', 'handle_dashboard', 'handle_file_open',
    'handle_palette', 'handle_projector_state', 'hud_plus_start', 'projector_page', 'projector_state',
    'projector_voice', 'recent_image', 'suggestions',
]
