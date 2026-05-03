#!/bin/bash
# Manual / on-demand sync to GitHub.
# Run: bash scripts/sync-github.sh
# Run with force: bash scripts/sync-github.sh --force
#
# Use --force when the remote has diverged (e.g. after a subrepl task
# was merged that added its own commits to GitHub).

set -e

if [ -z "$GITHUB_TOKEN" ]; then
  echo "ERROR: GITHUB_TOKEN secret is not set. Add it in Replit Secrets."
  exit 1
fi

GITHUB_URL="https://bazmahti:${GITHUB_TOKEN}@github.com/bazmahti/CRIA.git"
BRANCH="main"
FORCE=""

if [ "$1" = "--force" ]; then
  FORCE="--force"
  echo "Force-push mode enabled."
fi

HEAD=$(git rev-parse --short HEAD)
echo "Pushing ${BRANCH} @ ${HEAD} to GitHub..."

if git push $FORCE "$GITHUB_URL" "$BRANCH" 2>&1; then
  echo "Done. GitHub is now at ${HEAD}."
else
  echo ""
  echo "Push failed. If the remote has diverged, re-run with --force:"
  echo "  bash scripts/sync-github.sh --force"
  exit 1
fi
