"""Pruebas de la 12.8: boletines del periodo en PDF, la IA local que ve imágenes, la copia cifrada cada noche en tu Drive
y el panel de salud."""
import io
import json
import os
import zipfile

import pytest

import boletin
import copianube
import datos
import motorlocal
import respaldo

NOTAS = [{"actividad": "Quiz fracciones", "nota": 4.5, "fecha": "2026-09-10"}, {"actividad": "Taller 1", "nota": 3.2, "fecha": "2026-09-12"},
         {"actividad": "Participación", "nota": 4.8, "fecha": "2026-09-22"}, {"actividad": "Autoevaluación", "nota": 4.0, "fecha": "2026-10-01"}]


# ============================================================================ 1. BOLETINES
def test_hoja_y_comentario_sin_ia():
    s = boletin.sheet("7A", "Ana Gómez", NOTAS, 4, [{"fecha": "2026-09-15", "tipo": "positiva", "texto": "Ayudó a sus compañeros."}],
                      {"previos": [3.8, 4.1], "vf_proy": 4.0, "vra": None, "aprobo": True}, materia="Matemáticas", periodo=3)
    assert s["val"] is not None and s["desempeno"] in ("Superior", "Alto", "Básico", "Bajo")
    assert [d["dim"] for d in s["dims"]] == ["Conocer", "Hacer", "Ser", "Autoevaluación"]
    assert dict(s["dims"][1]["actividades"])["Taller 1"] == 3.2
    c = boletin.fallback_comment(s)
    assert "Ana" in c["comentario"] and "Hacer" in c["comentario"] and "4 fallas" in c["comentario"] and len(c["recomendaciones"]) == 2
    vacia = boletin.fallback_comment(boletin.sheet("7A", "Luis Rojas", [], 0))
    assert "no hay notas suficientes" in vacia["comentario"]
    ok = boletin.comment_validate({"comentarios": [{"id": 0, "comentario": "Muy bien.", "recomendaciones": ["Leer", ""]}, {"id": 9, "comentario": "x"}]}, 1)
    assert ok == {0: {"comentario": "Muy bien.", "recomendaciones": ["Leer"]}}
    assert "Matemáticas: 4" in boletin.message("Ana Gómez", [s], "Prof. Ruiz") and boletin.message("A", [s]).startswith("Buen día")


@pytest.mark.skipif(not boletin.available(), reason="sin fpdf2")
def test_pdf_por_estudiante(tmp_path):
    s = boletin.sheet("7A", "Ana Gómez Peña", NOTAS, 1, materia="Tecnología e Informática", periodo=2)
    path = boletin.build_pdf([(s, boletin.fallback_comment(s))], str(tmp_path / "a.pdf"), "IE San José", "Prof. Ruiz")
    raw = open(path, "rb").read()
    assert raw.startswith(b"%PDF") and len(raw) > 2000
    import pypdf
    r = pypdf.PdfReader(path)
    assert len(r.pages) == 1                                                   # sin páginas en blanco por el pie
    text = r.pages[0].extract_text()
    assert "Ana Gómez Peña" in text and "Tecnología" in text and "Hacer" in text


