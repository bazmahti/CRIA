#!/bin/bash
# Manual / on-demand sync to GitHub.
# Run: bash scripts/sync-github.sh
# Run with force: bash scripts/sync-github.sh --force
#
# Use --force when the remote has diverged (e.g. after a subrepl task
# was merged that added its own commits to GitHub).

set -e

if [ -z "$GITHUB_TOKEN" ]; then
  echo "" >&2
  echo "╔══════════════════════════════════════════════════════════════╗" >&2
  echo "║  GITHUB SYNC FAILED                                         ║" >&2
  echo "║  GITHUB_TOKEN secret is not set.                            ║" >&2
  echo "║  Add it in Replit Secrets and re-run this script.           ║" >&2
  echo "╚══════════════════════════════════════════════════════════════╝" >&2
  exit 1
fi

GITHUB_URL="https://bazmahti:${GITHUB_TOKEN}@github.com/bazmahti/CRIA.git"
BRANCH="main"
FORCE=""

if [ "$1" = "--force" ]; then
  FORCE="--force"
  echo "Force-push mode enabled."
fi

HEAD_SHORT="$(git rev-parse --short HEAD)"
HEAD_FULL="$(git rev-parse HEAD)"
echo "Pushing ${BRANCH} @ ${HEAD_SHORT} to GitHub..."

PUSH_OUTPUT="$(git push $FORCE "$GITHUB_URL" "$BRANCH" 2>&1)"
PUSH_EXIT="$?"

if [ "$PUSH_EXIT" -eq 0 ]; then
  echo "Done. GitHub is now at ${HEAD_SHORT}."
else
  echo "" >&2
  echo "╔══════════════════════════════════════════════════════════════╗" >&2
  echo "║  GITHUB SYNC FAILED                                         ║" >&2
  echo "║  The push to GitHub did not succeed. Possible causes:       ║" >&2
  echo "║    • GITHUB_TOKEN expired or revoked                        ║" >&2
  echo "║    • Remote diverged (retry with: --force)                  ║" >&2
  echo "║    • GitHub is temporarily unreachable                      ║" >&2
  echo "╚══════════════════════════════════════════════════════════════╝" >&2
  echo "" >&2
  echo "[github-sync] commit    : $HEAD_FULL" >&2
  echo "[github-sync] branch    : $BRANCH" >&2
  echo "[github-sync] exit code : $PUSH_EXIT" >&2
  echo "[github-sync] details   :" >&2
  echo "$PUSH_OUTPUT" | sed 's/^/[github-sync]   /' >&2
  echo "" >&2
  exit 1
fi
