#!/usr/bin/env bash
set -euo pipefail

# Local smoke test for the same Core API mode used by Vercel.
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi
export STUDIO_BACKEND="core_api"
: "${MAGICLAYER_CORE_URL:?Set MAGICLAYER_CORE_URL first}"
exec uvicorn web.backend.app:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" "$@"
