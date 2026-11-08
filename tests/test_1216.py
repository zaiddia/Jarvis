"""Pruebas de la 12.16: guía, Telegram con archivos, cumpleaños de Google, inicio unificado, autoprueba, compartir, resumen del mes y no molestar."""
import datetime as dt
import json
import sys
import time

import pytest

import guia
import hogar as H
import vidadiaria as vd

D = dt.date


@pytest.fixture
def base(jv, tmp_path, monkeypatch):
    import adjuntos
    H.configure(str(tmp_path))
    vd.configure(str(tmp_path))
    adjuntos.configure(str(tmp_path))
    adjuntos.items.clear()
    sent = []
    monkeypatch.setattr(jv, "telegram_send", lambda text, chat=None: sent.append(text) or True)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    monkeypatch.setattr(jv, "notify", lambda msg, origin="": jv._rec.replies.append((msg, origin)))
    jv.dnd.update(until=0.0, queue=[], was="")
    yield jv, sent
    for k, v in H.KEYS.items():
        H.data[k] = v.copy()
    jv.dnd.update(until=0.0, queue=[], was="")
    adjuntos.items.clear()


# ============================================================================ 1. GUÍA
def test_guia_y_busqueda(jv, ask, monkeypatch):
    g = guia.build(jv.CAPABILITIES)
    ids = [c["id"] for c in g]
    assert {"colegio", "pc", "dia", "dinero"} <= set(ids) and guia.count(g) > 150
    names = [x["nombre"] for c in g for x in c["grupos"]]
    assert len(names) == len(set(names))
    assert guia.category_of("Medicamentos (12.15)") == "dia" and guia.category_of("Gastos y pagos (12.9)") == "dinero"
    hits = guia.search(g, "el presupuesto")
    assert hits and "Presupuesto" in hits[0][1]["nombre"] and "«mi presupuesto de comida es de 800 mil»" in guia.spoken(hits)
    who, said = ask("¿qué puedes hacer con los medicamentos?")
    assert "losartán" in said
    pages = []
    monkeypatch.setattr(jv, "_open_page", lambda path, title, holder: pages.append(path))
    ask("abre la guía")
    assert pages == ["/guia"] and jv.app.test_client().get("/guia").status_code == 200
    run = []
    monkeypatch.setattr(jv, "submit_command", lambda cmd, src: run.append(cmd))
    assert jv.handle_guide_try({"cmd": "volumen al 30"})["ok"] and run == ["volumen al 30"]
    assert not jv.handle_guide_try({"cmd": "(sube la foto…)"})["ok"]


# ============================================================================ 2. TELEGRAM CON ARCHIVOS
def test_telegram_fotos_y_archivos(base, monkeypatch):
    jv, sent = base
    monkeypatch.setitem(jv.settings, "telegram_chat", "42")
    monkeypatch.setattr(jv, "_tg_file", lambda fid: b"ALKOSTO TOTAL 50.000")
    done = []
    monkeypatch.setattr(jv, "receipt_from", lambda it: done.append(("recibo", it["nombre"])) or "Anoté $50.000.")
    monkeypatch.setattr(jv, "audio_from_item", lambda it: done.append(("audio", it["nombre"])))
    msg = {"chat": {"id": 42}, "document": {"file_id": "x", "file_name": "factura.txt", "file_size": 20}, "caption": "recibo"}
    assert jv.tg_file_in(msg) and done == [("recibo", "factura.txt")] and "Anoté $50.000." in sent
    sent.clear()
    msg = {"chat": {"id": 42}, "document": {"file_id": "y", "file_name": "lectura.txt", "file_size": 20}}
    assert jv.tg_file_in(msg) and "¿Qué hago?" in sent[-1]
    assert not jv.tg_pending_answer("no sé qué decirte de esto ahora mismo")
    assert jv.tg_pending_answer("audio") and done[-1] == ("audio", "lectura.txt")
    assert not jv.tg_pending_answer("audio")                                      # ya se usó
    assert jv.tg_file_in({"chat": {"id": 42}, "document": {"file_id": "z", "file_name": "grande.pdf", "file_size": 30_000_000}})
    assert "muy grande" in sent[-1]
    assert jv.tg_file_in({"chat": {"id": 42}, "text": "", "photo": [{"file_id": "a", "width": 90}, {"file_id": "b", "width": 900}], "caption": "esto es un gasto"})
    assert done[-1][0] == "recibo" and done[-1][1].startswith("foto_")
    assert not jv.tg_file_in({"chat": {"id": 42}, "text": "hola"})


