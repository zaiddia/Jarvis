"""Copias de seguridad de Jarvis: ajustes, notas, cursos, rutinas y memoria en un solo .zip.

    crear:     create(config_dir, carpeta, ajustes, ...)  -> "Jarvis respaldo 2026-10-25 1304.zip"
    revisar:   inspect(ruta)                              -> qué trae (sin tocar nada)
    restaurar: restore(ruta, config_dir, partes)          -> escribe los datos elegidos

Sirve para no perder nada si se daña el equipo y para pasar Jarvis a otro computador.
Por defecto las claves de API NO se guardan (la copia se puede llevar en una USB sin riesgo).
"""
import datetime
import json
import os
import platform
import re
import zipfile

import datos

MANIFEST = "jarvis_respaldo.json"
MAX_BYTES = 20 * 1024 * 1024
# archivo -> (parte, descripción)
FILES = {
    "config.json": ("ajustes", "Ajustes"),
    "notas.json": ("notas", "Notas y recordatorios"),
    "aula.json": ("aula", "Cursos, listas y asistencia"),
    "rutinas.json": ("rutinas", "Rutinas"),
    "memoria.json": ("memoria", "Memoria de la conversación"),
    "perfil.json": ("perfil", "Lo que Jarvis sabe de ti"),
    "tareas.json": ("tareas", "Tareas programadas"),
    "aprendizaje.json": ("aprendizaje", "Costumbres aprendidas"),
    "notas_estudiantes.json": ("seguimiento", "Notas de los estudiantes"),
    "horario.json": ("horario", "Horario de clases"),
    "observador.json": ("observador", "Observador de los estudiantes"),
    "registro_clase.json": ("registro", "Diario de clase y mallas"),
    "formularios.json": ("formularios", "Formularios de Google Forms"),
    "banco_preguntas.json": ("banco", "Banco de preguntas"),
}
# carpeta -> (parte, descripción, extensión): cada archivo de la carpeta va en la copia
FOLDERS = {
    "habilidades": ("habilidades", "Habilidades instaladas", ".json"),
    "diario": ("diario", "Diario", ".jsonl"),
    "historial": ("historial", "Historial de conversaciones", ".jsonl"),
    "guias": ("guias", "Habilidades de la comunidad", ".md"),
}
FOLDER_MAX_FILE = 2 * 1024 * 1024
PARTS = {p: d for p, d in FILES.values()}
PARTS.update({p: d for p, d, _ in FOLDERS.values()})


def _folder_files(config_dir, folder, ext):
    d = os.path.join(config_dir, folder)
    try:
        return sorted(e for e in os.listdir(d) if e.lower().endswith(ext) and os.path.isfile(os.path.join(d, e))
                      and os.path.getsize(os.path.join(d, e)) <= FOLDER_MAX_FILE)
    except OSError:
        return []


def _safe_member(name, folder, ext):
    """«habilidades/wikipedia.json» → «wikipedia.json»; None si la ruta no es segura."""
    if not name.startswith(folder + "/"):
        return None
    base = name[len(folder) + 1:]
    if not base or "/" in base or "\\" in base or ".." in base or ":" in base or base.startswith(".") or not base.lower().endswith(ext):
        return None
    return base


class BackupError(Exception):
    pass


def _now():
    return datetime.datetime.now()


