"""Pruebas de la 12.69: ascenso, pictogramas, PhET, graficadora, Parakeet, Fomag y modelo en vivo retirado."""
import json
import time

import adjuntos
import ascenso as AS
import graficadora as GF
import phet as PH
import pictos as PC
import pytest
import vidapractica as VP

Q = {"competencia": "praxis", "caso": "En un grado séptimo varios estudiantes no entienden las fracciones después de la explicación.",
     "pregunta": "¿Qué es lo más adecuado?", "opciones": {"A": "Repetir la misma explicación más despacio",
                                                         "B": "Usar material concreto y preguntas para diagnosticar el error",
                                                         "C": "Poner un taller como tarea", "D": "Seguir con el siguiente tema"},
     "correcta": "B", "explicacion": "Diagnosticar y usar representaciones concretas atiende la causa del error."}


# ---------------------------------------------------------------- ascenso (puro)
def test_ascenso_puro():
    qs = AS.clean({"preguntas": [Q, dict(Q, competencia="ambiente"), {"caso": "x", "opciones": {"A": "1"}}]}, seed=4)
    assert len(qs) == 2 and qs[0]["opciones"][qs[0]["correcta"]].startswith("Usar material concreto")
    assert AS.answer_letter("la b") == "B" and AS.answer_letter("opcion d") == "D" and AS.answer_letter("bueno") == ""
    good, n, by, weak = AS.summary([{"competencia": "praxis", "ok": True}, {"competencia": "ambiente", "ok": False}])
    assert (good, n, weak) == (1, 2, "ambiente")
    y, z, m = AS.parse_points("8 anos de servicio zona urbana de cali ningun ascenso")
    assert (y, z[1], m) == (8, 12, 0)
    txt = AS.needed_text(y, z, m)
    assert "16 puntos" in txt and "48 de 55" in txt and "32 de los 45" in txt
    assert "tres años" in AS.needed_text(2, z, m)
    assert AS.zone_points("rural de dificil acceso")[1] == 15 and AS.moves_points(3) == 9


def test_simulacro_por_voz(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps({"preguntas": [Q, dict(Q, competencia="ambiente")]}))
    monkeypatch.setitem(jv.asc_state, "on", False)
    jv._rec.clear()
    jv.process_command("hagamos un simulacro de la prueba de ascenso")
    assert jv.asc_state["on"] and "Pregunta 1 de 2" in jv._rec.said()
    right = jv.asc_state["qs"][0]["correcta"]
    jv._rec.clear()
    jv.process_command(f"la {right.lower()}")
    assert "¡Correcto!" in jv._rec.said() and "Pregunta 2 de 2" in jv._rec.said()
    wrong = next(k for k in "ABCD" if k != jv.asc_state["qs"][1]["correcta"])
    jv._rec.clear()
    jv.process_command(wrong.lower())
    assert "No: la mejor" in jv._rec.said() and "acertaste 1 de 2" in jv._rec.said() and not jv.asc_state["on"]
    jv._rec.clear()
    jv.process_command("¿cómo voy en el simulacro de ascenso?")
    assert "1 simulacro" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("calcula mis puntos de ascenso: 12 años, zona rural, un ascenso")
    assert "18 puntos" in jv._rec.said()


# ---------------------------------------------------------------- pictogramas
class _R:
    def __init__(self, b):
        self.b = b

    def read(self):
        return self.b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _png():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


def test_pictogramas(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "docs"))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    calls = []

    def http(method, url, headers=None, payload=None, timeout=0, stream=False):
        calls.append(url)
        if "bestsearch" in url:
            if "volar" in url:
                raise jv.AIError("no", code=404)
            return [{"_id": 2350, "keywords": []}]
        return _R(_png())
    monkeypatch.setattr(jv, "_http", http)
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps({"titulo": "Al llegar al salón", "pasos": [
        {"texto": "Saluda", "claves": ["saludar"]}, {"texto": "Saca el cuaderno", "claves": ["cuaderno"]},
        {"texto": "Vuela alto", "claves": ["volar"]}]}))
    jv._rec.clear()
    jv.process_command("pasa a pictogramas: saluda, saca el cuaderno y vuela alto")
    files = list((tmp_path / "docs" / "Pictogramas").iterdir())
    assert len(files) == 1 and "1 no tienen dibujo" in jv._rec.said()
    import docx
    d = docx.Document(str(files[0]))
    assert "ARASAAC" in d.paragraphs[-1].text and len(d.inline_shapes) == 2
    n = len(calls)
    jv.picto_for("cuaderno")
    jv.picto_for("volar")
    assert len(calls) == n                                                    # caché (también de los que no hay)
    assert PC.split_plain("Lávate las manos. Siéntate")["pasos"][1]["texto"] == "Siéntate"


