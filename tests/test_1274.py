"""Pruebas de la 12.74: generadores de imágenes nuevos (FLUX en NVIDIA y el de tu PC), la IA según el trabajo (código),
la cadena de respaldos que nunca se queda parada, generar código revisado y el Estudio creativo."""
import base64
import io
import json
import os

import enrutador as EN
import imagenlocal as IL


def _png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(buf, "PNG")
    return buf.getvalue()


# ============================================================================ LÓGICA PURA: IMÁGENES
def test_motor_y_orden_del_generador():
    rel = [{"tag_name": "master-9-abc", "assets": [
        {"name": "cudart-sd-bin-win-cu12-x64.zip", "browser_download_url": "https://x/c.zip"},
        {"name": "sd-master-abc-bin-win-cpu-x64.zip", "browser_download_url": "https://x/cpu.zip"},
        {"name": "sd-master-abc-bin-win-vulkan-x64.zip", "browser_download_url": "https://x/vk.zip"}]}]
    assert IL.pick_release(rel, True, True)[0] == "https://x/vk.zip"
    assert IL.pick_release(rel, True, False)[0] == "https://x/cpu.zip"
    a = IL.cli_args("sd-cli.exe", "m.gguf", "a cat", "o.png", "16:9", seed=7, threads=4)
    assert a[:3] == ["sd-cli.exe", "-m", "m.gguf"] and a[a.index("-W") + 1] == "704" and a[a.index("--steps") + 1] == "1"
    assert a[a.index("--cfg-scale") + 1] == "1" and a[a.index("-t") + 1] == "4" and "-i" not in a
    e = IL.cli_args("sd", "m", "p", "o", init="in.png")
    assert e[e.index("-i") + 1] == "in.png" and e[e.index("--steps") + 1] == "2"
    for w, h in IL.LOCAL_SIZES.values():
        assert w % 64 == 0 and h % 64 == 0


def test_flux_respuesta():
    png = _png()
    assert IL.nv_extract({"artifacts": [{"base64": base64.b64encode(png).decode(), "finishReason": "SUCCESS"}]}) == (png, ".png")
    assert IL.nv_extract({"data": [{"b64_json": base64.b64encode(png).decode()}]})[0] == png
    for bad in ({"artifacts": [{"base64": "", "finishReason": "CONTENT_FILTERED"}]}, {}):
        try:
            IL.nv_extract(bad)
            assert False
        except ValueError:
            pass
    p = IL.nv_payload("a cat", "3:4")
    assert (p["width"], p["height"]) == (896, 1152) and p["steps"] == 4


def test_orden_segun_el_pedido():
    av = ["gemini", "chatgpt", "nvidia", "sensenova", "local"]
    assert IL.order(av, tema="un gato") == ["gemini", "chatgpt", "nvidia", "sensenova", "local"]
    assert IL.order(av, ai_provider="chatgpt", tema="un afiche que diga Día del Idioma")[0] == "chatgpt"
    foto = IL.order(av, own_photo=True)
    assert "sensenova" not in foto and "nvidia" not in foto                 # foto tuya: ni China ni FLUX (no edita)
    assert IL.order(av, offline=True) == ["local"]
    assert IL.order(av, own_photo=True, private=True) == ["local"]
    assert IL.order(["gemini", "nvidia"], chosen="nvidia")[0] == "nvidia"
    assert IL.order(["gemini", "nvidia"], cool={"gemini": 9e18}) == ["nvidia", "gemini"]   # el que falló, al final
    assert IL.order(["gemini"], offline=True) == []


