"""End-to-end demo and evidence collector (Member 1 / Member 4 integration).

Runs, in order:
    create events -> presale whitelist -> primary purchase (success and failure)
    -> direct transfer bypass (failure) -> over-priced listing (failure)
    -> near-event cap (failure) -> legal listing -> resale purchase
    -> resale-count cap (failure) -> verifier authorisation -> first check-in
    -> duplicate check-in (failure) -> unauthorised check-in (failure)

Outputs:
    results/tx_evidence.json   real tx_hash / block / gas for every operation
    results/demo_report.md     the same evidence as a table that can go into the report

Usage:
    ./blockchain/start_node.sh --reset
    python backend/deploy.py
    python backend/demo_flow.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import ticket_api as api  # noqa: E402
from backend.chain import TxResult  # noqa: E402

RESULTS = ROOT / "results"
STEPS: list[dict] = []


def record(
    test_id: str,
    action: str,
    actor: str,
    result: TxResult | dict,
    expected: str,
    note: str = "",
) -> TxResult | dict:
    data = result.to_dict() if isinstance(result, TxResult) else dict(result)
    entry = {
        "test_id": test_id,
        "action": action,
        "actor": actor,
        "expected": expected,
        "ok": bool(data.get("ok")),
        "pass": bool(data.get("ok")) == expected.startswith("success"),
        "tx_hash": data.get("tx_hash"),
        "block_number": data.get("block_number"),
        "gas_used": data.get("gas_used"),
        "error": data.get("error"),
        "note": note,
    }
    STEPS.append(entry)
    flag = "PASS" if entry["pass"] else "FAIL"
    print(f"[{flag}] {test_id} {action:<44} ok={entry['ok']!s:<5} "
          f"tx={entry['tx_hash'] or '-'} gas={entry['gas_used'] or '-'}"
          + (f" err={entry['error']}" if entry["error"] else ""))
    return result


def expect_fail(result: TxResult | dict) -> bool:
    """A negative case passes only when ok=False."""
    return not (result.to_dict() if isinstance(result, TxResult) else result).get("ok")


def main() -> None:
    status = api.get_chain_status()
    if not status["connected"] or not status["contract_address"]:
        sys.exit("Chain or contract unavailable: run ./blockchain/start_node.sh and backend/deploy.py")

    print("=" * 78)
    print(f"chain {status['chain_id']} - block {status['block_number']} - contract "
          f"{status['contract_address']}")
    print("=" * 78)

    now = datetime.now(timezone.utc)

    # ------------------------------------------------------------- events
    ev1 = api.create_event("FTEC5520 Live Concert 2026", 1, 100, now + timedelta(days=10), 2, False,
                           "organizer")
    record("T01", "Create event (1 ETH / 100 tickets / limit 2)", "organizer", ev1, "success",
           "event starts in 10 days")
    event1 = api.get_next_event_id() - 1

    ev2 = api.create_event("Last-Minute Night (<=7 days)", 0.5, 50, now + timedelta(days=3), 2, False,
                           "organizer")
    record("T01b", "Create near-event event (0.5 ETH / 3 days out)", "organizer", ev2, "success",
           "used for the 100% dynamic cap")
    event2 = api.get_next_event_id() - 1

    ev3 = api.create_event("Presale Only Event", 0.8, 20, now + timedelta(days=14), 2, True, "organizer")
    record("T01c", "Create presale event (presaleActive=true)", "organizer", ev3, "success")
    event3 = api.get_next_event_id() - 1
    record("T02", "Batch whitelist buyerA / buyerB", "organizer",
           api.set_whitelist(event3, ["buyerA", "buyerB"], True, "organizer"), "success")

    # ------------------------------------------------------------ purchases
    r = record("T03", "buyerA buys 1 ticket during presale", "buyerA",
               api.buy_ticket(event3, "buyerA", 1), "success")
    presale_token = r.extra.get("first_token_id") if isinstance(r, TxResult) else None

    record("T04", "attacker (not whitelisted) buys during presale", "attacker",
           api.buy_ticket(event3, "attacker", 1), "failure",
           "expected revert: Wallet is not whitelisted")

    r1 = record("T05a", "buyerA buys 1 ticket (event 1)", "buyerA",
                api.buy_ticket(event1, "buyerA", 1), "success")
    token_a1 = r1.extra.get("first_token_id")
    r2 = record("T05b", "buyerA buys a second ticket (reaches the limit)", "buyerA",
                api.buy_ticket(event1, "buyerA", 1), "success")
    token_a2 = r2.extra.get("first_token_id")
    record("T05c", "buyerB buys 1 ticket (event 1)", "buyerB",
           api.buy_ticket(event1, "buyerB", 1), "success")
    record("T06", "attacker tries to buy 3 tickets (limit is 2)", "attacker",
           api.buy_ticket(event1, "attacker", 3), "failure",
           "expected revert: Wallet limit exceeded")

    # sold-out scenario: a dedicated event with a single ticket
    ev4 = api.create_event("Sold Out Test", 0.2, 1, now + timedelta(days=20), 1, False, "organizer")
    event4 = api.get_next_event_id() - 1
    record("T06b", "attacker buys the only ticket", "attacker",
           api.buy_ticket(event4, "attacker", 1), "success")
    record("T06c", "buyerB buys after the event sold out", "buyerB",
           api.buy_ticket(event4, "buyerB", 1), "failure", "expected revert: Not enough tickets")

    # ------------------------------------------------------------ bypass
    # Call the overridden transferFrom for real: send the transaction and keep the status=0 receipt.
    w3 = api.get_w3()
    chain = api.chain()
    contract = chain.require_contract()
    sender = api.get_accounts()["buyerA"]
    fn = contract.functions.transferFrom(sender, api.get_accounts()["attacker"], token_a1)
    tx = fn.build_transaction(
        {
            "from": sender,
            "nonce": w3.eth.get_transaction_count(sender, "pending"),
            "chainId": chain.settings.chain_id,
            "gas": 120_000,
            **chain._fee_fields(),
        }
    )
    tx.pop("from", None)
    signed = __import__("eth_account").Account.sign_transaction(tx, chain.settings.key("buyerA"))
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    bypass_hash = w3.eth.send_raw_transaction(raw)
    bypass_receipt = w3.eth.wait_for_transaction_receipt(bypass_hash, timeout=120)
    record(
        "T11",
        "holder calls transferFrom directly to move the ticket",
        "buyerA",
        {
            "ok": bypass_receipt.status == 1,
            "function": "transferFrom",
            "tx_hash": "0x" + bypass_hash.hex().removeprefix("0x"),
            "block_number": bypass_receipt.blockNumber,
            "gas_used": bypass_receipt.gasUsed,
            "error": "execution reverted (status=0)" if bypass_receipt.status == 0 else None,
        },
        "failure",
        "the contract overrides the function with revert: the tx is mined but status=0",
    )

    # ------------------------------------------------------------ price caps
    record("T08", "buyerA lists at 1.5 ETH (original price 1 ETH)", "buyerA",
           api.list_ticket(token_a1, 1.5, "buyerA"), "failure",
           "expected revert: Price exceeds dynamic limit")
    record("T12", "attacker lists a ticket it does not own", "attacker",
           api.list_ticket(token_a1, 1.1, "attacker"), "failure", "expected revert: Not the owner")

    # near-event event: the cap is 100%
    record("T09a", "buyerB buys a ticket of event 2", "buyerB",
           api.buy_ticket(event2, "buyerB", 1), "success")
    token_b2 = api.get_next_token_id() - 1
    record("T09", "3 days out, lists at 0.6 ETH (cap 0.5)", "buyerB",
           api.list_ticket(token_b2, 0.6, "buyerB"), "failure",
           "expected revert: Price exceeds dynamic limit")
    record("T09b", "3 days out, lists at 0.5 ETH (= 100%)", "buyerB",
           api.list_ticket(token_b2, 0.5, "buyerB"), "success",
           "the cap drops to the original price near the event")

    # ------------------------------------------------------------ legal resale
    record("T07a", "buyerA lists at 1.2 ETH (= 120%)", "buyerA",
           api.list_ticket(token_a1, 1.2, "buyerA"), "success")
    r = record("T07", "buyerB buys the resale listing", "buyerB",
               api.buy_resale(token_a1, "buyerB"), "success")
    print(f"      ownerOf({token_a1}) after the resale = {api.get_ticket_owner(token_a1)}")

    # ------------------------------------------------------------ resale cap (3)
    # T07 already performed resale #1; do two more to reach the cap of 3.
    seller, buyer = "buyerB", "buyerA"
    for i in range(2):
        listed = api.list_ticket(token_a1, 1.1, seller)
        if not listed.ok:
            sys.exit(f"listing for resale #{i + 2} failed unexpectedly: {listed.error}")
        res = api.buy_resale(token_a1, buyer)
        if not res.ok:
            sys.exit(f"resale #{i + 2} failed unexpectedly: {res.error}")
        print(f"      resale #{i + 2} ok: tx={res.tx_hash} gas={res.gas_used} "
              f"resaleCount={api.get_ticket(token_a1)['resale_count']}")
        seller, buyer = buyer, seller

    owner_role = next(
        r for r, a in api.get_accounts().items() if a.lower() == api.get_ticket_owner(token_a1).lower()
    )
    record("T10", "fourth listing (resaleCount already 3)", owner_role,
           api.list_ticket(token_a1, 1.1, owner_role), "failure",
           "expected revert: Max resale limit reached")

    # ------------------------------------------------------------ check-in
    record("T17", "attacker (unauthorised) calls checkIn", "attacker",
           api.check_in(presale_token, "attacker"), "failure",
           "expected revert: Not an authorized verifier")
    record("T13", "owner authorises the verifier", "deployer",
           api.set_verifier("verifier", True, "deployer"), "success")
    record("T15", "verifier checks the ticket in for the first time", "verifier",
           api.check_in(presale_token, "verifier"), "success")
    record("T16", "second check-in of the same ticket", "verifier",
           api.check_in(presale_token, "verifier"), "failure", "expected revert: Ticket already used")

    # ------------------------------------------------------------ leave one listing for the UI
    record("T07c", "attacker buys 1 ticket of event 1 as a display item", "attacker",
           api.buy_ticket(event1, "attacker", 1), "success")
    display_token = api.get_next_token_id() - 1
    record("T07d", "that ticket is listed at 1.2 ETH (kept for the demo pages)", "attacker",
           api.list_ticket(display_token, 1.2, "attacker"), "success")

    # ------------------------------------------------------------ summary
    api.get_chain_status()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "network": {
            "rpc_url": api.get_settings().rpc_url,
            "chain_id": api.get_settings().chain_id,
            "contract_address": api.get_contract_address(),
            "deploy_tx": api.get_settings().deploy_tx,
            "deploy_block": api.get_settings().deploy_block,
            "accounts": api.get_accounts(),
            "final_block": api.get_w3().eth.block_number,
        },
        "state": {
            "events": {e["event_id"]: e["name"] for e in api.list_events()},
            "tokens": len(api.all_tokens()),
            "listed": [t["token_id"] for t in api.listed_tickets()],
        },
        "steps": STEPS,
        "summary": {
            "total": len(STEPS),
            "pass": sum(1 for s in STEPS if s["pass"]),
            "fail": sum(1 for s in STEPS if not s["pass"]),
        },
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "tx_evidence.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), "utf-8")
    write_markdown(payload)
    print("=" * 78)
    print(f"{payload['summary']['total']} operations, PASS {payload['summary']['pass']}, "
          f"FAIL {payload['summary']['fail']}")
    print(f"evidence: {RESULTS / 'tx_evidence.json'}")
    print(f"report table: {RESULTS / 'demo_report.md'}")


def write_markdown(payload: dict) -> None:
    net = payload["network"]
    lines = [
        "# FTEC5520 Anti-Scalping Ticketing System - on-chain evidence",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Network: private chain, chainId `{net['chain_id']}`, RPC `{net['rpc_url']}`",
        f"- Contract address: `{net['contract_address']}`",
        f"- Deployment tx: `{net['deploy_tx']}` (block {net['deploy_block']})",
        "",
        "## Test detail",
        "",
        "| ID | Scenario | Actor | Expected | Actual | Result | Tx hash | Block | Gas |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in payload["steps"]:
        actual = "success" if s["ok"] else f"rejected: {s['error']}"
        lines.append(
            f"| {s['test_id']} | {s['action']} | {s['actor']} | {s['expected']} | {actual} | "
            f"{'PASS' if s['pass'] else 'FAIL'} | `{s['tx_hash'] or '-'}` | "
            f"{s['block_number'] or '-'} | {s['gas_used'] or '-'} |"
        )
    lines += [
        "",
        "## Summary",
        "",
        f"- Operations: {payload['summary']['total']}, pass {payload['summary']['pass']}, "
        f"fail {payload['summary']['fail']}",
        f"- Final block: {net['final_block']}",
        f"- Tickets minted: {payload['state']['tokens']}, currently listed: {payload['state']['listed']}",
        "",
        "> Note: the pass flag respects the expected direction - a case expected to fail only counts as "
        "PASS when the contract really rejected it.",
    ]
    (RESULTS / "demo_report.md").write_text("\n".join(lines), "utf-8")


if __name__ == "__main__":
    main()
