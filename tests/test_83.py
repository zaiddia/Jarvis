"""Pruebas de la 8.3: resumen semanal, proyectos que se repiten y actualización de noche con vuelta atrás."""
import datetime
import os

import horario
import notas
import seguimiento
import tareas


def test_resumen_semanal(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Juan Pérez", "Ana Gómez"]})
    monkeypatch.setitem(jv.aula.data, "asistencia", {})
    monkeypatch.setattr(seguimiento, "data", {"7A": {"Juan Pérez": [{"actividad": "quiz", "nota": 2.0, "fecha": "", "origen": "voz"}]}})
    monkeypatch.setattr(notas, "pending", lambda: [{"texto": "calificar talleres", "fecha": "", "hora": ""}])
    monkeypatch.setattr(notas, "what", lambda n: n["texto"])
    monkeypatch.setattr(horario, "items", [{"dia": 0, "inicio": "07:00", "fin": "07:55", "curso": "7A", "materia": "M"}])
    txt = jv.weekly_summary(datetime.datetime(2026, 10, 30, 16, 0))
    assert "Tu semana (26/10 al 30/10)" in txt and "calificar talleres" in txt and "7A: Juan Pérez" in txt
    assert "1 clases en tu horario" in txt
    jv._rec.clear()
    jv.process_command("dame el resumen semanal")
    assert "Tu semana" in jv._rec.said()


def test_resumen_una_vez_el_dia_elegido(jv, monkeypatch):
    sent = []
    monkeypatch.setattr(jv, "phone_send", lambda text: sent.append(text) or True)
    monkeypatch.setattr(jv, "weekly_summary", lambda now=None: "RESUMEN")
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.settings, "weekly_summary", True)
    monkeypatch.setitem(jv.settings, "weekly_day", "viernes")
    monkeypatch.setitem(jv.settings, "weekly_hour", 16)
    monkeypatch.setitem(jv.settings, "weekly_sent", "")
    jv._week_state["sent"] = ""
    assert jv.weekly_tick(datetime.datetime(2026, 10, 29, 17, 0)) is None     # jueves
    assert jv.weekly_tick(datetime.datetime(2026, 10, 30, 15, 0)) is None     # viernes, antes de la hora
    assert jv.weekly_tick(datetime.datetime(2026, 10, 30, 16, 5)) == "RESUMEN"
    assert jv.weekly_tick(datetime.datetime(2026, 10, 30, 17, 0)) is None     # una vez por semana
    assert sent == ["RESUMEN"]


