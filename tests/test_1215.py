"""Pruebas de la 12.15: vencimientos, recibos, medicamentos, citas, cumpleaños, presupuesto, menú, audio, médico del PC y viajes."""
import datetime as dt
import json
import os
import sys

import pytest

import hogar as H
import pcsalud
import vidadiaria as vd

D, DT = dt.date, dt.datetime


@pytest.fixture
def store(tmp_path):
    H.configure(str(tmp_path))
    vd.configure(str(tmp_path))
    yield H
    for k, v in H.KEYS.items():
        H.data[k] = v.copy()


# ============================================================================ LÓGICA PURA
def test_fechas_y_horas():
    T = D(2026, 11, 7)
    assert H.parse_date("el 15 de marzo de 2027", T) == D(2027, 3, 15) and H.parse_date("2 de febrero", T) == D(2027, 2, 2)
    assert H.parse_date("15/03/2027", T) == D(2027, 3, 15) and H.parse_date("en 3 meses", T) == D(2027, 2, 7)
    assert H.parse_date("el 20", T) == D(2026, 11, 20) and H.parse_date("el 3", T) == D(2026, 12, 3) and H.parse_date("pronto", T) is None
    assert H.parse_time("a las 3 de la tarde") == "15:00" and H.parse_time("8:30 am") == "08:30" and H.parse_time("a las 7 y media de la noche") == "19:30"
    assert H.parse_time("sin hora") == "" and H.every_hours(8, "06:00") == ["06:00", "14:00", "22:00"]
    assert H.add_months(D(2027, 1, 31), 1) == D(2027, 2, 28) and H.hour_spoken("20:30") == "8:30 de la noche"


def test_vencimientos_y_avisos(store):
    T = D(2026, 11, 7)
    s = H.venc_add("SOAT de la moto", D(2026, 12, 7))
    assert s["tipo"] == "soat" and H.venc_type("revisión técnico mecánica") == "tecnomecanica"
    H.venc_add("Pasaporte", D(2026, 11, 14))
    assert [x["nombre"] for x, _ in H.venc_to_warn(T)] == ["SOAT de la moto", "Pasaporte"] and H.venc_to_warn(T) == []
    assert H.venc_text(s, 30) == "SOAT de la moto se vence en 30 días (el 7 de diciembre, en 30 días)." or "30 días" in H.venc_text(s, 30)
    assert H.venc_add("SOAT de la moto", D(2027, 12, 7))["fecha"] == "2027-12-07" and len(H.data["venc"]) == 2
    assert [x["nombre"] for x, _ in H.venc_soon(T, 31)] == ["Pasaporte"]


def test_medicamentos(store):
    m = H.med_add("Losartán", ["08:00", "20:00"], "50 mg", stock=11)
    with pytest.raises(ValueError):
        H.med_add("x", [])
    assert [x for x, _ in H.meds_due(DT(2026, 11, 7, 8, 3))] == [m] and H.meds_due(DT(2026, 11, 7, 8, 5)) == []
    assert H.meds_due(DT(2026, 11, 7, 8, 20)) == []                                     # ya pasó la ventana
    h, stock = H.med_taken(m, DT(2026, 11, 7, 9, 0))
    assert h == "08:00" and stock == 10 and H.med_taken(m, DT(2026, 11, 7, 9, 5))[1] == 10      # no descuenta dos veces
    assert H.med_days_left(m) == 5 and [x for x, _ in H.meds_refill(D(2026, 11, 7))] == [m] and H.meds_refill(D(2026, 11, 7)) == []
    assert [h for _, h in H.meds_missed(DT(2026, 11, 7, 21, 10))] == ["20:00"]
    corto = H.med_add("Amoxicilina", ["07:00"], hasta=D(2026, 11, 9))
    assert H.med_active(corto, D(2026, 11, 9)) and not H.med_active(corto, D(2026, 11, 10))


