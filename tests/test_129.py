"""Pruebas de la 12.9: modos Docente / Asistente general, disparadores, el PC con órdenes del sistema, gastos, pagos,
listas y Home Assistant."""
import datetime as dt

import pytest

import casa
import equipo
import vidadiaria as vd


@pytest.fixture
def vida(tmp_path):
    vd.configure(str(tmp_path))
    yield vd
    vd.configure(str(tmp_path / "limpio"))


# ============================================================================ LÓGICA PURA
def test_dinero_y_categorias():
    for txt, want in (("20 mil", 20000), ("$15.000", 15000), ("1,5 millones", 1500000), ("un millón", 1000000), ("35.500", 35500),
                      ("2.5 lucas", 2500), ("12k", 12000), ("20000 pesos", 20000)):
        assert vd.parse_amount(txt) == want, txt
    assert vd.money(1234567) == "$1.234.567" and vd.money_spoken(20000) == "20 mil pesos"
    assert vd.category("almuerzo") == "Comida" and vd.category("taxi al colegio") == "Transporte" and vd.category("recibo de la luz") == "Servicios"
    assert vd.category("algo raro") == "Otros"


def test_gastos_y_pagos(vida):
    today = dt.date(2026, 11, 20)
    vd.add_expense(20000, "almuerzo", today)
    vd.add_expense(5000, "bus", today)
    vd.add_expense(90000, "mercado", dt.date(2026, 10, 3))
    tot, by, n = vd.spent("mes", today)
    assert (tot, n) == (25000, 2) and list(by) == ["Comida", "Transporte"]
    assert vd.spent("mes_pasado", today)[0] == 90000 and vd.spent("mes", today, cat="Transporte")[0] == 5000
    assert vd.undo_last_expense()["monto"] == 90000
    vd.add_payment("internet", 22, 90000, today)
    vd.add_payment("arriendo", 5, today=today)
    up = vd.upcoming(today, 5)
    assert [(p["nombre"], left) for p, _d, left in up] == [("internet", 2)]
    assert [p["nombre"] for p, _d, _l in vd.payments_to_warn(today)] == ["internet"]
    assert vd.payments_to_warn(today) == []                                     # no se repite el mismo día
    vd.mark_paid("internet", today)
    assert vd.upcoming(today, 5) == []                                          # pagado: el próximo es en diciembre
    assert vd.when_text(0) == "hoy" and vd.when_text(-2) == "hace 2 días"
    assert vd.remove_payment("arriendo")["nombre"] == "arriendo" and len(vd.data["pagos"]) == 1


def test_listas(vida):
    assert vd.list_name("del mercado") == "mercado" and vd.list_name("de compras") == "mercado" and vd.list_name("de clase") == ""
    assert vd.split_items("leche, pan y unos huevos") == ["leche", "pan", "huevos"]
    assert vd.add_items("mercado", ["leche", "pan"]) == ["leche", "pan"] and vd.add_items("mercado", ["leche"]) == []
    assert vd.check_items(["leche"]) == [("mercado", "leche")] and vd.pending_items("mercado") == ["pan"]
    assert vd.remove_items("mercado", ["pan"]) == ["pan"] and vd.pending_items("mercado") == []


def test_disparadores(vida):
    cases = {"cuando conecte el cargador, modo general": ("cargador_on", "", "modo general"),
             "cuando desconecte el cargador activa el ahorro de bateria": ("cargador_off", "", "activa el ahorro de bateria"),
             "cuando me conecte al wifi Colegio San José, modo docente": ("wifi", "colegio san jose", "modo docente"),
             "cuando abra excel silencia las notificaciones": ("app", "excel", "silencia las notificaciones"),
             "cuando la batería esté al 15 %, activa el ahorro de batería": ("bateria_baja", "15", "activa el ahorro de bateria"),
             "cuando encienda el pc, dame el resumen de la mañana": ("encender", "", "dame el resumen de la manana")}
    for txt, (ev, val, act) in cases.items():
        tr = vd.parse_trigger(txt)
        assert tr == {"evento": ev, "valor": val, "accion": act}, txt
        assert vd.add_trigger(tr)
    assert vd.parse_trigger("cuando llueva haz algo") is None and vd.add_trigger({"evento": "app", "valor": "x", "accion": "cuando algo"}) is None
    assert [x["accion"] for x in vd.fire([("app", "Excel excel.exe")])] == ["silencia las notificaciones"]
    assert [x["evento"] for x in vd.fire([("wifi", "Colegio San José")])] == ["wifi"] and not vd.fire([("wifi", "Casa")])
    assert vd.fire([("bateria_baja", 30)]) == [] and len(vd.fire([("bateria_baja", 14)])) == 1
    assert "cargador" in vd.describe(vd.data["disparadores"][0]).lower()
    assert vd.remove_trigger("1")["evento"] == "cargador_on" and vd.remove_trigger("excel")["evento"] == "app"


