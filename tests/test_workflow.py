#!/usr/bin/env python
"""Member 5 deliverable — end-to-end / negative / adversarial test suite.

Covers the 18 scenarios required by the project brief (T01–T18) and adds:
  * adversarial tests that bypass the front end and call the contract directly
    with Web3.py — proof that the rules do not live in the UI layer;
  * boundary cases (exactly 7 days, sold out, re-listing a used ticket,
    self-dealing, wrong payment amount, operations after the event starts);
  * real on-chain evidence for rejected transactions — every negative case is
    also forced on chain with a fixed gas limit so we obtain a status=0 receipt
    and the gas it actually burned.

Design rules
------------
1. Every case creates its own event, so cases never share state and the suite
   can be re-run without redeploying the contract (only new ids are created).
2. Judging follows the brief: a case that is expected to fail only counts as
   PASS when the contract really rejects it.
3. Each case records expected / actual / PASS-FAIL / tx_hash / block / gas /
   revert reason.
4. Negative cases keep two pieces of evidence:
   - the pre-check path (estimate_gas catches the revert, no tx, no gas spent);
   - the forced on-chain path (fixed gas, status=0 receipt, gas is charged).
   Together they support the "rules live on chain / failures still cost gas"
   argument in the report.

Outputs
-------
    results/test_results.csv       full result table (UTF-8 BOM, Excel-ready)
    results/test_evidence.json     complete evidence + environment + summary
    results/test_environment.json  environment snapshot
    results/gas_data.csv           raw gas data for the charts

Usage
-----
    ./blockchain/start_node.sh             # start the private chain
    python backend/deploy.py               # deploy (first run or after a reset)
    .venv/bin/python tests/test_workflow.py
"""

from __future__ import annotations

import csv
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eth_account import Account  # noqa: E402

from app import qr_utils  # noqa: E402
from backend import ticket_api as api  # noqa: E402
from backend.chain import TxResult, clean_revert, hx  # noqa: E402

RESULTS = ROOT / "results"

COLUMNS = [
    "test_id", "module", "owner", "scenario", "actor", "input", "expected", "actual",
    "verdict", "tx_hash", "block_number", "gas_used", "tx_status", "revert_reason",
    "screenshot", "kind", "note",
]

ROWS: list[dict] = []
GAS: list[dict] = []
STEPS: list[dict] = []
START_TS = datetime.now(timezone.utc)


# ----------------------------------------------------------------------
# Recording and judging
# ----------------------------------------------------------------------
def record(
    test_id: str,
    module: str,
    owner: str,
    scenario: str,
    actor: str,
    input_desc: str,
    expected: str,
    actual: str,
    verdict: str,
    *,
    tx: dict | None = None,
    revert_reason: str = "",
    screenshot: str = "",
    kind: str = "normal",
    note: str = "",
) -> dict:
    tx = tx or {}
    row = {
        "test_id": test_id,
        "module": module,
        "owner": owner,
        "scenario": scenario,
        "actor": actor,
        "input": input_desc,
        "expected": expected,
        "actual": actual,
        "verdict": verdict,
        "tx_hash": tx.get("tx_hash") or "",
        "block_number": tx.get("block_number") or "",
        "gas_used": tx.get("gas_used") or "",
        "tx_status": "" if tx.get("status") is None else tx.get("status"),
        "revert_reason": revert_reason,
        "screenshot": screenshot,
        "kind": kind,
        "note": note,
    }
    ROWS.append(row)
    icon = {"PASS": "OK  ", "FAIL": "FAIL", "DEVIATION": "DEV "}.get(verdict, "    ")
    print(
        f"[{icon}] {test_id:<7} {scenario[:44]:<46} "
        f"tx={row['tx_hash'][:12] + '...' if row['tx_hash'] else '-':<16} "
        f"gas={row['gas_used'] or '-':<8}"
        + (f" reason={revert_reason}" if revert_reason else "")
    )
    return row


def case_ok(test_id, module, owner, scenario, actor, input_desc, result: TxResult | dict,
            expected="success", checks: dict | None = None, screenshot="", note="", kind="normal"):
    """Positive case: the call must succeed and the on-chain assertions must hold."""
    data = result.to_dict() if isinstance(result, TxResult) else dict(result)
    ok = bool(data.get("ok"))
    failed_checks = {k: v for k, v in (checks or {}).items() if not v}
    verdict = "PASS" if ok and not failed_checks else "FAIL"
    actual = "success"
    if not ok:
        actual = f"rejected: {data.get('error')}"
    elif failed_checks:
        actual = f"tx succeeded but state assertions failed: {', '.join(failed_checks)}"
    return record(
        test_id, module, owner, scenario, actor, input_desc, expected, actual, verdict,
        tx=data, revert_reason="" if ok else (data.get("error") or ""),
        screenshot=screenshot, kind=kind,
        note=note + ("; " + json.dumps({k: bool(v) for k, v in checks.items()}, ensure_ascii=False)
                     if checks else ""),
    )


def case_reject(test_id, module, owner, scenario, actor, input_desc, result, expected_reason: str,
                tx: dict | None = None, expected="rejected", checks: dict | None = None,
                screenshot="", note="", kind="negative"):
    """Negative case: the call must be rejected with the expected revert reason."""
    data = result.to_dict() if isinstance(result, TxResult) else dict(result)
    ok = bool(data.get("ok"))
    reason = data.get("error") or ""
    reason_hit = expected_reason.lower() in reason.lower() if expected_reason else True
    failed_checks = {k: v for k, v in (checks or {}).items() if not v}
    verdict = "PASS" if (not ok and reason_hit and not failed_checks) else "FAIL"
    if ok:
        actual = "tx unexpectedly succeeded - the rule did not fire"
    elif not reason_hit:
        actual = f"rejected but the reason differs: {reason}"
    elif failed_checks:
        actual = f"rejected but state assertions failed: {', '.join(failed_checks)}"
    else:
        actual = f"rejected: {reason}"
    # For negative cases prefer the receipt of the forced on-chain attempt.
    merged = {**(tx or {}), "tx_hash": (tx or {}).get("tx_hash") or data.get("tx_hash"),
              "block_number": (tx or {}).get("block_number") or data.get("block_number"),
              "gas_used": (tx or {}).get("gas_used") or data.get("gas_used")}
    if merged["tx_hash"]:
        try:
            receipt = api.get_receipt(merged["tx_hash"])
            if receipt.get("ok"):
                merged["status"] = receipt["status"]
                merged["gas_used"] = receipt["gas_used"]
                merged["block_number"] = receipt["block_number"]
        except Exception:  # noqa: BLE001  pre-check path has no tx
            pass
    return record(
        test_id, module, owner, scenario, actor, input_desc, expected, actual, verdict,
        tx=merged, revert_reason=reason, screenshot=screenshot, kind=kind,
        note=note + ("; " + json.dumps({k: bool(v) for k, v in checks.items()}, ensure_ascii=False)
                     if checks else ""),
    )