# ============================================================================ LÓGICA PURA: LA IA SEGÚN EL TRABAJO
def test_ia_para_codigo_y_respaldos():
    assert EN.code_choice("gemini", {"gemini", "nvidia", "zai"}) == ("nvidia", "moonshotai/kimi-k3.1-pro")
    assert EN.code_choice("gemini", {"gemini", "zai"}) == ("zai", "glm-4.7-flash")
    assert EN.code_choice("anthropic", {"anthropic", "nvidia"}) is None         # la tuya ya programa muy bien
    assert EN.code_choice("gemini", {"gemini"}) is None
    assert EN.code_choice("gemini", {"gemini", "nvidia"}, "off") is None
    assert EN.code_choice("gemini", {"gemini", "nvidia", "deepseek"}, "deepseek") == ("deepseek", "")
    ch = EN.backup_chain("gemini", {"gemini", "deepseek", "zai", "sensenova"}, first="nvidia", local=True)
    assert ch == ["nvidia", "deepseek", "zai", "sensenova", "motor"]
    assert "zai" not in EN.backup_chain("gemini", {"zai"}, has_names=True)      # con nombres de estudiantes, no a China
    assert EN.backup_chain("gemini", {"zai"}, want="off") == []
    assert EN.is_code([{"role": "user", "content": "revisa este código:\n```python\nprint(1)\n```"}])
    assert not EN.is_code([{"role": "user", "content": "¿qué es una fracción?"}])
    g = EN.gen_validate({"codigo": "```python\nprint('hola')\n```", "nombre": "saludo.py", "explicacion": "Saluda."}, "Python")
    assert g["codigo"] == "print('hola')" and g["nombre"] == "saludo.py"
    assert EN.lang_from("una página web con un botón") == "HTML" and EN.lang_from("un programa que sume") == "Python"


# ============================================================================ IMÁGENES EN JARVIS
def _keys(jv, monkeypatch, nvidia=True, gemini=False, local=False):
    monkeypatch.setattr(jv, "_gemini_for_stt", lambda: {"key": "g"} if gemini else None)
    monkeypatch.setattr(jv, "image_model", lambda: "gemini-img" if gemini else "")
    monkeypatch.setitem(jv.settings, "chatgpt_api_key", "")
    monkeypatch.setitem(jv.settings, "sensenova_api_key", "")
    monkeypatch.setitem(jv.settings, "nvidia_api_key", "nvapi-x" if nvidia else "")
    monkeypatch.setattr(jv, "im73_ready", lambda: local)


def test_crear_con_flux(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.studio, "items", [])
    monkeypatch.setitem(jv.settings, "image_provider", "auto")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    _keys(jv, monkeypatch)
    png, sent = _png(), []

    def http(method, url, headers=None, payload=None, timeout=120, stream=False):
        sent.append((url, headers, payload))
        return {"artifacts": [{"base64": base64.b64encode(png).decode(), "finishReason": "SUCCESS"}]}
    monkeypatch.setattr(jv, "_http", http)
    assert jv.image_backend()[0] == "nvidia"
    paths = jv.studio_generate("el ciclo del agua", "", "16:9")
    url, headers, body = sent[-1]
    assert url == IL.NV_URL and headers["Authorization"] == "Bearer nvapi-x" and (body["width"], body["height"]) == (1344, 768)
    assert len(paths) == 1 and open(paths[0], "rb").read() == png


def test_si_uno_falla_descansa_y_sigue_otro(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.studio, "items", [])
    monkeypatch.setitem(jv.settings, "image_provider", "auto")
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    _keys(jv, monkeypatch, gemini=True, local=True)
    png, tried = _png(), []

    def one(prov, cfg, prompt, aspect="", src=None):
        tried.append(prov)
        if prov in ("gemini", "nvidia"):
            raise jv.AIError("429", code=429, kind="quota", why="sin cupo")
        return png, ".png"
    monkeypatch.setattr(jv, "_one_image", one)
    assert len(jv.studio_generate("un volcán")) == 1 and tried == ["gemini", "nvidia", "local"]
    tried.clear()
    jv.studio_generate("un volcán")
    assert tried[0] == "local"                                    # los que fallaron descansan: directo al que sí puede


def test_foto_privada_solo_en_el_pc(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.studio, "items", [])
    monkeypatch.setitem(jv.settings, "image_provider", "auto")
    monkeypatch.setitem(jv.settings, "img_private", True)
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    _keys(jv, monkeypatch, gemini=True, local=True)
    foto = tmp_path / "foto.png"
    foto.write_bytes(_png())
    tried = []
    monkeypatch.setattr(jv, "_one_image", lambda prov, *a, **k: (tried.append(prov), (_png(), ".png"))[1])
    jv.studio_generate("", src=str(foto), instruccion="ponle un sombrero")
    assert tried == ["local"]