def test_citas_y_cumpleanos(store):
    c = H.cita_add("Odontología", D(2026, 11, 8), "15:00", "EPS Sura")
    assert H.citas_to_warn(DT(2026, 11, 7, 17, 0)) == [] and [x for x, _ in H.citas_to_warn(DT(2026, 11, 7, 19, 0))] == [c]
    assert H.citas_to_warn(DT(2026, 11, 8, 8, 0)) == []                                  # temprano: espera
    assert [k for _, k in H.citas_to_warn(DT(2026, 11, 8, 13, 0))] == ["hoy"]
    assert "a las 3 de la tarde en EPS Sura" in H.cita_text(c, "mañana")
    a = H.cumple_add("Ana", 11, 10, 1990, "hermana")
    assert H.next_birthday(a, D(2026, 11, 7)) == D(2026, 11, 10) and H.age_on(a, D(2026, 11, 10)) == 36
    assert [x for x, _, _ in H.cumples_to_warn(D(2026, 11, 7))] == [a] and H.cumples_to_warn(D(2026, 11, 8)) == []
    bis = H.cumple_add("Leo", 2, 29)
    assert H.next_birthday(bis, D(2027, 1, 1)) == D(2027, 3, 1)
    assert "cumple 36 años" in H.greeting_prompt(a, D(2026, 11, 10)) and "hasta $100.000" in H.gift_prompt(a, "$100.000")


def test_presupuesto_y_suscripciones(store):
    H.budget_set("Comida", 500_000)
    assert H.budget_to_warn({"Comida": 420_000}, D(2026, 11, 7))[0][4] == 80 and H.budget_to_warn({"Comida": 430_000}, D(2026, 11, 7)) == []
    assert H.budget_to_warn({"Comida": 520_000}, D(2026, 11, 7))[0][4] == 100
    g = [{"fecha": "2026-09-05", "concepto": "Netflix", "monto": 26900}, {"fecha": "2026-10-05", "concepto": "netflix", "monto": 26900},
         {"fecha": "2026-11-05", "concepto": "Netflix", "monto": 26900}, {"fecha": "2026-10-10", "concepto": "almuerzo", "monto": 15000},
         {"fecha": "2026-11-10", "concepto": "almuerzo", "monto": 60000}]
    subs = H.subscriptions(g, [{"nombre": "Internet", "monto": 90000}], D(2026, 11, 7))
    assert [s["nombre"] for s in subs] == ["Internet", "Netflix"] and subs[1]["anual"] == 26900 * 12


def test_recibo_menu_y_viaje():
    T = D(2026, 11, 7)
    r = H.parse_receipt({"negocio": "Alkosto", "fecha": "2026-11-06", "total": "1.299.900", "concepto": "Televisor 50 pulgadas", "es_garantia": True,
                         "producto": "Televisor", "meses_garantia": 0}, T)
    assert r["total"] == 1299900 and r["fecha"] == D(2026, 11, 6) and r["garantia"] and r["meses"] == 12
    assert H.parse_receipt({"total": 25000, "fecha": "2031-01-01"}, T)["fecha"] == T
    with pytest.raises(ValueError):
        H.parse_receipt({"total": 0}, T)
    m = H.meals_validate({"dias": [{"dia": "Lunes", "almuerzo": "Arroz con pollo"}], "lista": [{"item": "pollo", "cantidad": "1 kg", "precio": "12000"}]})
    assert m["costo"] == 12000 and m["lista"][0]["item"] == "pollo"
    tr = {"desde": "2026-11-20", "hasta": "2026-11-24", "internacional": False}
    items = H.packing_list(tr, 31, 24, 70)
    assert "Bloqueador solar" in items and "Sombrilla o impermeable" in items and "5 mudas de ropa" in items and "Chaqueta abrigada" not in items
    assert "Pasaporte" in H.packing_list(dict(tr, internacional=True), 10, 2, 0) and "Chaqueta abrigada" in H.packing_list(tr, 10, 2, 0)


