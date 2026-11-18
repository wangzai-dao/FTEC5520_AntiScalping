"""Web3 连接与交易发送的底层封装（成员 1 模块）。

设计要点：
* 所有写操作都走 `Chain.send()`，由它统一处理 nonce、gas、签名、等待回执和异常，
  上层 ticket_api.py 只关心业务参数。
* 返回值统一为 TxResult(ok, tx_hash, block_number, gas_used, error)，方便 Streamlit 展示。
* 私有链（Clique）的 extraData 超过 32 字节，必须注入 POA 中间件，否则拿不到区块。
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from eth_account import Account
from web3 import Web3
from web3.exceptions import TimeExhausted
from web3.middleware import ExtraDataToPOAMiddleware

from .config import Settings, load_settings

GWEI = 10**9
RECEIPT_TIMEOUT = 120


@dataclass
class TxResult:
    """统一返回结构：ok / tx_hash / block_number / gas_used / error。"""

    ok: bool
    function: str
    tx_hash: str | None = None
    block_number: int | None = None
    gas_used: int | None = None
    status: int | None = None
    from_address: str | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:  # 方便 CLI / 日志
        if self.ok:
            return (
                f"[OK] {self.function} tx={self.tx_hash} block={self.block_number} "
                f"gas={self.gas_used}"
            )
        return f"[FAIL] {self.function}: {self.error}"


def hx(value) -> str:
    """把 HexBytes / bytes 转成带 0x 前缀的十六进制字符串。"""
    text = value.hex() if hasattr(value, "hex") else str(value)
    return text if text.startswith("0x") else "0x" + text


def clean_revert(exc: Exception) -> str:
    """从 web3 抛出的异常里取出人类可读的 revert 原因。"""
    raw = getattr(exc, "message", None) or str(exc)
    if isinstance(raw, dict):
        raw = raw.get("message", "") or str(raw)
    msg = str(raw)
    if "execution reverted:" in msg:
        msg = msg.split("execution reverted:", 1)[1]
    # web3 会把 revert data 也拼进消息里，形如 "... reason', '0x08c379a0..."
    for sep in ("', '0x", '", "0x', "', '", '\n'):
        msg = msg.split(sep, 1)[0]
    return msg.strip().strip("'\"")[:400] or exc.__class__.__name__


class Chain:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.w3 = Web3(Web3.HTTPProvider(self.settings.rpc_url, request_kwargs={"timeout": 30}))
        # Clique 私有链：区块 extraData 为 97 字节，需要 POA 中间件解析
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.contract = None
        if self.settings.contract_address:
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.settings.contract_address),
                abi=self.abi,
            )

    # ------------------------------------------------------------------
    # 基础信息
    # ------------------------------------------------------------------
    @property
    def abi(self) -> list[dict]:
        import json

        data = json.loads(Path(self.settings.abi_path).read_text("utf-8"))
        return data["abi"]

    @property
    def is_connected(self) -> bool:
        try:
            return self.w3.is_connected()
        except Exception:
            return False

    def require_contract(self):
        if self.contract is None:
            raise RuntimeError(
                "尚未部署合约：请先运行 python backend/deploy.py 生成 config/network.json"
            )
        return self.contract

    def chain_status(self) -> dict[str, Any]:
        status: dict[str, Any] = {
            "connected": self.is_connected,
            "rpc_url": self.settings.rpc_url,
            "chain_id": None,
            "block_number": None,
            "contract_address": self.settings.contract_address,
            "deploy_block": self.settings.deploy_block,
            "network_name": self.settings.network_name,
            "balances": {},
        }
        if not status["connected"]:
            return status
        status["chain_id"] = self.w3.eth.chain_id
        status["block_number"] = self.w3.eth.block_number
        for role, addr in self.settings.account_addresses.items():
            status["balances"][role] = self.w3.from_wei(
                self.w3.eth.get_balance(Web3.to_checksum_address(addr)), "ether"
            )
        return status

    def balance_eth(self, address: str) -> float:
        return float(self.w3.from_wei(self.w3.eth.get_balance(Web3.to_checksum_address(address)), "ether"))

    # ------------------------------------------------------------------
    # 交易发送
    # ------------------------------------------------------------------
    def _fee_fields(self) -> dict[str, Any]:
        block = self.w3.eth.get_block("latest")
        base_fee = block.get("baseFeePerGas")
        if base_fee is None:  # 未启用 London 的老链
            return {"gasPrice": max(self.w3.eth.gas_price, GWEI)}
        priority = GWEI
        return {
            "maxPriorityFeePerGas": priority,
            "maxFeePerGas": base_fee * 2 + priority,
        }

    def send(self, fn, role: str = "deployer", value: int = 0) -> TxResult:
        """调用合约写函数，返回统一结构的 TxResult。"""
        name = getattr(fn, "fn_name", "call")
        try:
            contract = self.require_contract()
            account = Account.from_key(self.settings.key(role))
        except Exception as exc:  # 配置错误
            return TxResult(ok=False, function=name, error=str(exc))

        sender = account.address

        try:
            gas_estimate = fn.estimate_gas({"from": sender, "value": value})
            tx = fn.build_transaction(
                {
                    "from": sender,
                    "value": value,
                    "nonce": self.w3.eth.get_transaction_count(sender, "pending"),
                    "chainId": self.settings.chain_id,
                    "gas": int(gas_estimate * 1.3) + 10_000,
                    **self._fee_fields(),
                }
            )
        except Exception as exc:  # noqa: BLE001  estimate_gas 会把 revert 原因抛出
            return TxResult(ok=False, function=name, from_address=sender, error=clean_revert(exc))

        tx.pop("from", None)
        try:
            signed = Account.sign_transaction(tx, account.key)
            raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
            tx_hash = self.w3.eth.send_raw_transaction(raw)
        except Exception as exc:  # noqa: BLE001
            return TxResult(ok=False, function=name, from_address=sender, error=str(exc)[:400])

        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=RECEIPT_TIMEOUT, poll_latency=0.4)
        except TimeExhausted:
            return TxResult(
                ok=False,
                function=name,
                tx_hash=hx(tx_hash),
                from_address=sender,
                error=f"{RECEIPT_TIMEOUT}s 内未确认，请检查节点是否在出块",
            )

        if receipt.status != 1:
            return TxResult(
                ok=False,
                function=name,
                tx_hash=hx(tx_hash),
                block_number=receipt.blockNumber,
                gas_used=receipt.gasUsed,
                status=receipt.status,
                from_address=sender,
                error="交易已打包但执行失败（status=0）",
            )

        return TxResult(
            ok=True,
            function=name,
            tx_hash=hx(tx_hash),
            block_number=receipt.blockNumber,
            gas_used=receipt.gasUsed,
            status=receipt.status,
            from_address=sender,
        )

    # ------------------------------------------------------------------
    # 只读辅助
    # ------------------------------------------------------------------
    def receipt(self, tx_hash: str) -> dict[str, Any]:
        try:
            r = self.w3.eth.get_transaction_receipt(tx_hash)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "tx_hash": tx_hash, "error": f"查不到该交易: {exc}"}
        if r is None:
            return {"ok": False, "tx_hash": tx_hash, "error": "交易未被打包"}
        tx = self.w3.eth.get_transaction(tx_hash)
        return {
            "ok": True,
            "tx_hash": tx_hash,
            "block_number": r.blockNumber,
            "block_hash": hx(r.blockHash),
            "gas_used": r.gasUsed,
            "gas_limit": tx.gas,
            "effective_gas_price_gwei": round(
                (r.get("effectiveGasPrice") or 0) / GWEI, 3
            ),
            "status": r.status,
            "from": r["from"],
            "to": r["to"],
            "contract_address": r.contractAddress,
            "timestamp": self.w3.eth.get_block(r.blockNumber)["timestamp"],
        }

    def wait_ready(self, timeout: float = 30.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_connected:
                return True
            time.sleep(0.5)
        return False


_chain: Chain | None = None


def get_chain(reload: bool = False) -> Chain:
    """进程内单例，避免每次页面刷新都重连。"""
    global _chain
    if _chain is None or reload:
        _chain = Chain()
    return _chain


_clean_revert = clean_revert  # 兼容旧调用
