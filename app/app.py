"""Overview page (entry point app.py): on-chain overview / system architecture / demo entry points."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    api,
    chain_guard,
    header,
    init_page,
    short,
    sidebar_nav,
    sidebar_status,
)

init_page()
sidebar_nav()
sidebar_status()
status = chain_guard()

header(
    "Blockchain Anti-Scalping Ticketing",
    "FTEC5520 Applied Blockchain & Cryptocurrencies · private chain + Solidity + Web3.py + Streamlit",
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Chain ID / Block", f"{status['chain_id']} / {status['block_number']}")
c2.metric("Contract", short(status["contract_address"], 10, 6))
events = api.list_events()
c3.metric("Events", len(events))
c4.metric("Tickets issued", api.get_next_token_id() - 1)

st.markdown("#### System architecture")
st.markdown(
    """
| Layer | Component | Owner |
|---|---|---|
| Chain | Geth private chain (Clique PoA, chainId 1337) | Member 1 |
| Contract | `ConcertTicket.sol`: ERC-721 tickets + capped resale + check-in | Members 2 / 3 |
| API | `backend/ticket_api.py`: Web3.py wrapper returning `ok / tx_hash / gas_used` | Member 1 |
| UI | Streamlit pages + signature-based QR check-in | Member 4 |
"""
)
st.caption(
    "Everything shown here — ticket owner, listing state, check-in status — is read from on-chain "
    "`ownerOf` / `tickets()` / `concertEvents()`. None of it is frontend mock data."
)

st.markdown("#### Test accounts and balances")
accounts = api.get_accounts()
rows = []
for role, addr in accounts.items():
    rows.append(
        {
            "Role": role,
            "Address": addr,
            "Balance (ETH)": api.get_balance_eth(addr),
            "Purpose": {
                "deployer": "Deploys the contract / owner",
                "organizer": "Event organizer, creates events",
                "buyerA": "Primary-market buyer",
                "buyerB": "Secondary-market buyer",
                "verifier": "Authorized check-in staff",
                "attacker": "Abuse-test account",
            }.get(role, ""),
        }
    )
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

st.markdown("#### Recent on-chain ticket transfers")
history = api.transfer_history(6)
if history:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "tokenId": h["token_id"],
                    "from": short(h["from"]),
                    "to": short(h["to"]),
                    "Type": "Mint" if h["from"] == "0x0000000000000000000000000000000000000000" else "Resale",
                    "Block": h["block"],
                    "Tx hash": h["tx_hash"],
                }
                for h in history
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
else:
    st.info("No tickets yet. Open **Events → Buy Tickets** on the left to create an event and buy one.")

st.markdown("#### Suggested demo flow")
st.markdown(
    """
1. **Events**: the organizer creates an event (face value 1 ETH, limit 2 per wallet, show 10 days out).
2. **Buy Tickets**: Buyer A buys 1 ticket; the page shows the real tx hash and `ownerOf` immediately.
3. **Resale Market**: Buyer A lists at 1.5 ETH and the contract rejects it; 1.2 ETH succeeds; Buyer B buys.
4. **Staff Check-in**: Buyer B shows the signed QR code; the first check-in succeeds, the second fails.
"""
)

with st.expander("Why must these rules live in the smart contract?"):
    st.markdown(
        """
- Per-wallet limits, price caps, resale counts and check-in state all live in `ConcertTicket.sol`,
  so **no frontend parameter can bypass them**.
- The contract `override`s `transferFrom` / `safeTransferFrom`, so wallets cannot move tickets
  privately. Ownership can only change via `listForResale` → `buyResale`, which leaves an on-chain
  record of every transfer.
- The website is just a remote control: it reads the real state of `ownerOf`, `tickets(tokenId)` and
  `concertEvents(eventId)` instead of mutable fields in a database.
"""
    )
