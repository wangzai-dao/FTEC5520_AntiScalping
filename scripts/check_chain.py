#!/usr/bin/env python
"""Private-chain connectivity self-check: chainId / block height / account balances / contract readability.

Usage:
    python scripts/check_chain.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import ticket_api as api  # noqa: E402


def main() -> int:
    status = api.get_chain_status()
    print(f"RPC          : {status['rpc_url']}")
    print(f"connected    : {status['connected']}")
    if not status["connected"]:
        print("Node unavailable: please run ./blockchain/start_node.sh")
        return 1
    print(f"chainId      : {status['chain_id']}")
    print(f"blockNumber  : {status['block_number']}")
    print(f"contract     : {status['contract_address'] or '(not deployed)'}")

    for role, balance in status["balances"].items():
        print(f"  {role:<10} {api.get_accounts()[role]}  {balance} ETH")

    if not status["contract_address"]:
        return 2

    print(f"nextEventId  : {api.get_next_event_id()}")
    print(f"nextTokenId  : {api.get_next_token_id()}")
    events = api.list_events()
    print(f"events       : {len(events)}")
    for e in events:
        print(f"  #{e['event_id']} {e['name']}  {e['sold']}/{e['max_supply']}  {e['price_eth']} ETH")
    print(f"tickets      : {len(api.all_tokens())}, listed {len(api.listed_tickets())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
