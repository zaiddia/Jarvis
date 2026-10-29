# Instala las voces neuronales de JARVIS para tu usuario de Windows
# (no necesita permisos de administrador):
#   - Whisper (whisper.cpp): entiende lo que dices, en tu equipo y sin internet.
#   - Piper: voz natural en español, también local.
# Todo queda en %LOCALAPPDATA%\JarvisVoz. Para quitarlo: desinstalar-voces-jarvis.bat

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Dest = Join-Path $env:LOCALAPPDATA 'JarvisVoz'
$WhisperZip = 'https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.2/whisper-bin-x64.zip'
$PiperZip = 'https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip'
$HfWhisper = 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main'
$HfVoices = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/es'

function Say($text, $color = 'Gray') { Write-Host $text -ForegroundColor $color }

function Get-File($url, $out, $label) {
    Say "       $label…"
    $tmp = "$out.descargando"
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $tmp
    Move-Item -LiteralPath $tmp -Destination $out -Force
}

# Texto en un archivo temporal UTF-8 (para pasárselo a Piper como entrada).
function New-TextFile($text) {
    $f = Join-Path $env:TEMP 'jarvis-prueba.txt'
    [IO.File]::WriteAllText($f, $text + "`n", (New-Object System.Text.UTF8Encoding($false)))
    return $f
}

function Ask($question, $options, $default) {
    Say ''
    Say "  $question" 'Cyan'
    for ($i = 0; $i -lt $options.Count; $i++) { Say ("    {0}) {1}" -f ($i + 1), $options[$i]) }
    $answer = Read-Host "  Elige un número (Enter = $default)"
    $n = 0
    if ([int]::TryParse($answer, [ref]$n) -and $n -ge 1 -and $n -le $options.Count) { return $n }
    return $default
}

