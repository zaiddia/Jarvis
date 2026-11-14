"""12.26: Jarvis general (no todo es del colegio), órdenes de varios pasos, «No era eso», frase directa y habilidad del día."""
import datetime as dt
import json
import os

import pytest

import correo
import guia
import mates
import proyectos
import vidadiaria as vd


@pytest.fixture
def general(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "assistant_mode", "general")
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    return jv


# ---------------------------------------------------------------- modo y quién es Jarvis
def test_sin_horario_no_es_siempre_docente(jv, monkeypatch):
    assert vd.resolve_mode("auto", has_schedule=False) == "general"
    assert vd.resolve_mode("auto", has_schedule=False, school_hours=True) == "docente"
    monkeypatch.setitem(jv.settings, "assistant_mode", "auto")
    monkeypatch.setattr(jv.horario, "items", [])
    monkeypatch.setattr(jv, "wifi_now", lambda: "")
    assert jv.current_mode(dt.datetime(2026, 11, 14, 10, 0)) == "general"          # sábado
    assert jv.current_mode(dt.datetime(2026, 11, 12, 21, 0)) == "general"          # jueves de noche
    assert jv.current_mode(dt.datetime(2026, 11, 12, 9, 0)) == "docente"           # jueves en la mañana


def test_los_textos_para_la_ia_siguen_el_modo(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "assistant_mode", "general")
    for p in (correo.prompt("dile a mi hermano que llego tarde"), jv.buscar.prompt("vuelos", []),
              jv.infodia.news_prompt([]), proyectos.plan_prompt("organiza mi viaje", general=True)):
        assert "asistente personal" in p and "asistente de un docente" not in p
    monkeypatch.setitem(jv.settings, "assistant_mode", "docente")
    assert "asistente de un docente" in correo.prompt("x") and "asistente de un docente" in jv.buscar.price_prompt("x", [])


# ---------------------------------------------------------------- frases que se iban por el lado que no era
def test_frases_generales_bien_atendidas(general, ask):
    assert ask("redacta un mensaje para el arrendador")[0] != "CUMPLEAÑOS"
    assert ask("evalúa mi idea de negocio")[0] != "MATE"
    assert ask("corrige este texto")[0] == "CORRECCIÓN"
    assert ask("calcula el 15% de 80000")[0] == "MATE" and ask("resuelve 2x+3=7")[0] == "MATE"


def test_cumple_sigue_funcionando(general, ask, monkeypatch):
    monkeypatch.setattr(general, "ai_chat", lambda *a, **k: "¡Feliz día, Ana!")
    assert ask("escríbele un mensaje de cumpleaños a Ana")[0] == "CUMPLEAÑOS"


def test_mates_solo_si_hay_cuenta():
    yes = ["evalua x=2 en 3x+1", "deriva seno de x", "cuanto es dos mas dos", "calcula la raiz de dieciseis", "integra x",
           "factoriza x al cuadrado menos uno", "calcula el 15% de 80000"]
    no = ["evalúa mi idea de negocio", "resuelve mi problema con el banco", "simplifica este texto", "cuánto vale un iphone"]
    assert all(mates.looks_math(f) for f in yes) and not any(mates.looks_math(f) for f in no)


def test_corrector_de_textos(general, monkeypatch):
    monkeypatch.setattr(general.J if hasattr(general, "J") else general, "state", dict(general.state, ai="ok"))
    asked, shown = [], []
    monkeypatch.setattr(general, "ai_chat", lambda msgs, **k: asked.append(msgs[0]["content"]) or "Mañana llego a las ocho.\nCambios: tildes.")
    monkeypatch.setattr(general, "show", lambda text, origin: shown.append((origin, text)))
    monkeypatch.setattr(general.threading, "Thread", lambda target, daemon=True: type("T", (), {"start": lambda s: target()})())
    general.process_command("corrige este texto: manana llego a las ocho")
    assert "manana llego" in asked[0] and "Corrige la ortografía" in asked[0]
    assert shown[-1][0] == "CORRECCIÓN" and "Mañana llego a las ocho." in shown[-1][1]


