"""Pruebas de la 11.8: HUD de alto impacto (momento del día, bandeja única, fórmulas, proyectar, paleta, orbe y
«Lo que hice hoy» con deshacer)."""
import datetime
import os

import pytest

import bitacora
import horario
import mathtext
import momento

D = datetime.datetime(2026, 10, 27, 0, 0)          # martes


def _at(h, m=0, day=D):
    return day.replace(hour=h, minute=m)


ITEMS = [{"dia": 1, "inicio": "07:00", "fin": "07:55", "curso": "7A", "materia": "Matemáticas"},
         {"dia": 1, "inicio": "09:00", "fin": "09:55", "curso": "10A", "materia": "Trigonometría"}]


def test_momento_del_dia():
    mo = lambda h, m=0, **k: momento.moment(_at(h, m), ITEMS, **k)["id"]       # noqa: E731
    assert mo(6, 0) == "inicio" and mo(6, 45) == "preparar" and mo(7, 30, in_class=True) == "clase"
    assert mo(8, 10) == "entre" and mo(8, 45) == "preparar" and mo(11, 0) == "cierre" and mo(19, 0) == "noche"
    assert momento.moment(_at(19, 0, D + datetime.timedelta(days=3)), [])["id"] == "libre"          # viernes en la noche
    assert momento.moment(_at(10, 0, D + datetime.timedelta(days=4)), [])["id"] == "libre"          # sábado
    m = momento.moment(_at(8, 50), ITEMS)
    assert m["siguiente"]["curso"] == "10A" and m["en"] == 10 and m["quedan"] == 1


def test_formulas_en_palabras_y_texto():
    t = r"Resuelve $x^2+3x-4=0$: $x=\frac{-3\pm\sqrt{25}}{2}$. Cuesta $5 y $10."
    assert [f for f, _ in mathtext.segments(t)] == [False, True, False, True, False]
    sp = mathtext.speech(t)
    assert "x al cuadrado más 3x menos 4 igual a 0" in sp and "raíz de 25" in sp and "Cuesta $5 y $10" in sp
    assert mathtext.plain(t).startswith("Resuelve x²+3x-4=0: x=(-3±√25)/(2)")
    assert mathtext.to_plain(r"\frac{3}{4} + \sqrt[3]{8} \cdot \pi") == "3/4 + ∛(8) · π"
    assert mathtext.graphable(r"La recta es $y = 2x + 1$") == "y = 2x + 1" and mathtext.graphable("hola") == ""
    import jarvis
    assert "x al cuadrado" in jarvis._clean_for_speech(r"Es $x^2$ siempre")
    assert "$" in jarvis.MATH_RULE


def test_bitacora_agrupa_y_deshace():
    bitacora.clear()
    out = []
    for i in range(3):
        bitacora.add(f"nota {i}", "nota", undo=lambda i=i: out.append(i), group=("g",), group_text=lambda n: f"{n} notas")
    bitacora.add("sin deshacer", "aprobacion")
    items = bitacora.today()
    assert len(items) == 2 and items[0]["texto"] == "3 notas" and items[0]["n"] == 3 and not items[1]["puede"]
    ok, msg = bitacora.undo(items[0]["id"])
    assert ok and out == [2, 1, 0] and msg.startswith("Deshecho: 3 notas")
    assert not bitacora.undo(items[0]["id"])[0] and not bitacora.undo(items[1]["id"])[0]
    assert bitacora.last_undoable() is None
    assert "Hoy hice 1 cosa" in bitacora.spoken(bitacora.today())


@pytest.fixture
def jr(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv.seguimiento, "save", lambda: None)
    monkeypatch.setattr(jv.informes, "save", lambda: None)
    monkeypatch.setattr(jv.aula, "save", lambda: None)
    monkeypatch.setattr(jv.notas, "save", lambda: None)
    jv.install_journal()
    bitacora.clear()
    yield jv
    bitacora.clear()


