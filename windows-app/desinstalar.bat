@echo off
chcp 65001 >nul
setlocal
title Desinstalar JARVIS
echo.
choice /c SN /m "  ¿Desinstalar JARVIS"
if errorlevel 2 exit /b 0
taskkill /im Jarvis.exe /f >nul 2>nul
timeout /t 1 /nobreak >nul
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v JARVIS /f >nul 2>nul
del /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\JARVIS.lnk" >nul 2>nul
for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do del /q "%%d\JARVIS.lnk" >nul 2>nul
rmdir /s /q "%LOCALAPPDATA%\Programs\JARVIS" >nul 2>nul
echo   Programa eliminado.
echo.
choice /c SN /m "  ¿Borrar también sus ajustes, notas y recordatorios (%APPDATA%\JARVIS)"
if not errorlevel 2 rmdir /s /q "%APPDATA%\JARVIS" >nul 2>nul
echo.
echo   Las voces neuronales (compartidas con el mod) se quitan con desinstalar-voces.bat.
echo.
pause
