"""Pruebas de la 12.63: videos cortos con IA gratis (NVIDIA Cosmos3 Nano)."""
import base64
import io
import json


def _png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), "blue").save(buf, "PNG")
    return buf.getvalue()


MP4 = b"\x00\x00\x00\x18ftypmp42" + b"0" * 200


def test_cuerpo(jv):
    b = jv.vi63_body("a volcano erupting", 5, "16:9")
    assert b == {"model_mode": "text2video", "prompt": "a volcano erupting", "resolution": "480_16_9", "num_frames": 121,
                 "fps": 24, "num_inference_steps": 35}
    i = jv.vi63_body("p", 1, "9:16", "QUJD")
    assert i["model_mode"] == "image2video" and i["input_reference"] == "data:image/png;base64,QUJD" and i["num_frames"] == 25
    assert jv.vi63_frames(60) == 241 and jv.vi63_frames(0.1) == 25


def test_llamada_y_cola(jv):
    calls = []
    ok = json.dumps({"b64_video": base64.b64encode(MP4).decode()}).encode()

    def req(url, key, body=None):
        calls.append(url)
        if len(calls) == 1:
            return 202, {"NVCF-REQID": "abc"}, b""
        return 200, {}, ok
    assert jv.vi63_call("nvapi-x", {"prompt": "p"}, sleep=lambda s: None, request=req) == MP4
    assert calls == [jv.VI63_URL, jv.VI63_STATUS + "abc"]
    try:
        jv.vi63_extract({"b64_video": ""})
        assert False
    except ValueError:
        pass


def test_por_voz(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "nvidia_api_key", "nvapi-x")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(jv, "vi63_prompt", lambda tema: "EN: " + tema)
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    sent = []
    monkeypatch.setattr(jv, "vi63_call", lambda key, body: (sent.append((key, body)), MP4)[1])
    jv._rec.clear()
    jv.process_command("hazme un video de 5 segundos de un volcán en erupción")
    assert sent and sent[-1][0] == "nvapi-x" and sent[-1][1]["prompt"] == "EN: un volcán en erupción"
    assert sent[-1][1]["num_frames"] == 121 and "Listo" in jv._rec.said()
    vids = list((tmp_path / "Videos" / "IA").iterdir())
    assert len(vids) == 1 and vids[0].read_bytes() == MP4
    jv.process_command("hazme un clip con IA de un colibrí volando")
    assert sent[-1][1]["model_mode"] == "text2video" and "colibrí" in sent[-1][1]["prompt"]


def test_explicativo_sigue_siendo_videomate(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "nvidia_api_key", "nvapi-x")
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": jv._rec.other.append("job:" + label))
    jv._rec.clear()
    jv.process_command("hazme un video de 2 minutos que explique el teorema de Pitágoras")
    assert "job:Creando el video con IA" not in jv._rec.other


def test_animar_imagen(jv, monkeypatch, tmp_path):
    img = tmp_path / "volcan.png"
    img.write_bytes(_png())
    monkeypatch.setitem(jv.settings, "nvidia_api_key", "nvapi-x")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    monkeypatch.setitem(jv.studio, "items", [{"path": str(img), "tema": "un volcán", "estilo": "", "formato": "", "t": __import__("time").time()}])
    monkeypatch.setattr(jv, "vi63_prompt", lambda tema: tema)
    monkeypatch.setattr(jv, "_open_doc", lambda p: None)
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": fn())
    sent = []
    monkeypatch.setattr(jv, "vi63_call", lambda key, body: (sent.append(body), MP4)[1])
    jv._rec.clear()
    jv.process_command("anima esta imagen")
    assert sent and sent[-1]["model_mode"] == "image2video" and sent[-1]["input_reference"].startswith("data:image/png;base64,")


def test_sin_clave(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "nvidia_api_key", "")
    monkeypatch.setattr(jv, "_vi63_key", lambda: "")
    jv._rec.clear()
    jv.process_command("hazme un video de 5 segundos de un volcán")
    assert "build.nvidia.com" in jv._rec.said()
