@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Instalador de J.A.R.V.I.S.
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_NO_INPUT=1"
set "LOG=instalar.log"
echo Instalacion de Jarvis - %date% %time% > "%LOG%"

echo ==========================================
echo    INSTALACION DE J.A.R.V.I.S.
echo ==========================================
echo.

rem ---- 0. Comprobar que el ZIP se descomprimio ----
if not exist "jarvis.py" (
  echo ERROR: no encuentro jarvis.py en esta carpeta.
  echo Descomprime el ZIP primero: clic derecho - Extraer todo. No lo ejecutes desde dentro del ZIP.
  goto :fallo
)

rem ---- 0b. OneDrive vuelve la instalacion y el arranque MUY lentos ----
echo "%CD%" | findstr /i "OneDrive" >nul
if errorlevel 1 goto :carpeta_ok
echo AVISO: esta carpeta esta dentro de OneDrive:
echo     %CD%
echo OneDrive sincroniza los miles de archivos que instala Jarvis, y eso vuelve
echo la instalacion y el arranque muy lentos. Lo recomendable es C:\Jarvis
echo.
choice /c SN /m "Copiar Jarvis a C:\Jarvis e instalarlo alli"
if errorlevel 2 goto :carpeta_ok
set "DEST=C:\Jarvis"
robocopy "%CD%" "%DEST%" /E /XD .venv dist build __pycache__ /XF instalar.log /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 set "DEST=%USERPROFILE%\Jarvis"
if errorlevel 8 robocopy "%CD%" "!DEST!" /E /XD .venv dist build __pycache__ /XF instalar.log /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
  echo No se pudo copiar. Sigo en la carpeta actual.
  goto :carpeta_ok
)
cd /d "!DEST!"
echo Copiado. La instalacion sigue en !DEST!
echo Cuando termine, puedes borrar las copias de Jarvis que tengas en OneDrive.
echo Instalacion movida a !DEST! >> "%LOG%"
echo.
:carpeta_ok

rem ---- 1. Buscar un Python que funcione de verdad ----
rem Se prefiere 3.12/3.11 porque todos los extras opcionales tienen instalador para ellas.
echo [1/6] Buscando Python...
set "BASEPY="
for %%V in (3.12 3.11 3.13 3.14 3.10) do (
  if not defined BASEPY (
    py -%%V -c "import sys" >nul 2>nul && set "BASEPY=py -%%V"
  )
)
if not defined BASEPY (
  for %%D in (Python312 Python311 Python313 Python314) do (
    if not defined BASEPY if exist "%LOCALAPPDATA%\Programs\Python\%%D\python.exe" set "BASEPY="%LOCALAPPDATA%\Programs\Python\%%D\python.exe""
  )
)
if not defined BASEPY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "BASEPY=python"
)
if not defined BASEPY goto :sin_python

:tengo_python
set "PYVER="
for /f "usebackq delims=" %%i in (`call %BASEPY% -c "import sys; print(sys.version.split()[0])"`) do set "PYVER=%%i"
echo       Usando Python %PYVER%
echo Python: %BASEPY% %PYVER% >> "%LOG%"

rem ---- 2. Entorno virtual: se recrea si quedo danado de un intento anterior ----
echo [2/6] Preparando el entorno .venv...
set "VPY=.venv\Scripts\python.exe"
if exist "%VPY%" (
  "%VPY%" -c "import sys" >nul 2>nul || (
    echo       El entorno anterior esta danado, lo vuelvo a crear...
    rmdir /s /q .venv
  )
)
if not exist "%VPY%" %BASEPY% -m venv .venv >> "%LOG%" 2>&1
if not exist "%VPY%" (
  echo ERROR: no se pudo crear el entorno virtual. Detalles en instalar.log
  goto :fallo
)
"%VPY%" -m pip install --upgrade pip >> "%LOG%" 2>&1

