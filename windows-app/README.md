# JARVIS para Windows

Asistente personal por voz para Windows 10/11, escrito en C# (.NET 8, WPF).

## Instalar

1. Abra **[Releases](https://github.com/zaiddia/Jarvis/releases)** y descargue el último `JARVIS-x.y.z.zip`.
2. Descomprímalo (mejor fuera de OneDrive, por ejemplo en `C:\JARVIS`).
3. Ejecute `instalar.bat`.

El zip ya trae `Jarvis.exe` compilado. Solo hace falta el entorno de escritorio .NET 8; si falta, Windows ofrece descargarlo al abrir JARVIS.

## Cómo está organizado

| Carpeta | Qué hay |
|---|---|
| `codigo/` | El programa (`JarvisApp.csproj`) |
| `pruebas/` | Pruebas automáticas; las frases están en `pruebas/frases.txt` |
| `voces/` | Instalador de las voces neuronales (Piper) y de Whisper |
| `*.bat` | Instalar, compilar a mano y desinstalar |

## Compilación automática

En cada cambio dentro de `windows-app/`, GitHub Actions ([`.github/workflows/windows-app.yml`](../.github/workflows/windows-app.yml)):

1. compila `Jarvis.exe` en Windows,
2. arma el zip para instalar (descargable en la pestaña *Actions*),
3. pasa las pruebas de comprensión,
4. si todas pasan, publica el zip en *Releases*.

## Pruebas de comprensión

Cada línea de `pruebas/frases.txt` es una prueba:

```
qué hora es => Time                      # qué parte de JARVIS la atiende
porfa ábreme Spotify -> abre spotify     # cómo queda la orden tras normalizarla
cuánto es 25 por 4 = 100                 # resultado de una cuenta
```

Si JARVIS no entiende algo, añada la frase aquí con lo que debía hacer: la próxima compilación lo marcará hasta que se arregle.

Para ejecutarlas a mano: `dotnet run --project windows-app/pruebas`.
