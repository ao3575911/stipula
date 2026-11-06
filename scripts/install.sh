#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example. Set BOT_TOKEN before running."
fi
echo "Installed. Run scripts/check.sh, then scripts/run.sh."
