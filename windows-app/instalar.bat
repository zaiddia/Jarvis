@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Instalar JARVIS

echo.
echo   ===  J.A.R.V.I.S.  ===  Instalación
echo.

if not exist "programa\Jarvis.exe" (
    call "%~dp0compilar.bat"
    if errorlevel 1 exit /b 1
)

set "DEST=%LOCALAPPDATA%\Programs\JARVIS"
echo   Cerrando JARVIS si estaba abierto...
taskkill /im Jarvis.exe /f >nul 2>nul
timeout /t 1 /nobreak >nul

echo   Copiando a %DEST%...
if not exist "%DEST%" mkdir "%DEST%"
robocopy "programa" "%DEST%" /e /njh /njs /nfl /ndl /np >nul
if errorlevel 8 (
    echo   No se pudo copiar el programa.
    pause
    exit /b 1
)

echo   Creando accesos directos...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$w = New-Object -ComObject WScript.Shell;" ^
  "foreach ($p in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {" ^
  "  $s = $w.CreateShortcut((Join-Path $p 'JARVIS.lnk'));" ^
  "  $s.TargetPath = '%DEST%\Jarvis.exe'; $s.WorkingDirectory = '%DEST%';" ^
  "  $s.Description = 'Asistente personal por voz'; $s.Save() }"

if not exist "%LOCALAPPDATA%\JarvisVoz\piper\piper.exe" (
    echo.
    echo   Las voces neuronales ^(Whisper para entender y Piper para hablar^) no están instaladas.
    choice /c SN /m "  ¿Instalarlas ahora? Son unos 600 MB y mejoran mucho a JARVIS"
    if not errorlevel 2 call "%~dp0instalar-voces.bat"
)

echo.
echo   Iniciando JARVIS...
start "" "%DEST%\Jarvis.exe"
echo.
echo   Hecho. JARVIS está en la bandeja del sistema (junto al reloj).
echo   Diga «Jarvis» o pulse Ctrl+Alt+J.
echo.
echo   Si también usa el mod de Windhawk «JARVIS», desactívelo para que no respondan los dos.
echo.
pause
