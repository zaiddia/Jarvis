"""12.40: profesor particular y comprador inteligente (modo general)."""
import datetime
import json
import os
import time

import pytest

import comprador as CM
import cursopersonal as CP

TODAY = datetime.date(2026, 11, 19)


# ================================================================ PROFESOR PARTICULAR (lógica)
def test_frases_para_crear_el_curso():
    assert CP.level_in("quiero aprender inglés desde cero") == "principiante"
    assert CP.level_in("francés nivel B1") == "B1" and CP.level_in("guitarra nivel intermedio") == "intermedio"
    assert CP.minutes_in("inglés 20 minutos al día") == 20 and CP.minutes_in("guitarra") == 15
    assert CP.language_of("inglés para viajar") == "inglés" and CP.language_of("guitarra") == ""
    assert CP.slug("Inglés para viajar") == "ingles-para-viajar"


def test_repeticion_espaciada_y_racha():
    c = CP.new_course("inglés", today=TODAY)
    CP.add_cards(c, [{"frente": "dog", "reverso": "perro"}, {"frente": "cat", "reverso": "gato"}, {"frente": "dog", "reverso": "x"}], today=TODAY)
    assert len(c["tarjetas"]) == 2 and not CP.due_cards(c, TODAY) and len(CP.due_cards(c, TODAY + datetime.timedelta(days=1))) == 2
    card = c["tarjetas"][0]
    CP.review(card, True, TODAY)
    assert card["caja"] == 1 and card["proxima"] == "2026-11-20"
    for _ in range(3):
        CP.review(card, True, TODAY)
    assert card["caja"] == 4 and card["proxima"] == "2026-12-05"
    CP.review(card, False, TODAY)
    assert card["caja"] == 0 and card["proxima"] == "2026-11-20"
    for d in (17, 18, 19):
        CP.mark_day(c, datetime.date(2026, 11, d))
    assert CP.streak(c, TODAY) == 3 and CP.streak(c, datetime.date(2026, 11, 20)) == 3 and CP.streak(c, datetime.date(2026, 11, 22)) == 0
    assert CP.quick_check("El perro", "perro | el perro") is True and CP.quick_check("perrro", "perro") is True
    assert CP.quick_check("la casa", "perro") is None


# ================================================================ PROFESOR PARTICULAR (por voz)
PLAN = {"plan": [{"titulo": f"Lección {i}", "objetivo": f"objetivo {i}"} for i in range(1, 25)]}
LESSON = {"explicacion": "Saludos en inglés.", "ejemplos": ["Hello = hola"],
          "ejercicios": [{"pregunta": "¿Cómo se dice hola?", "respuesta": "hello | hi", "pista": "Empieza por h"},
                         {"pregunta": "¿Cómo se dice gracias?", "respuesta": "thank you | thanks", "pista": "th…"},
                         {"pregunta": "¿Cómo se dice adiós?", "respuesta": "goodbye | bye", "pista": "g…"}],
          "tarjetas": [{"frente": "hello", "reverso": "hola"}, {"frente": "thanks", "reverso": "gracias"}], "practica": "Saluda a 3 personas en inglés."}


@pytest.fixture
def prof(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="", *a, **k: fn())
    monkeypatch.setitem(jv._st, "session", None)
    monkeypatch.setitem(jv._st, "convo", "")
    calls = []

    def ai(msgs, json_mode=False, max_tokens=None, **k):
        p = msgs[0]["content"]
        calls.append(p)
        if "Arma un plan de 24 lecciones" in p:
            return json.dumps(PLAN)
        if "Explica en español sencillo" in p:
            return json.dumps(LESSON)
        if "¿Está bien?" in p:
            return json.dumps({"bien": "goodbye" in p.lower() and "bye bye" in p.lower(), "comentario": "Vale."})
        return "ok"
    monkeypatch.setattr(jv, "ai_chat", ai)
    return calls


