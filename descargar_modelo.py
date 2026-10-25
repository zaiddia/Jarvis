"""Descarga el modelo de voz en español de Vosk y lo deja en la carpeta model_es/."""
import os
import shutil
import sys
import urllib.request
import zipfile

MODEL_NAME = "vosk-model-small-es-0.42"
URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
BASE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(BASE, "model_es")
ZIP_PATH = os.path.join(BASE, f"{MODEL_NAME}.zip")


def progress(blocks, block_size, total):
    if total > 0:
        pct = min(100, blocks * block_size * 100 // total)
        sys.stdout.write(f"\rDescargando modelo Vosk... {pct}%")
        sys.stdout.flush()


def main():
    if os.path.isdir(TARGET) and os.listdir(TARGET):
        print(f"El modelo ya existe en {TARGET}. Nada que hacer.")
        return
    print(f"Fuente: {URL}")
    urllib.request.urlretrieve(URL, ZIP_PATH, progress)
    print("\nDescomprimiendo...")
    with zipfile.ZipFile(ZIP_PATH) as z:
        z.extractall(BASE)
    extracted = os.path.join(BASE, MODEL_NAME)
    if os.path.isdir(TARGET):
        shutil.rmtree(TARGET)
    os.rename(extracted, TARGET)
    os.remove(ZIP_PATH)
    print(f"Modelo listo en {TARGET}")


if __name__ == "__main__":
    main()
