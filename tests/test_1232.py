"""12.32: consumo de la IA, nombres de estudiantes protegidos, consejo de modelos, avisos por evento y proyectos que se repiten."""
import datetime as dt
import json
import os

import pytest

import aula
import automaticos as A
import proyectos


# ---------------------------------------------------------------- consumo
def test_consumo(jv, monkeypatch, ask, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    jv._use.update(days={}, t=1.0, warned="")
    cfg = {"label": "Gemini", "model": "gemini-flash", "ai_provider": "gemini"}
    jv.usage_add(cfg, [{"role": "user", "content": "x" * 400}], "y" * 200)
    jv.usage_add(cfg, [{"role": "user", "content": "hola"}], "", ok=False, kind="quota")
    d = jv.usage_today()
    assert (d["calls"], d["in"], d["out"], d["quota"]) == (2, 101, 50, 1) and d["models"]["Gemini · gemini-flash"]["calls"] == 2
    who, said = ask("¿cuánto he usado la IA hoy?")
    assert who == "CONSUMO" and "2 llamadas" in said and "sin cuota" in said
    notes = []
    monkeypatch.setattr(jv, "notify", lambda text, origin="": notes.append(text))
    monkeypatch.setitem(jv.settings, "ai_daily_limit", 3)
    jv.usage_add(cfg, [], "")
    assert notes and "de las 3" in notes[0]
    jv.usage_add(cfg, [], "")
    assert len(notes) == 1                                                 # una vez al día
    st = {"pasos": []}
    jv._tl.project_st = st
    jv.usage_add(cfg, [{"role": "user", "content": "z" * 40}], "")
    jv._tl.project_st = None
    assert st["consumo"] == {"calls": 1, "tok": 10}
    jv._use["dirty"] = True
    jv.usage_flush()
    assert json.load(open(tmp_path / "consumo_ia.json"))["days"]


# ---------------------------------------------------------------- privacidad
@pytest.fixture
def curso(monkeypatch):
    monkeypatch.setitem(aula.data, "cursos", {"7A": ["Ana María Gómez Ruiz", "Pedro Pérez", "Luisa Fernanda Ríos"]})


def test_nombres_de_estudiantes_salen_cambiados(jv, curso, monkeypatch):
    msgs = [{"role": "system", "content": "Eres Jarvis."}, {"role": "user", "content": "Ana María sacó 3,2 y Pedro Pérez 4,5; ¿qué le digo a ANA MARÍA GÓMEZ?"}]
    out, mp = jv.privacy_scrub(msgs)
    u = out[1]["content"]
    assert "Pedro" not in u and "Ana" not in u and "Estudiante 1" in u and "Estudiante 2" in u
    assert msgs[1]["content"].startswith("Ana María")                       # el original no se toca
    back = jv.privacy_restore("A Estudiante 1 felicítala; Estudiante 2 va bien.", mp)
    assert "Estudiante" not in back and ("Ana María" in back or "ANA MARÍA GÓMEZ" in back) and "Pedro Pérez" in back
    assert jv.privacy_names_in("¿cómo va luisa fernanda?") and not jv.privacy_names_in("¿cómo va la economía?")
    monkeypatch.setitem(jv.settings, "privacy_students", False)
    assert jv.privacy_scrub(msgs)[0] is msgs


def test_la_nube_no_ve_los_nombres(jv, curso, monkeypatch):
    sent = []
    monkeypatch.setattr(jv.sys.modules["nucleo.ia"], "ai_chat", jv.sys.modules["nucleo.ia"].ai_chat)
    monkeypatch.setattr(jv, "ai_chat", jv.sys.modules["nucleo.ia"].ai_chat)
    gem = {"ai_provider": "gemini", "kind": "gemini", "label": "Gemini", "model": "g", "key": "k", "base": "", "ollama_host": ""}
    oll = {"ai_provider": "ollama", "kind": "ollama", "label": "Ollama", "model": "llama3", "key": "", "base": "", "ollama_host": "http://x"}
    monkeypatch.setattr(jv, "_ai_cfg", lambda override=None: dict(oll) if override and override.get("ai_provider") == "ollama" else dict(gem))
    monkeypatch.setattr(jv, "net_preflight", lambda: False)
    monkeypatch.setattr(jv, "_need_key", lambda cfg: None)
    monkeypatch.setattr(jv, "_with_fallback", lambda cfg, fn: fn(cfg))
    monkeypatch.setattr(jv, "_cloud_chat", lambda cfg, m, json_mode=False, max_tokens=None: sent.append(m) or "Estudiante 1 necesita refuerzo.")
    out = jv.ai_chat([{"role": "user", "content": "Pedro Pérez perdió el quiz"}])
    assert "Pedro" not in json.dumps(sent, ensure_ascii=False) and out == "Pedro Pérez necesita refuerzo."
    assert jv.ai_chat([{"role": "user", "content": "¿qué es la fotosíntesis?"}]) and "fotosíntesis" in sent[-1][0]["content"]
    local = []                                                             # «que ni salgan»: con IA local, la responde ella
    monkeypatch.setitem(jv.settings, "privacy_local_first", True)
    monkeypatch.setitem(jv.net, "local_model", "llama3")
    monkeypatch.setattr(jv, "ollama", object())
    monkeypatch.setattr(jv, "ollama_ensure", lambda host: None)
    monkeypatch.setattr(jv, "_ollama_chat", lambda cfg, **k: local.append(k["messages"]) or {"message": {"content": "Que repase."}})
    n = len(sent)
    assert jv.ai_chat([{"role": "user", "content": "Pedro Pérez perdió el quiz"}]) == "Que repase."
    assert len(sent) == n and "Pedro Pérez" in local[-1][0]["content"]


# ---------------------------------------------------------------- consejo
def test_consejo_de_modelos(jv, monkeypatch, ask):
    main = {"ai_provider": "gemini", "kind": "gemini", "label": "Gemini", "model": "gemini-pro", "key": "k", "base": "", "ollama_host": ""}
    monkeypatch.setattr(jv, "_ai_cfg", lambda override=None: dict(main) if not override else dict(main, ai_provider=override.get("ai_provider"), label=override.get("ai_provider"), model="m-" + str(override.get("ai_provider"))))
    monkeypatch.setattr(jv, "fast_model", lambda: "gemini-flash")
    monkeypatch.setattr(jv, "local_pick", lambda: "")
    members = jv.council_members()
    assert [m["model"] for m in members[:2]] == ["gemini-pro", "gemini-flash"]
    monkeypatch.setattr(jv, "_cloud_chat", lambda cfg, m, json_mode=False, max_tokens=None: f"{cfg['model']}: arrienda.")
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: "Coinciden en arrendar.")
    answers, synth = jv.council_run("¿compro o arriendo?")
    assert len(answers) >= 2 and synth == "Coinciden en arrendar." and answers[0][1] == "gemini-pro: arrienda."
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="", *a, **k: fn())
    shown, spoken = [], []
    monkeypatch.setattr(jv, "show", lambda text, origin: shown.append(text))
    monkeypatch.setattr(jv, "speak", lambda text, *a, **k: spoken.append(text))
    assert ask("pregúntale al consejo: ¿me conviene comprar o arrendar?")[0] == "CONSEJO"
    assert "**Síntesis:** Coinciden en arrendar." in shown[-1] and spoken[-1] == "Coinciden en arrendar."
    monkeypatch.setattr(jv, "fast_model", lambda: "")
    monkeypatch.setattr(jv, "council_members", lambda: [main])
    assert jv.council_run("x")[0] is None


