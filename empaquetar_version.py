"""Crea el .zip limpio para publicar una versión de Jarvis en GitHub (Releases).

    python empaquetar_version.py

Deja «jarvis_project_vX.Y.zip» en la carpeta «publicar». Ese archivo es el que subes
a la Release (con la etiqueta vX.Y). NO incluye tus claves (.env), el entorno de Python
(.venv), el modelo de voz, las voces de Piper, el ejecutable compilado ni las copias
de seguridad: así puedes publicarlo sin miedo, aunque el repositorio sea público.
"""
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {".venv", "venv", ".git", "dist", "build", "__pycache__", "model_es", "publicar",
             "_respaldo_actualizacion", "piper_voices"}
SKIP_FILES = {".env", "config.json"}
SKIP_EXT = (".pyc", ".log", ".nuevo", ".onnx", ".onnx.json", ".spec")


def main():
    src = open(os.path.join(HERE, "jarvis.py"), encoding="utf-8").read()
    m = re.search(r'^VERSION\s*=\s*"([^"]+)"', src, re.M)
    if not m:
        sys.exit("No encontré VERSION en jarvis.py")
    version = m.group(1)
    out_dir = os.path.join(HERE, "publicar")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"jarvis_project_v{version}.zip")
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(HERE):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for f in files:
                low = f.lower()
                if f in SKIP_FILES or low.endswith(SKIP_EXT) or low.startswith("."):
                    if f not in (".env.ejemplo", ".gitignore"):
                        continue
                p = os.path.join(root, f)
                rel = os.path.relpath(p, HERE).replace(os.sep, "/")
                if rel.startswith("recursos/") and not low.endswith(".txt"):
                    continue                      # tu icono, tu sirena: son tuyos
                z.write(p, "jarvis_project/" + rel)
                n += 1
    print(f"Listo: {out}  ({n} archivos)")
    print(f"En GitHub: Releases › Draft a new release › etiqueta v{version} › adjunta este .zip › Publish.")


if __name__ == "__main__":
    main()
