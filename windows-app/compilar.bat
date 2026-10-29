@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Compilar JARVIS

where dotnet >nul 2>nul || goto nosdk
dotnet --list-sdks 2>nul | findstr /r "^8\. ^9\. ^10\." >nul || goto nosdk

echo.
echo   Compilando JARVIS (la primera vez tarda un par de minutos)...
echo.
if exist programa rmdir /s /q programa
dotnet publish "codigo\JarvisApp.csproj" -c Release -r win-x64 --self-contained false -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:DebugType=none -o "programa" -nologo > compilacion.log 2>&1
if errorlevel 1 goto failed
if not exist "programa\Jarvis.exe" goto failed

rem El instalador de voces viaja con el programa (lo usa el botón de los ajustes).
copy /y "instalar-voces.bat" "programa\" >nul
copy /y "desinstalar-voces.bat" "programa\" >nul
xcopy /y /i /q "voces" "programa\voces" >nul

echo   Listo: programa\Jarvis.exe
echo.
exit /b 0

:failed
echo   No se pudo compilar. Estos son los errores:
echo.
findstr /i /c:"error" compilacion.log
echo.
echo   El informe completo está en compilacion.log. Envíeselo a Claude para corregirlo.
echo.
pause
exit /b 1

:nosdk
echo.
echo   Para compilar JARVIS hace falta el SDK de .NET 8 (gratuito, de Microsoft).
echo.
choice /c SN /m "  ¿Lo instalo ahora con winget"
if errorlevel 2 (
    echo   Descárguelo de https://dotnet.microsoft.com/download/dotnet/8.0 y vuelva a ejecutar este archivo.
    pause
    exit /b 1
)
winget install --id Microsoft.DotNet.SDK.8 -e --accept-source-agreements --accept-package-agreements
echo.
echo   Cierre esta ventana y vuelva a ejecutar el instalador (el sistema necesita ver el SDK nuevo).
pause
exit /b 1
