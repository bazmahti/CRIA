#!/bin/bash
set -e
pnpm install --frozen-lockfile
pnpm --filter db push --force

# ── Install the tracked post-commit hook ────────────────────────────────────
HOOK_SRC="$(git rev-parse --show-toplevel)/scripts/hooks/post-commit"
HOOK_DST="$(git rev-parse --show-toplevel)/.git/hooks/post-commit"
if [ -f "$HOOK_SRC" ]; then
  cp "$HOOK_SRC" "$HOOK_DST"
  chmod +x "$HOOK_DST"
  echo "post-commit hook installed from scripts/hooks/post-commit"
fi

# ── Sync to GitHub ──────────────────────────────────────────────────────────
# Uses the GitHub API to push changed files so diverged histories never block.
# This is non-fatal — a sync failure must not cause post-merge to exit non-zero.
if [ -z "$GITHUB_TOKEN" ]; then
  echo "GITHUB_TOKEN not set — skipping GitHub sync"
elif ! command -v python3 &>/dev/null; then
  echo "python3 not found — skipping GitHub sync"
else
  COMMIT_SHORT="$(git rev-parse --short HEAD)"
  echo "Syncing to GitHub via API ($COMMIT_SHORT)..."

  set +e
  python3 /home/runner/workspace/scripts/github_sync.py
  SYNC_EXIT="$?"
  set -e

  if [ "$SYNC_EXIT" -ne 0 ]; then
    echo "GitHub sync encountered an error (non-fatal — merge succeeded)"
  fi
fi
