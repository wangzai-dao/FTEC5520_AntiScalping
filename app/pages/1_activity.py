"""Event management page: the organizer creates events, toggles ticket sales/presale, manages the whitelist and settles ticket revenue."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
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

header("Events", "Organizers create a concert, set price / supply / per-wallet limit, and control the presale whitelist.")

organizer = account_select("Acting account (organizer)", "evt_organizer", "organizer")
st.caption(f"Organizer recorded on-chain for new events: `{api.get_accounts()[organizer]}`")

with st.form("create_event_form"):
    st.markdown("##### Create event")
    col1, col2, col3 = st.columns(3)
    name = col1.text_input("Event name", value="FTEC5520 Live Concert 2026")
    price = col2.number_input("Ticket price (ETH)", min_value=0.01, value=1.0, step=0.1, format="%.2f")
    supply = col3.number_input("Total supply", min_value=1, value=100, step=10)

    col4, col5, col6 = st.columns(3)
    days_ahead = col4.number_input("Days until the show", min_value=1, value=10, step=1,
                                   help="Drives the dynamic resale cap: >7 days → 120% of face value, ≤7 days → 100%")
    wallet_limit = col5.number_input("Limit per wallet", min_value=1, value=2, step=1)
    presale = col6.checkbox("Enable presale (whitelist only)", value=False)

    submitted = st.form_submit_button("Create event on-chain", type="primary", use_container_width=True)

if submitted:
    event_time = datetime.now(timezone.utc) + timedelta(days=int(days_ahead))
    result = api.create_event(
        name=name,
        price_eth=price,
        max_supply=int(supply),
        event_time=event_time,
        wallet_limit=int(wallet_limit),
        presale_active=bool(presale),
        organizer=organizer,
    )
    if result.ok:
        st.session_state["last_event_id"] = result.extra.get("event_id", api.get_next_event_id() - 1)
    tx_box(result, "event written to chain")

st.divider()
st.markdown("##### Existing events")
events = api.list_events()
if not events:
    st.info("No events on-chain yet. Create one with the form above.")
    st.stop()

df = pd.DataFrame(
    [
        {
            "eventId": e["event_id"],
            "Event": e["name"],
            "Price (ETH)": e["price_eth"],
            "Sold / Supply": f"{e['sold']}/{e['max_supply']}",
            "Remaining": e["remaining"],
            "Limit": e["wallet_limit"],
            "Show time (UTC)": e["event_time_str"],
            "On sale": "✅" if e["active"] else "⏸",
            "Presale": "🔒" if e["presale_active"] else "—",
            "Organizer": short(e["organizer"]),
        }
        for e in events
    ]
)
st.dataframe(df, hide_index=True, use_container_width=True)

st.markdown("##### Event switches")
c1, c2, c3 = st.columns([1, 1, 2])
event_ids = [e["event_id"] for e in events]
target = c1.selectbox("Select event", event_ids, format_func=lambda i: f"#{i} {api.get_event(i)['name']}")
if c2.button("Toggle on-sale status", use_container_width=True):
    current = api.get_event(target)["active"]
    tx_box(api.set_event_active(target, not current, organizer), f"active={not current}")
if c3.button("Toggle presale (whitelist only)", use_container_width=True):
    current = api.get_event(target)["presale_active"]
    tx_box(api.set_presale_active(target, not current, organizer), f"presale={not current}")

st.markdown("##### Presale whitelist")
whitelist_text = st.text_area(
    "One entry per line (address or role name, e.g. buyerA)",
    value="buyerA\nbuyerB",
    height=90,
    key="whitelist_text",
)
w1, w2 = st.columns(2)
if w1.button("Add to whitelist", type="primary", use_container_width=True):
    accounts = [line.strip() for line in whitelist_text.splitlines() if line.strip()]
    try:
        tx_box(api.set_whitelist(target, accounts, True, organizer), f"{len(accounts)} addresses")
    except ValueError as exc:
        st.error(str(exc))
if w2.button("Remove from whitelist", use_container_width=True):
    accounts = [line.strip() for line in whitelist_text.splitlines() if line.strip()]
    try:
        tx_box(api.set_whitelist(target, accounts, False, organizer), f"{len(accounts)} addresses")
    except ValueError as exc:
        st.error(str(exc))

st.divider()
st.markdown("##### Settlement (Pull Payment)")
st.caption(
    "The contract never pushes funds. Primary-market revenue accrues to the organizer's "
    "pendingProceeds; 5% of every resale accrues to the contract owner's pendingPlatformFees. "
    "Both must be withdrawn explicitly."
)

settle = account_select("Settlement account", "evt_settle", organizer)
s1, s2, s3 = st.columns(3)
s1.metric("Pending proceeds (ETH)", f"{api.pending_proceeds(settle):.4f}",
          help="pendingProceeds[account]: accumulated primary-market revenue")
s2.metric("Pending platform fees (ETH)", f"{api.pending_platform_fees(settle):.4f}",
          help="pendingPlatformFees[account]: 5% of each resale, withdrawable by the contract owner only")
s3.metric("Account balance (ETH)", f"{api.get_balance_eth(settle):.4f}")

d1, d2 = st.columns(2)
if d1.button("Withdraw proceeds", type="primary", use_container_width=True):
    result = api.withdraw_proceeds(settle)
    st.session_state["settle_result"] = result.to_dict()
    if result.ok:
        st.rerun()  # re-read the on-chain balance so the three metrics update immediately
if d2.button("Withdraw platform fees", use_container_width=True):
    result = api.withdraw_platform_fees(settle)
    st.session_state["settle_result"] = result.to_dict()
    if result.ok:
        st.rerun()
if "settle_result" in st.session_state:
    tx_box(st.session_state["settle_result"], "funds received")
    st.caption("Switch the settlement account to a non-owner (e.g. buyerA) and try withdrawing platform fees — the contract will reject it.")

with st.expander("Contract functions used on this page"):
    st.code(
        "createEvent(name, price, maxSupply, eventTime, walletLimit, presaleActive)\n"
        "setEventActive(eventId, active)      // organizer or owner only\n"
        "setPresaleActive(eventId, presaleActive)\n"
        "setWhitelistBatch(eventId, accounts[], allowed)\n"
        "withdrawProceeds()                   // pull pendingProceeds of msg.sender\n"
        "withdrawPlatformFees()               // owner only, pull platform fees",
        language="solidity",
    )
    st.caption(
        "Access control: `onlyEventManager(eventId)` = the event organizer or the contract owner; "
        "`withdrawPlatformFees` is `onlyOwner` and still only pays out the caller's own balance."
    )
