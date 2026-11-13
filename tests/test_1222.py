"""12.22: video en el HUD, búsqueda por modos, pulsar para hablar, reporte al abrir tarde y respaldo entre modelos."""
import datetime
import os
import time

import buscar

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------- video
def test_video_en_el_hud_y_microfono(jv, ask, monkeypatch):
    sent = []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: sent.append((ev, data)))
    monkeypatch.setitem(jv.settings, "video_mute_mic", True)
    jv.video_close(tell=False)
    assert not jv.video_mic_muted()
    _who, said = ask("pon el video https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5s")
    assert "en el HUD" in said and ("hud_video", {"id": "dQw4w9WgXcQ", "title": "", "mute": True}) in sent
    assert jv.video_mic_muted()                               # mientras suena, no escucha
    jv.video["ping"] = time.time() - 60
    assert not jv.video_mic_muted()                           # el HUD dejó de avisar: el micrófono vuelve solo
    jv.handle_video_ping()
    assert jv.video_mic_muted()
    monkeypatch.setitem(jv.settings, "video_mute_mic", False)
    assert not jv.video_mic_muted()
    assert "quité el video" in ask("quita el video")[1] and jv.video["id"] == "" and ("hud_video", {"id": ""}) in sent
    assert "No hay ningún video" in ask("cierra el video")[1]
    assert not jv._VID_ON.match("pon el videobeam en solo pc") and jv._VID_ON.match("muestrame un video sobre el ciclo del agua")


def test_busca_el_video(jv, monkeypatch):
    import nucleo.novedades as nv
    page = ('x"videoRenderer":{"videoId":"abcdefghijk","thumbnail":{},"title":{"runs":[{"text":"Fracciones equivalentes \\u00a1f\\u00e1cil!"}]}}'
            '"videoId":"zzzzzzzzzzz"')

    class R:
        def read(self):
            return page.encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    urls = []
    monkeypatch.setattr(nv.urllib.request, "urlopen", lambda req, timeout=None: urls.append(req.full_url) or R())
    assert jv.video_find("fracciones equivalentes") == ("abcdefghijk", "Fracciones equivalentes ¡fácil!")
    assert "search_query=fracciones+equivalentes" in urls[0]


# ---------------------------------------------------------------- búsqueda por modos
RES = [{"titulo": "Lenovo IdeaPad 3 $1.899.000", "url": "https://a.co/1", "fuente": "a.co", "resumen": "Desde $1.899.000"},
       {"titulo": "IdeaPad en oferta", "url": "https://b.co/2", "fuente": "b.co", "resumen": "$2.150.000"}]


def test_precios_y_comparar(jv, monkeypatch):
    asked, said = [], []
    monkeypatch.setattr(jv, "_web_results", lambda q: asked.append(q) or list(RES))
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, json_mode=False, max_tokens=None: asked.append(msgs[0]["content"]) or "Entre $1.899.000 y $2.150.000.")
    monkeypatch.setattr(jv, "reply", lambda text, origin="JARVIS": said.append((origin, text)))
    jv.price_search("portátil Lenovo IdeaPad")
    assert asked[0] == "precio portátil Lenovo IdeaPad Colombia" and "no inventes" in asked[1] and "$1.899.000" in asked[1]
    assert said[-1] == ("PRECIOS", "Entre $1.899.000 y $2.150.000.")
    asked.clear()
    jv.compare_search("iPhone 16", "Galaxy S25")
    assert asked[0] == "iPhone 16 vs Galaxy S25 comparación diferencias" and said[-1][0] == "COMPARAR"
    monkeypatch.setattr(jv, "ai_chat", lambda *a, **k: (_ for _ in ()).throw(jv.AIError("x")))
    jv.price_search("tablero acrílico")                        # sin IA: dice lo que encontró, no se queda mudo
    assert "Lenovo IdeaPad 3" in said[-1][1]
    assert "«A»" in buscar.compare_prompt("A", "B", RES)
    for no in ["compara las notas de 7a con 7b", "cuanto cuesta el dolar", "compara este pdf con el otro documento"]:
        assert jv._NOT_WEB.search(no), no
    assert jv._PRICE.match("busca el precio de un portatil lenovo ideapad").group(1) == "portatil lenovo ideapad"
    assert jv._raw_tail("Busca el precio de un portátil Lenovo IdeaPad.", 3) == "portátil Lenovo IdeaPad"