def case_deviation(test_id, module, owner, scenario, actor, input_desc, actual, note="",
                   expected="per the brief this should be rejected"):
    return record(test_id, module, owner, scenario, actor, input_desc,
                  expected, actual, "DEVIATION", note=note, kind="deviation")


# ----------------------------------------------------------------------
# Chain helpers
# ----------------------------------------------------------------------
def addr(role: str) -> str:
    return api.get_accounts()[role]


def contract():
    return api.chain().require_contract()


def wei(eth) -> int:
    return api.to_wei(eth)


def now() -> datetime:
    return datetime.now(timezone.utc)


def fresh_event(name: str, price, supply: int, days: float, limit: int,
                presale: bool = False) -> int:
    """Create a dedicated event and return its id (cases stay independent)."""
    r = api.create_event(name, price, supply, now() + timedelta(days=days), limit, presale, "organizer")
    if not r.ok:
        sys.exit(f"createEvent failed: {r.error}")
    _collect_gas("createEvent", r, "setup")
    return int(r.extra["event_id"])


def buy(event_id: int, role: str, qty: int = 1):
    """Primary purchase; returns (TxResult, first tokenId)."""
    r = api.buy_ticket(event_id, role, qty)
    token = int(r.extra["first_token_id"]) if r.ok else None
    return r, token


def precheck(fn, role: str, value: int = 0) -> str:
    """Read-only simulation: get the revert reason without sending a transaction."""
    try:
        fn.estimate_gas({"from": addr(role), "value": value})
        return ""
    except Exception as exc:  # noqa: BLE001
        return clean_revert(exc)


def force_send(fn, role: str, value: int = 0, gas: int = 500_000, tag: str = "revert") -> dict:
    """Bypass the backend wrapper and send with a fixed gas limit.

    Used to produce a real status=0 receipt: the rejection comes from the EVM,
    and the sender still pays for the gas.
    """
    chain = api.chain()
    w3 = chain.w3
    acct = Account.from_key(chain.settings.key(role))
    tx = fn.build_transaction({
        "from": acct.address,
        "value": value,
        "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
        "chainId": chain.settings.chain_id,
        "gas": gas,
        **chain._fee_fields(),
    })
    tx.pop("from", None)
    signed = Account.sign_transaction(tx, acct.key)
    raw = getattr(signed, "raw_transaction", None) or signed.raw_transaction
    tx_hash = w3.eth.send_raw_transaction(raw)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180, poll_latency=0.3)
    GAS.append({"operation": getattr(fn, "fn_name", "unknown"), "tag": tag,
                "tx_hash": hx(tx_hash), "gas_used": receipt.gasUsed, "status": receipt.status})
    return {
        "tx_hash": hx(tx_hash),
        "block_number": receipt.blockNumber,
        "gas_used": receipt.gasUsed,
        "status": receipt.status,
        "ok": receipt.status == 1,
        "error": "" if receipt.status == 1 else "execution reverted (status=0)",
    }


def _collect_gas(op: str, result: TxResult | dict, tag: str) -> None:
    data = result.to_dict() if isinstance(result, TxResult) else dict(result)
    if data.get("tx_hash") and data.get("gas_used"):
        GAS.append({"operation": op, "tag": tag, "tx_hash": data["tx_hash"],
                    "gas_used": int(data["gas_used"]), "status": data.get("status", 1)})


def balance(who: str) -> float:
    return api.get_balance_eth(who)


def pending_fee_wei(who: str = "deployer") -> int:
    return int(contract().functions.pendingPlatformFees(addr(who)).call())


# ----------------------------------------------------------------------
# Environment snapshot
# ----------------------------------------------------------------------
def environment() -> dict:
    status = api.get_chain_status()
    settings = api.get_settings()
    build = json.loads((ROOT / "contracts/build/ConcertTicket.json").read_text("utf-8"))
    try:
        lines = subprocess.run(
            [str(ROOT / "tools/geth"), "version"], capture_output=True, text=True, timeout=20
        ).stdout.splitlines()
        geth_version = next((ln.split(":", 1)[1].strip() for ln in lines
                             if ln.startswith("Version:")), lines[0] if lines else "unknown")
    except Exception:  # noqa: BLE001
        geth_version = "unknown"
    deploy_receipt = api.get_receipt(settings.deploy_tx) if settings.deploy_tx else {}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chain": {
            "rpc_url": settings.rpc_url,
            "chain_id": status.get("chain_id"),
            "block_number": status.get("block_number"),
            "network_name": status.get("network_name"),
            "geth_version": geth_version,
            "consensus": "Clique PoA (2 s block time, single node)",
        },
        "contract": {
            "address": api.get_contract_address(),
            "deploy_tx": settings.deploy_tx,
            "deploy_block": settings.deploy_block,
            "deploy_gas_used": deploy_receipt.get("gas_used"),
            "compiler": build.get("compiler"),
            "abi_items": len(build.get("abi", [])),
            "bytecode_bytes": (len(build.get("bytecode", "")) - 2) // 2,
            "deployed_bytes": (len(build.get("deployedBytecode", "")) - 2) // 2,
        },
        "python": {"version": platform.python_version(), "implementation": platform.python_implementation()},
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "accounts": api.get_accounts(),
        "balances_eth": {k: float(v) for k, v in (status.get("balances") or {}).items()},
    }


