"""Pruebas de la 12.55: frases que van directo sin la IA, frases ya entendidas y avisos al celular cuando no estás."""
import datetime
import time

import skills


# ---------------------------------------------------------------- órdenes directas nuevas (sin la IA)
def test_parse_directo():
    assert skills.parse("baja el brillo") == ("brillo", {"nivel": "bajar"})
    assert skills.parse("sube el brillo de la pantalla") == ("brillo", {"nivel": "subir"})
    assert skills.parse("más brillo") == ("brillo", {"nivel": "subir"})
    assert skills.parse("brillo al 50") == ("brillo", {"nivel": "50"})
    assert skills.parse("apaga la pantalla") == ("apagar_pantalla", {})
    assert skills.parse("apaga el equipo")[0] == "apagar"
    assert skills.parse("pon música") == ("youtube", {"consulta": "mix de música"})
    assert skills.parse("pon música relajante") == ("youtube", {"consulta": "música relajante"})
    assert skills.parse("pon algo de salsa") == ("youtube", {"consulta": "música salsa"})
    assert skills.parse("pon un poco de vallenato") == ("youtube", {"consulta": "música vallenato"})
    assert skills.parse("pon algo de tiempo") is None
    assert skills.parse("manda un mensaje a mamá por whatsapp diciendo que ya voy") == ("whatsapp", {"contacto": "mamá", "mensaje": "ya voy"})
    assert skills.parse("escríbele a Juan por WhatsApp que llego tarde") == ("whatsapp", {"contacto": "Juan", "mensaje": "llego tarde"})
    assert skills.parse("manda un whatsapp a Ana que llego tarde") == ("whatsapp", {"contacto": "Ana", "mensaje": "llego tarde"})


def test_brillo_relativo(monkeypatch):
    calls = []

    class R:
        returncode = 0
    monkeypatch.setattr(skills, "_brightness_now", lambda: 70)
    monkeypatch.setattr(skills.subprocess, "run", lambda args, **k: (calls.append(args[-1]), R())[1])
    assert skills.REGISTRY["brillo"].fn(nivel="bajar") == "Brillo al 50 %."
    assert skills.REGISTRY["brillo"].fn(nivel="subir") == "Brillo al 90 %." and "WmiSetBrightness(1,90)" in calls[-1]
    monkeypatch.setattr(skills, "_brightness_now", lambda: None)
    try:
        skills.REGISTRY["brillo"].fn(nivel="subir")
        assert False
    except skills.SkillError as e:
        assert "no permite" in str(e)


def test_ruteo_sin_ia(jv):
    for frase, quien in (("baja el brillo", "skill:brillo"), ("pon música relajante", "skill:youtube"), ("apaga la pantalla", "skill:apagar_pantalla"),
                         ("manda un mensaje a mamá por whatsapp diciendo que ya voy", "skill:whatsapp")):
        jv._rec.clear()
        jv.process_command(frase)
        assert jv._rec.who() == quien, frase
        assert not jv._rec.ai


def test_respuestas_al_instante(jv, monkeypatch):
    for frase in ("gracias jarvis", "muchas gracias", "perfecto gracias", "buenas noches", "chao jarvis"):
        jv._rec.clear()
        jv.process_command(frase)
        assert jv._rec.replies and not jv._rec.ai, frase
    monkeypatch.setattr(jv.rutinas, "routines", [{"nombre": "buenas noches", "frases": [], "acciones": []}])
    jv._rec.clear()
    jv.process_command("buenas noches")
    assert jv._rec.routines == ["buenas noches"]                 # si tienes esa rutina, manda ella


def test_alias(jv, monkeypatch):
    ran = []
    monkeypatch.setattr(jv, "nl_run", lambda o: (ran.append(o), True)[1])
    for frase, orden in (("qué recordatorios tengo", "qué tengo pendiente"), ("lee mis correos", "revisa mi correo"),
                         ("cuántos estudiantes perdieron en 9A", "quiénes van perdiendo en 9a"), ("cuántos perdieron", "quiénes van perdiendo")):
        jv._rec.clear()
        jv.process_command(frase)
        assert ran[-1] == orden and not jv._rec.ai, frase


def test_alias_de_verdad(jv):
    jv._rec.clear()
    jv.process_command("qué recordatorios tengo")
    assert jv._rec.who() == "NOTAS" and not jv._rec.ai
    jv._rec.clear()
    jv.process_command("lee mis correos")                        # va a la bandeja (sin cuenta: lo dice), nunca se cuelga en bucle
    assert not jv._rec.ai