# ============================================================================ 3. CUMPLEAÑOS DESDE GOOGLE
def test_cumpleanos_de_google(base, monkeypatch, ask):
    jv, _ = base
    conns = [{"names": [{"displayName": "Ana Gómez"}], "birthdays": [{"date": {"month": 5, "day": 3, "year": 1990}}]},
             {"names": [{"displayName": "Luis"}], "birthdays": [{"date": {"month": 12, "day": 24}}]},
             {"names": [{"displayName": "Sin fecha"}]}]
    assert jv.parse_birthdays(conns) == [("Ana Gómez", 5, 3, 1990), ("Luis", 12, 24, None)]
    monkeypatch.setattr(jv, "classroom_client", lambda: None)
    assert "conecta tu cuenta de Google" in jv.import_birthdays()

    class C:
        def call(self, method, path, params=None, body=None, base=None):
            assert path == "people/me/connections" and base.startswith("https://people.googleapis.com")
            return {"connections": conns}
    monkeypatch.setattr(jv, "classroom_client", lambda: C())
    monkeypatch.setitem(jv.settings, "google_scopes", "calendar")
    assert "permiso nuevo" in jv.import_birthdays()
    monkeypatch.setitem(jv.settings, "google_scopes", "https://www.googleapis.com/auth/contacts.readonly")
    who, said = ask("importa los cumpleaños de mis contactos")
    assert "Traje 2 cumpleaños" in said and H.find("cumples", "ana gomez")["anio"] == 1990
    import classroom
    assert "https://www.googleapis.com/auth/contacts.readonly" in classroom.SCOPES


# ============================================================================ 4. INICIO UNIFICADO
def test_mi_dia_en_el_panel_hoy(base):
    jv, _ = base
    now = dt.datetime.now()
    H.venc_add("soat", now.date() + dt.timedelta(days=4))
    H.med_add("Losartán", ["00:00", "23:59"])
    H.budget_set("Comida", 100_000)
    vd.add_expense(90_000, "mercado")
    d = jv.midia_dash(now)
    assert d["venc"][0]["n"] == 4 and d["toma"]["t"] == "Losartán" and d["presupuesto"] == {"cat": "Comida", "pct": 90}
    assert "midia" in jv.dashboard(now)


# ============================================================================ 5. AUTOPRUEBA
def test_autoprueba(base, ask, monkeypatch):
    jv, _ = base
    items = jv.features_check()
    assert items and all(i["grupo"] == "Funciones nuevas (autoprueba)" and i["estado"] in ("ok", "aviso", "fallo", "info") for i in items)
    assert any("generador de documentos" in i["texto"] for i in items)
    assert any(i["grupo"] == "Funciones nuevas (autoprueba)" for i in jv.system_check())
    monkeypatch.setattr(jv, "open_health_panel", lambda: None)
    who, said = ask("haz la autoprueba")
    assert said.startswith("Autoprueba:")


# ============================================================================ 6. COMPARTIR CON LA FAMILIA
def test_compartir_con_aprobacion(base, ask, monkeypatch):
    jv, _ = base
    asked = []
    monkeypatch.setattr(jv, "request_approval", lambda *a, **k: asked.append((a, k)))
    monkeypatch.setattr(jv.skills, "resolve_contact", lambda who: "+573001112233" if "esposa" in who or "hermana" in who else None)
    vd.add_items("mercado", ["leche", "pan"])
    who, said = ask("mándale la lista del mercado a mi esposa")
    (a, k) = asked[-1]
    assert "WhatsApp a esposa" in a[1] and "• leche" in a[2] and "¿Lo envío?" in k["say"]
    sent = []
    monkeypatch.setattr(jv, "run_skill", lambda name, args, confirmed=False: sent.append((name, args)))
    k["on_ok"]()
    assert sent == [("whatsapp", {"contacto": "esposa", "mensaje": a[2]})]
    H.cumple_add("Mamá", 5, 3)
    ask("avísale a mi hermana del cumpleaños de mamá")
    assert "Mamá cumple" in asked[-1][0][2]
    who, said = ask("mándale el menú a mi tía")
    assert "Aún no hay menú" in said
    H.data["comidas"] = {"dias": [{"dia": "Lunes", "almuerzo": "Sancocho", "cena": ""}]}
    who, said = ask("mándale el menú a mi tía")
    assert "No tengo a «tía»" in said or "No tengo a «tia»" in said
    n = len(asked)
    jv._rec.clear()
    ask("pasa la lista de esta foto a excel")                                    # no es para una persona
    assert len(asked) == n


