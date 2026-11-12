"""12.21: HUD que se ve bien al abrirse y habilidades del día a día."""
import datetime
import json
import os
import time

import festivos
import instante

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N = instante.norm


# ---------------------------------------------------------------- HUD
def test_hud_no_se_atenua_ni_recalcula_de_mas():
    css = open(os.path.join(ROOT, "static", "css", "hud.css"), encoding="utf-8").read()
    assert "body.dim .shell { opacity: .8;" in css and "opacity: .42" not in css          # antes se veía transparente
    js = open(os.path.join(ROOT, "static", "js", "hud.js"), encoding="utf-8").read()
    assert 'el.shell.style.setProperty("--lvl"' not in js                               # el nivel del micro ya no toca todo el HUD
    assert 'window.addEventListener("resize"' in js and "!pillOn" in js
    pil = open(os.path.join(ROOT, "static", "js", "pildora.js"), encoding="utf-8").read()
    assert "H.poke()" in pil


def test_al_abrir_la_pildora_se_quita_el_recorte_antes_de_crecer(jv, monkeypatch):
    import nucleo.pildora as p
    order = []

    class Win:
        def resize(self, w, h):
            order.append("resize")

        def move(self, x, y):
            order.append("move")
    monkeypatch.setitem(jv.hud, "window", Win())
    monkeypatch.setattr(p, "_unshape", lambda: order.append("unshape"))
    monkeypatch.setattr(p, "_shape", lambda: order.append("shape"))
    monkeypatch.setattr(p, "cursor_over_hud", lambda: False)
    monkeypatch.setitem(p.pill, "docked", True)
    assert p._dock_now(False)
    assert order[:2] == ["unshape", "resize"]


# ---------------------------------------------------------------- plata y calendario
def test_cuentas():
    assert instante.money(N("cuánto es el IVA de 250000")) == "El IVA del 19 % de $250.000 es $47.500. Con IVA queda en $297.500."
    assert "$100.000" in instante.money(N("119.000 sin iva"))
    assert "queda en $64.000" in instante.money(N("cuánto es 80000 con el 20% de descuento"))
    assert "cada uno pone $49.500" in instante.money(N("divide una cuenta de 180000 entre 4 con propina"))
    r = instante.money(N("cuota de un préstamo de 10 millones a 24 meses al 1.8% mensual"))
    assert "$516.808" in r and "1,8 % mensual" in r and "aproximado" in r
    assert "$1.142.128" in instante.money(N("cuánto pago por un crédito de 50 millones al 14% efectivo anual a 5 años"))
    assert "$2.662.000" in instante.money(N("interés compuesto de 2 millones al 10% anual por 3 años"))
    assert "entonces 8 son 32.000" in instante.money(N("regla de tres: si 5 cuadernos cuestan 20000 cuánto cuestan 8"))
    for no in ["cuánto es el 15% de 80000", "el iva de la factura", "divide la clase entre 4 grupos", "si llueve mañana cuánto tarda"]:
        assert instante.money(N(no)) is None, no


def test_dias_habiles_y_festivos():
    hoy = datetime.date(2026, 11, 11)
    r = instante.workdays(N("cuántos días hábiles faltan para el 15 de diciembre"), hoy, festivos.holidays)
    assert "22 días hábiles" in r and "2 festivos" in r
    assert instante.workdays(N("festivos de diciembre"), hoy, festivos.holidays) == "Festivos de diciembre de 2026: martes 8, Inmaculada Concepción; viernes 25, Navidad."
    assert "quedan 3 festivos" in instante.workdays(N("cuántos festivos quedan este año"), hoy, festivos.holidays)


# ---------------------------------------------------------------- QR
def test_qr(jv, tmp_path, monkeypatch):
    assert jv.qr_payload("crea un QR de https://colegio.edu.co/circular") == ("https://colegio.edu.co/circular", "https://colegio.edu.co/circular")
    assert jv.qr_payload("hazme un QR de colegio.edu.co")[0] == "https://colegio.edu.co"
    c, label = jv.qr_payload("crea un QR del wifi Casa Pérez con clave Abc;123")
    assert c == "WIFI:T:WPA;S:Casa Pérez;P:Abc\;123;;" and "Abc" not in label          # la clave no se repite en voz alta
    assert jv.qr_payload("genera un código QR") is None
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    path = jv.make_qr("https://colegio.edu.co", "colegio")
    assert os.path.getsize(path) > 300 and open(path, "rb").read(4) == b"\x89PNG"


# ---------------------------------------------------------------- radio
def test_radio_busca_primero_en_colombia(jv, monkeypatch):
    import nucleo.vidadiaria as v
    urls = []

    class R:
        def __init__(self, data):
            self.d = data

        def read(self):
            return json.dumps(self.d).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        urls.append(req.full_url)
        return R([{"name": "Caracol Radio Bogotá", "url_resolved": "https://x/stream"}] if "countrycode=CO" in req.full_url else [])
    monkeypatch.setattr(v.urllib.request, "urlopen", fake)
    assert jv.radio_find("caracol") == [{"name": "Caracol Radio Bogotá", "url": "https://x/stream"}]
    assert "name=caracol" in urls[0] and "countrycode=CO" in urls[0]
    jv.radio_find("", "salsa")
    assert "tag=salsa" in urls[-1]
    assert jv._RADIO_ON.search("pon la emisora caracol") and jv._RADIO_ON.search("pon tropicana estereo")
    assert not jv._RADIO_ON.search("pon una alarma a las 6 am") and not jv._RADIO_ON.search("pon musica de salsa")


