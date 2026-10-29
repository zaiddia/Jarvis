"""Pruebas de lo nuevo de la 7.0: proactividad, vigilante, habilidades, diario, MCP, panel del celular y servidor MCP."""
import datetime
import json
import os
import sys
import tempfile

import pytest

import diario
import habilidades
import mcp_cliente
import proactivo
import vigilante

HERE = os.path.dirname(os.path.abspath(__file__))
D = datetime.datetime


# ----------------------------------------------------------------------------- proactividad
def cfg(**kw):
    c = {"proactive_enabled": True, "proactive_quiet": "21:30-06:30", "proactive_max": 12, "proactive_breaks": True,
         "proactive_break_min": 120, "proactive_battery": True, "proactive_rain": True, "proactive_greeting": True}
    c.update(kw)
    return c


def test_horas_de_silencio():
    assert proactivo.in_quiet(D(2026, 1, 1, 23, 0), "21:30-06:30")
    assert proactivo.in_quiet(D(2026, 1, 1, 5, 59), "21:30-06:30")
    assert not proactivo.in_quiet(D(2026, 1, 1, 12, 0), "21:30-06:30")
    assert proactivo.in_quiet(D(2026, 1, 1, 13, 0), "12:00-14:00")
    assert not proactivo.in_quiet(D(2026, 1, 1, 13, 0), "")


def test_tope_y_separacion():
    st, now = proactivo.State(), D(2026, 10, 29, 10, 0)
    assert proactivo.can_speak(st, now, cfg())
    proactivo.said(st, now, "a")
    assert not proactivo.can_speak(st, now + datetime.timedelta(minutes=5), cfg())          # muy seguido
    assert proactivo.can_speak(st, now + datetime.timedelta(minutes=5), cfg(), optional=False)
    assert proactivo.can_speak(st, now + datetime.timedelta(minutes=16), cfg())
    st.count = 12
    assert not proactivo.can_speak(st, now + datetime.timedelta(minutes=30), cfg())          # tope del día
    assert proactivo.can_speak(st, now + datetime.timedelta(days=1), cfg())                  # al día siguiente, de nuevo
    assert not proactivo.can_speak(proactivo.State(), D(2026, 10, 29, 23, 0), cfg())         # silencio
    assert not proactivo.can_speak(proactivo.State(), now, cfg(proactive_enabled=False))


def test_pausa():
    st, t0 = proactivo.State(), D(2026, 10, 29, 8, 0)
    proactivo.activity(st, t0, 0)
    proactivo.activity(st, t0 + datetime.timedelta(minutes=60), 20)
    assert proactivo.break_due(st, t0 + datetime.timedelta(minutes=60), cfg()) is None
    due = proactivo.break_due(st, t0 + datetime.timedelta(minutes=121), cfg())
    assert due and due[0] == "pausa" and "2 horas" in due[1]
    assert proactivo.break_due(st, t0 + datetime.timedelta(minutes=130), cfg()) is None      # una sola vez
    proactivo.activity(st, t0 + datetime.timedelta(minutes=140), 400)                         # descansó 5+ min
    proactivo.activity(st, t0 + datetime.timedelta(minutes=141), 0)
    assert proactivo.break_due(st, t0 + datetime.timedelta(minutes=200), cfg()) is None


def test_bateria():
    st = proactivo.State()
    assert proactivo.battery_due(st, 50, False, cfg()) is None
    assert proactivo.battery_due(st, 19, False, cfg())[0] == "bateria"
    assert proactivo.battery_due(st, 15, False, cfg()) is None                                # ya avisó
    assert proactivo.battery_due(st, 15, True, cfg()) is None                                 # cargando: se rearma
    assert proactivo.battery_due(st, 18, False, cfg())[0] == "bateria"


def test_saludo():
    st = proactivo.State()
    proactivo.activity(st, D(2026, 10, 29, 2, 0), 5 * 3600)
    assert proactivo.greeting_due(st, D(2026, 10, 29, 7, 10), 3, cfg())
    st2 = proactivo.State()
    proactivo.activity(st2, D(2026, 10, 29, 2, 0), 5 * 3600)
    assert not proactivo.greeting_due(st2, D(2026, 10, 29, 15, 0), 3, cfg())                # por la tarde no
    assert not proactivo.greeting_due(st2, D(2026, 10, 29, 7, 0), 3, cfg(), done_today=True)


def test_lluvia():
    st = proactivo.State()
    hourly = [("2026-10-29T11:00", 10), ("2026-10-29T12:00", 70), ("2026-10-29T13:00", 80)]
    assert proactivo.rain_due(st, D(2026, 10, 29, 10, 0), "12:30", hourly, cfg()) is None     # aún es pronto
    due = proactivo.rain_due(st, D(2026, 10, 29, 11, 30), "12:30", hourly, cfg())
    assert due and "80" in due[1]
    assert proactivo.rain_due(proactivo.State(), D(2026, 10, 29, 11, 30), "12:30", [("2026-10-29T12:00", 20)], cfg()) is None


