import subprocess
import shutil
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_powershell(command):
    env = dict(os.environ)
    # Do not pass PowerShell 7's module search path into Windows PowerShell 5.1.
    env.pop('PSModulePath', None)
    return subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                           '-Command', command], capture_output=True, text=True, env=env)


@pytest.mark.skipif(not shutil.which('powershell.exe'), reason='Windows only')
def test_native_failure_stops_installation():
    command = (
        f". '{ROOT / 'scripts/windows-install.ps1'}'; "
        "try { Invoke-Checked $env:ComSpec @('/c', 'exit 7'); 'FALSE_SUCCESS'; exit 0 } "
        "catch { Write-Output $_.Exception.Message; exit 7 }"
    )
    result = run_powershell(command)
    assert result.returncode == 7
    assert 'FALSE_SUCCESS' not in result.stdout
    assert 'exit code 7' in result.stdout


def test_offline_setup_rejects_missing_embedding_model(tmp_path):
    from scripts.prepare_windows import ensure_embeddings
    with pytest.raises(RuntimeError, match='model'):
        ensure_embeddings(tmp_path / 'missing', offline=True)


def test_missing_ollama_model_is_not_success(monkeypatch):
    from scripts import prepare_windows
    monkeypatch.setattr(prepare_windows, 'ollama_request', lambda *a, **k: {'models': []})
    with pytest.raises(RuntimeError, match='qwen2.5:7b'):
        prepare_windows.ensure_llm(offline=True)


def test_ollama_stream_propagates_download_failure(monkeypatch):
    import io
    from types import SimpleNamespace
    from scripts import prepare_windows
    monkeypatch.setattr(prepare_windows, 'build_opener', lambda *args: SimpleNamespace(
        open=lambda *args, **kwargs: io.BytesIO(b'{"status":"pulling"}\n{"error":"disk full"}\n')))
    with pytest.raises(RuntimeError, match='disk full'):
        prepare_windows.ollama_request('/api/pull', {'stream': True})


def test_embedding_signature_ignores_download_cache(tmp_path):
    from yastreb.backend import Backend
    model = tmp_path / 'model'
    model.mkdir()
    (model / 'config.json').write_text('{}')
    backend = Backend(tmp_path / 'data', model)
    before = backend._embedding_signature()
    cache = model / '.cache'
    cache.mkdir()
    (cache / 'download.lock').write_text('changed metadata')
    assert backend._embedding_signature() == before


@pytest.mark.skipif(not shutil.which('powershell.exe'), reason='Windows only')
@pytest.mark.parametrize('delayed', [False, True])
def test_setup_rejects_daemon_from_another_copy(tmp_path, delayed):
    executable = tmp_path / 'tools/ollama/ollama.exe'
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b'test placeholder, never executed')
    probe = ("$script:probes=0; function Invoke-RestMethod { $script:probes++; "
             "if ($script:probes -eq 1) { throw 'not ready' }; return @{version='0.34.0'} }; "
             if delayed else "function Invoke-RestMethod { return @{version='0.34.0'} }; ")
    command = (
        f". '{ROOT / 'scripts/windows-install.ps1'}'; "
        + probe +
        "function Start-Process { }; "
        "function Get-NetTCPConnection { return @{OwningProcess=123} }; "
        "function Get-CimInstance { return @{ExecutablePath='C:/other/ollama.exe'} }; "
        f"try {{ Start-YastrebOllama '{tmp_path}'; exit 0 }} "
        "catch { Write-Output $_.Exception.Message; exit 3 }"
    )
    result = run_powershell(command)
    assert result.returncode == 3
    assert 'another installation' in result.stdout


@pytest.mark.skipif(not shutil.which('powershell.exe'), reason='Windows only')
def test_verified_download_reuses_valid_archive_without_network(tmp_path):
    import hashlib
    archive = tmp_path / 'download.zip'
    archive.write_bytes(b'checked archive')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    command = (
        "$ErrorActionPreference='Stop'; "
        f". '{ROOT / 'scripts/windows-install.ps1'}'; "
        f"Get-VerifiedDownload 'https://invalid.invalid/archive' '{archive}' '{digest}'"
    )
    result = run_powershell(command)
    assert result.returncode == 0, result.stdout + result.stderr
    assert archive.read_bytes() == b'checked archive'


@pytest.mark.skipif(not shutil.which('powershell.exe'), reason='Windows only')
def test_missing_native_runtime_stops_offline_setup(tmp_path):
    command = (
        f". '{ROOT / 'scripts/windows-install.ps1'}'; "
        "function Get-ItemProperty { return $null }; "
        f"try {{ Install-YastrebRuntime '{tmp_path}' -Offline; exit 0 }} "
        "catch { Write-Output $_.Exception.Message; exit 4 }"
    )
    result = run_powershell(command)
    assert result.returncode == 4
    assert 'Visual C++' in result.stdout


@pytest.mark.skipif(not shutil.which('powershell.exe'), reason='Windows only')
def test_missing_ocr_stops_offline_setup(tmp_path):
    command = (
        f". '{ROOT / 'scripts/windows-install.ps1'}'; "
        f". '{ROOT / 'scripts/windows-ocr.ps1'}'; "
        f"try {{ Install-YastrebOcr '{tmp_path}' -Offline; exit 0 }} "
        "catch { Write-Output $_.Exception.Message; exit 5 }"
    )
    result = run_powershell(command)
    assert result.returncode == 5
    assert 'OCR is missing' in result.stdout
