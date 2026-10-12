import hashlib
import io
from zipfile import ZipFile

import pytest

from yastreb.backend import Backend, BackendError

P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'


def deck(image=None, external=False, crop=''):
    """Small OOXML fixture: slide order intentionally differs from filenames."""
    raw = io.BytesIO()
    with ZipFile(raw, 'w') as z:
        z.writestr('ppt/presentation.xml', f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="256" r:id="s2"/><p:sldId id="257" r:id="s1"/></p:sldIdLst></p:presentation>')
        z.writestr('ppt/_rels/presentation.xml.rels', f'<Relationships xmlns="{REL}"><Relationship Id="s2" Type="{R}/slide" Target="slides/slide2.xml"/><Relationship Id="s1" Type="{R}/slide" Target="slides/slide1.xml"/></Relationships>')
        text = '<p:sp><p:txBody><a:p><a:r><a:t>Порядок подачи отчёта</a:t></a:r></a:p></p:txBody></p:sp>'
        table = '<p:graphicFrame><a:graphic><a:graphicData><a:tbl>'
        for row in [('Документ', 'Срок'), ('Отчёт', '12 дней')]:
            table += '<a:tr>' + ''.join(f'<a:tc><a:txBody><a:p><a:r><a:t>{v}</a:t></a:r></a:p></a:txBody></a:tc>' for v in row) + '</a:tr>'
        table += '</a:tbl></a:graphicData></a:graphic></p:graphicFrame>'
        picture = ''
        if image or external:
            attribute = 'link' if external else 'embed'
            picture = f'<p:grpSp><p:pic><p:blipFill><a:blip r:{attribute}="img"/>{crop}</p:blipFill></p:pic></p:grpSp>'
            target = 'https://example.invalid/private.png' if external else '../media/image.png'
            mode = ' TargetMode="External"' if external else ''
            z.writestr('ppt/slides/_rels/slide1.xml.rels', f'<Relationships xmlns="{REL}"><Relationship Id="img" Type="{R}/image" Target="{target}"{mode}/></Relationships>')
            if image:
                z.writestr('ppt/media/image.png', image)
        for name, body in [('slide2', text + table), ('slide1', picture)]:
            z.writestr(f'ppt/slides/{name}.xml', f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld><p:spTree>{body}</p:spTree></p:cSld></p:sld>')
    return raw.getvalue()


def test_pptx_table_order_original_and_duplicate(tmp_path):
    b = Backend(tmp_path / 'library', tmp_path / 'model')
    raw = deck()
    progress = []
    result = b.ingest_folder([('Материалы/порядок.pptx', raw)], can_manage=True, confirmed=True,
                             progress=lambda *event: progress.append(event))
    assert result['added'] == 1
    doc = b.document(hashlib.sha256(raw).hexdigest())
    assert doc['raw'] == raw and doc['format'] == 'pptx'
    assert 'Документ | Срок\nОтчёт | 12 дней' in doc['units'][0][1]
    assert doc['units'][1] == (2, '')
    assert progress[-1][1:] == (2, 2)
    assert b.ingest([('duplicate.pptx', raw)], can_manage=True, confirmed=True)['duplicates'] == 1


def test_pptx_embedded_image_ocr_survives_reload(tmp_path, monkeypatch):
    from PIL import Image
    from yastreb import ocr
    output = io.BytesIO()
    with Image.new('RGB', (80, 60), 'black') as image:
        image.save(output, format='PNG')
    monkeypatch.setattr(ocr, 'recognize', lambda image: 'Надпись на рисунке: проверка 25 мая')
    raw = deck(output.getvalue())
    b = Backend(tmp_path / 'library', tmp_path / 'model')
    result = b.ingest_folder([('image.pptx', raw)], can_manage=True, confirmed=True)
    assert result['added'] == 1
    monkeypatch.setattr(ocr, 'recognize', lambda image: pytest.fail('Saved OCR must be reused'))
    doc = b.document(hashlib.sha256(raw).hexdigest())
    assert 'проверка 25 мая' in doc['units'][1][1]


def test_external_image_is_not_fetched_and_has_slide_warning(tmp_path):
    b = Backend(tmp_path / 'library', tmp_path / 'model')
    result = b.ingest_folder([('linked.pptx', deck(external=True))], can_manage=True, confirmed=True)
    assert result['added'] == 1
    assert [w['page'] for w in result['warnings']] == [2]
    assert 'внешн' in result['warnings'][0]['message'].lower()


def test_picture_ocr_only_receives_visible_crop(tmp_path, monkeypatch):
    from PIL import Image
    from yastreb import ocr
    output = io.BytesIO()
    with Image.new('RGBA', (100, 80), (0, 0, 0, 0)) as image:
        image.save(output, format='PNG')
    def recognized(image):
        assert image.size == (50, 80)
        assert image.getpixel((0, 0)) == (255, 255, 255)
        return 'Only visible part'
    monkeypatch.setattr(ocr, 'recognize', recognized)
    b = Backend(tmp_path / 'library', tmp_path / 'model')
    raw = deck(output.getvalue(), crop='<a:srcRect l="50000"/>')
    b.ingest([('crop.pptx', raw)], can_manage=True, confirmed=True)
    assert 'Only visible part' in b.document(hashlib.sha256(raw).hexdigest())['units'][1][1]


def test_unsupported_image_warns_without_losing_native_text(tmp_path):
    b = Backend(tmp_path / 'library', tmp_path / 'model')
    result = b.ingest_folder([('vector.pptx', deck(b'not a raster image'))], can_manage=True, confirmed=True)
    assert result['added'] == 1
    assert result['warnings'][0]['page'] == 2


def test_smartart_and_charts_are_reported_as_unindexed(tmp_path):
    raw = io.BytesIO()
    with ZipFile(io.BytesIO(deck())) as source, ZipFile(raw, 'w') as target:
        for entry in source.infolist():
            content = source.read(entry)
            if entry.filename == 'ppt/slides/slide2.xml':
                graphic = (f'<p:graphicFrame><a:graphic><a:graphicData uri="{A}/diagram">'
                           '</a:graphicData></a:graphic></p:graphicFrame>')
                content = content.replace(b'</p:spTree>', graphic.encode() + b'</p:spTree>')
            target.writestr(entry, content)
    b = Backend(tmp_path / 'library', tmp_path / 'model')
    result = b.ingest([('diagram.pptx', raw.getvalue())], can_manage=True, confirmed=True)
    assert result['added'] == 1
    assert any(w['page'] == 1 and 'SmartArt' in w['message'] for w in result['warnings'])


def test_xml_entities_are_rejected(tmp_path):
    raw = io.BytesIO()
    with ZipFile(raw, 'w') as z:
        z.writestr('ppt/presentation.xml', '<!DOCTYPE x [<!ENTITY x "secret">]><x>&x;</x>')
    b = Backend(tmp_path / 'library', tmp_path / 'model')
    with pytest.raises(BackendError, match='XML'):
        b.ingest([('unsafe.pptx', raw.getvalue())], can_manage=True, confirmed=True)


def test_corrupt_pptx_does_not_abort_folder(tmp_path):
    b = Backend(tmp_path / 'library', tmp_path / 'model')
    result = b.ingest_folder([('bad.pptx', b'broken'), ('good.pptx', deck())], can_manage=True, confirmed=True)
    assert result['added'] == 1
    assert [error['file'] for error in result['errors']] == ['bad.pptx']


def test_presentation_sources_are_labelled_as_slides():
    from yastreb.viewer import location_label
    assert location_label({'format': 'pptx', 'page': 2}) == 'слайд 2'
    assert location_label({'format': 'ppt', 'page': 4}) == 'слайд 4'


def test_presentation_permissions_before_io(tmp_path):
    b = Backend(tmp_path / 'library', tmp_path / 'model')
    with pytest.raises(PermissionError):
        b.ingest([('private.pptx', deck())], can_manage=False, confirmed=True)
    assert not b.data_dir.exists()


def test_legacy_ppt_requires_office_with_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setenv('YASTREB_LIBREOFFICE', str(tmp_path / 'missing.exe'))
    b = Backend(tmp_path / 'library', tmp_path / 'model')
    with pytest.raises(BackendError, match='LibreOffice'):
        b.ingest([('old.ppt', bytes.fromhex('d0cf11e0a1b11ae1') + b'old')], can_manage=True, confirmed=True)


def test_legacy_conversion_persists_original_and_text(tmp_path, monkeypatch):
    from yastreb import office
    from types import SimpleNamespace
    executable = tmp_path / 'soffice.exe'
    executable.touch()
    monkeypatch.setenv('YASTREB_LIBREOFFICE', str(executable))
    def convert(command, **kwargs):
        from pathlib import Path
        out = Path(command[command.index('--outdir') + 1])
        (out / 'input.pptx').write_bytes(deck())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(office.subprocess, 'run', convert)
    b = Backend(tmp_path / 'library', tmp_path / 'model')
    raw = bytes.fromhex('d0cf11e0a1b11ae1') + b'old'
    b.ingest([('old.ppt', raw)], can_manage=True, confirmed=True)
    monkeypatch.setattr(office.subprocess, 'run', lambda *a, **k: pytest.fail('No reconversion on read'))
    doc = b.document(hashlib.sha256(raw).hexdigest())
    assert doc['raw'] == raw and '12 дней' in doc['units'][0][1]


def test_pptx_entities_and_zip_budget(tmp_path, monkeypatch):
    from yastreb import presentations
    b = Backend(tmp_path / 'library', tmp_path / 'model')
    monkeypatch.setattr(presentations, 'MAX_UNPACKED', 10)
    with pytest.raises(BackendError, match='лимит'):
        b.ingest([('big.pptx', deck())], can_manage=True, confirmed=True)


def test_slide_preview_failure_keeps_source_text(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    from yastreb.accounts import Accounts
    monkeypatch.setenv('YASTREB_DEMO', '0')
    monkeypatch.setenv('YASTREB_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('YASTREB_LIBREOFFICE', str(tmp_path / 'missing.exe'))
    accounts = Accounts(tmp_path / 'accounts/users.sqlite')
    accounts.create_user('reader@local.test', 'Читатель', 'worker', 'long-password-123')
    raw = deck()
    backend = Backend(tmp_path / 'library', tmp_path / 'model')
    backend.ingest([('order.pptx', raw)], can_manage=True, confirmed=True)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
    app.query_params['document'] = hashlib.sha256(raw).hexdigest()
    app.query_params['section'] = '1'
    app.text_input[0].set_value('reader@local.test')
    app.text_input[1].set_value('long-password-123')
    app.button[0].click().run()
    assert not app.exception
    assert app.selectbox[0].label == 'Слайд'
    assert any('12 дней' in m.value for m in app.markdown)
    assert any('LibreOffice' in w.value for w in app.warning)
    assert app.get('download_button')


def replace_part(raw, part, transform):
    result = io.BytesIO()
    with ZipFile(io.BytesIO(raw)) as source, ZipFile(result, 'w') as target:
        for entry in source.infolist():
            data = source.read(entry)
            target.writestr(entry, transform(data) if entry.filename == part else data)
    return result.getvalue()


def test_alternate_content_uses_fallback_without_conflicting_choice():
    from yastreb.presentations import presentation_units
    mc = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
    alternative = (f'<mc:AlternateContent xmlns:mc="{mc}" xmlns:p14="urn:unsupported">'
                   '<mc:Choice Requires="p14"><p:sp><a:p><a:r><a:t>Wrong 90 days</a:t>'
                   '</a:r></a:p></p:sp></mc:Choice><mc:Fallback><p:sp><a:p><a:r>'
                   '<a:t>Correct 12 days</a:t></a:r></a:p></p:sp></mc:Fallback></mc:AlternateContent>')
    raw = replace_part(deck(), 'ppt/slides/slide2.xml',
                       lambda data: data.replace(b'</p:spTree>', alternative.encode() + b'</p:spTree>'))
    text = presentation_units(raw, '.pptx')[0][1]
    assert 'Correct 12 days' in text and 'Wrong 90 days' not in text


def test_alternate_content_selects_first_supported_namespace_alias():
    from yastreb.presentations import presentation_units
    mc = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
    alternative = (f'<mc:AlternateContent xmlns:mc="{mc}" xmlns:alias="{P}" xmlns:u="urn:unknown">'
                   '<mc:Choice Requires="alias"><p:sp><a:p><a:r><a:t>First valid</a:t>'
                   '</a:r></a:p></p:sp></mc:Choice><mc:Fallback><mc:AlternateContent>'
                   '<mc:Choice Requires="u"/></mc:AlternateContent></mc:Fallback></mc:AlternateContent>')
    raw = replace_part(deck(), 'ppt/slides/slide2.xml',
                       lambda data: data.replace(b'</p:spTree>', alternative.encode() + b'</p:spTree>'))
    assert 'First valid' in presentation_units(raw, '.pptx')[0][1]


def test_oversized_table_row_requires_split_instead_of_losing_column_context():
    from yastreb.presentations import slide_chunks
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    text = '[Таблица]\nName | Deadline\n' + 'x' * 1100 + ' | 12 days'
    with pytest.raises(ValueError, match='таблиц'):
        list(slide_chunks(text, RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)))


def test_repeated_slide_part_is_rejected():
    from yastreb.presentations import presentation_units
    raw = replace_part(deck(), 'ppt/_rels/presentation.xml.rels',
                       lambda data: data.replace(b'slides/slide1.xml', b'slides/slide2.xml'))
    with pytest.raises(ValueError, match='повтор'):
        presentation_units(raw, '.pptx')


def test_total_presentation_text_is_bounded(monkeypatch):
    from yastreb import presentations
    monkeypatch.setattr(presentations, 'MAX_TEXT', 20, raising=False)
    with pytest.raises(ValueError, match='текст'):
        presentations.presentation_units(deck(), '.pptx')


def test_long_table_index_and_answer_keep_headers_and_exact_quotes(tmp_path, monkeypatch):
    from types import SimpleNamespace
    model = tmp_path / 'model'
    model.mkdir()
    b = Backend(tmp_path / 'library', model)
    header = 'Department | Approval deadline, days | Storage, years'
    text = '[Таблица]\n' + header + '\n' + '\n'.join(
        f'Department {i:02} of the large institution | {i + 10} | {i + 1}' for i in range(40))
    monkeypatch.setattr(b, '_units', lambda *a: [(1, text)])
    b.ingest([('table.pptx', deck())], can_manage=True, confirmed=True)
    rows, embedded = [], []
    def add(**kwargs):
        rows.extend(zip(kwargs['documents'], kwargs['metadatas']))
    def embed(texts):
        embedded.extend(texts)
        return [[1., 0.] for _ in texts]
    collection = SimpleNamespace(add=add, count=lambda: len(rows))
    client = SimpleNamespace(create_collection=lambda *a, **k: collection,
                             get_collection=lambda *a, **k: collection)
    monkeypatch.setattr(b, '_client', lambda *a: client)
    monkeypatch.setattr(b, '_embed', embed)
    b.rebuild(can_manage=True)
    tail, metadata = next((t, m) for t, m in rows if 'Department 39' in t)
    assert metadata.get('table_header') == header
    assert header in next(t for t in embedded if 'Department 39' in t)
    assert text[metadata['start']:metadata['start'] + len(tail)] == tail
    collection.query = lambda **k: {'documents': [[tail]], 'metadatas': [[metadata]], 'distances': [[0.1]]}
    def generate(question, context, mode):
        assert context[0]['table_header'] == header
        return {'text': '49 days; 40 years [1]', 'sources': [{'id': 1}]}
    monkeypatch.setattr(b, '_generate', generate)
    answer = b.answer('Department 39 approval and storage?')
    assert answer['sources'][0]['quote'] == tail
    assert answer['sources'][0]['table_header'] == header
