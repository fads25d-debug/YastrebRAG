"""Offline PowerPoint text, table and embedded-picture OCR extraction."""
import io
import math
import posixpath
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
MC = '{http://schemas.openxmlformats.org/markup-compatibility/2006}'
MAX_SLIDES = 2000
MAX_UNPACKED = 100 * 1024 * 1024
MAX_TEXT = 4_000_000


def _xml(archive, name):
    info = archive.getinfo(name)
    if info.file_size > 16 * 1024 * 1024:
        raise ValueError('XML презентации превышает лимит 16 МиБ.')
    raw = archive.read(info)
    probe = raw.replace(b'\x00', b'').upper()
    if b'<!DOCTYPE' in probe or b'<!ENTITY' in probe:
        raise ValueError('XML-сущности в презентациях не поддерживаются.')
    # Resolve Requires in the namespace scope of each Choice, including aliases.
    scopes, pending, supported = [], {}, {}
    parser = ET.iterparse(io.BytesIO(raw), events=('start-ns', 'start', 'end'))
    for event, node in parser:
        if event == 'start-ns':
            pending[node[0]] = node[1]
        elif event == 'start':
            scope = {**(scopes[-1] if scopes else {}), **pending}
            scopes.append(scope)
            pending = {}
            if node.tag == MC + 'Choice':
                required = node.get('Requires', '').split()
                supported[id(node)] = bool(required) and all(
                    scope.get(prefix) in (P[1:-1], A[1:-1], R[1:-1]) for prefix in required)
        else:
            if node.tag == MC + 'AlternateContent':
                choice = next((child for child in node if child.tag == MC + 'Choice'
                               and supported.get(id(child))), None)
                if choice is None:
                    choice = node.find(MC + 'Fallback')
                if choice is None:
                    # An unsupported object in an unselected outer branch is irrelevant.
                    node.clear()
                    node.set('_unsupported', '1')
                    scopes.pop()
                    continue
                children = list(choice)
                node.clear()
                node.extend(children)
            scopes.pop()
    if any(node.get('_unsupported') for node in parser.root.iter(MC + 'AlternateContent')):
        raise ValueError('Альтернативный объект не имеет поддерживаемого варианта. Сохраните его как изображение.')
    return parser.root


def slide_chunks(text, splitter):
    """Keep table context separate from literal quotes and their coordinates."""
    for block in re.finditer(r'[^\n](?:.*?)(?=\n\n|\Z)', text, re.S):
        value = block.group()
        table_header = value.split('\n', 2)[1] if value.startswith('[Таблица]\n') else ''
        if len(table_header) > 1000:
            raise ValueError('Заголовок таблицы превышает 1000 символов. Разделите таблицу.')
        if table_header and any(len(row) > 1000 for row in value.splitlines()[1:]):
            raise ValueError('Строка таблицы превышает 1000 символов. Разделите таблицу.')
        search_from = 0
        for chunk in splitter.split_text(value):
            offset = value.find(chunk, search_from)
            if offset < 0:  # Overlap may start before the preceding fragment ended.
                offset = value.find(chunk)
            search_from = max(offset + 1, 0)
            metadata = {'start': block.start() + offset}
            if table_header:
                metadata['table_header'] = table_header
            yield chunk, metadata


def _relationships(archive, part):
    folder, name = posixpath.split(part)
    relpath = posixpath.join(folder, '_rels', name + '.rels')
    if relpath not in archive.namelist():
        return {}
    result = {}
    for rel in _xml(archive, relpath):
        target = rel.get('Target', '')
        if rel.get('TargetMode') == 'External':
            result[rel.get('Id')] = None
            continue
        resolved = posixpath.normpath(posixpath.join(folder, target))
        if (not target or ':' in target or '\\' in target or target.startswith('/')
                or not resolved.startswith('ppt/')):
            raise ValueError('Недопустимая ссылка внутри презентации.')
        result[rel.get('Id')] = resolved
    return result


def _text(element):
    paragraphs = []
    for paragraph in element.iter(A + 'p'):
        parts = []
        for node in paragraph.iter():
            if node.tag == A + 't':
                parts.append(node.text or '')
            elif node.tag == A + 'br':
                parts.append('\n')
        paragraphs.append(''.join(parts))
    return '\n'.join(paragraphs).strip()


