"""12.36: modo general y modo docente bien separados, más velocidad y la base de datos de habilidades docentes."""
import inspect
import json
import os
import re

import pytest

import aula
import catalogo_docente as C


@pytest.fixture
def curso(monkeypatch):
    monkeypatch.setitem(aula.data, "cursos", {"7A": ["Ana Gómez", "Luis Pérez", "María Ruiz", "Juan Díaz"]})
    monkeypatch.setitem(aula.data, "activo", "7A")


@pytest.fixture
def quiet(jv, monkeypatch):
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setattr(jv, "start_job", lambda *a, **k: None)
    monkeypatch.setitem(jv.material_job, "busy", False)
    monkeypatch.setitem(jv.office_job, "busy", False)


# ---------------------------------------------------------------- la base de datos
def test_base_de_datos_bien_armada():
    ids = [h["id"] for h in C.H]
    assert len(ids) == len(set(ids)) >= 50
    cats = {c for c, _n, _d in C.CATEGORIAS}
    for h in C.H:
        assert h["cat"] in cats and h["frases"] and h["que"] and h["produce"] and h["necesita"] and h["handler"].endswith("_voice"), h["id"]
    assert sum(len(c["habilidades"]) for c in C.by_cat()) == len(C.H)
    assert C.search("boletines")[0]["id"] == "boletines" and C.search("PIAR")[0]["id"] == "piar"


def test_cada_frase_la_atiende_su_habilidad(jv, ask, quiet, curso, monkeypatch, tmp_path):
    """En modo docente, cada frase del catálogo llega a la función que dice el catálogo (la base de datos no miente)."""
    import informes
    import seguimiento
    for mod in (informes, seguimiento):                  # lo que anotan estas frases no debe quedar para otras pruebas
        monkeypatch.setattr(mod, "data", {})
        if hasattr(mod, "_path"):
            monkeypatch.setattr(mod, "_path", str(tmp_path / f"{mod.__name__}.json"))
    src = inspect.getsource(jv.process_command)
    names = sorted(set(re.findall(r"\b(\w+_voice|\w+_answer|\w+_capture)\(", src)))
    hit = []
    for n in names:
        orig = getattr(jv, n, None)
        if callable(orig):
            def spy(*a, _o=orig, _n=n, **k):
                r = _o(*a, **k)
                if r and not hit:
                    hit.append(_n)
                return r
            monkeypatch.setattr(jv, n, spy)
    bad = []
    for h in C.H:
        for f in h["frases"]:
            hit.clear()
            jv.material_job["busy"] = jv.office_job["busy"] = False
            ask(f)
            if (hit[0] if hit else "-") != h["handler"]:
                bad.append(f"{h['id']}: «{f}» → {hit[0] if hit else 'nadie'} (esperaba {h['handler']})")
    assert not bad, "\n".join(bad)


# ---------------------------------------------------------------- dos roles
def test_cuando_algo_es_del_colegio():
    s = C.school_explicit
    for f in ("crea un quiz para 7A", "¿cómo van mis estudiantes?", "haz la malla del periodo", "prepara la clase de mañana",
              "boletines de 11b", "notas de séptimo"):
        assert s(f), f
    for f in ("hazme un examen de cultura general", "de 5 a 7 de la tarde", "haz grupos con Ana y Luis", "mis clases de baile",
              "organiza mi fin de semana", "una presentación de mi viaje"):
        assert not s(f), f
    assert s("cómo va el grupo Delfines", courses=["Delfines"])


GENERAL = {
    "hazme un examen de cultura general": "MATERIAL",
    "haz un quiz de películas": "MATERIAL",
    "hazme un taller de cocina": "MATERIAL",
    "crea una presentación sobre mi viaje a Cartagena": "DOCUMENTOS",
}


def test_en_modo_general_no_es_profesor(jv, ask, quiet, curso, monkeypatch):
    monkeypatch.setitem(jv.settings, "assistant_mode", "general")
    for f, who in GENERAL.items():
        jv.material_job["busy"] = jv.office_job["busy"] = False
        assert ask(f)[0] == who, f
    for f in ("alertas tempranas", "llama a lista", "haz grupos de 4", "abre la práctica de fracciones", "modo tutor"):
        assert ask(f)[0] not in ("AULA", "ALERTAS", "PRÁCTICA", "TUTOR"), f
    jv.material_job["busy"] = False
    assert ask("crea un quiz para 7A sobre fracciones")[0] == "AULA"                   # si lo dice, es del colegio
    assert ask("haz grupos de 4 en 7A")[0] == "AULA"


def test_en_modo_general_el_material_no_es_de_clase(jv, monkeypatch):
    p = aula.build_prompt("quiz", "examen de cultura general", 10, "7°", general=True)
    assert "no es para un colegio" in p and "docente" not in p and "Grado" not in p and "quien corrige" in p
    p2 = aula.build_prompt("quiz", "quiz de fracciones", 10, "7°")
    assert "docente" in p2 and "Grado: 7°" in p2
    import oficina
    g = oficina.pptx_prompt("mi viaje", 6, general=True)
    assert "no es para una clase" in g and "docente" not in g and "pregunta" not in g.lower().split("reglas")[1][:60]
    assert "docente" in oficina.pptx_prompt("fracciones", 6)


