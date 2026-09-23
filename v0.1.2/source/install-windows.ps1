param([switch]$Offline)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path $python)) {
    if ($Offline) { throw 'Offline installation requires a prepared .venv or local wheelhouse.' }
    py -3.12 -m venv .venv
    $python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
}
if ($Offline) {
    & $python -m pip install --no-index --find-links wheelhouse -r requirements.txt
} else {
    & $python -m pip install -r requirements.txt
}
& $python -m pip check
Write-Host 'Installation complete. Run start.cmd.'
