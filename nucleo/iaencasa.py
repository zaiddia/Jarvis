"""12.2: cerebro local, la mejor IA que cabe en tu computador para trabajar sin internet ni clave.

«¿Qué IA puedo usar sin internet?» analiza tu equipo (memoria, disco, Ollama) y te dice si es posible y qué cabe.
«Prepara la IA sin internet» descarga los modelos candidatos, los prueba con tareas reales de docente midiendo la
velocidad y deja el mejor que pase como IA sin internet (Ajustes › IA › Sin internet). «Instala Ollama» lo instala con
winget. La lógica está en cerebrolocal.py. Los nombres globales de Jarvis se usan como J.<nombre>.
"""
import re
import shutil
import subprocess
import time

import cerebrolocal
from nucleo import J

local_job = {"busy": False, "last": None}


def _ollama_client():
    if J.ollama is None:
        return None
    return J.ollama.Client(host=J.settings["ollama_host"].rstrip("/") or J.DEFAULT_SETTINGS["ollama_host"], timeout=600)


def _ollama_installed():
    try:
        c = _ollama_client()
        if c is None:
            return None
        resp = c.list()
        models = resp.models if hasattr(resp, "models") else resp["models"]
        return [J._model_name(m) for m in models]
    except Exception:
        return None


def analyze():
    """→ el plan de cerebrolocal.plan con los datos de este equipo."""
    ram = J.psutil.virtual_memory().total if J.psutil else 8 * cerebrolocal.GB
    try:
        disk = shutil.disk_usage(J.CONFIG_DIR).free
    except OSError:
        disk = 0
    inst = _ollama_installed()
    return cerebrolocal.plan(ram, disk, inst is not None, inst or ())


def _pull(name, progress=None):
    c = _ollama_client()
    last = 0.0
    for p in c.pull(name, stream=True):
        d = p if isinstance(p, dict) else getattr(p, "__dict__", {})
        tot, done = d.get("total") or 0, d.get("completed") or 0
        if progress and tot and time.time() - last > 2:
            last = time.time()
            progress(name, done / tot)


def _try(name):
    """Corre las pruebas con ese modelo. → resultado para cerebrolocal.verdict."""
    c = _ollama_client()
    out = {"modelo": name, "pruebas": [], "tps": None, "error": ""}
    speeds = []
    for tst in cerebrolocal.TESTS:
        kw = {"format": "json"} if tst["json"] else {}
        r = c.chat(model=name, messages=[{"role": "user", "content": tst["prompt"]}], options={"num_predict": 400, "temperature": 0.2},
                   keep_alive="10m", **kw)
        msg = (r.get("message") if isinstance(r, dict) else r.message)
        text = msg["content"] if isinstance(msg, dict) else msg.content
        ok, note = cerebrolocal.grade(tst["id"], text)
        out["pruebas"].append((tst["id"], ok, note))
        n = (r.get("eval_count") if isinstance(r, dict) else getattr(r, "eval_count", 0)) or 0
        dur = (r.get("eval_duration") if isinstance(r, dict) else getattr(r, "eval_duration", 0)) or 0
        if n and dur:
            speeds.append(n / (dur / 1e9))
    out["tps"] = sum(speeds) / len(speeds) if speeds else 0.0
    return out


def prepare_local(progress=None):
    """Analiza, descarga y prueba. → (modelo elegido o "", frase)."""
    p = J.analyze()
    if not p["posible"]:
        return "", cerebrolocal.spoken_plan(p)
    results = []
    for name in p["modelos"]:
        try:
            J._pull(name, progress)
            results.append(J._try(name))
        except Exception as e:
            results.append({"modelo": name, "pruebas": [], "tps": None, "error": str(e)[:80]})
        best = cerebrolocal.verdict(results)[0]
        if best:
            break                                   # el mejor que cabe ya pasó: no hace falta bajar los más pequeños
    best, msg = cerebrolocal.verdict(results)
    if best:
        J.settings["offline_model"] = best
        try:
            J.save_settings_file()
        except OSError:
            pass
        J.net["local_at"] = 0.0                     # que lo vuelva a buscar ya
        J.local_ai_model(refresh=True)
    local_job["last"] = {"resultados": results, "elegido": best}
    return best, msg


