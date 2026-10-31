"""Pruebas de la 11.1: entregas de programación revisadas por la IA (sin ejecutar nada) y el reto de la semana."""
import base64
import datetime
import io
import json
import threading
import time

import pytest

import entregas
import practica
import retos
import seguimiento


def _wait_approvals():
    for _ in range(150):
        if not any(t.name.startswith("aprobacion") and t.is_alive() for t in threading.enumerate()):
            return
        time.sleep(0.02)


REV = {"funciona": False, "bien": ["Lees bien el número"], "errores": [{"donde": "línea 3", "que": "el if compara con 1 en vez de 0"}],
       "pista": "¿Qué residuo deja un número par al dividir entre 2?", "nota": 3.4, "para_docente": "Casi"}


@pytest.fixture
def tec(jv, monkeypatch, tmp_path):
    for mod, val in ((entregas, {"tareas": {}}), (practica, {"cursos": {}}), (retos, {"retos": {}, "puntos": {}})):
        monkeypatch.setattr(mod, "_path", str(tmp_path / (mod.__name__ + ".json")))
        monkeypatch.setattr(mod, "data", val)
    monkeypatch.setattr(seguimiento, "_path", str(tmp_path / "n.json"))
    monkeypatch.setattr(seguimiento, "data", {})
    monkeypatch.setitem(jv.aula.data, "cursos", {"8A": ["Ana Gómez", "Luis Rojas", "Eva Díaz"]})
    monkeypatch.setitem(jv.aula.data, "activo", "8A")
    monkeypatch.setitem(jv.settings, "course_subjects", "")
    monkeypatch.setattr(jv.horario, "items", [])
    monkeypatch.setitem(jv.mobile, "server", object())
    monkeypatch.setattr(jv, "_open_projector", lambda: None)
    monkeypatch.setitem(jv.state, "ai", "ok")
    jv.es.update(code="", tid="", tokens={})
    return tmp_path


def test_entregas_de_programacion(jv, tec, monkeypatch):
    seen = []
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: seen.append(msgs[0]["content"]) or json.dumps(REV))
    jv._rec.clear()
    jv.process_command("recibe los programas de 8A, la tarea es: un programa que diga si un número es par")
    assert jv.es["code"] and "Nunca ejecuto su código" in jv._rec.said()
    c = jv.mobile_app.test_client()
    base = f"/e/{jv.es['code']}"
    assert c.get("/e/otro").status_code == 404 and c.get(base).status_code == 200
    d = c.get(base + "/lista").get_json()
    assert d["consigna"].startswith("un programa que diga") and "Python" in d["lenguajes"]
    k = c.post(base + "/entrar", json={"nombre": "Ana Gómez", "pin": "1234"}).get_json()["k"]
    assert not c.post(base + "/enviar", json={"k": k, "lenguaje": "Python", "codigo": "x"}).get_json()["ok"]        # vacío
    code = "n = int(input())\nif n % 2 == 1:\n    print('par')\n"
    r = c.post(base + "/enviar", json={"k": k, "lenguaje": "Python", "codigo": code}).get_json()
    assert r["ok"] and r["revisado"] and not r["funciona"] and "residuo" in r["pista"] and r["quedan"] == 2 and "nota" not in r   # la nota no la ve
    assert "NO ejecutes nada" in seen[0] and "un número es par" in seen[0] and code.strip() in seen[0]
    # si la IA intenta darle la solución, la pista se cambia
    leak = dict(REV, pista="Así:\n```\nif n % 2 == 0:\n    print('par')\n```")
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps(dict(leak, nota=4.5, funciona=True)))
    r = c.post(base + "/enviar", json={"k": k, "lenguaje": "Python", "codigo": code.replace("== 1", "== 0")}).get_json()
    assert "```" not in r["pista"] and "línea por línea" in r["pista"]
    jv._rec.clear()
    jv.process_command("¿cómo van las entregas?")
    assert "1 de 3" in jv._rec.said() and "Luis Rojas" in jv._rec.said()
    jv.process_command("cierra las entregas")
    assert not jv.es["code"] and c.get(base).status_code == 404
    jv.process_command("anota las entregas")
    a = jv.aprobaciones.latest()
    assert "1 estudiantes, en Hacer" in a["titulo"] and "4,5" in a["detalle"]                                      # la mejor de sus entregas
    jv.process_command("sí")
    _wait_approvals()
    n = seguimiento.data["8A"]["Ana Gómez"][-1]
    assert n["nota"] == 4.5 and n["dim"] == "hacer" and n["actividad"].startswith("Programa:")


