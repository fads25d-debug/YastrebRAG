"""Make a non-overwriting transfer snapshot, including an online SQLite backup."""
import argparse
import hashlib
import shutil
import sqlite3
from pathlib import Path


def export(source: Path, target: Path):
    source, target = source.resolve(), target.resolve()
    if target.exists():
        raise FileExistsError(target)
    if target == source or source in target.parents:
        raise ValueError('Export outside the source tree.')
    target.mkdir(parents=True, exist_ok=False)
    names = ['app.py', 'README.md', 'ASTRA.md', 'requirements.txt',
             'requirements-dev.txt', 'pyproject.toml', 'install-astra.sh',
             'start-linux.sh', 'yastreb', 'scripts', 'tests', '.streamlit', 'models',
             'data/library/documents', 'data/library/manifest.json']
    ignore = shutil.ignore_patterns('__pycache__', '*.pyc', '.cache')
    for name in names:
        src, dst = source / name, target / name
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=ignore)
        else:
            shutil.copy2(src, dst)
    database = source / 'data/accounts/users.sqlite'
    if database.exists():
        destination = target / 'data/accounts/users.sqlite'
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as original:
            with sqlite3.connect(destination) as snapshot:
                original.backup(snapshot)
                if snapshot.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                    raise RuntimeError('SQLite snapshot integrity check failed')
    # Full hashes also allow the operator to verify USB/SMB transfer on Linux.
    with (target / 'SHA256SUMS').open('w', encoding='utf-8', newline='\n') as manifest:
        for path in sorted(target.rglob('*')):
            if path.is_file() and path.name != 'SHA256SUMS':
                with path.open('rb') as content:
                    digest = hashlib.file_digest(content, 'sha256').hexdigest()
                manifest.write(f'{digest}  {path.relative_to(target).as_posix()}\n')
    print(f'Export complete: {target}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    export(Path(__file__).resolve().parents[1], args.destination)
