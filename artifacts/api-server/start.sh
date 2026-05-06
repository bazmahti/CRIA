#!/bin/bash
set -e

# Derive workspace root from this script's absolute location
SCRIPT_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "[start.sh] WORKSPACE_ROOT=$WORKSPACE_ROOT"

# Prefer the project-local Python (has all packages); fall back to PATH
PYTHON="$WORKSPACE_ROOT/.pythonlibs/bin/python3"
if [ ! -x "$PYTHON" ]; then
  echo "[start.sh] .pythonlibs python3 not found, falling back to PATH"
  PYTHON="python3"
fi

echo "[start.sh] Using python: $PYTHON"
echo "[start.sh] Starting Python research services..."

# Start each service in the background; stdout/stderr flow to the deployment log
PORT=8003 BASE_PATH=/cria-unified ULTRARIA_URL=http://localhost:8004 \
  "$PYTHON" "$WORKSPACE_ROOT/artifacts/cria-unified/main.py" &
PY_UNIFIED=$!

PORT=8001 \
  "$PYTHON" "$WORKSPACE_ROOT/artifacts/cria-deepseek/main.py" &
PY_V2=$!

PORT=8002 \
  "$PYTHON" "$WORKSPACE_ROOT/artifacts/cria-v4/main.py" &
PY_V4=$!

PORT=8004 ULTRARIA_PORT=8004 \
  "$PYTHON" "$WORKSPACE_ROOT/artifacts/cria-unified/ultraria_stub.py" &
PY_ULTRARIA=$!

echo "[start.sh] Python PIDs: unified=$PY_UNIFIED v2=$PY_V2 v4=$PY_V4 ultraria=$PY_ULTRARIA"
echo "[start.sh] Starting api-server (Node)..."

# Hand off to Node; it inherits all env vars and foreground signal handling
exec node --enable-source-maps "$WORKSPACE_ROOT/artifacts/api-server/dist/index.mjs"