@pytest.mark.skipif(not boletin.available(), reason="sin fpdf2")
def test_boletines_de_un_curso(jv, monkeypatch, tmp_path):
    import seguimiento
    import nucleo.boletines as nb
    monkeypatch.setitem(seguimiento.data, "9B", {"Ana Gómez": NOTAS, "Luis Rojas": NOTAS[:2]})
    monkeypatch.setitem(seguimiento.data, "9B · Tecnología", {"Ana Gómez": NOTAS[2:]})
    monkeypatch.setattr(nb.aula, "students", lambda c: ["Ana Gómez", "Luis Rojas", "Sara Díaz"] if c == "9B" else [])
    monkeypatch.setattr(nb.aula, "find_course", lambda t: "9B" if t.strip().lower() == "9b" else "")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "_absences", lambda c: {"Luis Rojas": 5})
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    monkeypatch.setattr(nb, "_bol_open_folder", lambda f: False)
    told = []
    monkeypatch.setattr(jv, "notify", lambda t, o="": told.append(t))
    asked = []

    def ai(msgs, **k):
        asked.append(msgs)
        n = msgs[0]["content"].count("\nid ")
        return json.dumps({"comentarios": [{"id": i, "comentario": f"Comentario {i}", "recomendaciones": ["Repasar"]} for i in range(n)]})
    monkeypatch.setattr(jv, "ai_chat", ai)
    jv._rec.clear()
    assert jv.boletin_voice("haz los boletines de 9B", "haz los boletines de 9b")
    folder = [d for d in os.listdir(tmp_path / "Boletines")][0]
    files = set(os.listdir(tmp_path / "Boletines" / folder))
    assert files == {"_Mensajes para WhatsApp.txt", "_Todo el curso 9B (para imprimir).pdf", "Ana Gómez.pdf", "Luis Rojas.pdf", "Sara Díaz.pdf"}
    import pypdf
    assert len(pypdf.PdfReader(str(tmp_path / "Boletines" / folder / "Ana Gómez.pdf")).pages) == 2   # matemáticas y tecnología
    assert "Comentario" in pypdf.PdfReader(str(tmp_path / "Boletines" / folder / "Ana Gómez.pdf")).pages[0].extract_text()
    assert asked and "Listos 3 boletines de 9B" in told[-1]
    # sin IA, igual salen (comentario con reglas)
    monkeypatch.setattr(jv, "ai_chat", lambda *a, **k: (_ for _ in ()).throw(jv.AIError("sin internet")))
    r = jv.make_boletines("9B", ["Luis Rojas"])
    assert r["n"] == 1 and not r["used_ai"] and os.path.exists(r["files"][0])


def test_ordenes_de_boletines():
    import nucleo.boletines as nb
    for t in ("haz los boletines de 7a", "boletin de ana gomez de 7a", "boletines del periodo de 9b", "boletines de todos los cursos"):
        assert nb._BOL_RE.search(t), t
    assert nb._BOL_RE.search("boletines de todos los cursos").group(1) == "todos los cursos"
    assert not nb._BOL_RE.search("busca un boletin de noticias en internet sobre clima")
    assert nb._BOL_RE.search("jarvis boletin de 7a") and nb._BOL_RE.search("boletines").group(1) is None


# ============================================================================ 5. LA IA LOCAL VE
def test_archivo_de_vision():
    sib = [{"rfilename": n} for n in ("Qwen3-VL-4B-Instruct-Q4_K_M.gguf", "mmproj-Qwen3-VL-4B-Instruct-F32.gguf",
                                      "mmproj-Qwen3-VL-4B-Instruct-F16.gguf", "README.md")]
    assert motorlocal.pick_mmproj(sib) == "mmproj-Qwen3-VL-4B-Instruct-F16.gguf"
    assert motorlocal.pick_gguf(sib) == "Qwen3-VL-4B-Instruct-Q4_K_M.gguf"            # el modelo no es el archivo de visión
    assert motorlocal.pick_mmproj([{"rfilename": "mmproj-model-f16.gguf"}]) == "mmproj-model-f16.gguf"
    assert motorlocal.pick_mmproj(sib[:1]) == ""
    assert motorlocal.entry_for_file("Qwen3-VL-4B-Instruct-Q4_K_M.gguf")["id"] == "qwen3-vl-4b"
    assert motorlocal.entry_for_file("Qwen3-4B-Instruct-2507-Q4_K_M.gguf")["id"] == "qwen3-4b"
    assert motorlocal.entry_for_file("gemma-3-4b-it-Q4_K_M.gguf")["vision"] and motorlocal.entry_for_file("mio.gguf") is None
    a = motorlocal.server_args("srv", "m.gguf", mmproj="v.gguf")
    assert a[a.index("--mmproj") + 1] == "v.gguf" and "--mmproj" not in motorlocal.server_args("srv", "m.gguf")
    assert motorlocal.recommend(16, 50)["id"] == "qwen3-4b"                           # para escribir, el de solo texto


