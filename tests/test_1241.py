"""Pruebas de la 12.41: la IA local más rápida (modelos de 2026, adivinador MTP, memoria comprimida, cerebro mini y la prueba
de velocidad que ajusta todo a tu PC)."""
import io
import os
import tarfile

import motorlocal


def test_catalogo_2026_y_archivos():
    ids = [m["id"] for m in motorlocal.CATALOG]
    assert ids[:4] == ["qwen3.5-4b", "gemma4-e2b", "gemma4-e4b", "qwen3.5-0.8b"] and "qwen3-4b" in ids     # los viejos se reconocen
    assert motorlocal.by_id("gemma4-e4b")["mtp"] and motorlocal.by_id("gemma4-e2b")["vision"] and motorlocal.VISION_ID == "gemma4-e2b"
    assert motorlocal.recommend(16, 50)["id"] == "qwen3.5-4b" and motorlocal.recommend(5, 50)["id"] == "qwen3.5-0.8b"
    assert motorlocal.entry_for_file("gemma-4-E4B-it-Q4_K_M.gguf")["id"] == "gemma4-e4b"
    assert motorlocal.entry_for_file("Qwen3.5-0.8B-Q4_K_M.gguf")["id"] == "qwen3.5-0.8b"
    assert motorlocal.entry_for_file("Qwen3.5-4B-Q4_K_M.gguf")["id"] == "qwen3.5-4b"
    sib = [{"rfilename": "gemma-4-E4B-it-Q4_K_M.gguf"}, {"rfilename": "gemma-4-E4B-it-UD-Q4_K_M.gguf"}, {"rfilename": "mmproj-F16.gguf"},
           {"rfilename": "mtp-gemma-4-E4B-it.gguf"}, {"rfilename": "MTP/mtp-gemma-4-E4B-it-Q4_K_M.gguf"}]
    assert motorlocal.pick_gguf(sib) == "gemma-4-E4B-it-Q4_K_M.gguf"            # nunca el adivinador como modelo
    assert motorlocal.pick_mtp(sib) == "mtp-gemma-4-E4B-it.gguf" and motorlocal.pick_mtp([{"rfilename": "a-Q4_K_M.gguf"}]) == ""
    assert motorlocal.engine_date_old("") and motorlocal.engine_date_old("2026-01-10") and not motorlocal.engine_date_old("2026-09-01")


def test_argumentos_del_motor():
    a = motorlocal.server_args("ls", "m.gguf", draft="d.gguf", draft_n=2, kv="q8_0")
    i = a.index("--model-draft")
    assert a[i:i + 6] == ["--model-draft", "d.gguf", "--spec-type", "draft-mtp", "--spec-draft-n-max", "2"]
    assert a[a.index("-ctk") + 1] == "q8_0" and a[a.index("-ctv") + 1] == "q8_0"
    plain = motorlocal.server_args("ls", "m.gguf", draft="d.gguf", draft_n=0)
    assert "--model-draft" not in plain and "-ctk" not in plain


def test_combinaciones_y_ganador():
    c = motorlocal.tune_candidates(4, 8, has_mtp=True, low_ram=True)
    assert c[0] == {"threads": 4, "mtp": 0, "kv": ""}                           # la base primero
    assert {x["threads"] for x in c} == {4, 3, 2, 8} and [x["mtp"] for x in c if x["mtp"]] == [2, 4] and c[-1]["kv"] == "q8_0"
    assert all(not x["mtp"] for x in motorlocal.tune_candidates(4, 8)) and len(motorlocal.tune_candidates(1, 1)) == 1
    base, mtp = {"threads": 4, "mtp": 0, "kv": ""}, {"threads": 4, "mtp": 2, "kv": ""}
    assert motorlocal.pick_best([(base, 10.0), (mtp, 10.3)]) == (base, 10.0)    # 3 % es ruido: se queda lo de siempre
    assert motorlocal.pick_best([(base, 10.0), (mtp, 16.0)]) == (mtp, 16.0)
    assert motorlocal.pick_best([(base, 0.0), (mtp, 7.0)]) == (mtp, 7.0) and motorlocal.pick_best([(base, 0.0)]) == (None, 0.0)


