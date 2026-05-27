#!/usr/bin/env bash
# End-to-end test runner: venv setup, install deps, pytest, OCR-cache validation.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VENV="${VENV_PATH:-$ROOT/.venv}"

echo "==> Invoice AI test runner"
echo "    Project: $ROOT"

if [[ ! -d "$VENV" ]]; then
  echo "==> Creating venv at $VENV"
  python3 -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install -q --upgrade pip

echo "==> Installing requirements (this may take several minutes)..."
pip install -q -r requirements.txt

echo "==> Pytest (unit + golden + phase tests)"
python -m pytest tests/ -v -m "not integration" --tb=short

echo "==> OCR-cache extraction report (no PDF OCR)"
python scripts/eval_ocr_cache.py | head -50

echo "==> E2E validation script"
python scripts/e2e_validate.py

echo ""
echo "==> All automated checks finished OK"
echo "    Optional: start server and upload:"
echo "      uvicorn app.main:app --reload"
echo "      curl -X POST http://localhost:8000/api/v1/upload -F file=@training_data/raw/YOUR.pdf"