def test_radio_suena_y_se_apaga(jv, monkeypatch):
    """La tubería real: ffmpeg decodifica y el sonido va saliendo; «apaga la radio» lo corta."""
    import sys
    import types
    import nucleo.vidadiaria as v
    if not jv._ffmpeg():
        import pytest
        pytest.skip("sin ffmpeg en este equipo")
    wrote = []

    class Out:
        def __init__(self, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def write(self, data):
            wrote.append(len(data))
    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(RawOutputStream=Out))
    real = v.subprocess.Popen

    def popen(args, **k):                                   # en vez de la emisora: un tono de 30 s generado por ffmpeg
        i = args.index("-i")
        k.pop("creationflags", None)
        return real(args[:1] + ["-loglevel", "quiet", "-re", "-f", "lavfi", "-i", "sine=frequency=440:duration=30"] + args[i + 2:], **k)
    monkeypatch.setattr(v.subprocess, "Popen", popen)
    monkeypatch.setattr(jv, "radio_find", lambda q, genre="": [{"name": "Prueba FM", "url": "http://x"}])
    assert jv.radio_play("prueba") == "Prueba FM"
    t0 = time.time()
    while not wrote and time.time() - t0 < 8:
        time.sleep(0.1)
    assert wrote and jv._radio["name"] == "Prueba FM"
    assert jv.radio_stop() and jv._radio["proc"] is None and not jv.radio_stop()


# ---------------------------------------------------------------- cocina
def test_modo_cocina(jv, ask, monkeypatch):
    timers = []
    monkeypatch.setattr(jv, "add_timer", lambda secs, label="": timers.append((secs, label)))
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, json_mode=False, max_tokens=None: json.dumps({
        "titulo": "Arroz con pollo", "porciones": 4, "ingredientes": ["2 tazas de arroz", "1 pechuga"],
        "pasos": [{"texto": "Lava el arroz.", "minutos": 0}, {"texto": "Cocina el pollo.", "minutos": 20}, {"texto": "Mezcla y sirve.", "minutos": 0}]}))
    who, said = ask("modo cocina arroz con pollo")
    assert who == "COCINA" and "Arroz con pollo" in said and jv.cook_active()
    assert "Paso 1 de 3: Lava el arroz." in ask("siguiente paso")[1]
    assert "Paso 2 de 3" in ask("siguiente paso")[1] and timers == [(1200, "Arroz con pollo: paso 2")]
    assert "Paso 2 de 3" in ask("repite")[1]
    assert "2 tazas de arroz" in ask("los ingredientes")[1]
    assert "Paso 1 de 3" in ask("paso anterior")[1]
    ask("siguiente paso")
    assert "último paso" in ask("siguiente paso")[1] and not jv.cook_active()
    assert ask("ayúdame a preparar la clase de fracciones")[0] != "COCINA"


# ---------------------------------------------------------------- inglés y cuentos
def test_quiz_de_ingles(jv, ask, monkeypatch):
    import nucleo.vidadiaria as v
    monkeypatch.setattr(v.random, "sample", lambda seq, k: list(seq[:k]))
    who, said = ask("quiz de inglés")
    assert who == "INGLÉS" and "achieve" in said
    assert "¡Correcto!" in ask("lograr")[1]                                # achieve
    assert "Casi" in ask("comprar")[1]                                     # borrow = pedir prestado
    assert "¡Correcto!" in ask("significa reto")[1]
    assert "Acertaste 2 de 3" in ask("termina el quiz")[1] and jv._eng["quiz"] is None
    assert ask("empieza la clase de inglés")[0] != "INGLÉS"
    w = instante.word_of_day(N("palabra del día en inglés"), datetime.date(2026, 11, 11))
    assert w == instante.WORDS[datetime.date(2026, 11, 11).toordinal() % len(instante.WORDS)]


def test_practica_de_ingles(jv, ask, monkeypatch):
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, json_mode=False, max_tokens=None: json.dumps(
        {"reply": "Nice! What did you eat?", "fix": "«I went» (no «I goed»): el pasado de go es irregular."}))
    assert ask("practiquemos inglés")[0] == "INGLÉS"
    who, said = ask("yesterday I goed to the park")
    assert who == "INGLÉS" and "What did you eat?" in said and "I went" in said
    assert "volvemos al español" in ask("terminemos la práctica")[1]
    assert jv._eng["talk_until"] == 0.0


def test_cuento(jv, ask, monkeypatch):
    asked = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, json_mode=False, max_tokens=None: asked.append(msgs) or "El dragón Tomás\n\nHabía una vez un dragón pequeño. Fin.")
    who, said = ask("cuéntame un cuento de dragones para un niño de 6 años")
    assert who == "CUENTO" and "El dragón Tomás" in said
    assert "6 años" in asked[0][0]["content"] and "dragones" in asked[0][1]["content"]


def test_pausa_activa_se_puede_cortar(jv, ask, monkeypatch):
    import nucleo.vidadiaria as v
    said = []
    monkeypatch.setattr(jv, "speak", lambda text, **k: said.append(text))
    v._pausa["stop"].clear()
    v._pausa["on"] = True
    v._pausa["stop"].set()                                  # ya pidieron parar: no dice todos los pasos
    v._pausa_run("pausa", 4)
    assert len(said) <= 2 and not v._pausa["on"]
    assert ask("hazme una pausa activa")[0] == "PAUSA" and ask("respiración de 2 minutos")[0] == "PAUSA"
