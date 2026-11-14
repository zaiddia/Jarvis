"""12.31: noticias con fuente que se abre, y proyectos con informe final, revisor, modelo por paso, tablero y varios a la vez."""
import json
import os
import threading
import time

import pytest

import aprobaciones
import infodia
import proyectos

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RSS = """<rss><channel>
<item><title>Suben las tasas del Banco de la República - El Tiempo</title><link>https://news.google.com/rss/articles/abc</link><source>El Tiempo</source></item>
<item><title>Nueva ley de educación</title><link>https://www.semana.com/educacion/ley</link><source>Semana</source></item>
<item><title>Sin enlace</title><source>Caracol</source></item>
</channel></rss>"""


# ---------------------------------------------------------------- noticias
def test_noticias_con_fuente_y_enlace():
    items = infodia.parse_rss(RSS)
    assert items[0] == {"titulo": "Suben las tasas del Banco de la República", "fuente": "El Tiempo", "fecha": "",
                        "link": "https://news.google.com/rss/articles/abc"}
    assert items[2]["link"] == ""
    pairs = infodia.news_parse({"noticias": [{"i": 1, "texto": "Hay una nueva ley de educación."}, {"i": 9, "texto": "x"},
                                             {"i": "0", "texto": "El Banco subió las tasas."}, {"i": 1, "texto": "repetida"},
                                             {"i": 2, "texto": "Algo en Caracol."}]}, items)
    assert [t for t, _ in pairs] == ["Hay una nueva ley de educación.", "El Banco subió las tasas.", "Algo en Caracol."]
    rich = infodia.news_rich(pairs)
    assert "- Hay una nueva ley de educación. — [Semana](https://www.semana.com/educacion/ley)" in rich
    assert "- Algo en Caracol. — Caracol" in rich
    assert "Semana: https://www.semana.com/educacion/ley" in infodia.news_rich(pairs, remote=True)     # en Telegram, a la vista
    spoken = infodia.news_spoken(pairs)
    assert "http" not in spoken and "Lo cuenta Semana." in spoken


def test_noticias_por_voz(jv, ask, monkeypatch):
    items = infodia.parse_rss(RSS)
    monkeypatch.setattr(jv, "is_offline", lambda: False)
    monkeypatch.setattr(jv, "_news_items", lambda topic="": items)
    monkeypatch.setattr(jv, "ai_chat", lambda *a, **k: json.dumps({"noticias": [{"i": 0, "texto": "El Banco subió las tasas."}]}))
    shown, spoken = [], []
    monkeypatch.setattr(jv, "show", lambda text, origin: shown.append(text))
    monkeypatch.setattr(jv, "speak", lambda text, *a, **k: spoken.append(text))
    assert ask("léeme las noticias")[0] == "NOTICIAS"
    assert "[El Tiempo](https://news.google.com/rss/articles/abc)" in shown[-1] and "toca la fuente" in shown[-1]
    assert spoken[-1] == "El Banco subió las tasas. Lo cuenta El Tiempo."
    monkeypatch.setattr(jv, "ai_chat", lambda *a, **k: (_ for _ in ()).throw(jv.AIError("x", kind="config")))
    ask("léeme las noticias")
    assert "[Semana](https://www.semana.com/educacion/ley)" in shown[-1]                               # sin IA: titulares con fuente


def test_el_enlace_se_abre_en_el_navegador(jv, monkeypatch):
    opened = []
    monkeypatch.setattr(jv.sys.modules["nucleo.web"].webbrowser, "open", lambda u: opened.append(u))
    assert jv.sys.modules["nucleo.web"].handle_open_link({"url": "https://www.semana.com/x"})["ok"]
    for bad in ("javascript:alert(1)", "file:///C:/Windows", "ms-settings:display", ""):
        assert not jv.sys.modules["nucleo.web"].handle_open_link({"url": bad})["ok"]
    assert opened == ["https://www.semana.com/x"]
    md = open(os.path.join(HERE, "static", "js", "mdmath.js"), encoding="utf-8").read()
    hud = open(os.path.join(HERE, "static", "js", "hud.js"), encoding="utf-8").read()
    assert 'class="mdlink"' in md and 'class="mdlink"' in hud and "https?:" in md
    assert hud.index('closest("a.mdlink")') > hud.index("const socket = io()") and 'socket.emit("open_link"' in hud


