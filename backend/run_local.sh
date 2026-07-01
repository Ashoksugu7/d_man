#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$BACKEND_DIR/.." && pwd)"

if [ -d "$ROOT_DIR/.venv312" ]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.venv312/bin/activate"
elif [ -d "$ROOT_DIR/.venv" ]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.venv/bin/activate"
elif [ -d "$BACKEND_DIR/.venv" ]; then
  # shellcheck disable=SC1091
  source "$BACKEND_DIR/.venv/bin/activate"
fi

cd "$BACKEND_DIR"
mkdir -p storage/results

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RELOAD="${RELOAD:-1}"

if [ "$RELOAD" = "1" ]; then
  exec uvicorn app.main:app --reload --host "$HOST" --port "$PORT"
fi

exec uvicorn app.main:app --host "$HOST" --port "$PORT"
