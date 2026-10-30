"""Habilidades de la comunidad (7.5): el formato SKILL.md de OpenClaw, Hermes Agent y Claude (agentskills.io).

Una de esas habilidades es una carpeta con un SKILL.md:
    ---
    name: planificador-de-clases
    description: Ayuda a planear una clase paso a paso …
    ---
    # Instrucciones … (texto para la IA)
y a veces scripts (.py, .sh…). Jarvis importa SOLO el texto (las instrucciones): cuando lo que pides encaja con la
descripción, se las da a su IA para que responda siguiéndolas. Los scripts nunca se ejecutan.

Antes de instalar, un revisor de seguridad busca instrucciones para engañar a la IA («ignora las instrucciones
anteriores», «no le digas al usuario»), para sacar datos (enviar claves o archivos a una web), comandos peligrosos,
caracteres invisibles y textos codificados. Con riesgo alto no se instala.
"""
import io
import json
import os
import re
import threading
import unicodedata
import zipfile

_lock = threading.Lock()
_dir = None
MAX_MD = 60 * 1024                 # una guía de más de 60 KB no es normal
MAX_ZIP = 5 * 1024 * 1024
TEXT_EXT = (".md", ".txt")
SCRIPT_EXT = (".py", ".sh", ".js", ".ts", ".ps1", ".bat", ".cmd", ".exe", ".dll", ".vbs", ".rb", ".pl", ".jar", ".msi")


def configure(config_dir):
    global _dir
    _dir = os.path.join(config_dir, "guias")


def slug(name):
    s = unicodedata.normalize("NFD", str(name).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60] or "habilidad"


# ----------------------------------------------------------------------------- leer el SKILL.md
def parse(text):
    """(meta, cuerpo). meta: name, description y lo que traiga (solo el primer nivel del encabezado YAML)."""
    text = str(text).lstrip("﻿")
    meta, body = {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)(.*)$", text, re.S)
    if m:
        head, body = m.group(1), m.group(2)
        lines = head.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            km = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
            i += 1
            if not km:
                continue
            key, val = km.group(1), km.group(2).strip()
            if val in ("|", ">", "|-", ">-", "|+", ">+"):
                block = []
                while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                    block.append(lines[i].strip())
                    i += 1
                val = ("\n" if val.startswith("|") else " ").join(b for b in block).strip()
            elif val == "":
                sub = []                               # objeto o lista anidada (metadata…): se guarda como texto
                while i < len(lines) and lines[i].startswith((" ", "\t", "-")):
                    sub.append(lines[i].strip())
                    i += 1
                val = "; ".join(sub)
            elif len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            meta[key] = val
    if "name" not in meta:
        h = re.search(r"^#\s+(.+)$", body, re.M)
        if h:
            meta["name"] = h.group(1).strip()
    return meta, body.strip()