# ---------------------------------------------------------------- PhET
def test_phet(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    assert PH.find("fracciones") == "fractions-intro" and PH.find("ley de Ohm") == "ohms-law" and PH.find("dragones") == ""
    assert PH.url("pendulum-lab") == "https://phet.colorado.edu/sims/html/pendulum-lab/latest/pendulum-lab_es.html"
    opened = []
    monkeypatch.setattr(jv, "open_window", lambda path, title: opened.append(path))
    jv._rec.clear()
    jv.process_command("muéstrales la simulación de fracciones")
    assert opened == ["/phet/fractions-intro"] and "Fracciones" in jv._rec.said()
    page = b"<!DOCTYPE html><html><head><title>PhET</title></head><body>" + b"x" * 6000 + b"</body></html>"
    asked = []

    def http(method, url, headers=None, payload=None, timeout=0, stream=False):
        asked.append(url)
        if url.endswith("_es.html") and "ohms" in url:
            raise jv.AIError("no", code=404)
        return _R(page)
    monkeypatch.setattr(jv, "_http", http)
    assert jv.phet_download("ohms-law").endswith("ohms-law.html") and asked[-1].endswith("_en.html")  # sin traducción: en inglés
    c = jv.app.test_client().get("/phet/ohms-law")
    assert c.status_code == 200 and b"PhET" in c.data
    assert jv.app.test_client().get("/phet/no-existe").status_code == 404
    monkeypatch.setattr(jv, "is_offline", lambda: False)
    monkeypatch.setattr(jv, "phet_download", lambda s: "")
    r = jv.app.test_client().get("/phet/pendulum-lab")
    assert r.status_code == 302 and "pendulum-lab_es.html" in r.headers["Location"]
    jv._rec.clear()
    jv.process_command("qué simulaciones de física hay")
    assert "Ley de Ohm" in jv._rec.said()


# ---------------------------------------------------------------- graficadora
def test_graficadora(jv, monkeypatch):
    assert GF.canonical(GF.from_speech("y = a x² + b x + c")) == ("a*x^2+b*x+c", ["a", "b", "c"])
    assert GF.canonical(GF.from_speech("y igual a x al cuadrado menos 4"))[0] == "x^2-4"
    e, _p = GF.canonical(GF.from_speech("2(x-1)(x+1)"))
    assert GF.evaluate(e, 3) == 16
    assert GF.canonical(GF.from_speech("raíz de x más seno de x"))[0] == "sqrt(x)+sin(x)"
    for bad in ("x + ", "(x", "x)", "z x", "import os", "x**"):
        with pytest.raises(ValueError):
            GF.canonical(GF.from_speech(bad))
    assert GF.values_in("con a = 2 y b = -1,5") == {"a": 2.0, "b": -1.5}
    opened = []
    monkeypatch.setattr(jv, "open_window", lambda path, title: opened.append(path))
    jv._rec.clear()
    jv.process_command("grafica y = a x² + b x + c con a = 2")
    assert opened and "f=a%2Ax%5E2%2Bb%2Ax%2Bc" in opened[0] and "a=2.0" in opened[0] and "deslizadores" in jv._rec.said()
    page = jv.app.test_client().get(opened[0])
    assert page.status_code == 200 and b"a*x^2+b*x+c" in page.data
    bad = jv.app.test_client().get("/graficadora?f=alert(1)")
    assert b"alert" not in bad.data.split(b"const INIT")[1][:80]


# ---------------------------------------------------------------- Parakeet, Fomag y modelo en vivo
def test_parakeet_y_ajustes(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "stt_refine", "auto")
    monkeypatch.setattr(jv, "_gemini_for_stt", lambda: None)
    monkeypatch.setattr(jv, "parakeet_ready", lambda: True)
    assert jv.stt_refine_mode() == "parakeet"
    monkeypatch.setattr(jv, "_parakeet_transcribe", lambda raw: "abre la pizarra")
    assert jv.refine_speech(b"\0" * 32000, "abre la pisarra") == "abre la pizarra"
    assert jv._validate("stt_refine", "parakeet") == "parakeet"
    monkeypatch.setattr(jv, "parakeet_ready", lambda: False)
    jv._rec.clear()
    jv.process_command("usa Parakeet para entenderme")
    assert "instala el reconocimiento Parakeet" in jv._rec.said()


def test_fomag_y_modelo_en_vivo(jv, monkeypatch):
    assert VP.sector_of("el Fomag no me da la cita con el especialista")[0] == "magisterio"
    assert "Supersalud" in VP.sector_of("fomag")[1] and "régimen especial" in VP.sector_of("fomag")[2]
    assert "FOMAG" in VP.letter_prompt("peticion", "Fomag", "no me entregan los medicamentos")
    assert "FOMAG" not in VP.letter_prompt("peticion", "EPS Sura", "no me autorizan")
    assert "gemini-3.1-flash-live-preview" not in jv.envivo.MODELS
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.settings, "live_model", "gemini-3.1-flash-live-preview")
    assert jv.a69_migrate() and jv.settings["live_model"] == "gemini-3.8-live"
    assert jv.a69_migrate() is False
