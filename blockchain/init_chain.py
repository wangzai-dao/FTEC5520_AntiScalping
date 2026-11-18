#!/usr/bin/env python
"""初始化本地私有链：生成测试账户 + genesis.json + .env。

对应"成员 1：准备 organizer / buyerA / buyerB / verifier / attacker 等课堂测试账户"。
本脚本只在本机使用；生成出来的 .env / genesis.json 含私钥与地址，
.env 已被 .gitignore 排除，禁止 push 到 GitHub。

用法:
    python blockchain/init_chain.py            # 首次初始化（已存在则拒绝覆盖）
    python blockchain/init_chain.py --force    # 重新生成账户并覆盖 genesis（会清空链数据）
"""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import sys
from pathlib import Path

from eth_account import Account

ROOT = Path(__file__).resolve().parents[1]
CHAIN = ROOT / "blockchain"

CHAIN_ID = 1337
PERIOD = 2          # Clique 出块间隔（秒）
BALANCE_ETH = 1000  # 每个测试账户的初始余额

ROLES = ["deployer", "organizer", "buyerA", "buyerB", "verifier", "attacker", "miner"]
GAS_LIMIT = "0x1c9c380"  # 30,000,000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="覆盖已有 genesis 和 .env（会销毁本地链数据）")
    args = ap.parse_args()

    env_path = ROOT / ".env"
    genesis_path = CHAIN / "genesis.json"
    if (env_path.exists() or genesis_path.exists()) and not args.force:
        sys.exit(
            "已存在 .env 或 blockchain/genesis.json。\n"
            "如需重新生成请加 --force（会删除 blockchain/data 里的本地链数据）。"
        )

    accounts = {}
    for role in ROLES:
        acct = Account.create(secrets.token_hex(32))
        accounts[role] = {
            "address": acct.address,
            "key": "0x" + acct.key.hex().removeprefix("0x"),
        }

    # ---- genesis.json -------------------------------------------------
    miner = accounts["miner"]["address"].lower().removeprefix("0x")
    alloc = {
        acc["address"].lower().removeprefix("0x"): {"balance": hex(BALANCE_ETH * 10**18)}
        for acc in accounts.values()
    }
    genesis = {
        "config": {
            "chainId": CHAIN_ID,
            "homesteadBlock": 0,
            "eip150Block": 0,
            "eip155Block": 0,
            "eip158Block": 0,
            "byzantiumBlock": 0,
            "constantinopleBlock": 0,
            "petersburgBlock": 0,
            "istanbulBlock": 0,
            "berlinBlock": 0,
            "londonBlock": 0,
            "clique": {"period": PERIOD, "epoch": 30000},
        },
        "difficulty": "0x1",
        "gasLimit": GAS_LIMIT,
        # Clique 的 extradata: 32 字节 0x00 + 签名者地址 + 65 字节 0x00
        "extradata": "0x" + "00" * 32 + miner + "00" * 65,
        "alloc": alloc,
    }
    CHAIN.mkdir(parents=True, exist_ok=True)
    genesis_path.write_text(json.dumps(genesis, indent=2), "utf-8")

    # ---- 节点启动需要的辅助文件 ---------------------------------------
    (CHAIN / "miner.key").write_text(accounts["miner"]["key"].removeprefix("0x") + "\n", "utf-8")
    (CHAIN / "miner.addr").write_text(accounts["miner"]["address"] + "\n", "utf-8")
    pw_path = CHAIN / "password.txt"
    if not pw_path.exists():
        pw_path.write_text("ftec5520\n", "utf-8")

    # ---- .env ---------------------------------------------------------
    lines = [
        "# 本地私有链连接配置（由 blockchain/init_chain.py 生成，切勿提交到 GitHub）",
        f"RPC_URL=http://127.0.0.1:8545",
        f"CHAIN_ID={CHAIN_ID}",
        "",
        "# 课堂测试账户私钥（仅用于本地演示；真实产品应由用户自己保管私钥）",
    ]
    for role, acc in accounts.items():
        lines.append(f"PRIVATE_KEY_{role.upper()}={acc['key']}")
    env_path.write_text("\n".join(lines) + "\n", "utf-8")

    if args.force and (CHAIN / "data").exists():
        shutil.rmtree(CHAIN / "data")
        print("[init] 已删除旧的 blockchain/data")

    print(f"[init] chainId={CHAIN_ID} clique period={PERIOD}s balance={BALANCE_ETH} ETH")
    for role, acc in accounts.items():
        print(f"[init] {role:<10} {acc['address']}")
    print(f"[init] genesis  -> {genesis_path}")
    print(f"[init] 私钥      -> {env_path}（已 gitignore）")


if __name__ == "__main__":
    main()
