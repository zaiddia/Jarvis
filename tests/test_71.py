"""Pruebas de lo nuevo de la 7.1: copias de seguridad completas, tiempos de respuesta y caché de voz."""
import json
import os
import tempfile
import zipfile

import rapidez
import respaldo


# ----------------------------------------------------------------------------- copias de seguridad
def _datos(d):
    os.makedirs(os.path.join(d, "habilidades"))
    os.makedirs(os.path.join(d, "diario"))
    with open(os.path.join(d, "perfil.json"), "w", encoding="utf-8") as f:
        json.dump([{"clave": "hermana", "valor": "Ana"}], f)
    with open(os.path.join(d, "habilidades", "wikipedia.json"), "w", encoding="utf-8") as f:
        json.dump({"nombre": "Wikipedia"}, f)
    with open(os.path.join(d, "habilidades", "rota.json"), "w", encoding="utf-8") as f:
        f.write("{no es json")
    with open(os.path.join(d, "diario", "2026-10-29.jsonl"), "w", encoding="utf-8") as f:
        f.write('{"t": "orden", "texto": "hola"}\n')


def test_respaldo_incluye_perfil_habilidades_y_diario():
    src, dst, out = tempfile.mkdtemp(), tempfile.mkdtemp(), tempfile.mkdtemp()
    _datos(src)
    r = respaldo.create(src, out, {"tema": "oscuro"}, version="7.1")
    assert {"perfil", "habilidades", "diario"} <= set(r["parts"])
    assert r["counts"]["habilidades"] == 2 and r["counts"]["diario"] == 1
    info = respaldo.inspect(r["path"])
    assert {p["part"] for p in info["parts"]} >= {"perfil", "habilidades", "diario"}
    done = respaldo.restore(r["path"], dst, ["perfil", "habilidades", "diario"])
    assert set(done) == {"perfil", "habilidades", "diario"}
    with open(os.path.join(dst, "perfil.json"), encoding="utf-8") as f:
        assert json.load(f)[0]["valor"] == "Ana"
    assert os.path.isfile(os.path.join(dst, "habilidades", "wikipedia.json"))
    assert not os.path.exists(os.path.join(dst, "habilidades", "rota.json"))   # JSON dañado: no se restaura
    assert os.path.isfile(os.path.join(dst, "diario", "2026-10-29.jsonl"))


def test_respaldo_sin_carpetas_sigue_funcionando():
    src, out = tempfile.mkdtemp(), tempfile.mkdtemp()
    r = respaldo.create(src, out, {})
    assert r["parts"] == ["ajustes"]


def test_respaldo_rechaza_rutas_peligrosas():
    for mal in ("habilidades/../config.json", "habilidades/a/b.json", "habilidades/.oculto.json",
                "habilidades/x.exe", "otra/x.json", "habilidades/C:x.json", "habilidades/"):
        assert respaldo._safe_member(mal, "habilidades", ".json") is None
    assert respaldo._safe_member("habilidades/ok.json", "habilidades", ".json") == "ok.json"
    # una copia manipulada no escribe fuera de la carpeta
    src, out, dst = tempfile.mkdtemp(), tempfile.mkdtemp(), tempfile.mkdtemp()
    p = respaldo.create(src, out, {})["path"]
    with zipfile.ZipFile(p, "a") as z:
        z.writestr("habilidades/../../fuera.json", "{}")
    respaldo.restore(p, dst, ["habilidades"])
    assert not os.path.exists(os.path.join(os.path.dirname(dst), "fuera.json"))


# ----------------------------------------------------------------------------- tiempos de respuesta
def test_rapidez_mide_etapas():
    rapidez.hist.clear()
    rapidez.begin("voz", now=100.0)
    rapidez.mark("transcripcion", now=100.5)
    rapidez.mark("orden", now=100.6)
    rapidez.mark("respuesta", now=102.6)
    rapidez.mark("respuesta", now=105.0)            # solo cuenta la primera vez
    rapidez.mark("voz_lista", now=103.1)
    r = rapidez.mark("sonando", now=103.2)
    assert r["total"] == 3.2 and r["pensar"] == 2.0 and r["transcribir"] == 0.5
    assert "3.2 s" in rapidez.line(r)
    assert rapidez.mark("orden") is None            # sin turno en curso no hace nada
    s = rapidez.summary()
    assert s["turnos"] == 1 and s["lenta"] == "pensar"


