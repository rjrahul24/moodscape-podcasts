#!/usr/bin/env bash
#
# One command to run the whole app in dev.
#
# Starts the FastAPI backend (:8000, --reload) and the Vite frontend dev server
# (:5173, which proxies /api → :8000) as child processes, streams both logs to
# this terminal, and tears both down together on Ctrl-C / exit.
#
# Usage:  ./dev.sh          (from the repo root)
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Hold the child PIDs so the trap can clean both up.
pids=()

# Kill a process and all its descendants, leaves first. uvicorn spawns a reload
# child and npm spawns vite/esbuild that don't forward signals, so killing the
# tracked parent alone would orphan them. pgrep -P is available on stock macOS.
kill_tree() {
  local pid="$1" child
  for child in $(pgrep -P "$pid" 2>/dev/null); do
    kill_tree "$child"
  done
  kill "$pid" 2>/dev/null || true
}

cleanup() {
  for pid in "${pids[@]:-}"; do
    kill_tree "$pid"
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "→ backend  http://localhost:8000  (FastAPI, --reload)"
echo "→ frontend http://localhost:5173  (Vite — open this one)"
echo

# Backend: uv-managed venv.
( cd "$ROOT/backend" && exec uv run uvicorn app.main:app --reload ) &
pids+=($!)

# Frontend: vite dev server with the /api proxy.
( cd "$ROOT/frontend" && exec npm run dev ) &
pids+=($!)

# Exit (and trigger cleanup via the trap) as soon as either process dies.
# Polled rather than `wait -n` so this works on macOS's stock bash 3.2.
while true; do
  for pid in "${pids[@]}"; do
    kill -0 "$pid" 2>/dev/null || exit 0
  done
  sleep 1
done
