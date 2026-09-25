"""Local Word extraction and PDF page rendering; no remote document services."""
import html
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from threading import Lock
from xml.etree import ElementTree
from zipfile import ZipFile

PDFIUM_LOCK = Lock()  # PDFium is not thread-safe, even with separate documents.
WORD_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def _convert_doc(raw):
    configured = os.environ.get('YASTREB_LIBREOFFICE')
    executable = configured or shutil.which('soffice')
    if not executable:
        candidate = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'LibreOffice/program/soffice.exe'
        executable = str(candidate) if candidate.is_file() else None
    if not executable:
        raise ValueError('Для старого формата .doc нужен LibreOffice на сервере. Сохраните файл как .docx или установите LibreOffice.')
    if not raw.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):
        raise ValueError('Файл не является документом Word .doc.')
    with tempfile.TemporaryDirectory(prefix='yastreb-word-') as folder:
        root = Path(folder)
        (root / 'input.doc').write_bytes(raw)
        profile = root / 'profile'
        (profile / 'user').mkdir(parents=True)
        (profile / 'user/registrymodifications.xcu').write_text(
            '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
            '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>'
            '<item oor:path="/org.openoffice.Office.Writer/Content/Update">'
            '<prop oor:name="Link" oor:op="fuse"><value>0</value></prop></item></oor:items>', encoding='utf-8')
        try:
            result = subprocess.run([executable, '-env:UserInstallation=' + profile.as_uri(),
                                     '--headless', '--nologo', '--nodefault', '--nofirststartwizard',
                                     '--convert-to', 'docx:Office Open XML Text', '--outdir', str(root),
                                     str(root / 'input.doc')], capture_output=True, timeout=60,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError('Не удалось преобразовать .doc через LibreOffice за 60 секунд.') from exc
        output = root / 'input.docx'
        if result.returncode or not output.is_file() or output.stat().st_size > 50 * 1024 * 1024:
            raise ValueError('LibreOffice не смог прочитать .doc. Проверьте, что документ не повреждён и не защищён паролем.')
        return output.read_bytes()


def word_units(raw, suffix):
    if suffix == '.doc':
        raw = _convert_doc(raw)
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(e.file_size for e in entries) > 100 * 1024 * 1024:
                raise ValueError('Слишком большой распакованный Word-документ.')
            info = archive.getinfo('word/document.xml')
            if info.file_size > 16 * 1024 * 1024:
                raise ValueError('Текст Word-документа превышает 16 МиБ.')
            xml = archive.read(info)
        # Parse only the embedded body; never load linked files or external entities.
        probe = xml.replace(b'\x00', b'').upper()
        if b'<!DOCTYPE' in probe or b'<!ENTITY' in probe:
            raise ValueError('Объявления XML-сущностей не поддерживаются.')
        body = ElementTree.fromstring(xml).find(WORD_NS + 'body')
        if body is None:
            raise ValueError('Тело документа отсутствует.')
        units = []
        # Document-order paragraphs include paragraphs inside table cells.
        for number, paragraph in enumerate(body.iter(WORD_NS + 'p'), 1):
            parts = []
            for node in paragraph.iter():
                if node.tag == WORD_NS + 't':
                    parts.append(node.text or '')
                elif node.tag in (WORD_NS + 'br', WORD_NS + 'cr'):
                    parts.append('\n')
                elif node.tag == WORD_NS + 'tab':
                    parts.append('\t')
            units.append((number, ''.join(parts)))
        if not any(text.strip() for _, text in units):
            raise ValueError('В документе нет извлекаемого текста.')
        return units
    except Exception as exc:
        raise ValueError('Не удалось прочитать Word-документ: ' + str(exc)) from exc


def highlighted_text(text, start=0, end=0):
    """Escape all document content before adding our own highlight markup."""
    if not (0 <= start < end <= len(text)):
        return html.escape(text)
    return html.escape(text[:start]) + '<mark>' + html.escape(text[start:end]) + '</mark>' + html.escape(text[end:])


def render_pdf(raw, page_number):
    import pypdfium2 as pdfium
    with PDFIUM_LOCK, pdfium.PdfDocument(raw) as document:
        if not 1 <= page_number <= len(document):
            raise ValueError('Страница отсутствует.')
        page = document[page_number - 1]
        try:
            width, height = page.get_size()
            scale = min(1.5, 1800 / max(width, height))
            bitmap = page.render(scale=scale)
            try:
                image = bitmap.to_pil()
                try:
                    output = io.BytesIO()
                    image.save(output, format='PNG')
                    return output.getvalue()
                finally:
                    image.close()
            finally:
                bitmap.close()
        finally:
            page.close()
