# Quita las voces neuronales de JARVIS (Whisper, Piper y sus modelos).
$Dest = Join-Path $env:LOCALAPPDATA 'JarvisVoz'
Get-Process -Name 'whisper-cli', 'piper' -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($Dest, [StringComparison]::OrdinalIgnoreCase) } |
    Stop-Process -Force
if (Test-Path -LiteralPath $Dest) { Remove-Item -LiteralPath $Dest -Recurse -Force }
Write-Host ''
Write-Host '  Voces neuronales desinstaladas. JARVIS vuelve a usar el reconocimiento y la voz de Windows.' -ForegroundColor Green
Write-Host ''