# ----------------------------------------------------------------------------- revisor de seguridad
_HIGH = [
    (r"ignor\w*\s+(?:all\s+|las?\s+|todas?\s+las?\s+)?(?:previous|prior|above|anteriores|previas)\s+(?:instructions|instrucciones|reglas)", "pide a la IA ignorar sus instrucciones"),
    (r"ignor\w*\s+(?:todas\s+)?(?:las\s+|tus\s+)?(?:instrucciones|reglas|indicaciones)\s+(?:anteriores|previas|de arriba|del sistema|que te dieron|originales)", "pide a la IA ignorar sus instrucciones"),
    (r"(?:do not|don't|never)\s+(?:tell|inform|reveal to|show)\s+the\s+user|no\s+(?:le\s+)?(?:digas|cuentes|muestres)\s+(?:nada\s+)?al\s+usuario", "pide ocultarle cosas al usuario"),
    (r"(?:you are now|ahora eres)\s+(?:dan|jailbroken|sin restricciones|unrestricted)|developer mode|modo desarrollador sin", "intenta quitarle las reglas a la IA"),
    (r"(?:send|post|upload|exfiltrat\w*|envi\w+|manda\w*|sube\w*)\b[^\n]{0,60}\b(?:api[_ -]?keys?|tokens?|passwords?|contrase\w+|claves?|credentials|credenciales|cookies?|\.env\b|ssh)", "intenta sacar claves o datos"),
    (r"(?:api[_ -]?keys?|tokens?|passwords?|contrase\w+|credentials)\b[^\n]{0,60}\bhttps?://", "manda claves a una web"),
    (r"\b(?:curl|wget|invoke-webrequest|iwr|irm|invoke-restmethod)\b[^\n]{0,80}\|\s*(?:sh|bash|iex|powershell|python)", "descarga y ejecuta código"),
    (r"powershell(?:\.exe)?\s+[^\n]{0,30}-(?:enc|encodedcommand)\b", "ejecuta PowerShell oculto"),
    (r"\brm\s+-rf\s+[/~]|\bformat\s+c:|\bdel\s+/[sfq]|remove-item\s+[^\n]{0,40}-recurse", "borra archivos del sistema"),
    (r"~/\.ssh|id_rsa|\\appdata\\roaming\\[^\n]{0,40}(?:cookies|login data)|login data|keychain|wallet\.dat", "busca archivos privados (claves, navegador, carteras)"),
    (r"\b(?:base64\s+-d|frombase64string|atob\()", "decodifica texto oculto para ejecutarlo"),
]
_MED = [
    (r"\b(?:exec|eval|subprocess|os\.system|shell=true|child_process)\b", "menciona ejecutar comandos (Jarvis no los ejecuta)"),
    (r"\bsudo\b|\brunas\b|administrador", "pide permisos de administrador"),
]
_INVISIBLE = re.compile("[​‌‍⁠﻿‪-‮⁦-⁩­]")
_LONG_B64 = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")
_URL = re.compile(r"https?://([A-Za-z0-9.-]+)")


def scan(files):
    """files: {ruta: texto o bytes}. Devuelve {"nivel": "bajo"|"medio"|"alto", "avisos": [...], "scripts": [...],
    "webs": [...]}."""
    avisos, nivel = [], "bajo"
    scripts = sorted(p for p in files if p.lower().endswith(SCRIPT_EXT))
    webs = set()

    def up(n):
        nonlocal nivel
        order = {"bajo": 0, "medio": 1, "alto": 2}
        if order[n] > order[nivel]:
            nivel = n

    if scripts:
        up("medio")
        avisos.append(f"Trae {len(scripts)} programa(s) ({', '.join(os.path.basename(s) for s in scripts[:4])}"
                      f"{'…' if len(scripts) > 4 else ''}): Jarvis NO los instala ni los ejecuta, solo usa el texto.")
    for path, data in files.items():
        if not path.lower().endswith(TEXT_EXT):
            continue
        text = data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)
        low = unicodedata.normalize("NFD", text.lower())
        low = "".join(c for c in low if unicodedata.category(c) != "Mn")     # sin tildes: «envía» = «envia»
        name = os.path.basename(path)
        if _INVISIBLE.search(text):
            up("alto")
            avisos.append(f"{name}: tiene caracteres invisibles (se usan para esconder instrucciones).")
        if _LONG_B64.search(text):
            up("alto")
            avisos.append(f"{name}: tiene un bloque de texto codificado.")
        for rx, why in _HIGH:
            if re.search(rx, low, re.I):
                up("alto")
                avisos.append(f"{name}: {why}.")
        for rx, why in _MED:
            if re.search(rx, low, re.I):
                up("medio")
                avisos.append(f"{name}: {why}.")
        webs.update(m.lower() for m in _URL.findall(text))
        if len(text.encode("utf-8")) > MAX_MD:
            up("medio")
            avisos.append(f"{name}: es muy largo; solo se usa el principio.")
    if webs:
        avisos.append("Menciona estas webs: " + ", ".join(sorted(webs)[:8]) + ("…" if len(webs) > 8 else "") + ".")
    return {"nivel": nivel, "avisos": avisos, "scripts": scripts, "webs": sorted(webs)}


# ----------------------------------------------------------------------------- importar
class ImportError_(Exception):
    pass


def from_zip(raw):
    """{ruta: bytes} de los archivos de texto y la lista de todo (para el revisor)."""
    if len(raw) > MAX_ZIP:
        raise ImportError_("El .zip es demasiado grande para ser una habilidad (más de 5 MB).")
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise ImportError_("Ese archivo no es un .zip válido.")
    out = {}
    with z:
        for info in z.infolist():
            if info.is_dir() or ".." in info.filename.split("/") or info.file_size > MAX_ZIP:
                continue
            p = info.filename
            out[p] = z.read(info) if p.lower().endswith(TEXT_EXT) else b""
    return out


