"""Local diagnostic for a real question; never modifies library or chat history."""
import argparse
import json
import os
import time
from pathlib import Path

from yastreb.backend import Backend


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('question')
    args = parser.parse_args()
    os.environ.setdefault('YASTREB_NUM_GPU', '0')
    root = Path(__file__).resolve().parents[1]
    backend = Backend(root / 'data/library', root / 'models/bge-m3')
    report = {'question': args.question}
    destination = root / 'data/diagnostics/last-answer.json'
    destination.parent.mkdir(parents=True, exist_ok=True)

    def save():
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    generate = backend._generate

    def capture(question, context, mode):
        report['context'] = context
        save()
        print('RETRIEVED', [(item['id'], item['page']) for item in context], flush=True)
        output = generate(question, context, mode)
        report['model_output'] = output
        save()
        return output

    backend._generate = capture
    started = time.monotonic()
    report['result'] = backend.answer(args.question)
    report['seconds'] = round(time.monotonic() - started, 1)
    save()
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