def test_imagenes_van_a_la_ia_local_si_ve(jv, monkeypatch, tmp_path):
    from PIL import Image
    img = tmp_path / "taller.png"
    Image.new("RGB", (3000, 2000), "white").save(img)
    motor = jv._ai_cfg({"ai_provider": "motor"})
    body, _ = jv._oa_body(motor, [{"role": "user", "content": "¿qué ves?"}], 100, image_path=str(img))
    url = body["messages"][-1]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    import base64
    small = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    assert max(small.size) <= 1024                                             # más pequeña: la lee más rápido
    # con visión: la elige para ver
    monkeypatch.setitem(jv.settings, "ai_provider", "motor")
    monkeypatch.setattr(jv, "motor_sees", lambda: True)
    cfg, err = jv._vision_cfg()
    assert cfg and cfg["ai_provider"] == "motor" and not err
    # sin visión (y sin Gemini): lo dice y cómo arreglarlo
    monkeypatch.setattr(jv, "motor_sees", lambda: False)
    monkeypatch.setattr(jv, "_gemini_for_stt", lambda: None)
    cfg, err = jv._vision_cfg()
    assert cfg is None and "dale visión a la IA local" in err
    monkeypatch.setattr(jv, "motor_ensure", lambda: None)
    with pytest.raises(jv.AIError):
        jv._cloud_chat(motor, [{"role": "user", "content": "x"}], image_path=str(img))
    # la imagen sí llega a la IA integrada cuando ve
    monkeypatch.setattr(jv, "motor_sees", lambda: True)
    got = {}
    monkeypatch.setattr(jv, "openai_chat", lambda cfg, m, j, t, image_path=None: got.update(img=image_path) or "<think>…</think>Un taller")
    assert jv._cloud_chat(motor, [{"role": "user", "content": "x"}], image_path=str(img)) == "Un taller" and got["img"] == str(img)


def test_dar_vision_pide_permiso(jv, monkeypatch):
    import nucleo.motor as mt
    asked, jobs = [], []
    monkeypatch.setattr(jv, "request_approval", lambda tipo, titulo, detalle="", on_ok=None, on_no=None, **k: asked.append((tipo, titulo, on_ok)))
    monkeypatch.setattr(jv, "motor_vision_job", lambda: jobs.append(1))
    monkeypatch.setattr(mt, "motor_sees", lambda: False)
    monkeypatch.setattr(jv, "motor_paths", lambda: ("/x/llama-server", "/x/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"))
    jv._rec.clear()
    assert jv.motor_voice("dale visión a la IA local", "dale vision a la ia local")
    assert asked[-1][0] == "instalar" and "Qwen3 VL 4B" in asked[-1][1] and not jobs     # su modelo no ve: propone el que ve
    asked[-1][2]()
    assert jobs == [1]
    monkeypatch.setattr(jv, "motor_paths", lambda: ("/x/llama-server", "/x/gemma-3-4b-it-Q4_K_M.gguf"))
    assert "Gemma 3 4B" in mt.vision_plan()[0] and mt.vision_plan()[1] == 0.8                # el suyo ve: solo los ojos


