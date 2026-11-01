"""8.3: resumen semanal al celular, proyectos que se repiten y actualización automática de noche (con vuelta atrás).

Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import datetime
import os
import re
import sys
import threading
import time

import aprobaciones
import aula
import calendario
import diario
import horario
import notas
import proyectos
import seguimiento
import tareas
from nucleo import J

_DAYS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


# ============================================================================ RESUMEN SEMANAL
def weekly_summary(now=None):
    """Texto del resumen de la semana: lo hecho, lo pendiente, quién está en riesgo y lo que viene."""
    now = now or datetime.datetime.now()
    monday = (now - datetime.timedelta(days=now.weekday())).date()
    out = [f"📅 Tu semana ({monday:%d/%m} al {now:%d/%m})"]
    try:
        entries = diario.days(monday, now.date())
        if entries:
            out.append("• " + diario.spoken(entries, "esta semana"))
    except Exception:
        pass
    try:
        since = datetime.datetime.combine(monday, datetime.time(0)).timestamp()
        done = [p for p in proyectos.load_all() if float(p.get("creado") or 0) >= since]
        if done:
            out.append("• Proyectos: " + "; ".join(f"{p['nombre']} ({p.get('estado', '')})" for p in done[-4:]))
    except Exception:
        pass
    try:
        hist = aprobaciones.history(days=now.weekday() + 1)
        ok = sum(1 for e in hist if e["evento"] == "aprobada")
        if hist:
            out.append(f"• Aprobaste {ok} cosa(s) que hice por mi cuenta.")
    except Exception:
        pass
    pend = notas.pending()
    if pend:
        out.append(f"• Pendientes ({len(pend)}): " + "; ".join(notas.what(n) for n in pend[:6]) + ("…" if len(pend) > 6 else ""))
    risk_parts = []
    for course in sorted(set(aula.data.get("cursos", {})) | set(seguimiento.data), key=aula.course_sort_key)[:24]:
        names = sorted(set(aula.students(course)) | set(seguimiento.data.get(course, {})))
        r = seguimiento.at_risk(course, names, J._absences(course), J.settings["risk_grade"], J.settings["risk_absences"])
        if r:
            risk_parts.append(f"{course}: " + ", ".join(n for n, _ in r[:6]))
    if risk_parts:
        out.append("• En riesgo: " + " · ".join(risk_parts))
    nxt = []
    nmon = monday + datetime.timedelta(days=7)
    n_classes = sum(1 for x in horario.items if x["dia"] < 5)
    if n_classes:
        nxt.append(f"{n_classes} clases en tu horario")
    try:
        start = datetime.datetime.combine(nmon, datetime.time(0), tzinfo=datetime.datetime.now().astimezone().tzinfo)
        evs = [e for e in calendario.upcoming(now=start, limit=20)
               if datetime.datetime.fromisoformat(e["inicio"]).date() < nmon + datetime.timedelta(days=7)]
        if evs:
            nxt.append(f"{len(evs)} evento(s) en el calendario, el primero «{evs[0]['titulo']}»")
    except Exception:
        pass
    if nxt:
        out.append("• La próxima semana: " + "; ".join(nxt) + ".")
    if len(out) == 1:
        out.append("• Semana tranquila: no tengo nada anotado.")
    return "\n".join(out)


_WEEK_RE = re.compile(r"\b(?:resumen|informe|balance|reporte)\s+(?:semanal|de (?:la|mi|esta) semana)\b|\bcomo me fue (?:esta|en la) semana\b")
_week_state = {"sent": ""}


def weekly_voice(text, t):
    if not _WEEK_RE.search(t):
        return False
    J.reply(J.weekly_summary(), "SEMANA")
    return True


def weekly_tick(now=None):
    """Envía el resumen el día y la hora elegidos (una vez por semana). Devuelve el texto si lo envió."""
    now = now or datetime.datetime.now()
    s = J.settings
    if not s["weekly_summary"] or _DAYS.index(s["weekly_day"]) != now.weekday() or now.hour < s["weekly_hour"]:
        return None
    week = now.strftime("%G-%V")
    if _week_state["sent"] == week or J.settings["weekly_sent"] == week:
        return None
    _week_state["sent"] = week
    J.settings["weekly_sent"] = week
    try:
        J.save_settings_file()
    except OSError:
        pass
    text = J.weekly_summary(now)
    if not J.phone_send(text):
        J.push_chat("jarvis", text, "SEMANA")
    J.log_terminal("Resumen semanal enviado.", "SEMANA")
    return text


# ============================================================================ PROYECTOS QUE SE REPITEN
def recurring_project(text, t):
    """«cada domingo a las 6 prepárame la semana de 7A sobre fracciones» → tarea programada que arma el proyecto."""
    if not proyectos.is_project(re.sub(r"^.*?\b(?:a las?\s+\d{1,2}(?::\d{2})?\s*(?:a\s?m|p\s?m|de la manana|de la tarde|de la noche)?)\s*", "", t)):
        return False
    if not tareas.parse_voice(text):
        return False
    return J.tasks_voice(text, t)


# ============================================================================ ACTUALIZACIÓN AUTOMÁTICA DE NOCHE
def _busy():
    return bool(J.tts_playing.is_set() or J.project_run["busy"] or J.material_job["busy"] or J.upd["busy"]
                or aprobaciones.pending())


def night_update_tick(now=None):
    """Entre la 1 y las 5 de la mañana, si hay versión nueva y Jarvis está quieto, la instala (con copia de seguridad)."""
    now = now or datetime.datetime.now()
    if not (J.settings["update_auto"] and J.settings["update_night"]) or getattr(sys, "frozen", False):
        return False
    if not (1 <= now.hour < 5) or J.is_offline() or J._busy():
        return False
    if time.time() - J._upd_load().get("night_checked", 0) < 20 * 3600:
        return False
    J._upd_save(night_checked=time.time())
    info = J.check_updates()
    if not info.get("newer"):
        return False
    if info.get("version") and info["version"] == J._upd_load().get("rolled_back"):
        return False                                   # 11.8.1: la que se deshizo sola no se vuelve a instalar de noche
    J.log_terminal(f"Instalo de noche la versión {info['version']} (con copia de seguridad).", "ACTUALIZACIÓN")
    J._upd_save(just_updated=info["version"], boot_count=0, updated_from=J.VERSION)
    J.install_update()
    return True


def _pid_alive(pid):
    try:
        import psutil
        return psutil.pid_exists(int(pid))
    except Exception:
        return False


def _log_tail(offset, limit=2500):
    """El final de lo que escribió en el registro el arranque anterior (desde donde empezó)."""
    try:
        with open(J.LOG_PATH, "rb") as f:
            size = os.fstat(f.fileno()).st_size
            start = offset if 0 <= offset <= size else 0
            f.seek(max(start, size - limit))
            return f.read().decode("utf-8", "replace").strip()
    except OSError:
        return ""


def boot_guard():
    """Si la versión recién instalada se cierra sola 2 veces seguidas sin terminar de arrancar, vuelve a la anterior.
    11.8.1: solo cuentan los arranques que de verdad fallaron (el proceso murió sin salir bien y antes de 150 s);
    cerrar Jarvis, reiniciarlo o que Windows lo abra dos veces a la vez ya no cuenta como fallo. El final del registro
    del arranque que falló queda en el informe de errores."""
    st = J._upd_load()
    if st.get("just_updated") != J.VERSION:
        return None
    prev = st.get("boot") or {}
    fails = int(st.get("boot_fails", 0))
    if prev.get("pid") and int(prev["pid"]) != os.getpid() and not prev.get("clean") and not J._pid_alive(prev["pid"]):
        fails += 1
        tail = J._log_tail(int(prev.get("log_at", 0)))
        J.note_error("ACTUALIZACIÓN", f"la versión {J.VERSION} se cerró sin terminar de arrancar" + (f". Final del registro:\n{tail}" if tail else ""))
    try:
        log_at = os.path.getsize(J.LOG_PATH)
    except OSError:
        log_at = 0
    J._upd_save(boot={"pid": os.getpid(), "t": time.time(), "log_at": log_at, "clean": False}, boot_fails=fails)
    if fails >= 2:
        J._upd_save(just_updated="", boot_fails=0, boot={}, rolled_back=J.VERSION)
        J.log_terminal(f"La versión {J.VERSION} se cerró sola {fails} veces al arrancar: vuelvo a la anterior.", "ACTUALIZACIÓN")
        J.note_error("ACTUALIZACIÓN", f"la versión {J.VERSION} falló al arrancar; se deshizo sola")
        return J.rollback_update()

    def ok():
        J._upd_save(just_updated="", boot_fails=0, boot={})
        J.log_terminal(f"La versión {J.VERSION} arrancó bien.", "ACTUALIZACIÓN")
    t = threading.Timer(150.0, ok)
    t.daemon = True
    t.start()
    return fails


def boot_clean_exit():
    """Al salir bien (Salir, reiniciar, actualizar): este arranque no cuenta como fallo."""
    try:
        st = J._upd_load()
        b = st.get("boot") or {}
        if b.get("pid") == os.getpid():
            J._upd_save(boot=dict(b, clean=True))
    except Exception:
        pass


def _autonomy_worker():
    time.sleep(120)
    while True:
        for fn in (J.weekly_tick, J.night_update_tick):
            try:
                fn()
            except Exception as e:
                J.note_error("AUTONOMÍA", e)
        time.sleep(60)


def autonomy_start():
    J.boot_guard()
    threading.Thread(target=J._autonomy_worker, daemon=True, name="autonomia").start()


__all__ = ['_DAYS', '_WEEK_RE', '_autonomy_worker', '_busy', '_week_state', '_log_tail', '_pid_alive', 'autonomy_start', 'boot_clean_exit', 'boot_guard',
           'night_update_tick', 'recurring_project', 'weekly_summary', 'weekly_tick', 'weekly_voice']
