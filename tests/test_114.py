"""Pruebas de la 11.4: guía viva por QR (con quiz que suma a la ruta) y podcast de repaso con dos voces."""
import json
import os
import time

import pytest

import guiaviva
import practica

GUIA = {"titulo": "Funciones lineales", "bloques": [
    {"tipo": "explicacion", "texto": "Una función lineal es…\nEjemplo: el taxi."},
    {"tipo": "ejemplo", "enunciado": "y = 2x + 1, x = 3", "pasos": ["1) Reemplazar", "2) 2·3 + 1 = 7"], "respuesta": "7"},
    {"tipo": "grafica", "grafica": {"tipo": "funcion", "expr": "2x+1"}, "pie": "La recta"},
    {"tipo": "grafica", "grafica": {"tipo": "funcion", "expr": "import os"}},
    {"tipo": "lab", "nombre": "recta", "texto": "Mueve m"}, {"tipo": "lab", "nombre": "inexistente"},
    {"tipo": "tarjetas", "tarjetas": [{"frente": "¿Pendiente?", "reverso": "m"}]},
    {"tipo": "quiz", "preguntas": [{"enunciado": f"P{i}", "opciones": ["a", "b", "c", "d"], "respuesta": "b", "explicacion": "e"} for i in range(4)]}]}


def _wait(jv, text):
    for _ in range(300):
        if text in jv._rec.said():
            return
        time.sleep(0.02)


@pytest.fixture
def g(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(guiaviva, "_path", str(tmp_path / "g.json"))
    monkeypatch.setattr(guiaviva, "data", {"guias": {}, "podcasts": {}})
    monkeypatch.setattr(practica, "_path", str(tmp_path / "p.json"))
    monkeypatch.setattr(practica, "data", {"cursos": {}})
    monkeypatch.setitem(jv.aula.data, "cursos", {"9A": ["Ana Gómez", "Luis Rojas"]})
    monkeypatch.setitem(jv.settings, "course_subjects", "")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path / "out"))
    monkeypatch.setattr(jv.horario, "items", [])
    monkeypatch.setitem(jv.mobile, "server", object())
    monkeypatch.setattr(jv, "_open_projector", lambda: None)
    monkeypatch.setitem(jv.state, "ai", "ok")
    return tmp_path


def test_guia_limpia():
    import graficas
    gd = guiaviva.clean_guide(GUIA, ["recta"], graficas.clean)
    assert [b["tipo"] for b in gd["bloques"]] == ["explicacion", "ejemplo", "grafica", "lab", "tarjetas", "quiz"]
    pub = guiaviva.public_guide(gd)
    assert "respuesta" not in json.dumps(pub["bloques"][-1]) and "grafica" not in pub["bloques"][2]


def test_guia_viva_completa(jv, g, monkeypatch):
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps(GUIA))
    jv._rec.clear()
    jv.process_command("haz una guía viva de funciones lineales para 9A")
    _wait(jv, "Lista la guía viva")
    assert "explicación, ejemplo resuelto, figura, laboratorio, tarjetas, mini quiz" in jv._rec.said()
    code = next(iter(guiaviva.data["guias"]))
    c = jv.mobile_app.test_client()
    assert c.get(f"/g/{code}").status_code == 200 and c.get("/g/otro").status_code == 404
    d = c.get(f"/g/{code}/datos").get_json()
    assert d["nombres"] == ["Ana Gómez", "Luis Rojas"] and d["bloques"][0]["tipo"] == "explicacion"
    img = c.get(f"/g/{code}/img/2.png")
    assert img.status_code == 200 and img.data[:4] == b"\x89PNG"
    assert c.get("/lab/recta").status_code == 200
    assert not c.post(f"/g/{code}/quiz", json={"k": "x", "respuestas": [1, 1, 1, 1]}).get_json()["ok"]
    k = c.post(f"/g/{code}/entrar", json={"nombre": "Ana Gómez", "pin": "2468"}).get_json()["k"]
    r = c.post(f"/g/{code}/quiz", json={"k": k, "respuestas": [1, 1, 0, 1]}).get_json()
    assert r["aciertos"] == 3 and r["resultados"][2]["correcta"] == 1
    assert practica.student("9A", "Ana Gómez")["temas"]["funciones lineales"]["n"] == 4       # cuenta en su práctica
    jv._rec.clear()
    jv.process_command("¿quién ha leído la guía?")
    assert "la terminaron 1, con 75 % de aciertos" in jv._rec.said() and "Luis Rojas" in jv._rec.said()
    jv.process_command("cierra la guía")
    assert c.get(f"/g/{code}").status_code == 404


def test_podcast(jv, g, monkeypatch):
    script = {"titulo": "Repaso de fracciones", "lineas": [{"quien": "Laura" if i % 2 == 0 else "Mateo", "texto": f"Línea {i}"} for i in range(6)]}
    monkeypatch.setattr(jv, "ai_chat", lambda msgs, **k: json.dumps(script))
    voices = []

    class FakeComm:
        def __init__(self, text, voice, **k):
            voices.append(voice)

        async def save(self, path):
            open(path, "wb").write(b"ID3fake")
    monkeypatch.setattr(jv, "edge_tts", type("E", (), {"Communicate": FakeComm}))
    jv._rec.clear()
    jv.process_command("haz un podcast de repaso de fracciones para 9A")
    _wait(jv, "Listo el podcast")
    assert "Laura y Mateo" in jv._rec.said() and set(voices) == {"es-CO-SalomeNeural", "es-CO-GonzaloNeural"}
    code, p = next(iter(guiaviva.data["podcasts"].items()))
    assert os.path.getsize(p["mp3"]) == 6 * 7
    c = jv.mobile_app.test_client()
    assert "Línea 3" in c.get(f"/a/{code}").get_data(as_text=True) and c.get(f"/a/{code}.mp3").data.startswith(b"ID3")