def test_modos():
    assert vd.resolve_mode("general") == "general" and vd.resolve_mode("docente") == "docente"
    assert vd.resolve_mode("auto", ssid="Colegio", school_wifi="Casa, colegio") == "docente"
    assert vd.resolve_mode("auto", in_class=True) == "docente" and vd.resolve_mode("auto", has_schedule=True) == "general"
    assert vd.resolve_mode("auto", has_schedule=False) == "docente"                # sin horario ni Wi-Fi: como siempre
    items = [{"dia": 0, "inicio": "07:00", "fin": "08:00"}, {"dia": 0, "inicio": "11:00", "fin": "12:30"}]
    mon = dt.datetime(2026, 11, 9, 6, 40)
    assert vd.school_hours(items, mon) and vd.school_hours(items, mon.replace(hour=12, minute=55))
    assert not vd.school_hours(items, mon.replace(hour=14)) and not vd.school_hours(items, mon + dt.timedelta(days=5))


def test_winget_y_sistema():
    out = """   - \\ |
Nombre                       Id                        Versión       Disponible   Origen
-------------------------------------------------------------------------------------
Google Chrome                Google.Chrome             130.0.1       131.0.2      winget
VLC media player             VideoLAN.VLC              3.0.18        3.0.21       winget
2 actualizaciones disponibles.
"""
    rows = equipo.parse_table(out)
    assert [(r["name"], r["id"], r["available"]) for r in rows] == [("Google Chrome", "Google.Chrome", "131.0.2"), ("VLC media player", "VideoLAN.VLC", "3.0.21")]
    assert equipo.best_package(rows, "vlc")["id"] == "VideoLAN.VLC" and equipo.best_package(rows, "chrome")["id"] == "Google.Chrome"
    assert equipo.best_package(rows, "zoom") is None
    assert equipo.winget_install("VideoLAN.VLC")[:4] == ["winget", "install", "--id", "VideoLAN.VLC"] and "--silent" in equipo.winget_install("x")
    plans = equipo.parse_plans("GUID del plan de energía: 381b4222-f694-41f0-9685-ff5bb260df2e  (Equilibrado) *\n"
                               "Power Scheme GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (High performance)")
    assert plans[0]["active"] and equipo.pick_plan(plans, "alto")["name"] == "High performance" and equipo.pick_plan(plans, "ahorro") is None
    assert equipo.parse_ssid("  Nombre : Wi-Fi\n  SSID : Casa 5G\n  BSSID : aa") == "Casa 5G" and equipo.parse_ssid("") == ""
    assert equipo.parse_profiles("Perfiles\n    Perfil de todos los usuarios     : Casa\n    All User Profile : Colegio") == ["Casa", "Colegio"]
    top = equipo.top_processes([{"name": "chrome.exe", "rss": 5e8, "cpu": 3}, {"name": "chrome.exe", "rss": 4e8, "cpu": 2},
                                {"name": "Code.exe", "rss": 6e8, "cpu": 0}])
    assert top[0]["name"] == "chrome.exe" and top[0]["rss"] == 9e8 and equipo.friendly("WINWORD.EXE") == "Word"
    assert not equipo.can_close("explorer.exe") and not equipo.can_close("svchost.exe") and equipo.can_close("chrome.exe")
    assert equipo.approved_enabled(b"\x02" + b"\x00" * 11) and not equipo.approved_enabled(equipo.approved_value(False, 5))
    sc = equipo.radio_script(["Bluetooth"], "Off")
    assert "SetStateAsync('Off')" in sc and "'Bluetooth'" in sc and "SetStateAsync" not in equipo.radio_script(["WiFi"])
    assert equipo.parse_radios("WiFi=On\nBluetooth=Off") == {"WiFi": "On", "Bluetooth": "Off"}


def test_temporales(tmp_path):
    import os
    import time
    old, new = tmp_path / "viejo.tmp", tmp_path / "nuevo.tmp"
    old.write_bytes(b"x" * 1000)
    new.write_bytes(b"y" * 10)
    os.utime(old, (time.time() - 3 * 86400,) * 2)
    files, total = equipo.temp_candidates([str(tmp_path)])
    assert files == [str(old)] and total == 1000 and equipo.gb(2.5e9) == "2,5 GB"


