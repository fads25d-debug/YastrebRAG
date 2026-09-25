"""Read-only local startup checks; never downloads weights."""
import importlib.util
import json
import os
import urllib.request
from pathlib import Path


def main():
    missing = [m for m in ['streamlit', 'chromadb', 'sentence_transformers', 'pypdf', 'pypdfium2', 'filelock', 'langchain_text_splitters']
               if importlib.util.find_spec(m) is None]
    root = Path(__file__).resolve().parents[1]
    model_path = Path(os.environ.get('YASTREB_EMBEDDING_PATH', root / 'models' / 'bge-m3'))
    print('Missing packages:', ', '.join(missing) or 'none')
    print('Embedding directory:', model_path, 'exists:', model_path.is_dir())
    url = os.environ.get('YASTREB_OLLAMA_URL', 'http://127.0.0.1:11434')
    from yastreb.backend import Backend, _NoRedirect
    # Reuse backend URL validation before any request.
    Backend(root / 'data' / 'library', model_path, url)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        with opener.open(url + '/api/tags', timeout=3) as response:
            models = [m['name'] for m in json.load(response)['models']]
        requested = os.environ.get('YASTREB_OLLAMA_MODEL', 'qwen2.5:7b')
        print('Ollama models:', models)
        ready = requested in models
    except Exception as error:
        print('Ollama not ready:', error)
        ready = False
    return 0 if not missing and model_path.is_dir() and ready else 1


if __name__ == '__main__':
    raise SystemExit(main())
