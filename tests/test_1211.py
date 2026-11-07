"""Pruebas de la 12.11: Modo Código, dólar/euro/cripto, huella SHA-256 de la IA local y el contexto del navegador y del Explorador."""
import json
import os

import pytest

import codigo
import divisas
import motorlocal
import skills


# ============================================================================ CONTEXTO: NAVEGADOR Y EXPLORADOR
@pytest.fixture
def browser(monkeypatch):
    launched = []
    monkeypatch.setattr(skills, "IS_WIN", True)
    monkeypatch.setattr(skills, "browser_exe", lambda proc: {"brave.exe": r"C:\Brave\brave.exe", "chrome.exe": r"C:\Chrome\chrome.exe"}.get(proc, ""))
    monkeypatch.setattr(skills.subprocess, "Popen", lambda args, **k: launched.append(args))
    monkeypatch.setattr(skills.webbrowser, "open", lambda u, *a, **k: launched.append(["predeterminado", u]))
    monkeypatch.setattr(skills, "_custom_commands", lambda: {})
    monkeypatch.setattr(skills, "_apps", {})
    skills._apps_ready.set()
    skills.context.update(browser="", browser_t=0.0, explorer=0, explorer_t=0.0)
    yield launched
    skills.context.update(browser="", browser_t=0.0, explorer=0, explorer_t=0.0)


def test_pagina_en_el_navegador_que_pides(browser):
    assert skills.open_app("youtube en el navegador brave") == "Abriendo youtube en Brave."
    assert browser[-1] == [r"C:\Brave\brave.exe", "https://www.youtube.com"]
    assert skills.open_app("gmail en chrome").endswith("en Chrome.") and browser[-1][1] == "https://mail.google.com"
    skills.open_app("colegio san jose en brave")
    assert "google.com/search?q=colegio+san+jose" in browser[-1][1]
    with pytest.raises(skills.SkillError):
        skills.open_app("youtube en firefox")                                  # no está instalado


def test_sigue_el_contexto_del_navegador(browser):
    skills.open_app("youtube")
    assert browser[-1][0] == "predeterminado"                                  # sin contexto: el predeterminado
    skills.note_browser("brave.exe")                                           # abriste o usaste Brave
    assert skills.open_app("youtube") == "Abriendo youtube en Brave." and browser[-1][0] == r"C:\Brave\brave.exe"
    skills.web_search("recetas de arepas")
    assert browser[-1][0] == r"C:\Brave\brave.exe" and "arepas" in browser[-1][1]
    skills.web_search("noticias en chrome")
    assert browser[-1] == [r"C:\Chrome\chrome.exe", "https://www.google.com/search?q=noticias"]
    assert skills.split_browser("recetas en el navegador brave") == ("recetas", "brave.exe")
    skills.context["browser_t"] -= 3 * 3600                                    # hace horas: ya no cuenta
    assert skills.context_browser() == ""


def test_explorador_en_la_misma_ventana(browser, monkeypatch):
    moved, launched = [], []
    monkeypatch.setattr(skills, "context_explorer", lambda: 77)
    monkeypatch.setattr(skills, "explorer_navigate", lambda target, h: moved.append((target, h)) or True)
    monkeypatch.setattr(skills, "_launch", lambda target: launched.append(target))
    assert "Explorador que tenías abierto" in skills.open_app("descargas") and moved == [("shell:Downloads", 77)] and not launched
    monkeypatch.setattr(skills, "context_explorer", lambda: 0)
    skills.open_app("la carpeta documentos")
    assert launched == ["shell:Personal"]


def test_ve_a_documentos(jv, monkeypatch):
    moved = []
    monkeypatch.setattr(jv, "IS_WIN", True)
    monkeypatch.setattr(skills, "context_explorer", lambda: 9)
    monkeypatch.setattr(skills, "explorer_navigate", lambda target, h: moved.append((target, h)) or True)
    jv._rec.clear()
    jv.process_command("ve a documentos")
    assert moved == [("shell:Personal", 9)] and "documentos" in jv._rec.said()


