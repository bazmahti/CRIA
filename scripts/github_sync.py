#!/usr/bin/env python3
"""
Sync local workspace files to GitHub via the GitHub API.
Safe against diverged histories — creates a new commit on top of GitHub HEAD.
Non-fatal: exits 0 even on errors so post-merge setup always succeeds.
"""
import os, sys, subprocess, json, base64, hashlib, urllib.request, urllib.error

TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO  = "bazmahti/CRIA"
API   = "https://api.github.com"

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "Content-Type": "application/json",
}

# Only sync files under these directories (avoids binary/cache/env files)
SYNC_DIRS = (
    "artifacts/",
    "lib/",
    "scripts/",
    "docs/",
)

# Skip these patterns entirely
SKIP_SUFFIXES = (
    ".pyc", ".pyo", ".so", ".map", ".log", ".jsonl",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf",
)
SKIP_DIRS = (
    "__pycache__", "node_modules", ".pythonlibs", "dist", ".venv",
    "pending_experiments", "schemas",
)


def api_call(method, path, body=None):
    url  = f"{API}{path}"
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:300]
        print(f"  GitHub API {e.code} {method} {path}: {msg}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  GitHub API error {method} {path}: {e}", file=sys.stderr)
        return None


def git_blob_sha(content_bytes: bytes) -> str:
    header = f"blob {len(content_bytes)}\0".encode()
    return hashlib.sha1(header + content_bytes).hexdigest()


def should_sync(rel_path: str) -> bool:
    if not any(rel_path.startswith(d) for d in SYNC_DIRS):
        return False
    if any(part in SKIP_DIRS for part in rel_path.split("/")):
        return False
    if any(rel_path.endswith(s) for s in SKIP_SUFFIXES):
        return False
    return True


def main():
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True
    ).stdout.strip()

    # Get all tracked files (NUL-delimited to handle spaces)
    tracked_raw = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, cwd=root
    ).stdout
    tracked = [p.decode("utf-8", errors="replace") for p in tracked_raw.split(b"\0") if p]

    # Filter to syncable files
    to_check = [p for p in tracked if should_sync(p)]
    print(f"  Checking {len(to_check)} files against GitHub...")

    # Get GitHub HEAD
    branch = api_call("GET", f"/repos/{REPO}/branches/main")
    if not branch:
        print("  Could not reach GitHub — skipping sync")
        return
    parent_sha = branch["commit"]["sha"]
    base_tree  = branch["commit"]["commit"]["tree"]["sha"]
    print(f"  GitHub HEAD: {parent_sha[:7]}")

    # Detect changed files by comparing blob SHAs
    changed = []
    for rel_path in to_check:
        full_path = os.path.join(root, rel_path)
        if not os.path.isfile(full_path):
            continue
        try:
            content = open(full_path, "rb").read()
        except Exception:
            continue
        local_sha = git_blob_sha(content)

        # URL-encode the path safely
        encoded_path = urllib.parse.quote(rel_path, safe="/")
        gh_file = api_call("GET", f"/repos/{REPO}/contents/{encoded_path}?ref={parent_sha}")
        if gh_file and isinstance(gh_file, dict) and gh_file.get("sha") == local_sha:
            continue  # identical

        # Create blob
        blob = api_call("POST", f"/repos/{REPO}/git/blobs", {
            "content": base64.b64encode(content).decode(),
            "encoding": "base64",
        })
        if blob and blob.get("sha"):
            changed.append({"path": rel_path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
            print(f"  updated: {rel_path}")

    if not changed:
        print("  GitHub already up to date.")
        return

    # Create new tree
    new_tree = api_call("POST", f"/repos/{REPO}/git/trees", {
        "base_tree": base_tree,
        "tree": changed,
    })
    if not new_tree:
        print("  Failed to create tree — skipping sync")
        return

    # Get commit message from local HEAD
    msg = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"], capture_output=True, text=True
    ).stdout.strip()

    new_commit = api_call("POST", f"/repos/{REPO}/git/commits", {
        "message": msg,
        "tree": new_tree["sha"],
        "parents": [parent_sha],
    })
    if not new_commit:
        print("  Failed to create commit — skipping sync")
        return

    result = api_call("PATCH", f"/repos/{REPO}/git/refs/heads/main", {
        "sha": new_commit["sha"],
        "force": False,
    })
    if result:
        print(f"  GitHub sync OK — {new_commit['sha'][:7]} ({len(changed)} file(s) updated)")
    else:
        print("  Failed to update branch ref — sync incomplete")


# urllib.parse needed for quote()
import urllib.parse

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"  GitHub sync error: {e}", file=sys.stderr)
        sys.exit(0)  # always exit 0 — non-fatal
