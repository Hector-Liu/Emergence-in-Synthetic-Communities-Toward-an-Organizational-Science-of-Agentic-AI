#!/bin/bash
# Launcher: prepares the Python environment on first run, starts the server and opens the browser.
# Paid runs need ANTHROPIC_API_KEY (environment variable or a .env file in this folder).
set -e
cd "$(dirname "$0")"
PORT="${PORT:-8767}"
URL="http://127.0.0.1:$PORT"

find_uv() { command -v uv 2>/dev/null || { [ -x "$HOME/.local/bin/uv" ] && echo "$HOME/.local/bin/uv"; } || true; }
find_python() {
  for p in python3.13 python3.12 python3.14 python3; do
    if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then echo "$p"; return; fi
  done
}

REQ_HASH=$(shasum requirements.txt | cut -d' ' -f1)
if [ ! -x venv/bin/python ] || [ "$(cat venv/.req_hash 2>/dev/null)" != "$REQ_HASH" ]; then
  echo "Preparing the Python environment (first run takes 1-2 minutes)..."
  UV=$(find_uv)
  if [ -n "$UV" ]; then
    [ -x venv/bin/python ] || "$UV" venv --python 3.13 venv
    "$UV" pip install --python venv/bin/python -r requirements.txt
  else
    PY=$(find_python)
    if [ -z "$PY" ]; then echo "Python 3.12+ not found. Install Python 3.13 from python.org, then run again."; read -r; exit 1; fi
    [ -x venv/bin/python ] || "$PY" -m venv venv
    venv/bin/pip install -q -r requirements.txt
  fi
  echo "$REQ_HASH" > venv/.req_hash
fi

if curl -fs "$URL/api/health" >/dev/null 2>&1; then
  echo "Already running: $URL"
  [ -n "$NO_BROWSER" ] || open "$URL" 2>/dev/null || true
  exit 0
fi

venv/bin/python -m uvicorn fakemolt.api:app --host 127.0.0.1 --port "$PORT" --log-level warning &
PID=$!
trap 'kill $PID 2>/dev/null; exit 0' EXIT INT TERM
for _ in $(seq 1 80); do
  curl -fs "$URL/api/health" >/dev/null 2>&1 && break
  sleep 0.25
done
[ -n "$NO_BROWSER" ] || open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true
echo ""
echo "Fake Moltbook is running at $URL"
echo "Close this window (or press Ctrl+C) to stop it."
wait $PID