def test_entrega_con_foto(jv, tec, monkeypatch):
    monkeypatch.setattr(jv, "_vision_cfg", lambda: ({"kind": "cloud"}, ""))
    monkeypatch.setattr(jv, "_need_key", lambda c: None)
    got = {}
    monkeypatch.setattr(jv, "_with_fallback", lambda cfg, fn: got.setdefault("x", 1) and json.dumps(dict(REV, funciona=True)))
    jv.process_command("recibe los programas de 8A")
    c = jv.mobile_app.test_client()
    base = f"/e/{jv.es['code']}"
    k = c.post(base + "/entrar", json={"nombre": "Luis Rojas", "pin": "5555"}).get_json()["k"]
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, "JPEG")
    r = c.post(base + "/enviar", json={"k": k, "lenguaje": "Scratch (foto)", "foto": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}).get_json()
    assert r["ok"] and r["funciona"] and got


RETO = {"tema": "Fracciones", "preguntas": [{"nivel": n, "enunciado": f"P{i}", "opciones": ["1", "2", "3", "4"], "respuesta": "b", "explicacion": "e"}
                                            for i, n in enumerate(("Bronce", "Plata", "Oro"))]}


def test_reto_puntos_e_insignias():
    retos.data = {"retos": {}, "puntos": {}}
    retos._path = None
    w = [datetime.date(2026, 10, 12) + datetime.timedelta(weeks=i) for i in range(3)]
    for i, day in enumerate(w):
        retos.open_challenge("7A", f"c{i}", retos.clean(RETO), today=day)
        retos.answer("7A", "Ana", 0, 1)
        retos.answer("7A", "Ana", 1, 1)
        retos.answer("7A", "Ana", 2, 1)                     # todo a la primera
        retos.answer("7A", "Luis", 0, 0)
        retos.answer("7A", "Luis", 0, 1)                    # segundo intento: mitad
        res = retos.close("7A")
    top = res[0]
    assert top[0] == "Ana" and top[1] == 3 + 2 + 1 + 1 + 1        # 6 por las tres + 1 por ser la primera + 1 por racha de 3
    assert "🔥 Racha 3" in top[2]
    rk = retos.ranking("7A")
    assert rk[0]["nombre"] == "Ana" and rk[0]["total"] == 22 and "🥇 Oro" in rk[0]["insignias"] and "💯 Perfecto" in rk[0]["insignias"]
    assert rk[1] == {"nombre": "Luis", "total": 1.5, "insignias": ["🔥 Racha 3"]} or rk[1]["total"] == 2.5


def test_reto_por_voz_y_celular(jv, tec, monkeypatch):
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps(RETO))
    monkeypatch.setattr("webbrowser.open", lambda *a, **k: None)
    jv._rec.clear()
    jv.process_command("lanza el reto de la semana para 8A sobre fracciones")
    for _ in range(200):
        if "8A" in retos.data["retos"]:
            break
        time.sleep(0.02)
    r = retos.data["retos"]["8A"]
    c = jv.mobile_app.test_client()
    base = f"/r/{r['code']}"
    assert c.get(base).status_code == 200 and c.get(base + "/lista").get_json()["tema"] == "Fracciones"
    e = c.post(base + "/entrar", json={"nombre": "Eva Díaz", "pin": "9090"}).get_json()
    assert e["ok"] and len(e["preguntas"]) == 3 and "respuesta" not in json.dumps(e["preguntas"])
    x = c.post(base + "/responder", json={"k": e["k"], "q": 2, "opcion": 0}).get_json()
    assert not x["correcto"] and not x["fin"] and x["preguntas"][2]["estado"] == "uno"
    for q in range(3):
        x = c.post(base + "/responder", json={"k": e["k"], "q": q, "opcion": 1}).get_json()
    assert x["correcto"] and "primero" in x["msg"]
    jv._rec.clear()
    jv.process_command("cierra el reto de 8A")
    assert "participaron 1" in jv._rec.said() and "Eva Díaz" in jv._rec.said()
    assert c.get(base).status_code == 404
    page = jv.app.test_client().get("/ranking/8A").get_data(as_text=True)
    assert "Eva Díaz" in page and "🥇" in page
    jv._rec.clear()
    jv.process_command("muestra el ranking de 8A")
    assert "1. Eva Díaz" in jv._rec.said()