# ======================================================================
# Cases
# ======================================================================
def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def test_primary_market():
    """Member 2: event creation, permissions, presale whitelist, limits, stock."""
    section("Member 2 - primary market (T01-T06)")

    before_token = api.get_next_token_id()
    ev = fresh_event("T01 Anti-Scalping Live 2026", 1, 10, 10, 2)
    event = api.get_event(ev)
    case_ok(
        "T01", "M2 Primary market", "Member 2",
        "Organizer creates an event (1 ETH / 10 tickets / limit 2 / +10 days)", "organizer",
        f"createEvent(name, price=1 ETH, maxSupply=10, eventTime=+10d, walletLimit=2, presale=false) -> eventId={ev}",
        {"ok": event is not None},
        expected="success; eventId, stock and price readable",
        checks={
            "eventId returned": ev >= 1,
            "name stored": (event or {}).get("name") == "T01 Anti-Scalping Live 2026",
            "price is 1 ETH": (event or {}).get("price_eth") == 1.0,
            "supply is 10": (event or {}).get("max_supply") == 10,
            "wallet limit is 2": (event or {}).get("wallet_limit") == 2,
            "on sale by default": bool((event or {}).get("active")),
            "nothing sold yet": (event or {}).get("sold") == 0,
            "remaining is 10": api.remaining_supply(ev) == 10,
        },
        screenshot="02_events.png",
        note=f"nextTokenId before the event={before_token}; creating an event mints nothing, minting happens on purchase",
    )

    # T02 permissions: a non-organizer manages somebody else's event
    reject = api.set_event_active(ev, False, "attacker")
    tx = force_send(contract().functions.setEventActive(ev, False), "attacker", gas=120_000)
    case_reject(
        "T02", "M2 Primary market", "Member 2",
        "Non-organizer toggles another event's sale switch", "attacker",
        f"setEventActive({ev}, false) called by attacker",
        reject, "Not event manager", tx=tx,
        checks={"event still on sale": bool(api.get_event(ev)["active"])},
        note="setWhitelist is protected by the same onlyEventManager modifier",
    )
    whitelist_reject = api.set_whitelist(ev, "attacker", True, "attacker")
    STEPS.append({"step": "T02-whitelist", "ok": not whitelist_reject.ok,
                  "error": whitelist_reject.error})
    print(f"       + non-organizer writes the whitelist: {whitelist_reject.error}")

    # T02 deviation: createEvent is permissionless (Member 2's design)
    own = api.create_event("Attacker Owned Event", 0.1, 5, now() + timedelta(days=5), 1, False, "attacker")
    case_deviation(
        "T02b", "M2 Primary market", "Member 5",
        "Ordinary account creates its own event", "attacker",
        "createEvent(...) called by attacker",
        f"success: eventId={own.extra.get('event_id')}, attacker becomes that event's organizer"
        if own.ok else f"rejected: {own.error}",
        note="the contract lets anyone create an event (Member 2 handover doc s3.1); only that "
             "event's organizer can manage it, so ticketing rules are unaffected, but the report "
             "must discuss the fake-event risk",
    )

    # T03 / T04 presale whitelist
    ev_pre = fresh_event("T03 Presale Only Event", 0.8, 20, 14, 2, presale=True)
    wl = api.set_whitelist(ev_pre, ["buyerA"], True, "organizer")
    _collect_gas("setWhitelistBatch(1)", wl, "setup")
    r3, tok3 = buy(ev_pre, "buyerA", 1)
    _collect_gas("purchaseTickets(1)", r3, "T03")
    case_ok(
        "T03", "M2 Primary market", "Member 2", "Whitelisted wallet buys during presale", "buyerA",
        f"setWhitelist({ev_pre}, buyerA, true) -> purchaseTickets({ev_pre}, 1) value=0.8 ETH",
        r3, expected="success; ownerOf updated to buyerA",
        checks={"ownerOf == buyerA": tok3 is not None and api.get_ticket_owner(tok3) == addr("buyerA"),
                "ticket belongs to the event": api.get_ticket(tok3)["event_id"] == ev_pre,
                "one ticket sold": api.get_event(ev_pre)["sold"] == 1},
        screenshot="03_buy_tickets.png",
        note=f"minted tokenId={tok3}",
    )

    r4 = api.buy_ticket(ev_pre, "attacker", 1)
    tx4 = force_send(contract().functions.purchaseTickets(ev_pre, 1), "attacker", value=wei(0.8), gas=300_000)
    case_reject(
        "T04", "M2 Primary market", "Member 2", "Non-whitelisted wallet buys during presale", "attacker",
        f"purchaseTickets({ev_pre}, 1) value=0.8 ETH (attacker is not whitelisted)",
        r4, "Wallet is not whitelisted", tx=tx4,
        checks={"stock unchanged": api.get_event(ev_pre)["sold"] == 1},
        screenshot="03_buy_tickets.png",
    )

    # T05 wallet limit
    ev_lim = fresh_event("T05 Wallet Limit Event", 0.5, 10, 10, 2)
    r5a, _ = buy(ev_lim, "buyerA", 2)  # buys exactly the limit in one call
    _collect_gas("purchaseTickets(2)", r5a, "T05")
    case_ok("T05a", "M2 Primary market", "Member 2", "Buy 2 tickets in one transaction (the limit)", "buyerA",
            f"purchaseTickets({ev_lim}, 2) value=1.0 ETH", r5a,
            checks={"purchasedByWallet == 2": api.purchased_count(ev_lim, "buyerA") == 2},
            note="also serves as the batched-mint gas sample")
    r5b = api.buy_ticket(ev_lim, "buyerA", 1)
    tx5 = force_send(contract().functions.purchaseTickets(ev_lim, 1), "buyerA", value=wei(0.5), gas=300_000)
    case_reject(
        "T05b", "M2 Primary market", "Member 2", "Exceed the per-wallet limit (2 bought, 1 more)", "buyerA",
        f"purchaseTickets({ev_lim}, 1) value=0.5 ETH", r5b, "Wallet limit exceeded", tx=tx5,
        checks={"counter still 2": api.purchased_count(ev_lim, "buyerA") == 2},
        screenshot="03_buy_tickets.png",
    )

    # T06 sold out
    ev_sold = fresh_event("T06 Sold Out Event", 0.2, 1, 20, 1)
    r6a, _ = buy(ev_sold, "buyerB", 1)
    case_ok("T06a", "M2 Primary market", "Member 2", "The last ticket is sold", "buyerB",
            f"purchaseTickets({ev_sold}, 1) value=0.2 ETH", r6a,
            checks={"remaining is 0": api.remaining_supply(ev_sold) == 0})
    r6b = api.buy_ticket(ev_sold, "attacker", 1)
    tx6 = force_send(contract().functions.purchaseTickets(ev_sold, 1), "attacker", value=wei(0.2), gas=300_000)
    case_reject(
        "T06b", "M2 Primary market", "Member 2", "Purchase after the stock is sold out", "attacker",
        f"purchaseTickets({ev_sold}, 1) value=0.2 ETH", r6b, "Not enough tickets", tx=tx6,
        screenshot="03_buy_tickets.png",
    )

    # E04 wrong payment amount (extra case)
    ev_pay = fresh_event("E04 Wrong Payment Event", 0.3, 5, 10, 2)
    wrong = contract().functions.purchaseTickets(ev_pay, 1)
    reason = precheck(wrong, "attacker", value=wei(0.1))
    tx_pay = force_send(wrong, "attacker", value=wei(0.1), gas=200_000)
    case_reject(
        "E04", "M2 Primary market", "Member 5", "Payment differs from price x quantity", "attacker",
        f"purchaseTickets({ev_pay}, 1) value=0.1 ETH (0.3 ETH required)",
        {"ok": False, "error": reason}, "Incorrect ETH amount", tx=tx_pay,
        note="the contract enforces msg.value == price*quantity, so underpayment has no path",
    )