# ---------------------------------------------------------------- informe, revisor y editar por partes
def test_partes_puras():
    assert proyectos.step_brain("orden") == "rapido" and proyectos.step_brain("investigar") == "potente"
    st = {"pedido": "p", "nombre": "N", "pasos": [{"titulo": "A", "tipo": "texto", "estado": "hecho", "resumen": "dato 1"}]}
    with pytest.raises(ValueError):
        proyectos.report_validate({"secciones": []}, st)
    rep = proyectos.report_validate({"titulo": "Informe", "resumen": "r", "secciones": [{"titulo": "Uno", "texto": "t1"}, {"texto": ""}],
                                     "conclusiones": "c"}, st)
    assert [s["titulo"] for s in rep["secciones"]] == ["Uno"] and "1. Uno" in proyectos.report_text(rep)
    assert proyectos.review_validate({"veredicto": "bien", "problemas": []})["veredicto"] == "bien"
    rv = proyectos.review_validate({"veredicto": "bien", "problemas": [{"parte": "1", "detalle": "la cifra no está en las fuentes"}]})
    assert rv["veredicto"] == "revisar" and "1 cosa por revisar" in proyectos.review_spoken(rv)
    assert proyectos.parse_edit("cambia la parte 2 del informe: hazla mas corta") == (2, "hazla mas corta")
    assert proyectos.parse_edit("acorta las conclusiones del informe")[0] == "conclusiones" and proyectos.parse_edit("cambia la parte") is None
    proyectos.apply_edit(rep, 1, "nuevo")
    assert rep["secciones"][0]["texto"] == "nuevo" and rep["revision"] is None


@pytest.fixture
def prj(jv, monkeypatch, tmp_path):
    proyectos.configure(str(tmp_path))
    aprobaciones.configure(str(tmp_path))
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "docs"))
    monkeypatch.setitem(jv.settings, "approvals_telegram", False)
    monkeypatch.setitem(jv.settings, "aula_open_docs", False)
    monkeypatch.setitem(jv.project_run, "busy", False)
    jv.project_runs.clear()
    notes = []
    monkeypatch.setattr(jv, "notify", lambda text, origin="JARVIS": notes.append(text))
    return notes


PLAN = {"nombre": "Viaje a Cartagena", "pasos": [
    {"id": "a", "tipo": "investigar", "titulo": "Vuelos", "pedido": "vuelos a Cartagena", "depende": []},
    {"id": "b", "tipo": "tabla", "titulo": "Presupuesto", "pedido": "presupuesto del viaje", "depende": ["a"]},
    {"id": "c", "tipo": "orden", "titulo": "Recordatorio", "pedido": "recuérdame el viernes hacer la maleta", "depende": []}]}


def _fake_step(st, step):
    os.makedirs(st["carpeta"], exist_ok=True)
    path = os.path.join(st["carpeta"], step["id"] + ".txt")
    open(path, "w").close()
    return {"archivo": path, "resumen": f"resultado de {step['titulo']}"}


def test_informe_final_revisado_y_modelo_por_paso(jv, prj, monkeypatch):
    monkeypatch.setattr(jv, "run_step", _fake_step)
    monkeypatch.setattr(jv, "fast_model", lambda: "gemini-flash-lite")
    asked = []

    def ai(msgs, **k):
        p = msgs[0]["content"]
        asked.append(p)
        if "redactor final" in p:
            return json.dumps({"titulo": "Viaje a Cartagena", "resumen": "Todo listo.", "conclusiones": "Reservar ya.",
                               "secciones": [{"titulo": "Vuelos", "texto": "Hay vuelos."}, {"titulo": "Presupuesto", "texto": "Cuesta 2 millones."}]})
        if "revisor de un informe" in p:
            return json.dumps({"veredicto": "revisar", "problemas": [{"parte": "2", "detalle": "los 2 millones no salen de las fuentes"}]})
        if "Reescríbela" in p:
            return "Cuesta alrededor de 1,8 millones."
        raise jv.AIError("x", kind="config")
    monkeypatch.setattr(jv, "ai_chat", ai)
    st = proyectos.new("planea mi viaje a Cartagena", proyectos.validate_plan(json.loads(json.dumps(PLAN))), jv.settings["output_dir"])
    jv.run_project(st)
    assert st["estado"] == "terminado" and "resultado de Vuelos" in asked[0] and "resultado de Vuelos" in asked[1]
    assert {p["id"]: p["modelo"] for p in st["pasos"]} == {"a": "potente", "b": "potente", "c": "rápido · gemini-flash-lite"}
    rep = st["informe"]
    assert os.path.exists(rep["ruta"]) and rep["revision"]["veredicto"] == "revisar"
    assert "informe final" in prj[-1] and "1 cosa por revisar" in prj[-1]
    from docx import Document
    body = "\n".join(p.text for p in Document(rep["ruta"]).paragraphs)
    assert "2. Presupuesto" in body and "Revisión" in body and "los 2 millones no salen de las fuentes" in body and "a.txt" in body
    msg = jv.report_edit(2, "pon la cifra de las fuentes")
    assert "cambié la parte 2" in msg and "pon la cifra de las fuentes" in asked[-1]
    st2 = proyectos.load_all()[-1]
    assert st2["informe"]["secciones"][1]["texto"] == "Cuesta alrededor de 1,8 millones." and st2["informe"]["revision"] is None
    assert "Cuesta alrededor de 1,8 millones." in "\n".join(p.text for p in Document(rep["ruta"]).paragraphs)
    assert "tiene 2 partes" in jv.report_edit(7, "x")