def test_velocidad_de_voz(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "tts_rate", 0)
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    jv._rec.clear()
    jv.process_command("habla más despacio")
    assert jv.settings["tts_rate"] == -15 and "despacio" in jv._rec.said()
    jv.process_command("más rápido")
    assert jv.settings["tts_rate"] == 0
    monkeypatch.setitem(jv.settings, "tts_rate", 50)
    jv._rec.clear()
    jv.process_command("habla más rápido")
    assert jv.settings["tts_rate"] == 50 and "lo más rápido" in jv._rec.said()


# ---------------------------------------------------------------- frases ya entendidas
def test_memo(jv, monkeypatch):
    ran = []
    monkeypatch.setattr(jv, "nl_run", lambda o: (ran.append(o), True)[1])
    jv.r55_memo_put("ponme la de los cumpleanos", "pon cumpleaños feliz en youtube")
    assert jv._r55_memo().get("ponme la de los cumpleanos", {}).get("orden") == "pon cumpleaños feliz en youtube"
    monkeypatch.setitem(jv.state, "ai", "off")                                   # aunque la IA esté apagada, va directo
    assert jv.nl_understand("ponme la de los cumpleaños", "ponme la de los cumpleanos") is True
    assert ran == ["pon cumpleaños feliz en youtube"]
    monkeypatch.setattr(jv, "nl_run", lambda o: False)                           # ya no sirve: la olvida
    jv._tl.nl_tried = ""
    assert jv.r55_memo_try("ponme la de los cumpleaños", "ponme la de los cumpleanos") is False
    assert "ponme la de los cumpleanos" not in jv._r55_memo()


def test_memo_delicado_y_privado(jv, monkeypatch):
    jv.r55_memo_put("ya no quiero ese archivo", "borra el archivo")
    assert "ya no quiero ese archivo" not in jv._r55_memo()
    monkeypatch.setitem(jv.priv, "on", True)
    jv.r55_memo_put("ponme algo alegre", "pon música alegre")
    assert "ponme algo alegre" not in jv._r55_memo()


def test_memo_aprende_de_la_comprension(jv, monkeypatch):
    import json
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "ack_start", lambda text: type("A", (), {"done": lambda self: None})())
    monkeypatch.setattr(jv, "card", lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: (calls.append(1), json.dumps({"tipo": "orden", "orden": "sube el volumen", "seguro": True}))[1])
    jv._rec.clear()
    jv.process_command("está muy bajito el sonido de esto")
    assert jv._rec.who() == "skill:volumen" and len(calls) == 1
    jv._rec.clear()
    jv.process_command("está muy bajito el sonido de esto")
    assert jv._rec.who() == "skill:volumen" and len(calls) == 1               # la segunda vez, sin preguntarle a la IA
    jv._rec.clear()
    jv.process_command("cuántas frases has aprendido")
    assert "1 frases" in jv._rec.said()
    jv.process_command("olvida las frases aprendidas")
    assert not jv._r55_memo()


# ---------------------------------------------------------------- avisos al celular cuando no estás
def _away(jv, monkeypatch, idle=1200, ready=True):
    sent = []
    monkeypatch.setattr(jv, "phone_send", lambda text: sent.append(text) or True)
    monkeypatch.setattr(jv, "r55_phone_ready", lambda: ready)
    monkeypatch.setattr(jv, "r55_idle", lambda: idle)
    monkeypatch.setattr(jv.threading, "Thread", lambda target, args=(), **k: type("T", (), {"start": lambda self: target(*args)})())
    monkeypatch.setitem(jv.settings, "phone_away", True)
    monkeypatch.setitem(jv.settings, "phone_away_min", 10)
    monkeypatch.setitem(jv.settings, "phone_away_max", 2)
    monkeypatch.setitem(jv.settings, "proactive_quiet", "21:30-06:30")
    jv.r55_away.update(day=None, n=0, sent=[])
    return sent


def test_away_send(jv, monkeypatch):
    sent = _away(jv, monkeypatch)
    noon = datetime.datetime(2026, 11, 24, 12, 0)
    assert jv.r55_away_send("uno", now=noon) and jv.r55_away_send("dos", now=noon)
    assert not jv.r55_away_send("tres", now=noon)                                # tope del día
    assert jv.r55_away_send("recordatorio", important=True, now=noon)            # tus recordatorios, siempre
    assert not jv.r55_away_send("de noche", now=datetime.datetime(2026, 11, 25, 23, 0))   # horas de silencio
    assert jv.r55_away_send("recordatorio de noche", important=True, now=datetime.datetime(2026, 11, 25, 23, 0))
    assert sent == ["uno", "dos", "recordatorio", "recordatorio de noche"]
    monkeypatch.setattr(jv, "r55_idle", lambda: 60)                              # estás en el computador
    assert not jv.r55_away_send("cuatro", important=True, now=noon)
    monkeypatch.setitem(jv.settings, "phone_away", False)
    monkeypatch.setattr(jv, "r55_idle", lambda: 5000)
    assert not jv.r55_away_send("cinco", important=True, now=noon)


