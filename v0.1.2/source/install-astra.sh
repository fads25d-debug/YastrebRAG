#!/usr/bin/env bash
# Initial ONLINE preparation. Run as the ordinary application user, not root.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo 'This installer requires Linux x86_64.' >&2; exit 1
fi
if [[ "$EUID" == 0 ]]; then
  echo 'Run as a normal user, not with sudo.' >&2; exit 1
fi
for tool in curl tar zstd sha256sum; do
  command -v "$tool" >/dev/null || { echo "Missing $tool. See ASTRA.md." >&2; exit 1; }
done
if [[ -f SHA256SUMS ]]; then sha256sum --check --quiet SHA256SUMS; fi
mkdir -p tools/linux downloads data/logs
chmod 700 data
if [[ ! -x tools/linux/uv ]]; then
  curl --fail --location --retry 3 https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-unknown-linux-gnu.tar.gz -o downloads/uv.tar.gz
  tar -xzf downloads/uv.tar.gz -C tools/linux --strip-components=1 uv-x86_64-unknown-linux-gnu/uv
fi
export UV_PYTHON_INSTALL_DIR="$PWD/tools/linux/python"
tools/linux/uv python install 3.12
if [[ ! -x .venv/bin/python ]]; then
  tools/linux/uv venv --python 3.12 --seed .venv
fi
# CPU wheels avoid downloading CUDA libraries on the baseline workstation.
.venv/bin/python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
if [[ ! -x tools/linux/ollama/bin/ollama ]]; then
  curl --fail --location --retry 3 https://github.com/ollama/ollama/releases/download/v0.34.0/ollama-linux-amd64.tar.zst -o downloads/ollama-linux-amd64.tar.zst
  echo 'cf95886728959aa09910bb34de5cca1cc5a8f68003b5597197d3f2c2d57c0804  downloads/ollama-linux-amd64.tar.zst' | sha256sum --check -
  mkdir -p tools/linux/ollama
  tar --zstd -xf downloads/ollama-linux-amd64.tar.zst -C tools/linux/ollama
fi
.venv/bin/python -m pip freeze > requirements-linux-installed.txt
echo 'Installation complete. Run: bash start-linux.sh'