def _fake_engine(jv, monkeypatch, tmp_path, model="gemma-4-E4B-it-Q4_K_M.gguf", mtp=True):
    monkeypatch.setattr(jv, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(jv, "IS_WIN", False)
    os.makedirs(tmp_path / "motor" / "bin")
    os.makedirs(tmp_path / "motor" / "modelos")
    exe = tmp_path / "motor" / "bin" / "llama-server"
    exe.write_text("#!/bin/sh\n")
    os.chmod(exe, 0o755)
    (tmp_path / "motor" / "bin" / "version.txt").write_text("b9000\n2026-08-01")
    (tmp_path / "motor" / "modelos" / model).write_bytes(b"GGUF")
    if mtp:
        os.makedirs(tmp_path / "motor" / "mtp")
        (tmp_path / "motor" / "mtp" / model).write_bytes(b"GGUF")
    monkeypatch.setitem(jv.settings, "motor_model", model)
    monkeypatch.setitem(jv.settings, "motor_backend", "cpu")
    monkeypatch.setattr(jv, "save_settings_file", lambda: None)


class _Proc:
    def __init__(self, args):
        self.args = args

    def poll(self):
        return None

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0


def test_arranca_con_los_ajustes_guardados(jv, monkeypatch, tmp_path):
    import nucleo.motor as mt
    _fake_engine(jv, monkeypatch, tmp_path)
    started = []
    monkeypatch.setattr(mt.subprocess, "Popen", lambda args, **k: started.append(args) or _Proc(args))
    monkeypatch.setattr(mt, "_health", lambda timeout=1.5: True)
    monkeypatch.setattr(jv, "motor_warmup", lambda: None)
    monkeypatch.setitem(mt.engine, "proc", None)
    monkeypatch.setitem(mt.engine, "no_extra", False)
    for k, v in (("motor_threads", 3), ("motor_mtp_n", 2), ("motor_kv", "q8_0")):
        monkeypatch.setitem(jv.settings, k, v)
    assert jv.motor_start(5)
    a = started[-1]
    assert a[a.index("-t") + 1] == "3" and a[a.index("--spec-draft-n-max") + 1] == "2" and "q8_0" in a
    assert a[a.index("--model-draft") + 1].endswith(os.path.join("mtp", "gemma-4-E4B-it-Q4_K_M.gguf"))
    mt.motor_stop()
    monkeypatch.setitem(mt.engine, "no_extra", True)                           # no arrancó con ellos: queda lo normal
    assert jv.motor_start(5) and "--model-draft" not in started[-1] and "-ctk" not in started[-1]
    mt.motor_stop()


def test_motor_viejo_se_actualiza(jv, monkeypatch, tmp_path):
    import nucleo.motor as mt
    _fake_engine(jv, monkeypatch, tmp_path)
    (tmp_path / "motor" / "bin" / "version.txt").write_text("b5000")           # sin fecha: viejo
    assert jv.engine_old()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        data = b"#!/bin/sh\necho nuevo\n"
        ti = tarfile.TarInfo("llama-b9/llama-server")
        ti.size = len(data)
        t.addfile(ti, io.BytesIO(data))
    rel = [{"tag_name": "b9", "published_at": "2026-10-01T10:00:00Z",
            "assets": [{"name": "llama-b9-bin-ubuntu-x64.tar.gz", "browser_download_url": "https://x/u.tgz"}]}]
    monkeypatch.setattr(jv, "_motor_get_json", lambda url, timeout=20: rel)
    def fetch(url, dst, progress=None, label=""):
        with open(dst, "wb") as f:
            f.write(buf.getvalue())
        return dst
    monkeypatch.setattr(jv, "_motor_fetch", fetch)
    monkeypatch.setattr(mt, "verify_download", lambda *a: True)
    exe = jv.install_engine(update=True)
    assert "nuevo" in open(exe).read() and jv.engine_date() == "2026-10-01" and not jv.engine_old()
    assert not os.path.exists(tmp_path / "motor" / "bin" / "llama-server")    # el viejo se quitó
    assert jv.install_engine(update=True) == exe                               # ya es reciente: no baja nada


def test_cerebro_mini_entiende_y_si_falla_responde_la_grande(jv, monkeypatch):
    import nucleo.motor as mt
    monkeypatch.setattr(mt, "mini_path", lambda: "/x/mini.gguf")
    monkeypatch.setitem(jv.settings, "motor_mini", True)
    assert jv.mini_use(True, None, 220) and not jv.mini_use(False, None, 220) and not jv.mini_use(True, "foto.png", 220)
    assert not jv.mini_use(True, None, 900)                                    # escribir algo largo: la IA grande
    monkeypatch.setitem(jv.settings, "motor_mini", False)
    assert not jv.mini_use(True, None, 220)
    jv._tl.mini_force = "on"
    assert jv.mini_use(True, None, 220)
    jv._tl.mini_force = ""
    monkeypatch.setitem(jv.settings, "motor_mini", True)
    monkeypatch.setattr(jv, "motor_ensure", lambda: None)
    bases = []
    monkeypatch.setattr(jv, "openai_chat", lambda c, m, j=False, t=1024, image_path=None: bases.append(c["base"]) or '{"tipo":"orden"}')
    monkeypatch.setattr(mt, "mini_start", lambda wait=60: True)
    motor = jv._ai_cfg({"ai_provider": "motor"})
    assert jv._cloud_chat(motor, [{"role": "user", "content": "x"}], json_mode=True, max_tokens=220) == '{"tipo":"orden"}'
    assert bases[-1] == "http://127.0.0.1:8092/v1"
    jv._cloud_chat(motor, [{"role": "user", "content": "x"}], max_tokens=220)
    assert bases[-1] == "http://127.0.0.1:8091/v1"                             # conversar: la grande
    monkeypatch.setattr(mt, "mini_start", lambda wait=60: False)               # el mini no arranca: responde la grande
    assert jv._cloud_chat(motor, [{"role": "user", "content": "x"}], json_mode=True, max_tokens=220) and bases[-1].endswith(":8091/v1")


def test_prueba_de_velocidad_deja_lo_mas_rapido(jv, monkeypatch, tmp_path):
    import nucleo.motor as mt
    _fake_engine(jv, monkeypatch, tmp_path)
    monkeypatch.setattr(mt, "_phys", lambda: 4)
    monkeypatch.setattr(mt.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(mt, "_ram_gb", lambda: 16.0)
    monkeypatch.setattr(jv, "install_engine", lambda progress=None, gpu=False, update=False: "x")
    seen = []
    monkeypatch.setattr(jv, "motor_start", lambda wait=120: seen.append(dict(mt.engine["tune"] or {})) or True)
    speeds = {(4, 0): 10.0, (3, 0): 10.2, (2, 0): 7.0, (8, 0): 9.0, (4, 2): 17.0, (4, 4): 15.0}
    monkeypatch.setattr(jv, "motor_bench", lambda: speeds[(seen[-1].get("threads", 4), seen[-1].get("mtp", 0))])
    for k in ("motor_threads", "motor_mtp_n", "motor_kv", "motor_mini", "motor_tuned"):
        monkeypatch.setitem(jv.settings, k, jv.settings.get(k))
    r = jv.motor_tune_run(with_mini=False)
    assert r["cfg"] == {"threads": 4, "mtp": 2, "kv": ""} and r["tps"] == 17.0 and r["base"] == 10.0
    assert jv.settings["motor_mtp_n"] == 2 and jv.settings["motor_threads"] == 4 and "adivinador" in r["texto"] and "antes 10" in r["texto"]
    assert mt.engine["tune"] is None and {"threads": 4, "mtp": 0, "kv": ""} in seen
    # el cerebro mini: se queda solo si acierta casi igual y es más rápido
    monkeypatch.setattr(mt, "install_mini", lambda progress=None: "/x/mini.gguf")
    monkeypatch.setattr(mt, "_mini_check", lambda n=10: (9, 9, 20.0, 6.0, 10))
    assert jv.motor_tune_run()["mini"] is True and "queda encendido" in jv.settings["motor_tuned"]
    monkeypatch.setattr(mt, "_mini_check", lambda n=10: (9, 6, 20.0, 6.0, 10))
    monkeypatch.setattr(mt, "mini_stop", lambda: None)
    assert jv.motor_tune_run()["mini"] is False and "no convenció" in jv.settings["motor_tuned"]


def test_por_voz_pide_permiso(jv, monkeypatch):
    import nucleo.motor as mt
    asked, jobs = [], []
    monkeypatch.setattr(jv, "request_approval", lambda tipo, titulo, detalle="", on_ok=None, on_no=None, **k: asked.append((tipo, titulo, on_ok)))
    monkeypatch.setattr(jv, "motor_tune_job", lambda: jobs.append(1))
    monkeypatch.setattr(jv, "motor_ready", lambda: True)
    monkeypatch.setitem(mt.engine, "job", False)
    for phrase in ("optimiza la IA local", "Jarvis, prueba la velocidad de la IA local", "quiero que la IA local sea más rápida",
                   "optimizar la IA local", "optimiza tu IA local", "optimiza la IA", "acelera el modelo local", "mejora la IA local",
                   "ajusta la velocidad de la IA local", "haz la prueba de velocidad",
                   "optimice la IA local", "acelere su IA local", "mejore la velocidad de la IA local"):     # 12.43: de usted        # 12.42: dicho de otras formas
        jv._rec.clear()
        jv.process_command(phrase)
        assert asked and asked[-1][0] == "instalar" and "velocidad" in asked[-1][1], phrase
    asked[-1][2]()
    assert jobs == [1]
    assert "ya está optimizada" in jv.ACTION_RULE and "optimiza la IA local" in jv.ACTION_RULE   # la IA no finge haberlo hecho
    st = jv.motor_status()
    assert {"mini", "adivina", "ajuste", "viejo"} <= set(st)