def test_anti_scalping():
    """Member 3: price cap, resale count, transfer bypass, check-in."""
    section("Member 3 - anti-scalping resale and check-in (T07-T12, T15-T17)")

    ev = fresh_event("T07 Resale Market Event", 1, 10, 10, 2)
    _, token = buy(ev, "buyerA", 1)
    fee_before = pending_fee_wei()  # 5% platform fee
    bal_before = balance("buyerA")

    # T08 over-price first, so the listing state stays clean for T07
    over = api.list_ticket(token, 1.3, "buyerA")
    tx8 = force_send(contract().functions.listForResale(token, wei(1.3)), "buyerA", gas=200_000)
    case_reject(
        "T08", "M3 Anti-scalping", "Member 3", "Listing price above the 120% cap", "buyerA",
        f"listForResale({token}, 1.3 ETH), original price 1 ETH, cap 1.2 ETH",
        over, "Price exceeds dynamic limit", tx=tx8,
        checks={"no listing created": not api.get_ticket(token)["is_listed"]},
        screenshot="05_resale_market.png",
    )

    cap = api.get_max_resale_price(token)
    case_ok("T08b", "M3 Anti-scalping", "Member 3", "Read the dynamic cap (10 days out -> 120%)", "read-only",
            f"getMaxResalePrice({token})", {"ok": True},
            expected="returns 1.2 ETH",
            checks={"cap = 1.2 ETH": cap.get("max_price_eth") == 1.2},
            note=f"returned {cap.get('max_price_eth')} ETH")

    # T12 non-owner listing
    t12 = api.list_ticket(token, 1.1, "attacker")
    tx12 = force_send(contract().functions.listForResale(token, wei(1.1)), "attacker", gas=200_000)
    case_reject(
        "T12", "M3 Anti-scalping", "Member 3", "Non-owner lists somebody else's ticket", "attacker",
        f"listForResale({token}, 1.1 ETH) called by attacker (owner is buyerA)",
        t12, "Not the owner", tx=tx12,
        screenshot="05_resale_market.png",
    )

    # T07 legal resale
    r7 = api.list_ticket(token, 1.2, "buyerA")
    _collect_gas("listForResale", r7, "T07")
    case_ok("T07a", "M3 Anti-scalping", "Member 3", "Holder lists at the 120% cap", "buyerA",
            f"listForResale({token}, 1.2 ETH)", r7,
            checks={"isListed=true": api.get_ticket(token)["is_listed"],
                    "listing price 1.2": api.get_ticket(token)["listing_price_eth"] == 1.2},
            screenshot="05_resale_market.png")

    r7b = api.buy_resale(token, "buyerB")
    _collect_gas("buyResale", r7b, "T07")
    ticket_after = api.get_ticket(token)
    bal_after = balance("buyerA")
    fee_delta = (pending_fee_wei() - fee_before) / 1e18
    case_ok("T07b", "M3 Anti-scalping", "Member 3", "Another wallet buys the resale listing", "buyerB",
            f"buyResale({token}) value=1.2 ETH", r7b,
            expected="success; ownerOf changes, resaleCount +1",
            checks={"ownerOf == buyerB": ticket_after["owner"] == addr("buyerB"),
                    "resaleCount == 1": ticket_after["resale_count"] == 1,
                    "listing cleared": not ticket_after["is_listed"],
                    "platform fee = 0.06 ETH": abs(fee_delta - 0.06) < 1e-9},
            screenshot="05_resale_market.png",
            note=f"seller received +{(bal_after - bal_before):.4f} ETH (1.2 minus the 5% fee, own gas excluded)")

    # E08 / E05 duplicate listing and buying a cancelled listing
    first_list = api.list_ticket(token, 1.1, "buyerB")   # buyResale cleared the previous listing
    again = api.list_ticket(token, 1.1, "buyerB")        # second call must be rejected
    tx_again = force_send(contract().functions.listForResale(token, wei(1.1)), "buyerB", gas=200_000)
    case_reject("E08", "M3 Anti-scalping", "Member 5", "Listing the same ticket twice", "buyerB",
                f"listForResale({token}, 1.1) called twice in a row",
                again, "Already listed", tx=tx_again,
                checks={"first listing succeeded": first_list.ok,
                        "still listed": api.get_ticket(token)["is_listed"]},
                note="the second call is rejected; the ticket keeps the first listing")

    cancel = api.cancel_listing(token, "buyerB")
    case_ok("E05a", "M3 Anti-scalping", "Member 3", "Owner cancels the listing", "buyerB",
            f"cancelListing({token})", cancel,
            checks={"isListed=false": not api.get_ticket(token)["is_listed"]})
    buy_cancelled = api.buy_resale(token, "buyerA")
    tx_cancel = force_send(contract().functions.buyResale(token), "buyerA", value=wei(1.1), gas=300_000)
    case_reject("E05b", "M3 Anti-scalping", "Member 5", "Buy a ticket whose listing was cancelled", "buyerA",
                f"buyResale({token}) value=1.1 ETH (listing already cancelled)",
                buy_cancelled, "Not listed for resale", tx=tx_cancel)

    # T10 resale-count cap (3): resaleCount is 1, make it 3
    seller, buyer = "buyerB", "buyerA"
    for i in (2, 3):
        listed = api.list_ticket(token, 1.1, seller)
        if not listed.ok:
            sys.exit(f"resale #{i} listing failed unexpectedly: {listed.error}")
        res = api.buy_resale(token, buyer)
        if not res.ok:
            sys.exit(f"resale #{i} purchase failed unexpectedly: {res.error}")
        _collect_gas("buyResale", res, f"T10-{i}")
        print(f"       + resale #{i} ok, resaleCount={api.get_ticket(token)['resale_count']}")
        seller, buyer = buyer, seller
    case_ok("T10a", "M3 Anti-scalping", "Member 3", "Resell until the third transfer (the cap)", "buyerA/buyerB",
            "listForResale -> buyResale x2", {"ok": True},
            expected="success; resaleCount = 3",
            checks={"resaleCount == 3": api.get_ticket(token)["resale_count"] == 3},
            note="the first resale came from T07b; this step performs #2 and #3")
    owner_role = "buyerB" if api.get_ticket_owner(token) == addr("buyerB") else "buyerA"
    fourth = api.list_ticket(token, 1.1, owner_role)
    tx10 = force_send(contract().functions.listForResale(token, wei(1.1)), owner_role, gas=200_000)
    case_reject("T10b", "M3 Anti-scalping", "Member 3", "Fourth listing after the 3-resale cap", owner_role,
                f"listForResale({token}, 1.1 ETH)", fourth, "Max resale limit reached",
                tx=tx10, checks={"still not listed": not api.get_ticket(token)["is_listed"]})

    # T11 direct transfer bypass (both entry points)
    _, token_bypass = buy(ev, "buyerA", 1)
    tf = contract().functions["transferFrom(address,address,uint256)"]
    tx11a = force_send(tf(addr("buyerA"), addr("attacker"), token_bypass), "buyerA", gas=150_000)
    case_reject(
        "T11a", "M3 Anti-scalping", "Member 3", "Holder calls ERC-721 transferFrom to bypass resale rules", "buyerA",
        f"transferFrom(buyerA -> attacker, tokenId={token_bypass}) forced on chain with a 150k gas limit",
        {"ok": tx11a["status"] == 1, "error": "execution reverted (status=0)"}, "execution reverted",
        tx=tx11a,
        checks={"ownerOf unchanged": api.get_ticket_owner(token_bypass) == addr("buyerA")},
        screenshot="05_resale_market.png",
        note="the transaction is mined but status=0, and the gas is still charged - the strongest "
             "single piece of evidence that the rule lives on chain",
    )
    stf = contract().functions["safeTransferFrom(address,address,uint256)"]
    tx11b = force_send(stf(addr("buyerA"), addr("attacker"), token_bypass), "buyerA", gas=150_000)
    case_reject(
        "T11b", "M3 Anti-scalping", "Member 3", "Holder calls safeTransferFrom to bypass resale rules", "buyerA",
        f"safeTransferFrom(buyerA -> attacker, tokenId={token_bypass})",
        {"ok": tx11b["status"] == 1, "error": "execution reverted (status=0)"}, "execution reverted",
        tx=tx11b,
        checks={"ownerOf unchanged": api.get_ticket_owner(token_bypass) == addr("buyerA")},
        note="both transfer entry points are overridden to revert, so neither the UI nor a script can bypass",
    )

    # T09 dynamic cap: 3 days out drops to 100%
    ev_near = fresh_event("T09 Near-Event (3 days)", 0.5, 10, 3, 2)
    _, token_near = buy(ev_near, "buyerB", 1)
    near_cap = api.get_max_resale_price(token_near)
    case_ok("T09a", "M3 Anti-scalping", "Member 3", "Read the dynamic cap (3 days out -> 100%)", "read-only",
            f"getMaxResalePrice({token_near}) (original price 0.5 ETH)", {"ok": True},
            expected="returns 0.5 ETH",
            checks={"cap = 0.5 ETH": near_cap.get("max_price_eth") == 0.5},
            note=f"returned {near_cap.get('max_price_eth')} ETH")
    over_near = api.list_ticket(token_near, 0.51, "buyerB")
    tx9 = force_send(contract().functions.listForResale(token_near, wei(0.51)), "buyerB", gas=200_000)
    case_reject("T09b", "M3 Anti-scalping", "Member 3", "Listing above the cap close to the event", "buyerB",
                f"listForResale({token_near}, 0.51 ETH), cap is 0.5 ETH inside 7 days",
                over_near, "Price exceeds dynamic limit", tx=tx9,
                screenshot="05_resale_market.png")
    ok_near = api.list_ticket(token_near, 0.5, "buyerB")
    case_ok("T09c", "M3 Anti-scalping", "Member 3", "Listing exactly at the cap (0.5 ETH)", "buyerB",
            f"listForResale({token_near}, 0.5 ETH)", ok_near,
            checks={"isListed=true": api.get_ticket(token_near)["is_listed"]},
            note="boundary: price <= maxPrice is allowed")
    api.cancel_listing(token_near, "buyerB")

    # T09d the exact 7-day boundary
    ev_edge = fresh_event("T09d Exactly 7 Days", 1, 4, 7, 2)
    _, tok_edge = buy(ev_edge, "buyerA", 2)
    tok_edge2 = tok_edge + 1          # second ticket for the over-price probe (avoids "already listed")
    edge_cap = api.get_max_resale_price(tok_edge)
    edge_ok = api.list_ticket(tok_edge, 1.0, "buyerA")
    edge_over = api.list_ticket(tok_edge2, 1.01, "buyerA")
    case_ok("T09d", "M3 Anti-scalping", "Member 5", "Price cap right at the 7-day boundary", "buyerA",
            f"getMaxResalePrice({tok_edge}) -> 1.0 ETH; token{tok_edge} list 1.0 succeeds / "
            f"token{tok_edge2} list 1.01 is rejected",
            edge_ok,
            expected="cap switches to 100%: 1.0 lists, 1.01 is rejected",
            checks={"cap = 1.0 ETH": edge_cap.get("max_price_eth") == 1.0,
                    "1 wei above the cap rejected": not edge_over.ok},
            note=f"list 1.0 -> {'success' if edge_ok.ok else edge_ok.error}; "
                 f"list 1.01 -> {edge_over.error or 'success'}")
    api.cancel_listing(tok_edge, "buyerA")

    return token, token_bypass, ev


