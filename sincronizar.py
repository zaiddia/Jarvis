"""Varios equipos (7.9): la misma memoria, rutinas y tareas en el PC del colegio y en el de la casa.

Eliges una carpeta que tus dos equipos compartan (OneDrive, Google Drive o Dropbox). Cada pocos minutos, Jarvis
compara sus archivos con los de esa carpeta y se queda con el más nuevo de cada uno. Nunca se copian tus claves ni
los ajustes (cada equipo tiene los suyos).
"""
import json
import os
import shutil
import socket

FILES = ["perfil.json", "rutinas.json", "tareas.json", "notas.json", "aula.json", "banco_preguntas.json",
         "notas_estudiantes.json", "aprendizaje.json", "horario.json", "formularios.json", "observador.json", "registro_clase.json", "compromisos.json", "lecciones.json", "paginas_vigiladas.json"]
FOLDERS = {"habilidades": ".json", "guias": ".md"}
SUB = "Jarvis-sincronizado"
STAMP = ".jarvis-sync.json"
MIN_DIFF = 2.0                 # segundos de diferencia para considerar un archivo distinto


def target(folder):
    return os.path.join(folder, SUB)


def _entries(base):
    out = {}
    for f in FILES:
        p = os.path.join(base, f)
        if os.path.isfile(p):
            out[f] = os.path.getmtime(p)
    for d, ext in FOLDERS.items():
        dp = os.path.join(base, d)
        if os.path.isdir(dp):
            for n in os.listdir(dp):
                p = os.path.join(dp, n)
                if n.endswith(ext) and os.path.isfile(p) and not n.startswith("."):
                    out[f"{d}/{n}"] = os.path.getmtime(p)
    return out


def plan(local, remote):
    """[(acción, ruta)] con acción «subir» (local → carpeta) o «bajar» (carpeta → local)."""
    a, b = _entries(local), _entries(remote)
    out = []
    for k in sorted(set(a) | set(b)):
        if k in a and k not in b:
            out.append(("subir", k))
        elif k in b and k not in a:
            out.append(("bajar", k))
        elif a[k] - b[k] > MIN_DIFF:
            out.append(("subir", k))
        elif b[k] - a[k] > MIN_DIFF:
            out.append(("bajar", k))
    return out


def _valid(path):
    if path.endswith(".json"):
        try:
            with open(path, "rb") as f:
                raw = f.read()
            if raw.startswith(b"JVENC1:"):                 # 8.9: datos de estudiantes cifrados (completos)
                return len(raw) > 60
            json.loads(raw.decode("utf-8"))
        except (OSError, ValueError):
            return False
    return True


def apply(local, remote, actions):
    """Copia según el plan (conservando la fecha). Devuelve las rutas que cambiaron en ESTE equipo."""
    changed = []
    for act, k in actions:
        src, dst = (os.path.join(local, k), os.path.join(remote, k)) if act == "subir" else (os.path.join(remote, k), os.path.join(local, k))
        if not _valid(src):
            continue                                   # un archivo a medio sincronizar por OneDrive: la próxima vez
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tmp = dst + ".sync-tmp"
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
        if act == "bajar":
            changed.append(k)
    try:
        with open(os.path.join(remote, STAMP), "w", encoding="utf-8") as f:
            json.dump({"equipo": socket.gethostname()}, f)
    except OSError:
        pass
    return changed


def sync(local, folder):
    remote = target(folder)
    os.makedirs(remote, exist_ok=True)
    acts = plan(local, remote)
    return acts, apply(local, remote, acts)