def test_rutina_para_evento():
    rs = [{"nombre": "Modo clase"}, {"nombre": "Fin de clase"}, {"nombre": "Modo planeación"}, {"nombre": "Buenos días", "cuando": "07:00"}]
    assert proactivo.routine_for_event("Clase 7A matemáticas", rs)["nombre"] == "Modo clase"
    assert proactivo.routine_for_event("Planeación semanal", rs)["nombre"] == "Modo planeación"
    assert proactivo.routine_for_event("Cita médica", rs) is None


# ----------------------------------------------------------------------------- vigilante
@pytest.mark.parametrize("frase,kind,target", [
    ("avísame cuando termine la descarga", "descarga", ""),
    ("me avisas cuando se descargue", "descarga", ""),
    ("avísame cuando se cierre Zoom", "cierre", "zoom"),
    ("avísame cuando termine de instalar", "proceso", "instalador"),
    ("avísame cuando Premiere termine", "proceso", "premiere"),
])
def test_vigilante_entiende(frase, kind, target):
    r = vigilante.parse(frase)
    assert r and r["kind"] == kind and r["target"] == target


@pytest.mark.parametrize("frase", ["avísame mañana a las 3", "recuérdame en 10 minutos", "abre la descarga", "cuando termine te digo"])
def test_vigilante_no_es(frase):
    assert vigilante.parse(frase) is None


def test_vigilante_descarga():
    t0 = D(2026, 10, 29, 10, 0)
    w = vigilante.Watch(vigilante.parse("avísame cuando termine la descarga"), t0)
    s = lambda sec, partial: w.step(t0 + datetime.timedelta(seconds=sec), partial)
    assert s(5, ["video.mp4.crdownload"]) is None
    assert s(60, []) is None                                  # recién terminada: espera a que se asiente
    assert "terminó la descarga" in s(70, [])
    w2 = vigilante.Watch(vigilante.parse("avísame cuando termine la descarga"), t0)
    assert w2.step(t0 + datetime.timedelta(seconds=200), []) == "timeout"   # nunca hubo descarga


def test_vigilante_cierre_y_proceso():
    t0 = D(2026, 10, 29, 10, 0)
    w = vigilante.Watch(vigilante.parse("avísame cuando se cierre zoom"), t0)
    assert w.step(t0, running=["zoom", "chrome"]) is None
    assert "se cerró zoom" in w.step(t0 + datetime.timedelta(seconds=30), running=["chrome"])
    assert vigilante.Watch(vigilante.parse("avísame cuando se cierre zoom"), t0).step(t0, running=["chrome"]) == "notfound"
    p = vigilante.Watch(vigilante.parse("avísame cuando premiere termine"), t0)
    assert p.step(t0, running=["adobe premiere pro"], cpu=60) is None
    assert p.step(t0 + datetime.timedelta(seconds=30), running=["adobe premiere pro"], cpu=2) is None
    assert "ya no está trabajando" in p.step(t0 + datetime.timedelta(seconds=95), running=["adobe premiere pro"], cpu=1)


# ----------------------------------------------------------------------------- habilidades
@pytest.fixture
def hab():
    habilidades.configure(tempfile.mkdtemp())
    return habilidades


def test_habilidades_de_ejemplo(hab):
    assert {h["nombre"] for h in hab.skills} >= {"Wikipedia", "Traductor", "Modo concentración", "Dato del día"}
    s, v = hab.match("busca la fotosíntesis en wikipedia")
    assert s["nombre"] == "Wikipedia" and v == {"tema": "la fotosintesis"}
    s, v = hab.match("¿cómo se dice buenos días en inglés?")
    assert s["nombre"] == "Traductor" and v == {"texto": "buenos dias", "idioma": "ingles"}
    assert hab.match("abre spotify") is None


def test_habilidad_instalar_y_validar(hab):
    h = hab.install(json.dumps({"nombre": "Saludo", "frases": ["saluda a {quien}"], "accion": "decir", "texto": "¡Hola, {quien}!"}))
    assert h["nombre"] == "Saludo"
    s, v = hab.match("saluda a los de séptimo")
    assert hab.fill(s["texto"], v) == "¡Hola, los de septimo!"
    for bad in ['{"nombre": "x"}', '{"nombre": "x", "frases": ["a"], "accion": "borrar"}',
                '{"nombre": "x", "frases": ["a"], "accion": "abrir", "url": "file:///C:/"}', "no es json"]:
        with pytest.raises(ValueError):
            hab.install(bad)
    hab.delete("Saludo")
    assert hab.match("saluda a todos") is None


def test_rellenar(hab):
    assert hab.fill("Dato{ sobre {tema}}.", {}) == "Dato."
    assert hab.fill("Dato{ sobre {tema}}.", {"tema": "volcanes"}) == "Dato sobre volcanes."
    assert hab.fill("https://x.org/?q={q}", {"q": "a&b c"}, url=True) == "https://x.org/?q=a%26b%20c"