def test_generador_del_pc(jv, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(jv, "im73_paths", lambda: ("sd-cli", "m.gguf"))

    class R:
        returncode = 0
        stdout = stderr = b""

    def run(args, cwd=None, **k):
        calls.append(args)
        open(args[args.index("-o") + 1], "wb").write(_png())
        return R()
    import nucleo.imagen73 as M
    monkeypatch.setattr(M.subprocess, "run", run)
    raw, ext = jv.im73_local("a cat", "3:4")
    assert raw == _png() and ext == ".png" and calls[0][calls[0].index("-W") + 1] == "448"
    monkeypatch.setattr(jv, "im73_paths", lambda: ("", ""))
    try:
        jv.im73_local("a cat")
        assert False
    except jv.AIError as e:
        assert "instala el generador" in e.why


def test_voz_generadores(jv, ask, monkeypatch):
    _keys(jv, monkeypatch)
    who, said = ask("¿qué generadores de imágenes tengo?")
    assert "FLUX (NVIDIA)" in said and "instala el generador" in said
    started = []
    monkeypatch.setattr(jv, "im73_install_job", lambda: started.append(1) or True)
    who, said = ask("instala el generador de imágenes")
    assert started and "2 GB" in said
    applied = []
    monkeypatch.setattr(jv, "apply_settings", lambda d: applied.append(d))
    ask("crea las imágenes con flux")
    assert applied[-1] == {"image_provider": "nvidia"}


# ============================================================================ LA IA SEGÚN EL TRABAJO Y NUNCA PARADO
def test_codigo_lo_hace_la_mejor_para_programar(jv, monkeypatch):
    import nucleo.ia as IA
    monkeypatch.setattr(jv, "ai_chat", IA.ai_chat)
    monkeypatch.setitem(jv.settings, "ai_provider", "gemini")
    monkeypatch.setitem(jv.settings, "gemini_api_key", "g")
    monkeypatch.setitem(jv.settings, "nvidia_api_key", "nvapi-x")
    monkeypatch.setitem(jv.settings, "ai_heavy_provider", "off")
    monkeypatch.setattr(jv, "net_preflight", lambda: False)
    used = []
    monkeypatch.setattr(jv, "_cloud_chat", lambda c, m, j=False, max_tokens=None, **k: (used.append((c["ai_provider"], c["model"])), "ok")[1])
    monkeypatch.setattr(jv, "_ensure_model", lambda c: c)
    jv._tl.task = "code"
    try:
        assert jv.ai_chat([{"role": "user", "content": "revisa"}]) == "ok"
    finally:
        jv._tl.task = ""
    assert used[-1] == ("nvidia", "moonshotai/kimi-k3.1-pro")
    jv.ai_chat([{"role": "user", "content": "hola"}])
    assert used[-1][0] == "gemini"                                 # lo de siempre, con tu IA de siempre


def test_nunca_parado_y_va_directo_al_que_responde(jv, monkeypatch):
    monkeypatch.setitem(jv.settings, "ai_backup_provider", "auto")
    monkeypatch.setitem(jv.settings, "gemini_api_key", "g")
    monkeypatch.setitem(jv.settings, "nvidia_api_key", "")
    monkeypatch.setitem(jv.settings, "iteracompute_api_key", "")
    monkeypatch.setitem(jv.settings, "deepseek_api_key", "d")
    monkeypatch.setitem(jv.settings, "zai_api_key", "z")
    monkeypatch.setattr(jv, "motor_ready", lambda: False)
    monkeypatch.setattr(jv, "_ensure_model", lambda c: c)
    monkeypatch.setattr(jv, "_try_other_models", lambda c, fn, e, tries=2: (_ for _ in ()).throw(e))
    calls = []

    def fn(c):
        calls.append(c["ai_provider"])
        if c["ai_provider"] in ("gemini", "deepseek"):
            raise jv.AIError("lleno", kind="quota", code=429, why="sin cupo")
        return "respuesta"
    cfg = jv._ai_cfg({"ai_provider": "gemini"})
    jv._tl.c73_names = False
    assert jv._with_fallback(cfg, fn) == "respuesta" and calls == ["gemini", "deepseek", "zai"]
    calls.clear()
    assert jv._with_fallback(cfg, fn) == "respuesta" and calls == ["zai"]      # gemini y deepseek descansan: directo
    jv.c73["down"].clear()
    jv._tl.c73_names = True                                       # con nombres de estudiantes, nunca a China
    calls.clear()
    try:
        jv._with_fallback(cfg, fn)
        assert False
    except jv.AIError:
        assert "zai" not in calls
    jv._tl.c73_names = False


# ============================================================================ GENERAR CÓDIGO REVISADO
def test_generar_codigo_se_corrige_solo(jv, monkeypatch, tmp_path):
    monkeypatch.setitem(jv.settings, "output_dir", str(tmp_path))
    answers = [json.dumps({"codigo": "def promedio(a, b)\n    return (a + b) / 2\n", "explicacion": "Saca el promedio.",
                           "como_probarlo": ["4 y 5 → 4.5"], "nombre": "promedio"}),
               json.dumps({"codigo": "def promedio(a, b):\n    return (a + b) / 2\n"})]
    tasks = []

    def chat(msgs, json_mode=False, max_tokens=None):
        tasks.append(getattr(jv._tl, "task", ""))
        return answers.pop(0)
    monkeypatch.setattr(jv, "ai_chat", chat)
    g = jv.code_generate("una función que saque el promedio de dos números", "Python")
    assert g["errores"] == [] and g["correcciones"] == 1 and "def promedio(a, b):" in g["codigo"]
    assert os.path.exists(g["ruta"]) and g["ruta"].endswith(".py") and tasks == ["code", "code"]
    assert "no tiene errores de sintaxis" in jv.code_generate_text(g) and "no lo ejecuté" in jv.code_generate_text(g)


def test_voz_generar_codigo(jv, ask, monkeypatch):
    got = []
    monkeypatch.setattr(jv, "_cd_gen_job", lambda desc, lang: got.append((desc, lang)))
    who, said = ask("escribe un programa en python que pida tres notas y diga si el estudiante aprobó")
    assert got and got[-1][1] == "Python" and "analizador" in said
    ask("hazme una página web que muestre un reloj")
    assert got[-1][1] == "HTML"
    got.clear()
    ask("crea un programa para el área de matemáticas de grado sexto")
    assert not got                                                # eso es un plan, no código


# ============================================================================ EL ESTUDIO CREATIVO
def test_estudio_pagina_y_api(jv, monkeypatch, tmp_path):
    c = jv.app.test_client()
    html = c.get("/estudio?tab=codigo").get_data(as_text=True)
    assert "Estudio creativo" in html and '"codigo"' in html
    st = c.get("/estudio/api/estado").get_json()
    assert {"imagenes", "ia", "galeria", "jobs"} <= set(st) and any(i["id"] == "local" for i in st["imagenes"]["items"])
    assert c.post("/estudio/api/imagen", json={"tema": ""}).get_json()["ok"] is False
    assert c.post("/estudio/api/codigo", json={"accion": "revisar", "codigo": ""}).get_json()["ok"] is False
    jobs = []
    monkeypatch.setattr(jv, "start_job", lambda label, fn, name="": (jobs.append(label), fn()))
    monkeypatch.setattr(jv, "code_review_data", lambda code, name="", goal="": (
        {"resumen": "Suma.", "errores": [], "mejoras": [], "pasos": [], "nivel": "", "corregido": ""}, "Python", []))
    r = c.post("/estudio/api/codigo", json={"accion": "revisar", "codigo": "print(1+1)"}).get_json()
    assert r["ok"] and jv.e73["jobs"][r["job"]]["estado"] == "listo" and jv.e73["jobs"][r["job"]]["res"]["resumen"] == "Suma."
    assert c.get("/estudio/archivo/999").status_code == 404
    assert c.get("/estudio/api/estado", environ_base={"REMOTE_ADDR": "192.168.1.9"}).status_code == 403    # solo este equipo


def test_voz_abrir_estudio(jv, ask, monkeypatch):
    opened = []
    monkeypatch.setattr(jv, "open_window", lambda path, title: opened.append(path))
    ask("abre el estudio de código")
    assert opened[-1] == "/estudio?tab=codigo"
    ask("abre el estudio creativo")
    assert opened[-1] == "/estudio?tab=imagenes"
    n = len(opened)
    ask("abre el estudio de cine")
    assert len(opened) == n                                       # ese es otro (el de las películas)