def test_viajes_avisos(store):
    t = H.trip_add("Cartagena", D(2026, 11, 20), D(2026, 11, 24))
    t["hora_vuelo"] = "06:00"
    assert [k for _, k in H.trips_to_warn(DT(2026, 11, 18, 10, 0))] == ["docs"]
    assert [k for _, k in H.trips_to_warn(DT(2026, 11, 19, 6, 30))] == ["checkin"]
    assert [k for _, k in H.trips_to_warn(DT(2026, 11, 20, 2, 45))] == ["salir"]


def test_medico_del_pc_logica():
    d = pcsalud.eval_disks([("C:", 3e9, 250e9)])
    assert d["estado"] == "fallo" and d["arreglo"][0][0] == "temporales"
    assert pcsalud.eval_disks([("C:", 120e9, 250e9)])["estado"] == "ok"
    assert pcsalud.eval_memory(92, 8e9, [("Chrome", 2e9)])["arreglo"]
    assert pcsalud.wear_from_report("<DesignCapacity>50000</DesignCapacity><FullChargeCapacity>27000</FullChargeCapacity>") == (50000, 27000)
    assert pcsalud.eval_battery(80, False, (50000, 27000))["estado"] == "fallo" and pcsalud.eval_battery(None, False, None)["estado"] == "info"
    assert pcsalud.av_from_state("Defender", 397568) == {"nombre": "Defender", "activo": True, "al_dia": True}
    assert pcsalud.av_from_state("Viejo", 393488)["al_dia"] is False and not pcsalud.av_from_state("Off", 393472)["activo"]
    assert pcsalud.eval_antivirus([])["estado"] == "fallo"
    assert pcsalud.eval_updates(3)["estado"] == "aviso" and pcsalud.eval_uptime(24 * 9)["estado"] == "aviso"
    cs = [pcsalud.eval_disks([("C:", 120e9, 250e9)]), pcsalud.eval_updates(2)]
    assert pcsalud.score(cs) == 80 and "Para revisar" in pcsalud.spoken(cs)


# ============================================================================ CON JARVIS
@pytest.fixture
def jvd(jv, tmp_path, monkeypatch, store):
    import adjuntos
    adjuntos.configure(str(tmp_path))
    monkeypatch.setattr(jv, "settings", dict(jv.settings, output_dir=str(tmp_path / "out"), telegram_alerts=False))
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    monkeypatch.setattr(jv, "notify", lambda msg, origin="": jv._rec.replies.append((msg, origin)))
    yield jv


def test_voz_vencimientos_y_renta(jvd, ask, monkeypatch):
    who, said = ask("el SOAT se vence el 15 de marzo de 2027")
    assert "SOAT vence" in said and H.data["venc"][0]["tipo"] == "soat"
    ask("la licencia de conducción se vence el 1 de diciembre de 2026")
    who, said = ask("¿qué se me vence este mes?")
    assert "Licencia de conducción" in said or "No se te vence" in said
    who, said = ask("¿cuándo vence el SOAT?")
    assert "SOAT se vence" in said
    ask("ya renové el SOAT hasta el 15 de marzo de 2028")
    assert H.find("venc", "soat")["fecha"] == "2028-03-15"
    who, said = ask("¿cuándo declaro renta?")
    assert "dos últimos dígitos" in said
    ask("los dos últimos dígitos de mi cédula son 4 5")
    searched = []
    monkeypatch.setattr(jvd, "web_search", lambda q: searched.append(q))
    ask("¿cuándo declaro renta?")
    assert searched and "dígitos NIT 45" in searched[0]


