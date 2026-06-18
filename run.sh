#!/usr/bin/env bash
# Launch the Personal AI Twin Platform.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment…"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
  echo "⚠️  No .env found. Copy .env.example to .env and add your ANTHROPIC_API_KEY."
fi

echo "Starting on http://localhost:8000"
exec uvicorn backend.app.main:app --reload --port 8000
