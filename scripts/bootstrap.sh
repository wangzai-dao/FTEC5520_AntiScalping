#!/usr/bin/env bash
# Bring the project up from scratch with a single command (new machine / teammates after unzipping)
# Prerequisites: Python 3.10+, with access to pypi / binaries.soliditylang.org / gethstore
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PY="${PYTHON:-python3}"
echo "[1/8] Creating the virtual environment"
[[ -d .venv ]] || "$PY" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
echo "[2/8] Installing Python dependencies"
.venv/bin/pip install -q -r requirements.txt

echo "[3/8] Downloading Geth 1.13.15"
./scripts/get_geth.sh

echo "[4/8] Downloading OpenZeppelin 5.0.2"
.venv/bin/python backend/fetch_deps.py

echo "[5/8] Generating test accounts + genesis"
if [[ -f .env ]]; then
  echo "     .env already exists, skipping (to rebuild, delete .env and blockchain/genesis.json first)"
else
  .venv/bin/python blockchain/init_chain.py
fi

echo "[6/8] Starting the private chain"
./blockchain/start_node.sh
sleep 4

echo "[7/8] Compile + deploy"
.venv/bin/python backend/compile.py
.venv/bin/python backend/deploy.py

echo "[8/8] Generate demo data and evidence"
.venv/bin/python backend/demo_flow.py

cat <<'MSG'

✅ All set. Start the website:
   .venv/bin/streamlit run app/app.py
   open http://127.0.0.1:8501 in your browser
MSG
