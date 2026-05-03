#!/bin/bash
set -e
pnpm install --frozen-lockfile
pnpm --filter db push

# ── Sync to GitHub ──────────────────────────────────────────────────────────
# Runs after every task-agent merge so GitHub stays current.
if [ -n "$GITHUB_TOKEN" ]; then
  GITHUB_URL="https://bazmahti:${GITHUB_TOKEN}@github.com/bazmahti/CRIA.git"
  echo "Pushing to GitHub..."
  if git push "$GITHUB_URL" main 2>&1; then
    echo "GitHub sync OK — $(git rev-parse --short HEAD)"
  else
    # Non-fatal: log and continue. Fast-forward failures mean a force push is
    # needed manually; divergence from a subrepl task is the usual cause.
    echo "WARNING: GitHub push failed (non-fatal). Run scripts/sync-github.sh manually."
  fi
else
  echo "GITHUB_TOKEN not set — skipping GitHub sync"
fi