# ============================================================================ DÓLAR, EURO Y CRIPTO
def test_divisas_logica():
    assert divisas.parse_conversion("¿cuánto son 50 dólares en pesos?") == (50.0, "USD", "COP")
    assert divisas.parse_conversion("convierte 200 mil pesos a dólares") == (200000.0, "COP", "USD")
    assert divisas.asks_rate("¿a cómo está el dólar?") == "USD" and divisas.asks_rate("la trm") == "USD" and divisas.asks_rate("precio del bitcoin") == "BTC"
    assert divisas.asks_rate("¿cómo está el clima?") == "" and divisas.asks_rate("a como esta el peso") == ""
    assert divisas.convert(50, "USD", "COP", 4000) == 200000 and round(divisas.convert(100, "EUR", "COP", 4000, {"EUR": 0.8})) == 500000
    assert divisas.fmt(4123.45, "COP") == "$4.123 pesos" and divisas.fmt(12.3456, "USD") == "12,35 dólares"
    assert divisas.foreign_expense("gasté 50 dólares en un curso") == (50.0, "USD", "un curso") and divisas.foreign_expense("gasté 20 mil en pan") is None
    assert divisas.parse_trm([{"valor": "4123.45", "vigenciadesde": "2026-11-07T00:00", "vigenciahasta": "2026-11-09T00:00"}]) == (4123.45, "2026-11-07", "2026-11-09")


def test_dolar_por_voz(jv, monkeypatch, tmp_path):
    import nucleo.dinero as dn
    import vidadiaria as vd
    vd.configure(str(tmp_path))
    pages = {divisas.TRM_URL: [{"valor": "4000", "vigenciadesde": "2026-11-07", "vigenciahasta": "2026-11-09T00:00"}],
             divisas.FX_URL: {"result": "success", "rates": {"COP": 4010, "EUR": 0.8}},
             divisas.CRYPTO_URL: {"bitcoin": {"usd": 70000, "cop": 280000000}}}
    monkeypatch.setattr(jv, "_get_text", lambda url, timeout=12: json.dumps(pages[url]))
    monkeypatch.setattr(jv, "is_offline", lambda: False)
    dn._fx_cache.update(t=0.0, trm=None, ct=0.0)
    for text, want in (("¿A cómo está el dólar?", "$4.000 pesos"), ("¿cuánto son 50 dólares en pesos?", "$200.000 pesos"),
                       ("precio del euro", "$5.000 pesos"), ("¿cuánto vale el bitcoin?", "$280.000.000 pesos")):
        jv._rec.clear()
        jv.process_command(text)
        assert want in jv._rec.said(), (text, jv._rec.said())
    jv.process_command("gasté 50 dólares en un curso de Python")
    assert vd.data["gastos"][-1]["monto"] == 200000 and "US$50" in vd.data["gastos"][-1]["concepto"]
    vd.configure(str(tmp_path / "limpio"))


# ============================================================================ MODO CÓDIGO
def test_codigo_logica():
    py = "def suma(a, b)\n    return a + b\nprint(suma(2, 3))"
    assert codigo.lang_of("", py) == "Python" and codigo.lang_of("x.ino") == "Arduino"
    assert codigo.syntax_check(py, "Python") == [{"linea": 1, "problema": "falta «:» al final de la línea"}]
    assert codigo.syntax_check("def f():\n    return 1\n", "Python") == []
    assert codigo.syntax_check("function f(){ console.log(1);", "JavaScript")[0]["problema"].startswith("falta una llave de cierre")
    assert "<div>" in codigo.syntax_check("<html><body><div>hola</body></html>", "HTML")[0]["problema"]
    r = codigo.review_validate({"resumen": "Suma dos números.", "errores": [{"linea": 3, "problema": "x"}], "mejoras": ["usa nombres claros"]},
                               [{"linea": 1, "problema": "falta «:»"}])
    assert [e["linea"] for e in r["errores"]] == [1, 3]                         # lo del analizador nunca se pierde
    assert "línea 1: falta «:»" in codigo.spoken(r, "suma.py", "Python", 3)
    assert codigo.looks_like_code(py) and not codigo.looks_like_code("hola profe, ¿cómo está?")


