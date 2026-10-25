"""
Descarga una voz de Piper (TTS offline en español) a la carpeta recursos\\piper.
Así Jarvis puede hablar sin internet.

Uso:
    python descargar_voz.py            -> descarga la voz por defecto (España, Dave)
    python descargar_voz.py mx         -> voz de México
    python descargar_voz.py --lista    -> muestra las voces disponibles
"""
import os
import sys
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(BASE, "recursos", "piper")
ROOT = "https://huggingface.co/rhasspy/piper-voices/resolve/main/es"

VOCES = {
    "es":  ("es_ES/davefx/medium/es_ES-davefx-medium",   "España · Dave · media"),
    "es2": ("es_ES/sharvard/medium/es_ES-sharvard-medium", "España · Sharvard · media"),
    "mx":  ("es_MX/ald/medium/es_MX-ald-medium",          "México · Ald · media"),
    "mx2": ("es_MX/claude/high/es_MX-claude-high",        "México · Claude · alta (más pesada)"),
}


def progress(blocks, size, total):
    if total > 0:
        pct = min(100, blocks * size * 100 // total)
        sys.stdout.write(f"\r  {pct}%")
        sys.stdout.flush()


def descargar(clave):
    rel, desc = VOCES[clave]
    nombre = rel.split("/")[-1]
    os.makedirs(DEST, exist_ok=True)
    print(f"Descargando voz: {desc}")
    for ext in (".onnx", ".onnx.json"):
        destino = os.path.join(DEST, nombre + ext)
        if os.path.exists(destino) and os.path.getsize(destino) > 0:
            print(f"  {nombre}{ext} ya existe.")
            continue
        url = f"{ROOT}/{rel}{ext}"
        print(f"  {nombre}{ext}")
        urllib.request.urlretrieve(url, destino, progress)
        print()
    print(f"\nListo. Voz guardada en {DEST}")
    print("En Jarvis: Ajustes › Voz › Motor de voz = Piper (offline).")


def main():
    args = [a for a in sys.argv[1:] if a]
    if "--lista" in args or "-l" in args:
        print("Voces disponibles:")
        for k, (_, desc) in VOCES.items():
            print(f"  {k:5} {desc}")
        return
    clave = next((a for a in args if a in VOCES), "es")
    try:
        descargar(clave)
    except Exception as e:
        print(f"\nNo se pudo descargar la voz: {e}")
        print("Revisa tu conexión a internet (solo hace falta esta vez).")
        sys.exit(1)


if __name__ == "__main__":
    main()