def test_proyecto_que_se_repite(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(tareas, "_path", str(tmp_path / "tareas.json"))
    monkeypatch.setattr(tareas, "tasks", [])
    jv._rec.clear()
    jv.process_command("cada domingo a las 6 de la tarde prepárame la semana de 7A sobre fracciones")
    assert "tarea programada" in jv._rec.said()
    x = tareas.tasks[-1]
    assert x["cuando"] == "18:00 dom" and "semana de 7a sobre fracciones" in tareas.norm(x["orden"])


def test_actualizacion_de_noche(jv, monkeypatch):
    state = {}
    monkeypatch.setattr(jv, "_upd_load", lambda: dict(state))
    monkeypatch.setattr(jv, "_upd_save", lambda **kw: state.update(kw))
    monkeypatch.setattr(jv, "check_updates", lambda: {"newer": True, "version": "9.9"})
    monkeypatch.setattr(jv, "is_offline", lambda: False)
    monkeypatch.setattr(jv, "_busy", lambda: False)
    installed = []
    monkeypatch.setattr(jv, "install_update", lambda: installed.append(1))
    monkeypatch.setitem(jv.settings, "update_auto", True)
    monkeypatch.setitem(jv.settings, "update_night", True)
    assert jv.night_update_tick(datetime.datetime(2026, 10, 30, 14, 0)) is False      # de día no
    assert jv.night_update_tick(datetime.datetime(2026, 10, 31, 2, 0)) is True
    assert installed == [1] and state["just_updated"] == "9.9" and state["updated_from"] == jv.VERSION
    assert jv.night_update_tick(datetime.datetime(2026, 10, 31, 3, 0)) is False       # una vez por noche
    monkeypatch.setattr(jv, "_busy", lambda: True)
    state.pop("night_checked")
    assert jv.night_update_tick(datetime.datetime(2026, 10, 31, 3, 0)) is False       # ocupado: espera


def test_vuelta_atras_si_no_arranca(jv, monkeypatch, tmp_path):
    """11.8.1: solo cuentan los arranques que de verdad murieron (no cerrar, reiniciar ni abrirlo dos veces)."""
    state = {"just_updated": jv.VERSION}
    monkeypatch.setattr(jv, "_upd_load", lambda: dict(state))
    monkeypatch.setattr(jv, "_upd_save", lambda **kw: state.update(kw))
    log = tmp_path / "jarvis.log"
    log.write_text("antes\n[ARRANQUE] Iniciando\nTraceback: algo falló\n", encoding="utf-8")
    monkeypatch.setattr(jv, "LOG_PATH", str(log))
    errs = []
    monkeypatch.setattr(jv, "note_error", lambda origin, e, cmd="": errs.append(str(e)))
    rolled = []
    monkeypatch.setattr(jv, "rollback_update", lambda: rolled.append(1) or {"ok": True})
    alive = set()
    monkeypatch.setattr(jv, "_pid_alive", lambda pid: int(pid) in alive)
    timers = []

    class T:
        def __init__(self, delay, fn):
            timers.append(fn)

        def start(self):
            pass
    monkeypatch.setattr(jv.threading, "Timer", T)
    assert jv.boot_guard() == 0 and state["boot"]["pid"] == os.getpid()           # primer arranque
    state["boot"] = {"pid": 999991, "log_at": 6, "clean": True}                  # salió bien: no cuenta
    assert jv.boot_guard() == 0
    alive.add(999992)
    state["boot"] = {"pid": 999992, "log_at": 6, "clean": False}                 # otro Jarvis vivo (abierto dos veces): no cuenta
    assert jv.boot_guard() == 0
    state["boot"] = {"pid": 999993, "log_at": 6, "clean": False}                 # murió sin salir bien: cuenta
    assert jv.boot_guard() == 1 and "se cerró sin terminar de arrancar" in errs[-1] and "Traceback: algo falló" in errs[-1]
    state["boot"] = {"pid": 999994, "log_at": 0, "clean": False}
    assert jv.boot_guard() == {"ok": True} and rolled == [1] and state["just_updated"] == "" and state["rolled_back"] == jv.VERSION
    state.update(just_updated=jv.VERSION, boot_fails=0, boot={})
    jv.boot_guard()
    timers[-1]()                                                   # arrancó bien: se limpia
    assert state["just_updated"] == "" and jv.boot_guard() is None
    state.update(just_updated=jv.VERSION, boot={"pid": os.getpid(), "log_at": 0, "clean": False})
    jv.boot_clean_exit()
    assert state["boot"]["clean"]


def test_la_deshecha_no_se_reinstala_de_noche(jv, monkeypatch):
    state = {"rolled_back": "9.9"}
    monkeypatch.setattr(jv, "_upd_load", lambda: dict(state))
    monkeypatch.setattr(jv, "_upd_save", lambda **kw: state.update(kw))
    monkeypatch.setattr(jv, "check_updates", lambda: {"newer": True, "version": "9.9"})
    monkeypatch.setattr(jv, "is_offline", lambda: False)
    monkeypatch.setattr(jv, "_busy", lambda: False)
    monkeypatch.setattr(jv, "install_update", lambda: (_ for _ in ()).throw(AssertionError("no debía instalar")))
    monkeypatch.setitem(jv.settings, "update_auto", True)
    monkeypatch.setitem(jv.settings, "update_night", True)
    assert jv.night_update_tick(datetime.datetime(2026, 10, 31, 2, 0)) is False


def test_un_solo_jarvis_a_la_vez(jv, tmp_path, monkeypatch):
    lock = str(tmp_path / "jarvis.lock")
    assert jv.take_instance_lock(lock) and open(lock).read() == str(os.getpid())
    assert jv.take_instance_lock(lock)                             # el candado es mío
    with open(lock, "w") as f:
        f.write("999995")                                          # de un proceso que ya no existe: se toma
    assert jv.take_instance_lock(lock) and open(lock).read() == str(os.getpid())
    import psutil

    class P:
        def __init__(self, pid=None):
            self.pid = pid if pid is not None else os.getpid()
    with open(lock, "w") as f:
        f.write("999996")
    monkeypatch.setattr(psutil, "Process", P)
    monkeypatch.setattr(jv, "_proc_is_jarvis", lambda p, allow_self=False: p.pid == 999996)
    assert jv.take_instance_lock(lock) is False                    # otro Jarvis vivo lo tiene
    jv.release_instance_lock(lock)
    assert os.path.exists(lock)                                    # no es mío: no lo borro
    with open(lock, "w") as f:
        f.write(str(os.getpid()))
    jv.release_instance_lock(lock)
    assert not os.path.exists(lock)