import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which('powershell.exe'), reason='Windows only')
@pytest.mark.parametrize('name', ['start.ps1', 'install-windows.ps1', 'scripts/windows-install.ps1', 'scripts/windows-ocr.ps1'])
def test_launcher_parses_in_windows_powershell(name):
    script = Path(__file__).resolve().parents[1] / name
    command = (
        "$tokens=$null; $errors=$null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{script}', "
        "[ref]$tokens, [ref]$errors) | Out-Null; "
        "$errors | ForEach-Object { Write-Output $_.Message }; "
        "if ($errors.Count) { exit 1 }"
    )
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
