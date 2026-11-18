"""Resale market page: list, cancel and buy resale tickets, and show the dynamic price cap."""

from __future__ import annotations

import sys
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

header(
    "Resale Market (Controlled)",
    "Wallet-to-wallet transfers are disabled by the contract. The only legal ownership change is "
    "listForResale → buyResale, bounded by the dynamic price cap and the resale-count limit.",
)

st.markdown("##### Currently listed")
listed = api.listed_tickets()
if listed:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "tokenId": t["token_id"],
                    "Event": t["event_name"],
                    "Face value (ETH)": t["original_price_eth"],
                    "Listing price (ETH)": t["listing_price_eth"],
                    "Dynamic cap (ETH)": t["max_resale_price_eth"],
                    "Resales": f"{t['resale_count']}/3",
                    "Seller": short(t["owner"]),
                }
                for t in listed
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
else:
    st.info("Nothing is listed right now.")

st.divider()
left, right = st.columns(2)

with left:
    st.markdown("##### List a ticket for resale")
    seller = account_select("Seller account", "resale_seller", "buyerA")
    my_tokens = [t for t in api.tokens_of(api.get_accounts()[seller]) if not api.get_ticket(t)["used"]]
    if not my_tokens:
        st.warning("This account has no transferable tickets.")
    else:
        token_labels = {t: f"#{t} · {api.get_ticket(t)['event_name']} · face {api.get_ticket(t)['original_price_eth']} ETH"
                        for t in my_tokens}
        token_id = st.selectbox("Select a ticket to sell", list(token_labels), format_func=token_labels.get)
        cap = api.get_max_resale_price(token_id)
        ticket = api.get_ticket(token_id)
        st.caption(
            f"Face value {ticket['original_price_eth']} ETH · current dynamic cap "
            f"**{cap['max_price_eth']} ETH** (>7 days to the show: 120%, ≤7 days: 100%)"
            f" · resold {ticket['resale_count']}/3 times"
        )
        default_price = cap["max_price_eth"] or ticket["original_price_eth"]
        price = st.number_input("Listing price (ETH)", min_value=0.01, value=float(default_price), step=0.1, format="%.2f")
        b1, b2 = st.columns(2)
        if b1.button("List at this price", type="primary", use_container_width=True):
            st.session_state["list_result"] = api.list_ticket(token_id, price, seller).to_dict()
        if b2.button("Over-price listing (expect rejection)", use_container_width=True):
            over = round((cap["max_price_eth"] or ticket["original_price_eth"]) * 1.25, 2)
            st.session_state["list_result"] = api.list_ticket(token_id, over, seller).to_dict()
            st.session_state["list_result"]["_note"] = f"Attempting to list at {over} ETH, above the cap"
        if "list_result" in st.session_state:
            note = st.session_state["list_result"].pop("_note", None)
            if note:
                st.caption(note)
            tx_box(st.session_state["list_result"])

with right:
    st.markdown("##### Buy a resale ticket")
    buyer = account_select("Buyer account", "resale_buyer", "buyerB")
    if listed:
        choices = {t["token_id"]: f"#{t['token_id']} · {t['listing_price_eth']} ETH · seller {short(t['owner'])}"
                   for t in listed}
        buy_token = st.selectbox("Select a listed ticket", list(choices), format_func=choices.get)
        selected = next(t for t in listed if t["token_id"] == buy_token)
        st.caption(
            f"Payable {selected['listing_price_eth']} ETH; the platform takes a 5% fee "
            f"({selected['listing_price_eth'] * 0.05:.4f} ETH) and the rest goes to the seller."
        )
        if st.button("Buy this ticket", type="primary", use_container_width=True):
            st.session_state["buy_resale_result"] = api.buy_resale(buy_token, buyer).to_dict()
    else:
        st.caption("No tickets available for purchase.")
    if "buy_resale_result" in st.session_state:
        stored = st.session_state["buy_resale_result"]
        tx_box(stored)
        if stored.get("ok"):
            st.caption(f"On-chain state after settlement: ownerOf = {api.get_ticket_owner(buy_token)} "
                       f"(expected buyer {short(api.get_accounts()[buyer])})")

st.divider()
st.markdown("##### Cancel a listing")
if listed:
    cancel_token = st.selectbox("Select a listing to cancel", [t["token_id"] for t in listed], key="cancel_token")
    owner_role = next((r for r, a in api.get_accounts().items()
                       if a.lower() == api.get_ticket(cancel_token)["owner"].lower()), None)
    st.caption(f"Listed by: {owner_role or api.get_ticket(cancel_token)['owner']}")
    if owner_role and st.button("Cancel listing", use_container_width=False):
        tx_box(api.cancel_listing(cancel_token, owner_role))
else:
    st.caption("No tickets are listed.")

with st.expander("Contract functions and rules on this page"):
    st.code(
        "listForResale(tokenId, price)   // owner only; price <= getMaxResalePrice()\n"
        "buyResale(tokenId) payable      // payment must equal the listing price; 5% platform fee; resaleCount +1\n"
        "cancelListing(tokenId)          // owner only\n"
        "transferFrom / safeTransferFrom // overridden, always revert",
        language="solidity",
    )