def test_casa():
    assert casa.parse("enciende la luz de la sala") == {"accion": "on", "nombre": "luz de la sala", "brillo": None}
    assert casa.parse("luz del cuarto al 40 %")["brillo"] == 40 and casa.parse("apaga el ventilador")["accion"] == "off"
    assert casa.parse("esta prendida la luz de la cocina")["accion"] == "estado"
    ents = casa.entities([{"entity_id": "light.sala", "state": "off", "attributes": {"friendly_name": "Luz de la sala"}},
                          {"entity_id": "fan.cuarto", "state": "on", "attributes": {"friendly_name": "Ventilador"}},
                          {"entity_id": "sensor.temp", "state": "21"}])
    assert [e["id"] for e in ents] == ["light.sala", "fan.cuarto"]
    assert casa.match(ents, "luz de la sala")["id"] == "light.sala" and casa.match(ents, "ventilador")["id"] == "fan.cuarto"
    assert casa.match(ents, "equipo") is None and casa.match(ents, "spotify") is None
    assert casa.service(ents[0], "on", 40) == ("light", "turn_on", {"entity_id": "light.sala", "brightness_pct": 40})
    assert casa.service({"id": "cover.x", "dominio": "cover"}, "off")[1] == "close_cover"
    assert casa.spoken_state(ents[1]) == "Ventilador: encendido."


# ============================================================================ JARVIS
def test_frases_del_asistente(jv, monkeypatch, vida):
    import nucleo.equipopc as pc
    hits = []
    monkeypatch.setattr(pc, "_install", lambda name, origin="": hits.append(("instalar", name)))
    monkeypatch.setattr(pc, "_ask_upgrades", lambda origin="", do_all=False: hits.append(("actualizar", do_all)))
    monkeypatch.setattr(pc, "_slow_report", lambda origin="": hits.append(("lento",)))
    monkeypatch.setattr(pc, "_clean_temp", lambda origin="": hits.append(("temporales",)))
    monkeypatch.setattr(pc, "_radios", lambda kinds, state, origin="": hits.append(("radio", tuple(kinds), state)))
    monkeypatch.setattr(pc, "_power_plan", lambda want, origin="": hits.append(("plan", want)))
    monkeypatch.setattr(pc, "_battery_saver", lambda on, origin="": hits.append(("ahorro", on)))
    monkeypatch.setattr(pc, "focus_start", lambda m=25, origin="": hits.append(("foco", m)))
    monkeypatch.setattr(jv, "IS_WIN", True)
    for text in ("instala VLC", "actualiza todos mis programas", "¿qué programas tienen actualización?", "¿qué está poniendo lento el PC?",
                 "limpia los temporales", "apaga el bluetooth", "activa el wifi", "modo avión", "plan de energía alto rendimiento",
                 "activa el ahorro de batería", "modo concentración 40 minutos"):
        jv._rec.clear()
        jv.process_command(text)
    assert hits == [("instalar", "vlc"), ("actualizar", True), ("actualizar", False), ("lento",), ("temporales",), ("radio", ("Bluetooth",), "Off"),
                    ("radio", ("WiFi",), "On"), ("radio", ("WiFi", "Bluetooth", "MobileBroadband"), "Off"), ("plan", "alto"), ("ahorro", True),
                    ("foco", 40)]
    # lo de Jarvis sigue siendo de Jarvis
    hits.clear()
    asked = []
    monkeypatch.setattr(jv, "request_approval", lambda tipo, titulo, detalle="", on_ok=None, on_no=None, **k: asked.append(titulo))
    jv._rec.clear()
    jv.process_command("instala ollama")
    assert not hits and asked and "Ollama" in asked[-1]