def test_alarma_a_una_hora(jv, ask):
    now = dt.datetime(2026, 11, 14, 10, 0)
    at = lambda f: (now + dt.timedelta(seconds=jv.parse_clock_reminder(jv.normalize(f), now)[0])).strftime("%d %H:%M")
    assert at("pon una alarma a las 6") == "14 18:00"                   # la más cercana que viene
    assert at("pon una alarma a las 6 de la mañana") == "15 06:00" and at("despiértame a las 5 y media") == "15 05:30"
    assert at("alarma a las 6:30") == "14 18:30" and at("pon alarma para las 9 am") == "15 09:00"
    assert jv.parse_clock_reminder(jv.normalize("recuérdame a las 3 de la tarde llamar a mamá"), now)[1] == "llamar a mama"
    assert ask("pon una alarma a las 6")[0] == "recordatorio"
    assert ask("recuerda que la reunión de padres es el jueves a las 3")[0] == "NOTAS"   # con día: a la agenda, como siempre


# ---------------------------------------------------------------- una orden, varios pasos
def test_ordenes_encadenadas():
    c = proyectos.chain_steps
    assert c("transcribe el audio, saca el acta y mandasela a coordinacion") == ["transcribe el audio", "saca el acta", "mandasela a coordinacion"]
    assert c("busca vuelos a cartagena y luego hazme un presupuesto") == ["busca vuelos a cartagena", "hazme un presupuesto"]
    for f in ("busca recetas de pollo", "recuerdame comprar pan y leche", "abre spotify y pon musica", "busca y abre la pagina",
              "haz una lista de mercado y agrega leche", "calcula 3 y 4"):
        assert c(f) == [], f
    assert proyectos.is_project("organiza mi fin de semana") and proyectos.is_project("encargate de la fiesta de mi hija")
    assert not proyectos.is_project("abre spotify y pon musica")


def test_plan_general_sin_colegio():
    p = proyectos.plan_prompt("organiza mi viaje", general=True)
    assert "tabla:" in p and "correo:" in p and "orden:" in p and "rubrica:" not in p and "No supongas que es del colegio" in p
    assert "rubrica:" in proyectos.plan_prompt("prepara la semana de 7A")
    d = {"nombre": "Viaje", "pasos": [{"id": "a", "tipo": "orden", "pedido": "recuérdame el viernes a las 9 hacer la maleta"},
                                       {"id": "b", "tipo": "orden", "pedido": "apaga el computador"},
                                       {"id": "c", "tipo": "tabla", "pedido": "presupuesto del viaje"}]}
    assert [x["id"] for x in proyectos.validate_plan(d)["pasos"]] == ["a", "c"]   # una orden peligrosa no entra al plan


@pytest.fixture
def folder(tmp_path):
    return str(tmp_path / "prj")


def test_paso_orden_y_tabla(general, folder, monkeypatch):
    seen = []
    monkeypatch.setattr(general, "process_command", lambda t: (seen.append((t, general._tl.remote)), general._tl.capture.append("Anotado.")))
    st = {"carpeta": folder, "pasos": []}
    r = general.run_daily_step(st, {"tipo": "orden", "pedido": "«recuérdame el viernes hacer la maleta»", "titulo": "x"}, "", folder)
    assert seen == [("recuérdame el viernes hacer la maleta", True)] and "Anotado." in r["resumen"] and r["archivo"] == ""
    with pytest.raises(RuntimeError):
        general.run_daily_step(st, {"tipo": "orden", "pedido": "borra mis notas", "titulo": "x"}, "", folder)
    monkeypatch.setattr(general, "ai_chat", lambda *a, **k: json.dumps({"titulo": "Presupuesto", "columnas": ["Cosa", "Valor"], "filas": [["Hotel", 400000]]}))
    os.makedirs(folder, exist_ok=True)
    r = general.run_daily_step(st, {"tipo": "tabla", "pedido": "presupuesto", "titulo": "Presupuesto"}, "presupuesto", folder)
    assert r["archivo"].endswith(".xlsx") and os.path.exists(r["archivo"])


