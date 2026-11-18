"""验票页：校验签名二维码 + 链上状态，再由授权 verifier 核销。"""

from __future__ import annotations

import json
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
from qr_utils import parse_payload, verify_payload  # noqa: E402

init_page()
sidebar_nav()
sidebar_status()
chain_guard()

header(
    "Staff Check-in",
    "Paste the holder's QR payload → verify the signature locally and cross-check on-chain state → "
    "an authorized verifier calls checkIn.",
)

verifier = account_select("Verifier account", "checkin_verifier", "verifier", use_url_preset=False)
verifier_addr = api.get_accounts()[verifier]
authorized = api.is_verifier(verifier_addr)
badge = (
    '<span class="tag tag-ok">authorized verifier</span>'
    if authorized
    else '<span class="tag tag-fail">not authorized</span>'
)
st.markdown(f"On-chain authorization for `{short(verifier_addr)}`: {badge}", unsafe_allow_html=True)
if not authorized:
    st.caption("The contract owner can authorize an account in the section below.")

st.divider()
st.markdown("##### Step 1 — read the QR payload")
raw = st.text_area(
    "QR payload (JSON)",
    value=st.session_state.get("verify_input", ""),
    height=180,
    placeholder='{"v":1,"token_id":2,"holder":"0x...","nonce":"...","issued_at":...,"expires_at":...,"sig":"0x..."}',
)

col1, col2 = st.columns([1, 3])
if col1.button("Verify ticket", type="primary", use_container_width=True):
    try:
        payload = parse_payload(raw)
        ticket = api.get_ticket(int(payload["token_id"]))
        st.session_state["verify_result"] = verify_payload(payload, ticket)
    except Exception as exc:  # noqa: BLE001
        st.session_state["verify_result"] = {"ok": False, "error": str(exc), "checks": []}
col2.caption("Checks: payload version / signature belongs to the holder / not expired / matches on-chain ownerOf / not already used.")

result = st.session_state.get("verify_result")
if result:
    if result.get("error"):
        st.error(f"Cannot parse the QR payload: {result['error']}")
    else:
        checks = result["checks"]
        st.dataframe(
            pd.DataFrame(
                [
                    {"Check": c["check"], "Result": "PASS" if c["ok"] else "FAIL", "Detail": c["detail"]}
                    for c in checks
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
        if result["ok"]:
            ticket = result["ticket"]
            st.success(
                f"Ticket valid: tokenId {ticket['token_id']}, on-chain owner {short(ticket['owner'])}, "
                f"event \"{ticket['event_name']}\""
            )
        else:
            st.error("Ticket verification failed: at least one check did not pass — entry denied.")

st.divider()
st.markdown("##### Step 2 — check in on-chain")
if not result or not result.get("ok"):
    st.caption("Verify the ticket first.")
else:
    token_id = int(result["payload"]["token_id"])
    ticket = api.get_ticket(token_id)
    last = st.session_state.get("checkin_result") or {}
    # 本次运行里刚核销成功时，链上状态还没来得及在页面顶部刷新，这里合并一下
    used_now = bool(ticket["used"]) or bool(last.get("ok"))
    c1, c2 = st.columns(2)
    c1.metric("tokenId", token_id)
    c2.metric("used", str(used_now))
    if c1.button("Check in (first time)", type="primary", use_container_width=True, disabled=used_now):
        result_tx = api.check_in(token_id, verifier)
        st.session_state["checkin_result"] = result_tx.to_dict()
        if result_tx.ok:
            st.rerun()  # 重新读一遍链上状态，used 指标与按钮状态立即同步
    if c2.button("Check in again (should fail)", use_container_width=True):
        st.session_state["checkin_result"] = api.check_in(token_id, verifier).to_dict()
    if "checkin_result" in st.session_state:
        tx_box(st.session_state["checkin_result"])
        st.caption(f"used on-chain after check-in = {api.get_ticket(token_id)['used']}")

st.divider()
with st.expander("Authorize / revoke verifier (contract owner only)"):
    c1, c2 = st.columns([2, 1])
    who = c1.selectbox("Select account", ["verifier", "attacker", "buyerA", "buyerB", "organizer"],
                       format_func=lambda r: f"{r} · {short(api.get_accounts()[r])}")
    if c2.button("Toggle authorization", use_container_width=True):
        current = api.is_verifier(api.get_accounts()[who])
        tx_box(api.set_verifier(who, not current), f"verifier[{who}] = {not current}")

with st.expander("Failure-scenario checklist (T14–T17)"):
    st.markdown(
        """
| Scenario | How | Expected |
|---|---|---|
| Expired QR | Set validity to 30 s on **My Tickets**, wait, then verify | "Not expired" = FAIL |
| Forged signature | Hand-edit token_id or holder in the payload | "Signature matches holder" = FAIL |
| Previous owner reuses | Generate the QR with the pre-resale owner | "Matches on-chain ownerOf" = FAIL |
| Double check-in | Press "Check in (first time)" twice on the same ticket | Contract reverts: Ticket already used |
| Unauthorized check-in | Switch the verifier to `attacker` and check in | Contract reverts: Not an authorized verifier |
"""
    )
