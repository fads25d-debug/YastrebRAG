"""Offline PDF OCR with raster and decoded-stream budgets."""
import io
import math
import os
from pathlib import Path
import shutil
import subprocess

from yastreb.documents import PDFIUM_LOCK

ROOT = Path(__file__).resolve().parents[1]
MAX_PAGES = 2000
MAX_PIXELS = 12_000_000
MAX_STREAM_BYTES = 8 * 1024 * 1024
MAX_DECODED_BYTES = 64 * 1024 * 1024


class _PdfBudget:
    """Preflight text/resources before pypdf retains their decoded streams."""

    def __init__(self):
        self.seen = {}
        self.decoded_ids = set()
        self.decoded = 0

    def inspect(self, obj, depth=0, role='data'):
        from pypdf.generic import ArrayObject, DictionaryObject, StreamObject
        obj = obj.get_object() if hasattr(obj, 'get_object') else obj
        if not isinstance(obj, (ArrayObject, DictionaryObject)):
            return False
        # The same stream may also be referenced as Contents or a font resource.
        # Only a real XObject image reference is exempt from text decoding.
        key = (id(obj), role)
        if key in self.seen:
            return self.seen[key]
        if depth > 50 or len(self.seen) >= 100_000:
            raise ValueError('Превышен лимит сложности PDF. Разделите документ.')
        self.seen[key] = False
        if isinstance(obj, StreamObject):
            if role == 'xobject' and obj.get('/Subtype') == '/Image':
                # Do not decompress image payloads in Python; PDFium renders them.
                self.seen[key] = True
                return True
            size = len(obj.get_data())
            if size > MAX_STREAM_BYTES:
                raise ValueError('Превышен лимит распаковки потока PDF. Разделите документ.')
            if id(obj) not in self.decoded_ids:
                self.decoded += size
                self.decoded_ids.add(id(obj))
            if self.decoded > MAX_DECODED_BYTES:
                raise ValueError('Превышен лимит распакованного содержимого PDF. Разделите документ.')
        children = enumerate(obj) if isinstance(obj, ArrayObject) else obj.items()
        has_image = False
        for name, child in children:
            child_role = 'xobject' if role == 'xobjects' else 'xobjects' if name == '/XObject' else 'data'
            has_image = self.inspect(child, depth + 1, child_role) or has_image
        self.seen[key] = has_image
        return has_image


