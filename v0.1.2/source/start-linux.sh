#!/usr/bin/env bash
# Offline execution. No model or dependency downloads.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ -x .venv/bin/python ]] || { echo 'Run bash install-astra.sh first.' >&2; exit 1; }
export OLLAMA_MODELS="$PWD/models/ollama"
export OLLAMA_HOST=127.0.0.1:11434
export OLLAMA_NO_CLOUD=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export YASTREB_NUM_GPU="${YASTREB_NUM_GPU:-0}"
export YASTREB_DEMO=0
export YASTREB_OLLAMA_URL=http://127.0.0.1:11434
mkdir -p data/logs
chmod 700 data
ollama_pid=''
cleanup() {
  if [[ -n "$ollama_pid" ]]; then kill "$ollama_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT
if ! curl --noproxy '*' --fail --silent http://127.0.0.1:11434/api/version >/dev/null; then
  [[ -x tools/linux/ollama/bin/ollama ]] || { echo 'Missing Linux Ollama; run install-astra.sh.' >&2; exit 1; }
  tools/linux/ollama/bin/ollama serve >data/logs/ollama.out.log 2>data/logs/ollama.err.log &
  ollama_pid=$!
  for attempt in {1..30}; do
    if curl --noproxy '*' --fail --silent http://127.0.0.1:11434/api/version >/dev/null; then break; fi
    sleep 1
  done
fi
.venv/bin/python -m scripts.check_environment
echo 'Yastreb: http://127.0.0.1:8502 -- keep this terminal open.'
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502 --server.headless false --server.showEmailPrompt false
