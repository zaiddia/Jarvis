"""La IA local dentro de Jarvis (12.6): el motor llama.cpp («llama-server», el mismo que usan Ollama y LM Studio por
dentro) y un modelo GGUF, descargados una sola vez a la carpeta de Jarvis. Jarvis lo enciende solo cuando hace falta
(sin internet, o si lo eliges como IA) y lo apaga cuando no se usa. No hay que instalar ni abrir Ollama. Lógica pura.
"""
import os
import re

PORT = 8091
RELEASES_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=8"

# Modelos que se probaron bien en español para tareas de docente (cuantización Q4_K_M: buena calidad y liviana).
CATALOG = [
    {"id": "qwen3-4b", "nombre": "Qwen3 4B Instruct (recomendado)", "repo": "unsloth/Qwen3-4B-Instruct-2507-GGUF", "patron": "Q4_K_M", "gb": 2.5,
     "ram": 8},
    {"id": "gemma3-4b", "nombre": "Gemma 3 4B", "repo": "unsloth/gemma-3-4b-it-GGUF", "patron": "Q4_K_M", "gb": 2.5, "ram": 8},
    {"id": "llama3.2-3b", "nombre": "Llama 3.2 3B", "repo": "unsloth/Llama-3.2-3B-Instruct-GGUF", "patron": "Q4_K_M", "gb": 2.0, "ram": 6},
    {"id": "gemma3-1b", "nombre": "Gemma 3 1B (liviano)", "repo": "unsloth/gemma-3-1b-it-GGUF", "patron": "Q4_K_M", "gb": 0.8, "ram": 4},
]


def asset_suffix(is_win=True, gpu=False):
    """12.7: con tarjeta gráfica, la versión Vulkan (sirve para casi cualquier GPU: Intel, AMD o NVIDIA)."""
    if is_win:
        return "bin-win-vulkan-x64.zip" if gpu else "bin-win-cpu-x64.zip"
    return "bin-ubuntu-vulkan-x64.tar.gz" if gpu else "bin-ubuntu-x64.tar.gz"


def pick_release(releases, is_win=True, gpu=False):
    """(url, nombre, versión) del motor más nuevo que tenga el archivo para este sistema (no todas las versiones lo traen)."""
    suf = asset_suffix(is_win, gpu)
    for rel in releases or []:
        for a in rel.get("assets") or []:
            if str(a.get("name", "")).endswith(suf) and a.get("browser_download_url", "").startswith("https://"):
                return a["browser_download_url"], a["name"], rel.get("tag_name", "")
    return None


def pick_gguf(siblings, patron="Q4_K_M"):
    """El archivo .gguf del modelo con esa cuantización (sin los de visión «mmproj» ni los partidos en varias piezas)."""
    names = [s.get("rfilename", s) if isinstance(s, dict) else str(s) for s in siblings or []]
    ok = [n for n in names if n.lower().endswith(".gguf") and "mmproj" not in n.lower() and not re.search(r"-\d{5}-of-\d{5}", n)]
    exact = [n for n in ok if patron.lower() in n.lower()]
    if exact:
        return sorted(exact, key=len)[0]
    q4 = [n for n in ok if re.search(r"q4", n, re.I)]
    return sorted(q4, key=len)[0] if q4 else (ok[0] if ok else "")


def hf_api(repo):
    return f"https://huggingface.co/api/models/{repo}"


def hf_file(repo, name):
    return f"https://huggingface.co/{repo}/resolve/main/{name}"


def recommend(ram_gb, free_gb):
    """El mejor modelo del catálogo que cabe en la memoria y en el disco. → entrada o None."""
    for m in CATALOG:
        if ram_gb >= m["ram"] and free_gb >= m["gb"] + 1.0:
            return m
    return None


def by_id(mid):
    return next((m for m in CATALOG if m["id"] == mid), None)


def server_args(exe, model_path, port=PORT, ctx=4096, threads=0, threads_batch=0, gpu=False):
    """12.7, más rápida: un solo turno a la vez con todo el contexto (-np 1), reusa lo ya leído del mensaje anterior
    (--cache-reuse: el «system prompt» de Jarvis no se vuelve a procesar en cada pregunta), atención rápida (-fa auto)
    y, si hay tarjeta gráfica, el modelo entero en ella (-ngl 99)."""
    a = [exe, "-m", model_path, "--host", "127.0.0.1", "--port", str(port), "-c", str(ctx), "--jinja", "--no-webui",
         "-np", "1", "--cache-reuse", "256", "-fa", "auto", "-ngl", "99" if gpu else "0"]
    if threads:
        a += ["-t", str(threads)]
    if threads_batch:
        a += ["-tb", str(threads_batch)]
    return a


def find_exe(folder, is_win=True, skip=("gpu",)):
    """llama-server dentro de lo que se descomprimió (puede venir en una subcarpeta). La versión GPU vive en «gpu»."""
    want = "llama-server.exe" if is_win else "llama-server"
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in skip]
        if want in files:
            return os.path.join(root, want)
    return ""


def tokens_per_second(resp):
    """La velocidad que informa llama-server en «timings» (palabras-token por segundo al responder)."""
    try:
        return float((resp.get("timings") or {}).get("predicted_per_second") or 0)
    except (AttributeError, TypeError, ValueError):
        return 0.0


def trim_context(text, limit=1500):
    """Para la IA local: el contexto dinámico más corto (cada carácter es tiempo de lectura en un computador sin GPU)."""
    text = str(text or "")
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


_THINK = re.compile(r"<think>.*?</think>\s*", re.S)


def clean_reply(text):
    """Algunos modelos «piensan» en voz alta entre <think>…</think>: eso no se dice."""
    return _THINK.sub("", str(text or "")).strip()
