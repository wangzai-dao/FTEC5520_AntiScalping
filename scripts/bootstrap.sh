#!/usr/bin/env bash
# 一条命令从零把项目跑起来（新机器 / 队友拿到压缩包后执行）
# 前置：Python 3.10+、能访问 pypi / binaries.soliditylang.org / gethstore
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PY="${PYTHON:-python3}"
echo "[1/8] 创建虚拟环境"
[[ -d .venv ]] || "$PY" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
echo "[2/8] 安装 Python 依赖"
.venv/bin/pip install -q -r requirements.txt

echo "[3/8] 下载 Geth 1.13.15"
./scripts/get_geth.sh

echo "[4/8] 下载 OpenZeppelin 5.0.2"
.venv/bin/python backend/fetch_deps.py

echo "[5/8] 生成测试账户 + genesis"
if [[ -f .env ]]; then
  echo "     .env 已存在，跳过（要重建请先删除 .env 和 blockchain/genesis.json）"
else
  .venv/bin/python blockchain/init_chain.py
fi

echo "[6/8] 启动私有链"
./blockchain/start_node.sh
sleep 4

echo "[7/8] 编译 + 部署"
.venv/bin/python backend/compile.py
.venv/bin/python backend/deploy.py

echo "[8/8] 生成演示数据与证据"
.venv/bin/python backend/demo_flow.py

cat <<'MSG'

✅ 全部就绪。启动网站：
   .venv/bin/streamlit run app/app.py
   浏览器打开 http://127.0.0.1:8501
MSG
