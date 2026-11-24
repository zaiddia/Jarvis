"""Pruebas de la 12.52: vigía de páginas, escritura de la clase, «piénsalo bien / rápido», modo privado, lo clave primero,
infografías, herramientas a tu medida y estilos."""
import json
import os

import escrituraclase as EC
import estilojarvis as EJ
import infografia as IG
import misherramientas as MH


# ---------------------------------------------------------------- 2. escritura
def test_escritura_puro():
    d = {"estudiante": "", "fortalezas": ["Buena idea central"], "mejorar": ["Usa conectores"], "nivel": "basico",
         "errores": [{"tipo": "Tildes", "dice": "arbol", "debe_decir": "árbol"}, {"tipo": "ortografia", "dice": "aser", "debe_decir": "hacer"}],
         "comentario": "Vas bien."}
    r = EC.clean_student(d, "Ana_Gomez.jpg")
    assert r["estudiante"] == "Ana Gomez" and r["nivel"] == "básico" and [e["tipo"] for e in r["errores"]] == ["tildes", "ortografía"]
    r2 = EC.clean_student({"errores": [{"tipo": "tilde", "dice": "cancion", "debe_decir": "canción"}], "nivel": "alto"}, "b.pdf")
    common = EC.common_errors([r, r2])
    assert common[0][0] == "tildes" and common[0][1] == 2
    assert EC.levels([r, r2]) == [("básico", 1), ("alto", 1)]
    assert "<<<" in EC.student_prompt("texto", "Describe tu barrio", "7A")


def test_escritura_de_la_clase(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    its = [{"id": f"a{i}", "nombre": f"est{i}.txt", "tipo": "texto", "t": 0} for i in range(3)]
    monkeypatch.setattr(jv, "_text_of_item", lambda it: "Mi barrio es muy bonito porque ay arboles y la jente es amable con todos los vecinos del sector.")

    def ai(msgs, json_mode=False, max_tokens=None):
        if "mini-clase" in msgs[0]["content"]:
            return json.dumps({"objetivo": "Usar bien la h y las tildes", "explicacion": "La h no suena…",
                               "ejercicios": [{"enunciado": "Corrige: ay arboles", "respuesta": "hay árboles"}], "cierre": "Repasa."})
        return json.dumps({"estudiante": "", "fortalezas": ["Describe bien"], "mejorar": ["Ortografía"], "nivel": "básico",
                           "errores": [{"tipo": "ortografía", "dice": "ay", "debe_decir": "hay"}, {"tipo": "tildes", "dice": "arboles", "debe_decir": "árboles"}],
                           "comentario": "Buen trabajo."})
    monkeypatch.setattr(jv, "ai_chat", ai)
    path, reviews, common = jv.writing_feedback(its, "Describe tu barrio", "7A")
    assert os.path.exists(path) and len(reviews) == 3 and common[0][1] == 3
    import docx
    txt = "\n".join(p.text for p in docx.Document(path).paragraphs)
    assert "Mini-clase" in txt and "«ay» → «hay»" in txt and "Usar bien la h" in txt


# ---------------------------------------------------------------- 3, 5, 9. estilos, clave primero, piénsalo bien
def test_estilos_y_pensar(jv, monkeypatch):
    assert EJ.style_from("modo breve") == "breve" and EJ.style_from("se mas amable") == "amable"
    assert EJ.style_from("activa el modo formal") == "formal" and EJ.style_from("modo docente") == ""
    assert EJ.deep_question("piensalo bien: como organizo la nivelacion de 9b") == "como organizo la nivelacion de 9b"
    assert EJ.fast_question("rapido: cuanto es el 15 % de 80 mil") and not EJ.fast_question("rapido")
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    jv._rec.clear()
    jv.process_command("modo breve")
    assert jv.settings["assistant_style"] == "breve" and "una sola frase" in jv.style_rule() and "PRIMERA frase" in jv.style_rule()
    assert "ESTILO BREVE" in jv.system_static() if hasattr(jv, "system_static") else True
    jv.process_command("modo normal")
    assert jv.settings["assistant_style"] == "normal"
    # piénsalo bien: va en segundo plano y pide espacio para pensar (la IA de trabajos pesados, si la hay)
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    seen = {}
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: seen.update(k=k, m=msgs) or "Primero, agrupa por desempeño.")
    said = []
    monkeypatch.setattr(jv, "notify", lambda m, o="": said.append(m))
    monkeypatch.setattr(jv, "save_memory", lambda: None)
    jv._rec.clear()
    jv.process_command("Jarvis, piénsalo bien: ¿cómo organizo la nivelación de 9B?")
    assert seen["k"]["max_tokens"] >= jv.HEAVY_MIN_TOKENS and said == ["Primero, agrupa por desempeño."]
    assert "nivelación de 9B" in seen["m"][1]["content"]


