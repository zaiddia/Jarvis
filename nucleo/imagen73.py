"""12.74: más generadores de imágenes y el orden automático entre todos.

  · FLUX.1-schnell en NVIDIA Build (la misma clave de NVIDIA de la IA, gratis mientras dure su prueba).
  · El generador integrado en tu PC: stable-diffusion.cpp + SD-Turbo (2 GB). Sin internet y sin que nada salga del
    equipo; calidad sencilla. «Jarvis, instala el generador de imágenes».
  · El orden lo decide Jarvis según el pedido: con letras (cartel, título…) primero Gemini o ChatGPT; una foto tuya en
    «fotos privadas» (Ajustes › Imágenes) o sin internet, solo el de tu PC; el que falló hace poco pasa al final por un rato, para
    no esperar por él. Si uno no puede, sigue el siguiente: nunca se queda parado.

La lógica pura está en imagenlocal.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile

import imagenlocal as IL
from nucleo import J

im73 = {"cool": {}, "job": False, "msg": "", "en": {}, "lock": threading.Lock()}
IM73_TIMEOUT = 15 * 60


def _im73_dir(*parts):
    return os.path.join(J.CONFIG_DIR, "imagenes_pc", *parts)


def im73_paths():
    """(sd-cli, modelo) o ("", "")."""
    be = J.settings.get("img_local_backend", "gpu")
    exe = ""
    for b in ([be] + [x for x in ("gpu", "cpu") if x != be]):
        d = _im73_dir("bin", b)
        exe = IL.find_cli(d, J.IS_WIN) if os.path.isdir(d) else ""
        if exe:
            break
    model = _im73_dir("modelo", IL.MODEL_FILE)
    return (exe, model) if exe and os.path.exists(model) else ("", "")


def im73_ready():
    return bool(J.im73_paths()[0])


# ============================================================================ INSTALAR
def _im73_engine(gpu, progress=None):
    dest = _im73_dir("bin", "gpu" if gpu else "cpu")
    exe = IL.find_cli(dest, J.IS_WIN) if os.path.isdir(dest) else ""
    if exe:
        return exe
    releases = J._motor_get_json(IL.RELEASES_API)
    rel = IL.pick_release(releases, J.IS_WIN, gpu)
    if not rel:
        raise ValueError("no encontré el generador para este sistema en las versiones de stable-diffusion.cpp")
    url, name, tag = rel
    os.makedirs(dest, exist_ok=True)
    arc = J._motor_fetch(url, _im73_dir(name), progress, "el generador" + (" (tarjeta gráfica)" if gpu else ""))
    J.verify_download(arc, J.motorlocal.asset_sha256(releases, name), "el generador de imágenes")
    with zipfile.ZipFile(arc) as z:
        z.extractall(dest)
    os.remove(arc)
    exe = IL.find_cli(dest, J.IS_WIN)
    if not exe:
        raise ValueError("el archivo del generador no trae sd-cli")
    if not J.IS_WIN:
        os.chmod(exe, 0o755)
    with open(os.path.join(dest, "version.txt"), "w", encoding="utf-8") as f:
        f.write(tag)
    return exe


def _im73_model(progress=None):
    dst = _im73_dir("modelo", IL.MODEL_FILE)
    if os.path.exists(dst):
        return dst
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    free = shutil.disk_usage(os.path.dirname(dst)).free / 1e9
    if free < IL.MODEL_GB + 1:
        raise ValueError(f"necesito unos {IL.MODEL_GB + 1:.0f} GB libres en el disco y hay {free:.1f} GB")
    J._motor_fetch(J.motorlocal.hf_file(IL.MODEL_REPO, IL.MODEL_FILE), dst, progress, "el modelo de imágenes")
    J.verify_download(dst, IL.MODEL_SHA, "el modelo de imágenes")
    return dst


def _im73_try(be):
    """Una imagen de prueba con ese motor. → segundos que tardó, o None si no arrancó."""
    J.settings["img_local_backend"] = be
    if not IL.find_cli(_im73_dir("bin", be), J.IS_WIN):
        return None
    t0 = time.time()
    try:
        J.im73_local("a red apple on a wooden table, simple illustration", "1:1", timeout=600)
    except Exception as e:
        J.log_terminal(f"El generador con {'la tarjeta gráfica' if be == 'gpu' else 'el procesador'} no arrancó: {str(e)[:120]}", "IMAGEN")
        return None
    return time.time() - t0


def im73_install_job():
    if im73["job"]:
        return False
    im73["job"] = True

    def prog(label, frac):
        im73["msg"] = f"Descargando {label}: {int(frac * 100)} %"
        try:
            J.socketio.emit("estudio73", {"tipo": "progreso", "msg": im73["msg"]})
        except Exception:
            pass

    def work():
        try:
            for gpu in (True, False):
                try:
                    _im73_engine(gpu, prog)
                except Exception as e:
                    if not gpu:
                        raise
                    J.log_terminal(f"Sin la versión con tarjeta gráfica del generador: {e}", "IMAGEN")
            _im73_model(prog)
            im73["msg"] = "Probando la velocidad…"
            res = {be: s for be in ("gpu", "cpu") if (s := _im73_try(be)) is not None}
            if not res:
                msg = "Descargué el generador de imágenes, pero no arrancó en este equipo (puede faltar memoria)."
            else:
                best = min(res, key=res.get)
                J.settings["img_local_backend"] = best
                try:
                    J.save_settings_file()
                except OSError:
                    pass
                where = "con la tarjeta gráfica" if best == "gpu" else "con el procesador"
                msg = (f"Listo el generador de imágenes de tu PC ({where}: unos {res[best]:.0f} s por imagen). Lo uso sin internet, "
                       "para las fotos privadas y cuando los de la nube no tengan cupo. La calidad es sencilla. "
                       f"Modelo SD-Turbo, {IL.MODEL_LICENSE}.")
        except Exception as e:
            msg = f"No pude instalar el generador de imágenes: {str(e)[:160]}"
        finally:
            im73["job"] = False
            im73["msg"] = ""
        J.notify(msg, "IMAGEN")
    J.start_job("Instalando el generador de imágenes", work, "imagen-pc")
    return True


# ============================================================================ CREAR
def im73_local(prompt, aspect="", src=None, timeout=IM73_TIMEOUT):
    """(bytes PNG, ".png") hecha en tu PC con sd-cli."""
    exe, model = J.im73_paths()
    if not exe:
        raise J.AIError("El generador de imágenes de tu PC no está instalado.", kind="config",
                        why="el generador de tu PC no está instalado (di «instala el generador de imágenes»)")
    tmp = tempfile.mkdtemp(prefix="jarvis-img-")
    out = os.path.join(tmp, "salida.png")
    init = ""
    if src:
        init = os.path.join(tmp, "entrada.png")
        w, h = IL.LOCAL_SIZES.get(aspect, IL.LOCAL_SIZES["1:1"])
        from PIL import Image
        Image.open(src).convert("RGB").resize((w, h)).save(init)
    args = IL.cli_args(exe, model, prompt, out, aspect, seed=int(time.time()) % 100000, threads=J._phys(), init=init)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        with im73["lock"]:                             # una a la vez: el PC no da para dos
            r = subprocess.run(args, cwd=tmp, capture_output=True, timeout=timeout, creationflags=flags)
        if r.returncode != 0 or not os.path.exists(out):
            tail = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
            raise J.AIError(f"sd-cli falló: {tail[0][:200]}", kind="server", why="el generador de tu PC no pudo con esa imagen")
        with open(out, "rb") as f:
            return f.read(), ".png"
    except subprocess.TimeoutExpired:
        raise J.AIError("sd-cli tardó demasiado", kind="server", why="el generador de tu PC tardó demasiado")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def im73_nvidia(cfg, prompt, aspect=""):
    data = J._http("POST", IL.NV_URL, {"Authorization": f"Bearer {cfg['key']}", "Accept": "application/json"},
                   IL.nv_payload(prompt, aspect, seed=int(time.time()) % 100000), timeout=180)
    return IL.nv_extract(data)


def im73_english(prompt):
    """El pedido (en español) como un prompt corto en inglés para FLUX y SD-Turbo. Sin IA, va tal cual."""
    key = str(prompt or "")[:600]
    if key in im73["en"]:
        return im73["en"][key]
    try:
        out = J.ai_chat([{"role": "system", "content": IL.english_prompt_rule()}, {"role": "user", "content": key}], max_tokens=200)
        out = re.sub(r"\s+", " ", str(out or "")).strip().strip('"')[:700] or key
    except Exception:
        out = key
    im73["en"][key] = out
    if len(im73["en"]) > 50:
        im73["en"].pop(next(iter(im73["en"])))
    return out


# ============================================================================ QUIÉN LA HACE
def im73_cfgs():
    """{nombre: cfg} de los generadores que se pueden usar ahora (con clave o instalados)."""
    out = {}
    g = J._gemini_for_stt()
    if g and J.image_model():
        out["gemini"] = g
    for pid in ("chatgpt", "sensenova", "nvidia"):
        c = J._ai_cfg({"ai_provider": pid})
        if c.get("key"):
            out[pid] = c
    if J.im73_ready():
        out["local"] = {"label": "PC"}
    return out


def im73_order(tema="", own_photo=False):
    """[(nombre, cfg)] en el orden en que se intentan."""
    cfgs = J.im73_cfgs()
    seq = IL.order(list(cfgs), getattr(J._tl, "img_pref", "") or J.settings.get("image_provider", "auto"), J.settings.get("ai_provider", ""), tema, own_photo,
                   offline=bool(J.net.get("offline")), private=bool(J.settings.get("img_private")), cool=im73["cool"])
    return [(n, cfgs[n]) for n in seq]


def im73_failed(prov, kind):
    """Uno no pudo: descansa un rato (para no esperar por él en la próxima)."""
    im73["cool"][prov] = IL.cool_until(kind)


def im73_status():
    cfgs = J.im73_cfgs()
    now = time.time()
    items = []
    for n in ("gemini", "chatgpt", "nvidia", "sensenova", "local"):
        st = "listo" if n in cfgs else ("instalando" if n == "local" and im73["job"] else "sin configurar")
        if n in cfgs and im73["cool"].get(n, 0) > now:
            st = f"descansando {int((im73['cool'][n] - now) / 60) + 1} min"
        items.append({"id": n, "nombre": IL.NAMES[n][:1].upper() + IL.NAMES[n][1:], "estado": st})
    return {"items": items, "elegido": J.settings.get("image_provider", "auto"), "msg": im73["msg"],
            "orden": [IL.NAMES[n][:1].upper() + IL.NAMES[n][1:] for n, _ in J.im73_order()]}


# ============================================================================ POR VOZ
_IM73_INST = re.compile(r"\b(?:instala|descarga|baja|prepara)(?:me)?\s+(?:el\s+)?generador\s+de\s+imagenes(?:\s+(?:integrado|local|en mi (?:pc|equipo|computador)|de mi (?:pc|equipo|computador)|sin internet))?\b")
_IM73_ASK = re.compile(r"\b(?:que|cuales)\s+generadores?\s+de\s+imagenes\s+(?:tengo|hay|usas|tienes)\b|\bcon\s+que\s+(?:creas|haces|generas)\s+(?:las\s+)?imagenes\b")
_IM73_USE = re.compile(r"^(?:jarvis\s+)?(?:usa|pon|crea las imagenes con|haz las imagenes con|genera las imagenes con)\s+(?:el\s+)?(?:generador\s+(?:de\s+imagenes\s+)?)?"
                       r"(?:de\s+)?(flux|nvidia|gemini|chatgpt|sensenova|mi pc|mi equipo|mi computador|local|automatico)(?:\s+para\s+(?:las\s+)?imagenes)?$")
_IM73_MAP = {"flux": "nvidia", "nvidia": "nvidia", "gemini": "gemini", "chatgpt": "chatgpt", "sensenova": "sensenova", "mi pc": "local",
             "mi equipo": "local", "mi computador": "local", "local": "local", "automatico": "auto"}


def imagen73_voice(text, t):
    if _IM73_INST.search(t):
        if J.im73_ready():
            J.reply("El generador de imágenes de tu PC ya está instalado.", "IMAGEN")
        elif J.im73_install_job():
            J.reply(f"Instalo el generador de imágenes de tu PC: baja unos {IL.MODEL_GB:.0f} GB (el motor y el modelo SD-Turbo) y "
                    "prueba si va mejor con la tarjeta gráfica o con el procesador. Te aviso al terminar.", "IMAGEN")
        else:
            J.reply("Ya lo estoy instalando.", "IMAGEN")
        return True
    if _IM73_ASK.search(t):
        st = J.im73_status()
        ok = [i["nombre"] for i in st["items"] if i["estado"] == "listo"]
        rest = [f"{i['nombre']} ({i['estado']})" for i in st["items"] if i["estado"].startswith("descansando")]
        msg = ("Puedo crear imágenes con " + ", ".join(ok) + "." if ok else "Todavía no tengo ningún generador de imágenes listo.")
        if rest:
            msg += " Descansando un rato porque fallaron hace poco: " + ", ".join(rest) + "."
        if st["orden"]:
            msg += " Ahora mismo probaría en este orden: " + ", ".join(st["orden"]) + "."
        if not J.im73_ready():
            msg += " Para crearlas sin internet, di «instala el generador de imágenes»."
        J.reply(msg, "IMAGEN")
        return True
    m = _IM73_USE.match(t)
    if m:
        pid = _IM73_MAP[m.group(1)]
        if pid == "local" and not J.im73_ready():
            J.reply("Primero hay que instalarlo: di «instala el generador de imágenes».", "IMAGEN")
            return True
        J.apply_settings({"image_provider": pid})
        J.reply("Listo: las imágenes las elijo yo según lo que pidas." if pid == "auto" else
                f"Listo: las imágenes las hago primero con {IL.NAMES[pid]}; si no puede, sigo con los demás.", "IMAGEN")
        return True
    return False


__all__ = ["IM73_TIMEOUT", "im73", "im73_cfgs", "im73_english", "im73_failed", "im73_install_job", "im73_local", "im73_nvidia",
           "im73_order", "im73_paths", "im73_ready", "im73_status", "imagen73_voice", "_IM73_ASK", "_IM73_INST", "_IM73_USE"]
