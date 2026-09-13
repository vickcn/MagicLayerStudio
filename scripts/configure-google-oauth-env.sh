#!/usr/bin/env bash
set -euo pipefail

# Securely synchronize Google OAuth configuration without writing credentials
# to a file, command history, or command output.
cd "$(dirname "$0")/.."

GH_REPO="vickcn/MagicLayerStudio"
TASK_PRODUCTION_REDIRECT_URI="https://magic-layer-studio.vercel.app/auth/google/callback"

command -v gh >/dev/null
command -v vercel >/dev/null

if gh variable list -R "$GH_REPO" --json name --jq '.[].name' | grep -Fxq "GOOGLE_CLIENT_ID"; then
  echo "GOOGLE_CLIENT_ID already exists as a GitHub variable; refusing to overwrite."
  exit 2
fi
if gh secret list -R "$GH_REPO" --json name --jq '.[].name' | grep -Fxq "GOOGLE_CLIENT_SECRET"; then
  echo "GOOGLE_CLIENT_SECRET already exists as a GitHub secret; refusing to overwrite."
  exit 2
fi
if vercel env ls production --format=json 2>/dev/null | grep -q 'GOOGLE_CLIENT_ID'; then
  echo "GOOGLE_CLIENT_ID already exists on Vercel Production; refusing to overwrite."
  exit 2
fi
if vercel env ls production --format=json 2>/dev/null | grep -q 'GOOGLE_CLIENT_SECRET'; then
  echo "GOOGLE_CLIENT_SECRET already exists on Vercel Production; refusing to overwrite."
  exit 2
fi

IFS= read -r -p "Google OAuth Client ID: " TASK_GOOGLE_CLIENT_ID
IFS= read -r -s -p "Google OAuth Client Secret: " TASK_GOOGLE_CLIENT_SECRET
printf '\n'

if [[ -z "$TASK_GOOGLE_CLIENT_ID" || -z "$TASK_GOOGLE_CLIENT_SECRET" ]]; then
  echo "Both OAuth values are required. No platform values were changed."
  unset TASK_GOOGLE_CLIENT_ID TASK_GOOGLE_CLIENT_SECRET TASK_PRODUCTION_REDIRECT_URI
  exit 1
fi

# Client ID is not a secret, but remains server-side because this application
# performs the authorization-code exchange in its backend.
gh variable set GOOGLE_CLIENT_ID -R "$GH_REPO" --body "$TASK_GOOGLE_CLIENT_ID"
gh secret set GOOGLE_CLIENT_SECRET -R "$GH_REPO" --body "$TASK_GOOGLE_CLIENT_SECRET"

printf '%s' "$TASK_GOOGLE_CLIENT_ID" | vercel env add GOOGLE_CLIENT_ID production --no-sensitive --yes
printf '%s' "$TASK_GOOGLE_CLIENT_SECRET" | vercel env add GOOGLE_CLIENT_SECRET production --sensitive --yes

unset TASK_GOOGLE_CLIENT_ID TASK_GOOGLE_CLIENT_SECRET TASK_PRODUCTION_REDIRECT_URI
echo "Google OAuth Client ID/Secret synchronized without displaying their values."