_LB_ASK = re.compile(r"\bque (?:ia|inteligencia artificial|modelo) (?:puedo usar|cabe|me sirve) sin internet\b|\bse puede (?:usar )?la ia sin internet\b|"
                     r"\banaliza (?:mi equipo|el computador) para la ia\b")
_LB_PREP = re.compile(r"\b(?:prepara|instala|descarga|configura)\s+(?:la\s+)?(?:ia|inteligencia artificial|cerebro)\s+(?:sin internet|local|offline)\b|"
                      r"\bprepara tu cerebro local\b")
_LB_OLLAMA = re.compile(r"\b(?:instala|descarga)\s+ollama\b")


def local_brain_voice(text, t):
    if _LB_ASK.search(t):
        J.reply(cerebrolocal.spoken_plan(J.analyze()), "IA LOCAL")
        return True
    if _LB_OLLAMA.search(t):
        if not J.IS_WIN:
            J.reply("Instala Ollama desde https://ollama.com y luego di «prepara la IA sin internet».", "IA LOCAL")
            return True
        def inst():
            try:
                r = subprocess.run(["winget", "install", "--id", "Ollama.Ollama", "-e", "--accept-package-agreements", "--accept-source-agreements"],
                                   capture_output=True, text=True, timeout=1800, creationflags=0x08000000)
                ok = r.returncode == 0
            except Exception:
                ok = False
            J.notify("Listo Ollama. Ahora di «prepara la IA sin internet»." if ok else
                     "No pude instalar Ollama solo. Bájalo de https://ollama.com e instálalo; luego di «prepara la IA sin internet».", "IA LOCAL")
        J.request_approval("instalar", "Instalar Ollama en este computador (con winget)", "Es el programa que corre la IA sin internet. Windows puede "
                           "pedirte permiso de administrador.", on_ok=lambda: (J.reply("Instalo Ollama; te aviso al terminar.", "IA LOCAL"),
                                                                              J.start_job("Instalando Ollama", inst, "ollama")),
                           on_no=lambda: J.reply("Vale, no lo instalo.", "IA LOCAL"), ttl=1800,
                           say="¿Instalo Ollama en este computador? Windows puede pedirte permiso. Di «sí» o «no».")   # 12.4: con tu «sí»
        return True
    if _LB_PREP.search(t):
        if local_job["busy"]:
            J.reply("Ya estoy preparando la IA sin internet; te aviso.", "IA LOCAL")
            return True
        p = J.analyze()
        if not p["posible"]:
            J.reply(cerebrolocal.spoken_plan(p), "IA LOCAL")
            return True

        def prog(name, frac):
            J.log_terminal(f"Descargando {name}: {int(frac * 100)} %", "IA LOCAL")

        def work():
            try:
                _best, msg = prepare_local(prog)
            except Exception as e:
                msg = f"No pude preparar la IA sin internet: {e}"
            finally:
                local_job["busy"] = False
            J.notify(msg, "IA LOCAL")
        def go():
            if local_job["busy"]:
                return
            local_job["busy"] = True
            J.reply(f"Preparo la IA sin internet: bajo {p['modelos'][0]} y lo pruebo con un quiz, una cuenta y una explicación, midiendo la "
                    "velocidad. Si no pasa, pruebo uno más liviano. Te aviso.", "IA LOCAL")
            J.start_job("Preparando la IA sin internet", work, "ia-local")
        J.request_approval("instalar", f"Descargar la IA sin internet ({p['modelos'][0]}, varios GB)", "Ocupa espacio en el disco y la descarga puede tardar "
                           "un buen rato.", on_ok=go, on_no=lambda: J.reply("Vale, no la descargo.", "IA LOCAL"), ttl=1800,
                           say=f"Voy a descargar {p['modelos'][0]}, que pesa varios gigas. ¿Lo hago? Di «sí» o «no».")   # 12.4: con tu «sí»
        return True
    return False


__all__ = ['_LB_ASK', '_LB_OLLAMA', '_LB_PREP', '_ollama_installed', '_ollama_client', '_pull', '_try', 'analyze', 'cerebrolocal', 'local_brain_voice',
           'local_job', 'prepare_local']