# ---------------------------------------------------------------- avisos por evento
def test_reglas():
    p = A.parse_rule
    assert p("cuando me llegue un correo de la coordinadora, avísame al celular") == {"tipo": "correo", "de": "coordinadora", "celular": True}
    assert p("si el dólar pasa de 4.200, avísame")["valor"] == 4200 and p("cuando el euro baje de 4500")["op"] == "<"
    assert p("avísame si el bitcoin supera 400 millones")["valor"] == 400_000_000
    assert p("cuando aparezca una reunión nueva en el calendario, recuérdamela la víspera")["vispera"]
    assert p("cuando conecte el cargador, modo general") is None and p("qué hora es") is None
    r = {"tipo": "precio", "op": ">", "valor": 4200}
    assert A.price_crossed(r, 4250, 4100) and not A.price_crossed(r, 4300, 4250) and not A.price_crossed(r, 4100, None)
    assert A.mail_matches({"de": "coordinadora"}, {"de_nombre": "Coordinadora Académica", "de": "coord@colegio.edu.co"})
    assert not A.mail_matches({"de": "coordinadora"}, {"de_nombre": "Banco", "de": "info@banco.com"})


@pytest.fixture
def auto(jv, monkeypatch, tmp_path):
    A.configure(str(tmp_path))
    A.data.update(reglas=[], recurrentes=[], vistos={"mail": [], "cal": []}, recordados=[])
    jv._auto.update(seeded=False, last_price={})
    alerts = []
    monkeypatch.setattr(jv, "_alert", lambda text, phone=False: alerts.append((text, phone)))
    return alerts


def test_correo_y_calendario(jv, auto, ask, monkeypatch):
    monkeypatch.setattr(jv, "mail_method", lambda: "password")
    assert "coordinadora" in ask("cuando me llegue un correo de la coordinadora, avísame al celular")[1]
    old = [{"uid": "1", "de": "coord@colegio.edu.co", "de_nombre": "Coordinadora", "asunto": "Viejo"}]
    assert jv.check_mail(old) == 0                                          # la primera pasada solo aprende
    jv._auto["seeded"] = True
    new = old + [{"uid": "2", "de": "coord@colegio.edu.co", "de_nombre": "Coordinadora", "asunto": "Reunión mañana"},
                 {"uid": "3", "de": "x@banco.com", "de_nombre": "Banco", "asunto": "Oferta"}]
    assert jv.check_mail(new) == 1 and auto[-1] == ("📧 Correo de Coordinadora: «Reunión mañana».", True)
    assert jv.check_mail(new) == 0
    monkeypatch.setattr(jv, "cal_configured", lambda: True)
    ask("cuando aparezca una reunión nueva en el calendario, recuérdamela la víspera")
    now = dt.datetime(2026, 11, 14, 10, 0)
    ev = {"titulo": "Consejo académico", "inicio": "2026-11-15T07:00", "todo_el_dia": False}
    jv._auto["seeded"] = False
    assert jv.check_calendar([], now) == 0
    jv._auto["seeded"] = True
    assert jv.check_calendar([ev], now) == 1 and "Consejo académico" in auto[-1][0]
    assert jv.check_calendar([ev], now.replace(hour=19)) == 1 and auto[-1][0].startswith("⏰ Mañana")   # la víspera
    assert jv.check_calendar([ev], now.replace(hour=20)) == 0


