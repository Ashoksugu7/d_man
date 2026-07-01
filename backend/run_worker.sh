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
mkdir -p storage/results storage/uploads

export PYTORCH_ENABLE_MPS_FALLBACK="${PYTORCH_ENABLE_MPS_FALLBACK:-1}"

POOL="${CELERY_WORKER_POOL:-}"
CONCURRENCY="${CELERY_WORKER_CONCURRENCY:-}"

if [ -z "$POOL" ]; then
  case "$(uname -s)" in
    Darwin)
      POOL="solo"
      export OBJC_DISABLE_INITIALIZE_FORK_SAFETY="${OBJC_DISABLE_INITIALIZE_FORK_SAFETY:-YES}"
      ;;
    *)
      POOL="prefork"
      CONCURRENCY="${CONCURRENCY:-2}"
      ;;
  esac
fi

args=(celery -A app.jobs.celery_app worker --loglevel="${CELERY_LOGLEVEL:-info}" --pool="$POOL")

if [ -n "$CONCURRENCY" ] && [ "$POOL" != "solo" ]; then
  args+=(--concurrency="$CONCURRENCY")
fi

exec "${args[@]}"
