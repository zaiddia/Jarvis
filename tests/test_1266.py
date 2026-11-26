"""Pruebas de la 12.66: reclamos, extracto, deudas, «¿esto es verdad?», exámenes de laboratorio y profesor de inglés."""
import datetime

import vidapractica as G


# ---------------------------------------------------------------- reclamos (puro)
def test_plazo_en_dias_habiles():
    hol = {datetime.date(2026, 12, 8), datetime.date(2026, 12, 25), datetime.date(2027, 1, 1), datetime.date(2027, 1, 11)}
    # radicado el viernes 27 de noviembre de 2026: 15 días hábiles sin el 8 de diciembre
    assert G.business_deadline(datetime.date(2026, 11, 27), 15, hol) == datetime.date(2026, 12, 21)
    assert G.business_deadline(datetime.date(2026, 12, 18), 3, hol) == datetime.date(2026, 12, 23)


def test_sector():
    assert G.sector_of("EPS Sura no me autoriza la resonancia")[0] == "salud"
    assert G.sector_of("Claro me cobró de más")[0] == "telecom" and "silencio administrativo" in G.sector_of("claro")[2]
    assert G.sector_of("EPM me facturó mal la luz")[0] == "servicios"
    assert G.sector_of("Bancolombia")[0] == "banco"
    assert G.sector_of("la tienda no me cambió el televisor")[0] == "consumo"
    assert "1755 de 2015" in G.letter_prompt("peticion", "Claro", "me cobraron")


def test_reclamo_por_voz(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    prompts = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: (prompts.append(msgs[-1]["content"]), "DERECHO DE PETICIÓN\nHECHOS\n1. …")[1])
    jv._rec.clear()
    jv.process_command("haz un derecho de petición a la EPS Sura porque no me autorizan la resonancia magnética")
    assert "no me autorizan la resonancia magnética" in prompts[-1] and "Sura" in prompts[-1]
    assert "tutela" in jv._rec.said() and list((tmp_path / "Reclamos").iterdir())
    jv._rec.clear()
    jv.process_command("ya radiqué el reclamo de la EPS Sura")
    r = jv.g66_data()["reclamos"][0]
    assert r["radicado"] == str(datetime.date.today()) and r["vence"] > r["radicado"]
    jv._rec.clear()
    jv.general66_tick(datetime.datetime.fromisoformat(r["vence"]) + datetime.timedelta(days=1, hours=10))
    assert "Supersalud" in jv._rec.said()
    jv._rec.clear()
    jv.general66_tick(datetime.datetime.fromisoformat(r["vence"]) + datetime.timedelta(days=2, hours=10))
    assert not jv._rec.said()                                                   # una sola vez
    jv.process_command("me respondieron el reclamo de la EPS Sura")
    assert jv.g66_data()["reclamos"][0]["respondido"]
    jv._rec.clear()
    jv.process_command("mis reclamos")
    assert "No tienes reclamos abiertos" in jv._rec.said()


# ---------------------------------------------------------------- deudas
def test_simulacion():
    debts = [{"nombre": "Tarjeta", "saldo": 3_000_000, "tasa": 0.021, "cuota": 250_000},
             {"nombre": "Libranza", "saldo": 1_000_000, "tasa": 0.012, "cuota": 100_000}]
    av = G.simulate(debts, extra=300_000, strategy="avalancha")
    sb = G.simulate(debts, extra=300_000, strategy="bola de nieve")
    assert not av["imposible"] and av["meses"] and av["intereses"] <= sb["intereses"]
    assert av["orden"][0][0] == "Tarjeta" and sb["orden"][0][0] == "Libranza"
    fast = G.simulate(debts, extra=300_000, lump=2_000_000)
    assert fast["meses"] < av["meses"] and fast["intereses"] < av["intereses"]
    assert G.simulate([{"nombre": "x", "saldo": 10_000_000, "tasa": 0.03, "cuota": 100_000}])["imposible"]
    assert abs(G.monthly_rate(28, "ea") - 0.0208) < 0.0003


