#!/usr/bin/env bash
# One command from fresh clone to green tests.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> python 3.12"
uv python install 3.12

echo "==> venv"
uv venv --python 3.12

echo "==> dependencies"
uv pip install --python .venv/bin/python -e ".[dev]"

echo "==> tests"
.venv/bin/python -m pytest

echo
echo "Ready. Next:"
echo "  .venv/bin/python -m uvicorn sikia_lab.transport:app --reload"
echo "  .venv/bin/python scripts/bench.py"