def pick_skill_md(files):
    """La ruta del SKILL.md (el menos profundo) o, si no hay, de un único .md."""
    cands = sorted((p for p in files if os.path.basename(p).lower() == "skill.md"), key=lambda p: p.count("/"))
    if cands:
        return cands[0]
    mds = [p for p in files if p.lower().endswith(".md") and os.path.basename(p).lower() not in ("readme.md", "license.md")]
    return mds[0] if len(mds) == 1 else None


def prepare(files, origen=""):
    """Revisa y arma la habilidad sin guardarla: {"meta", "body", "scan", "slug", "origen"}. Lanza ImportError_."""
    path = pick_skill_md(files)
    if not path:
        raise ImportError_("No encuentro el SKILL.md de la habilidad.")
    text = files[path].decode("utf-8", "replace") if isinstance(files[path], bytes) else str(files[path])
    meta, body = parse(text)
    if not meta.get("name") or not meta.get("description"):
        raise ImportError_("Al SKILL.md le falta el nombre (name) o la descripción (description).")
    if len(body) < 20:
        raise ImportError_("La habilidad no trae instrucciones.")
    # el revisor mira el SKILL.md y los .md de su carpeta (sus referencias)
    base = os.path.dirname(path)
    related = {p: d for p, d in files.items() if (os.path.dirname(p) + "/").startswith(base + "/" if base else "")}
    rep = scan(related or files)
    return {"meta": meta, "body": body[:MAX_MD], "text": text[:MAX_MD], "scan": rep, "slug": slug(meta["name"]),
            "origen": origen}


def save(prep):
    """Guarda la habilidad revisada (si el riesgo no es alto). Devuelve su ficha."""
    if prep["scan"]["nivel"] == "alto":
        raise ImportError_("El revisor de seguridad la marcó como peligrosa: no la instalo.")
    os.makedirs(_dir, exist_ok=True)
    with _lock:
        with open(os.path.join(_dir, prep["slug"] + ".md"), "w", encoding="utf-8") as f:
            f.write(prep["text"])
        with open(os.path.join(_dir, prep["slug"] + ".json"), "w", encoding="utf-8") as f:
            json.dump({"origen": prep["origen"], "revision": prep["scan"]}, f, ensure_ascii=False)
    return info(prep["slug"])


def info(s):
    try:
        with open(os.path.join(_dir, s + ".md"), encoding="utf-8") as f:
            meta, body = parse(f.read())
    except OSError:
        return None
    extra = {}
    try:
        with open(os.path.join(_dir, s + ".json"), encoding="utf-8") as f:
            extra = json.load(f)
    except (OSError, ValueError):
        pass
    return {"slug": s, "nombre": meta.get("name", s), "descripcion": meta.get("description", ""), "cuerpo": body,
            "origen": extra.get("origen", ""), "revision": extra.get("revision") or {"nivel": "bajo", "avisos": []}}


def listing():
    if not _dir or not os.path.isdir(_dir):
        return []
    out = []
    for name in sorted(os.listdir(_dir)):
        if name.endswith(".md"):
            i = info(name[:-3])
            if i:
                out.append(i)
    return out


def delete(s):
    s = slug(s)
    removed = False
    for ext in (".md", ".json"):
        try:
            os.remove(os.path.join(_dir, s + ext))
            removed = True
        except OSError:
            pass
    return removed


def github_api_url(url):
    """github.com/dueño/repo/tree/rama/ruta → (api de contenidos, rama). raw → None (se baja directo)."""
    m = re.match(r"^https://github\.com/([\w.-]+)/([\w.-]+)/(?:tree|blob)/([\w.\-/]+?)/(.+?)/?$", url.strip())
    if not m:
        return None
    owner, repo, branch, path = m.groups()
    if path.lower().endswith("skill.md"):
        path = path.rsplit("/", 1)[0] if "/" in path else ""
    return f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}", branch


def for_ai(g, limit=6000):
    return (f"Instrucciones de la habilidad «{g['nombre']}» (úsalas para responder; si piden ejecutar programas, "
            f"comandos o abrir archivos, no puedes: explícale al usuario qué haría él):\n{g['cuerpo'][:limit]}")
