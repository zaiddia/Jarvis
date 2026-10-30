"""Pruebas de la 7.6: centro de aprobaciones y proyectos con sub-agentes."""
import json
import os
import time

import aprobaciones
import proyectos


# ----------------------------------------------------------------------------- aprobaciones
def test_ciclo_de_una_aprobacion(tmp_path):
    aprobaciones.configure(str(tmp_path))
    a = aprobaciones.add("prueba", "Mandar el correo a la coordinadora", "detalle", ttl=60, now=1000)
    assert a["estado"] == "pendiente" and aprobaciones.latest(now=1001)["id"] == a["id"]
    assert aprobaciones.resolve(a["id"], True, "celular", now=1002)["estado"] == "aprobada"
    assert aprobaciones.resolve(a["id"], False, now=1003) is None        # ya no está pendiente
    b = aprobaciones.add("prueba", "Otra", ttl=60, now=2000)
    assert aprobaciones.pending(now=2100) == [] and b["estado"] == "caducada"
    hist = aprobaciones.history(days=36500, now=3000)
    assert [e["evento"] for e in hist] == ["pedida", "aprobada", "pedida", "caducada"]
    assert "aprobaste" in aprobaciones.spoken_history(hist) and "nadie aprobó" in aprobaciones.spoken_history(hist)


def test_aprobar_por_voz_y_por_numero(jv, monkeypatch, tmp_path):
    aprobaciones.configure(str(tmp_path))
    rec = jv._rec
    done = []
    monkeypatch.setitem(jv.settings, "approvals_telegram", False)
    a = jv.request_approval("prueba", "Hacer algo importante", "", on_ok=lambda: done.append("ok"), on_no=lambda: done.append("no"))
    assert rec.replies[-1][1] == "APROBAR" and "¿Lo apruebas?" in rec.replies[-1][0]
    jv.process_command("sí")
    for _ in range(50):
        if done:
            break
        time.sleep(0.02)
    assert done == ["ok"] and aprobaciones.get(a["id"])["estado"] == "aprobada"
    b = jv.request_approval("prueba", "Otra cosa", on_ok=lambda: done.append("ok2"), on_no=lambda: done.append("no2"))
    rec.clear()
    jv.process_command(f"no {b['id']}")
    for _ in range(50):
        if "no2" in done:
            break
        time.sleep(0.02)
    assert "no2" in done and rec.replies[-1][0].startswith("Rechazado")
    rec.clear()
    jv.process_command("sí 77")
    assert "No tengo ninguna aprobación pendiente" in rec.replies[-1][0]
    # «sí» a secas cuando no hay nada pendiente no lo come el centro de aprobaciones
    assert not jv.approvals_answer("si")


def test_aprobar_desde_telegram_y_celular(jv, monkeypatch, tmp_path):
    aprobaciones.configure(str(tmp_path))
    done = []
    monkeypatch.setitem(jv.settings, "approvals_telegram", False)
    a = jv.request_approval("prueba", "Desde el celular", on_ok=lambda: done.append(1))
    jv.telegram_run(f"sí {a['id']}")                          # llega por Telegram (reglas del celular)
    assert aprobaciones.get(a["id"])["estado"] == "aprobada" and aprobaciones.get(a["id"])["por"] == "celular"
    b = jv.request_approval("prueba", "Desde el panel", on_ok=lambda: done.append(2))
    monkeypatch.setitem(jv.settings, "mobile_token", "x" * 32)
    c = jv.mobile_app.test_client()
    assert c.post("/api/aprobar", json={"id": b["id"], "ok": True}).status_code == 403
    r = c.post("/api/aprobar", json={"id": b["id"], "ok": True}, headers={"X-Jarvis-Token": "x" * 32})
    assert r.get_json()["ok"] and aprobaciones.get(b["id"])["estado"] == "aprobada"


