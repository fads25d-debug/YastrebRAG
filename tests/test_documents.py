import hashlib
import io
from pathlib import Path
from zipfile import ZipFile

import pytest

from yastreb.backend import Backend, BackendError
from test_backend import pdf


def docx(text='Порядок подачи отчёта', table='Срок — 12 дней'):
    from xml.sax.saxutils import escape
    xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:body><w:p><w:r><w:t>' + escape(text) + '</w:t></w:r></w:p>'
           '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>' + escape(table) +
           '</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
    raw = io.BytesIO()
    with ZipFile(raw, 'w') as archive:
        archive.writestr('word/document.xml', xml)
    return raw.getvalue()


def test_folder_import_pdf_word_nested_duplicates_and_bad_file(tmp_path):
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    raw = docx()
    report = backend.ingest_folder([
        ('Приказы/2026/порядок.docx', raw),
        ('Архив/порядок.docx', raw),
        ('Приказы/регламент.pdf', pdf()),
        ('Приказы/broken.pdf', b'broken'),
        ('Приказы/notes.txt', b'ignore'),
    ], can_manage=True, confirmed=True)
    assert report['added'] == 2
    assert report['duplicates'] == 1
    assert len(report['errors']) == 1
    assert report['skipped'] == 1
    document = backend.document(hashlib.sha256(raw).hexdigest())
    assert document['source'] == 'Приказы/2026/порядок.docx'
    assert document['units'] == [(1, 'Порядок подачи отчёта'), (2, 'Срок — 12 дней')]
    assert document['raw'] == raw
    assert document['format'] == 'docx'


def test_folder_permissions_and_path_validation(tmp_path):
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    with pytest.raises(PermissionError):
        backend.ingest_folder([], can_manage=False, confirmed=True)
    assert not backend.data_dir.exists()
    for path in ('../secret.pdf', '/etc/a.pdf', 'C:/a.pdf', 'a/../../b.pdf', 'a\\b.pdf'):
        report = backend.ingest_folder([(path, pdf())], can_manage=True, confirmed=True)
        assert report['added'] == 0
        assert len(report['errors']) == 1
    for identifier in ('../x', 'a' * 64, 'no-id'):
        with pytest.raises(BackendError):
            backend.document(identifier)


def test_duplicate_names_have_separate_document_ids(tmp_path):
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    a, b = docx('Первый'), docx('Второй')
    backend.ingest_folder([('a/report.docx', a), ('b/report.docx', b)], can_manage=True, confirmed=True)
    assert backend.document(hashlib.sha256(a).hexdigest())['units'][0][1] == 'Первый'
    assert backend.document(hashlib.sha256(b).hexdigest())['units'][0][1] == 'Второй'


def test_docx_rejects_entities_and_corrupted_archive(tmp_path):
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    for raw in (b'bad zip', b''):
        with pytest.raises(BackendError):
            backend.ingest([('bad.docx', raw)], can_manage=True, confirmed=True)
    raw = io.BytesIO()
    with ZipFile(raw, 'w') as archive:
        archive.writestr('word/document.xml', '<!DOCTYPE x [<!ENTITY xx "hidden">]><x>&xx;</x>')
    with pytest.raises(BackendError):
        backend.ingest([('bad.docx', raw.getvalue())], can_manage=True, confirmed=True)


def test_pdf_document_and_render_target_page(tmp_path):
    from pypdf import PdfReader, PdfWriter
    from yastreb.documents import render_pdf
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_page(PdfReader(io.BytesIO(pdf('Target sentence'))).pages[0])
    out = io.BytesIO()
    writer.write(out)
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    backend.ingest([('two.pdf', out.getvalue())], can_manage=True, confirmed=True)
    document = backend.document(hashlib.sha256(out.getvalue()).hexdigest())
    assert document['units'][1][1] == 'Target sentence'
    image = render_pdf(document['raw'], 2)
    assert image.startswith(b'\x89PNG')
    with pytest.raises(ValueError):
        render_pdf(document['raw'], 0)


def test_highlight_escapes_document_markup():
    from yastreb.documents import highlighted_text
    assert highlighted_text('<script>alert(1)</script>', 0, 8).startswith('<mark>&lt;script&gt;</mark>')
    assert '<script>' not in highlighted_text('<script>alert(1)</script>', -1, 999)


def test_legacy_doc_conversion_is_retained_for_offline_rebuild(tmp_path, monkeypatch):
    from yastreb import documents
    raw = bytes.fromhex('d0cf11e0a1b11ae1') + b'legacy document'
    monkeypatch.setattr(documents, '_convert_doc', lambda data: docx('Converted content'))
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    backend.ingest([('legacy.doc', raw)], can_manage=True, confirmed=True)
    def unavailable(data):
        raise AssertionError('Stored extraction must not require a second conversion')
    monkeypatch.setattr(documents, '_convert_doc', unavailable)
    document = backend.document(hashlib.sha256(raw).hexdigest())
    assert document['raw'] == raw
    assert document['units'][0][1] == 'Converted content'


def test_old_pdf_manifest_without_snapshot_still_opens(tmp_path):
    import json
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    raw = pdf('Old library')
    digest = hashlib.sha256(raw).hexdigest()
    (backend.data_dir / 'documents').mkdir(parents=True)
    (backend.data_dir / 'documents' / (digest + '.pdf')).write_bytes(raw)
    (backend.data_dir / 'manifest.json').write_text(json.dumps({digest: {'source': 'old.pdf'}}))
    assert backend.document(digest)['units'][0][1] == 'Old library'
    assert backend.resolve_source({'source': 'old.pdf', 'page': 1}) == digest


def test_snapshot_corruption_is_detected(tmp_path):
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    raw = docx()
    backend.ingest([('a.docx', raw)], can_manage=True, confirmed=True)
    digest = hashlib.sha256(raw).hexdigest()
    (backend.data_dir / 'documents' / (digest + '.text.json')).write_text('[[1,"tampered"]]')
    with pytest.raises(BackendError, match='сумма'):
        backend.document(digest)