def test_material_general_sin_membrete_ni_banco(jv, quiet, curso, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "assistant_mode", "general")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.settings, "aula_docente", "Profe Pérez")
    monkeypatch.setitem(jv.settings, "aula_institucion", "IE San José")
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="", *a, **k: fn())
    quiz = {"titulo": "Cultura general", "grado": "", "tema": "cultura", "instrucciones": "Marca una.",
            "preguntas": [{"enunciado": f"P{i}", "opciones": ["a", "b", "c", "d"], "respuesta": "a", "explicacion": "x"} for i in range(4)]}
    asked, banked, docs = [], [], []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: asked.append(msgs[0]["content"]) or json.dumps(quiz))
    monkeypatch.setattr(jv.banco, "add_quiz", lambda m: banked.append(m))
    real = aula.build_docx
    monkeypatch.setattr(aula, "build_docx", lambda kind, m, out, D, docente="", inst="", curso="": docs.append((docente, inst, curso)) or real(kind, m, out, D, docente, inst, curso))
    jv.generate_material("hazme un examen de cultura general", "quiz")
    assert "no es para un colegio" in asked[-1] and not banked and docs[-1] == ("", "", "")
    monkeypatch.setitem(jv.settings, "assistant_mode", "docente")
    jv.material_job["busy"] = False
    jv.generate_material("crea un quiz sobre fracciones", "quiz")
    assert banked and docs[-1] == ("Profe Pérez", "IE San José", "7A")


def test_la_personalidad_no_dice_docente(jv):
    import animo
    assert "docente" not in animo.MODES["relajado"][1]


# ---------------------------------------------------------------- velocidad
def test_menos_llamadas_a_la_ia(jv, ask, monkeypatch):
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "_is_local_ai", lambda cfg=None: False)
    calls = []

    def ai(msgs, **k):
        if "parte de Jarvis que entiende" in msgs[0]["content"]:
            calls.append(1)
            return json.dumps({"tipo": "charla"})
        raise jv.AIError("x", kind="config")
    monkeypatch.setattr(jv, "ai_chat", ai)
    ask("oye es que hoy me siento muy cansado y no sé qué hacer con mi tarde")
    assert len(calls) == 1 and jv._rec.ai and jv._rec.ai[-1][1] is False                # sin enrutador después: directo a responder
    calls.clear()
    assert ask("oye sube el volumen")[0] == "skill:volumen" and not calls             # orden corta con «oye»: instantánea, sin IA
    used = []
    import sys
    monkeypatch.setattr(sys.modules["selector"], "choose", lambda text, items, k=8, embed=None, tag="": used.append(embed) or [i[0] for i in items[:k]])
    jv.nl_examples("lo del súper")
    assert used == [None]                                                              # sin pedir «embeddings» a la nube


# ---------------------------------------------------------------- la base de datos, a la vista
def test_catalogo_por_voz_pagina_y_excel(jv, ask, quiet, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    opened = []
    monkeypatch.setattr(jv, "_open_page", lambda path, title, holder: opened.append(path))
    who, said = ask("¿qué puedo hacer en modo docente?")
    assert who == "CATÁLOGO" and opened == ["/docente"] and f"{len(C.H)} habilidades" in said
    assert "Boletines" in ask("habilidades docentes de boletines")[1]
    who, said = ask("exporta el catálogo docente")
    path = os.path.join(str(tmp_path), "Jarvis", "Catálogo de habilidades docentes.xlsx")
    assert who == "CATÁLOGO" and os.path.exists(path)
    from openpyxl import load_workbook
    wb = load_workbook(path)
    assert wb["Todas"].max_row == len(C.H) + 1 and "Evaluación y notas" in wb.sheetnames
    html = jv.app.test_client().get("/docente").get_data(as_text=True)
    assert "HABILIDADES DOCENTES" in html and 'socket.emit("teacher_try"' in html
    r = jv.handle_teacher_catalog({"q": "asistencia"})
    assert r["total"] == len(C.H) and any(h["id"] == "asistencia" for c in r["categorias"] for h in c["habilidades"])
    sent = []
    monkeypatch.setattr(jv, "submit_command", lambda text, source="texto": sent.append(text))
    assert jv.handle_teacher_try({"frase": "llama a lista"})["ok"] and sent == ["llama a lista"]
    assert not jv.handle_teacher_try({"frase": "apaga el pc"})["ok"]                  # solo frases del catálogo


def test_la_comprension_usa_el_catalogo_solo_en_modo_docente(jv, monkeypatch):
    monkeypatch.setattr(jv, "_is_local_ai", lambda cfg=None: False)
    monkeypatch.setitem(jv.settings, "assistant_mode", "docente")
    near = jv.nl_examples("haz los boletines de séptimo")
    assert "haz los boletines de 7A" in near
    monkeypatch.setitem(jv.settings, "assistant_mode", "general")
    assert "haz los boletines de 7A" not in jv.nl_examples("haz los boletines de séptimo")
