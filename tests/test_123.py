"""Pruebas de la 12.3: revisar y calificar un taller (la foto o el PDF que subes, varias páginas, la lista del curso)."""
import base64
import io
import time

from PIL import Image

import adjuntos


def _img(color="white", size=(400, 300), fmt="PNG"):
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, fmt)
    return b.getvalue()


def _url(raw, mime="image/png"):
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


def _pdf(pages=2):
    b = io.BytesIO()
    ims = [Image.new("RGB", (600, 800), "white") for _ in range(pages)]
    ims[0].save(b, "PDF", save_all=True, append_images=ims[1:])
    return b.getvalue()


def _wait(cond, n=400):
    for _ in range(n):
        if cond():
            return True
        time.sleep(0.02)
    return False


RES = {"legible": True, "que_es": "taller", "resumen": "", "aciertos": ["1", "2"], "errores": [{"donde": "p. 2, punto 3", "que_esta_mal": "signo",
       "correccion": "x = 5"}], "nota": 4.2, "justificacion_nota": "", "retroalimentacion": "Bien"}


import pytest


@pytest.fixture(autouse=True)
def _limpia(jv):
    yield
    adjuntos.items.clear()                             # que lo subido aquí no cambie otras pruebas
    jv.review_state.update(path="", paths=[], t=0, source="", busy=False)


def _setup(jv, monkeypatch, tmp_path):
    from nucleo.clase import start_review
    monkeypatch.setattr(jv, "start_review", start_review)
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    adjuntos.items.clear()
    adjuntos.configure(str(tmp_path / "cfg"))
    monkeypatch.setitem(jv.aula.data, "cursos", {**jv.aula.data.get("cursos", {}), "7A": ["Ana Gómez", "Luis Rojas"]})
    monkeypatch.setitem(jv.aula.data, "activo", "7A")
    jv.review_state["busy"] = False
    cams, seen, props = [], [], []
    monkeypatch.setattr(jv, "capture_camera", lambda wait=0: cams.append(wait) or (_ for _ in ()).throw(ValueError("cámara")))
    monkeypatch.setattr(jv, "review_work", lambda path, est="", que="", clave="", grado="", asignatura="": seen.append((path, est, que, clave)) or (dict(RES), ""))
    monkeypatch.setattr(jv, "propose_review_grade", lambda *a, **k: props.append(a))
    emitted = []
    monkeypatch.setattr(jv.socketio, "emit", lambda ev, data=None, **k: emitted.append((ev, data)))
    return cams, seen, props, emitted


def test_por_voz_revisa_la_foto_subida_no_la_camara(jv, monkeypatch, tmp_path):
    cams, seen, props, emitted = _setup(jv, monkeypatch, tmp_path)
    jv.handle_attach({"files": [{"name": "taller.jpg", "data": _url(_img(fmt="JPEG"), "image/jpeg")}]})
    jv._rec.clear()
    jv.process_command("califica el taller de ana gomez")
    assert _wait(lambda: seen) and not cams
    path, est, _q, _k = seen[0]
    assert isinstance(path, str) and est == "Ana Gómez"                     # el nombre como está en la lista
    assert _wait(lambda: props) and props[0][:2] == ("7A", "Ana Gómez")
    assert _wait(lambda: any(e == "review_result" and d["status"] == "done" for e, d in emitted))
    # sin nada subido hace un rato: usa la cámara como antes
    adjuntos.items.clear()
    jv.review_state.update(path="", paths=[], t=0)
    seen.clear()
    jv.process_command("califica el taller de Luis")
    assert _wait(lambda: cams)


def test_taller_en_pdf_y_varias_fotos(jv, monkeypatch, tmp_path):
    cams, seen, props, emitted = _setup(jv, monkeypatch, tmp_path)
    r = jv.handle_attach({"files": [{"name": "taller.pdf", "data": _url(_pdf(3), "application/pdf")}]})
    assert "revisar" in [a["a"] for a in r["acciones"]]
    info = jv.handle_review_from_attach({"ids": r["ids"]})
    assert info["ok"] and info["paginas"] == 3 and info["preview"].startswith("data:image/jpeg") and info["cursos"]["7A"] == ["Ana Gómez", "Luis Rojas"]
    assert jv.handle_review_run({"estudiante": "Luis Rojas", "que": "Taller 3", "clave": "1) 3/4", "curso": "7A"})["ok"]
    assert _wait(lambda: seen)
    pages, est, que, clave = seen[0]
    assert isinstance(pages, list) and len(pages) == 3 and est == "Luis Rojas" and clave == "1) 3/4"
    # varias fotos subidas juntas: un taller de varias páginas
    a = jv.handle_attach({"files": [{"name": "p1.png", "data": _url(_img())}]})
    b = jv.handle_attach({"files": [{"name": "p2.png", "data": _url(_img("gray"))}]})
    card = jv.handle_attach_card({"ids": a["ids"] + b["ids"]})
    assert [x["a"] for x in card["acciones"]][0] == "revisar"
    assert jv.handle_review_from_attach({"ids": a["ids"] + b["ids"]})["paginas"] == 2


def test_no_inventa_estudiantes(jv, monkeypatch):
    monkeypatch.setitem(jv.aula.data, "cursos", {**jv.aula.data.get("cursos", {}), "7A": ["Ana Gómez", "Luis Rojas"]})
    asked = []
    monkeypatch.setattr(jv, "request_approval", lambda *a, **k: asked.append(a[1]))
    jv._rec.clear()
    assert jv.propose_review_grade("7A", "Anita", "Taller", 4.0) is None and not asked
    assert "No encontré a «Anita» en la lista de 7A" in jv._rec.said()
    jv.propose_review_grade("7A", "luis rojas", "Taller", 3.5)
    assert asked and "Luis Rojas" in asked[0]


def test_varias_imagenes_y_tipo_real(jv, tmp_path):
    jpg, png = tmp_path / "a.jpg", tmp_path / "b.png"
    jpg.write_bytes(_img(fmt="JPEG"))
    png.write_bytes(_img())
    assert jv._img_mime(str(jpg)) == "image/jpeg" and jv._img_mime(str(png)) == "image/png"
    msgs = [{"role": "user", "content": "revisa"}]
    g = jv._gemini_body({"model": "m", "spec": {}}, msgs, 100, image_path=[str(jpg), str(png)])
    parts = g["contents"][-1]["parts"]
    assert [p["inlineData"]["mimeType"] for p in parts if "inlineData" in p] == ["image/jpeg", "image/png"]
    oa, _ = jv._oa_body({"model": "m", "spec": {}}, msgs, 100, image_path=[str(jpg), str(png)])
    assert [c["image_url"]["url"][:15] for c in oa["messages"][-1]["content"] if c["type"] == "image_url"] == ["data:image/jpeg", "data:image/png;"]
    an = jv._anthropic_body({"model": "m", "spec": {}}, msgs, 100, image_path=str(jpg))
    assert an["messages"][-1]["content"][0]["source"]["media_type"] == "image/jpeg"