def test_un_enlace_no_puede_aprobar(jv, monkeypatch, tmp_path):
    aprobaciones.configure(str(tmp_path))
    monkeypatch.setitem(jv.settings, "approvals_telegram", False)
    a = jv.request_approval("prueba", "Algo delicado")
    import windows_shell
    assert windows_shell.parse_link(f"jarvis://orden/si {a['id']}")      # llega como orden…
    jv.run_link(f"jarvis://orden/si%20{a['id']}")                         # …pero un enlace (una web) no aprueba
    time.sleep(0.3)
    assert aprobaciones.get(a["id"])["estado"] == "pendiente"
    jv._tl.via = "mcp"                                                    # ni otra IA por MCP
    assert not jv.approvals_answer(f"si {a['id']}")
    jv._tl.via = None
    assert aprobaciones.get(a["id"])["estado"] == "pendiente"


def test_lo_que_hice_por_mi_cuenta(jv, tmp_path):
    aprobaciones.configure(str(tmp_path))
    aprobaciones.log("hecha", texto="empecé el proyecto «Semana 7A»")
    rec = jv._rec
    rec.clear()
    jv.process_command("¿qué hiciste por tu cuenta hoy?")
    assert rec.replies[-1][1] == "APROBAR" and "Semana 7A" in rec.replies[-1][0]
    rec.clear()
    jv.process_command("¿qué tengo por aprobar?")
    assert rec.replies[-1][1] == "APROBAR"


# ----------------------------------------------------------------------------- proyectos
PLAN = {"nombre": "Semana de fracciones 7A", "pasos": [
    {"id": "p1", "tipo": "investigar", "titulo": "Investigar fracciones", "pedido": "fracciones para séptimo", "depende": []},
    {"id": "p2", "tipo": "plan", "titulo": "Plan clase 1", "pedido": "plan de clase de fracciones para 7A", "depende": ["p1"]},
    {"id": "p3", "tipo": "quiz", "titulo": "Quiz", "pedido": "quiz de 5 preguntas de fracciones", "depende": ["p2"]},
    {"id": "p4", "tipo": "texto", "titulo": "Carta a padres", "pedido": "carta a padres", "depende": []},
    {"id": "p5", "tipo": "volar", "titulo": "No existe", "pedido": "nada", "depende": []},
    {"id": "p6", "tipo": "rubrica", "titulo": "Ciclo", "pedido": "rúbrica de la exposición", "depende": ["p6", "zz"]},
]}


def test_validar_plan():
    p = proyectos.validate_plan(json.loads(json.dumps(PLAN)), "x")
    ids = [s["id"] for s in p["pasos"]]
    assert sorted(ids) == ["p1", "p2", "p3", "p4", "p6"]                      # sin el tipo inventado
    assert ids.index("p1") < ids.index("p2") < ids.index("p3")              # cada paso después de lo que necesita
    assert next(s for s in p["pasos"] if s["id"] == "p6")["depende"] == []
    assert "5 pasos" in proyectos.spoken_plan(p)
    try:
        proyectos.validate_plan({"pasos": [{"tipo": "volar", "pedido": "x"}]})
        assert False
    except ValueError:
        pass
    ciclo = proyectos.validate_plan({"pasos": [{"id": "a", "tipo": "texto", "pedido": "aaaa", "depende": ["b"]},
                                               {"id": "b", "tipo": "texto", "pedido": "bbbb", "depende": ["a"]}]})
    assert len(ciclo["pasos"]) == 2


def test_reconocer_proyectos():
    for f in ("prepárame la semana de 7A sobre fracciones", "organiza la unidad de ecosistemas para sexto",
              "hazme un proyecto sobre el reciclaje", "proyecto: semana de la ciencia", "prepara todo para la reunión de padres"):
        assert proyectos.is_project(proyectos.safe_name(f).lower().replace("á", "a").replace("é", "e")) or \
            proyectos.is_project(__import__("rutinas").normalize(f)), f
    for f in ("prepara un taller de fracciones", "qué tengo esta semana", "pon un temporizador"):
        assert not proyectos.is_project(__import__("rutinas").normalize(f)), f