rem ---- 3. Dependencias: primero todas juntas, que es mucho mas rapido ----
echo [3/6] Instalando componentes. La primera vez tarda unos minutos...
set "FALLOS="
set "CRITICO="
"%VPY%" -m pip install --prefer-binary -r requirements.txt >> "%LOG%" 2>&1
if not errorlevel 1 (
  echo       Todos los componentes instalados.
  goto :componentes_ok
)
echo       Alguno fallo. Los instalo uno por uno para saber cual...
for /f "usebackq eol=# tokens=1" %%P in ("requirements.txt") do (
  <nul set /p "=      - %%P ... "
  "%VPY%" -m pip install --prefer-binary %%P >> "%LOG%" 2>&1
  if errorlevel 1 (
    echo FALLO
    set "FALLOS=!FALLOS! %%P"
    for %%C in (flask flask-socketio vosk) do if /i "%%P"=="%%C" set "CRITICO=1"
  ) else (
    echo OK
  )
)
if defined CRITICO (
  echo.
  echo ERROR: no se instalaron componentes imprescindibles:!FALLOS!
  echo Revisa tu conexion a internet y vuelve a ejecutar instalar.bat.
  echo Si sigue fallando, enviame el archivo instalar.log de esta carpeta.
  goto :fallo
)
:componentes_ok

rem ---- 4. Modelo de reconocimiento de voz: solo se descarga la primera vez ----
echo [4/6] Modelo de voz en espanol...
"%VPY%" descargar_modelo.py
if errorlevel 1 (
  echo       AVISO: no se pudo descargar el modelo. Reintenta luego con:
  echo           .venv\Scripts\python descargar_modelo.py
  set "FALLOS=!FALLOS! modelo-de-voz"
)

rem ---- 5. Accesos directos ----
echo [5/6] Creando accesos directos...
"%VPY%" crear_accesos.py >> "%LOG%" 2>&1
if errorlevel 1 (
  echo       AVISO: no se crearon los accesos. Puedes abrir Jarvis con Jarvis.vbs
)

rem ---- 6. Extras opcionales: voz sin internet, Whisper y Spotify ----
echo [6/6] Extras opcionales. Si alguno falla, Jarvis funciona igual:
"%VPY%" -m pip install --prefer-binary piper-tts faster-whisper spotipy >> "%LOG%" 2>&1
if not errorlevel 1 (
  echo       Extras instalados.
  goto :extras_ok
)
for %%P in (piper-tts faster-whisper spotipy) do (
  <nul set /p "=      - %%P ... "
  "%VPY%" -m pip install --prefer-binary %%P >> "%LOG%" 2>&1
  if errorlevel 1 (echo no disponible) else (echo OK)
)
:extras_ok

rem ---- Ollama: solo se ofrece si esta instalado y aun no tiene el modelo ----
where ollama >nul 2>nul
if errorlevel 1 (
  echo.
  echo NOTA: Ollama no esta instalado. No hace falta si usas Gemini, Claude u otra IA en la nube.
  goto :ollama_ok
)
ollama list 2>nul | findstr /i /c:"llama3.2" >nul
if not errorlevel 1 (
  echo       Modelo local llama3.2 ya instalado.
  goto :ollama_ok
)
echo.
choice /c SN /t 15 /d N /m "Descargar la IA local llama3.2 de unos 2 GB. Solo hace falta para usar Jarvis sin internet"
if errorlevel 2 goto :ollama_ok
ollama pull llama3.2
:ollama_ok

rem Si quedo un .exe compilado de una version vieja, avisar.
if exist "dist\jarvis\jarvis.exe" (
  echo.
  echo AVISO: hay un jarvis.exe compilado antiguo en dist. Ejecuta compilar.bat
  echo para actualizarlo, o borra la carpeta dist para usar esta version.
)

echo.
echo ==========================================
if defined FALLOS (
  echo  Instalado, pero fallo:!FALLOS!
  echo  Jarvis funciona sin ellos. Si necesitas ayuda, enviame instalar.log
) else (
  echo  Instalacion completa sin errores.
)
echo ==========================================
echo Jarvis quedo en: %CD%
echo Abrelo con el acceso directo del Escritorio o con doble clic en Jarvis.vbs
echo Si no aparece, ejecuta depurar.bat para ver el error.
pause
exit /b 0

:sin_python
echo.
echo No encontre un Python que funcione.
echo Nota: el "python" de la Microsoft Store no sirve, solo abre la tienda.
where winget >nul 2>nul
if errorlevel 1 goto :python_manual
echo Instalo Python 3.12 automaticamente con winget...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
  set "BASEPY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
  goto :tengo_python
)

:python_manual
echo.
echo Instala Python 3.12 desde https://www.python.org/downloads/
echo marcando la casilla "Add python.exe to PATH", y vuelve a ejecutar instalar.bat
goto :fallo

:fallo
echo.
pause
exit /b 1
