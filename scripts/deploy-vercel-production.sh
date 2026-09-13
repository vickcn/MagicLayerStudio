#!/usr/bin/env bash
set -euo pipefail

# Manual production fallback. Normal pushes use the linked Vercel Git
# integration; this script is useful for an intentional CLI deployment.
cd "$(dirname "$0")/.."

command -v vercel >/dev/null
vercel deploy --prod --yes
