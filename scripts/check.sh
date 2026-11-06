#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo "No virtualenv. Run scripts/install.sh first." >&2
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate
ruff check src tests
ruff format --check src tests
pytest -q
DATABASE_PATH="${DATABASE_PATH:-./data/stipula.sqlite3}" \
  LOG_PATH="${LOG_PATH:-}" \
  python -m telegram_innovation check --offline