def test_curso_leccion_y_repaso(jv, ask, prof):
    who, said = ask("quiero aprender inglés desde cero")
    assert who == "PROFESOR" and "24 lecciones de 15 minutos" in " ".join(t for t, _o in jv._rec.replies)
    d = jv.cp_load()
    assert d["activo"] == "ingles" and d["cursos"]["ingles"]["hora"] == "19:00"
    ask("dame la lección de hoy")
    assert "Ejercicio 1 de 3: ¿Cómo se dice hola?" in jv._rec.replies[-1][0]
    assert "Pista: Empieza por h" in ask("pista")[1]
    ask("hello")
    assert "¡Bien!" in jv._rec.replies[-2][0] and "Ejercicio 2 de 3" in jv._rec.replies[-1][0]
    ask("no sé")
    assert "Era: thank you | thanks" in jv._rec.replies[-2][0]
    ask("bye bye")                                         # la IA decide (no es igual a la respuesta)
    said = " ".join(t for t, _o in jv._rec.replies[-3:])
    assert "Terminamos: 2 de 3 bien" in said and "Saluda a 3 personas" in said
    c = jv.cp_load()["cursos"]["ingles"]
    assert c["hechas"] == [1] and len(c["tarjetas"]) == 3 and c["intentos"] == 3 and c["aciertos"] == 2
    assert jv._st["session"] is None
    for card in c["tarjetas"]:
        card["proxima"] = "2000-01-01"
    d = jv.cp_load()
    d["cursos"]["ingles"] = c
    jv.cp_save(d)
    ask("repasa inglés")
    assert "3 tarjetas para hoy" in jv._rec.replies[-2][0] and "Tarjeta 1 de 3" in jv._rec.replies[-1][0]
    assert "dejamos la práctica aquí" in ask("salir del repaso")[1]
    assert "1 de 24 lecciones" in ask("¿cómo voy en inglés?")[1]


def test_una_orden_en_medio_de_la_leccion(jv, ask, prof, monkeypatch):
    ask("quiero aprender inglés")
    ask("dame la lección de hoy")
    who, _ = ask("sube el volumen")
    assert who == "skill:volumen" and jv._st["session"] is not None


def test_conversacion_en_ingles(jv, ask, prof, monkeypatch):
    streamed = []
    monkeypatch.setattr(jv, "answer_question_streaming", lambda text: streamed.append(text))
    who, said = ask("practica inglés conmigo")
    assert who == "PROFESOR" and "te corrijo en español" in said
    assert "PRÁCTICA DE CONVERSACIÓN EN INGLÉS" in jv.study_ctx() and "Corrección:" in jv.study_ctx()
    ask("yesterday I go to the beach with my family")
    assert streamed == ["yesterday I go to the beach with my family"]
    assert "Terminamos la práctica" in ask("termina la práctica")[1] and jv.study_ctx() == ""


def test_recordatorio_diario(jv, ask, prof, monkeypatch):
    ask("quiero aprender guitarra")
    assert "18:30" in ask("recuérdame practicar guitarra a las 6 y media de la tarde")[1]
    sent = []
    monkeypatch.setattr(jv, "notify", lambda text, origin="": sent.append((text, origin)))
    assert jv.study_tick(datetime.datetime(2026, 11, 19, 18, 0)) == []
    assert jv.study_tick(datetime.datetime(2026, 11, 19, 18, 31)) == ["guitarra"] and sent[0][1] == "RECORDATORIO"
    assert jv.study_tick(datetime.datetime(2026, 11, 19, 20, 0)) == []                    # una vez al día


def test_no_se_confunde(jv, ask, prof):
    assert ask("enséñame lo que sabes hacer")[0] != "PROFESOR"
    assert ask("olvida la lección de los quices")[0] != "PROFESOR"


# ================================================================ COMPRADOR (lógica)
def test_plata_y_pedido():
    assert CM.money("2 millones") == 2_000_000 and CM.money("1,5 millones") == 1_500_000 and CM.money("un millón y medio") == 1_500_000
    assert CM.money("800 mil") == 800_000 and CM.money("$2.199.900") == 2_199_900 and CM.money("2 palos") == 2_000_000
    r = CM.parse_request("quiero comprar un portátil de unos 2 millones para trabajar y ver películas")
    assert r == {"producto": "portatil", "presupuesto": 2_000_000, "uso": "trabajar y ver peliculas"}
    assert CM.parse_request("ayúdame a escoger una nevera de 1,5 millones")["presupuesto"] == 1_500_000
    assert CM.parse_request("qué celular me recomiendas de 800 mil")["producto"] == "celular"
    for no in ("quiero comprar leche", "quiero comprar un carro", "agrega leche a la lista del mercado"):
        assert CM.parse_request(no) is None, no


