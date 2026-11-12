"""12.20: cambio rápido a la IA local, IA local más ágil y habilidades al instante."""
import datetime
import random
import time

import instante


# ---------------------------------------------------------------- red
def test_sondas_en_paralelo_no_suman_tiempos(jv, monkeypatch):
    import nucleo.ia as ia

    def slow(addr, timeout=None):
        time.sleep(0.4)
        raise OSError("sin red")
    monkeypatch.setattr(ia.socket, "create_connection", slow)
    t0 = time.time()
    assert jv._tcp_any(1.0) is False
    assert time.time() - t0 < 0.9                       # 3 sondas de 0,4 s en paralelo ≈ 0,4 s (antes: una tras otra)

    class Ok:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(ia.socket, "create_connection", lambda addr, timeout=None: Ok())
    assert jv._tcp_any(1.0) is True


def test_comprobacion_previa_cambia_ya_a_la_ia_local(jv, monkeypatch):
    for k, v in {"offline": False, "fails": 0, "ok_at": 0.0, "watch": True, "proxy_only": False, "local_model": "qwen3:4b", "local_at": time.time()}.items():
        monkeypatch.setitem(jv.net, k, v)
    monkeypatch.setitem(jv.settings, "offline_auto", True)
    monkeypatch.setattr(jv, "local_warm", lambda reason="": None)
    monkeypatch.setattr(jv, "check_ai", lambda *a, **k: None)
    monkeypatch.setattr(jv, "_tcp_any", lambda timeout=1.5: True)
    assert jv.net_preflight() is False and jv.net["ok_at"] > 0          # hay internet: sigue en la nube
    calls = []
    monkeypatch.setattr(jv, "_tcp_any", lambda timeout=1.5: calls.append(timeout) or False)
    assert jv.net_preflight() is False and not calls                   # recién comprobado: no gasta ni un milisegundo
    jv.net["ok_at"] = 0.0
    monkeypatch.setattr(jv, "_internet_ok", lambda: False)
    assert jv.net_preflight() is True and jv.net["offline"]            # se cayó: sin esperar a que la nube falle
    jv.net.update(offline=False, fails=0, ok_at=0.0, watch=False)
    assert jv.net_preflight() is False                                 # sin vigilancia de red (pruebas): no toca nada


def test_primer_fallo_precarga_la_ia_local(jv, monkeypatch):
    warmed = []
    for k, v in {"offline": False, "fails": 0, "local_model": "x", "local_at": time.time()}.items():
        monkeypatch.setitem(jv.net, k, v)
    monkeypatch.setattr(jv, "local_warm", lambda reason="": warmed.append(reason))
    monkeypatch.setattr(jv, "check_ai", lambda *a, **k: None)
    jv._net_set(False)
    assert warmed and not jv.net["offline"]             # al primer fallo se adelanta, sin declarar aún «sin internet»
    jv._net_set(False)
    assert jv.net["offline"] and len(warmed) == 2
    assert jv._keep_alive() == "4h"                     # sin internet no se descarga de la memoria
    jv.net.update(offline=False, fails=0)
    assert jv._keep_alive() == "30m"


# ---------------------------------------------------------------- IA local sin «pensar»
def test_ollama_sin_pensar_y_respaldo(jv, monkeypatch):
    seen = []

    class Cli:
        def __init__(self, host=None, timeout=None):
            pass

        def chat(self, **k):
            seen.append(k)
            if k.get("think") is False and k["model"] == "llama3.2":
                raise RuntimeError('"llama3.2" does not support thinking')
            return {"message": {"content": "ok"}}

    class Lib:
        Client = Cli
    monkeypatch.setattr(jv, "ollama", Lib())
    monkeypatch.setitem(jv._think, "ok", True)
    monkeypatch.setitem(jv._think, "no", set())
    cfg = {"ollama_host": "http://127.0.0.1:11434"}
    jv._ollama_chat(cfg, model="qwen3:4b", messages=[])
    assert seen[-1]["think"] is False                   # qwen3: pensamiento apagado
    jv._ollama_chat(cfg, model="llama3.2", messages=[])
    assert "think" not in seen[-1] and "llama3.2" in jv._think["no"]
    n = len(seen)
    jv._ollama_chat(cfg, model="llama3.2", messages=[])
    assert len(seen) == n + 1                           # ya lo sabe: no vuelve a intentarlo dos veces


