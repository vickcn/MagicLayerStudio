#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi
export STUDIO_BACKEND="${STUDIO_BACKEND:-local}"
exec conda run -n lama uvicorn web.backend.app:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" "$@"
