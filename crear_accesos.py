"""Crea el icono de Jarvis y accesos directos en el Escritorio y el menú Inicio (Windows)."""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
GENERATED_ICON = os.path.join(BASE, "static", "jarvis.ico")
# Si pones tu propio recursos\icono.ico, los accesos directos lo usan.
CUSTOM_ICON = os.path.join(BASE, "recursos", "icono.ico")
ICON = CUSTOM_ICON if os.path.isfile(CUSTOM_ICON) else GENERATED_ICON


def make_icon():
    global ICON
    if os.path.isfile(CUSTOM_ICON):
        ICON = CUSTOM_ICON
        return
    ICON = GENERATED_ICON
    if os.path.exists(ICON):
        return
    from PIL import Image, ImageDraw
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = (46, 230, 255)
    d.ellipse((8, 8, 248, 248), fill=(4, 10, 18, 255), outline=c + (255,), width=14)
    d.ellipse((52, 52, 204, 204), outline=c + (170,), width=10)
    d.ellipse((96, 96, 160, 160), fill=(255, 255, 255, 255))
    img.save(ICON, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Icono creado: {ICON}")


def shortcut(path, target, args, workdir):
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);"
        "$s.TargetPath=$env:TGT;$s.Arguments=$env:ARGS;$s.WorkingDirectory=$env:WD;"
        "$s.IconLocation=$env:ICO;$s.Description='Jarvis - asistente virtual';$s.Save()"
    )
    env = dict(os.environ, LNK=path, TGT=target, ARGS=args, WD=workdir, ICO=ICON)
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=True,
                   creationflags=0x08000000)
    print(f"Acceso directo: {path}")


def main():
    make_icon()
    if os.name != "nt":
        return
    # Siempre a través de Jarvis.vbs: él decide entre el .exe compilado y el código,
    # y evita abrir un .exe viejo cuando actualizaste el código sin recompilar.
    target = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "wscript.exe")
    args = f'"{os.path.join(BASE, "Jarvis.vbs")}"'
    desktop = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                             capture_output=True, text=True, creationflags=0x08000000).stdout.strip()
    programs = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs")
    for folder in filter(None, (desktop, programs)):
        shortcut(os.path.join(folder, "Jarvis.lnk"), target, args, BASE)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"No se pudieron crear los accesos directos: {e}")
        sys.exit(1)