def create(config_dir, dest_dir, settings, secret_fields=(), include_secrets=False,
           version="", kind="manual"):
    """Guarda la copia. settings: los ajustes actuales (se escriben ya validados)."""
    os.makedirs(dest_dir, exist_ok=True)
    stamp = _now()
    tag = {"manual": "", "auto": " (automática)", "antes": " (antes de restaurar)"}.get(kind, "")
    name = f"Jarvis respaldo {stamp:%Y-%m-%d %H%M%S}{tag}.zip"
    path = os.path.join(dest_dir, name)
    n = 2
    while os.path.exists(path):                            # dos copias en el mismo segundo
        name = f"Jarvis respaldo {stamp:%Y-%m-%d %H%M%S}{tag} ({n}).zip"
        path = os.path.join(dest_dir, name)
        n += 1
    cfg = dict(settings)
    removed = []
    if not include_secrets:
        for k in secret_fields:
            if cfg.get(k):
                removed.append(k)
            cfg.pop(k, None)
    included, counts = [], {}
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("config.json", json.dumps(cfg, ensure_ascii=False, indent=1))
        included.append("ajustes")
        for fname, (part, _) in FILES.items():
            if fname == "config.json":
                continue
            src = os.path.join(config_dir, fname)
            try:
                with open(src, "rb") as f:
                    raw = f.read()
            except OSError:
                continue                                   # no existe: se omite
            if datos.is_encrypted(raw):                    # 8.9: datos de estudiantes cifrados: van cifrados
                z.writestr(fname, raw)
                included.append(part)
                try:
                    counts[part] = _count(part, datos.loads(raw))
                except (datos.DataLocked, ValueError):
                    counts[part] = 0
                continue
            try:
                data = json.loads(raw.decode("utf-8"))
            except ValueError:
                continue                                   # dañado: se omite
            z.writestr(fname, json.dumps(data, ensure_ascii=False, indent=1))
            included.append(part)
            counts[part] = _count(part, data)
        for folder, (part, _, ext) in FOLDERS.items():
            files = _folder_files(config_dir, folder, ext)
            for f in files:
                z.write(os.path.join(config_dir, folder, f), f"{folder}/{f}")
            if files:
                included.append(part)
                counts[part] = len(files)
        z.writestr(MANIFEST, json.dumps({
            "app": "Jarvis", "version": version, "fecha": stamp.isoformat(timespec="seconds"),
            "equipo": platform.node(), "tipo": kind, "con_claves": bool(include_secrets and _has_secrets(cfg, secret_fields)),
            "partes": included, "conteos": counts}, ensure_ascii=False, indent=1))
    os.replace(tmp, path)
    return {"path": path, "name": name, "parts": included, "counts": counts,
            "secrets_removed": removed, "with_secrets": bool(include_secrets)}


def _has_secrets(cfg, secret_fields):
    return any(cfg.get(k) for k in secret_fields)


def _count(part, data):
    if part == "notas" and isinstance(data, list):
        return len(data)
    if part == "aula" and isinstance(data, dict):
        return len(data.get("cursos") or {})
    if part == "rutinas" and isinstance(data, list):
        return len(data)
    if part in ("memoria", "perfil", "tareas", "banco") and isinstance(data, list):
        return len(data)
    return None


def _open(path):
    if not os.path.isfile(path):
        raise BackupError("No encuentro ese archivo de copia de seguridad.")
    if os.path.getsize(path) > MAX_BYTES:
        raise BackupError("Ese archivo es demasiado grande para ser una copia de Jarvis.")
    try:
        return zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise BackupError("Ese archivo no es un .zip válido.")


def inspect(path):
    """Qué trae la copia, sin tocar nada. Lanza BackupError si no es una copia de Jarvis."""
    with _open(path) as z:
        names = set(z.namelist())
        if MANIFEST not in names or "config.json" not in names:
            raise BackupError("Ese archivo no es una copia de seguridad de Jarvis.")
        try:
            man = json.loads(z.read(MANIFEST).decode("utf-8"))
            if not isinstance(man, dict) or man.get("app") != "Jarvis":
                raise ValueError
        except ValueError:
            raise BackupError("La copia de seguridad está dañada.")
        parts = []
        for fname, (part, desc) in FILES.items():
            if fname in names:
                try:
                    data = json.loads(z.read(fname).decode("utf-8"))
                except ValueError:
                    continue
                parts.append({"part": part, "desc": desc, "count": _count(part, data)})
        for folder, (part, desc, ext) in FOLDERS.items():
            n = sum(1 for x in names if _safe_member(x, folder, ext))
            if n:
                parts.append({"part": part, "desc": desc, "count": n})
    return {"name": os.path.basename(path), "version": man.get("version", ""), "date": man.get("fecha", ""),
            "computer": man.get("equipo", ""), "kind": man.get("tipo", "manual"),
            "with_secrets": bool(man.get("con_claves")), "parts": parts}


