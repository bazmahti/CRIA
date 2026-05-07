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

# Quick sanity: can we import fastapi/uvicorn/slowapi?
# (pip install ran during the build phase — this is just a fast smoke test)
"$PYTHON" -c "import fastapi, uvicorn, asyncpg, slowapi; print('[start.sh] Python imports OK')" 2>&1 \
  || echo "[start.sh] WARNING: Python import check failed — dependencies may be missing"

# Start services, capturing output to /tmp logs AND echoing to stdout
mkdir -p /tmp/cria-logs
start_service() {
  local name="$1"; local logfile="/tmp/cria-logs/${name}.log"
  shift
  echo "[start.sh] Starting $name ..."
  env "$@" "$PYTHON" "$WORKSPACE_ROOT/artifacts/${name}.py" \
    > >(tee -a "$logfile") 2>&1 &
  echo $! > "/tmp/cria-logs/${name}.pid"
  echo "[start.sh] $name PID=$(cat /tmp/cria-logs/${name}.pid)"
}

start_service "cria-unified/main"   PORT=8003 BASE_PATH=/cria-unified ULTRARIA_URL=http://localhost:8004
start_service "cria-deepseek/main"  PORT=8001
start_service "cria-v4/main"        PORT=8002
start_service "cria-unified/ultraria_stub" PORT=8004 ULTRARIA_PORT=8004

# Wait for each port to actually bind (up to 30 s) before starting Node
wait_for_port() {
  local port="$1" name="$2" tries=30
  while [ $tries -gt 0 ]; do
    if (echo >/dev/tcp/127.0.0.1/"$port") 2>/dev/null; then
      echo "[start.sh] $name port $port ready"
      return 0
    fi
    sleep 1; tries=$((tries-1))
  done
  echo "[start.sh] WARNING: $name port $port not ready after 30 s — continuing anyway"
}

wait_for_port 8003 cria-unified
wait_for_port 8001 cria-v2
wait_for_port 8002 cria-v4
wait_for_port 8004 ultraria

echo "[start.sh] All services checked — starting Node api-server"
exec node --enable-source-maps "$WORKSPACE_ROOT/artifacts/api-server/dist/index.mjs"
