"""12.37: el Drive docente lo arma y lo llena Jarvis (solo con lo que él mismo crea)."""
import os
import time

import pytest

import aula
import catalogo_docente as C


class FakeDrive:
    def __init__(self):
        self.files, self.n, self.patched = {}, 0, []

    def call(self, method, path, params=None, body=None, base=""):
        if method == "GET":
            fid = path.split("/")[1]
            if fid not in self.files:
                raise RuntimeError("404")
            return {"id": fid, "trashed": False}
        self.n += 1
        fid = f"f{self.n}"
        self.files[fid] = dict(body, kind="folder")
        return {"id": fid}

    def raw(self, method, url, data, ctype):
        if method == "PATCH":
            self.patched.append(url)
            return {"id": "x"}
        self.n += 1
        fid = f"u{self.n}"
        name = data.split(b'"name": "')[1].split(b'"')[0].decode("unicode_escape") if b'"name"' in data else "?"
        self.files[fid] = {"name": name, "kind": "file", "parents": data.split(b'"parents": ["')[1].split(b'"')[0].decode()}
        return {"id": fid, "webViewLink": f"https://drive/{fid}"}


@pytest.fixture
def drive(jv, monkeypatch, tmp_path):
    fake = FakeDrive()
    fake.files["JARVIS"] = {"name": "Jarvis", "kind": "folder"}
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(jv, "classroom_client", lambda: fake)
    monkeypatch.setattr(jv, "gdrive_ready", lambda: True)
    monkeypatch.setitem(jv.settings, "drive_folder_id", "JARVIS")
    monkeypatch.setitem(jv.settings, "drive_auto", False)
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="", *a, **k: fn())
    monkeypatch.setitem(jv._dd, "last", "")
    return fake


def _folders(fake, parent):
    return {f["name"]: k for k, f in fake.files.items() if f.get("kind") == "folder" and parent in (f.get("parents") or [])}


def test_nombres_iguales_a_la_base_de_datos(jv):
    cats, skills = jv.tree_names()
    assert cats["evaluacion"] == "04 Evaluación y notas" and skills["recuperaciones"] == ("evaluacion", "04 Recuperaciones")
    assert skills["quiz"][1] == "01 Evaluación - quiz" and len(skills) == len(C.H)
    assert "type%3Afolder" in jv.formats_search_url("boletines") and "04%20Boletines%20del%20periodo" in jv.formats_search_url("boletines")


def test_crea_todo_el_arbol_y_el_indice(jv, ask, drive):
    who, said = ask("crea las carpetas docentes en Drive")
    root = _folders(drive, "JARVIS")["Jarvis · Docente"]
    cats = _folders(drive, root)
    assert len(cats) == 10 and "06 Pruebas Saber (ICFES)" in cats
    assert sum(len(_folders(drive, c)) for c in cats.values()) == len(C.H)
    assert "01 Ajustes razonables (PIAR)" in _folders(drive, cats["10 Inclusión"])
    assert any(f["name"] == jv.INDEX_NAME for f in drive.files.values())
    assert f"{len(C.H)} carpetas" in " ".join(t for t, _o in jv._rec.replies)
    n = drive.n
    ask("crea las carpetas docentes en Drive")                       # otra vez: no duplica, solo actualiza el índice
    assert drive.n == n and drive.patched


def test_cada_material_del_colegio_va_a_su_carpeta(jv, drive, tmp_path, monkeypatch):
    monkeypatch.setitem(jv.settings, "assistant_mode", "docente")
    f = tmp_path / "Quiz fracciones 7A.docx"
    f.write_bytes(b"x")
    jv.note_skill("aula_voice", "crea un quiz de 10 preguntas sobre fracciones para 7A")
    assert jv.recent_skill() == "quiz"
    jv.on_new_file(str(f))
    up = [v for v in drive.files.values() if v["kind"] == "file" and v["name"].startswith("Quiz")]
    folder = drive.files[up[0]["parents"]]
    assert folder["name"] == "01 Evaluación - quiz" and drive.files[folder["parents"][0]]["name"] == "02 Material de clase"
    d = jv.dd_load()
    assert d["files"]["quiz"][0]["n"] == "Quiz fracciones 7A.docx" and d["files"]["quiz"][0]["l"].startswith("https://drive/")
    assert jv.folder_links()["quiz"].endswith(d["skills"]["quiz"])
    jv.note_skill("aula_voice", "haz una rúbrica para evaluar una exposición de noveno")
    assert jv.recent_skill() == "rubrica"
    jv.note_skill("boletin_voice", "haz los boletines de 7A")
    assert jv.recent_skill() == "boletines"