def test_lo_que_hice_hoy_con_deshacer(jr, tmp_path, monkeypatch):
    jv = jr
    jv.seguimiento.add("9Z", "Ana", "Quiz", 4.5)
    jv.seguimiento.add("9Z", "Luis", "Quiz", 3.0)                       # seguidas: un solo renglón
    lst = jv.journal_list()
    assert lst[0]["texto"] == "Anoté 2 notas de «Quiz» (9Z)" and lst[0]["puede"]
    assert jv.handle_journal_undo({"id": lst[0]["id"]})["ok"]
    assert not jv.seguimiento.data["9Z"]["Ana"] and not jv.seguimiento.data["9Z"]["Luis"]
    e = jv.informes.add("9Z", "Ana", "Participó en clase.", tipo="positiva")
    assert jv.journal_list()[0]["texto"].startswith("Participación de Ana (9Z)")
    jv._rec.clear()
    jv.process_command("deshaz lo último")
    assert "Deshecho" in jv._rec.said() and e not in jv.informes.data["9Z"]["Ana"]
    n = jv.notas.add("comprar marcadores")
    assert any(x["texto"] == "Pendiente: comprar marcadores" for x in jv.journal_list())
    bitacora.undo(bitacora.last_undoable()["id"])
    assert not any(x["id"] == n["id"] for x in jv.notas.notes)
    f = tmp_path / "Quiz.docx"
    f.write_bytes(b"x")
    jv.journal_file(str(f))
    jv.journal_file(str(f))                                               # no se repite
    files = [x for x in jv.journal_list() if x["tipo"] == "archivo"]
    assert len(files) == 1 and files[0]["texto"] == "Creé «Quiz.docx»"
    bitacora.undo(files[0]["id"])
    assert not f.exists() and (tmp_path / "Papelera de Jarvis" / "Quiz.docx").exists()      # a la papelera, no se borra
    jv._rec.clear()
    jv.process_command("¿qué hiciste hoy?")
    assert "Hoy hice" in jv._rec.said()


def test_panel_por_momento_bandeja_y_lista(jr, monkeypatch):
    jv = jr
    monkeypatch.setattr(horario, "items", list(ITEMS))
    monkeypatch.setattr(jv, "_weather_short", lambda: "")
    monkeypatch.setitem(jv.live_class, "on", False)
    monkeypatch.setitem(jv.aula.data, "cursos", {**jv.aula.data.get("cursos", {}), "7A": ["Ana Gómez", "Luis Rojas"]})
    d = jv.dashboard(_at(7, 30))
    mo = d["momento"]
    assert mo["id"] == "clase" and mo["curso"] == "7A" and mo["falta"] == 25 and [x["n"] for x in mo["lista"]["estudiantes"]] == ["Ana Gómez", "Luis Rojas"]
    assert d["orbe"]["progreso"] is not None and d["orbe"]["clase"] == "7A" and "bandeja" in d and "hice" in d
    r = jv.handle_roster_act({"curso": "7A", "est": "Ana Gómez", "action": "falla"})
    assert r["ok"] and r["lista"]["estudiantes"][0]["falta"]
    r = jv.handle_roster_act({"curso": "7A", "est": "Luis Rojas", "action": "positiva", "tema": "fracciones"})
    assert r["ok"] and r["lista"]["estudiantes"][1]["pos"] == 1
    assert not jv.handle_roster_act({"curso": "7A", "est": "Nadie", "action": "falla"})["ok"]
    assert [x["texto"].split(":")[0] for x in jv.journal_list()][:2] == ["Participación de Luis Rojas (7A)", "Falla"]
    jv.handle_roster_act({"curso": "7A", "est": "Ana Gómez", "action": "presente"})
    d = jv.dashboard(_at(8, 45))
    assert d["momento"]["id"] == "preparar" and d["momento"]["curso"] == "10A" and d["momento"]["acciones"][0]["t"] == "Prepárame esto"
    d = jv.dashboard(_at(20, 0))
    assert d["momento"]["id"] == "noche" and [c["curso"] for c in d["momento"]["manana"]] == []       # miércoles sin clases
    # bandeja: aprobaciones y atención juntas; ocultar una de atención
    jv.request_approval("notas", "Guardar notas de 7A", "x", on_ok=lambda: None, ttl=60)
    monkeypatch.setattr(jv, "attention_items", lambda now=None: [{"k": "no:1", "p": 1, "t": "atrasado: planilla", "cmd": "¿qué tengo pendiente?"}])
    box = jv.inbox()
    assert box[0]["tipo"] == "aprobar" and any(x["k"] == "no:1" for x in box)
    jv.handle_inbox_snooze({"k": "no:1"})
    assert not any(x["k"] == "no:1" for x in jv.inbox())
    for a in jv.aprobaciones.pending():
        jv.resolve_approval(a["id"], False, "prueba")