def check_available():
    configured = os.environ.get('YASTREB_TESSERACT')
    local = ROOT / 'tools/tesseract/tesseract.exe'
    executable = configured or (str(local) if local.is_file() else shutil.which('tesseract'))
    if not executable or not Path(executable).is_file():
        raise ValueError('OCR не установлен. В Windows повторите install.cmd; в Linux установите tesseract-ocr, tesseract-ocr-rus и tesseract-ocr-eng.')
    data = os.environ.get('YASTREB_TESSDATA')
    if not data and (Path(executable).parent / 'tessdata').is_dir():
        data = str(Path(executable).parent / 'tessdata')
    executable = str(Path(executable).resolve())
    data = str(Path(data).resolve()) if data else None
    command = [executable, '--list-langs']
    if data:
        # Tesseract's Windows CLI cannot reliably decode Cyrillic argv paths.
        # Set the working directory through the Unicode OS API; pass only '.'.
        command += ['--tessdata-dir', '.']
    try:
        result = subprocess.run(command, capture_output=True, timeout=15, cwd=data,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('OCR не запускается. Повторите install.cmd или проверьте установку Tesseract.') from exc
    languages = result.stdout.decode('utf-8', errors='replace').splitlines()
    if result.returncode or not {'rus', 'eng'}.issubset({line.strip() for line in languages}):
        raise ValueError('Для OCR отсутствуют языки rus/eng. Повторите install.cmd или установите языковые пакеты Tesseract.')
    return executable, data


def recognize(image):
    executable, data = check_available()
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    command = [executable, 'stdin', 'stdout', '-l', 'rus+eng', '--psm', '3', '--dpi', '300']
    if data:
        command += ['--tessdata-dir', '.']
    env = dict(os.environ, OMP_THREAD_LIMIT='2')
    try:
        result = subprocess.run(command, input=stream.getvalue(), capture_output=True,
                                timeout=120, env=env, cwd=data,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('OCR: превышено время обработки страницы (120 секунд).') from exc
    except OSError as exc:
        raise ValueError('OCR: не удалось запустить Tesseract. Повторите install.cmd.') from exc
    if result.returncode:
        raise ValueError(f'OCR: Tesseract завершился с кодом {result.returncode}; проверьте установку и доступную память.')
    return result.stdout.decode('utf-8', errors='replace').strip()


def _page_image(raw, index):
    import pypdfium2 as pdfium
    with PDFIUM_LOCK, pdfium.PdfDocument(raw) as document:
        page = document[index]
        try:
            width, height = page.get_size()
            if not math.isfinite(width * height) or width <= 0 or height <= 0:
                raise ValueError('Некорректный размер страницы PDF.')
            scale = min(300 / 72, math.sqrt(MAX_PIXELS / (width * height)), 6000 / max(width, height))
            bitmap = page.render(scale=scale)
            try:
                return bitmap.to_pil().convert('RGB')
            finally:
                bitmap.close()
        finally:
            page.close()


def pdf_units(raw, progress=None, warnings=None):
    from pypdf import apply_configuration
    from pypdf.errors import LimitReachedError
    # Context-local settings: concurrent imports do not change each other's limits.
    try:
        with apply_configuration(zlib_maximum_output_length=MAX_STREAM_BYTES,
                                 lzw_maximum_output_length=MAX_STREAM_BYTES,
                                 run_length_maximum_output_length=MAX_STREAM_BYTES,
                                 array_based_stream_maximum_output_length=MAX_STREAM_BYTES):
            return _pdf_units(raw, progress, warnings if warnings is not None else [])
    except LimitReachedError as exc:
        raise ValueError('Превышен лимит распаковки PDF. Разделите документ.') from exc


def _pdf_units(raw, progress, warnings):
    from pypdf import PdfReader
    from pypdf.errors import LimitReachedError
    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
        encrypted = reader.is_encrypted
        count = len(reader.pages) if not encrypted else 0
    except LimitReachedError:
        raise
    except Exception as exc:
        raise ValueError('PDF повреждён или имеет неподдерживаемую структуру.') from exc
    if encrypted:
        raise ValueError('PDF защищён паролем. Сохраните незашифрованную копию и загрузите её.')
    if count > MAX_PAGES:
        raise ValueError(f'В PDF больше {MAX_PAGES} страниц. Разделите его на несколько файлов.')
    units = []
    budget = _PdfBudget()
    for index, page in enumerate(reader.pages):
        try:
            has_image = budget.inspect(page.get('/Resources', {}))
            budget.inspect(page.get('/Contents'))
            text = page.extract_text() or ''
        except (LimitReachedError, ValueError):
            raise
        except Exception as exc:
            raise ValueError(f'Не удалось прочитать текст страницы {index + 1} PDF.') from exc
        stage = 'Чтение PDF'
        if not text.strip() or (has_image and sum(c.isalnum() for c in text) < 50):
            stage = 'Распознавание скана (OCR)'
            if progress:
                progress(stage, index, count)
            try:
                with _page_image(raw, index) as image:
                    with image.convert('L') as gray:
                        low, high = gray.getextrema()
                    if high - low > 8:
                        recognized = recognize(image)
                        if recognized.strip():
                            text = recognized
                        else:
                            warnings.append({'page': index + 1, 'message':
                                'OCR не распознал текст на непустой странице. Это может быть иллюстрация или плохой скан; проверьте оригинал.'})
            except ValueError as exc:
                raise ValueError(f'Страница {index + 1}: {exc}') from exc
            except Exception as exc:
                raise ValueError(f'OCR: не удалось подготовить страницу {index + 1}.') from exc
        units.append((index + 1, text))
        if progress:
            progress(stage, index + 1, count)
    if not any(text.strip() for _, text in units):
        raise ValueError('В PDF не удалось распознать текст. Проверьте качество и ориентацию скана.')
    return units