def _picture(raw, crop):
    from PIL import Image
    from yastreb.ocr import MAX_PIXELS, recognize
    with Image.open(io.BytesIO(raw)) as source:
        if source.width * source.height > 40_000_000:
            raise ValueError('Изображение превышает 40 млн пикселей.')
        left, top, right, bottom = crop
        if (min(crop) < 0 or max(crop) > 100000 or left + right >= 100000 or top + bottom >= 100000):
            raise ValueError('Некорректная обрезка рисунка.')
        box = (round(source.width * left / 100000), round(source.height * top / 100000),
               round(source.width * (1 - right / 100000)), round(source.height * (1 - bottom / 100000)))
        with source.crop(box).convert('RGBA') as visible, Image.new('RGB', visible.size, 'white') as image:
            image.paste(visible, mask=visible.getchannel('A'))
            scale = min(1, math.sqrt(MAX_PIXELS / (image.width * image.height)))
            if scale < 1:
                image.thumbnail((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
            return recognize(image)


def presentation_units(raw, suffix, progress=None, warnings=None):
    warnings = warnings if warnings is not None else []
    if suffix == '.ppt':
        from yastreb.office import convert_presentation
        raw = convert_presentation(raw, '.ppt', 'pptx')
    try:
        with ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if (len(entries) > 10000 or len({e.filename for e in entries}) != len(entries)
                    or sum(e.file_size for e in entries) > MAX_UNPACKED):
                raise ValueError('Превышен лимит распакованной презентации или есть повторяющиеся части.')
            main = _xml(archive, 'ppt/presentation.xml')
            refs = _relationships(archive, 'ppt/presentation.xml')
            ids = main.findall('./' + P + 'sldIdLst/' + P + 'sldId')
            if not 1 <= len(ids) <= MAX_SLIDES:
                raise ValueError(f'В презентации должно быть от 1 до {MAX_SLIDES} слайдов.')
            units = []
            image_cache = {}
            seen_slides = set()
            total_text = 0
            for number, slide_id in enumerate(ids, 1):
                if progress:
                    progress('Чтение презентации / OCR рисунков', number - 1, len(ids))
                path = refs.get(slide_id.get(R + 'id'))
                if not path:
                    raise ValueError(f'Не найден слайд {number}.')
                if path in seen_slides:
                    raise ValueError('Недопустимая повторная ссылка на один слайд.')
                seen_slides.add(path)
                slide = _xml(archive, path)
                media = _relationships(archive, path)
                blocks = []
                def append_block(text):
                    nonlocal total_text
                    total_text += len(text) + 2
                    if total_text > MAX_TEXT:
                        raise ValueError('Превышен лимит извлечённого текста презентации (4 млн символов).')
                    blocks.append(text)
                for shape in slide.iter():
                    if shape.tag == P + 'sp':
                        text = _text(shape)
                        if text:
                            append_block(text)
                    elif shape.tag == A + 'graphicData' and shape.find(A + 'tbl') is None:
                        warnings.append({'page': number, 'message': 'Встроенная диаграмма, SmartArt или другой графический объект не индексируется. Для OCR сохраните его как PNG/JPEG и вставьте в презентацию.'})
                    elif shape.tag == A + 'tbl':
                        rows = []
                        for row in shape.findall(A + 'tr'):
                            cells = [_text(cell).replace('\n', ' / ').replace('|', '¦')
                                     for cell in row.findall(A + 'tc')]
                            rows.append(' | '.join(cells))
                        if any(len(row) > 1000 for row in rows):
                            raise ValueError('Строка таблицы превышает 1000 символов. Разделите таблицу.')
                        append_block('[Таблица]\n' + '\n'.join(rows))
                    elif shape.tag == P + 'blipFill' or shape.tag == A + 'blipFill':
                        blip = shape.find(A + 'blip')
                        if blip is None:
                            continue
                        identifier = blip.get(R + 'embed') or blip.get(R + 'link')
                        rect = shape.find(A + 'srcRect')
                        crop = tuple(int(rect.get(side, '0')) if rect is not None else 0 for side in ('l', 't', 'r', 'b'))
                        target = media.get(identifier)
                        if not target:
                            warnings.append({'page': number, 'message': 'Внешний или отсутствующий рисунок не загружен. Вставьте изображение в сам файл презентации.'})
                            continue
                        cache_key = (target, crop)
                        if cache_key not in image_cache:
                            try:
                                image_cache[cache_key] = _picture(archive.read(target), crop)
                            except (OSError, KeyError):
                                # Unsupported vector media must not masquerade as indexed text.
                                warnings.append({'page': number, 'message': 'Рисунок не прочитан: повреждён или имеет неподдерживаемый формат. Сохраните его как PNG/JPEG.'})
                                continue
                        text = image_cache[cache_key]
                        if text.strip():
                            append_block('[Текст рисунка, OCR]\n' + text)
                        else:
                            warnings.append({'page': number, 'message': 'На рисунке не распознан текст. Содержание изображения не анализируется; проверьте оригинал.'})
                units.append((number, '\n\n'.join(blocks)))
                if progress:
                    progress('Чтение презентации / OCR рисунков', number, len(ids))
            if not any(text.strip() for _, text in units):
                raise ValueError('В презентации не найден текст, в том числе после OCR рисунков.')
            return units
    except Exception as exc:
        raise ValueError('Не удалось прочитать презентацию: ' + str(exc)) from exc
