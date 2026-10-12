import hashlib
import io
import subprocess

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter

from test_backend import pdf
from yastreb.backend import Backend, BackendError


def scan_pdf():
    image = Image.new('RGB', (600, 800), 'white')
    ImageDraw.Draw(image).text((40, 40), 'Scanned report deadline: 12 days', fill='black')
    output = io.BytesIO()
    image.save(output, format='PDF', resolution=100)
    image.close()
    return output.getvalue()


def test_scan_uses_ocr_and_preserves_original_and_page(tmp_path, monkeypatch):
    from yastreb import ocr
    monkeypatch.setattr(ocr, 'recognize', lambda image: 'Срок подачи отчёта — 12 дней.')
    writer = PdfWriter()
    writer.add_page(PdfReader(io.BytesIO(pdf('Native text'))).pages[0])
    writer.add_page(PdfReader(io.BytesIO(scan_pdf())).pages[0])
    output = io.BytesIO()
    writer.write(output)
    raw = output.getvalue()
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    progress = []
    backend.ingest([('scan.pdf', raw)], can_manage=True, confirmed=True,
                   progress=lambda *event: progress.append(event))
    doc = backend.document(hashlib.sha256(raw).hexdigest())
    assert doc['raw'] == raw
    assert doc['units'] == [(1, 'Native text'), (2, 'Срок подачи отчёта — 12 дней.')]
    assert any(current == total == 2 for _, current, total in progress)
    monkeypatch.setattr(ocr, 'recognize', lambda image: pytest.fail('Duplicate must reuse saved text'))
    assert backend.ingest([('again.pdf', raw)], can_manage=True, confirmed=True)['duplicates'] == 1


def test_pdf_failures_are_distinguishable(tmp_path):
    backend = Backend(tmp_path, tmp_path / 'model')
    with pytest.raises(BackendError, match='повреждён'):
        backend.ingest([('bad.pdf', b'broken')], can_manage=True, confirmed=True)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt('secret')
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(BackendError, match='паролем'):
        backend.ingest([('locked.pdf', output.getvalue())], can_manage=True, confirmed=True)


def test_ocr_failure_does_not_publish_partial_document(tmp_path, monkeypatch):
    from yastreb import ocr
    def failed(image):
        raise ValueError('OCR: превышено время обработки страницы')
    monkeypatch.setattr(ocr, 'recognize', failed)
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    with pytest.raises(BackendError, match='OCR'):
        backend.ingest([('scan.pdf', scan_pdf())], can_manage=True, confirmed=True)
    assert backend.status()['documents'] == 0


def test_missing_engine_has_actionable_error(monkeypatch, tmp_path):
    from yastreb import ocr
    monkeypatch.setenv('YASTREB_TESSERACT', str(tmp_path / 'missing.exe'))
    with pytest.raises(ValueError, match='install.cmd'):
        ocr.check_available()


def test_timeout_is_not_reported_as_corrupt_pdf(monkeypatch):
    from yastreb import ocr
    monkeypatch.setattr(ocr, 'check_available', lambda: ('tesseract', None))
    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired('tesseract', 120)
    monkeypatch.setattr(ocr.subprocess, 'run', timed_out)
    with Image.new('RGB', (100, 100), 'white') as image:
        with pytest.raises(ValueError, match='время'):
            ocr.recognize(image)


def test_empty_scan_not_silently_accepted(tmp_path, monkeypatch):
    from yastreb import ocr
    monkeypatch.setattr(ocr, 'recognize', lambda image: '')
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    with pytest.raises(BackendError, match='распознать'):
        backend.ingest([('scan.pdf', scan_pdf())], can_manage=True, confirmed=True)


def test_native_page_number_does_not_hide_scan(monkeypatch):
    from yastreb import ocr
    writer = PdfWriter()
    page = writer.add_page(PdfReader(io.BytesIO(scan_pdf())).pages[0])
    page.merge_page(PdfReader(io.BytesIO(pdf('1'))).pages[0])
    output = io.BytesIO()
    writer.write(output)
    monkeypatch.setattr(ocr, 'recognize', lambda image: 'Scanned report deadline: 12 days')
    assert '12 days' in ocr.pdf_units(output.getvalue())[0][1]


def test_unrecognized_nonblank_page_warning_survives_reload(tmp_path, monkeypatch):
    from yastreb import ocr
    writer = PdfWriter()
    for _ in range(2):
        writer.add_page(PdfReader(io.BytesIO(scan_pdf())).pages[0])
    writer.add_blank_page(width=200, height=200)
    output = io.BytesIO()
    writer.write(output)
    raw = output.getvalue()
    responses = iter(['Recognized first page', ''])
    monkeypatch.setattr(ocr, 'recognize', lambda image: next(responses))
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    report = backend.ingest_folder([('scan.pdf', raw)], can_manage=True, confirmed=True)
    assert report['added'] == 1
    assert [w['page'] for w in report.get('warnings', [])] == [2]
    reloaded = Backend(tmp_path / 'library', tmp_path / 'model')
    doc = reloaded.document(hashlib.sha256(raw).hexdigest())
    assert [w['page'] for w in doc['ocr_warnings']] == [2]
    assert doc['units'] == [(1, 'Recognized first page'), (2, ''), (3, '')]
    duplicate = reloaded.ingest_folder([('scan.pdf', raw)], can_manage=True, confirmed=True)
    assert duplicate['warnings'] == report['warnings']


