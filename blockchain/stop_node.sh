#!/usr/bin/env bash
# Stop the local Geth node
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$ROOT/blockchain/geth.pid"

if [[ ! -f "$PIDFILE" ]] || ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "[node] no local node is running"
  rm -f "$PIDFILE"
  exit 0
fi

PID="$(cat "$PIDFILE")"
echo "[node] stopping PID $PID"
kill "$PID"
for _ in $(seq 1 20); do
  kill -0 "$PID" 2>/dev/null || break
  sleep 0.5
done
kill -9 "$PID" 2>/dev/null || true
rm -f "$PIDFILE"
echo "[node] stopped"
