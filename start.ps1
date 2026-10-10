param([switch]$Demo, [string]$SetupEmail = '', [int]$Port = 8501)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path $pythonPath)) { throw 'Missing .venv. See README.md to install Python dependencies.' }
# Reopening the shortcut must not fail when the local interface is already running.
$existing = $false
try {
    $health = Invoke-RestMethod "http://127.0.0.1:$Port/_stcore/health" -TimeoutSec 2 -MaximumRedirection 0
    $existing = ($health -eq 'ok')
} catch { }
if ($existing) {
    Write-Host "Opening the running local interface: http://127.0.0.1:$Port"
    Start-Process "http://127.0.0.1:$Port"
    exit 0
}
$env:YASTREB_DEMO = if ($Demo) { '1' } else { '0' }
$env:YASTREB_SETUP_EMAIL = $SetupEmail
$env:YASTREB_SETUP = if ($Demo) { '0' } else { '1' }
# This workstation's GTX 1050 Ti fails CUDA initialization with bundled Ollama.
# 0 is a reliable CPU default; an explicit environment value overrides it.
if (-not $env:YASTREB_NUM_GPU) { $env:YASTREB_NUM_GPU = '0' }
if (-not $Demo) {
    . (Join-Path $PSScriptRoot 'scripts/windows-install.ps1')
    $ollamaUrl = if ($env:YASTREB_OLLAMA_URL) { $env:YASTREB_OLLAMA_URL.TrimEnd('/') } else { 'http://127.0.0.1:11435' }
    $env:YASTREB_OLLAMA_URL = $ollamaUrl
    & $pythonPath -c "import os; from pathlib import Path; from yastreb.backend import Backend; Backend(Path('data/library'),Path('models/bge-m3'),os.environ['YASTREB_OLLAMA_URL'])"
    if ($LASTEXITCODE -ne 0) { throw 'Invalid local Ollama URL.' }
    Start-YastrebOllama $PSScriptRoot $ollamaUrl
    $ready = $false
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        try {
            $tags = Invoke-RestMethod "$ollamaUrl/api/tags" -TimeoutSec 2 -MaximumRedirection 0
            $ready = $true
            break
        } catch { Start-Sleep -Seconds 1 }
    }
    if (-not $ready) { throw 'Ollama failed to start. See data/logs/ollama.err.log.' }
    $model = if ($env:YASTREB_OLLAMA_MODEL) { $env:YASTREB_OLLAMA_MODEL } else { 'qwen2.5:7b' }
    if ($model -notin @($tags.models.name)) { throw "Model $model is missing. See README.md." }
    & $pythonPath -m scripts.check_environment
    if ($LASTEXITCODE -ne 0) { throw 'Environment is incomplete. Run install.cmd. See the checks above.' }
}
Write-Host "Yastreb: http://127.0.0.1:$Port -- keep this window open."
& $pythonPath -m streamlit run app.py --server.address 127.0.0.1 --server.headless false --server.showEmailPrompt false --server.port $Port
exit $LASTEXITCODE