def test_proyecto_de_principio_a_fin(jv, monkeypatch, tmp_path):
    proyectos.configure(str(tmp_path))
    aprobaciones.configure(str(tmp_path))
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "docs"))
    monkeypatch.setitem(jv.settings, "approvals_telegram", False)
    monkeypatch.setitem(jv.settings, "project_parallel", 3)
    order, seen_ctx = [], {}
    lock = __import__("threading").Lock()

    def fake_step(st, step):
        with lock:
            order.append(step["id"])
            seen_ctx[step["id"]] = proyectos.context_for(st, step)
        time.sleep(0.05)
        if step["id"] == "p4":
            raise RuntimeError("la IA no respondió")
        path = os.path.join(st["carpeta"], step["id"] + ".docx")
        os.makedirs(st["carpeta"], exist_ok=True)
        open(path, "w").close()
        return {"archivo": path, "resumen": f"resultado de {step['titulo']}"}
    monkeypatch.setattr(jv, "run_step", fake_step)
    notes = []
    monkeypatch.setattr(jv, "notify", lambda text, origin="JARVIS": notes.append(text))
    plan = proyectos.validate_plan(json.loads(json.dumps(PLAN)), "semana")
    st = proyectos.new("prepárame la semana de 7A", plan, jv.settings["output_dir"])
    jv.run_project(st)
    assert st["estado"] == "terminado"
    assert order.index("p1") < order.index("p2") < order.index("p3")
    assert "resultado de Investigar fracciones" in seen_ctx["p2"]          # el sub-agente recibe lo anterior
    estados = {p["id"]: p["estado"] for p in st["pasos"]}
    assert estados == {"p1": "hecho", "p2": "hecho", "p3": "hecho", "p4": "error", "p6": "hecho"}
    assert notes and "4 de 5 pasos" in notes[-1] and "Carta a padres" in notes[-1]
    assert os.path.exists(os.path.join(st["carpeta"], "Resumen del proyecto.txt"))
    assert proyectos.load_all()[-1]["estado"] == "terminado"


def test_planear_pide_aprobacion(jv, monkeypatch, tmp_path):
    proyectos.configure(str(tmp_path))
    aprobaciones.configure(str(tmp_path))
    monkeypatch.setitem(jv.settings, "approvals_telegram", False)
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, json_mode=False, max_tokens=None: json.dumps(PLAN))
    started = []
    monkeypatch.setattr(jv, "run_project", lambda st: started.append(st))
    rec = jv._rec
    rec.clear()
    jv.state["ai"] = "ok"
    jv.process_command("prepárame la semana de 7A sobre fracciones")
    jv.state["ai"] = "unknown"
    assert any("¿Lo hago así?" in r[0] for r in rec.replies) and not started   # antes de empezar, pregunta
    jv.process_command("sí")
    for _ in range(100):
        if started:
            break
        time.sleep(0.02)
    assert started and started[0]["nombre"] == "Semana de fracciones 7A"


def test_dependencia_fallida_omite_lo_que_sigue():
    st = {"pasos": [dict(id="a", estado="error", depende=[]), dict(id="b", estado="pendiente", depende=["a"], error=""),
                    dict(id="c", estado="pendiente", depende=[], error="")]}
    ready = proyectos.ready_steps(st)
    assert [p["id"] for p in ready] == ["c"] and st["pasos"][1]["estado"] == "omitido"


def test_sub_agente_de_texto(jv, monkeypatch, tmp_path):
    if jv.Document is None:
        return
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, json_mode=False, max_tokens=None:
                        "## Saludo\nQueridas familias:\n\nLes cuento que esta semana veremos fracciones.\n\n- Traer regla\n- Traer colores")
    st = {"carpeta": str(tmp_path / "p"), "pasos": [dict(id="a", titulo="Investigar", estado="hecho", resumen="Las fracciones…", depende=[])]}
    step = {"id": "b", "tipo": "texto", "titulo": "Carta a padres", "pedido": "carta a padres", "depende": ["a"]}
    out = jv.run_step(st, step)
    assert out["archivo"].endswith("Carta a padres.docx") and os.path.exists(out["archivo"]) and "fracciones" in out["resumen"]
