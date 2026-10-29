"""Actualizar Jarvis desde GitHub (la página «Releases» de tu repositorio).

    buscar:   latest("usuario/jarvis", "5.8")  -> ¿hay una versión más nueva?
    instalar: download(...) + apply(zip, carpeta)  -> copia de seguridad + archivos nuevos
    deshacer: rollback(carpeta)                    -> vuelve a dejarlo como estaba

Nunca toca tus datos: los ajustes, notas, cursos y rutinas viven en %APPDATA%\\Jarvis,
y aquí además se respetan .env, el modelo de voz (model_es), las voces de Piper, el
entorno de Python (.venv) y el ejecutable compilado (dist, build).
"""
import datetime
import json
import os
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
import zipfile

GITHUB_API = "https://api.github.com"
BACKUP_DIR = "_respaldo_actualizacion"
MAX_BYTES = 300 * 1024 * 1024
KEEP_BACKUPS = 2
# Si ya existen en tu carpeta, se dejan como están (tu .env, tu icono, tus voces, el modelo)
KEEP_IF_EXISTS = (".env", "model_es/", "recursos/")
# Nunca se instalan desde el .zip
ALWAYS_SKIP = (BACKUP_DIR + "/", ".venv/", "venv/", ".git/", "dist/", "build/")


class UpdateError(Exception):
    pass


def parse_version(text):
    nums = re.findall(r"\d+", str(text or ""))
    return tuple(int(n) for n in nums[:4]) or (0,)


def clean_repo(text):
    """«usuario/repo», «https://github.com/usuario/repo» o «…/repo.git» -> «usuario/repo»."""
    t = str(text or "").strip()
    t = re.sub(r"^(?:https?://)?(?:www\.)?github\.com/", "", t, flags=re.I)
    t = re.sub(r"\.git$|/+$", "", t)
    parts = [p for p in t.split("/") if p][:2]
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", p) and p.strip(".") for p in parts):
        raise UpdateError("Escribe el repositorio como usuario/nombre (por ejemplo: profe-diana/jarvis).")
    return "/".join(parts)


