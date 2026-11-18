"""Buy page: primary-market purchases, showing the real transaction hash and on-chain ticket owner."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import (  # noqa: E402
    account_select,
    api,
    chain_guard,
    header,
    init_page,
    short,
    sidebar_nav,
    sidebar_status,
    tx_box,
)

init_page()
sidebar_nav()
sidebar_status()
chain_guard()

header("Buy Tickets (Primary Market)", "Calls purchaseTickets to mint an ERC-721 ticket. Price, supply, wallet limit and whitelist are all enforced by the contract.")

events = [e for e in api.list_events() if e["active"]]
if not events:
    st.warning("No event is currently on sale. Create one in **Events** and keep it active.")
    st.stop()

event_labels = {e["event_id"]: f"#{e['event_id']} {e['name']} · {e['price_eth']} ETH" for e in events}
event_id = st.selectbox("Select event", list(event_labels), format_func=event_labels.get)
event = api.get_event(event_id)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Ticket price", f"{event['price_eth']} ETH")
m2.metric("Tickets left", event["remaining"])
m3.metric("Limit per wallet", event["wallet_limit"])
m4.metric("Show time (UTC)", event["event_time_str"][:10])

buyer = account_select("Buying account", "buy_account", "buyerA")
quantity = st.number_input("Quantity", min_value=1, max_value=10, value=1, step=1)

already = api.purchased_count(event_id, buyer)
st.caption(
    f"On-chain `purchasedByWallet`: {already} / {event['wallet_limit']} purchased. "
    "Resale purchases do not count toward this limit."
)

allowed, reason = api.can_purchase(event_id, buyer, int(quantity))
if allowed:
    st.success(f"On-chain pre-check passed: {reason} · payable {event['price_eth'] * quantity:.4f} ETH")
else:
    st.error(f"On-chain pre-check failed: {reason}")

col_a, col_b = st.columns([1, 2])
if col_a.button("Buy now", type="primary", use_container_width=True):
    result = api.buy_ticket(event_id, buyer, int(quantity))
    st.session_state["buy_result"] = result.to_dict()

if "buy_result" in st.session_state:
    stored = st.session_state["buy_result"]
    tx_box(stored)
    if stored.get("ok"):
        first = stored["extra"].get("first_token_id")
        last = stored["extra"].get("last_token_id")
        st.markdown("##### Mint result (read straight from chain)")
        owner = api.get_ticket_owner(first)
        st.markdown(
            f'<div class="card card-ok">tokenId <b>{first}</b>'
            f'{f" – {last}" if last and last != first else ""} minted<br>'
            f'<span class="mono">ownerOf({first}) = {owner}</span><br>'
            f'{"✅ matches the buying account" if owner.lower() == api.get_accounts()[buyer].lower() else "❌ does NOT match the buying account"}'
            f"</div>",
            unsafe_allow_html=True,
        )

st.divider()
st.markdown("##### Failure scenarios")
st.caption("The buttons below deliberately trigger contract `require`s — to show why the rules cannot live only in the frontend.")
f1, f2 = st.columns(2)
if f1.button("Over the wallet limit", use_container_width=True):
    sn = api.get_next_token_id()
    st.session_state["buy_fail"] = api.buy_ticket(event_id, buyer, max(int(event["wallet_limit"]), 3)).to_dict()
    st.session_state["buy_fail_note"] = f"Attempting to buy {max(int(event['wallet_limit']), 3)} tickets (nextTokenId is still {sn})"
if f2.button("Buy after sell-out (insufficient stock)", use_container_width=True):
    st.session_state["buy_fail"] = api.buy_ticket(event_id, "attacker", int(event["remaining"]) + 1).to_dict()
    st.session_state["buy_fail_note"] = "Attempt to buy more than the remaining stock in one transaction"

if "buy_fail" in st.session_state:
    st.caption(st.session_state.get("buy_fail_note", ""))
    tx_box(st.session_state["buy_fail"])
    st.caption(f"After the revert, nextTokenId is still {api.get_next_token_id()} — no state changed.")