# ---------------------------------------------------------------- pulsar para hablar
def test_pulsar_para_hablar(jv, monkeypatch):
    monkeypatch.setattr(jv, "refresh_mode", lambda: None)
    monkeypatch.setattr(jv, "stop_speech", lambda log=True: None)
    monkeypatch.setitem(jv.settings, "mic_enabled", True)
    jv.video_close(tell=False)
    import nucleo
    nucleo.J.wake_until = 0.0
    assert jv.ptt_set(True)["ok"] and jv.ptt["on"]
    assert 25 < nucleo.J.wake_until - time.time() <= jv.PTT_HOLD        # mientras lo mantienes, lo que digas es una orden
    assert jv.ptt_set(False)["ok"] and not jv.ptt["on"]
    assert 0 < nucleo.J.wake_until - time.time() <= jv.PTT_GRACE        # al soltar se cierra (con un margen corto)
    monkeypatch.setitem(jv.settings, "mic_enabled", False)
    assert not jv.ptt_set(True)["ok"]
    nucleo.J.wake_until = 0.0
    html = open(os.path.join(ROOT, "templates", "hud.html"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "static", "js", "hud.js"), encoding="utf-8").read()
    assert 'id="btn-ptt"' in html and 'id="vid"' in html and 'socket.emit("ptt", { down: false })' in js and 'socket.on("hud_video"' in js


# ---------------------------------------------------------------- reporte al abrir tarde
def test_reporte_al_abrir_tarde(jv):
    D = datetime.datetime
    due = jv.brief_catchup_due
    assert due(D(2026, 11, 13, 8, 40), True, "07:30", (None, None))            # abriste a las 8:40: te lo da
    assert not due(D(2026, 11, 13, 7, 0), True, "07:30", (None, None))         # aún no es la hora: lo da el horario normal
    assert not due(D(2026, 11, 13, 14, 0), True, "07:30", (None, None))        # ya es de tarde
    assert not due(D(2026, 11, 13, 8, 40), True, "07:30", ("2026-11-13", None))  # hoy ya se dio
    assert not due(D(2026, 11, 13, 8, 40), True, "07:30", (None, "2026-11-13"))  # o ya te saludó
    assert due(D(2026, 11, 13, 8, 40), True, "07:30", ("2026-11-12", None))
    assert not due(D(2026, 11, 13, 8, 40), False, "07:30", (None, None)) and not due(D(2026, 11, 13, 8, 40), True, "", (None, None))


# ---------------------------------------------------------------- respaldo entre modelos
def test_modelo_saturado_prueba_con_otro(jv, monkeypatch):
    cfg = {"ai_provider": "gemini", "kind": "gemini", "model": "gemini-a", "label": "Gemini", "spec": {}}
    monkeypatch.setattr(jv, "_ensure_model", lambda c: c)
    monkeypatch.setattr(jv, "ai_list_models", lambda c: ["gemini-a", "gemini-b", "gemini-c"])
    monkeypatch.setattr(jv, "_recommend_model", lambda pid, models, exclude=(): next((m for m in models if m not in exclude), ""))
    monkeypatch.setitem(jv.settings, "gemini_model", "gemini-a")
    jv._alt.update(until=0.0, model="")
    jv._alt["for"] = ""
    calls = []

    def fn(c):
        calls.append(c["model"])
        if c["model"] in ("gemini-a", "gemini-b"):
            raise jv.AIError("overloaded", kind="server")
        return "hola"
    assert jv._with_fallback(cfg, fn) == "hola" and calls == ["gemini-a", "gemini-b", "gemini-c"]
    assert jv.settings["gemini_model"] == "gemini-a"                     # tu elección en Ajustes no cambia
    calls.clear()
    assert jv._with_fallback(cfg, fn) == "hola" and calls == ["gemini-c"]  # 5 minutos: directo al que respondió
    jv._alt["until"] = 0.0
    calls.clear()

    def bad(c):
        calls.append(c["model"])
        raise jv.AIError("clave", kind="key")
    try:
        jv._with_fallback(cfg, bad)
        assert False
    except jv.AIError as e:
        assert e.kind == "key" and calls == ["gemini-a"]                  # una clave mala no se arregla cambiando de modelo