try {
    Say ''
    Say '  JARVIS · voces neuronales' 'Cyan'
    Say '  -------------------------' 'Cyan'

    $model = Ask '¿Qué modelo de Whisper quieres? (cuanto más grande, mejor entiende y más tarda)' @(
        'Rápido   · base  ·  60 MB · para equipos modestos',
        'Preciso  · small · 190 MB · recomendado',
        'Máximo   · large-v3-turbo · 570 MB · para procesadores potentes') 2
    $modelFile = @('ggml-base-q5_1.bin', 'ggml-small-q5_1.bin', 'ggml-large-v3-turbo-q5_0.bin')[$model - 1]

    # Todas las voces oficiales de Piper en español (las de calidad «low» no se ofrecen: suenan peor que estas).
    $voices = @(
        @{ name = 'es_MX-ald-medium';     path = 'es_MX/ald/medium';     label = 'Hombre · México (Ald) · calidad media · recomendada para JARVIS' },
        @{ name = 'es_ES-davefx-medium';  path = 'es_ES/davefx/medium';  label = 'Hombre · España (Davefx) · calidad media' },
        @{ name = 'es_ES-sharvard-medium'; path = 'es_ES/sharvard/medium'; label = 'Hombre y mujer · España (Sharvard) · calidad media · dos voces en una' },
        @{ name = 'es_MX-claude-high';    path = 'es_MX/claude/high';    label = 'Mujer · México (Claude) · calidad alta' },
        @{ name = 'es_AR-daniela-high';   path = 'es_AR/daniela/high';   label = 'Mujer · Argentina (Daniela) · calidad alta' },
        @{ name = 'es_ES-carlfm-x_low';   path = 'es_ES/carlfm/x_low';   label = 'Hombre · España (Carlfm) · calidad baja, muy ligera' })
    $labels = @($voices | ForEach-Object { $_.label }) + @('Instalar todas (unos 500 MB) y elegir después diciendo «cambia la voz a …»')
    $voice = Ask '¿Qué voz quieres para JARVIS?' $labels 1
    if ($voice -eq $labels.Count) { $pick = $voices } else { $pick = @($voices[$voice - 1]) }

    foreach ($d in 'whisper', 'modelos', 'piper', 'voces') {
        New-Item -ItemType Directory -Force -Path (Join-Path $Dest $d) | Out-Null
    }
    $tmpDir = Join-Path $env:TEMP 'jarvis-voces'
    New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

    Say ''
    Say '  1/4  Whisper (programa)' 'White'
    if (Test-Path -LiteralPath (Join-Path $Dest 'whisper\whisper-cli.exe')) { Say '       ya estaba instalado' 'Green' } else {
    $zip = Join-Path $tmpDir 'whisper.zip'
    Get-File $WhisperZip $zip 'descargando whisper.cpp 1.9.2'
    $unz = Join-Path $tmpDir 'whisper'
    if (Test-Path $unz) { Remove-Item $unz -Recurse -Force }
    Expand-Archive -LiteralPath $zip -DestinationPath $unz -Force
    $cli = Get-ChildItem -LiteralPath $unz -Recurse -Filter 'whisper-cli.exe' | Select-Object -First 1
    if (-not $cli) { throw 'No encontré whisper-cli.exe en el paquete de Whisper.' }
    Get-ChildItem -LiteralPath $cli.DirectoryName -File |
        Where-Object { $_.Extension -eq '.dll' -or $_.Name -eq 'whisper-cli.exe' } |
        Copy-Item -Destination (Join-Path $Dest 'whisper') -Force
    Say '       listo' 'Green'
    }

    Say '  2/4  Whisper (modelo de voz en español)' 'White'
    $modelPath = Join-Path $Dest "modelos\$modelFile"
    if (Test-Path -LiteralPath $modelPath) { Say '       ya estaba descargado' 'Green' }
    else { Get-File "$HfWhisper/$modelFile" $modelPath "descargando $modelFile"; Say '       listo' 'Green' }

    Say '  3/4  Piper (programa de voz)' 'White'
    if (Test-Path -LiteralPath (Join-Path $Dest 'piper\piper.exe')) { Say '       ya estaba instalado' 'Green' } else {
    $zip = Join-Path $tmpDir 'piper.zip'
    Get-File $PiperZip $zip 'descargando Piper'
    $unz = Join-Path $tmpDir 'piper'
    if (Test-Path $unz) { Remove-Item $unz -Recurse -Force }
    Expand-Archive -LiteralPath $zip -DestinationPath $unz -Force
    $exe = Get-ChildItem -LiteralPath $unz -Recurse -Filter 'piper.exe' | Select-Object -First 1
    if (-not $exe) { throw 'No encontré piper.exe en el paquete de Piper.' }
    Copy-Item -Path (Join-Path $exe.DirectoryName '*') -Destination (Join-Path $Dest 'piper') -Recurse -Force
    Say '       listo' 'Green'
    }

    Say '  4/4  Voces en español' 'White'
    foreach ($v in $pick) {
        foreach ($ext in '.onnx', '.onnx.json') {
            $out = Join-Path $Dest ("voces\" + $v.name + $ext)
            if (-not (Test-Path -LiteralPath $out)) { Get-File ("$HfVoices/" + $v.path + '/' + $v.name + $ext) $out ($v.name + $ext) }
        }
    }
    Say '       listo' 'Green'

    Remove-Item $tmpDir -Recurse -Force -ErrorAction SilentlyContinue

    # Prueba de las voces. Piper escribe avisos informativos en la salida
    # de errores; no son fallos, así que aquí no deben detener el instalador.
    $piperExe = Join-Path $Dest 'piper\piper.exe'
    function Test-Voice($v, $speaker) {
        $test = Join-Path $env:TEMP 'jarvis-prueba.wav'
        $voicePath = Join-Path $Dest ("voces\" + $v.name + '.onnx')
        $oldPref = $ErrorActionPreference
        $ErrorActionPreference = 'SilentlyContinue'
        try {
            if (Test-Path $test) { Remove-Item $test -Force }
            $pargs = @('--model', "`"$voicePath`"", '--output_file', "`"$test`"")
            if ($speaker -ne $null) { $pargs += @('--speaker', "$speaker") }
            Start-Process -FilePath $piperExe -ArgumentList $pargs `
                -RedirectStandardInput (New-TextFile 'Sistemas en línea. Para usted, señor, siempre.') `
                -RedirectStandardError (Join-Path $env:TEMP 'jarvis-piper-log.txt') -NoNewWindow -Wait | Out-Null
            if (Test-Path $test) {
                (New-Object Media.SoundPlayer $test).PlaySync()
                Remove-Item $test -Force
            } else {
                Say '       (No pude reproducir esta voz, pero quedó instalada.)' 'Yellow'
            }
        } catch {
            Say '       (No pude reproducir esta voz, pero quedó instalada.)' 'Yellow'
        } finally {
            $ErrorActionPreference = $oldPref
        }
    }
    Say ''
    foreach ($v in $pick) {
        if ($v.name -eq 'es_ES-sharvard-medium') {
            Say ("  Así suena: " + $v.label + ' — voz de hombre') 'White'; Test-Voice $v 0
            Say ("  Así suena: " + $v.label + ' — voz de mujer') 'White'; Test-Voice $v 1
        } else {
            Say ("  Así suena: " + $v.label) 'White'; Test-Voice $v $null
        }
    }

    Say ''
    Say '  Para cambiar de voz, dile a JARVIS por ejemplo «cambia la voz a Daniela» o «¿qué voces tienes?».' 'Cyan'
    Say '  También puedes elegirla en los ajustes de JARVIS (pestaña Voz).' 'Cyan'
    Say ''
    Say '  Voces neuronales instaladas.' 'Green'
    Say "  Carpeta: $Dest"
    Say '  En Windhawk, abre los ajustes de JARVIS y pulsa Guardar (o desactívalo y actívalo)' 'Cyan'
    Say '  para que empiece a usarlas.' 'Cyan'
    Say ''
} catch {
    Say ''
    Say ('  No se pudo instalar: ' + $_.Exception.Message) 'Red'
    Say '  Revisa tu conexión a internet y vuelve a ejecutar «instalar-voces-jarvis.bat».' 'Yellow'
    Say ''
    exit 1
}
