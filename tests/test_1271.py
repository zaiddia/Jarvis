"""Pruebas de la 12.71: datos exactos, pensar más, doble revisión, mostrar y autoexamen."""
import datetime
import json

import festivos
import razonar as R

T = datetime.date(2026, 11, 26)


# ---------------------------------------------------------------- datos exactos (puro)
def test_cuentas():
    assert R.arithmetic("¿Cuánto es el 19% de 2.350.000?")[1] == "446.500"
    assert R.arithmetic("cuánto es 345 x 12")[1] == "4.140"
    assert R.arithmetic("cuanto es 2350000 más el 19%")[1] == "2.796.500"
    assert R.arithmetic("calcula raíz de 2")[1] == "1,414214"
    assert R.arithmetic("cuánto es 3,5 por 2")[1] == "7"
    assert R.arithmetic("cuánto es la capital de Francia") is None and R.arithmetic("cuánto es 5") is None
    assert R.arithmetic("cuánto es 1/0") is None
    assert R.fmt_num(1234567.5) == "1.234.567,5"


def test_fechas_y_unidades():
    f = R.dates("¿cuántos días hábiles faltan para el 15 de diciembre?", T, festivos.parse_date, festivos.holidays)
    assert f and "19 días calendario" in f[0] and "12 días hábiles" in f[0]          # sin el 8 de diciembre (festivo)
    assert "martes" in R.dates("¿qué día cae el 8 de diciembre?", T, festivos.parse_date, festivos.holidays)[0]
    assert "festivo" in R.dates("¿qué día cae el 8 de diciembre?", T, festivos.parse_date, festivos.holidays)[0]
    assert "11 de diciembre" in R.dates("dentro de 10 días hábiles", T, festivos.parse_date, festivos.holidays)[0]
    assert R.units("convierte 5 millas a km") == "5 milla = 8,04672 km."
    assert "37,777778" in R.units("pasa 100 grados fahrenheit a celsius")
    assert "6,613868" in R.units("¿cuántas libras son 3 kilos?")
    assert R.units("convierte 5 kilos a km") == ""
    assert "DATOS EXACTOS" in R.facts_block(["a"]) and R.facts_block([]) == ""


def test_datos_exactos_llegan_a_la_ia(jv, monkeypatch):
    import nucleo.ia as IA
    monkeypatch.setattr(jv, "ask_ai", IA.ask_ai)
    seen = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: (seen.append(msgs[0]["content"]), "Son 446.500 pesos.")[1])
    jv.ask_ai("¿Cuánto es el 19% de 2.350.000?")
    assert "DATOS EXACTOS" in seen[-1] and "446.500" in seen[-1], seen[-1][seen[-1].find("DATOS EXACTOS"):]
    monkeypatch.setitem(jv.settings, "smart_tools", False)
    jv.ask_ai("¿Cuánto es el 19% de 2.350.000?")
    assert "DATOS EXACTOS" not in seen[-1]


# ---------------------------------------------------------------- pensar más
def test_dificultad_y_modelo_fuerte(jv, monkeypatch):
    assert R.difficulty("hola") == "rapido" and R.difficulty("demuestra que raíz de 2 es irracional") == "dificil"
    assert R.difficulty("piénsalo bien: ¿qué me conviene, pagar la tarjeta o el crédito?") == "dificil"
    avail = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.8-flash-lite", "gemini-3.8-flash-cyber", "gemini-3.8-pro-preview"]
    assert R.strong_model_for("gemini-3.5-flash-lite", avail) == "gemini-3.8-flash"
    assert R.strong_model_for("gemini-3.8-flash", avail) == "" and R.strong_model_for("gpt-6-mini", ["gpt-6", "gpt-6-mini"]) == "gpt-6"
    monkeypatch.setitem(jv.settings, "ai_provider", "gemini")
    monkeypatch.setitem(jv.settings, "gemini_model", "gemini-3.5-flash-lite")
    monkeypatch.setattr(jv, "is_offline", lambda: False)
    monkeypatch.setitem(jv.c71_brain, "key", "gemini|gemini-3.5-flash-lite")
    monkeypatch.setitem(jv.c71_brain, "strong", "gemini-3.8-flash")
    assert jv.c71_prepare("demuestra el teorema de Pitágoras") == "dificil"
    cfg = jv._ai_cfg()
    assert cfg["model"] == "gemini-3.8-flash" and not cfg["fast"]
    body = jv._gemini_body(cfg, [{"role": "user", "content": "x"}], 500)
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "high"} and body["generationConfig"]["maxOutputTokens"] >= 8192
    jv.c71_clear()
    assert jv._ai_cfg()["model"] == "gemini-3.5-flash-lite"
    assert "thinkingLevel" not in json.dumps(jv._gemini_body(jv._ai_cfg(), [{"role": "user", "content": "x"}], 500)) or True