# ============================================================================ 7. RESUMEN DEL MES
def test_resumen_del_mes(base, ask):
    jv, _ = base
    vd.data["gastos"] += [{"id": "a", "fecha": "2026-10-03", "monto": 600000, "concepto": "mercado", "categoria": "Comida"},
                          {"id": "b", "fecha": "2026-10-10", "monto": 80000, "concepto": "taxi", "categoria": "Transporte"}]
    H.budget_set("Comida", 500000)
    H.venc_add("Pasaporte", D(2026, 10, 20))
    H.cumple_add("Ana", 11, 10)
    s = jv.month_summary(D(2026, 10, 15), D(2026, 11, 1))
    assert "En octubre gastaste $680.000" in s and "Te pasaste del presupuesto en Comida" in s and "Pasaporte" in s and "cumple Ana el 10" in s
    who, said = ask("resumen del mes pasado")
    assert "gastaste" in said or "No anotaste" in said


# ============================================================================ 8. NO MOLESTAR
def test_no_molestar(base, ask, monkeypatch):
    jv, sent = base
    spoken = []
    monkeypatch.setattr(jv, "reply", lambda text, origin="": spoken.append(text))
    monkeypatch.setattr(jv, "card", lambda *a, **k: None)
    monkeypatch.setitem(jv.settings, "telegram_token", "t")
    monkeypatch.setitem(jv.settings, "telegram_chat", "42")
    real_notify = sys.modules["nucleo.vivo"].notify
    assert jv.dnd_reason() == ""
    jv.process_command("no me molestes por 2 horas")
    assert jv.dnd_reason() == "no molestar" and jv.dnd["until"] > time.time() + 7000
    spoken.clear()
    real_notify("Listo el audio de «Libro».", "AUDIO")
    real_notify("Es hora de tomar Losartán.", "MEDICAMENTOS")
    assert spoken == [] and len(jv.dnd["queue"]) == 1
    for _ in range(50):
        if any("Losartán" in s for s in sent):
            break
        time.sleep(0.02)
    assert any("Losartán" in s for s in sent)                                      # crítico: en silencio al celular
    assert jv.dnd_status()["guardados"] == 1
    jv.process_command("ya puedes hablar")
    assert jv.dnd_reason() == "" and any("Listo el audio" in s for s in spoken) and jv.dnd["queue"] == []
    monkeypatch.setattr(jv, "_foreground_title", lambda: "Reunión de Zoom")
    assert jv.dnd_reason() == "videollamada"
    monkeypatch.setitem(jv.settings, "dnd_auto", False)
    assert jv.dnd_reason() == ""
    monkeypatch.setitem(jv.settings, "dnd_auto", True)
    monkeypatch.setattr(jv, "_foreground_title", lambda: "Documento1 - Word")
    assert jv.dnd_reason() == ""


def test_contrasena_de_aplicacion_limpia(jv):
    clean = sys.modules["nucleo.gcorreo"].clean_app_password
    assert clean("abcd efgh ijkl mnop") == "abcdefghijklmnop"
    assert clean("abcd-efgh-ijkl-mnop") == "abcdefghijklmnop" and clean("abcdefghijklmnop.") == "abcdefghijklmnop"
    assert clean("​abcd efgh ijkl mnop﻿") == "abcdefghijklmnop" and clean("«abcdefghijklmnop»") == "abcdefghijklmnop"
    assert clean("MiClaveNormal2024!") == "MiClaveNormal2024!"                    # una clave normal no se «arregla»
    r = jv.email_test("ana@gmail.com", "MiClaveNormal2024!")
    assert not r["ok"] and "sin números" in r["msg"]


def test_copia_en_drive_sin_google_explica_que_falta(jv, monkeypatch):
    import classroom
    import gservicios
    monkeypatch.setattr(jv, "classroom_client", lambda: None)
    r = jv.handle_cloud_backup({"action": "listar"})
    assert r["ok"] is False and "Conectar con Google" in r["error"] and "NoneType" not in r["error"]
    assert jv.handle_cloud_backup({"action": "ahora"})["ok"] is False
    with pytest.raises(classroom.ClassroomError, match="Conectar con Google"):
        gservicios.ensure_folder(None, "")
    with pytest.raises(classroom.ClassroomError):
        jv.backup_to_drive("x.zip")
