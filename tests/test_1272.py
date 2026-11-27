"""Pruebas de la 12.72: las funciones se encienden solas o por voz, sin ir a Ajustes."""


def _settings(jv, monkeypatch, **kv):
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    for k, v in kv.items():
        monkeypatch.setitem(jv.settings, k, v)


def test_activar_y_desactivar_por_voz(jv, monkeypatch):
    _settings(jv, monkeypatch, night_shift=False, quake_alerts=False, morning_news=False, copilot_enabled=False)
    jv._rec.clear()
    jv.process_command("activa el turno de noche")                           # (ya tenía su propia orden: se respeta)
    assert jv.settings["night_shift"] is True
    _settings(jv, monkeypatch, schedule_warn=False)
    jv._rec.clear()
    jv.process_command("activa el aviso antes de cada clase")
    assert jv.settings["schedule_warn"] is True and "encendí el aviso antes de cada clase" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("avísame de los sismos")
    assert jv.settings["quake_alerts"] is True, jv._rec.said()
    jv.process_command("enciende las noticias del reporte de la mañana")
    assert jv.settings["morning_news"] is True
    jv._rec.clear()
    jv.process_command("desactiva el aviso antes de cada clase")
    assert jv.settings["schedule_warn"] is False and "apagué el aviso antes de cada clase" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("desactiva el aviso antes de cada clase")
    assert "ya está apagado" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("¿qué funciones tengo apagadas?")
    assert "el aviso antes de cada clase" in jv._rec.said() and "el copiloto" in jv._rec.said()
    assert jv.feature_find("los temblores") == "quake_alerts" and jv.feature_find("la música") == ""


def test_lo_que_falta_y_lo_delicado(jv, monkeypatch):
    _settings(jv, monkeypatch, telegram_remote=False, telegram_token="", telegram_chat="", privacy_students=True)
    jv._rec.clear()
    jv.process_command("activa las órdenes por telegram")
    assert jv.settings["telegram_remote"] is True and "falta conectar Telegram" in jv._rec.said()
    asked = []
    monkeypatch.setattr(jv, "request_approval", lambda *a, **k: asked.append(k.get("on_ok")))
    jv.process_command("desactiva ocultar los nombres de los estudiantes")
    assert asked and jv.settings["privacy_students"] is True             # pide permiso: aún no cambia
    asked[0]()
    assert jv.settings["privacy_students"] is False


def test_se_encienden_solas(jv, monkeypatch, tmp_path):
    _settings(jv, monkeypatch, diary_enabled=False, history_enabled=False, mobile_enabled=False)
    monkeypatch.setitem(jv._said, "diary_enabled", 0)
    jv._rec.clear()
    jv.process_command("¿qué hice ayer?")
    assert jv.settings["diary_enabled"] is True and "Encendí el diario" in jv._rec.said()
    assert "Ajustes" not in jv._rec.said()
    started = []

    def fake_apply():
        started.append(1)
        jv.mobile["server"] = object()
    monkeypatch.setattr(jv, "mobile_apply", fake_apply)
    monkeypatch.setattr(jv, "MOBILE_AUTO", True)
    monkeypatch.setitem(jv.mobile, "server", None)
    jv._rec.clear()
    assert jv._need_lan() is False and jv.settings["mobile_enabled"] is True and "panel del celular" in jv._rec.said()
    monkeypatch.setitem(jv.mobile, "server", None)


def test_la_ia_no_manda_a_ajustes(jv):
    assert "activa el turno de noche" in jv.AUTO_RULE and "AUTO_RULE" not in jv.system_static()
    assert "no lo mandes a Ajustes" in jv.system_static()
