import sqlite3
from pathlib import Path

from scripts import export_astra


def test_transfer_preserves_live_sqlite_but_excludes_windows_and_indexes(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'app.py').write_text('app')
    accounts = source / 'data/accounts'
    accounts.mkdir(parents=True)
    with sqlite3.connect(accounts / 'users.sqlite') as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE sample (value TEXT)')
        db.execute("INSERT INTO sample VALUES ('saved chat')")
        db.commit()
        for name in ['models/bge-m3/weights', 'models/ollama/blobs/weight',
                     'data/library/documents/a.pdf', 'data/library/manifest.json',
                     'data/library/indexes/old', '.venv/Scripts/python.exe',
                     'tools/ollama/ollama.exe', 'data/demo/private']:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'content')
        target = tmp_path / 'export'
        export_astra.export(source, target)
    with sqlite3.connect(target / 'data/accounts/users.sqlite') as db:
        assert db.execute('SELECT value FROM sample').fetchone() == ('saved chat',)
    assert (target / 'models/bge-m3/weights').read_bytes() == b'content'
    assert (target / 'data/library/documents/a.pdf').exists()
    assert not (target / 'data/library/indexes').exists()
    assert not (target / '.venv').exists()
    assert not (target / 'tools/ollama').exists()
    assert not (target / 'data/demo').exists()
    assert (target / 'SHA256SUMS').is_file()


def test_transfer_never_overwrites_existing_folder(tmp_path):
    import pytest
    target = tmp_path / 'existing'
    target.mkdir()
    with pytest.raises(FileExistsError):
        export_astra.export(tmp_path, target)
