"""部署 ConcertTicket 到私有链，并生成 config/network.json。

用法:
    ./blockchain/start_node.sh          # 先起链
    python backend/deploy.py            # 编译(如需要) + 部署 + 写配置

输出:
    config/network.json  合约地址、部署交易、部署区块、账户地址、ABI 路径
    contracts/build/ConcertTicket.json  ABI + bytecode（成员 2、3 交付物）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from eth_account import Account
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.chain import hx  # noqa: E402
from backend.compile import BUILD, compile_contracts  # noqa: E402
from backend.config import CONFIG_DIR, ROLES, load_settings  # noqa: E402

GWEI = 10**9


def main() -> None:
    settings = load_settings()
    w3 = Web3(Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": 30}))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    if not w3.is_connected():
        sys.exit(f"连不上节点 {settings.rpc_url}，请先运行 ./blockchain/start_node.sh")
    if w3.eth.chain_id != settings.chain_id:
        sys.exit(f"链 ID 不匹配：节点 {w3.eth.chain_id} vs .env {settings.chain_id}")

    artifact_path = BUILD / "ConcertTicket.json"
    if not artifact_path.exists():
        print("[deploy] 未找到编译产物，先编译")
        compile_contracts()
    artifact = json.loads(artifact_path.read_text("utf-8"))

    account = Account.from_key(settings.key("deployer"))
    balance = w3.from_wei(w3.eth.get_balance(account.address), "ether")
    print(f"[deploy] 链 {settings.chain_id}，区块高度 {w3.eth.block_number}，部署账户 "
          f"{account.address}（{balance} ETH）")
    if balance == 0:
        sys.exit("部署账户余额为 0，请确认 genesis.json 的 alloc 是否包含该账户")

    factory = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    nonce = w3.eth.get_transaction_count(account.address)
    base_fee = w3.eth.get_block("latest").get("baseFeePerGas", GWEI)
    tx = factory.constructor().build_transaction(
        {
            "from": account.address,
            "nonce": nonce,
            "chainId": settings.chain_id,
            "gas": 4_000_000,
            "maxPriorityFeePerGas": GWEI,
            "maxFeePerGas": base_fee * 2 + GWEI,
        }
    )
    signed = Account.sign_transaction(tx, account.key)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    tx_hash = w3.eth.send_raw_transaction(raw)
    print(f"[deploy] 已发送部署交易 {hx(tx_hash)}，等待打包…")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt.status != 1:
        sys.exit("部署失败：交易 status=0")

    address = receipt.contractAddress
    code_size = len(w3.eth.get_code(address))
    print(f"[deploy] 合约地址 {address}")
    print(f"[deploy] 区块 {receipt.blockNumber}，gas {receipt.gasUsed}，代码 {code_size} bytes")

    CONFIG_DIR.mkdir(exist_ok=True)
    network = {
        "network_name": "FTEC5520 local private chain (Geth clique, chainId 1337)",
        "rpc_url": settings.rpc_url,
        "chain_id": settings.chain_id,
        "contract_address": Web3.to_checksum_address(address),
        "deploy_block": receipt.blockNumber,
        "deploy_tx": hx(tx_hash),
        "deploy_gas_used": receipt.gasUsed,
        "compiler": artifact["compiler"],
        "abi_path": "contracts/build/ConcertTicket.json",
        "accounts": {role: Account.from_key(settings.key(role)).address
                     for role in ROLES if role in settings.private_keys},
    }
    (CONFIG_DIR / "network.json").write_text(json.dumps(network, indent=2, ensure_ascii=False), "utf-8")
    print(f"[deploy] 配置已写入 {CONFIG_DIR / 'network.json'}")

    # 部署后立即做一次只读调用，确认 ABI 与地址匹配
    contract = w3.eth.contract(address=address, abi=artifact["abi"])
    print(f"[deploy] self-check: nextEventId={contract.functions.nextEventId().call()} "
          f"nextTokenId={contract.functions.nextTokenId().call()} "
          f"owner={contract.functions.owner().call()}")


if __name__ == "__main__":
    main()
