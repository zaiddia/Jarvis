@echo off
chcp 65001 >nul
title Compilador J.A.R.V.I.S. - USB portable
cd /d "%~dp0"
call compilar.bat nopause
if errorlevel 1 (
  pause
  exit /b 1
)

echo [4/4] Preparando la carpeta portable...
set "OUT=%~dp0USB\Jarvis"
if exist "%OUT%" rmdir /s /q "%OUT%"
robocopy "dist\jarvis" "%OUT%" /E /NFL /NDL /NJH /NJS /NP >nul
if exist ".env" copy /y ".env" "%OUT%\" >nul
if exist "recursos" robocopy "recursos" "%OUT%\recursos" /E /NFL /NDL /NJH /NJS /NP >nul
rem Este archivo activa el modo portable: ajustes, registro y documentos se quedan en la USB.
type nul > "%OUT%\portable"
mkdir "%OUT%\datos" 2>nul

echo.
echo ==========================================
echo  LISTO PARA LA USB
echo ==========================================
echo Copia la carpeta completa:   USB\Jarvis
echo a tu memoria. En cualquier PC con Windows 10/11 abre:   Jarvis\jarvis.exe
echo.
echo Ya incluye el modelo de voz, la interfaz, tus recursos (sirena.mp3...) y el .env.
echo No hace falta copiar nada a mano.
echo.
pause