def test_rapidez_sin_voz_y_consejos():
    rapidez.hist.clear()
    assert "Aún no" in rapidez.spoken(rapidez.summary())
    for _ in range(3):
        rapidez.begin("texto", now=10.0)
        rapidez.mark("orden", now=10.0)
        rapidez.mark("respuesta", now=16.0)
        assert rapidez.finish_without_voice()["total"] == 6.0
    txt = rapidez.spoken(rapidez.summary())
    assert "6.0 segundos" in txt and "pensar" in txt and "más rápido" in txt


# ----------------------------------------------------------------------------- caché de voz
def test_cache_de_voz(jv):
    jv.VOICE_CACHE = tempfile.mkdtemp()
    item = {"voice": None, "gemini": {}}
    assert jv._voice_cache_get("edge", item, "Hecho.", "+0%", "+0%", "+0Hz") is None
    src = os.path.join(tempfile.mkdtemp(), "a.mp3")
    with open(src, "wb") as f:
        f.write(b"ID3audio")
    jv._voice_cache_put("edge", item, "Hecho.", "+0%", "+0%", "+0Hz", src)
    hit = jv._voice_cache_get("edge", item, "Hecho.", "+0%", "+0%", "+0Hz")
    assert hit and open(hit, "rb").read() == b"ID3audio"
    # otra voz, otra velocidad o una frase larga no usan la caché
    assert jv._voice_cache_get("edge", {"voice": "es-MX-JorgeNeural", "gemini": {}}, "Hecho.", "+0%", "+0%", "+0Hz") is None
    assert jv._voice_cache_get("edge", item, "Hecho.", "+20%", "+0%", "+0Hz") is None
    largo = "x" * (jv.VOICE_CACHE_MAX_CHARS + 1)
    jv._voice_cache_put("edge", item, largo, "+0%", "+0%", "+0Hz", src)
    assert jv._voice_cache_get("edge", item, largo, "+0%", "+0%", "+0Hz") is None


# ----------------------------------------------------------------------------- bienvenida
def test_bienvenida(jv):
    abiertas = []
    jv.open_welcome_window = lambda: abiertas.append(1)
    jv.close_welcome_window = lambda: None
    s = jv.welcome_status()
    assert s["try"] and "gemini" in s["providers"] and "openai" not in s["providers"]
    assert all(k in s for k in ("name", "mics", "voices", "ai_ok", "themes"))
    old = jv.settings["onboarding_done"]
    jv.settings["onboarding_done"] = False
    jv.welcome_at_start()
    assert abiertas
    jv.handle_welcome_done({"keep": True})
    assert jv.settings["onboarding_done"] is True
    jv.settings["onboarding_done"] = old
    client = jv.app.test_client()
    html = client.get("/bienvenida").get_data(as_text=True)
    assert "welcome_status" in html and "welcome_done" in html


# ----------------------------------------------------------------------------- estructura (nucleo/)
def test_las_partes_encajan(jv):
    """Cada J.<nombre> que usan las partes de nucleo/ existe en jarvis, y cada parte exporta todo lo suyo."""
    import glob
    import re
    import nucleo
    assert nucleo.J is jv
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    faltan = []
    for f in glob.glob(os.path.join(raiz, "nucleo", "*.py")):
        src = open(f, encoding="utf-8").read()
        faltan += [(os.path.basename(f), n) for n in set(re.findall(r"\bJ\.(\w+)", src)) if not hasattr(jv, n)]
        if not f.endswith("__init__.py"):
            mod = __import__("nucleo." + os.path.basename(f)[:-3], fromlist=["__all__"])
            for n in mod.__all__:
                assert hasattr(jv, n), (f, n)
    assert not faltan, faltan