def read_config(path):
    with _open(path) as z:
        d = json.loads(z.read("config.json").decode("utf-8"))
    if not isinstance(d, dict):
        raise BackupError("Los ajustes de la copia están dañados.")
    return d


def restore(path, config_dir, parts):
    """Escribe en config_dir los datos de las partes elegidas (menos «ajustes», que aplica
    jarvis.py validando cada valor). Devuelve las partes restauradas."""
    inspect(path)
    done = []
    with _open(path) as z:
        names = set(z.namelist())
        for fname, (part, _) in FILES.items():
            if part not in parts or part == "ajustes" or fname not in names:
                continue
            raw = z.read(fname)
            if datos.is_encrypted(raw):                    # 8.9: se restaura tal cual (se abre con la clave de recuperación)
                dest = os.path.join(config_dir, fname)
                os.makedirs(config_dir, exist_ok=True)
                with open(dest + ".tmp", "wb") as f:
                    f.write(raw)
                os.replace(dest + ".tmp", dest)
                done.append(part)
                continue
            try:
                data = json.loads(raw.decode("utf-8"))
            except ValueError:
                continue
            if part in ("aula", "seguimiento") and not isinstance(data, dict):
                continue
            if part in ("notas", "rutinas", "memoria", "perfil", "tareas", "banco") and not isinstance(data, list):
                continue
            dest = os.path.join(config_dir, fname)
            os.makedirs(config_dir, exist_ok=True)
            with open(dest + ".tmp", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(dest + ".tmp", dest)
            done.append(part)
        for folder, (part, _, ext) in FOLDERS.items():
            if part not in parts:
                continue
            members = [(x, _safe_member(x, folder, ext)) for x in names]
            members = [(x, b) for x, b in members if b]
            if not members:
                continue
            dest_dir = os.path.join(config_dir, folder)
            os.makedirs(dest_dir, exist_ok=True)
            for member, base in members:
                info = z.getinfo(member)
                if info.file_size > FOLDER_MAX_FILE:
                    continue
                raw = z.read(member)
                if ext == ".json":
                    try:
                        json.loads(raw.decode("utf-8"))
                    except ValueError:
                        continue
                with open(os.path.join(dest_dir, base + ".tmp"), "wb") as f:
                    f.write(raw)
                os.replace(os.path.join(dest_dir, base + ".tmp"), os.path.join(dest_dir, base))
            done.append(part)
    return done


def listing(folder):
    """Copias de la carpeta, de la más nueva a la más vieja."""
    out = []
    try:
        entries = [e for e in os.scandir(folder) if e.is_file() and e.name.lower().endswith(".zip")]
    except OSError:
        return []
    for e in sorted(entries, key=lambda e: e.stat().st_mtime, reverse=True):
        try:
            info = inspect(e.path)
        except BackupError:
            continue
        info["size_kb"] = max(1, round(e.stat().st_size / 1024))
        out.append(info)
    return out


def prune(folder, keep, kind="auto"):
    """Borra las copias automáticas más viejas (las manuales nunca se borran solas)."""
    autos = [b for b in listing(folder) if b["kind"] == kind]
    for b in autos[keep:]:
        try:
            os.remove(os.path.join(folder, b["name"]))
        except OSError:
            pass


def safe_name(name):
    """Nombre de archivo de una copia dentro de la carpeta de copias (sin rutas)."""
    n = os.path.basename(str(name or ""))
    if not n.lower().endswith(".zip") or n != str(name) or n.startswith("."):
        raise BackupError("Nombre de copia no válido.")
    return n
