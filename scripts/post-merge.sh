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
# Runs after every task-agent merge so GitHub stays current.
# NOTE: GitHub sync is explicitly non-fatal — a push failure must not cause
# post-merge setup to exit non-zero, which would block the merge.
if [ -z "$GITHUB_TOKEN" ]; then
  echo "GITHUB_TOKEN not set — skipping GitHub sync"
else
  GITHUB_URL="https://bazmahti:${GITHUB_TOKEN}@github.com/bazmahti/CRIA.git"
  COMMIT_SHORT="$(git rev-parse --short HEAD)"
  echo "Pushing to GitHub ($COMMIT_SHORT)..."

  # Use set +e around the push so a failure doesn't trigger set -e exit.
  set +e
  PUSH_OUTPUT="$(git push "$GITHUB_URL" HEAD:main 2>&1)"
  PUSH_EXIT="$?"
  set -e

  if [ "$PUSH_EXIT" -eq 0 ]; then
    echo "GitHub sync OK — $COMMIT_SHORT"
  else
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  GITHUB SYNC FAILED (post-merge)                            ║"
    echo "║  This merge was NOT pushed to GitHub. Possible causes:      ║"
    echo "║    • GITHUB_TOKEN expired or revoked                        ║"
    echo "║    • Remote diverged — run: bash scripts/sync-github.sh     ║"
    echo "║    • GitHub is temporarily unreachable                      ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo "[github-sync] commit    : $(git rev-parse HEAD)"
    echo "[github-sync] exit code : $PUSH_EXIT"
    echo "[github-sync] details   : $PUSH_OUTPUT"
    # Deliberately NOT exiting non-zero — sync failure is informational only.
  fi
fi
