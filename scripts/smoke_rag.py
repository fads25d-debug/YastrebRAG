"""Opt-in live model check, writes an isolated test library under data/smoke.

Run after installing models: python -m scripts.smoke_rag
This synthetic English PDF tests bilingual retrieval and Russian answers.
It is not added to the users' real library.
"""
import io
import json
import os
import re
import time
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from yastreb.backend import Backend


def sample_pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({
        NameObject('/F1'): writer._add_object(font)})})
    lines = [
        'YASTREB SYNTHETIC TEST - NOT A REAL REGULATION',
        'The report must be submitted within 12 working days after the inspection.',
        'The department head reviews the report within 3 working days.',
        'The report must contain a title page, findings, and a list of sources.',
        'After approval, the secretary registers the report in the local register.',
        'The report is stored in the archive for 5 years.',
    ]
    content = 'BT /F1 11 Tf 35 780 Td 20 TL\n' + '\n'.join(f'({line}) Tj T*' for line in lines) + '\nET'
    stream = DecodedStreamObject()
    stream.set_data(content.encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def main():
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['ANONYMIZED_TELEMETRY'] = 'False'
    os.environ['LANGSMITH_TRACING'] = 'false'
    os.environ['LANGCHAIN_TRACING_V2'] = 'false'
    os.environ.setdefault('YASTREB_NUM_GPU', '0')
    root = Path(__file__).resolve().parents[1]
    backend = Backend(root / 'data' / 'smoke', root / 'models' / 'bge-m3')
    print('Preparing isolated synthetic PDF...', flush=True)
    backend.ingest([('synthetic-test.pdf', sample_pdf())], can_manage=True, confirmed=True)
    print('Index:', backend.rebuild(can_manage=True), flush=True)
    checks = [('quick', 'В какой срок после проверки нужно подать отчёт?'),
              ('detailed', 'Объясни порядок подготовки, согласования и хранения отчёта.'),
              ('quick', 'Какова температура поверхности Марса?')]
    results = []
    for i, (mode, question) in enumerate(checks):
        started = time.monotonic()
        answer = backend.answer(question, mode)
        record = {'mode': mode, 'question': question, 'seconds': round(time.monotonic() - started, 1), **answer}
        print(json.dumps(record, ensure_ascii=False), flush=True)
        results.append(record)
        assert not answer.get('error'), answer
        if i < 2:
            assert answer['sources'], answer
            assert all(s['source'] == 'synthetic-test.pdf' and s['page'] == 1 for s in answer['sources'])
            assert '12' in answer['text'], 'Срок подачи должен быть в самом ответе'
            assert re.search('[А-Яа-я]', answer['text']), 'Ответ должен быть на русском языке'
            if i == 1:
                assert '3' in answer['text'] and '5' in answer['text'], 'Подробный ответ должен объяснять сроки согласования и хранения'
        else:
            assert not answer['sources'] and answer['text'] == backend.REFUSAL, answer
    print('LIVE_SMOKE_PASS', flush=True)


if __name__ == '__main__':
    main()
