"""Pruebas de la 12.6: la IA local integrada (motor llama.cpp dentro de Jarvis, sin Ollama)."""
import io
import os
import tarfile

import motorlocal


def test_reglas_del_motor():
    rel = [{"tag_name": "b2", "assets": [{"name": "llama-b2-bin-macos-arm64.zip", "browser_download_url": "https://x/m.zip"}]},
           {"tag_name": "b1", "assets": [{"name": "llama-b1-bin-win-cpu-x64.zip", "browser_download_url": "https://x/w.zip"},
                                         {"name": "llama-b1-bin-ubuntu-x64.tar.gz", "browser_download_url": "https://x/u.tgz"}]}]
    assert motorlocal.pick_release(rel, True) == ("https://x/w.zip", "llama-b1-bin-win-cpu-x64.zip", "b1")
    assert motorlocal.pick_release(rel, False)[1].endswith("ubuntu-x64.tar.gz") and motorlocal.pick_release([], True) is None
    sib = [{"rfilename": "README.md"}, {"rfilename": "mmproj-F16.gguf"}, {"rfilename": "Qwen3-4B-Q8_0.gguf"}, {"rfilename": "Qwen3-4B-Q4_K_M.gguf"},
           {"rfilename": "big-00001-of-00002.gguf"}]
    assert motorlocal.pick_gguf(sib, "Q4_K_M") == "Qwen3-4B-Q4_K_M.gguf"
    assert motorlocal.recommend(16, 50)["id"] == "qwen3-4b" and motorlocal.recommend(4, 50)["id"] == "gemma3-1b" and motorlocal.recommend(2, 50) is None
    assert motorlocal.recommend(16, 1) is None                                     # sin disco
    a = motorlocal.server_args("llama-server.exe", "m.gguf", threads=3)
    assert a[:3] == ["llama-server.exe", "-m", "m.gguf"] and "127.0.0.1" in a and "-t" in a
    assert motorlocal.clean_reply("<think>pienso…</think>\nSon 56.") == "Son 56."


def test_instalar_y_usar_sin_ollama(jv, monkeypatch, tmp_path):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(jv, "IS_WIN", False)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        data = b"#!/bin/sh\necho motor\n"
        ti = tarfile.TarInfo("llama-b1/llama-server")
        ti.size = len(data)
        t.addfile(ti, io.BytesIO(data))
    rel = [{"tag_name": "b1", "assets": [{"name": "llama-b1-bin-ubuntu-x64.tar.gz", "browser_download_url": "https://x/u.tgz"}]}]

    def get_json(url, timeout=20):
        return rel if "github" in url else {"siblings": [{"rfilename": "gemma-3-1b-it-Q4_K_M.gguf"}]}

    def fetch(url, dst, progress=None, label=""):
        with open(dst, "wb") as f:
            f.write(buf.getvalue() if url.endswith(".tgz") else b"GGUF")
        return dst
    monkeypatch.setattr(jv, "_motor_get_json", get_json)
    monkeypatch.setattr(jv, "_motor_fetch", fetch)
    monkeypatch.setattr(jv, "motor_recommend", lambda: motorlocal.by_id("gemma3-1b"))
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)
    monkeypatch.setitem(jv.settings, "motor_model", "")
    assert not jv.motor_ready()
    exe = jv.install_engine()
    assert exe.endswith("llama-server") and os.access(exe, os.X_OK)
    path = jv.install_model()
    assert os.path.basename(path) == "gemma-3-1b-it-Q4_K_M.gguf" and jv.motor_ready() and jv.motor_name() == "gemma-3-1b-it-Q4_K_M"
    # sin internet: la IA de respaldo es la integrada (no Ollama)
    monkeypatch.setitem(jv.net, "local_at", 0)
    assert jv.local_ai_model(refresh=True) == "motor:gemma-3-1b-it-Q4_K_M"
    monkeypatch.setitem(jv.settings, "ai_provider", "gemini")
    monkeypatch.setitem(jv.settings, "offline_auto", True)
    monkeypatch.setitem(jv.net, "offline", True)
    cfg = jv._ai_cfg()
    assert cfg["ai_provider"] == "motor" and cfg["base"] == "http://127.0.0.1:8091/v1" and cfg.get("offline")
    jv._need_key(cfg)                                                             # no pide clave
    asked = []
    monkeypatch.setattr(jv, "motor_ensure", lambda: asked.append("ensure"))
    monkeypatch.setattr(jv, "openai_chat", lambda c, m, j=False, t=1024, image_path=None: "<think>x</think>Hola profe.")
    from nucleo.ia import ai_chat
    assert ai_chat([{"role": "user", "content": "hola"}]) == "Hola profe." and asked == ["ensure"]
    a = jv.ai_now()
    assert a["donde"] == "local" and a["proveedor"] == "Jarvis local"
    monkeypatch.setitem(jv.net, "offline", False)
    jv.net.update(local_model="", local_at=0)


def test_instalar_pide_permiso(jv, monkeypatch):
    asked = []
    monkeypatch.setattr(jv, "request_approval", lambda tipo, titulo, detalle="", on_ok=None, on_no=None, **k: asked.append((tipo, titulo, on_ok)))
    monkeypatch.setattr(jv, "motor_recommend", lambda: motorlocal.by_id("qwen3-4b"))
    monkeypatch.setattr(jv, "motor_ready", lambda: False)
    jobs = []
    monkeypatch.setattr(jv, "motor_install_job", lambda mid=None: jobs.append(mid))
    jv._rec.clear()
    jv.process_command("instala la IA integrada")
    assert asked and asked[0][0] == "instalar" and "Qwen3 4B" in asked[0][1] and not jobs
    asked[0][2]()
    assert jobs == ["qwen3-4b"]


def test_estilo_aurora_en_todas_las_paginas(jv):
    import glob
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = jv.app.jinja_env
    for p in glob.glob(os.path.join(here, "templates", "*.html")):
        name = os.path.basename(p)
        src = open(p, encoding="utf-8").read()
        assert '{% include "_aurora.css" %}' in src and "data-look=" in src, name
        env.get_template(name)                                                   # compila (el include del estilo también)
    css = open(os.path.join(here, "templates", "_aurora.css"), encoding="utf-8").read()
    assert "{{" not in css and "{%" not in css and "{#" not in css               # no confunde a Jinja
    with jv.app.test_request_context("/"):
        from flask import render_template
        assert 'data-look="clasico"' in render_template("bienvenida.html")
    assert jv._validate("look", "clasico") == "clasico"
