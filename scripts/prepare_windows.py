"""Online model preparation followed by an isolated real indexing/answer check."""
import argparse
import json
import os
import tempfile
from pathlib import Path
from urllib.request import Request, ProxyHandler, build_opener

MODEL_REVISION = '5617a9f61b028005a4858fdac845db406aefb181'


def ensure_embeddings(path, *, offline=False):
    path = Path(path)
    if not path.is_dir() and offline:
        raise RuntimeError('Embedding model is missing. Run install.cmd with Internet access.')
    from sentence_transformers import SentenceTransformer

    def validate():
        encoder = SentenceTransformer(str(path.resolve()), device='cpu',
                                      local_files_only=True, trust_remote_code=False)
        vector = encoder.encode(['Installation check'], normalize_embeddings=True)
        if vector.shape != (1, 1024):
            raise RuntimeError('Unexpected embedding model dimensions')

    try:
        if not path.is_dir():
            raise FileNotFoundError(path)
        validate()
        return
    except Exception as exc:
        if offline:
            raise RuntimeError('Embedding model is incomplete or cannot load; run online setup.') from exc
    from huggingface_hub import snapshot_download
    print('Downloading BAAI/bge-m3 (about 2.3 GB)...', flush=True)
    snapshot_download('BAAI/bge-m3', revision=MODEL_REVISION, local_dir=str(path),
                      allow_patterns=['*.json', '1_Pooling/*', 'pytorch_model.bin',
                                      'sentencepiece.bpe.model'], max_workers=2, force_download=True)
    validate()


def ollama_request(route, payload=None):
    from yastreb.backend import Backend, _NoRedirect
    url = os.environ.get('YASTREB_OLLAMA_URL', 'http://127.0.0.1:11435').rstrip('/')
    Backend(Path('.'), Path('.'), url)  # Validate the loopback target before requesting.
    request = Request(url + route, data=None if payload is None else json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'})
    with build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=7200) as response:
        if payload and payload.get('stream'):
            last_progress = None
            result = {}
            while line := response.readline(1024 * 1024 + 1):
                if len(line) > 1024 * 1024:
                    raise RuntimeError('Unexpectedly large Ollama download response')
                result = json.loads(line)
                if result.get('error'):
                    raise RuntimeError(result['error'])
                percent = int(100 * result.get('completed', 0) / max(result.get('total', 1), 1))
                progress = (result.get('status', ''), percent // 10)
                if progress != last_progress:
                    print(f'Ollama: {progress[0]} {percent}%', flush=True)
                    last_progress = progress
            return result
        return json.load(response)


def ensure_llm(*, offline=False):
    model = os.environ.get('YASTREB_OLLAMA_MODEL', 'qwen2.5:7b')
    tags = ollama_request('/api/tags')
    if model not in [entry['name'] for entry in tags['models']]:
        if offline:
            raise RuntimeError(f'Ollama model {model} is missing. Run online setup.')
        print(f'Downloading {model} (several GB; please wait)...', flush=True)
        result = ollama_request('/api/pull', {'model': model, 'stream': True})
        if result.get('status') != 'success':
            raise RuntimeError(f'Model download failed: {result}')
        if model not in [m['name'] for m in ollama_request('/api/tags')['models']]:
            raise RuntimeError(f'Ollama model {model} is still missing')


def verify_pipeline(root):
    from yastreb.backend import Backend
    from scripts.smoke_rag import sample_pdf
    root = Path(root)
    (root / 'data').mkdir(exist_ok=True)
    # The disposable check is never added to the user's document library.
    # Chroma keeps SQLite handles until process exit on Windows, so preserve the
    # diagnostic directory instead of trying to delete live database files.
    directory = tempfile.mkdtemp(prefix='setup-check-', dir=root / 'data')
    backend = Backend(Path(directory), root / 'models/bge-m3',
                      os.environ.get('YASTREB_OLLAMA_URL', 'http://127.0.0.1:11435'),
                      os.environ.get('YASTREB_OLLAMA_MODEL', 'qwen2.5:7b'))
    backend.ingest([('setup-test.pdf', sample_pdf())], can_manage=True, confirmed=True)
    index = backend.rebuild(can_manage=True)
    if not index['chunks']:
        raise RuntimeError('Test document was not indexed')
    answer = backend.answer('В какой срок после проверки нужно подать отчёт?')
    if answer.get('error') or not answer['sources'] or '12' not in answer['text']:
        raise RuntimeError(f'Test answer failed: {answer.get("error") or answer["text"]}')
    print('VERIFIED: document import, embeddings, index and real answer with source.', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    os.environ['HF_HUB_OFFLINE'] = '1' if args.offline else '0'
    os.environ['TRANSFORMERS_OFFLINE'] = '1' if args.offline else '0'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    # Standard HTTPS works on restrictive corporate networks without the Xet client.
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    os.environ['ANONYMIZED_TELEMETRY'] = 'False'
    os.environ.setdefault('YASTREB_NUM_GPU', '0')
    root = Path(__file__).resolve().parents[1]
    ensure_embeddings(root / 'models/bge-m3', offline=args.offline)
    ensure_llm(offline=args.offline)
    print('Checking indexing and generation (may take several minutes on CPU)...', flush=True)
    verify_pipeline(root)
    from yastreb.backend import Backend
    library = Backend(root / 'data/library', root / 'models/bge-m3')
    active = library._read('active.json', {})
    if library._read('manifest.json', {}) and active.get('embedding_signature') != library._embedding_signature():
        print('Rebuilding the existing library for this model installation...', flush=True)
        library.rebuild(can_manage=True)


if __name__ == '__main__':
    main()