def test_precio(jv, auto, ask, monkeypatch):
    ask("si el dólar pasa de 4.200, avísame")
    vals = iter([4100.0, 4250.0, 4300.0])
    monkeypatch.setattr(jv, "price_now", lambda a: next(vals))
    assert jv.check_prices() == 0 and jv.check_prices() == 1 and jv.check_prices() == 0
    assert "4.250" in auto[-1][0]
    who, said = ask("mis avisos automáticos")
    assert "Aviso 1" in said and "dólar" in said
    assert "Quité" in ask("borra el aviso automático 1")[1] and not A.data["reglas"]


# ---------------------------------------------------------------- proyectos que se repiten
def test_recurrentes_puros():
    r = A.parse_recurring("cada lunes a las 7, investiga los precios de la canasta familiar y hazme un informe")
    assert r == {"dias": [0], "hora": "07:00", "pedido": "investiga los precios de la canasta familiar y hazme un informe"}
    assert A.parse_recurring("todos los días a las 6 pm resúmeme las noticias de educación")["hora"] == "18:00"
    assert A.parse_recurring("cada lunes pon música") is None
    mon = dt.datetime(2026, 11, 16, 7, 5)
    assert A.due(r, mon) and not A.due(r, mon.replace(hour=6)) and not A.due(r, mon + dt.timedelta(days=1))
    assert not A.due(dict(r, ultimo="2026-11-16"), mon) and "cada lunes a las 07:00" == A.when_text(r)


def test_recurrente_de_principio_a_fin(jv, auto, ask, monkeypatch, tmp_path):
    proyectos.configure(str(tmp_path))
    __import__("aprobaciones").configure(str(tmp_path))
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "docs"))
    monkeypatch.setitem(jv.settings, "approvals_telegram", False)
    monkeypatch.setitem(jv.settings, "aula_open_docs", False)
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="", *a, **k: fn())
    plan = {"nombre": "Canasta", "pasos": [{"id": "a", "tipo": "investigar", "titulo": "Precios", "pedido": "precios", "depende": []},
                                           {"id": "b", "tipo": "texto", "titulo": "Análisis", "pedido": "análisis", "depende": ["a"]}]}
    approvals = []
    monkeypatch.setattr(jv, "request_approval", lambda tipo, titulo, detalle="", on_ok=None, **k: approvals.append(on_ok))
    calls = []

    def ai(msgs, **k):
        p = msgs[0]["content"]
        calls.append(p)
        if "planificador" in p:
            return json.dumps(plan)
        if "redactor final" in p:
            n = sum(1 for c in calls if "redactor final" in c)
            return json.dumps({"titulo": "Canasta", "resumen": f"Arroz a {4000 + n * 500}.", "secciones": [{"titulo": "Precios", "texto": f"Arroz {4000 + n * 500}"}]})
        if "revisor" in p:
            return json.dumps({"veredicto": "bien", "problemas": []})
        if "periódicamente" in p:
            return "El arroz subió de 4.500 a 5.000."
        raise jv.AIError("x", kind="config")
    monkeypatch.setattr(jv, "ai_chat", ai)
    monkeypatch.setattr(jv, "run_step", lambda st, step: (os.makedirs(st["carpeta"], exist_ok=True), {"archivo": "", "resumen": "dato " + step["id"]})[1])
    who, said = ask("cada lunes a las 7, investiga los precios de la canasta familiar y hazme un informe")
    assert who == "AVISOS" and approvals
    approvals[0]()
    rec = A.data["recurrentes"][0]
    assert rec["plan"]["nombre"] == "Canasta" and rec["id"] == 1
    jv.run_recurring(rec)
    assert rec["veces"] == 1 and "Arroz" in rec["ultimo_texto"] and not any("periódicamente" in c for c in calls)
    last = jv.run_recurring(rec)
    assert rec["veces"] == 2 and auto and "subió de 4.500 a 5.000" in auto[-1][0] and auto[-1][1]
    assert last["informe"]["secciones"][0]["titulo"] == "Frente a la vez anterior"
    started = []
    monkeypatch.setattr(jv.threading if hasattr(jv, "threading") else __import__("threading"), "Thread",
                        lambda target, args=(), daemon=True, name="": type("T", (), {"start": lambda s: started.append(args)})())
    rec["ultimo"] = ""
    jv.auto_tick(dt.datetime(2026, 11, 16, 7, 1))
    assert started and rec["ultimo"] == "2026-11-16"
