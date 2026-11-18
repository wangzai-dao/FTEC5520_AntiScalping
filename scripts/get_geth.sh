#!/usr/bin/env bash
# 下载 Geth 1.13.15（最后一个支持 Clique / miner.start() 私有链的稳定版）。
# Lab 1 用的是私有链 + 挖矿，Geth >= 1.14 只支持 PoS，故本项目锁定 1.13.15。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GETH_VERSION="${GETH_VERSION:-1.13.15}"
GETH_COMMIT="${GETH_COMMIT:-c5ba367e}"
BASE="https://gethstore.blob.core.windows.net/builds"

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)   SUFFIX="darwin-arm64" ;;
  Darwin-x86_64)  SUFFIX="darwin-amd64" ;;
  Linux-x86_64)   SUFFIX="linux-amd64"  ;;
  Linux-aarch64)  SUFFIX="linux-arm64"  ;;
  *) echo "不支持的平台: $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

NAME="geth-${SUFFIX}-${GETH_VERSION}-${GETH_COMMIT}"
URL="${BASE}/${NAME}.tar.gz"

if [[ -x "$ROOT/tools/geth" ]]; then
  echo "[geth] 已存在: $("$ROOT/tools/geth" version | head -2 | tail -1)"
  exit 0
fi

echo "[geth] 下载 $URL"
mkdir -p "$ROOT/tools"
curl -fSL --progress-bar -o "$ROOT/tools/geth.tar.gz" "$URL"
tar -xzf "$ROOT/tools/geth.tar.gz" -C "$ROOT/tools"
ln -sf "$ROOT/tools/${NAME}/geth" "$ROOT/tools/geth"
rm -f "$ROOT/tools/geth.tar.gz"
echo "[geth] 安装完成: $("$ROOT/tools/geth" version | head -3 | tr '\n' ' ')"
