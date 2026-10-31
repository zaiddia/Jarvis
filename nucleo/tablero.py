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
    out["clase"] = {"ahora": horario.label(x) if x else "", "hasta": x["fin"] if x else "",
                    "falta": _mins_until(x["fin"], now) if x else None,
                    "siguiente": horario.label(nx) if nx else "", "a_las": nx["inicio"] if nx else "",
                    "hoy": bool(nx and day == now.date()),
                    "en": _mins_until(nx["inicio"], now) if nx and day == now.date() else None}
    try:
        evs = calendario.upcoming(limit=3)
        out["agenda"] = [{"t": e["titulo"][:60], "h": e["inicio"][11:16], "d": e["inicio"][:10]} for e in evs]
    except Exception:
        out["agenda"] = []
    out["clima"] = _weather_short()
    pend = notas.pending()
    out["pendientes"] = [notas.what(n)[:80] for n in pend[:5]]
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
    for course in sorted(set(aula.data.get("cursos", {})) | set(seguimiento.data))[:8]:
        names = sorted(set(aula.data.get("cursos", {}).get(course, [])) | set(seguimiento.data.get(course, {})))
        r = seguimiento.at_risk(course, names, J._absences(course), J.settings["risk_grade"], J.settings["risk_absences"])
        if r:
            risk.append({"curso": course, "n": len(r), "nombres": [n for n, _ in r[:3]]})
    out["riesgo"] = risk
    out["sugerencias"] = suggestions(now, out)
    return out


def suggestions(now, d):
    """Botones rápidos según el momento: [{"t": texto del botón, "cmd": orden, "fill": True si hay que completarla}]."""
    s = []
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
    seen, out = set(), []
    for x in s:
        if x["cmd"] not in seen:
            seen.add(x["cmd"])
            out.append(x)
    return out[:7]


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
    'RecentFiles', '_IMG', '_KINDS', '_PROJ_OFF', '_PROJ_RE', '_allowed', '_dashboard_worker', '_mins_until',
    '_open_projector', '_weather', '_weather_short', 'dashboard', 'file_card', 'handle_dashboard', 'handle_file_open',
    'handle_palette', 'handle_projector_state', 'hud_plus_start', 'projector_page', 'projector_state',
    'projector_voice', 'recent_image', 'suggestions',
]