def test_no_se_dice_lo_que_piensa(jv):
    assert "".join(jv._skip_think(iter(["<th", "ink>voy a pen", "sar</think>\n\nHola, ", "profe."]))) == "Hola, profe."
    assert "".join(jv._skip_think(iter(["Hola, ", "profe."]))) == "Hola, profe."
    assert "".join(jv._skip_think(iter(["<", "b>negrita"]))) == "<b>negrita"


def test_preguntas_a_la_ia_local_con_contexto_corto(jv, monkeypatch):
    got = {}
    monkeypatch.setattr(jv, "_ai_cfg", lambda override=None: {"kind": "ollama", "model": "qwen3:4b", "ollama_host": "x", "spec": {}, "label": "local"})
    monkeypatch.setattr(jv, "ollama", object())
    monkeypatch.setattr(jv, "_notes_ctx", lambda: " NOTAS " + "x" * 5000)
    monkeypatch.setattr(jv, "_stream_chunks", lambda cfg, msgs: got.update(msgs=msgs) or iter(["Listo."]))
    monkeypatch.setattr(jv, "save_memory", lambda: None)
    monkeypatch.setattr(jv, "chat_history", [{"role": "user", "content": f"p{i}"} for i in range(30)])
    import nucleo.ia as ia
    ia.answer_question_streaming("¿qué es un número primo?")       # la de verdad (la de pruebas está sustituida)
    sysmsg = got["msgs"][0]["content"]
    assert sysmsg.startswith(jv.system_static())        # mismo comienzo fijo: la IA local no lo relee
    assert len(sysmsg) < len(jv.system_static()) + 1400 and len(got["msgs"]) <= 8


# ---------------------------------------------------------------- al instante
HOY = datetime.date(2026, 11, 11)
UTC = datetime.datetime(2026, 11, 12, 3, 16, tzinfo=datetime.timezone.utc)


def _a(q, rng=None):
    return instante.answer(instante.norm(q), q, HOY, UTC, rng or random.Random(3))


def test_hora_mundial():
    assert _a("¿qué hora es en Tokio?") == ("HORA", "En Tokio son las 12:16 de la tarde de mañana.") or "Tokio son las 12:16" in _a("¿qué hora es en Tokio?")[1]
    assert "Nueva York son las 10:16 de la noche" in _a("qué hora es en nueva york")[1]
    assert _a("qué hora es") is None and _a("qué hora es en el salón") is None


def test_fechas():
    assert "faltan 44 días" in _a("¿cuántos días faltan para navidad?")[1]
    assert _a("qué día cae el 20 de diciembre")[1] == "El 20 de diciembre de 2026 cae domingo."
    assert "fue sábado" in _a("qué día fue el 7 de agosto de 1819")[1]
    assert _a("qué edad tengo si nací el 3 de mayo de 1985")[1].startswith("Son 41 años.")
    assert "73 días" in _a("cuántos días hay entre el 1 de enero y el 15 de marzo")[1]
    assert "26 de diciembre" in _a("qué fecha es en 45 días")[1]
    assert instante.until_hour(instante.norm("¿cuánto falta para las 5 de la tarde?"), datetime.datetime(2026, 11, 11, 14, 30)) == \
        "Para las 5:00 de la tarde faltan 2 horas y 30 minutos."


def test_unidades():
    assert _a("convierte 5 millas a kilómetros")[1] == "5 millas son 8,05 kilómetros."
    assert _a("convierte 2,5 millas a km")[1] == "2,5 millas son 4,02 kilómetros."
    assert _a("cuánto son 80 grados fahrenheit en celsius")[1] == "80 grados Fahrenheit son 26,67 grados Celsius."
    assert _a("cuántos gramos hay en 2 libras")[1] == "2 libras son 907,2 gramos."
    assert _a("pasa 100 km/h a millas por hora")[1] == "100 kilómetros por hora son 62,14 millas por hora."
    assert _a("convierte 3 litros a kilómetros") is None                # magnitudes distintas: no inventa
    for no in ["convierte este pdf a audio", "pasa las notas de 7A a excel", "cuánto es 20 dólares en pesos", "pasa a la siguiente diapositiva"]:
        assert _a(no) is None, no