def test_deudas_por_voz(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    d = jv.debt_parse("tarjeta exito 3 millones al 2,1 % mensual, cuota de 250 mil")
    assert d["saldo"] == 3_000_000 and abs(d["tasa"] - 0.021) < 1e-9 and d["cuota"] == 250_000
    assert jv.debt_parse("credito carro 20 millones al 18% ea cuota 600 mil")["tasa_txt"] == "18 % EA"
    jv._rec.clear()
    jv.process_command("anota una deuda: tarjeta Éxito 3 millones al 2,1 % mensual, cuota de 250 mil")
    jv.process_command("anota una deuda: libranza 1 millón al 1,2 % mensual, cuota de 100 mil")
    jv._rec.clear()
    jv.process_command("mis deudas")
    assert "$4.000.000" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("plan para salir de deudas")
    assert "avalancha" in jv._rec.said() and "prima" in jv._rec.said()
    jv._rec.clear()
    jv.process_command("ya pagué la deuda de la tarjeta éxito")
    assert "Felicidades" in jv._rec.said() and len(jv.g66_data()["deudas"]) == 1


# ---------------------------------------------------------------- «¿esto es verdad?»
def test_verificar(jv, monkeypatch):
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    monkeypatch.setattr(jv, "_web_results", lambda q: [{"titulo": "Falso: no habrá subsidio", "resumen": "ColombiaCheck…",
                                                         "fuente": "colombiacheck.com", "url": "https://x"}])
    seen = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: (seen.append(msgs), "FALSO: no existe ese subsidio.\nPara el grupo: …")[1])
    jv._rec.clear()
    jv.process_command("¿Esto es verdad? El gobierno va a dar un subsidio de 500 mil a todos los que reenvíen este mensaje")
    assert "FALSO" in jv._rec.said() and "colombiacheck.com" in seen[-1][1]["content"] and "neutral" in seen[-1][0]["content"]
    jv._rec.clear()
    jv.process_command("¿esto es verdad?")
    assert "Pégame la cadena" in jv._rec.said() or "FALSO" in jv._rec.said()


# ---------------------------------------------------------------- extracto y laboratorio
def test_botones_y_archivos(jv, monkeypatch):
    assert [a["a"] for a in jv.g66_card_actions([{"tipo": "pdf", "nombre": "Extracto Bancolombia octubre.pdf"}])] == ["extracto"]
    assert [a["a"] for a in jv.g66_card_actions([{"tipo": "imagen", "nombre": "resultado hemograma.jpg"}])] == ["laboratorio"]
    assert jv.g66_card_actions([{"tipo": "pdf", "nombre": "taller.pdf"}]) == []
    asked = []
    monkeypatch.setattr(jv, "ask_files", lambda its, q: (asked.append(q), "RESUMEN: …")[1])
    jv.g66_attach([{"tipo": "pdf", "nombre": "x.pdf"}], "extracto")
    assert "cuota de manejo" in asked[-1]
    jv.g66_attach([{"tipo": "pdf", "nombre": "x.pdf"}], "laboratorio")
    assert "No diagnostiques" in asked[-1] and "RANGO DE REFERENCIA" not in asked[-1].upper().replace("MISMO INFORME", "")[:0]


# ---------------------------------------------------------------- inglés
def test_ingles(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "live_mode", lambda: "vivo")
    started = []
    monkeypatch.setattr(jv, "live_start", lambda initial_audio=None: (started.append(1), True)[1])
    monkeypatch.setitem(jv.g66_tutor, "on", False)
    jv._rec.clear()
    jv.process_command("practiquemos inglés en vivo nivel intermedio sobre viajes")
    assert started and jv.g66_tutor["on"] and jv.g66_tutor["level"] == "intermedio" and jv.g66_tutor["topic"] == "viajes"
    assert "MODO PROFESOR DE INGLÉS" in jv._live_system() and "viajes" in jv._live_system()
    monkeypatch.setattr(jv, "chat_history", [{"role": "user", "content": "I goed to the beach yesterday with my family"},
                                             {"role": "assistant", "content": "You can say: I went to the beach. How was it?"}] * 2)
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: "ERRORES\n- I goed → I went")
    path = jv.g66_tutor_review()
    assert path and path.endswith(".docx") and not jv.g66_tutor["on"]
    assert "MODO PROFESOR" not in jv._live_system()
    monkeypatch.setattr(jv, "live_mode", lambda: "clasico")
    jv._rec.clear()
    jv.process_command("practiquemos inglés en vivo")
    assert "en vivo" in jv._rec.said() and not jv.g66_tutor["on"]