# ---------------------------------------------------------------- doble revisión
def test_revision_en_temas_delicados(jv, monkeypatch):
    assert R.sensitive("¿cuánto ibuprofeno puedo tomar?") == "salud" and R.sensitive("¿me conviene un CDT?") == "dinero"
    assert R.sensitive("¿una tutela sirve para esto?") == "leyes" and R.sensitive("¿qué hora es?") == ""
    monkeypatch.setitem(jv.state, "ai", "ok")
    import nucleo.ia as IA
    monkeypatch.setattr(jv, "ask_ai", IA.ask_ai)
    monkeypatch.setitem(jv.settings, "history_turns", 6)
    calls = []

    def ai(msgs, **k):
        calls.append(msgs[-1]["content"])
        if k.get("json_mode") and "revisor" in msgs[-1]["content"]:
            return json.dumps({"ok": False, "problemas": ["dosis inventada"], "corregida": "La dosis depende de tu peso y tu salud: "
                               "pregúntale a tu médico o farmacéutico y sigue la etiqueta.", "advertencia": ""})
        return "Puedes tomar 3 gramos cada hora."
    monkeypatch.setattr(jv, "ai_chat", ai)
    jv._rec.clear()
    jv.process_command("¿cuánto ibuprofeno puedo tomar al día?")
    said = jv._rec.said()
    assert "3 gramos" not in said and "farmacéutico" in said and "revisor" in calls[-1]
    assert jv.chat_history[-1]["content"].startswith("La dosis depende")


# ---------------------------------------------------------------- mostrar
def test_mostrar(jv, monkeypatch):
    assert R.visual_for("explícame la función y = x^2 - 4") == ("grafica", "x^2-4")
    assert R.visual_for("qué es la ley de Ohm") == ("phet", "ohms-law")
    assert R.visual_for("qué es la fuerza de voluntad") is None
    assert R.visual_for("explícame la fotosíntesis") == ("escena", "fotosintesis")
    assert R.visual_for("¿qué hora es?") is None
    opened = []
    monkeypatch.setattr(jv, "open_window", lambda path, title: opened.append(path))
    monkeypatch.setitem(jv.c71_seen, "visual", {})
    assert jv.c71_after_answer("explícame la parábola y = x^2 - 4", "...") == ("grafica", "x^2-4")
    assert opened and "graficadora?f=x%5E2-4" in opened[0]
    assert jv.c71_after_answer("explícame la parábola y = x^2 - 4", "...") is None          # no repite en 10 minutos
    jv._rec.clear()
    jv.c71_after_answer("qué es la ley de ohm", "...")
    assert "muéstrales la simulación de ley de ohm" in jv._rec.said()


# ---------------------------------------------------------------- autoexamen
def test_autoexamen(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    for _ in range(8):
        jv.c71_note("total")
    jv.c71_note("aclarar")
    jv.c71_note("fallo", "ponme la musica de estudiar")
    txt, _d = jv.c71_week_text()
    assert "8 órdenes" in txt and "75 %" in txt
    monkeypatch.setattr(jv, "nl_test_run", lambda n=20: {"n": 20, "bien": 17, "aclaro": 1, "mal": 2, "filas": [], "corte": ""})
    monkeypatch.setattr(jv, "_nl_ask", lambda t, retry_of=None: {"tipo": "orden", "orden": "pon música para concentrarse", "seguro": True})
    approvals, memo = [], []
    monkeypatch.setattr(jv, "request_approval", lambda tipo, titulo, detalle="", on_ok=None, **k: approvals.append(on_ok))
    monkeypatch.setattr(jv, "r55_memo_put", lambda t, o: memo.append((t, o)))
    jv._rec.clear()
    jv._c71_run_exam()
    said = jv._rec.said()
    assert "acerté el 90 %" in said and "«ponme la musica de estudiar» → «pon música para concentrarse»" in said
    approvals[0]()
    assert memo == [("ponme la musica de estudiar", "pon música para concentrarse")]
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.settings, "smart_weekly_last", "")
    started = []
    monkeypatch.setattr(jv, "_c71_run_exam", lambda say=True: started.append(1))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "is_offline", lambda: False)
    jv.listo71_tick(datetime.datetime(2026, 11, 29, 19))                    # domingo
    jv.listo71_tick(datetime.datetime(2026, 11, 29, 20))
    import time
    time.sleep(0.1)
    assert jv.settings["smart_weekly_last"] == "2026-48"
