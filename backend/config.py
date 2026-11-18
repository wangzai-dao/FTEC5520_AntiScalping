"""Unified configuration loading: .env (private keys / RPC URL) + config/network.json
(contract address / ABI / accounts).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
ENV_PATH = ROOT / ".env"

DEFAULT_RPC = "http://127.0.0.1:8545"
DEFAULT_CHAIN_ID = 1337
ROLES = ("deployer", "organizer", "buyerA", "buyerB", "verifier", "attacker")


def _load_dotenv(path: Path = ENV_PATH) -> None:
    """Lightweight .env parser that avoids a hard dependency on python-dotenv.

    Environment variables that are already set take precedence.
    """
    if not path.exists():
        return
    for raw in path.read_text("utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


@dataclass
class Settings:
    rpc_url: str = DEFAULT_RPC
    chain_id: int = DEFAULT_CHAIN_ID
    contract_address: str | None = None
    deploy_block: int = 0
    deploy_tx: str | None = None
    abi_path: Path = field(default_factory=lambda: ROOT / "contracts" / "build" / "ConcertTicket.json")
    network_name: str = "FTEC5520 local private chain"
    account_addresses: dict[str, str] = field(default_factory=dict)
    private_keys: dict[str, str] = field(default_factory=dict)

    def key(self, role: str) -> str:
        try:
            return self.private_keys[role]
        except KeyError as exc:
            raise KeyError(
                f"Missing private key for {role}; check .env PRIVATE_KEY_{role.upper()}"
            ) from exc

    def address(self, role: str) -> str:
        try:
            return self.account_addresses[role]
        except KeyError as exc:
            raise KeyError(
                f"Unknown role: {role}; available: {', '.join(self.account_addresses) or 'none'}"
            ) from exc


def load_settings(path: Path | None = None) -> Settings:
    _load_dotenv()
    settings = Settings(rpc_url=os.getenv("RPC_URL", DEFAULT_RPC), chain_id=int(os.getenv("CHAIN_ID", DEFAULT_CHAIN_ID)))

    network_file = CONFIG_DIR / "network.json"
    if network_file.exists():
        data = json.loads(network_file.read_text("utf-8"))
        settings.network_name = data.get("network_name", settings.network_name)
        settings.rpc_url = data.get("rpc_url", settings.rpc_url)
        settings.chain_id = int(data.get("chain_id", settings.chain_id))
        settings.contract_address = data.get("contract_address")
        settings.deploy_block = int(data.get("deploy_block", 0))
        settings.deploy_tx = data.get("deploy_tx")
        settings.account_addresses = dict(data.get("accounts", {}))
        abi = data.get("abi_path")
        if abi:
            settings.abi_path = (ROOT / abi) if not Path(abi).is_absolute() else Path(abi)

    # Private keys are read only from environment variables and never written to
    # network.json. Addresses derived from the private keys are the single source of
    # truth: after re-running init_chain.py, stale addresses in network.json are
    # corrected. Otherwise you hit the bizarre failure of signing with a new key while
    # assuming you are still the old address (found by Member 5 while reproducing tests).
    for role in ROLES:
        key = os.getenv(f"PRIVATE_KEY_{role.upper()}")
        if key:
            from eth_account import Account

            settings.private_keys[role] = key
            settings.account_addresses[role] = Account.from_key(key).address

    return settings