# ---------------------------------------------------------------- 4. privado
def test_modo_privado(jv, monkeypatch, tmp_path):
    import diario
    import recuerdos
    saved = []
    monkeypatch.setattr(jv, "MEMORY_PATH", str(tmp_path / "mem.json"))
    jv.chat_history[:] = [{"role": "user", "content": "antes"}]
    jv._rec.clear()
    jv.process_command("activa el modo privado")
    assert jv.private_on() and diario.paused and recuerdos.paused and "no guardo" in jv._rec.said()
    jv.chat_history.append({"role": "user", "content": "algo delicado"})
    jv.save_memory()
    assert not os.path.exists(tmp_path / "mem.json")                            # nada al disco
    jv.process_command("¿estamos en modo privado?")
    jv.process_command("sal del modo privado")
    assert not jv.private_on() and not diario.paused and [m["content"] for m in jv.chat_history] == ["antes"]
    assert "algo delicado" not in open(tmp_path / "mem.json", encoding="utf-8").read()


# ---------------------------------------------------------------- 7. infografía
def test_infografia(jv, monkeypatch, tmp_path):
    g = IG.clean({"titulo": "El ciclo del agua", "subtitulo": "Cómo viaja el agua", "dato_clave": "El 97 % del agua del planeta es salada.",
                  "secciones": [{"titulo": "Evaporación", "puntos": ["El sol calienta el agua", "Sube como vapor"]},
                                {"titulo": "Condensación", "puntos": ["Se forman las nubes"]},
                                {"titulo": "Precipitación", "puntos": ["Cae como lluvia o granizo", "Llena ríos y mares"]}], "cierre": "¡Cuida el agua!"})
    import animar
    img = IG.render(g, animar.font, "oscuro")
    assert img.size == (1080, 1920)
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "ai_chat", lambda *a, **k: json.dumps(g))
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    said = []
    monkeypatch.setattr(jv, "notify", lambda m, o="": said.append(m))
    jv._rec.clear()
    jv.process_command("hazme una infografía sobre el ciclo del agua para quinto")
    assert said and "Lista la infografía «El ciclo del agua»" in said[-1]
    assert glob_one(tmp_path, "Infografías/*.png") and glob_one(tmp_path, "Infografías/*.pdf")


def glob_one(base, pat):
    import glob
    return glob.glob(os.path.join(str(base), pat))


# ---------------------------------------------------------------- 8. herramientas
def test_herramientas(jv, monkeypatch, tmp_path):
    raw = ("Aquí está:\n```html\n<!DOCTYPE html><html><head><title>Préstamo de calculadoras</title>"
           "<script src=\"https://cdn.evil.com/x.js\"></script><link rel=stylesheet href=\"https://fonts.x/y.css\"></head>"
           "<body><img src=\"https://tracker.com/p.gif\"><script>localStorage.setItem('a','1')</script></body></html>\n```")
    page = MH.harden(MH.extract_html(raw))
    assert "Content-Security-Policy" in page and "connect-src 'none'" in page and "cdn.evil.com" not in page
    assert "fonts.x" not in page and "tracker.com" not in page and "localStorage" in page
    assert MH.title_of(page, "x") == "Préstamo de calculadoras"
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "ai_chat", lambda *a, **k: raw)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    opened = []
    monkeypatch.setattr(jv, "_open_doc", lambda p: opened.append(p))
    said = []
    monkeypatch.setattr(jv, "notify", lambda m, o="": said.append(m))
    jv._rec.clear()
    jv.process_command("créame una herramienta para llevar el préstamo de calculadoras del salón")
    assert said and "Préstamo de calculadoras" in said[-1] and opened[-1].endswith(".html")
    jv._rec.clear()
    jv.process_command("abre la herramienta de calculadoras")
    assert "Abrí «Préstamo de calculadoras»" in jv._rec.said()
