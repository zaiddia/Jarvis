"""Pruebas de la 12.70: cerrar el año escolar y modo vacaciones."""
import datetime
import os
import zipfile

import calendario_cali as CC
import horario


def test_calendario_cali():
    c = CC.CALI[2027]
    assert c["inicio_clases"] == datetime.date(2027, 1, 25) and sum(n for _a, _b, n in c["semestres"]) == 40
    assert CC.return_date(datetime.date(2026, 11, 30)) == datetime.date(2027, 1, 11)
    assert CC.return_date(datetime.date(2027, 7, 1)) == datetime.date(2027, 7, 19)
    titles = [t for t, _a, _b in CC.events(2027)]
    assert "Inicio de clases 2027" in titles and titles.count("Semana de desarrollo institucional") == 4


def test_modo_vacaciones(jv, monkeypatch):
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.settings, "vacation_until", "")
    monkeypatch.setitem(jv.settings, "year_reminder", "")
    monkeypatch.setattr(horario, "items", [{"dia": d, "inicio": "07:00", "fin": "07:55", "curso": "7A", "materia": "Matemáticas"}
                                           for d in range(5)])
    monkeypatch.setattr(horario, "off_until", None)
    jv._rec.clear()
    jv.process_command("activa el modo vacaciones")
    until = CC.return_date(datetime.date.today())
    assert jv.settings["vacation_until"] == until.isoformat() and "Felices vacaciones" in jv._rec.said()
    assert horario.today() == [] and horario.now_class() is None
    nx, day = horario.next_class()
    assert day is None or day >= until
    jv._rec.clear()
    import threading

    def tick():                                                                # un aviso automático (otro hilo, nadie lo pidió)
        jv.notify("Mañana vence la recuperación de Ana.", "RECUPERACIÓN")      # del colegio: no se dice
        jv.notify("Mañana pagas la luz.", "PAGOS")                             # lo personal, sí
    th = threading.Thread(target=tick)
    th.start()
    th.join()
    assert "recuperación" not in jv._rec.said() and "pagas la luz" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("¿estoy de vacaciones?")
    assert "Sí: estás de vacaciones" in jv._rec.said()
    jv._rec.clear()
    before = datetime.datetime.combine(until - datetime.timedelta(days=2), datetime.time(10))
    jv.vacation_tick(before)
    jv.vacation_tick(before)
    assert jv._rec.said().count("Se acaban las vacaciones") == 1
    jv._rec.clear()
    jv.vacation_tick(datetime.datetime.combine(until, datetime.time(7)))
    assert "Bienvenido" in jv._rec.said() and jv.settings["vacation_until"] == "" and horario.off_until is None
    jv.process_command("activa el modo vacaciones hasta el 20 de enero")
    assert jv.settings["vacation_until"].endswith("-01-20")
    jv.process_command("desactiva el modo vacaciones")
    assert jv.settings["vacation_until"] == "" and horario.today() != [] or datetime.date.today().weekday() >= 5


def test_cerrar_el_ano(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "docs"))
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    for k in ("year_start", "school_weeks", "period_current", "year_reminder", "vacation_until"):
        monkeypatch.setitem(jv.settings, k, jv.settings.get(k))
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Ana Ruiz", "Luis Gómez"], "8B": ["Juan Pérez"]})
    monkeypatch.setitem(jv.aula.data, "asistencia", {"7A": {"2026-11-03": ["Luis Gómez"]}})
    monkeypatch.setitem(jv.aula.data, "pendientes", {})
    monkeypatch.setattr(jv.aula, "save", lambda: None)
    monkeypatch.setattr(jv.seguimiento, "save", lambda: None)
    monkeypatch.setattr(jv.seguimiento, "data", {"7A": {"Ana Ruiz": [{"actividad": "Taller", "nota": 4.5, "fecha": "2026-10-01", "origen": "voz"}],
                                                         "Luis Gómez": [{"actividad": "Taller", "nota": 2.5, "fecha": "2026-10-01", "origen": "voz"}]}})
    zips = tmp_path / "copia.zip"
    with zipfile.ZipFile(zips, "w") as z:
        z.writestr("config.json", "{}")
    monkeypatch.setattr(jv, "make_backup", lambda kind="manual", include_secrets=None, upload=True: {"path": str(zips), "parts": [], "counts": {}})
    monkeypatch.setattr(jv.festivos, "data", {"eventos": []})
    monkeypatch.setattr(jv.festivos, "save", lambda: None)
    approvals = []
    monkeypatch.setattr(jv, "request_approval", lambda tipo, titulo, detalle="", on_ok=None, on_no=None, ttl=900, say=None, quiet=False:
                        approvals.append((titulo, detalle, on_ok)))
    jv._rec.clear()
    jv.process_command("cierra el año 2026")
    assert approvals and "2 estudiantes con notas" in approvals[0][1] and jv.aula.data["cursos"]["7A"]   # aún nada borrado
    approvals[0][2]()                                                          # «sí»
    folder = tmp_path / "docs" / "Cierre del año 2026"
    names = sorted(os.listdir(folder))
    assert "Copia completa de Jarvis 2026.zip" in names and "Resumen del año 2026.docx" in names and "Notas y asistencia 2026.xlsx" in names
    assert jv.aula.data["cursos"] == {"7A": [], "8B": []} and jv.aula.data["asistencia"] == {} and jv.seguimiento.data == {}
    assert jv.settings["year_start"] == "2027-01-25" and jv.settings["school_weeks"] == 40 and jv.settings["period_current"] == 1
    assert jv.settings["year_reminder"] == "2027-01-11" and len(jv.festivos.data["eventos"]) == len(CC.events(2027))
    said = jv._rec.said()
    assert "Cierre del año 2026" in said and "25 de enero" in said and "modo vacaciones" in said
    import docx
    txt = "\n".join(c.text for row in docx.Document(str(folder / "Resumen del año 2026.docx")).tables[0].rows for c in row.cells)
    assert "7A" in txt and "3,5" in txt
    jv.year_setup(2027)
    assert len(jv.festivos.data["eventos"]) == len(CC.events(2027))         # no se duplican
    jv._rec.clear()
    jv.year_reminder_tick(datetime.datetime(2027, 1, 11, 8))
    assert "vuelven los docentes" in jv._rec.said() and jv.settings["year_reminder"] == ""


def test_cerrar_sin_borrar(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    for k in ("year_start", "school_weeks", "period_current", "year_reminder"):
        monkeypatch.setitem(jv.settings, k, jv.settings.get(k))
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Ana Ruiz"]})
    monkeypatch.setattr(jv, "year_archive", lambda y: {"carpeta": str(tmp_path), "archivos": []})
    monkeypatch.setattr(jv, "year_setup", lambda y: 0)
    called = []
    monkeypatch.setattr(jv, "request_approval", lambda *a, **k: called.append(1))
    jv.process_command("cierra el año sin borrar nada")
    assert not called and jv.aula.data["cursos"]["7A"] == ["Ana Ruiz"]