def test_lo_general_y_lo_viejo_no_van_al_drive_docente(jv, drive, tmp_path, monkeypatch):
    f = tmp_path / "Examen cultura.docx"
    f.write_bytes(b"x")
    monkeypatch.setitem(jv.settings, "assistant_mode", "general")
    jv.note_skill("aula_voice", "hazme un examen de cultura general")
    assert jv.recent_skill() == ""                                    # no era del colegio
    assert jv.docente_file(str(f)) is False
    monkeypatch.setitem(jv.settings, "assistant_mode", "docente")
    jv.note_skill("aula_voice", "crea un quiz sobre fracciones")
    jv._dd["t"] = time.time() - jv.RECENT - 5                         # hace rato: ya no se asume
    assert jv.docente_file(str(f)) is False
    jv._dd["t"] = time.time()
    monkeypatch.setitem(jv.settings, "drive_docente", False)          # apagado en Ajustes
    assert jv.docente_file(str(f)) is False


def test_la_habilidad_queda_anotada_al_usarla(jv, ask, monkeypatch):
    monkeypatch.setitem(jv.settings, "assistant_mode", "docente")
    monkeypatch.setitem(aula.data, "cursos", {"7A": ["Ana Gómez", "Luis Pérez"]})
    monkeypatch.setattr(jv, "start_job", lambda *a, **k: None)
    monkeypatch.setitem(jv.material_job, "busy", False)
    monkeypatch.setitem(jv._dd, "last", "")
    ask("crea un quiz de 10 preguntas sobre fracciones para séptimo")
    assert jv._dd["last"] == "quiz"
    assert getattr(jv.aula_voice, "skill_noted", False) and getattr(jv.boletin_voice, "school_gated", False)


def test_pagina_con_enlaces_a_drive(jv, drive, monkeypatch):
    opened = []
    monkeypatch.setattr(jv, "_open_link", lambda url: opened.append(url))
    r = jv.handle_teacher_catalog({})
    h = r["categorias"][0]["habilidades"][0]
    assert h["formatos"].startswith("https://drive.google.com/drive/search?q=") and h["drive"] == "" and not r["drive_listo"]
    assert jv.handle_teacher_link({"id": h["id"], "kind": "formatos"})["ok"] and opened[-1] == h["formatos"]
    assert not jv.handle_teacher_link({"id": h["id"], "kind": "drive"})["ok"]          # aún no existe la de Jarvis
    jv.build_tree()
    r = jv.handle_teacher_catalog({})
    assert r["drive_listo"] and r["categorias"][0]["habilidades"][0]["drive"].startswith("https://drive.google.com/drive/folders/")
    assert not jv.handle_teacher_link({"id": "nada", "kind": "drive"})["ok"]
    html = jv.app.test_client().get("/docente").get_data(as_text=True)
    assert "Formatos en Drive" in html and 'socket.emit("teacher_link"' in html


def test_sin_google_lo_dice(jv, ask, monkeypatch):
    monkeypatch.setattr(jv, "gdrive_ready", lambda: False)
    assert "Google conectado" in ask("crea las carpetas docentes en Drive")[1]


def test_todas_las_habilidades_del_colegio_quedan_filtradas(jv):
    """Arreglo: 9 habilidades se cargaban después del filtro de modo (boletines, ensayo, copia, salón…) y se escapaban."""
    assert jv._wrap_catalog_handlers() == []
    for n in C.SCHOOL_ONLY:
        assert getattr(getattr(jv, n), "school_gated", False), n
    for n in {h["handler"] for h in C.H}:
        assert getattr(getattr(jv, n), "skill_noted", False), n


def test_en_modo_general_ya_no_se_cuelan(jv, ask, monkeypatch):
    monkeypatch.setitem(jv.settings, "assistant_mode", "general")
    monkeypatch.setattr(jv, "start_job", lambda *a, **k: None)
    assert ask("ensaya la clase de factorización")[0] == "ENSAYO"                 # «la clase»: sí es del colegio
    for f in ("¿hay copia en las entregas?", "¿mañana hay clase?"):
        assert ask(f)[0] not in ("ENSAYO", "COPIA", "AULA", "SALÓN", "CALENDARIO ESCOLAR"), f