def test_qr_and_checkin(token_owner_ctx: dict):
    """Member 4's QR ticket plus Member 3's on-chain check-in."""
    section("Member 4 / Member 3 - QR verification and check-in (T13-T17)")

    ev = fresh_event("T13 QR Check-in Event", 0.3, 5, 10, 2)
    _, token = buy(ev, "buyerB", 1)
    holder = addr("buyerB")

    # T13 valid QR payload
    payload = qr_utils.create_ticket_qr(token, holder, api.signing_key("buyerB"), ttl=180)
    png = qr_utils.make_qr_png(payload)
    result = qr_utils.verify_payload(payload, api.get_ticket(token))
    case_ok(
        "T13", "M4 Check-in/QR", "Member 4", "Valid holder generates a short-lived QR and verifies it", "buyerB",
        f"create_ticket_qr(token={token}, holder=buyerB, ttl=180) -> verify_payload",
        {"ok": result["ok"]},
        expected="all five checks pass",
        checks={c["check"]: c["ok"] for c in result["checks"]},
        screenshot="04_my_tickets.png",
        note=f"QR PNG {len(png)} bytes; the payload carries token_id/holder/nonce/expires_at and an EIP-191 signature",
    )

    # T14a forged signature
    forged = qr_utils.create_ticket_qr(token, holder, api.signing_key("attacker"), ttl=180)
    res_forged = qr_utils.verify_payload(forged, api.get_ticket(token))
    case_reject("T14a", "M4 Check-in/QR", "Member 4", "Attacker forges the holder's signature", "attacker",
                "sign the buyerB holder field with the attacker key",
                {"ok": res_forged["ok"], "error": "signature mismatch"},
                "signature mismatch",
                checks={"signature check fails": not _check_ok(res_forged, "Signature matches holder")},
                note=f"recovered={res_forged['recovered']}")
    # T14b expired
    expired = qr_utils.create_ticket_qr(token, holder, api.signing_key("buyerB"), ttl=-30)
    res_expired = qr_utils.verify_payload(expired, api.get_ticket(token))
    case_reject("T14b", "M4 Check-in/QR", "Member 4", "Expired QR (screenshot forwarding)", "buyerB",
                "generated with ttl=-30 so expires_at is in the past",
                {"ok": res_expired["ok"], "error": "expired"}, "expired",
                checks={"expiry check fails": not _check_ok(res_expired, "Not expired")})
    # T14c previous owner after a resale
    ev_old = fresh_event("T14 Old Owner Event", 0.4, 5, 10, 2)
    _, tok_old = buy(ev_old, "buyerA", 1)
    old_qr = qr_utils.create_ticket_qr(tok_old, addr("buyerA"), api.signing_key("buyerA"), ttl=180)
    api.list_ticket(tok_old, 0.48, "buyerA")   # 120% = 0.48
    resale = api.buy_resale(tok_old, "buyerB")
    if not resale.ok:
        sys.exit(f"T14c resale failed: {resale.error}")
    res_old = qr_utils.verify_payload(old_qr, api.get_ticket(tok_old))
    case_reject("T14c", "M4 Check-in/QR", "Member 4", "QR held by the previous owner after a resale", "buyerA",
                "buyerA generates a QR -> resale to buyerB -> present the old QR",
                {"ok": res_old["ok"], "error": "ownerOf mismatch"}, "ownerOf mismatch",
                checks={"on-chain owner check fails": not _check_ok(res_old, "Matches on-chain ownerOf")},
                note=f"current ownerOf={api.get_ticket_owner(tok_old)}, QR holder={addr('buyerA')}")

    # T17 unauthorized check-in
    unauth = api.check_in(token, "attacker")
    tx17 = force_send(contract().functions.checkIn(token), "attacker", gas=150_000)
    case_reject("T17", "M4 Check-in/QR", "Member 3", "Account without the verifier role calls checkIn", "attacker",
                f"checkIn({token}) called by attacker", unauth, "Not an authorized verifier",
                tx=tx17, checks={"used is still false": not api.get_ticket(token)["used"]},
                screenshot="06_staff_checkin.png")

    # T15 authorization then first check-in
    grant = api.set_verifier("verifier", True, "deployer")
    case_ok("T15a", "M4 Check-in/QR", "Member 3", "Contract owner authorizes a verifier", "deployer",
            "setVerifier(verifier, true)", grant,
            checks={"verifiers[verifier] = true": api.is_verifier("verifier")})
    first = api.check_in(token, "verifier")
    _collect_gas("checkIn", first, "T15")
    case_ok("T15b", "M4 Check-in/QR", "Member 3", "Authorized verifier checks the ticket in", "verifier",
            f"checkIn({token}) called by verifier", first,
            expected="success; used = true",
            checks={"used = true": api.get_ticket(token)["used"]},
            screenshot="06_staff_checkin.png")

    # T16 double check-in
    second = api.check_in(token, "verifier")
    tx16 = force_send(contract().functions.checkIn(token), "verifier", gas=150_000)
    case_reject("T16", "M4 Check-in/QR", "Member 3", "Same ticket checked in a second time", "verifier",
                f"checkIn({token}) called again", second, "Ticket already used", tx=tx16,
                screenshot="06_staff_checkin.png")

    # E01 re-listing a used ticket
    used_list = api.list_ticket(token, 0.3, "buyerB")
    tx_e1 = force_send(contract().functions.listForResale(token, wei(0.3)), "buyerB", gas=200_000)
    case_reject("E01", "M3 Anti-scalping", "Member 5", "List an already checked-in ticket", "buyerB",
                f"listForResale({token}, 0.3 ETH) with used=true", used_list,
                "Ticket already used", tx=tx_e1)

    # E09 check-in clears an active listing
    _, tok_listed = buy(ev, "buyerA", 1)
    api.list_ticket(tok_listed, 0.33, "buyerA")
    listed_before = api.get_ticket(tok_listed)["is_listed"]
    check = api.check_in(tok_listed, "verifier")
    case_ok("E09", "M3 Anti-scalping", "Member 3", "Check-in clears an active listing", "verifier",
            f"listForResale({tok_listed}, 0.33) -> checkIn({tok_listed})", check,
            checks={"listed before check-in": listed_before,
                    "listing cleared after check-in": not api.get_ticket(tok_listed)["is_listed"],
                    "used = true": api.get_ticket(tok_listed)["used"]})

    # E02 self-dealing
    _, tok_self = buy(ev, "buyerA", 1)
    api.list_ticket(tok_self, 0.33, "buyerA")
    selfbuy = api.buy_resale(tok_self, "buyerA")
    tx_e2 = force_send(contract().functions.buyResale(tok_self), "buyerA", value=wei(0.33), gas=300_000)
    case_reject("E02", "M3 Anti-scalping", "Member 5", "Owner buys its own listing (wash trade)", "buyerA",
                f"buyResale({tok_self}) value=0.33 ETH with msg.sender == seller", selfbuy,
                "Cannot buy your own ticket", tx=tx_e2)
    api.cancel_listing(tok_self, "buyerA")


