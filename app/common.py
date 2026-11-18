"""Shared Streamlit page layer: path bootstrap, styling, account selection, transaction result rendering."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "app")):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend import ticket_api as api  # noqa: E402
from backend.chain import TxResult  # noqa: E402

ROLE_LABELS = {
    "organizer": "Organizer",
    "buyerA": "Buyer A",
    "buyerB": "Buyer B",
    "verifier": "Verifier",
    "attacker": "Attacker",
    "deployer": "Deployer",
}

CSS = """
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1180px;}
h1 {font-size: 1.9rem !important;}
h2 {font-size: 1.35rem !important; margin-top: 1.4rem !important;}
h3 {font-size: 1.1rem !important;}
div[data-testid="stMetric"] {
    background: #f7f9fc; border: 1px solid #e3e8ef; border-radius: 12px;
    padding: 12px 16px;
}
div[data-testid="stMetricLabel"] p {font-size: 0.82rem; color: #5b6577;}
div[data-testid="stMetricValue"] {font-size: 1.3rem;}
.mono {font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.82rem;}
.card {
    border: 1px solid #e3e8ef; border-radius: 12px; padding: 14px 18px;
    background: #ffffff; margin-bottom: 10px;
}
.card-ok {border-left: 4px solid #16a34a;}
.card-fail {border-left: 4px solid #dc2626;}
.card-warn {border-left: 4px solid #d97706;}
.tag {
    display: inline-block; padding: 1px 8px; border-radius: 999px;
    font-size: 0.75rem; font-weight: 600;
}
.tag-ok {background: #dcfce7; color: #166534;}
.tag-fail {background: #fee2e2; color: #991b1b;}
.tag-warn {background: #fef3c7; color: #92400e;}
.hint {color: #5b6577; font-size: 0.88rem;}
/* Hide Streamlit's built-in Deploy button and menu during screenshots/demos so they are not mistaken for business features */
[data-testid="stAppDeployButton"] {display: none !important;}
[data-testid="stToolbar"] {display: none !important;}
</style>
"""


NAV = [
    ("app.py", "Overview", "🏠"),
    ("pages/1_activity.py", "Events", "🎪"),
    ("pages/2_buy.py", "Buy Tickets", "🛒"),
    ("pages/3_my_tickets.py", "My Tickets", "🎟️"),
    ("pages/4_resale.py", "Resale Market", "🔁"),
    ("pages/5_checkin.py", "Staff Check-in", "✅"),
]


def init_page() -> None:
    """Called at the start of every page: page config + styles."""
    st.set_page_config(
        page_title="FTEC5520 Anti-Scalping Ticketing",
        page_icon="🎫",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CSS, unsafe_allow_html=True)


def sidebar_nav() -> None:
    """Custom sidebar navigation: more controllable than the default multipage nav (English labels + icons + order)."""
    with st.sidebar:
        for path, label, icon in NAV:
            st.page_link(path, label=label, icon=icon)


def header(title: str, subtitle: str = "") -> None:
    st.title(title)
    if subtitle:
        st.markdown(f'<div class="hint">{subtitle}</div>', unsafe_allow_html=True)
    st.divider()


def chain_guard() -> dict:
    """Confirm the node and contract are available before the page loads; otherwise show a clear message and stop rendering."""
    status = api.get_chain_status()
    if not status["connected"]:
        st.error(
            "Cannot reach the private-chain node. "
            "Start it from the project root: `./blockchain/start_node.sh`"
        )
        st.code(status["rpc_url"], language="text")
        st.stop()
    if not status["contract_address"]:
        st.error("No contract deployed yet. Run `python backend/deploy.py`.")
        st.stop()
    return status


def account_select(label: str, key: str, default: str = "buyerA", roles: list[str] | None = None,
                   use_url_preset: bool = True) -> str:
    """Account dropdown. Supports ?account=buyerB deep-link preselection (handy for demos/screenshots
    that need to land on a specific account directly).

    `use_url_preset=False` is for dropdowns where the role *is* the identity (for example the
    Verifier account on the check-in page): otherwise a stale `?account=buyerA` in the URL would
    silently replace the verifier with a buyer, the page would show "not authorized", and it
    would look like a permissions bug.
    """
    roles = roles or ["organizer", "buyerA", "buyerB", "verifier", "attacker", "deployer"]
    if use_url_preset and key not in st.session_state:
        preset = st.query_params.get("account")
        if preset in roles:
            st.session_state[key] = preset
    return st.selectbox(
        label,
        options=roles,
        index=roles.index(default) if default in roles else 0,
        format_func=lambda r: f"{ROLE_LABELS.get(r, r)} · {short(api.get_accounts().get(r, ''))}",
        key=key,
    )


def short(address: str | None, head: int = 6, tail: int = 4) -> str:
    if not address:
        return "—"
    return f"{address[:head]}…{address[-tail:]}"


def tx_box(result: TxResult | dict, success_hint: str = "") -> None:
    """Render a transaction result consistently: on success show tx/block/gas, on failure show the revert reason."""
    data = result.to_dict() if isinstance(result, TxResult) else result
    if data.get("ok"):
        st.markdown(
            f'<div class="card card-ok"><span class="tag tag-ok">TX SUCCESS</span> '
            f'<b>{data.get("function")}</b>{(" · " + success_hint) if success_hint else ""}'
            f'<div class="mono">tx: {data.get("tx_hash")}<br>block: {data.get("block_number")}'
            f' · gas: {data.get("gas_used")}</div></div>',
            unsafe_allow_html=True,
        )
        extra = data.get("extra") or {}
        if extra:
            st.caption(" · ".join(f"{k}={v}" for k, v in extra.items()))
    else:
        st.markdown(
            f'<div class="card card-fail"><span class="tag tag-fail">REVERTED</span> '
            f'<b>{data.get("function")}</b>'
            f'<div class="mono">reason: {data.get("error")}</div></div>',
            unsafe_allow_html=True,
        )


def status_pill(ok: bool, text_ok: str, text_fail: str) -> str:
    cls, text = ("tag-ok", text_ok) if ok else ("tag-fail", text_fail)
    return f'<span class="tag {cls}">{text}</span>'


def sidebar_status() -> None:
    status = api.get_chain_status()
    with st.sidebar:
        st.markdown("### Chain status")
        if status["connected"]:
            st.markdown(
                f'<span class="tag tag-ok">node online</span> chainId {status["chain_id"]}',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<span class="tag tag-fail">node offline</span>', unsafe_allow_html=True)
        st.caption(f"block {status['block_number']}")
        st.caption(f"RPC {status['rpc_url']}")
        st.caption(f"Contract {short(status['contract_address'], 8, 6)}")
        st.divider()
        st.caption("FTEC5520 · Anti-Scalping Ticket System")