def test_sin_ia_no_hay_informe_pero_el_proyecto_termina(jv, prj, monkeypatch):
    monkeypatch.setattr(jv, "run_step", _fake_step)
    st = proyectos.new("x", proyectos.validate_plan(json.loads(json.dumps(PLAN))), jv.settings["output_dir"])
    jv.run_project(st)
    assert st["estado"] == "terminado" and not st.get("informe") and "informe" not in prj[-1]


def test_dos_a_la_vez_pausa_y_rehacer(jv, prj, monkeypatch, ask):
    gate = threading.Event()
    started = []

    def slow(st, step):
        started.append(step["id"])
        gate.wait(5)
        return _fake_step(st, step)
    monkeypatch.setattr(jv, "run_step", slow)
    one = {"nombre": "Uno", "pasos": [{"id": "a", "tipo": "texto", "titulo": "A", "pedido": "aaaa", "depende": []},
                                      {"id": "b", "tipo": "texto", "titulo": "B", "pedido": "bbbb", "depende": ["a"]}]}
    sts = [proyectos.new(f"p{i}", proyectos.validate_plan(json.loads(json.dumps(one))), jv.settings["output_dir"]) for i in range(3)]
    ths = [threading.Thread(target=jv.run_project, args=(s,)) for s in sts[:2]]
    for t in ths:
        t.start()
    end = time.time() + 3
    while len(jv.project_runs) < 2 and time.time() < end:
        time.sleep(0.02)
    assert len(jv.project_runs) == 2 and jv.project_run["busy"]
    jv._rec.clear()
    jv.run_project(sts[2])
    assert "Ya tengo 2 proyectos" in jv._rec.said()                         # el tercero espera
    who, said = ask("pausa el proyecto")
    assert who == "PROYECTO" and jv.project_runs[sts[1]["id"]]["pause"]
    assert "(en pausa)" in ask("cómo va el proyecto")[1]
    gate.set()
    time.sleep(0.6)
    assert sts[1]["pasos"][1]["estado"] == "pendiente"                      # en pausa: no empieza el paso B
    ask("sigue con el proyecto")
    for t in ths:
        t.join(5)
    assert all(s["estado"] == "terminado" for s in sts[:2]) and not jv.project_runs and not jv.project_run["busy"]
    b0 = next(b for b in jv.handle_projects_state()["board"] if b["id"] == sts[0]["id"])
    assert b0["pasos"][0]["modelo"] == "potente" and b0["estado"] == "terminado"
    jv.handle_project_action({"id": sts[0]["id"], "action": "redo", "step": "a"})        # rehacer A rehace también B
    end = time.time() + 3
    while time.time() < end and (jv.project_runs or proyectos.load_all()[0]["estado"] != "terminado"):
        time.sleep(0.05)
    again = next(p for p in proyectos.load_all() if p["id"] == sts[0]["id"])
    assert started.count("a") >= 2 and again["estado"] == "terminado"


def test_tablero(jv, prj, ask, monkeypatch):
    opened = []
    monkeypatch.setattr(jv, "_open_page", lambda path, title, holder: opened.append(path))
    assert ask("abre el tablero de proyectos")[0] == "PROYECTO" and opened == ["/proyectos"]
    html = jv.app.test_client().get("/proyectos").get_data(as_text=True)
    assert "PROYECTOS" in html and 'socket.on("project_update"' in html and "Rehacer" in html