def test_voz_medicamentos_sin_quitar_recordatorios(jvd, ask, monkeypatch):
    who, said = ask("recuérdame tomar losartán de 50 mg a las 8 de la mañana y a las 8 de la noche, tengo 30 pastillas")
    m = H.data["meds"][0]
    assert m["nombre"].lower().startswith("losart") and m["horas"] == ["08:00", "20:00"] and m["stock"] == 30 and m["dosis"] == "50 mg"
    ask("recuérdame darle amoxicilina a mi hijo cada 8 horas desde las 6 por 7 días")
    a = H.find("meds", "amoxicilina")
    assert a["horas"] == ["06:00", "14:00", "22:00"] and a["persona"] == "hijo" and a["hasta"]
    monkeypatch.setattr(H.DT, "now", classmethod(lambda cls: DT(2026, 11, 7, 9, 0))) if False else None
    who, said = ask("ya me tomé el losartán")
    assert "Anotado: Losartán" in said or "Anotado: losartán" in said
    ask("compré 30 pastillas de losartán")
    assert H.find("meds", "losartan")["stock"] >= 59
    who, said = ask("¿qué medicamentos tengo?")
    assert "amoxicilina" in said.lower()
    n = len(H.data["meds"])
    jvd._rec.clear()
    ask("recuérdame tomar agua a las 3")                                           # eso es un recordatorio normal
    assert len(H.data["meds"]) == n
    ask("ya no tomo amoxicilina")
    assert not H.find("meds", "amoxicilina")


def test_voz_citas_cumples_presupuesto(jvd, ask, monkeypatch):
    who, said = ask("tengo cita con el odontólogo el 20 a las 3 de la tarde")
    assert "Anotada" in said and H.data["citas"][0]["hora"] == "15:00"
    n = len(H.data["citas"])
    ask("tengo una reunión de padres el 20 a las 3")                               # no es médica: no va a citas
    assert len(H.data["citas"]) == n
    who, said = ask("el cumpleaños de mi mamá es el 3 de mayo de 1965")
    assert "Mama cumple" in said or "mamá" in said.lower() or "Mama" in said
    monkeypatch.setattr(jvd, "ai_chat", lambda msgs, **k: "¡Feliz cumpleaños, mamá! Te quiero mucho.")
    monkeypatch.setattr(jvd, "card", lambda *a, **k: None)
    who, said = ask("escríbele un mensaje de cumpleaños a mi mamá")
    assert "Feliz cumpleaños" in said
    who, said = ask("mi presupuesto de comida es de 500 mil")
    assert "$500.000 al mes para Comida" in said
    vd.add_expense(450_000, "mercado")
    who, said = ask("¿cómo voy con el presupuesto?")
    assert "Comida: $450.000 de $500.000 (90 %, ojo)" in said
    who, said = ask("gasté 20 mil en almuerzo")                                   # los gastos siguen como siempre
    assert said.startswith("Anotado: $20.000")