def test_idle_cuenta_lo_que_le_hablas(jv, monkeypatch):
    monkeypatch.setattr(jv, "_idle_seconds", lambda: 5000)
    monkeypatch.setitem(jv._ag, "last_user", time.time() - 30)
    assert jv.r55_idle() < 60


def test_alert_y_proactivo_al_celular(jv, monkeypatch):
    sent = _away(jv, monkeypatch)
    monkeypatch.setattr(jv, "telegram_ready", lambda: True)
    monkeypatch.setitem(jv.settings, "telegram_alerts", True)
    monkeypatch.setitem(jv.settings, "telegram_remote", False)               # antes, sin esto no llegaba nada
    for name in ("whatsapp_alert", "windows_toast", "notice_add"):
        monkeypatch.setattr(jv, name, lambda *a, **k: None)
    jv.alert("Llamar a la coordinadora.", "NOTAS")
    assert sent and "coordinadora" in sent[-1]
    monkeypatch.setattr(jv, "r55_idle", lambda: 0)
    n = len(sent)
    jv.alert("Otro.", "NOTAS")
    assert len(sent) == n                                                   # estás en el computador: solo aquí


def test_attention_al_celular_si_no_estas(jv, monkeypatch):
    sent = _away(jv, monkeypatch)
    monkeypatch.setitem(jv.settings, "attention_pulse", True)
    monkeypatch.setitem(jv.settings, "attention_phone", False)
    monkeypatch.setitem(jv.settings, "attention_from", 0)
    monkeypatch.setitem(jv.settings, "attention_to", 24)
    monkeypatch.setitem(jv.settings, "attention_weekend", True)
    monkeypatch.setitem(jv.settings, "proactive_quiet", "")
    monkeypatch.setitem(jv._pulse, "last", 0.0)
    monkeypatch.setitem(jv._pulse, "seen", set())
    monkeypatch.setattr(jv, "attention_items", lambda now=None: [{"k": "ap:1", "p": 1, "t": "aprobar «la salida»", "cmd": ""}])
    monkeypatch.setattr(jv, "notice_add", lambda *a, **k: None)
    jv.attention_tick(datetime.datetime(2026, 11, 24, 10, 0))
    assert sent and "salida" in sent[-1]


def test_away_voz(jv, monkeypatch):
    _away(jv, monkeypatch)
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.settings, "phone_away", False)
    jv._rec.clear()
    jv.process_command("avísame al celular cuando no esté")
    assert jv.settings["phone_away"] is True and "10 minutos" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("no me mandes avisos al celular")
    assert jv.settings["phone_away"] is False
    jv.r55_away.update(day=datetime.date.today(), n=1, sent=[("10:00", "✦ Va a llover")])
    jv._rec.clear()
    jv.process_command("qué me mandaste al celular hoy")
    assert "llover" in jv._rec.said()
    monkeypatch.setattr(jv, "r55_phone_ready", lambda: False)
    jv._rec.clear()
    jv.process_command("avísame al celular")
    assert "Telegram" in jv._rec.said()


def test_reporte_manana_sin_telegram_remote(jv, monkeypatch):
    sent = []
    monkeypatch.setattr(jv, "telegram_ready", lambda: True)
    monkeypatch.setattr(jv, "telegram_send", lambda text, chat=None: sent.append(text))
    monkeypatch.setattr(jv.threading, "Thread", lambda target, args=(), **k: type("T", (), {"start": lambda self: target(*args)})())
    monkeypatch.setitem(jv.settings, "telegram_alerts", True)
    monkeypatch.setitem(jv.settings, "telegram_remote", False)
    monkeypatch.setitem(jv.settings, "morning_voice_note", False)
    monkeypatch.setitem(jv.settings, "morning_weather", False)
    monkeypatch.setitem(jv.settings, "morning_news", False)
    monkeypatch.setitem(jv.settings, "weather_city", "")
    for name in ("notes_today_summary", "check_ai", "_upd_save"):
        monkeypatch.setattr(jv, name, lambda *a, **k: True)
    monkeypatch.setattr(jv, "brief_extras", lambda *a, **k: [])
    import nucleo.temporizadores as T
    T.morning_report()
    assert sent and sent[-1].startswith("☀️")