def compressed_pdf(pages, decoded_size, fake_image=False):
    from pypdf.generic import NameObject, DecodedStreamObject, DictionaryObject
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_page(PdfReader(io.BytesIO(pdf('Native text'))).pages[0])
        stream = DecodedStreamObject()
        stream.set_data(b' ' * decoded_size + page.get_contents().get_data())
        encoded = stream.flate_encode()
        if fake_image:
            encoded[NameObject('/Subtype')] = NameObject('/Image')
            # The same object can be reached as an image resource before Contents.
            page['/Resources'][NameObject('/XObject')] = DictionaryObject({
                NameObject('/FakeImage'): writer._add_object(encoded)})
        page[NameObject('/Contents')] = writer._add_object(encoded)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize('limit, pages, size', [
    ('MAX_DECODED_BYTES', 4, 32_768),
    ('MAX_STREAM_BYTES', 1, 131_072),
])
def test_compressed_pdf_exceeds_budget_without_partial_import(tmp_path, monkeypatch, limit, pages, size):
    from yastreb import ocr
    monkeypatch.setattr(ocr, limit, 65_536, raising=False)
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    with pytest.raises(BackendError, match='лимит'):
        backend.ingest([('compressed.pdf', compressed_pdf(pages, size))], can_manage=True, confirmed=True)
    assert backend.status()['documents'] == 0


def test_content_disguised_as_image_still_consumes_budget(tmp_path, monkeypatch):
    from yastreb import ocr
    monkeypatch.setattr(ocr, 'MAX_DECODED_BYTES', 65_536)
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    with pytest.raises(BackendError, match='лимит'):
        backend.ingest([('fake-image.pdf', compressed_pdf(4, 32_768, True))], can_manage=True, confirmed=True)
    assert backend.status()['documents'] == 0


def test_bad_content_stream_does_not_abort_folder(tmp_path):
    from pypdf.generic import NameObject, EncodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    stream = EncodedStreamObject()
    stream._data = b'GG>'
    stream[NameObject('/Filter')] = NameObject('/ASCIIHexDecode')
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    report = backend.ingest_folder([('bad.pdf', output.getvalue()), ('good.pdf', pdf())],
                                   can_manage=True, confirmed=True)
    assert report['added'] == 1
    assert [error['file'] for error in report['errors']] == ['bad.pdf']
    assert backend.status()['documents'] == 1


def test_live_ocr_when_installed():
    from yastreb import ocr
    from PIL import ImageFont
    if not (ocr.ROOT / 'tools/tesseract/tesseract.exe').is_file():
        pytest.skip('Optional live OCR check; engine installed by Windows setup')
    ocr.check_available()
    with Image.new('RGB', (1600, 450), 'white') as image:
        font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 60)
        ImageDraw.Draw(image).text((60, 120), 'Срок подачи отчёта 12 дней', font=font, fill='black')
        text = ocr.recognize(image)
    assert '12' in text and 'дней' in text and 'подачи' in text


def test_missing_russian_language_is_not_ready(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from yastreb import ocr
    executable = tmp_path / 'tesseract.exe'
    executable.touch()
    monkeypatch.setenv('YASTREB_TESSERACT', str(executable))
    monkeypatch.setattr(ocr.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=b'eng\n'))
    with pytest.raises(ValueError, match='rus/eng'):
        ocr.check_available()


def test_cyrillic_tessdata_uses_unicode_working_directory(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from yastreb import ocr
    executable = tmp_path / 'Ястреб' / 'tesseract.exe'
    executable.parent.mkdir()
    executable.touch()
    data = executable.parent / 'русские языки'
    data.mkdir()
    monkeypatch.setenv('YASTREB_TESSERACT', str(executable))
    monkeypatch.setenv('YASTREB_TESSDATA', str(data))
    def engine(command, **kwargs):
        # Simulate the native CLI's inability to decode a Unicode argv path.
        if '--tessdata-dir' not in command or command[command.index('--tessdata-dir') + 1] != '.' or kwargs.get('cwd') != str(data):
            return SimpleNamespace(returncode=1, stdout=b'')
        return SimpleNamespace(returncode=0, stdout=b'rus\neng\n')
    monkeypatch.setattr(ocr.subprocess, 'run', engine)
    assert ocr.check_available() == (str(executable), str(data))