def test_gastos_listas_y_pagos_por_voz(jv, vida):
    for text in ("Gasté 20 mil en almuerzo", "compré pan por 5.000", "agrega leche, pan y huevos a la lista del mercado",
                 "recuérdame pagar el internet el 15 de cada mes de 90 mil", "ya compré leche"):
        jv._rec.clear()
        jv.process_command(text)
    assert [g["monto"] for g in vd.data["gastos"]] == [20000, 5000] and vd.data["gastos"][1]["concepto"] == "pan"
    assert vd.pending_items("mercado") == ["pan", "huevos"]
    assert vd.data["pagos"][0]["nombre"] == "internet" and vd.data["pagos"][0]["dia"] == 15 and vd.data["pagos"][0]["monto"] == 90000
    jv._rec.clear()
    jv.process_command("¿cuánto he gastado este mes?")
    assert "$25.000" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("¿qué hay en la lista del mercado?")
    assert "pan, huevos" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("ya pagué el internet")
    assert vd.data["pagos"][0]["pagado"] == dt.date.today().strftime("%Y-%m")
    # «lista de clase» no es una lista personal
    assert not jv.list_voice("agrega a Juan a la lista de clase", "agrega a juan a la lista de clase")


def test_modo_y_disparadores_por_voz(jv, monkeypatch, vida):
    applied = {}
    monkeypatch.setattr(jv, "apply_settings", lambda d: applied.update(d) or jv.settings.update(d))
    jv._rec.clear()
    jv.process_command("modo general")
    assert applied["assistant_mode"] == "general" and jv.current_mode() == "general" and "MODO ASISTENTE GENERAL" in jv.system_static()
    jv.process_command("modo docente")
    assert jv.current_mode() == "docente" and "MODO DOCENTE" in jv.system_static()
    jv.process_command("modo automático")
    assert jv.settings["assistant_mode"] == "auto"
    jv._rec.clear()
    jv.process_command("cuando conecte el cargador, modo general")
    assert vd.data["disparadores"][0]["evento"] == "cargador_on" and "cargador" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("¿qué disparadores tengo?")
    assert "1." in jv._rec.said()
    # el cargador se conecta: corre la acción
    import nucleo.modos as mo
    ran = []
    monkeypatch.setattr(mo, "_run_trigger", lambda x: ran.append(x["accion"]))

    class Bat:
        def __init__(self, plugged, pct):
            self.power_plugged, self.percent = plugged, pct

    class PS:
        bat = Bat(False, 50)

        @staticmethod
        def sensors_battery():
            return PS.bat

        @staticmethod
        def process_iter(attrs=None):
            return []
    monkeypatch.setattr(jv, "psutil", PS)
    told = []
    monkeypatch.setattr(jv, "notify", lambda t, o="": told.append(t))
    mo.mode_state.update(plugged=None, warned={"low": False, "critical": False})
    mo._tick()
    PS.bat = Bat(True, 51)
    mo._tick()
    assert ran == ["modo general"]
    PS.bat = Bat(False, 19)
    mo._tick()
    mo._tick()
    assert len([x for x in told if "19 %" in x]) == 1                            # un solo aviso de batería baja
    jv.process_command("borra el disparador 1")
    assert vd.data["disparadores"] == []


def test_casa_por_voz(jv, monkeypatch):
    import nucleo.diaadia as dd
    monkeypatch.setitem(jv.settings, "ha_url", "http://192.168.1.20:8123")
    monkeypatch.setitem(jv.settings, "ha_token", "t")
    calls = []

    def call(method, path, body=None, timeout=6):
        calls.append((method, path, body))
        return [{"entity_id": "light.sala", "state": "off", "attributes": {"friendly_name": "Luz de la sala"}}] if path == "/api/states" else {}
    monkeypatch.setattr(dd, "_ha_call", call)
    dd._ha_cache.update(t=0.0, ents=[], fail=0.0)
    jv._rec.clear()
    jv.process_command("enciende la luz de la sala al 60 %")
    assert calls[-1] == ("POST", "/api/services/light/turn_on", {"entity_id": "light.sala", "brightness_pct": 60}) and "Encendí" in jv._rec.said()
    calls.clear()
    assert not jv.home_voice("abre spotify", "abre spotify")                      # no es de la casa: sigue su camino
    assert not jv.home_voice("apaga el equipo", "apaga el equipo")
    assert not any(c[0] == "POST" for c in calls)


def test_concentracion(jv, monkeypatch):
    import nucleo.equipopc as pc
    notif = []
    monkeypatch.setattr(pc.skills, "notifications", lambda a="silenciar": notif.append(a))
    monkeypatch.setattr(jv, "add_timer", lambda s, label="": None)
    monkeypatch.setattr(jv, "IS_WIN", False)
    jv._rec.clear()
    pc.focus_start(30)
    assert notif == ["silenciar"] and "30 minutos" in jv._rec.said() and pc.pc_state["focus_until"]
    pc.focus_end()
    assert notif == ["silenciar", "activar"] and not pc.pc_state["focus_until"]
