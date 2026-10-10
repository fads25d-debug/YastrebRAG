param([switch]$Offline, [switch]$NoLaunch)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
. (Join-Path $PSScriptRoot 'scripts/windows-install.ps1')
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$transcript = $false
try {
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
        throw 'This installer requires Windows 10/11 x64.'
    }
    foreach ($port in @(8501, 8502)) {
        $running = $false
        try { $running = (Invoke-RestMethod "http://127.0.0.1:$port/_stcore/health" -TimeoutSec 2) -eq 'ok' } catch { }
        if ($running) { throw "Close the running application on port $port before installing or updating." }
    }
    New-Item -ItemType Directory -Force 'data/logs', 'downloads', 'tools/windows' | Out-Null
    Start-Transcript -Path "data/logs/install-$(Get-Date -Format yyyyMMdd-HHmmss).log" | Out-Null
    $transcript = $true
    Write-Host 'Yastreb setup. Internet is needed for initial downloads (several GB).'
    Install-YastrebRuntime $PSScriptRoot -Offline:$Offline
    Write-Host '[1/5] Preparing local Python 3.12 (no system Python required)...'
    $python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        if ($Offline) { throw 'Offline installation needs a prepared Python environment. Run online setup first.' }
        Get-VerifiedDownload 'https://github.com/astral-sh/uv/releases/download/0.8.22/uv-x86_64-pc-windows-msvc.zip' `
            (Join-Path $PSScriptRoot 'downloads/uv-windows.zip') '5049375aa2a5162f132b2c1cb992e25d42d47d934cab8c174dbe6f60973dcc12'
        Expand-Archive -LiteralPath 'downloads/uv-windows.zip' -DestinationPath 'tools/windows' -Force
        $uv = Join-Path $PSScriptRoot 'tools/windows/uv.exe'
        $env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot 'tools/windows/python'
        $env:UV_PYTHON_BIN_DIR = Join-Path $PSScriptRoot 'tools/windows/bin'
        $env:UV_CACHE_DIR = Join-Path $PSScriptRoot 'downloads/uv-cache'
        Invoke-Checked $uv @('python', 'install', '3.12.11', '--no-registry')
        Invoke-Checked $uv @('venv', '--python', '3.12.11', '--managed-python', '--seed', '.venv')
    }
    Invoke-Checked $python @('-c', 'import sys; assert sys.version_info[:2] == (3,12) and sys.maxsize > 2**32')
    # Recover a venv interrupted before pip seeding completed.
    Invoke-Checked $python @('-m', 'ensurepip', '--upgrade')
    Write-Host '[2/5] Installing Python packages...'
    if ($Offline) {
        Invoke-Checked $python @('-m', 'pip', 'install', '--no-index', '--find-links', 'wheelhouse', '-r', 'requirements-lock.txt')
    } else {
        Invoke-Checked $python @('-m', 'pip', 'install', '-r', 'requirements-lock.txt')
    }
    Invoke-Checked $python @('-m', 'pip', 'check')
    Write-Host '[3/5] Preparing local Ollama...'
    if (-not (Test-Path -LiteralPath 'tools/ollama/.setup-complete-0.34.0')) {
        if ($Offline) { throw 'Ollama is missing. Run online setup first.' }
        Get-VerifiedDownload 'https://github.com/ollama/ollama/releases/download/v0.34.0/ollama-windows-amd64.zip' `
            (Join-Path $PSScriptRoot 'downloads/ollama-windows.zip') 'a7dd1b174f39d3d1b8a25d4cbc86045d0e190b17187bfdcbe2f2ee3b5a11470e'
        $stage = Join-Path $PSScriptRoot ('tools/ollama-stage-' + [guid]::NewGuid().ToString('N'))
        Expand-Archive -LiteralPath 'downloads/ollama-windows.zip' -DestinationPath $stage
        if (-not (Test-Path -LiteralPath (Join-Path $stage 'ollama.exe'))) { throw 'Incomplete Ollama archive.' }
        if (Test-Path -LiteralPath 'tools/ollama') {
            Move-Item -LiteralPath 'tools/ollama' -Destination ('tools/ollama-backup-' + [guid]::NewGuid().ToString('N'))
        }
        Move-Item -LiteralPath $stage -Destination 'tools/ollama'
        New-Item -ItemType File -Path 'tools/ollama/.setup-complete-0.34.0' | Out-Null
    }
    if (-not $env:YASTREB_OLLAMA_URL) { $env:YASTREB_OLLAMA_URL = 'http://127.0.0.1:11435' }
    Start-YastrebOllama $PSScriptRoot $env:YASTREB_OLLAMA_URL
    Write-Host '[4/5] Preparing and checking models...'
    $prepareArgs = @('-m', 'scripts.prepare_windows')
    if ($Offline) { $prepareArgs += '--offline' }
    Invoke-Checked $python $prepareArgs
    Write-Host '[5/5] Installation verified. Opening administrator setup...'
    Stop-Transcript | Out-Null
    $transcript = $false
    if (-not $NoLaunch) {
        & (Join-Path $PSScriptRoot 'start.ps1') -Port 8502
        if ($LASTEXITCODE -ne 0) { throw 'Application did not start.' }
    }
} catch {
    Write-Host "INSTALLATION FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'See data/logs/install-*.log. Retry install.cmd after resolving the error.'
    if ($transcript) { Stop-Transcript | Out-Null }
    exit 1
}