# ----------------------------------------------------------------------------- diario
def test_diario():
    diario.configure(tempfile.mkdtemp(), True, 30)
    now = D.now()
    diario.log("orden", "abre word", now)
    diario.log("rutina", "Modo clase", now)
    diario.log("orden", "mi contraseña del banco es 1234", now)
    e = diario.day(now.date())
    assert len(e) == 3 and "contrasena" not in json.dumps(e) and "1234" not in json.dumps(e)
    assert "2 órdenes" in diario.spoken(e) and "Modo clase" in diario.spoken(e)
    assert "abre word" in diario.today_context(now=now)
    old = now - datetime.timedelta(days=40)
    diario.log("orden", "algo viejo", old)
    assert diario.purge() == 1 and diario.day(old.date()) == []


# ----------------------------------------------------------------------------- MCP
def test_mcp_config():
    assert mcp_cliente.parse_config("") == {}
    c = mcp_cliente.parse_config('{"mcpServers": {"hora": {"command": "uvx", "args": ["mcp-server-time"]}, "x": {"command": "a", "disabled": true}}}')
    assert list(c) == ["hora"] and c["hora"]["args"] == ["mcp-server-time"]
    for bad in ["{", '{"mcpServers": {"a b": {"command": "x"}}}', '{"mcpServers": {"r": {"url": "http://ejemplo.com/mcp"}}}',
                '{"mcpServers": {"r": {}}}']:
        with pytest.raises(ValueError):
            mcp_cliente.parse_config(bad)


def test_mcp_servidor_real():
    hub = mcp_cliente.Hub("7.0", log=lambda m: None)
    conf = {"mcpServers": {"falso": {"command": sys.executable, "args": [os.path.join(HERE, "servidor_mcp_falso.py")]}}}
    st = hub.configure(json.dumps(conf))
    try:
        assert st[0]["ok"], st
        assert set(st[0]["herramientas"]) == {"sumar", "saludo"}
        cat = hub.catalog()
        assert any(l.startswith("- mcp__falso__sumar(a*, b*)") for l in cat)
        assert hub.call("mcp__falso__sumar", {"a": 2, "b": 3}) == ("5", False)
        assert hub.call("mcp__falso__saludo", {"nombre": "Ana"})[0] == "Hola, Ana"
        assert hub.find("mcp__falso__nada") is None and hub.find("abrir_app") is None
    finally:
        hub.close()


def test_mcp_servidor_que_no_existe():
    hub = mcp_cliente.Hub("7.0", log=lambda m: None)
    st = hub.configure('{"mcpServers": {"roto": {"command": "programa-que-no-existe-jarvis"}}}')
    assert not st[0]["ok"] and st[0]["error"]
    assert hub.catalog() == []


# ----------------------------------------------------------------------------- panel del celular y servidor MCP (dentro de jarvis.py)
def test_panel_celular(jv):
    jv.settings["mobile_token"] = "secreto-de-prueba-1234"
    c = jv.mobile_app.test_client()
    assert c.get("/api/estado").status_code == 403
    assert c.get("/api/estado", headers={"X-Jarvis-Token": "malo"}).status_code == 403
    r = c.get("/api/estado", headers={"X-Jarvis-Token": "secreto-de-prueba-1234"})
    assert r.status_code == 200 and r.get_json()["version"] == jv.VERSION
    assert c.get("/?k=secreto-de-prueba-1234").status_code == 200
    jv.mobile["last"] = 0
    r = c.post("/api/orden", json={"texto": "apaga el equipo"}, headers={"X-Jarvis-Token": "secreto-de-prueba-1234"})
    assert "seguridad" in r.get_json()["text"].lower()


def test_servidor_mcp_de_jarvis(jv):
    c = jv.app.test_client()
    jv.settings["mcp_server_enabled"] = False
    assert c.post("/api/mcp", json={"tool": "jarvis_estado"}).status_code == 403
    jv.settings["mcp_server_enabled"] = True
    jv.mcp_server_token["value"] = "t" * 64
    assert c.post("/api/mcp", json={"tool": "jarvis_estado"}, headers={"X-Jarvis-Token": "x"}).status_code == 403
    r = c.post("/api/mcp", json={"tool": "jarvis_estado"}, headers={"X-Jarvis-Token": "t" * 64})
    assert r.status_code == 200 and jv.VERSION in r.get_json()["text"]
    r = c.post("/api/mcp", json={"tool": "jarvis_orden", "args": {"texto": "reinicia el pc"}}, headers={"X-Jarvis-Token": "t" * 64})
    assert "seguridad" in r.get_json()["text"].lower()
    jv.settings["mcp_server_enabled"] = False


def test_oferta_de_rutina(ask, jv):
    r = jv.rutinas.find("modo clase")
    jv.pro_offer.update(routine=r, expires=jv.time.time() + 60)
    who, _ = ask("sí")
    assert who == "rutina:Modo clase"
    jv.pro_offer.update(routine=r, expires=jv.time.time() + 60)
    who, said = ask("no")
    assert who == "PROACTIVO" and jv.pro_offer["routine"] is None