def test_paso_correo_pide_permiso(general, folder, monkeypatch):
    os.makedirs(folder, exist_ok=True)
    monkeypatch.setitem(general.settings, "email_book", "Hermano = juan@example.com")
    monkeypatch.setattr(general, "mail_method", lambda: "google")
    monkeypatch.setattr(general, "ai_chat", lambda *a, **k: json.dumps({"asunto": "Llego tarde", "cuerpo": "Hola Juan, llego a las 8."}))
    sent, asked = [], []
    monkeypatch.setattr(general, "mail_send", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(general, "request_approval", lambda tipo, titulo, detalle="", on_ok=None, **k: asked.append((titulo, on_ok)))
    r = general.run_daily_step({"carpeta": folder}, {"tipo": "correo", "pedido": "a mi hermano que llego tarde", "titulo": "Correo"},
                               "a mi hermano que llego tarde", folder)
    assert r["archivo"].endswith(".docx") and not sent and "juan@example.com" in asked[0][0]   # sin «sí», no sale
    asked[0][1]()
    assert sent and sent[0][0] == "juan@example.com"
    monkeypatch.setattr(general, "mail_method", lambda: "")
    asked.clear()
    r = general.run_daily_step({"carpeta": folder}, {"tipo": "correo", "pedido": "a mi hermano que llego tarde", "titulo": "Correo"}, "x", folder)
    assert not asked and "Word" in r["resumen"]


def test_semana_personal_en_modo_general(general, ask, monkeypatch):
    planned = []
    monkeypatch.setattr(general, "state", dict(general.state, ai="ok"))
    monkeypatch.setattr(general, "plan_project", lambda goal: planned.append(goal))
    assert ask("prepárame la semana")[0] == "SEMANA" and "organiza mi semana" in planned[0]


# ---------------------------------------------------------------- «No era eso», frase directa, habilidad del día
def test_no_era_eso(general, tmp_path, monkeypatch, ask):
    monkeypatch.setattr(general, "CONFIG_DIR", str(tmp_path))
    assert general.handle_misheard({"said": "pon algo de salsa", "reply": "No entendí", "origin": "IA"})["n"] == 1
    assert general.handle_misheard({"said": ""})["ok"] is False
    rows = general.fallos_all()
    assert rows[0]["frase"] == "pon algo de salsa" and rows[0]["origen"] == "IA" and rows[0]["modo"] == "general"
    assert ask("cuántos fallos tienes")[1].startswith("Tengo 1 fallo")
    assert "1 fallos" in ask("abre el registro de fallos")[1]
    js = open(os.path.join(os.path.dirname(__file__), "..", "static", "js", "hud.js"), encoding="utf-8").read()
    assert 'socket.emit("misheard"' in js and "No era eso" in js


def test_frase_directa_una_vez_al_dia(general, monkeypatch):
    g = [{"id": "dia", "nombre": "Mi día", "grupos": [{"nombre": "Menú y mercado (12.15)", "ejemplos": [
        {"t": "arma el menú de la semana para 3 personas", "probar": True}]}]}]
    assert guia.best_example(g, "quiero que armes un menú para la semana de 3 personas") == ("Menú y mercado", "arma el menú de la semana para 3 personas")
    assert guia.best_example(g, "menú") is None and guia.best_example(g, "busca vuelos baratos") is None
    monkeypatch.setattr(general, "guide", lambda: g)
    monkeypatch.setitem(general.settings, "tip_last", "")
    cards = []
    monkeypatch.setattr(general, "card", lambda *a, **k: cards.append(a))
    now = dt.datetime(2026, 11, 14, 10)
    assert "arma el menú" in general.phrase_tip("quiero que armes un menú para la semana de 3 personas", now)
    assert general.phrase_tip("quiero que armes un menú para la semana de 3 personas", now) == ""     # ya hubo uno hoy


def test_habilidad_del_dia(general, monkeypatch):
    g = [{"id": "colegio", "nombre": "Colegio", "grupos": [{"nombre": "Aula (9.0)", "ejemplos": [{"t": "pasa lista", "probar": True}]}]},
         {"id": "dia", "nombre": "Mi día", "grupos": [{"nombre": "Viajes (12.15)", "ejemplos": [{"t": "mis viajes", "probar": True}]},
                                                       {"nombre": "Menú (12.15)", "ejemplos": [{"t": "arma el menú", "probar": True}]}]}]
    assert guia.daily_pick(g, general=True, day=0)[0] == "Viajes (12.15)"
    assert guia.daily_pick(g, seen=["Viajes (12.15)"], general=True)[0] == "Menú (12.15)"
    assert {guia.daily_pick(g, day=d)[0] for d in range(3)} == {"Aula (9.0)", "Viajes (12.15)", "Menú (12.15)"}
    monkeypatch.setattr(general, "guide", lambda: g)
    monkeypatch.setitem(general.settings, "skill_day_seen", [])
    a, b = general.skill_of_day(), general.skill_of_day()
    assert a.startswith("Habilidad del día, ") and a != b and "pasa lista" not in a + b
    monkeypatch.setitem(general.settings, "skill_of_day", False)
    assert general.skill_of_day() == ""