class _NoAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """GitHub redirige las descargas a otro servidor: allí la clave no debe viajar."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            new.remove_header("Authorization")
        return new


_opener = urllib.request.build_opener(_NoAuthOnRedirect)


def _headers(token="", accept="application/vnd.github+json"):
    h = {"Accept": accept, "User-Agent": "Jarvis-actualizador", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get_json(url, token=""):
    try:
        with _opener.open(urllib.request.Request(url, headers=_headers(token)), timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError("No encontré versiones publicadas en ese repositorio. Revisa el nombre, que tenga "
                              "al menos una «Release», y si es privado, pon una clave de GitHub.")
        if e.code in (401, 403):
            body = e.read().decode("utf-8", "replace").lower()
            if "rate limit" in body:
                raise UpdateError("GitHub limita las consultas sin clave. Prueba en una hora.")
            raise UpdateError("GitHub no dejó leer el repositorio (¿privado? revisa la clave de GitHub).")
        raise UpdateError(f"GitHub respondió con error {e.code}.")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise UpdateError("No hay conexión con GitHub. Revisa tu internet.")
    except ValueError:
        raise UpdateError("Respuesta no válida de GitHub.")


def latest(repo, current, token=""):
    """Información de la última versión publicada y si es más nueva que la actual."""
    repo = clean_repo(repo)
    d = _get_json(f"{GITHUB_API}/repos/{repo}/releases/latest", token)
    tag = str(d.get("tag_name") or d.get("name") or "")
    assets = [a for a in (d.get("assets") or []) if str(a.get("name", "")).lower().endswith(".zip")]
    assets.sort(key=lambda a: ("jarvis" not in a["name"].lower(), a["name"]))
    if assets:
        a = assets[0]
        url = a["url"] if token else a.get("browser_download_url") or a["url"]
        name, size, binary = a["name"], int(a.get("size") or 0), bool(token)
        digest = str(a.get("digest") or "")           # «sha256:…»: GitHub lo calcula para cada archivo publicado
        sha256 = digest[7:].lower() if digest.lower().startswith("sha256:") else ""
    elif d.get("zipball_url"):
        url, name, size, binary = d["zipball_url"], f"{repo.split('/')[1]}-{tag}.zip", 0, False
        sha256 = ""
    else:
        raise UpdateError("La última versión del repositorio no tiene un archivo .zip.")
    notes = re.sub(r"\r", "", str(d.get("body") or "")).strip()
    return {"repo": repo, "version": tag.lstrip("vV") or "?", "tag": tag, "current": current,
            "newer": parse_version(tag) > parse_version(current), "notes": notes[:1500],
            "url": url, "binary": binary, "name": name, "size": size, "sha256": sha256,
            "date": str(d.get("published_at") or "")[:10], "page": d.get("html_url", "")}


def download(info, dest, token="", progress=None):
    accept = "application/octet-stream" if info.get("binary") else "application/vnd.github+json"
    req = urllib.request.Request(info["url"], headers=_headers(token, accept))
    try:
        with _opener.open(req, timeout=60) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or info.get("size") or 0)
            got = 0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                got += len(chunk)
                if got > MAX_BYTES:
                    raise UpdateError("El archivo de la actualización es demasiado grande.")
                f.write(chunk)
                if progress:
                    progress(got, total)
    except urllib.error.HTTPError as e:
        raise UpdateError(f"No se pudo descargar la actualización (error {e.code}).")
    except (urllib.error.URLError, TimeoutError) as e:
        raise UpdateError(f"Se cortó la descarga: {getattr(e, 'reason', e)}. Revisa tu internet.")
    verify(dest, info)
    return dest


def sha256_of(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(path, info):
    """Que el archivo descargado sea exactamente el publicado: mismo tamaño y misma huella SHA-256."""
    size = int(info.get("size") or 0)
    if size and os.path.getsize(path) != size:
        raise UpdateError(f"La descarga quedó incompleta ({os.path.getsize(path)} de {size} bytes). Prueba otra vez.")
    want = str(info.get("sha256") or "").lower()
    if want and sha256_of(path) != want:
        raise UpdateError("La huella del archivo descargado no coincide con la publicada en GitHub; no lo instalo.")


def _skip(rel):
    low = rel.lower()
    return (low.startswith(ALWAYS_SKIP) or "__pycache__/" in low or low.endswith((".pyc", ".nuevo")))


def _keep(rel):
    low = rel.lower()
    return any(low == k or (k.endswith("/") and low.startswith(k)) for k in KEEP_IF_EXISTS)


def inspect_zip(path):
    """Comprueba que el .zip sea una versión de Jarvis y devuelve (raíz, [(info, ruta_relativa)])."""
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise UpdateError("El archivo descargado no es un .zip válido.")
    with z:
        names = [i for i in z.infolist() if not i.is_dir()]
        cands = sorted((n.filename for n in names if n.filename.rsplit("/", 1)[-1] == "jarvis.py"),
                       key=lambda s: s.count("/"))
        if not cands:
            raise UpdateError("Ese .zip no parece una versión de Jarvis (no trae jarvis.py).")
        root = cands[0][:-len("jarvis.py")]
        out = []
        for info in names:
            n = info.filename.replace("\\", "/")
            if not n.startswith(root):
                continue
            rel = n[len(root):]
            parts = rel.split("/")
            if (not rel or rel.startswith("/") or ".." in parts or ":" in rel
                    or any(p in ("", ".") for p in parts)):
                raise UpdateError("El .zip trae rutas no permitidas; no lo instalo por seguridad.")
            if info.file_size > MAX_BYTES:
                raise UpdateError("El .zip trae un archivo demasiado grande.")
            out.append((info, rel))
        return root, out


def zip_version(path):
    root, members = inspect_zip(path)
    with zipfile.ZipFile(path) as z:
        src = z.read(root + "jarvis.py").decode("utf-8", "replace")
    m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)', src, re.M)
    return m.group(1) if m else "?"


def backups(target):
    base = os.path.join(target, BACKUP_DIR)
    try:
        items = [os.path.join(base, d) for d in os.listdir(base)
                 if os.path.isfile(os.path.join(base, d, "manifiesto.json"))]
    except OSError:
        return []
    return sorted(items, key=os.path.getmtime)


def last_backup(target):
    b = backups(target)
    if not b:
        return None
    with open(os.path.join(b[-1], "manifiesto.json"), encoding="utf-8") as f:
        m = json.load(f)
    m["path"] = b[-1]
    return m


def apply(zip_path, target, current, progress=None):
    """Instala la versión del .zip en target. Lo que se reemplaza queda en una copia de seguridad."""
    root, members = inspect_zip(zip_path)
    new_version = zip_version(zip_path)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bdir = os.path.join(target, BACKUP_DIR, f"{current}_{stamp}")
    os.makedirs(bdir, exist_ok=True)
    changed, added, skipped = [], [], []
    req_old = _read(os.path.join(target, "requirements.txt"))
    plan = []
    with zipfile.ZipFile(zip_path) as z:
        for info, rel in members:
            dest = os.path.join(target, *rel.split("/"))
            exists = os.path.exists(dest)
            if _skip(rel):
                continue
            if exists and _keep(rel):
                skipped.append(rel)
                continue
            data = z.read(info)
            if exists and _read_bytes(dest) == data:
                continue                                    # igual: no hace falta tocarlo
            plan.append((rel, dest, data, exists))
        # 1) copia de seguridad de todo lo que se va a reemplazar
        for rel, dest, data, exists in plan:
            if exists:
                b = os.path.join(bdir, *rel.split("/"))
                os.makedirs(os.path.dirname(b), exist_ok=True)
                shutil.copy2(dest, b)
        _write_manifest(bdir, {"desde": current, "hacia": new_version, "fecha": stamp,
                               "cambiados": [p[0] for p in plan if p[3]],
                               "nuevos": [p[0] for p in plan if not p[3]], "completo": False})
        # 2) escribe (cada archivo se reemplaza de una vez: nunca queda a medias)
        for i, (rel, dest, data, exists) in enumerate(plan):
            os.makedirs(os.path.dirname(dest) or target, exist_ok=True)
            tmp = dest + ".nuevo"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
            (changed if exists else added).append(rel)
            if progress:
                progress(i + 1, len(plan))
    _write_manifest(bdir, {"desde": current, "hacia": new_version, "fecha": stamp,
                           "cambiados": changed, "nuevos": added, "completo": True})
    for old in backups(target)[:-KEEP_BACKUPS]:
        shutil.rmtree(old, ignore_errors=True)
    return {"version": new_version, "changed": changed, "added": added, "skipped": skipped,
            "backup": bdir, "requirements_changed": _read(os.path.join(target, "requirements.txt")) != req_old}


def rollback(target):
    """Deja Jarvis como estaba antes de la última actualización."""
    m = last_backup(target)
    if not m:
        raise UpdateError("No hay ninguna actualización que deshacer.")
    bdir = m["path"]
    for rel in m.get("nuevos", []):
        p = os.path.join(target, *rel.split("/"))
        try:
            os.remove(p)
        except OSError:
            pass
    for rel in m.get("cambiados", []):
        src = os.path.join(bdir, *rel.split("/"))
        if os.path.exists(src):
            dest = os.path.join(target, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest + ".nuevo")
            os.replace(dest + ".nuevo", dest)
    shutil.rmtree(bdir, ignore_errors=True)
    return {"version": m.get("desde", "?"), "from": m.get("hacia", "?")}


def _write_manifest(bdir, data):
    with open(os.path.join(bdir, "manifiesto.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _read_bytes(p):
    try:
        with open(p, "rb") as f:
            return f.read()
    except OSError:
        return None
