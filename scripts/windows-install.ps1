# Shared setup primitives. Dot-sourcing never installs anything.
function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed with exit code $LASTEXITCODE" }
}

function Get-YastrebFileHash {
    param([string]$Path)
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}

function Get-VerifiedDownload {
    param([string]$Url, [string]$Destination, [string]$Sha256)
    if ((Test-Path -LiteralPath $Destination) -and
        (Get-YastrebFileHash $Destination) -eq $Sha256) { return }
    $partial = "$Destination.part"
    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        Invoke-Checked 'curl.exe' @('--fail', '--location', '--retry', '3', '--connect-timeout', '30', '--output', $partial, $Url)
    } else {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $partial
    }
    if ((Get-YastrebFileHash $partial) -ne $Sha256) {
        throw "Checksum mismatch: $Destination. Nothing was executed. Retry installation."
    }
    Move-Item -LiteralPath $partial -Destination $Destination -Force
}

function Install-YastrebRuntime {
    param([string]$Root, [switch]$Offline)
    $runtime = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64' -ErrorAction SilentlyContinue
    if ($runtime -and $runtime.Installed -eq 1 -and [version]($runtime.Version.TrimStart('v')) -ge [version]'14.40') { return }
    if ($Offline) { throw 'Microsoft Visual C++ x64 Runtime is missing. Run online setup.' }
    Write-Host 'Installing Microsoft Visual C++ Runtime. Windows may ask for UAC approval.'
    $installer = Join-Path $Root 'downloads/vc_redist.x64.exe'
    Invoke-WebRequest -UseBasicParsing 'https://aka.ms/vc14/vc_redist.x64.exe' -OutFile $installer
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'CN=Microsoft Corporation,') {
        throw 'Microsoft Visual C++ installer signature verification failed.'
    }
    $process = Start-Process -FilePath $installer -ArgumentList '/install', '/quiet', '/norestart' `
        -Verb RunAs -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -eq 3010) { throw 'Visual C++ installed. Restart Windows, then run install.cmd again.' }
    if ($process.ExitCode -notin @(0, 1638)) { throw "Visual C++ installation failed: $($process.ExitCode)" }
}

function Assert-YastrebOllamaOwner {
    param([string]$Executable)
    $listener = Get-NetTCPConnection -LocalPort 11435 -State Listen -ErrorAction Stop | Select-Object -First 1
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if (-not $owner.ExecutablePath -or
        [IO.Path]::GetFullPath($owner.ExecutablePath) -ne [IO.Path]::GetFullPath($Executable)) {
        throw 'Port 11435 belongs to another installation. Close that Ollama instance before continuing.'
    }
}

function Start-YastrebOllama {
    param([string]$Root, [string]$Url = 'http://127.0.0.1:11435')
    $executable = Join-Path $Root 'tools/ollama/ollama.exe'
    $responding = $false
    try {
        Invoke-RestMethod "$Url/api/version" -TimeoutSec 3 -MaximumRedirection 0 | Out-Null
        $responding = $true
    } catch { }
    if ($responding) {
        if ($Url -eq 'http://127.0.0.1:11435') {
            Assert-YastrebOllamaOwner $executable
        }
        return
    }
    if ($Url -ne 'http://127.0.0.1:11435') {
        throw "Configured Ollama is not available at $Url. Start it separately."
    }
    if (-not (Test-Path -LiteralPath $executable)) { throw 'Ollama is missing. Run install.cmd.' }
    $env:OLLAMA_MODELS = Join-Path $Root 'models/ollama'
    $env:OLLAMA_HOST = '127.0.0.1:11435'
    $env:OLLAMA_NO_CLOUD = '1'
    $logs = Join-Path $Root 'data/logs'
    New-Item -ItemType Directory -Force $logs | Out-Null
    Start-Process -FilePath $executable -ArgumentList 'serve' -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs 'ollama-setup.out.log') `
        -RedirectStandardError (Join-Path $logs 'ollama-setup.err.log') | Out-Null
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            Invoke-RestMethod "$Url/api/version" -TimeoutSec 2 -MaximumRedirection 0 | Out-Null
        } catch { Start-Sleep -Seconds 1; continue }
        Assert-YastrebOllamaOwner $executable
        return
    }
    throw 'Ollama did not start. See data/logs/ollama-setup.err.log.'
}
