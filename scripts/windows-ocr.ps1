# Portable OCR: extract official, checksum-pinned packages; no registry or PATH changes.
# Get-VerifiedDownload and Invoke-Checked come from windows-install.ps1.
function Install-YastrebOcr {
    param([string]$Root, [switch]$Offline)
    $ErrorActionPreference = 'Stop'
    $Root = [IO.Path]::GetFullPath($Root)
    $target = Join-Path $Root 'tools/tesseract'
    $marker = Join-Path $target '.portable-5.5.3'
    if (-not (Test-Path -LiteralPath $marker) -or -not (Test-Path -LiteralPath (Join-Path $target 'tesseract.exe'))) {
        if ($Offline) { throw 'OCR is missing. Run install.cmd with Internet access first.' }
        New-Item -ItemType Directory -Force (Join-Path $Root 'downloads'), (Join-Path $Root 'tools/windows') | Out-Null
        Get-VerifiedDownload 'https://github.com/ip7z/7zip/releases/download/26.04/7zr.exe' `
            (Join-Path $Root 'downloads/7zr.exe') '256feca8e274e5da655e2a284fabafd9f554365eb164862089dacd4e8276d282'
        Get-VerifiedDownload 'https://github.com/ip7z/7zip/releases/download/26.04/7z2604-x64.exe' `
            (Join-Path $Root 'downloads/7zip.exe') 'd54bf805f9f3704d1e8db2fa3498ae7ef2df0312b40b558e7c71c734430a665d'
        Get-VerifiedDownload 'https://github.com/tesseract-ocr/tesseract/releases/download/5.5.3/tesseract-ocr-w64-setup-5.5.3.20260724.exe' `
            (Join-Path $Root 'downloads/tesseract-5.5.3.exe') 'bee9e3434bd94fd65387d9be28cd467a41f61b1275383b55b0f59a1331270ae4'
        Push-Location -LiteralPath $Root
        try {
            Invoke-Checked (Join-Path $Root 'downloads/7zr.exe') @('x', 'downloads/7zip.exe', '-otools/windows/7zip', '-y', '-bso0')
            $stage = 'tools/tesseract-stage-' + [guid]::NewGuid().ToString('N')
            Invoke-Checked (Join-Path $Root 'tools/windows/7zip/7z.exe') @('x', 'downloads/tesseract-5.5.3.exe', "-o$stage", '-y', '-bso0')
            if (-not (Test-Path -LiteralPath "$stage/tesseract.exe")) { throw 'Incomplete OCR archive.' }
            if (Test-Path -LiteralPath $target) {
                # Both exact paths are children of the explicit project root.
                Rename-Item -LiteralPath $target -NewName ('tesseract-backup-' + [guid]::NewGuid().ToString('N'))
            }
            Move-Item -LiteralPath (Join-Path $Root $stage) -Destination $target
            New-Item -ItemType File -Path $marker | Out-Null
        } finally { Pop-Location }
    }
    $languages = @{
        rus = 'e16e5e036cce1d9ec2b00063cf8b54472625b9e14d893a169e2b0dedeb4df225'
        eng = '7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2'
    }
    foreach ($language in $languages.Keys) {
        $destination = Join-Path $target "tessdata/$language.traineddata"
        $valid = (Test-Path -LiteralPath $destination) -and (Get-YastrebFileHash $destination) -eq $languages[$language]
        if (-not $valid) {
            if ($Offline) { throw "OCR language $language is missing or damaged. Run online setup." }
            Get-VerifiedDownload "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/$language.traineddata" `
                $destination $languages[$language]
        }
    }
}
