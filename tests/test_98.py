"""Pruebas de la 9.8: semana lista el domingo, cierre de periodo y bandeja limpia."""
import datetime
import json
import os
import threading
import time

import pytest

import compromisos
import diarioclase
import horario
import semana
import seguimiento

HOR = [{"dia": 0, "inicio": "07:00", "fin": "07:55", "curso": "7A", "materia": "Matemáticas"},
       {"dia": 2, "inicio": "08:00", "fin": "08:55", "curso": "7A", "materia": "Matemáticas"},
       {"dia": 1, "inicio": "09:00", "fin": "09:55", "curso": "9B", "materia": "Física"},
       {"dia": 5, "inicio": "09:00", "fin": "09:55", "curso": "11", "materia": "Química"}]


def _wait_approvals():
    for _ in range(150):
        if not any(t.name.startswith("aprobacion") and t.is_alive() for t in threading.enumerate()):
            return
        time.sleep(0.02)


@pytest.fixture
def prof(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(horario, "items", list(HOR))
    monkeypatch.setattr(diarioclase, "_path", str(tmp_path / "r.json"))
    monkeypatch.setattr(diarioclase, "data", {"registro": {}, "mallas": {}})
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "notas.json"))
    monkeypatch.setattr(seguimiento, "data", {"7A": {"Ana Gómez": [{"actividad": "q", "nota": 4.5, "fecha": "2026-10-01", "origen": "voz"}],
                                                     "Luis Rojas": [{"actividad": "q", "nota": 2.0, "fecha": "2026-10-01", "origen": "voz"}]}})
    monkeypatch.setattr(compromisos, "_path", str(tmp_path / "c.json"))
    monkeypatch.setattr(compromisos, "data", {"items": [], "respondidos": [], "descartados": []})
    monkeypatch.setitem(jv.aula.data, "cursos", {"7A": ["Ana Gómez", "Luis Rojas", "Eva Díaz"]})
    monkeypatch.setitem(jv.aula.data, "asistencia", {})
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "out"))
    for k in ("week_prep_last", "period_end", "period_closed", "period_warned", "inbox_last", "period_name"):
        monkeypatch.setitem(jv.settings, k, "")
    return tmp_path


def test_plan_de_semana_puro():
    topics = {"7A": "Fracciones", "9B": ""}
    plan, sin = semana.week_plan(HOR, lambda c: topics.get(c, ""), datetime.date(2026, 11, 2))
    assert sin == ["9B"] and plan["nombre"] == "Semana del 02/11"
    assert [p["tipo"] for p in plan["pasos"]] == ["plan", "quiz"]
    assert "2 sesiones" in plan["pasos"][0]["pedido"] and "lunes, miércoles" in plan["pasos"][0]["pedido"]
    assert plan["pasos"][1]["depende"] == [plan["pasos"][0]["id"]]
    many = [{"dia": i % 5, "inicio": "07:00", "fin": "08:00", "curso": f"{6 + i}A", "materia": "M"} for i in range(6)]
    plan, _ = semana.week_plan(many, lambda c: "tema", datetime.date(2026, 11, 2))
    assert len(plan["pasos"]) == 8 and sum(p["tipo"] == "plan" for p in plan["pasos"]) == 6


def test_fechas():
    hoy = datetime.date(2026, 10, 31)
    assert semana.parse_date("el 28 de noviembre", hoy) == datetime.date(2026, 11, 28)
    assert semana.parse_date("28/11", hoy) == datetime.date(2026, 11, 28)
    assert semana.parse_date("15 de febrero", hoy) == datetime.date(2027, 2, 15)
    assert semana.parse_date("2026-12-04", hoy) == datetime.date(2026, 12, 4)
    assert semana.parse_date("pronto", hoy) is None
    assert semana.next_monday(hoy) == datetime.date(2026, 11, 2)
    assert semana.days_left("2026-11-07", hoy) == 7


def test_semana_lista_el_domingo(jv, prof, monkeypatch):
    diarioclase.set_malla("7A", {"semanas": [{"semana": 1, "tema": "Números enteros"}, {"semana": 2, "tema": "Fracciones"}]})
    diarioclase.add("7A", "Números enteros")
    diarioclase.add("9B", "Movimiento rectilíneo")
    ran = []
    monkeypatch.setattr(jv, "run_project", lambda st: ran.append(st))
    assert jv.week_prep_tick(datetime.datetime(2026, 11, 7, 18)) is None           # sábado: no
    plan = jv.week_prep_tick(datetime.datetime(2026, 11, 8, 18))                    # domingo
    titles = [p["titulo"] for p in plan["pasos"]]
    assert "Plan de clase 7A: Fracciones" in titles and any("continuación de Movimiento" in x for x in titles)
    assert jv.week_prep_tick(datetime.datetime(2026, 11, 8, 19)) is None           # una vez
    assert jv.aprobaciones.latest()["titulo"].startswith("Preparar la semana del 09/11")
    jv.process_command("sí")
    _wait_approvals()
    assert ran and ran[0]["nombre"] == "Semana del 09/11" and len(ran[0]["pasos"]) == 4


