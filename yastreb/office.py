"""Isolated local LibreOffice conversion for PowerPoint imports/previews."""
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZipFile


def office_executable():
    configured = os.environ.get('YASTREB_LIBREOFFICE')
    root = Path(__file__).resolve().parents[1]
    candidates = [configured] if configured else [
        str(root / 'tools/libreoffice/program/soffice.exe'), shutil.which('soffice'),
        str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'LibreOffice/program/soffice.exe'),
        str(Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'LibreOffice/program/soffice.exe')]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise ValueError('Нужен LibreOffice Impress: установите LibreOffice или укажите YASTREB_LIBREOFFICE. Для импорта без него сохраните презентацию как PPTX.')


def convert_presentation(raw, suffix, output):
    executable = office_executable()
    if suffix not in ('.ppt', '.pptx') or output not in ('pptx', 'pdf'):
        raise ValueError('Неподдерживаемый формат преобразования презентации.')
    if suffix == '.ppt' and not raw.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):
        raise ValueError('Файл не является презентацией PPT.')
    if suffix == '.pptx':
        from yastreb.presentations import _xml, MAX_UNPACKED
        try:
            with ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                if len(entries) > 10000 or sum(e.file_size for e in entries) > MAX_UNPACKED:
                    raise ValueError('Превышен лимит распакованной презентации.')
                for item in entries:
                    if item.filename.endswith('.rels'):
                        for rel in _xml(archive, item.filename):
                            if rel.get('TargetMode') == 'External' and not rel.get('Type', '').endswith('/hyperlink'):
                                raise ValueError('Предпросмотр отключён: в презентации есть внешние ресурсы. Вставьте их в файл.')
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError('Повреждённая презентация PPTX.') from exc
    with tempfile.TemporaryDirectory(prefix='yastreb-slides-') as folder:
        directory = Path(folder)
        source = directory / ('input' + suffix)
        source.write_bytes(raw)
        profile = directory / 'profile'
        (profile / 'user').mkdir(parents=True)
        (profile / 'user/registrymodifications.xcu').write_text(
            '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
            '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>'
            '</oor:items>', encoding='utf-8')
        filter_name = ('pptx:Impress MS PowerPoint 2007 XML' if output == 'pptx' else
                       'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}')
        try:
            result = subprocess.run([executable, '-env:UserInstallation=' + profile.as_uri(),
                                     '--headless', '--nologo', '--nodefault', '--nofirststartwizard',
                                     '--convert-to', filter_name, '--outdir', str(directory), str(source)],
                                    capture_output=True, timeout=120,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError('LibreOffice не смог преобразовать презентацию за 120 секунд.') from exc
        target = directory / ('input.' + output)
        if result.returncode or not target.is_file() or not 0 < target.stat().st_size <= 50 * 1024 * 1024:
            raise ValueError('LibreOffice не прочитал презентацию: проверьте пароль, структуру файла и доступную память.')
        return target.read_bytes()