def test_azar_deletreo_y_banco():
    assert _a("tira un dado")[0] == "AZAR" and "suman" in _a("lanza dos dados")[1]
    n = int(_a("dime un número al azar entre 1 y 50")[1].split()[1].strip("."))
    assert 1 <= n <= 50
    assert _a("escoge entre pizza, sushi o tacos")[1].split(": ")[1].strip(".") in ("pizza", "sushi", "tacos")
    assert _a("deletrea murciélago")[1] == "murciélago: M, U, R, C, I, É, L, A, G, O."
    assert _a("cuéntame un chiste")[0] == "CHISTE" and _a("dime un dato curioso")[0] == "DATO CURIOSO" and _a("dame una frase motivadora")[0] == "FRASE"
    assert _a("cuéntame un chiste de programadores") is None            # con tema: lo inventa la IA
    assert _a("elige el mejor trabajo de 7A") is None


def test_contrasena_no_se_dice_ni_se_guarda(jv, ask, monkeypatch):
    pw, n = instante.password(instante.norm("genera una contraseña segura de 20 caracteres"))
    assert n == 20 and len(pw) == 20 and any(c.isdigit() for c in pw) and any(c.isupper() for c in pw) and not set(pw) & set("lIO0o1")
    sent = []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: sent.append((ev, data)))
    who, said = ask("genera una contraseña segura")
    shown = [d["text"] for e, d in sent if e == "chat" and d.get("source") == "CONTRASEÑA" and "`" in d["text"]]
    assert who == "CONTRASEÑA", who
    assert shown, sent
    secret = shown[0].split("`")[1]
    assert len(secret) == 16 and secret not in said and all(secret not in line for line in jv.log_buffer)


# ---------------------------------------------------------------- con red o IA
def test_velocidad_y_traductor(jv, monkeypatch):
    assert jv.speed_rating(80, 20, 20).startswith("Muy buena") and jv.speed_rating(0.5, 0.2, 300).startswith("Muy lenta")
    monkeypatch.setattr(jv, "_speed_get", lambda url, limit_s, data=None: (len(data), 1.0) if data is not None else (2_500_000, 1.0))
    import nucleo.instantes as ins

    class S:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(ins.socket, "create_connection", lambda addr, timeout=None: S())
    r = jv.speed_test()
    assert r["ok"] and r["bajada"] == 20.0 and "megas de bajada" in r["msg"]
    assert jv._tr_parse("¿Cómo se dice buenos días en inglés?", instante.norm("¿Cómo se dice buenos días en inglés?")) == ("buenos días", "ingles")
    assert jv._tr_parse("traduce al francés: ¿dónde queda la estación?", instante.norm("traduce al francés: ¿dónde queda la estación?"))[1] == "frances"
    assert jv._tr_parse("traduce este documento", instante.norm("traduce este documento")) is None
    asked = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, json_mode=False, max_tokens=None: asked.append(msgs) or '"Good morning"')
    assert jv.translate("buenos días", "ingles") == "Good morning"
    assert len(asked[0]) == 2 and len(asked[0][0]["content"]) < 250      # pedido corto: sin contexto ni conversación


def test_video_de_youtube(jv, monkeypatch):
    m = jv._YT.search("resume este video https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s por favor")
    assert m and m.group(1).startswith("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert jv._YT.search("mira https://youtu.be/dQw4w9WgXcQ") and not jv._YT.search("abre https://example.com/watch?v=1")
    sent = {}
    monkeypatch.setattr(jv, "_gemini_for_stt", lambda: {"model": "gemini-x", "key": "k"})
    monkeypatch.setattr(jv, "_gemini_headers", lambda g: {})
    monkeypatch.setattr(jv, "_post", lambda url, headers, body, optional=(), timeout=180, stream=False: sent.update(url=url, body=body) or
                        {"candidates": [{"content": {"parts": [{"text": "Trata de fracciones."}]}}]})
    assert jv.youtube_summary("https://youtu.be/dQw4w9WgXcQ", "puntos clave") == "Trata de fracciones."
    assert sent["body"]["contents"][0]["parts"][0] == {"file_data": {"file_uri": "https://youtu.be/dQw4w9WgXcQ"}}