def test_semana_sin_horario_ni_temas(jv, prof, monkeypatch):
    monkeypatch.setattr(horario, "items", [])
    jv._rec.clear()
    jv.process_command("prepárame la semana")
    assert "horario" in jv._rec.said()
    monkeypatch.setattr(horario, "items", list(HOR))
    jv._rec.clear()
    jv.process_command("prepárame la semana")
    assert "malla" in jv._rec.said()


def test_cierre_de_periodo(jv, prof, monkeypatch):
    monkeypatch.setattr(jv, "_open_doc", lambda p: False)
    jv._rec.clear()
    jv.process_command("el periodo termina el 28 de noviembre")
    assert jv.settings["period_end"].endswith("-11-28") and "28 de noviembre" in jv._rec.said()
    end = datetime.date.fromisoformat(jv.settings["period_end"])
    notices = []
    monkeypatch.setattr(jv, "notice_add", lambda text, kind="info", origin="": notices.append(text))
    assert jv.period_tick(end - datetime.timedelta(days=8)) is None
    assert jv.period_tick(end - datetime.timedelta(days=7)) == "aviso"
    assert "Faltan 7 días" in notices[-1] and "1 en riesgo" in notices[-1] and "1 sin notas" in notices[-1]
    assert jv.period_tick(end) == "cierre"
    jv._rec.clear()
    jv.process_command("sí")
    _wait_approvals()
    out = os.path.join(jv.settings["output_dir"])
    files = [f for _, _, fs in os.walk(out) for f in fs]
    assert any(f.endswith(".docx") and "Cierre" in f for f in files) and any(f.endswith(".xlsx") for f in files)
    assert jv.settings["period_closed"] == jv.settings["period_end"]
    assert jv.settings["zeti_since"] == (end + datetime.timedelta(days=1)).isoformat()
    assert "recuperación de 7A" in jv._rec.said()
    assert jv.period_tick(end) is None                                              # ya cerrado


def test_cuanto_falta(jv, prof):
    jv.settings["period_end"] = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
    jv._rec.clear()
    jv.process_command("¿cuánto falta para cerrar el periodo?")
    assert "Faltan 10 días" in jv._rec.said() and "7A" in jv._rec.said()


MAILS = [{"de": "coord@colegio.edu.co", "de_nombre": "Coordinadora", "asunto": "¿Puedes enviar las notas?", "texto":
          "Profe, ¿me puedes enviar las notas de 7A antes del viernes? Quedo atenta.", "fecha": "2026-10-30", "msgid": "<a1>",
          "masivo": False},
         {"de": "noticias@tienda.com", "de_nombre": "Tienda", "asunto": "Ofertas", "texto": "Compra ya", "fecha": "2026-10-30",
          "msgid": "<a2>", "masivo": True}]


def test_bandeja_limpia(jv, prof, monkeypatch):
    monkeypatch.setitem(jv.state, "ai", "ok")
    monkeypatch.setitem(jv.settings, "email_read", True)
    monkeypatch.setattr(jv, "mail_method", lambda: "google")
    monkeypatch.setattr(jv, "_mail_fetch", lambda force=False: list(MAILS))
    monkeypatch.setattr(jv, "is_offline", lambda: False)
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps({"cuerpo": "Hola, claro: se las envío el [día]. Saludos."}))
    sent = []
    monkeypatch.setattr(jv, "mail_send", lambda to, asunto, cuerpo, in_reply_to="": sent.append((to, asunto, cuerpo)) or "gmail")
    monkeypatch.setattr(jv, "learn_style", lambda *a, **k: None)
    assert jv.inbox_tick(datetime.datetime(2026, 11, 2, 5)) is None                 # antes de la hora
    jv._rec.clear()
    n = jv.inbox_tick(datetime.datetime(2026, 11, 2, 7))
    assert n == 1 and jv._rec.said() == ""                                          # en silencio: queda por aprobar
    a = jv.aprobaciones.latest()
    assert a["titulo"].startswith("Responder a Coordinadora") and "[día]" in a["detalle"]
    assert jv.inbox_tick(datetime.datetime(2026, 11, 2, 8)) is None                 # una vez al día
    assert jv.inbox_drafts() == 0                                                   # no repite la que ya espera
    jv.process_command("sí")
    _wait_approvals()
    assert sent and sent[0][0] == "coord@colegio.edu.co" and sent[0][1].startswith("Re:")
    assert compromisos.to_answer(MAILS, "") == []


def test_bandeja_por_voz_sin_correo(jv, prof, monkeypatch):
    monkeypatch.setattr(jv, "mail_method", lambda: "")
    jv._rec.clear()
    jv.process_command("limpia mi bandeja")
    assert "correo conectado" in jv._rec.said()