def test_revisa_este_codigo(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    told = []
    monkeypatch.setattr(jv, "notify", lambda t, o="": told.append(t))
    seen = []

    def ai(msgs, **k):
        seen.append(msgs[0]["content"])
        return json.dumps({"resumen": "Suma dos números y muestra el resultado.", "errores": [{"linea": 1, "problema": "falta «:»", "arreglo": "def suma(a, b):"}],
                           "mejoras": ["agrega una docstring"], "pasos": ["define suma", "la usa"], "corregido": "def suma(a, b):\n    return a + b"})
    monkeypatch.setattr(jv, "ai_chat", ai)
    jv._rec.clear()
    jv.process_command("revisa este código:\ndef suma(a, b)\n    return a + b\nprint(suma(2, 3))")
    assert "1| def suma(a, b)" in seen[0] and "línea 1: falta «:»" in seen[0]          # va numerado y con lo del analizador
    assert "Errores: línea 1: falta «:»" in told[-1]
    docs = os.listdir(tmp_path / "Código")
    assert len(docs) == 1 and docs[0].endswith(".docx")
    from docx import Document
    text = "\n".join(p.text for p in Document(str(tmp_path / "Código" / docs[0])).paragraphs)
    assert "Código corregido" in text and "def suma(a, b):" in text
    # sin código ni archivo: pide que lo pegues
    jv._rec.clear()
    jv.process_command("explícame este código")
    assert "Pega el código" in jv._rec.said()


def test_codigo_sin_ia_solo_sintaxis(jv, monkeypatch):
    monkeypatch.setattr(jv, "ai_chat", lambda *a, **k: (_ for _ in ()).throw(jv.AIError("sin IA")))
    msg, path = jv.code_review("for i in range(3)\n    print(i)")
    assert "Sin IA" in msg and "línea 1" in msg and path == ""


def test_tarjeta_de_un_archivo_de_codigo(jv):
    import nucleo.adjuntar as aj
    card = aj.card_of([{"id": "1", "nombre": "juego.py", "tipo": "texto", "ruta": "x", "ext": ".py", "t": 0, "paginas": 0, "bytes": 10}])
    assert [a["a"] for a in card["acciones"][:2]] == ["codigo", "codigo_ej"]
    card = aj.card_of([{"id": "2", "nombre": "notas.txt", "tipo": "texto", "ruta": "x", "ext": ".txt", "t": 0, "paginas": 0, "bytes": 10}])
    assert "codigo" not in [a["a"] for a in card["acciones"]]


# ============================================================================ HUELLA SHA-256 DE LA IA LOCAL
def test_huella_de_la_ia_local(jv, tmp_path):
    rel = [{"assets": [{"name": "llama-b1-bin-win-cpu-x64.zip", "digest": "sha256:ABC123"}]}]
    assert motorlocal.asset_sha256(rel, "llama-b1-bin-win-cpu-x64.zip") == "abc123" and motorlocal.asset_sha256(rel, "otro") == ""
    assert motorlocal.hf_sha256([{"rfilename": "m.gguf", "lfs": {"sha256": "FF"}}], "m.gguf") == "ff"
    assert motorlocal.hf_api("a/b").endswith("?blobs=true")
    f = tmp_path / "motor.zip"
    f.write_bytes(b"hola")
    good = motorlocal.sha256_file(str(f))
    assert jv.verify_download(str(f), good, "el motor") is True
    with pytest.raises(ValueError):
        jv.verify_download(str(f), "0" * 64, "el motor")
    assert not f.exists()                                                      # alterado: se borra y no se usa
    f.write_bytes(b"x")
    assert jv.verify_download(str(f), "", "el motor") is False and f.exists()   # sin huella publicada: se avisa en el registro