def test_presale_resale_whitelist():
    """E03: secondary trades during presale are still whitelist-gated."""
    section("Extra case - whitelist on the resale market during presale (E03)")
    ev = fresh_event("E03 Presale Resale Event", 0.8, 10, 14, 2, presale=True)
    api.set_whitelist(ev, ["buyerA"], True, "organizer")
    _, token = buy(ev, "buyerA", 1)
    listed = api.list_ticket(token, 0.9, "buyerA")   # 120% = 0.96
    case_ok("E03a", "M3 Anti-scalping", "Member 5", "Whitelisted holder lists during presale", "buyerA",
            f"listForResale({token}, 0.9 ETH)", listed,
            checks={"isListed=true": api.get_ticket(token)["is_listed"]},
            note="listing itself is allowed; the restriction lands on the buyer")
    blocked = api.buy_resale(token, "attacker")
    tx = force_send(contract().functions.buyResale(token), "attacker", value=wei(0.9), gas=300_000)
    case_reject("E03b", "M3 Anti-scalping", "Member 5", "Non-whitelisted wallet buys a resale ticket in presale",
                "attacker", f"buyResale({token}) value=0.9 ETH", blocked,
                "Buyer not in presale whitelist", tx=tx)
    api.cancel_listing(token, "buyerA")


