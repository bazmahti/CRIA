#!/bin/bash
set -e
pnpm install --frozen-lockfile
pnpm --filter db push

# ── Install the tracked post-commit hook ────────────────────────────────────
# Keep .git/hooks/post-commit in sync with scripts/hooks/post-commit so that
# every commit fires the GitHub sync automatically.
HOOK_SRC="$(git rev-parse --show-toplevel)/scripts/hooks/post-commit"
HOOK_DST="$(git rev-parse --show-toplevel)/.git/hooks/post-commit"
if [ -f "$HOOK_SRC" ]; then
  cp "$HOOK_SRC" "$HOOK_DST"
  chmod +x "$HOOK_DST"
  echo "post-commit hook installed from scripts/hooks/post-commit"
fi

# ── Sync to GitHub ──────────────────────────────────────────────────────────
# Runs after every task-agent merge so GitHub stays current.
if [ -z "$GITHUB_TOKEN" ]; then
  echo "GITHUB_TOKEN not set — skipping GitHub sync"
else
  GITHUB_URL="https://bazmahti:${GITHUB_TOKEN}@github.com/bazmahti/CRIA.git"
  COMMIT_SHORT="$(git rev-parse --short HEAD)"
  echo "Pushing to GitHub ($COMMIT_SHORT)..."

  PUSH_OUTPUT="$(git push "$GITHUB_URL" main 2>&1)"
  PUSH_EXIT="$?"

  if [ "$PUSH_EXIT" -eq 0 ]; then
    echo "GitHub sync OK — $COMMIT_SHORT"
  else
    echo "" >&2
    echo "╔══════════════════════════════════════════════════════════════╗" >&2
    echo "║  GITHUB SYNC FAILED (post-merge)                            ║" >&2
    echo "║  This merge was NOT pushed to GitHub. Possible causes:      ║" >&2
    echo "║    • GITHUB_TOKEN expired or revoked                        ║" >&2
    echo "║    • Remote diverged (try: bash scripts/sync-github.sh      ║" >&2
    echo "║      --force)                                               ║" >&2
    echo "║    • GitHub is temporarily unreachable                      ║" >&2
    echo "╚══════════════════════════════════════════════════════════════╝" >&2
    echo "" >&2
    echo "[github-sync] commit    : $(git rev-parse HEAD)" >&2
    echo "[github-sync] exit code : $PUSH_EXIT" >&2
    echo "[github-sync] details   :" >&2
    echo "$PUSH_OUTPUT" | sed 's/^/[github-sync]   /' >&2
    echo "" >&2
    # Non-fatal: do not let a sync failure block the post-merge setup.
  fi
fi