def test_botones_de_la_respuesta_y_proyector(jr, monkeypatch, tmp_path):
    jv = jr
    emitted = []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: emitted.append((ev, data)))
    monkeypatch.setattr(jv, "_open_projector", lambda: None)
    monkeypatch.setitem(jv.hud, "proj_open", True)
    txt = "La fórmula: $x = \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}$\n- primero\n- segundo"
    assert jv.handle_msg_action({"text": txt, "action": "proyectar"})["ok"]
    show = [d for e, d in emitted if e == "projector_show"][-1]
    assert show["kind"] == "texto" and show["text"] == txt and jv.handle_projector_now() ["kind"] == "texto"
    assert any(e == "projecting" and d["on"] for e, d in emitted)
    jv.handle_project_clear()
    assert jv.handle_projector_now()["kind"] == "nada"
    added = []
    monkeypatch.setattr(jv.generated_files, "add", lambda p: added.append(p))
    assert jv.handle_msg_action({"text": txt, "action": "word"})["ok"]
    from docx import Document
    paras = [p.text for p in Document(added[0]).paragraphs]
    assert "La fórmula: x = (-b ± √(b²-4ac))/(2a)" in paras and "primero" in paras
    sent = []
    monkeypatch.setattr(jv, "submit_command", lambda t, s="texto": sent.append(t))
    assert jv.handle_msg_action({"text": "La recta $y = 2x + 1$", "action": "graficar"})["ok"] and sent == ["grafica y = 2x + 1"]
    assert not jv.handle_msg_action({"text": "hola", "action": "graficar"})["ok"]
    # por voz: «proyecta eso»
    monkeypatch.setattr(jv, "chat_buffer", [{"role": "user", "text": "x"}, {"role": "jarvis", "text": "El área del círculo es $\\pi r^2$."}])
    emitted.clear(); jv._rec.clear()
    jv.process_command("proyecta eso")
    assert "en el proyector" in jv._rec.said() and [d for e, d in emitted if e == "projector_show"][-1]["text"].startswith("El área")


def test_paleta_y_letra(jr, monkeypatch):
    jv = jr
    monkeypatch.setattr(horario, "items", list(ITEMS))
    monkeypatch.setattr(jv, "moment_card", lambda now, out: {"id": "clase", "curso": "7A", "acciones": [{"t": "Escoger estudiante", "cmd": "escoge un estudiante"}]})
    pal = jv.handle_palette()
    assert pal["smart"][0] == {"t": "escoge un estudiante", "g": "Ahora", "label": "Escoger estudiante"}
    assert any(x["t"] == "exporta las notas de 7A para Zeti" for x in pal["smart"]) and not any(x["g"] == "Nuevo" for x in pal["examples"])
    saved = []
    monkeypatch.setattr(jv, "apply_settings", lambda d: saved.append(d) or jv.settings.update(d))
    monkeypatch.setitem(jv.settings, "hud_text_size", "normal")
    assert jv.handle_hud_text_size({})["size"] == "grande" and jv.handle_hud_text_size({"size": "proyector"})["size"] == "proyector"
    assert jv._validate("hud_text_size", "proyector") == "proyector"
    with pytest.raises(ValueError):
        jv._validate("hud_text_size", "gigante")


def test_paginas_cargan_katex():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("hud.html", "proyector.html"):
        html = open(os.path.join(here, "templates", name), encoding="utf-8").read()
        assert "vendor/katex/katex.min.js" in html and "js/mdmath.js" in html, name
    assert os.path.exists(os.path.join(here, "static", "vendor", "katex", "fonts", "KaTeX_Main-Regular.woff2"))
    js = open(os.path.join(here, "static", "js", "hud.js"), encoding="utf-8").read()
    for name in ("function momentCard(", "function inboxCard(", "function doneCard(", "function drawOrb(", "msg_action", "roster_act", "hud_text_size"):
        assert name in js, name
