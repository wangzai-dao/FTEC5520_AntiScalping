"""我的门票页：查看持仓、链上状态，并生成持票人签名的短时二维码。"""

from __future__ import annotations

import sys
import time
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
)
from qr_utils import DEFAULT_TTL, create_ticket_qr, make_qr_pil, payload_to_text  # noqa: E402

init_page()
sidebar_nav()
sidebar_status()
chain_guard()

header("My Tickets", "Reads the NFT tickets held by the selected account — owner, resale count, check-in status — and issues a short-lived signed QR code.")

holder = account_select("Signed-in account", "my_tickets_holder", "buyerA")
address = api.get_accounts()[holder]
st.caption(f"Wallet address: `{address}` (this classroom demo signs server-side in Python; a production build would keep the key in the user's own wallet)")

token_ids = api.tokens_of(address)
# 未使用的排在前面，演示时默认选中一张可以生成有效二维码的票
token_ids = sorted(token_ids, key=lambda t: (api.get_ticket(t) or {}).get("used", False))
if not token_ids:
    st.info("This account holds no tickets. Buy one in **Buy Tickets**, or check that the right account is selected.")
    st.stop()

options = {}
for token_id in token_ids:
    ticket = api.get_ticket(token_id)
    if ticket:
        flag = "checked in" if ticket["used"] else ("listed" if ticket["is_listed"] else "unused")
        options[token_id] = f"#{token_id} · {ticket['event_name']} · {flag}"

token_id = st.selectbox("Select ticket", list(options), format_func=options.get)
ticket = api.get_ticket(token_id)

c1, c2, c3, c4 = st.columns(4)
c1.metric("tokenId", ticket["token_id"])
c2.metric("Event", f"#{ticket['event_id']}")
c3.metric("Resales", f"{ticket['resale_count']} / {ticket['resale_limit']}")
c4.metric("Check-in status", "used" if ticket["used"] else "unused")

st.markdown(
    f"""
| Field | Value read from chain |
|---|---|
| ownerOf({token_id}) | `{ticket['owner']}` |
| Face value | {ticket['original_price_eth']} ETH |
| Current listing | {"yes · " + str(ticket["listing_price_eth"]) + " ETH" if ticket["is_listed"] else "no"} |
| Dynamic resale cap | {ticket['max_resale_price_eth']} ETH |
| used | {ticket["used"]} |
"""
)

st.divider()
st.markdown("##### Issue check-in QR code")
st.caption(
    "QR content = {tokenId, holder, random nonce, issued_at, expires_at, holder signature}. "
    "The check-in side rebuilds the signed message, recovers the signer, then cross-checks it "
    "against on-chain ownerOf / used."
)
ttl = st.slider("QR validity (seconds)", min_value=30, max_value=600, value=DEFAULT_TTL, step=30)

if ticket["used"]:
    st.warning("This ticket has already been checked in, so the generated QR code will be rejected by the check-in page — that is expected.")

if st.button("Generate signed QR code", type="primary"):
    payload = create_ticket_qr(token_id, address, api.signing_key(holder), ttl=int(ttl))
    st.session_state["qr_payload"] = payload
    st.session_state["qr_holder"] = holder
    st.session_state["qr_token"] = token_id

if "qr_payload" in st.session_state:
    payload = st.session_state["qr_payload"]
    left, right = st.columns([1, 1])
    with left:
        st.image(make_qr_pil(payload), caption=f"tokenId {payload['token_id']} · holder signature", width=320)
    with right:
        remaining = payload["expires_at"] - int(time.time())
        st.success(f"Valid for {max(remaining, 0)} more seconds (verification always fails after expiry)")
        st.code(payload_to_text(payload), language="json", wrap_lines=True)
        st.caption("Copy the JSON above into the **Staff Check-in** page to verify it.")
        st.download_button(
            "Download QR JSON",
            data=payload_to_text(payload),
            file_name=f"ticket_{payload['token_id']}_qr.json",
            mime="application/json",
        )
        if st.button("Send to check-in page", use_container_width=True):
            st.session_state["verify_input"] = payload_to_text(payload)
            st.switch_page("pages/5_checkin.py")
