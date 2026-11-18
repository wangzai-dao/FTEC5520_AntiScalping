#!/usr/bin/env bash
# 停止本地 Geth 节点
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$ROOT/blockchain/geth.pid"

if [[ ! -f "$PIDFILE" ]] || ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "[node] 没有正在运行的本地节点"
  rm -f "$PIDFILE"
  exit 0
fi

PID="$(cat "$PIDFILE")"
echo "[node] 停止 PID $PID"
kill "$PID"
for _ in $(seq 1 20); do
  kill -0 "$PID" 2>/dev/null || break
  sleep 0.5
done
kill -9 "$PID" 2>/dev/null || true
rm -f "$PIDFILE"
echo "[node] 已停止"
