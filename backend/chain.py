"""Low-level wrapper around the Web3 connection and transaction sending (Member 1 module).

Design notes:
* Every write goes through `Chain.send()`, which handles nonce, gas, signing, waiting for
  the receipt and exceptions in one place, so the layer above (ticket_api.py) only has to
  deal with business parameters.
* Return values are always TxResult(ok, tx_hash, block_number, gas_used, error), which is
  easy to display in Streamlit.
* On the private chain (Clique) extraData is longer than 32 bytes, so the POA middleware
  must be injected, otherwise blocks cannot be fetched.
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
    """Unified return structure: ok / tx_hash / block_number / gas_used / error."""

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

    def __str__(self) -> str:  # convenient for CLI / logging
        if self.ok:
            return (
                f"[OK] {self.function} tx={self.tx_hash} block={self.block_number} "
                f"gas={self.gas_used}"
            )
        return f"[FAIL] {self.function}: {self.error}"


def hx(value) -> str:
    """Convert HexBytes / bytes into a hex string with a 0x prefix."""
    text = value.hex() if hasattr(value, "hex") else str(value)
    return text if text.startswith("0x") else "0x" + text


def clean_revert(exc: Exception) -> str:
    """Extract a human-readable revert reason from an exception raised by web3."""
    raw = getattr(exc, "message", None) or str(exc)
    if isinstance(raw, dict):
        raw = raw.get("message", "") or str(raw)
    msg = str(raw)
    if "execution reverted:" in msg:
        msg = msg.split("execution reverted:", 1)[1]
    # web3 also appends the revert data to the message, as in "... reason', '0x08c379a0..."
    for sep in ("', '0x", '", "0x', "', '", '\n'):
        msg = msg.split(sep, 1)[0]
    return msg.strip().strip("'\"")[:400] or exc.__class__.__name__


class Chain:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.w3 = Web3(Web3.HTTPProvider(self.settings.rpc_url, request_kwargs={"timeout": 30}))
        # Clique private chain: block extraData is 97 bytes, the POA middleware parses it
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.contract = None
        if self.settings.contract_address:
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.settings.contract_address),
                abi=self.abi,
            )

    # ------------------------------------------------------------------
    # Basic information
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
                "Contract not deployed: run python backend/deploy.py to create config/network.json"
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
    # Sending transactions
    # ------------------------------------------------------------------
    def _fee_fields(self) -> dict[str, Any]:
        block = self.w3.eth.get_block("latest")
        base_fee = block.get("baseFeePerGas")
        if base_fee is None:  # old chain without London enabled
            return {"gasPrice": max(self.w3.eth.gas_price, GWEI)}
        priority = GWEI
        return {
            "maxPriorityFeePerGas": priority,
            "maxFeePerGas": base_fee * 2 + priority,
        }

    def send(self, fn, role: str = "deployer", value: int = 0) -> TxResult:
        """Call a contract write function and return a TxResult in the unified structure."""
        name = getattr(fn, "fn_name", "call")
        try:
            contract = self.require_contract()
            account = Account.from_key(self.settings.key(role))
        except Exception as exc:  # configuration error
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
        except Exception as exc:  # noqa: BLE001  estimate_gas surfaces the revert reason
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
                error=f"Not mined within {RECEIPT_TIMEOUT}s; is the node producing blocks?",
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
                error="Transaction was mined but execution failed (status=0)",
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
    # Read-only helpers
    # ------------------------------------------------------------------
    def receipt(self, tx_hash: str) -> dict[str, Any]:
        try:
            r = self.w3.eth.get_transaction_receipt(tx_hash)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "tx_hash": tx_hash, "error": f"Transaction not found: {exc}"}
        if r is None:
            return {"ok": False, "tx_hash": tx_hash, "error": "Transaction not mined"}
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
    """In-process singleton, so a page refresh does not reconnect every time."""
    global _chain
    if _chain is None or reload:
        _chain = Chain()
    return _chain


_clean_revert = clean_revert  # kept for backwards compatibility
