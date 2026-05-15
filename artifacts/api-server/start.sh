#!/bin/bash
# No set -e — we want to see what fails, not abort silently

SCRIPT_DIR="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
echo "[start.sh] WORKSPACE_ROOT=$WORKSPACE_ROOT"

PYTHON="$WORKSPACE_ROOT/.pythonlibs/bin/python3"
if [ ! -x "$PYTHON" ]; then
  echo "[start.sh] .pythonlibs python3 not found, falling back to PATH"
  PYTHON="$(which python3 2>/dev/null || echo python3)"
fi
echo "[start.sh] Using python: $PYTHON ($($PYTHON --version 2>&1))"

# Ensure log dirs exist (including service subdirs)
mkdir -p /tmp/cria-logs/cria-unified /tmp/cria-logs/cria-deepseek /tmp/cria-logs/cria-v4

start_service() {
  local name="$1"; local logfile="/tmp/cria-logs/${name}.log"
  shift
  echo "[start.sh] Starting $name ..."
  env "$@" "$PYTHON" "$WORKSPACE_ROOT/artifacts/${name}.py" \
    > >(tee -a "$logfile") 2>&1 &
  local pid=$!
  echo $pid > "/tmp/cria-logs/${name}.pid"
  echo "[start.sh] $name PID=$pid"
}

start_service "cria-unified/main"        PORT=8003 BASE_PATH=/cria-unified ULTRARIA_URL=http://localhost:8004
start_service "cria-deepseek/main"       PORT=8001
start_service "cria-v4/main"             PORT=8002
start_service "cria-unified/ultraria_stub" PORT=8004 ULTRARIA_PORT=8004

# Python services warm up in the background.
# Node's python-proxy.ts has a 45-second ECONNREFUSED retry loop,
# so Node can start immediately — no need to block here.
echo "[start.sh] Python services starting in background — launching Node api-server now"
exec env NODE_ENV=production node --enable-source-maps "$WORKSPACE_ROOT/artifacts/api-server/dist/index.mjs"