def test_motor_arranca_con_vision(jv, monkeypatch, tmp_path):
    import nucleo.motor as mt
    model = tmp_path / "modelos" / "gemma-3-4b-it-Q4_K_M.gguf"
    vis = tmp_path / "vision" / "gemma-3-4b-it-Q4_K_M.gguf"
    for p in (model, vis):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    monkeypatch.setattr(mt, "_dir", lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.setattr(jv, "motor_paths", lambda: ("/x/srv", str(model)))
    mt.engine["no_mm"] = False
    assert mt.motor_mmproj() == str(vis) and mt.motor_sees()
    mt.engine["no_mm"] = True                                                  # no arrancó con ella: queda solo texto
    assert mt.motor_mmproj() == "" and not mt.motor_sees()
    mt.engine["no_mm"] = False


# ============================================================================ 9. COPIA CIFRADA EN LA NUBE
def test_cifrado_de_la_copia():
    blob = copianube.seal(b"hola mundo" * 50, "clave-segura-123")
    assert copianube.is_sealed(blob) and b"hola" not in blob
    assert copianube.unseal(blob, "clave-segura-123") == b"hola mundo" * 50
    with pytest.raises(copianube.WrongPassword):
        copianube.unseal(blob, "otra-clave-999")
    with pytest.raises(ValueError):
        copianube.seal(b"x", "corta")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.json", "{}")
    z2 = copianube.with_key(buf.getvalue(), "K" * 44)
    rest, key = copianube.split_key(z2)
    assert key == "K" * 44 and zipfile.ZipFile(io.BytesIO(rest)).namelist() == ["a.json"]
    assert copianube.split_key(buf.getvalue())[1] == ""
    assert copianube.cloud_name("C:/x/Jarvis respaldo 2026-11-06 213000 (automática).zip") == "Jarvis respaldo 2026-11-06 213000 (automática).jvbk"
    assert copianube.is_copy("Jarvis respaldo 1.jvbk") and copianube.is_copy("Jarvis respaldo 1.zip") and not copianube.is_copy("quiz.docx")


def test_cuando_toca_la_copia_de_la_noche():
    import datetime as dt
    d = dt.datetime
    assert copianube.due(d(2026, 11, 6, 10), "")                                    # nunca se ha hecho: ya
    assert not copianube.due(d(2026, 11, 6, 22), "2026-11-06T21:05:00")             # ya se hizo hoy
    assert copianube.due(d(2026, 11, 6, 21, 1), "2026-11-05T21:10:00")              # llegó la hora
    assert not copianube.due(d(2026, 11, 6, 8), "2026-11-05T22:00:00")              # aún no
    assert copianube.due(d(2026, 11, 7, 9), "2026-11-05T21:00:00")                  # anoche estaba apagado: ahora


def test_restaurar_tambien_lo_cifrado(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "data_key", datos.new_key())
    monkeypatch.setitem(jv.settings, "protect_students", True)
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    datos.write_json(str(cfg / "notas_estudiantes.json"), {"7A": {"Ana": [{"actividad": "q", "nota": 4}]}})
    assert datos.is_encrypted(open(cfg / "notas_estudiantes.json", "rb").read())
    res = respaldo.create(str(cfg), str(tmp_path / "bk"), {"theme": "cyan"})
    parts = {p["part"] for p in respaldo.inspect(res["path"])["parts"]}
    assert "seguimiento" in parts                                              # antes se saltaba y no se podía restaurar


def test_sube_cifrada_y_se_trae(jv, monkeypatch, tmp_path):
    import nucleo.proteccion as pr
    key = datos.new_key()
    monkeypatch.setitem(jv.settings, "data_key", key)
    monkeypatch.setitem(jv.settings, "protect_students", True)
    monkeypatch.setitem(jv.settings, "cloud_pass", "mi-clave-larga")
    monkeypatch.setitem(jv.settings, "backup_dir", str(tmp_path / "bk"))
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    datos.write_json(str(cfg / "notas_estudiantes.json"), {"7A": {"Ana": []}})
    res = respaldo.create(str(cfg), str(tmp_path / "bk"), {"theme": "cyan"})
    drive = {}

    def upload(client, path, folder):
        drive[os.path.basename(path)] = open(path, "rb").read()
        return {"name": os.path.basename(path)}
    monkeypatch.setattr(jv, "classroom_client", lambda: object())
    monkeypatch.setattr(pr, "_drive_backup_folder", lambda c: "F")
    monkeypatch.setattr(pr.gservicios, "upload", upload)
    monkeypatch.setattr(pr.gservicios, "list_folder", lambda c, f: [{"id": n, "name": n, "createdTime": "2026-11-06T21:00:00Z", "size": len(b)}
                                                                       for n, b in drive.items()])
    monkeypatch.setattr(pr.gservicios, "delete", lambda c, i: drive.pop(i, None))
    monkeypatch.setattr(pr.gservicios, "download", lambda c, i: drive[i])
    applied = {}
    monkeypatch.setattr(jv, "apply_settings", lambda d: applied.update(d) or jv.settings.update(d))
    name = jv.backup_to_drive(res["path"])
    assert name.endswith(".jvbk") and copianube.is_sealed(drive[name]) and b"notas_estudiantes" not in drive[name]
    assert applied.get("cloud_last") and not os.path.exists(os.path.join(jv.CONFIG_DIR, "tmp", name))   # no queda copia suelta
    # equipo nuevo: sin clave de las notas; con la clave de las copias, la trae y pone la de las notas
    monkeypatch.setitem(jv.settings, "data_key", "")
    unlocked = []
    monkeypatch.setattr(pr, "unlock_students", lambda k: unlocked.append(k))
    r = jv.cloud_fetch(name)
    assert unlocked == [key] and r["clave_datos"] == "puse" and "seguimiento" in {p["part"] for p in r["info"]["parts"]}
    assert copianube.KEY_MEMBER not in zipfile.ZipFile(os.path.join(jv.backup_folder(), r["name"])).namelist()
    with pytest.raises(copianube.WrongPassword):
        jv.cloud_fetch(name, "otra-clave-larga")
    # la de la noche: una copia y a Drive (sin subirla dos veces)
    made = []
    monkeypatch.setattr(jv, "make_backup", lambda kind="manual", include_secrets=None, upload=True: made.append((kind, upload)) or res)
    jv.cloud_backup_now("auto")
    assert made == [("auto", False)]


def test_ordenes_de_la_nube():
    import nucleo.proteccion as pr
    assert pr._CLOUD_FETCH.search("trae la copia de mi drive") and pr._CLOUD_FETCH.search("descarga el respaldo de la nube")
    assert pr._CLOUD_WHEN.search("cuando fue la ultima copia en la nube")
    assert not pr._CLOUD_FETCH.search("haz una copia de seguridad en drive")


# ============================================================================ 10. PANEL DE SALUD
def test_panel_de_salud(jv, monkeypatch):
    monkeypatch.setattr(jv, "motor_status", lambda: {"modelo": "", "recomendado": "Qwen3 4B", "recomendado_gb": 2.5})
    snap = jv.health_snapshot()
    ids = [c["id"] for c in snap["cards"]]
    for need in ("ia", "local", "voz", "red", "copias", "datos", "errores", "equipo", "version"):
        assert need in ids, need
    assert 0 <= snap["score"] <= 100 and all(c["estado"] in ("ok", "aviso", "fallo", "info") for c in snap["cards"])
    local = next(c for c in snap["cards"] if c["id"] == "local")
    assert local["accion"] == {"label": "Instalar", "socket": "motor", "data": {"action": "instalar"}}
    from nucleo.panelsalud import _hp_score
    assert _hp_score([{"estado": "ok"}, {"estado": "fallo"}, {"estado": "info"}]) == 50
    client = jv.app.test_client()
    html = client.get("/salud").get_data(as_text=True)
    assert "SALUD" in html and "health_snapshot" in html


def test_orden_del_panel(jv, monkeypatch):
    opened = []
    monkeypatch.setattr(jv, "open_window", lambda path, title: opened.append(path))
    jv._rec.clear()
    assert jv.health_panel_voice("abre el panel de salud", "abre el panel de salud")
    assert opened == ["/salud"] and "de 100" in jv._rec.said()
    assert not jv.health_panel_voice("prueba completa", "prueba completa")


def test_las_frases_llegan(jv, monkeypatch):
    import nucleo.boletines as nb
    import nucleo.proteccion as pr
    hits = []
    monkeypatch.setattr(nb, "boletines_for", lambda target, origin="": hits.append(("bol", target)) or True)
    monkeypatch.setattr(jv, "open_window", lambda path, title: hits.append(("win", path)))
    monkeypatch.setattr(jv, "handle_motor", lambda d: hits.append(("motor", d["action"])) or {"msg": "ok"})
    monkeypatch.setattr(pr, "cloud_info", lambda: {"ultima": "2026-11-06T21:03:00", "lista": True, "falta": ""})
    for text in ("Jarvis, haz los boletines de 7A", "boletín de Ana Gómez de 7A", "abre el panel de salud", "dale visión a la IA local",
                 "¿cuándo fue la última copia en la nube?"):
        jv._rec.clear()
        jv.process_command(text)
    assert ("bol", "7a") in hits and ("bol", "ana gomez de 7a") in hits and ("win", "/salud") in hits and ("motor", "vision") in hits
    assert "06" in jv._rec.said() and "21:03" in jv._rec.said()
