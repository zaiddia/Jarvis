@echo off
chcp 65001 >nul
title Compilador J.A.R.V.I.S.
cd /d "%~dp0"
echo ==========================================
echo    ENSAMBLADOR J.A.R.V.I.S.
echo ==========================================
echo.
if not exist ".venv\Scripts\activate.bat" (
  echo Falta el entorno. Ejecuta primero instalar.bat
  goto :fallo
)
if not exist "model_es" (
  echo Falta la carpeta model_es. Ejecuta: .venv\Scripts\python descargar_modelo.py
  goto :fallo
)
call ".venv\Scripts\activate.bat"

echo [1/3] Purgando caches y compilaciones previas...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q jarvis.spec 2>nul
echo.

echo [2/3] Empaquetando el nucleo del sistema (tarda unos minutos)...
pip install -q pyinstaller
python crear_accesos.py >nul
set "EXTRA="
if exist "recursos" set EXTRA=--add-data "recursos;recursos"
rem Icono del .exe: usa recursos\icono.ico si lo pusiste; si no, el generado.
set "ICONO=static\jarvis.ico"
if exist "recursos\icono.ico" set "ICONO=recursos\icono.ico"
rem Incluir Piper y Whisper solo si estan instalados.
set "ML="
python -c "import piper" 2>nul && set "ML=%ML% --collect-all piper"
python -c "import sounddevice" 2>nul && set "ML=%ML% --collect-all _sounddevice_data --hidden-import audio_compat"
python -c "import faster_whisper" 2>nul && set "ML=%ML% --collect-all faster_whisper --collect-all ctranslate2 --collect-all onnxruntime"
pyinstaller --noconfirm --clean --onedir --windowed --name jarvis --icon "%ICONO%" ^
  --add-data "model_es;model_es" ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data "habilidades_comunidad;habilidades_comunidad" ^
  %EXTRA% %ML% ^
  --collect-all vosk ^
  --hidden-import edge_tts --collect-all edge_tts ^
  --hidden-import pygame --collect-all pygame ^
  --hidden-import ollama ^
  --collect-submodules nucleo ^
  --collect-all webview ^
  --hidden-import engineio.async_drivers.threading ^
  --hidden-import pystray._win32 ^
  --collect-submodules websockets ^
  --collect-all pptx ^
  --collect-submodules openpyxl ^
  jarvis.py
if errorlevel 1 (
  echo.
  echo ERROR: PyInstaller no pudo compilar. Revisa los mensajes de arriba.
  goto :fallo
)
rem El .env nunca se mete dentro del paquete: se copia al lado del ejecutable.
if exist ".env" copy /y ".env" "dist\jarvis\" >nul
rem El orbe de la barra de tareas (mod de Windhawk) va al lado, para copiarlo desde Ajustes.
if exist "windhawk" xcopy /e /i /y /q "windhawk" "dist\jarvis\windhawk" >nul
echo.

echo [3/3] Actualizando accesos directos...
if /i not "%~1"=="nopause" python crear_accesos.py
echo.
echo Listo: dist\jarvis\jarvis.exe
if /i not "%~1"=="nopause" pause
exit /b 0

:fallo
if /i not "%~1"=="nopause" pause
exit /b 1
