"""Pruebas de la 12.61: crear y editar imágenes con SenseNova (gratis en su beta)."""
import base64
import io

import imagenes


def _png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")
    return buf.getvalue()


def test_cuerpo_y_respuesta():
    b = imagenes.sensenova_payload("", "un perro", "16:9")
    assert b == {"model": "sensenova-u1.5-lite", "prompt": "un perro", "n": 1, "size": "2048x1152", "watermark": False,
                 "prompt_extend": True, "response_format": "b64_json"}
    e = imagenes.sensenova_payload("m", "fondo azul", "", "QUJD")
    assert e["size"] == "auto" and e["images"] == [{"image_url": "data:image/png;base64,QUJD"}]
    for size in imagenes.SENSENOVA_SIZES.values():
        w, h = map(int, size.split("x"))
        assert w % 32 == 0 and h % 32 == 0 and 512 <= min(w, h) and max(w, h) <= 4096 and max(w, h) / min(w, h) <= 3
    png = _png()
    assert imagenes.sensenova_extract({"data": [{"b64_json": base64.b64encode(png).decode()}]}, None) == (png, ".png")
    got = imagenes.sensenova_extract({"data": [{"url": "https://cdn.x/i.jpg"}]}, lambda u: b"\xff\xd8\xff" + b"0" * 10)
    assert got[1] == ".jpg"
    for bad in ({"data": []}, {"data": [{"url": "http://inseguro"}]}, {}):
        try:
            imagenes.sensenova_extract(bad, lambda u: b"")
            assert False
        except ValueError:
            pass


def _keys(jv, monkeypatch, gemini=False, chatgpt=False, sn=True):
    monkeypatch.setattr(jv, "_gemini_for_stt", lambda: {"key": "g"} if gemini else None)
    monkeypatch.setitem(jv.settings, "chatgpt_api_key", "o" if chatgpt else "")
    monkeypatch.setitem(jv.settings, "sensenova_api_key", "sk-sn" if sn else "")
    monkeypatch.setattr(jv, "image_model", lambda: "gemini-img" if gemini else "")


def test_quien_crea(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "image_provider", "auto")
    _keys(jv, monkeypatch)
    assert jv.image_backend()[0] == "sensenova"
    prov, msg = jv.image_backend(allow_cn=False)
    assert prov is None and "China" in msg
    _keys(jv, monkeypatch, gemini=True)
    assert jv.image_backend()[0] == "gemini"
    monkeypatch.setitem(jv.settings, "image_provider", "sensenova")
    assert jv.image_backend(allow_cn=False)[0] == "sensenova"           # si la escoges tú, siempre
    _keys(jv, monkeypatch, sn=False)
    assert "SenseNova" in jv.image_backend()[1]
    monkeypatch.setitem(jv.settings, "image_provider", "auto")
    assert "SenseNova (gratis)" in jv.image_backend()[1]


def test_crear_con_sensenova(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.studio, "items", [])          # que las imágenes de esta prueba no se cuelen en otras
    monkeypatch.setitem(jv.settings, "image_provider", "sensenova")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    _keys(jv, monkeypatch)
    sent = []
    png = _png()

    def http(method, url, headers=None, payload=None, timeout=120, stream=False):
        sent.append((url, headers, payload))
        return {"data": [{"b64_json": base64.b64encode(png).decode()}]}
    monkeypatch.setattr(jv, "_http", http)
    paths = jv.studio_generate("el ciclo del agua", "", "16:9")
    assert len(paths) == 1 and open(paths[0], "rb").read() == png
    url, headers, body = sent[-1]
    assert url == "https://token.sensenova.ai/v1/images/generations" and headers["Authorization"] == "Bearer sk-sn"
    assert body["size"] == "2048x1152" and body["watermark"] is False
    jv.studio_generate("", src=paths[0], instruccion="ponle el fondo azul")          # editar una creada aquí
    assert sent[-1][0].endswith("/images/edits") and sent[-1][2]["images"][0]["image_url"].startswith("data:image/png;base64,")


def test_foto_propia_no_va_a_china_en_automatico(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.studio, "items", [])
    monkeypatch.setitem(jv.settings, "image_provider", "auto")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    _keys(jv, monkeypatch)
    foto = tmp_path / "mi_foto.png"
    foto.write_bytes(_png())
    monkeypatch.setattr(jv, "_http", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía enviarse")))
    try:
        jv.studio_generate("", src=str(foto), instruccion="quítale el fondo")
        assert False
    except RuntimeError as e:
        assert "China" in str(e)


# ---------------------------------------------------------------- 12.62: si uno no tiene cupo, el siguiente
def test_sin_cupo_pasa_al_siguiente(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.studio, "items", [])
    monkeypatch.setitem(jv.settings, "image_provider", "auto")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    _keys(jv, monkeypatch, gemini=True)
    png = _png()
    tried = []

    def one(prov, cfg, prompt, aspect="", src=None):
        tried.append(prov)
        if prov == "gemini":
            raise jv.AIError("429", code=429, kind="quota", why="se agotó la cuota")
        return png, ".png"
    monkeypatch.setattr(jv, "_one_image", one)
    paths = jv.studio_generate("el ciclo del agua", n=2)
    assert len(paths) == 2 and tried == ["gemini", "sensenova", "sensenova"]


def test_ninguno_puede(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.studio, "items", [])
    monkeypatch.setitem(jv.settings, "image_provider", "auto")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    _keys(jv, monkeypatch, gemini=True, sn=False)
    monkeypatch.setattr(jv, "_one_image", lambda *a, **k: (_ for _ in ()).throw(jv.AIError("429", code=429, kind="quota", why="x")))
    try:
        jv.studio_generate("el ciclo del agua")
        assert False
    except RuntimeError as e:
        assert "Gemini no tiene cupo para imágenes" in str(e) and "platform.sensenova.ai" in str(e)


def test_otro_error_no_reintenta(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.studio, "items", [])
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    _keys(jv, monkeypatch, gemini=True)
    tried = []
    monkeypatch.setattr(jv, "_one_image", lambda prov, *a, **k: (tried.append(prov), (_ for _ in ()).throw(
        jv.AIError("safety", code=400, kind="safety", why="contenido bloqueado")))[1])
    try:
        jv.studio_generate("algo")
        assert False
    except RuntimeError as e:
        assert tried == ["gemini"] and "bloqueado" in str(e)
