#!/usr/bin/env bash
# 启动本地 Geth 私有链（Clique PoA，chainId 1337）。
# 用法: ./blockchain/start_node.sh [--reset]
# 日志: blockchain/geth.log    PID: blockchain/geth.pid
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATADIR="$ROOT/blockchain/data"
GETH="${GETH:-$ROOT/tools/geth}"
CHAIN_ID=1337
RPC_PORT="${RPC_PORT:-8545}"
P2P_PORT="${P2P_PORT:-30304}"

if [[ ! -x "$GETH" ]]; then
  echo "找不到 geth: $GETH" >&2
  echo "请先运行: ./tools/get_geth.sh" >&2
  exit 1
fi
if [[ ! -f "$ROOT/blockchain/genesis.json" ]]; then
  echo "缺少 blockchain/genesis.json，请先运行: python blockchain/init_chain.py" >&2
  exit 1
fi

if [[ "${1:-}" == "--reset" ]]; then
  echo "[node] --reset：停止节点并删除链数据"
  "$ROOT/blockchain/stop_node.sh" || true
  rm -rf "$DATADIR"
fi

MINER="$(cat "$ROOT/blockchain/miner.addr")"
PASSWORD="$ROOT/blockchain/password.txt"

if [[ ! -d "$DATADIR/geth/chaindata" ]]; then
  echo "[node] 首次启动：导入矿工账户并写入 genesis"
  "$GETH" --datadir "$DATADIR" account import \
      --password "$PASSWORD" "$ROOT/blockchain/miner.key" >/dev/null
  "$GETH" --datadir "$DATADIR" init "$ROOT/blockchain/genesis.json" >/dev/null
fi

if [[ -f "$ROOT/blockchain/geth.pid" ]] && kill -0 "$(cat "$ROOT/blockchain/geth.pid")" 2>/dev/null; then
  echo "[node] 已经在运行，PID $(cat "$ROOT/blockchain/geth.pid")"
  exit 0
fi

echo "[node] 启动 Geth：chainId=$CHAIN_ID RPC=http://127.0.0.1:$RPC_PORT miner=$MINER"
nohup "$GETH" \
  --datadir "$DATADIR" \
  --networkid "$CHAIN_ID" \
  --http --http.addr 127.0.0.1 --http.port "$RPC_PORT" \
  --http.api eth,net,web3,personal \
  --http.corsdomain '*' \
  --mine --miner.etherbase "$MINER" \
  --unlock "$MINER" --password "$PASSWORD" --allow-insecure-unlock \
  --nodiscover --port "$P2P_PORT" --ipcdisable \
  --verbosity 3 \
  >> "$ROOT/blockchain/geth.log" 2>&1 &

echo $! > "$ROOT/blockchain/geth.pid"
sleep 3

if curl -sS -m 5 -X POST -H 'Content-Type: application/json' \
    --data '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' \
    "http://127.0.0.1:$RPC_PORT" | grep -q result; then
  echo "[node] RPC 就绪（PID $(cat "$ROOT/blockchain/geth.pid")，日志 blockchain/geth.log）"
else
  echo "[node] RPC 未就绪，请查看 blockchain/geth.log" >&2
  exit 1
fi
