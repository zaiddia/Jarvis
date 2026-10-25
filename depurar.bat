@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Jarvis - modo diagnostico
if not exist ".venv\Scripts\python.exe" (
  echo Falta el entorno .venv: ejecuta primero instalar.bat
  pause
  exit /b 1
)
echo ==========================================
echo   JARVIS - MODO DIAGNOSTICO
echo ==========================================
echo Procesos de Python abiertos ahora mismo:
tasklist /fi "imagename eq pythonw.exe" /fo table /nh 2>nul | findstr /i "python"
tasklist /fi "imagename eq jarvis.exe" /fo table /nh 2>nul | findstr /i "jarvis"
echo.
echo Iniciando Jarvis con consola. Si falla, el error aparece aqui abajo.
echo Haz una captura de esta ventana o copia el texto y envialo.
echo.
".venv\Scripts\python.exe" jarvis.py --mostrar
echo.
echo ==== Jarvis se cerro - codigo %errorlevel% ====
pause