def test_precio_comprobado_en_la_pagina():
    page = "Portátil Lenovo IdeaPad Slim 3 15 pulgadas Ryzen 5 8GB RAM 512GB SSD. Antes $2.499.900 Ahora $2.199.900 envío gratis"
    assert CM.price_in_page(2199900, page) and not CM.price_in_page(2099900, page)
    src = [{"texto": page, "leida": True, "url": "https://www.alkosto.com/p1", "fuente": "alkosto.com"},
           {"texto": "resumen", "leida": False, "url": "https://x.com", "fuente": "x.com"}]
    ok, bad = CM.verify_products([
        {"nombre": "Lenovo IdeaPad Slim 3", "fuente": 1, "precio": 2199900, "cita_precio": "Ahora $2.199.900 envío gratis",
         "specs": "Ryzen 5, 8GB, 512GB", "cita_specs": "Ryzen 5 8GB RAM 512GB SSD"},
        {"nombre": "Inventado", "fuente": 1, "precio": 1899900, "cita_precio": "", "specs": "", "cita_specs": ""},
        {"nombre": "Del resumen", "fuente": 2, "precio": 1000000, "cita_precio": "", "specs": "", "cita_specs": ""}], src, 2_000_000)
    assert [x["nombre"] for x in ok] == ["Lenovo IdeaPad Slim 3"] and ok[0]["tienda"] == "Alkosto" and ok[0]["sobre"]
    assert {b["motivo"] for b in bad} == {"el precio no está en la página", "solo había el resumen del buscador"}
    ok2, bad2 = CM.verify_products([{"nombre": "Caro", "fuente": 1, "precio": 2499900, "cita_precio": "", "specs": "", "cita_specs": ""}], src, 2_000_000)
    assert not ok2 and "presupuesto" in bad2[0]["motivo"]
    assert CM.current_price(page, 2199900) == 2199900 and CM.current_price("Ahora $1.999.900 antes $2.199.900", 2199900) == 1999900


# ================================================================ COMPRADOR (por voz, de principio a fin)
PAGES = {"alkosto": "Portátil Lenovo IdeaPad Slim 3 Ryzen 5 8GB RAM 512GB SSD pantalla 15,6 pulgadas. Precio $1.899.900 envío gratis a todo el país.",
         "exito": "Portátil HP 15 Intel Core i5 16GB RAM 512GB SSD. Hoy $2.049.900 con 12 cuotas sin interés en tarjeta Éxito y más cosas para tu hogar y oficina.",
         "falabella": "Portátil ASUS Vivobook 16 Core i7 16GB 1TB. Precio $3.299.900 en Falabella; garantía de un año con el fabricante y envío a todo Colombia."}


