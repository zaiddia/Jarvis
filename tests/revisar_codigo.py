"""Revisión del código antes de las pruebas: que todo compile y que no haya nombres sin definir.
En GitHub, cada error sale como anotación. Uso: python tests/revisar_codigo.py"""
import os
import py_compile
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {".venv", "venv", "windows-app", "publicar", ".git", "__pycache__", "dist", "build"}
GH = os.environ.get("GITHUB_ACTIONS") == "true"


def error(msg):
    print(f"::error::{msg}" if GH else f"ERROR: {msg}", flush=True)


files = []
for base, dirs, names in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in SKIP]
    files += [os.path.join(base, n) for n in names if n.endswith(".py")]

bad = 0
for f in files:
    try:
        py_compile.compile(f, doraise=True)
    except py_compile.PyCompileError as e:
        bad += 1
        error(f"No compila {os.path.relpath(f, ROOT)}: {e.msg}")

# jarvis.py trae sus partes con «from nucleo.X import *». Para que pyflakes siga encontrando nombres sin definir,
# se revisa una copia donde cada * se cambia por la lista de nombres de esa parte (en la misma línea).
import ast  # noqa: E402
import re  # noqa: E402

STAR = re.compile(r"^from nucleo\.(\w+) import \*")
_copy = os.path.join(ROOT, "_revision_jarvis.py")


def _all(mod):
    t = ast.parse(open(os.path.join(ROOT, "nucleo", mod + ".py"), encoding="utf-8").read())
    for st in t.body:
        if isinstance(st, ast.Assign) and any(getattr(x, "id", "") == "__all__" for x in st.targets):
            return [e.value for e in st.value.elts]
    return []


main = os.path.join(ROOT, "jarvis.py")
if os.path.exists(main) and os.path.isdir(os.path.join(ROOT, "nucleo")):
    lines = open(main, encoding="utf-8").read().split("\n")
    for i, line in enumerate(lines):
        m = STAR.match(line)
        if m:
            lines[i] = f"from nucleo.{m.group(1)} import ({', '.join(_all(m.group(1)))})"
    with open(_copy, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    files = [_copy if f == main else f for f in files]

try:
    out = subprocess.run([sys.executable, "-m", "pyflakes", *files], capture_output=True, text=True, encoding="utf-8").stdout
except Exception as e:
    out = ""
    print(f"pyflakes no disponible: {e}")
finally_rm = os.path.exists(_copy) and os.remove(_copy)
out = out.replace("_revision_jarvis.py", "jarvis.py")
SERIOUS = ("undefined name", "syntax error", "invalid syntax", "unexpected indent", "referenced before assignment")
for line in out.splitlines():
    if any(s in line for s in SERIOUS):
        bad += 1
        k = line.find(".py:")                      # en Windows la ruta lleva «C:», no vale partir por «:»
        error(os.path.relpath(line[:k + 3], ROOT) + line[k + 3:] if k > 0 else line)

print(f"{len(files)} archivos revisados, {bad} errores.")
sys.exit(1 if bad else 0)