def test_bypass_frontend():
    """Adversarial tests: no Streamlit, no ticket_api business functions, raw Web3.py."""
    section("Adversarial - calling the contract directly, bypassing the website")
    ev = fresh_event("Bypass Frontend Event", 0.6, 8, 10, 2)
    _, first = buy(ev, "buyerA", 2)     # two tickets: the second is used by B02
    token, token2 = first, first + 1

    # B01 over-price listing straight from web3
    over = contract().functions.listForResale(token, wei(2.0))
    reason = precheck(over, "buyerA")
    tx = force_send(over, "buyerA", gas=200_000)
    case_reject("B01", "M5 Bypass", "Member 5", "List at 2.0 ETH (original 0.6) without the UI", "buyerA",
                "web3 calls listForResale directly, no backend/ticket_api.py involved",
                {"ok": False, "error": reason}, "Price exceeds dynamic limit", tx=tx,
                note="neither the page button nor the backend wrapper is a security boundary")

    # B02 direct transfer
    t = contract().functions["transferFrom(address,address,uint256)"](
        addr("buyerA"), addr("attacker"), token2)
    tx2 = force_send(t, "buyerA", gas=150_000)
    case_reject("B02", "M5 Bypass", "Member 5", "Change the owner with transferFrom without the UI", "buyerA",
                f"transferFrom(buyerA -> attacker, {token2})",
                {"ok": tx2["status"] == 1, "error": "execution reverted (status=0)"},
                "execution reverted", tx=tx2,
                checks={"ownerOf unchanged": api.get_ticket_owner(token2) == addr("buyerA")})

    # B03 unauthorized check-in
    tx3 = force_send(contract().functions.checkIn(token), "attacker", gas=150_000)
    case_reject("B03", "M5 Bypass", "Member 5", "Call checkIn without the check-in page", "attacker",
                f"checkIn({token})", {"ok": tx3["status"] == 1, "error": "execution reverted (status=0)"},
                "execution reverted", tx=tx3,
                checks={"used is still false": not api.get_ticket(token)["used"]})

    # B04 underpayment (the wallet limit is checked before the amount, so use a fresh wallet)
    wrong = contract().functions.purchaseTickets(ev, 1)
    reason4 = precheck(wrong, "attacker", value=wei(0.1))
    tx4 = force_send(wrong, "attacker", value=wei(0.1), gas=250_000)
    case_reject("B04", "M5 Bypass", "Member 5", "Pay 0.1 ETH for a 0.6 ETH ticket", "attacker",
                "purchaseTickets(ev, 1) value=0.1 ETH", {"ok": False, "error": reason4},
                "Incorrect ETH amount", tx=tx4,
                checks={"stock unchanged": api.get_event(ev)["sold"] == 2},
                note="require order is stock/limit/whitelist before payment, so a wallet that has not "
                     "purchased yet is needed to hit the amount check")


def test_time_rules():
    """Time rules: sales stop after the event starts; getMaxResalePrice underflow."""
    section("Extra cases - time rules (E06 / E07)")
    ev = fresh_event("E06 Event Starts Soon", 0.1, 3, 25 / 86400, 2)  # starts in 25 seconds
    r, token = buy(ev, "buyerA", 1)
    case_ok("E06a", "M2 Primary market", "Member 5", "Purchase before the event starts", "buyerA",
            f"purchaseTickets({ev}, 1) value=0.1 ETH (event starts in 25 s)", r,
            checks={"sold == 1": api.get_event(ev)["sold"] == 1})

    event_time = api.get_event(ev)["event_time"]
    wait = max(event_time - int(time.time()) + 6, 0)
    print(f"       + waiting {wait}s for the event to start (chain time)...")
    time.sleep(wait)

    late = api.buy_ticket(ev, "attacker", 1)
    tx_late = force_send(contract().functions.purchaseTickets(ev, 1), "attacker", value=wei(0.1), gas=250_000)
    case_reject("E06b", "M2 Primary market", "Member 5", "Purchase after the event started", "attacker",
                f"purchaseTickets({ev}, 1) with block.timestamp >= eventTime", late,
                "Event already started", tx=tx_late)
    late_list = api.list_ticket(token, 0.1, "buyerA")
    tx_late2 = force_send(contract().functions.listForResale(token, wei(0.1)), "buyerA", gas=200_000)
    case_reject("E06c", "M3 Anti-scalping", "Member 5", "List for resale after the event started", "buyerA",
                f"listForResale({token}, 0.1 ETH)", late_list, "Event already started", tx=tx_late2)

    cap = api.get_max_resale_price(token)
    case_deviation(
        "E07", "M3 Anti-scalping", "Member 5", "Read getMaxResalePrice after the event started", "read-only",
        f"getMaxResalePrice({token}) with eventTime already in the past",
        f"call reverts ({str(cap.get('error'))[:80]}) - eventTime - block.timestamp underflows",
        expected="a view call should return normally (e.g. 0), not panic",
        note="implementation defect in Member 3's contract: the view panics once the event has started; "
             "the UI wraps it in try/except, but the function should check the time first",
    )


