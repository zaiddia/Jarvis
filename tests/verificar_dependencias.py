"""12.51: ¿se instalaron de verdad las librerías de Jarvis? Lo corre la compilación del .exe (y las pruebas en Windows)
antes de seguir: si falta una, se detiene en vez de publicar un Jarvis incompleto.

python tests/verificar_dependencias.py      → sale con error y dice cuáles faltan.
"""
import importlib
import os
import sys

# nombre en requirements.txt → módulo que se importa
MODULES = {
    "flask": "flask", "flask-socketio": "flask_socketio", "vosk": "vosk", "sounddevice": "sounddevice", "pygame-ce": "pygame",
    "edge-tts": "edge_tts", "ollama": "ollama", "pywebview": "webview", "pystray": "pystray", "Pillow": "PIL",
    "pyautogui": "pyautogui", "pyperclip": "pyperclip", "psutil": "psutil", "schedule": "schedule", "python-docx": "docx",
    "sympy": "sympy", "opencv-python-headless": "cv2", "icalendar": "icalendar", "recurring-ical-events": "recurring_ical_events",
    "tzdata": "tzdata", "websockets": "websockets", "python-pptx": "pptx", "openpyxl": "openpyxl", "qrcode": "qrcode",
    "pywin32": "win32api", "cryptography": "cryptography", "pypdf": "pypdf", "pypdfium2": "pypdfium2",
    "imageio-ffmpeg": "imageio_ffmpeg", "playwright": "playwright", "fpdf2": "fpdf",
}
WINDOWS_ONLY = {"pywin32"}
# Sin estas, Jarvis no arranca o pierde lo básico (servidor, voz, micrófono, ventana, bandeja, datos cifrados).
CORE = {"flask", "flask-socketio", "vosk", "sounddevice", "pygame-ce", "edge-tts", "pywebview", "pystray", "Pillow", "psutil",
        "cryptography", "pywin32"}


def requirements(path=None):
    path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "requirements.txt")
    with open(path, encoding="utf-8") as f:
        return [ln.split("#")[0].strip() for ln in f if ln.split("#")[0].strip()]


def missing(names, is_win=None):
    is_win = os.name == "nt" if is_win is None else is_win
    out = []
    for n in names:
        if n in WINDOWS_ONLY and not is_win:
            continue
        try:
            importlib.import_module(MODULES[n])
        except Exception as e:                         # no solo ImportError: una DLL que no carga también cuenta
            out.append((n, f"{type(e).__name__}: {str(e)[:120]}"))
    return out


def main():
    reqs = requirements()
    unknown = [r for r in reqs if r not in MODULES]
    if unknown:
        print("Falta decir qué módulo importa:", ", ".join(unknown))
        return 2
    bad = missing(reqs)
    for n, why in bad:
        print(f"{'FALTA (básica)' if n in CORE else 'FALTA'}: {n} — {why}")
    if bad:
        print(f"No se instalaron {len(bad)} de {len(reqs)} librerías. No sigo: el .exe saldría incompleto.")
        return 1
    print(f"Las {len(reqs)} librerías de Jarvis están instaladas y cargan bien.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