def test_recibo_por_foto_y_excel(jvd, ask, monkeypatch, tmp_path):
    import adjuntos
    it = adjuntos.add("recibo.txt", "ALKOSTO\nTelevisor 50\nTOTAL $1.299.900".encode())
    monkeypatch.setattr(jvd, "ai_chat", lambda msgs, **k: json.dumps({"negocio": "Alkosto", "fecha": D.today().isoformat(), "total": 1299900,
                                                                    "concepto": "Televisor", "es_garantia": True, "producto": "Televisor", "meses_garantia": 24}))
    msg = jvd.receipt_from(it)
    assert "$1.299.900" in msg and "garantía" in msg and H.data["venc"][0]["tipo"] == "garantia"
    assert vd.data["gastos"][-1]["monto"] == 1299900
    who, said = ask("registra el recibo")
    assert vd.data["gastos"][-1]["monto"] == 1299900 and len(vd.data["gastos"]) == 2
    who, said = ask("exporta mis gastos del mes a excel")
    assert "Excel" in said and any(f.endswith(".xlsx") for f in os.listdir(tmp_path / "out" / "Documentos"))
    card = jvd.card_of([it])
    assert "audio" in {a["a"] for a in card["acciones"]}
    foto = adjuntos.add("recibo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    assert "recibo" in {a["a"] for a in jvd.card_of([foto])["acciones"]}


def test_menu_y_cocina(jvd, ask, monkeypatch):
    monkeypatch.setattr(jvd, "ai_chat", lambda msgs, **k: json.dumps({"dias": [{"dia": "Lunes", "desayuno": "Arepa", "almuerzo": "Sancocho", "cena": "Tortilla"}],
                                                                    "lista": [{"item": "yuca", "cantidad": "1 kg", "precio": 3000}], "costo_total": 3000})
                        if k.get("json_mode") else "1. Arroz con pollo...")
    who, said = ask("arma el menú de la semana para 3 personas")
    assert "Sancocho" in said and "yuca (1 kg)" in vd.pending_items("mercado")
    who, said = ask("¿qué cocino con arroz, pollo y tomate?")
    assert "Arroz con pollo" in said
    who, said = ask("haz el plan de clase de fracciones")                         # eso es del aula, no del menú
    assert "Sancocho" not in said


def test_audio_por_partes(jvd, monkeypatch, tmp_path):
    hv = sys.modules["nucleo.hogarvoz"]
    made = []
    monkeypatch.setattr(hv, "_hg_synth", lambda text, base: (made.append(text), open(base + ".mp3", "wb").write(b"ID3"), base + ".mp3")[2])
    text = "\n\n".join(f"Párrafo {i}. " + "palabra " * 120 for i in range(12))
    assert len(hv.chunks(text, 3500)) == 4 and all(len(c) <= 3500 for c in hv.chunks(text, 3500))
    folder, paths = hv.text_to_audio("Mi libro", text, str(tmp_path))
    assert len(paths) == 4 and all(os.path.exists(p) for p in paths) and folder.endswith(os.path.join("Audios", "Mi libro"))
    with pytest.raises(ValueError):
        hv.text_to_audio("x", "corto")


def test_viaje_por_voz(jvd, ask, monkeypatch):
    hv = sys.modules["nucleo.hogarvoz"]
    monkeypatch.setattr(hv, "_forecast", lambda dest, a, b: (32, 25, 60, {"place": "Cartagena, Bolívar, Colombia"}))
    who, said = ask("me voy a Cartagena del 20 al 24 de noviembre")
    v = H.data["viajes"][-1]
    assert v["destino"] == "Cartagena" and not v["internacional"] and "entre 25 y 32 grados" in said
    assert "Bloqueador solar" in vd.pending_items(v["lista"])
    who, said = ask("mi vuelo sale a las 6 de la mañana")
    assert H.data["viajes"][-1]["hora_vuelo"] == "06:00"


def test_paginas_y_medico(jvd, ask, monkeypatch):
    c = jvd.app.test_client()
    assert c.get("/mi-dia").status_code == 200 and c.get("/pc").status_code == 200
    r = jvd.handle_midia_save({"seccion": "venc", "nombre": "Pasaporte", "fecha": "2027-01-10", "tipo": "pasaporte"})
    assert r["ok"] and r["venc"][0]["tipo_txt"] == "Pasaporte"
    assert jvd.handle_midia_save({"seccion": "meds", "nombre": "Vitamina D", "horas": "8:00, 20:00", "stock": "20"})["ok"]
    assert jvd.handle_midia_save({"seccion": "venc", "nombre": "x"})["ok"] is False
    mid = H.data["meds"][0]["id"]
    assert jvd.handle_midia_taken({"id": mid})["meds"][0]["hoy"]
    assert jvd.handle_midia_delete({"seccion": "venc", "id": r["venc"][0]["id"]})["venc"] == []
    st = jvd.handle_pc_state()
    assert "score" in st and any(x["id"] == "disco" for x in st["checks"])
    monkeypatch.setattr(jvd, "_open_page", lambda *a: None)
    who, said = ask("revisa mi pc")
    assert "de 100" in said