def test_end_to_end():
    """T18 full flow plus gas sampling."""
    section("End-to-end - T18 create -> buy -> resell -> check in")
    ev = fresh_event("T18 Full Flow Concert", 0.6, 6, 9, 1)
    rows = []

    r1 = api.get_event(ev)
    rows.append(("Create event", r1 is not None, f"eventId={ev}, remaining {api.remaining_supply(ev)}"))
    r2, token = buy(ev, "buyerA", 1)
    _collect_gas("purchaseTickets(1)", r2, "T18")
    rows.append(("buyerA buys", r2.ok and api.get_ticket_owner(token) == addr("buyerA"),
                 f"tokenId={token}, tx={r2.tx_hash}"))
    r3 = api.list_ticket(token, 0.72, "buyerA")   # 120% of 0.6
    _collect_gas("listForResale", r3, "T18")
    rows.append(("buyerA lists at 0.72 ETH", r3.ok and api.get_ticket(token)["is_listed"],
                 f"tx={r3.tx_hash}"))
    r4 = api.buy_resale(token, "buyerB")
    _collect_gas("buyResale", r4, "T18")
    rows.append(("buyerB buys the resale", r4.ok and api.get_ticket_owner(token) == addr("buyerB"),
                 f"tx={r4.tx_hash}, resaleCount={api.get_ticket(token)['resale_count']}"))
    qr = qr_utils.create_ticket_qr(token, addr("buyerB"), api.signing_key("buyerB"))
    v = qr_utils.verify_payload(qr, api.get_ticket(token))
    rows.append(("buyerB generates and verifies a QR", v["ok"],
                 f"{len(v['checks'])} checks passed" if v["ok"] else "verification failed"))
    r5 = api.check_in(token, "verifier")
    _collect_gas("checkIn", r5, "T18")
    rows.append(("verifier checks in", r5.ok and api.get_ticket(token)["used"], f"tx={r5.tx_hash}"))
    r6 = api.check_in(token, "verifier")
    rows.append(("second check-in rejected", not r6.ok and "already used" in (r6.error or "").lower(),
                 f"reason: {r6.error}"))

    all_ok = all(ok for _, ok, _ in rows)
    case_ok(
        "T18", "M5 End-to-end", "Members 1/4/5",
        "Full flow: create -> buy -> list -> resale -> QR -> check-in -> double check-in", "multiple",
        "seven on-chain operations plus one QR verification", {"ok": all_ok},
        expected="all seven steps behave as designed",
        checks={f"step{i + 1} {name}": ok for i, (name, ok, _) in enumerate(rows)},
        screenshot="06_staff_checkin.png",
        note=" | ".join(f"{name}: {detail}" for name, _, detail in rows),
    )
    for i, (name, ok, detail) in enumerate(rows, start=1):
        STEPS.append({"step": f"T18.{i}", "name": name, "ok": ok, "detail": detail})


def _check_ok(result: dict, name: str) -> bool:
    for c in result["checks"]:
        if c["check"] == name:
            return c["ok"]
    return False


# ======================================================================
def main() -> None:
    status = api.get_chain_status()
    if not status.get("connected"):
        sys.exit("Private chain unreachable: start it with ./blockchain/start_node.sh")
    if not status.get("contract_address"):
        sys.exit("Contract not deployed: run python backend/deploy.py first")

    print("=" * 78)
    print("FTEC5520 Anti-Scalping Ticketing System - Member 5 automated test suite")
    print(f"chainId={status['chain_id']} block={status['block_number']} contract={status['contract_address']}")
    print(f"started at {START_TS.isoformat(timespec='seconds')}")
    print("=" * 78)

    test_primary_market()
    token, token_bypass, ev = test_anti_scalping()
    test_qr_and_checkin({"token": token, "token_bypass": token_bypass, "event": ev})
    test_presale_resale_whitelist()
    test_bypass_frontend()
    test_end_to_end()
    test_time_rules()

    # ---------------------------------------------------------------- summary
    env = environment()
    counts = {"PASS": 0, "FAIL": 0, "DEVIATION": 0}
    for row in ROWS:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    judged = counts["PASS"] + counts["FAIL"]
    by_module: dict[str, dict[str, int]] = {}
    for row in ROWS:
        bucket = by_module.setdefault(row["module"], {"PASS": 0, "FAIL": 0, "DEVIATION": 0, "total": 0})
        bucket[row["verdict"]] += 1
        bucket["total"] += 1

    def status_of(row: dict) -> int:
        value = row.get("status")
        return 1 if value in (None, "") else int(value)

    failed_tx_gas = [r for r in GAS if status_of(r) == 0]
    summary = {
        "total_cases": len(ROWS),
        "pass": counts["PASS"],
        "fail": counts["FAIL"],
        "deviation": counts["DEVIATION"],
        "pass_rate": round(counts["PASS"] / judged * 100, 2) if judged else 0.0,
        "by_module": by_module,
        "normal_cases": sum(1 for r in ROWS if r["kind"] == "normal"),
        "negative_cases": sum(1 for r in ROWS if r["kind"] == "negative"),
        "on_chain_failed_txs": len(failed_tx_gas),
        "on_chain_failed_gas_total": sum(r["gas_used"] for r in failed_tx_gas),
        "final_block": api.get_w3().eth.block_number,
        "duration_seconds": int((datetime.now(timezone.utc) - START_TS).total_seconds()),
    }

    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / "test_results.csv", "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(ROWS)

    with open(RESULTS / "gas_data.csv", "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["operation", "tag", "tx_hash", "gas_used", "status"])
        writer.writeheader()
        for row in GAS:
            writer.writerow({**row, "status": status_of(row)})

    (RESULTS / "test_environment.json").write_text(
        json.dumps(env, indent=2, ensure_ascii=False), "utf-8")
    (RESULTS / "test_evidence.json").write_text(
        json.dumps({"environment": env, "summary": summary, "rows": ROWS,
                    "gas": GAS, "steps": STEPS},
                   indent=2, ensure_ascii=False), "utf-8")

    print("\n" + "=" * 78)
    print(f"{summary['total_cases']} cases: PASS {summary['pass']} / FAIL {summary['fail']} / "
          f"DEVIATION {summary['deviation']}, pass rate {summary['pass_rate']}%")
    by_op: dict[str, list[int]] = {}
    for row in GAS:
        if status_of(row) == 1:
            by_op.setdefault(row["operation"], []).append(row["gas_used"])
    for op, values in by_op.items():
        print(f"  gas {op:<26} n={len(values):<2} median={int(statistics_median(values)):>9,}")
    print(f"real failed transactions (status=0): {summary['on_chain_failed_txs']}, "
          f"gas {summary['on_chain_failed_gas_total']:,}")
    print(f"duration {summary['duration_seconds']}s, final block {summary['final_block']}")
    print(f"results: {RESULTS / 'test_results.csv'}")
    print(f"evidence: {RESULTS / 'test_evidence.json'}")
    print("=" * 78)

    if summary["fail"]:
        print("\nFAILED cases:")
        for row in ROWS:
            if row["verdict"] == "FAIL":
                print(f"  - {row['test_id']} {row['scenario']}: {row['actual']}")
        sys.exit(1)


def statistics_median(values: list[int]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


if __name__ == "__main__":
    main()