@pytest.fixture
def tienda(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "out"))
    monkeypatch.setattr(jv, "is_offline", lambda: False)
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="", *a, **k: fn())
    monkeypatch.setitem(jv._cm, "busy", False)
    monkeypatch.setitem(jv._cm, "last", None)
    ddg = '<a class="result__a" href="https://www.{d}/p">{d}</a><a class="result__snippet">x</a>'

    def get_text(url, timeout=12):
        if "duckduckgo" in url:
            return "".join(ddg.format(d=d) for d in ("alkosto.com", "exito.com", "falabella.com.co"))
        for k, v in PAGES.items():
            if k in url:
                return f"<html><body><p>{v}</p></body></html>"
        return ""
    monkeypatch.setattr(jv, "_get_text", get_text)

    def ai(msgs, json_mode=False, max_tokens=None, **k):
        p = msgs[0]["content"]
        if "PRODUCTOS que se venden" in p:
            import re
            n = {k: int(re.search(rf"\[(\d+)\][^\n]*{k}", p).group(1)) for k in ("alkosto", "exito", "falabella")}
            return json.dumps({"productos": [
                {"nombre": "Lenovo IdeaPad Slim 3", "fuente": n["alkosto"], "precio": 1899900, "cita_precio": "Precio $1.899.900 envío gratis",
                 "specs": "Ryzen 5, 8 GB, 512 GB", "cita_specs": "Ryzen 5 8GB RAM 512GB SSD"},
                {"nombre": "HP 15", "fuente": n["exito"], "precio": 2049900, "cita_precio": "Hoy $2.049.900 con 12 cuotas",
                 "specs": "Core i5, 16 GB", "cita_specs": "Intel Core i5 16GB RAM 512GB SSD"},
                {"nombre": "ASUS Vivobook 16", "fuente": n["falabella"], "precio": 3299900, "cita_precio": "Precio $3.299.900 en Falabella",
                 "specs": "", "cita_specs": ""},
                {"nombre": "Dell inventado", "fuente": n["alkosto"], "precio": 1500000, "cita_precio": "", "specs": "", "cita_specs": ""}]})
        if "Ayuda a escoger" in p:
            return json.dumps({"productos": [{"n": 1, "pros": ["Barato"], "contras": ["8 GB"], "para_quien": "Uso básico"},
                                             {"n": 2, "pros": ["16 GB"], "contras": ["Se pasa un poco"], "para_quien": "Trabajo"}],
                               "recomendado": 2, "por_que": "tiene el doble de memoria para trabajar.", "consejos": ["Revisa la garantía."]})
        return "{}"
    monkeypatch.setattr(jv, "ai_chat", ai)
    return tmp_path


def test_comparacion_de_principio_a_fin(jv, ask, tienda):
    ask("quiero comprar un portátil de unos 2 millones para trabajar y ver películas")
    said = " ".join(t for t, _o in jv._rec.replies)
    assert "Encontré 2 opciones con precio comprobado, desde $1.899.900 (Lenovo IdeaPad Slim 3 en Alkosto)" in said
    assert "te recomiendo HP 15 por $2.049.900 en Éxito" in said
    folder = os.path.join(jv.settings["output_dir"], "Jarvis", "Compras")
    from docx import Document
    doc = Document(os.path.join(folder, os.listdir(folder)[0]))
    text = "\n".join(p.text for p in doc.paragraphs) + "\n".join(c.text for r in doc.tables[0].rows for c in r.cells)
    assert "La recomendación" in text and "$2.049.900 (se pasa un poco)" in text and "+ 16 GB" in text
    assert "2 productos se descartaron" in text and "se pasa del presupuesto" in text and "el precio no está en la página" in text
    who, said = ask("vigila el precio del recomendado")
    assert who == "COMPRAS" and "HP 15" in said and jv.watched()[0]["ultimo"] == 2049900
    assert "HP 15 (Éxito): $2.049.900" in ask("¿qué precios estás vigilando?")[1]


def test_aviso_si_baja(jv, tienda, monkeypatch):
    jv.watch_add({"nombre": "HP 15", "url": "https://www.exito.com/p", "tienda": "Éxito", "precio": 2049900})
    sent = []
    monkeypatch.setattr(jv, "notify", lambda text, origin="": sent.append(text))
    it = jv.watched()[0]
    it["visto"] = 0
    jv._cm_save([it])
    PAGES["exito"] = "Portátil HP 15 Intel Core i5 16GB. Antes $2.049.900 Hoy $1.849.900 por tiempo limitado en tienda virtual y envío gratis a todo el país."
    try:
        assert jv.watch_tick() == 1
    finally:
        PAGES["exito"] = "Portátil HP 15 Intel Core i5 16GB RAM 512GB SSD. Hoy $2.049.900 con 12 cuotas sin interés en tarjeta Éxito y más cosas para tu hogar y oficina."
    assert "Bajó de precio: HP 15 ahora está en $1.849.900" in sent[0] and jv.watched()[0]["ultimo"] == 1849900
    assert jv.watch_tick() == 0                                         # no vuelve a mirar hasta dentro de 12 horas
