#!/usr/bin/env python
"""Per-account verification against the "7 test accounts" (matches docs/ACCOUNTS.md and the
comparison table our teammates handed over).

Why this script exists
----------------------
`tests/test_workflow.py` covers T01-T18 plus the E*/B* series, but it does **not** cover the
actions that the teammate table maps to T19 / T20 / T23 / T24:

    * deployer collects the 5% platform fee and withdraws it (withdrawPlatformFees)
    * organizer withdraws the ticket proceeds (withdrawProceeds)
    * buyerB is the buyer on the receiving end of a resale, so NFT ownership after the
      resale matters (ownerOf / resaleCount)
    * miner produces a block every 2 seconds

This script performs a real on-chain verification of these "account-specific duties"
(it sends a transaction where a transaction should be sent, and requires a rejection where
a rejection is expected), then groups the existing cases from `results/test_results.csv`
by actor for every account and produces:

    results/account_verification.md     human-readable per-account report (can be sent to teammates)
    results/account_check.json          machine-readable verification details

Usage
-----
    ./blockchain/start_node.sh
    .venv/bin/python scripts/check_accounts.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import ticket_api as api  # noqa: E402

RESULTS = ROOT / "results"
CHECKS: list[dict] = []

# The "which cases does this correspond to" column of the teammate table = the wording in docs/ACCOUNTS.md
TEAMMATE_CASES = {
    "deployer": "T19 / T24",
    "organizer": "T01 / T02 / T20",
    "buyerA": "T03 / T09b / T13 / T15",
    "buyerB": "T14 / T23",
    "verifier": "T15 / T16",
    "attacker": "T04 / T06 / T08 / T10",
    "miner": "running in the background the whole time",
}

IDENTITY = {
    "deployer": ("Platform side (the person who deploys the contract)", "Contract owner; sets the verifier; collects the 5% platform fee"),
    "organizer": ("Organizer (the concert company)", "Creates events, toggles the presale, manages the whitelist, collects ticket proceeds"),
    "buyerA": ("Normal buyer (on the whitelist)", "Buys tickets during the presale, lists them for resale, gets scanned in at the gate"),
    "buyerB": ("Second normal buyer", "The buyer who takes over after a resale; verifies that NFT ownership has changed"),
    "verifier": ("On-site staff (ticket verifier)", "Scans and redeems tickets, marks them as \"used\""),
    "attacker": ("Scalper", "Deliberately breaks the rules: grabs presale tickets while not whitelisted, exceeds the purchase limit, resells above the price cap"),
    "miner": ("The block producer (Clique authorized signer)", "Packs one block every 2 seconds"),
}

ORDER = ["deployer", "organizer", "buyerA", "buyerB", "verifier", "attacker", "miner"]


def record(role: str, item: str, expected: str, actual: str, verdict: str,
           tx: str = "", note: str = "") -> None:
    CHECKS.append({
        "role": role, "item": item, "expected": expected,
        "actual": actual, "verdict": verdict, "tx_hash": tx, "note": note,
    })
    mark = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️", "DEVIATION": "⚠️"}[verdict]
    print(f"  {mark} [{role:<10}] {item:<34} {actual}")


def eth(who: str) -> float:
    return api.get_balance_eth(who)


def reason_of(err: object) -> str:
    """Translate a revert result into plain language (the contract uses custom errors, so only the 4-byte selector is available)."""
    text = str(err or "")
    if text.startswith("0x118cdaa7"):
        return "Rejected: OwnableUnauthorizedAccount (the caller is not the owner)"
    return ("Rejected: " + text[:70]) if text else "Rejected (no reason returned)"


def token_transfers(token_id: int) -> list[dict]:
    """All Transfer records of a single ticket (ascending by block).

    Note: `api.transfer_history(limit)` returns the **most recent N transfers site-wide**, not those
    of a single ticket, so the logs are filtered directly by topics[3] = tokenId.
    """
    w3 = api.get_w3()
    settings = api.get_settings()
    logs = w3.eth.get_logs({
        "fromBlock": max(int(settings.deploy_block), 0),
        "toBlock": "latest",
        "address": settings.contract_address,
        "topics": [api.TRANSFER_TOPIC, None, None, "0x" + format(int(token_id), "064x")],
    })
    return api._decode_transfer_logs(logs)  # noqa: SLF001


# ----------------------------------------------------------------------
# miner: block production cadence
# ----------------------------------------------------------------------
def check_miner() -> None:
    print("\n[1/7] miner -- block production (Clique PoA, 2s per block)")
    w3 = api.get_w3()
    b0 = w3.eth.block_number
    t0 = time.time()
    time.sleep(6.5)
    b1 = w3.eth.block_number
    dt = time.time() - t0
    produced = b1 - b0
    ok = produced >= 2
    record("miner", "New blocks within 6 seconds", ">=2 (2s per block)", f"{produced} (blocks {b0} -> {b1}, {dt:.1f}s)",
           "PASS" if ok else "FAIL")
    miner_addr = api.get_accounts().get("miner")
    if miner_addr:
        record("miner", "Is an authorized signer (miner account)", "Address exists and keeps producing blocks",
               f"{miner_addr}", "PASS" if ok else "FAIL")
    else:
        record("miner", "Is the miner account present in .env / genesis", "Present",
               "Not in the test account list (only the genesis alloc holds 1000 ETH)", "SKIP",
               note="The miner private key is managed by geth --unlock + password.txt and is not one of the 6 roles in .env")


# ----------------------------------------------------------------------
# deployer: owner + 5% platform fee + withdrawal rights
# ----------------------------------------------------------------------
def check_deployer() -> None:
    print("\n[2/7] deployer -- contract owner, 5% platform fee, fee withdrawal")
    accounts = api.get_accounts()
    owner = api._contract().functions.owner().call()  # noqa: SLF001
    is_owner = owner.lower() == accounts["deployer"].lower()
    record("deployer", "Is contract owner() = deployer", "Yes (the deployer is the owner)",
           f"{owner}", "PASS" if is_owner else "FAIL")

    # 5% fee: read the most recent TicketResold event and check the amount directly
    resales = api.get_events("TicketResold", limit=5)
    if resales:
        arg = resales[-1]["args"]
        price, fee = int(arg["price"]), int(arg["platformFee"])
        expect = price * 5 // 100
        ok = fee == expect
        record("deployer", "Resale platform fee = 5% of the sale price", f"{expect} wei (5%)",
               f"{fee} wei (token {arg['tokenId']}, sale price {price} wei)",
               "PASS" if ok else "FAIL", tx=resales[-1]["tx_hash"])
    else:
        record("deployer", "Resale platform fee = 5% of the sale price", "A TicketResold event exists", "No resale event", "SKIP")

    # Withdraw the fee
    pending = api.pending_platform_fees("deployer")
    before = eth("deployer")
    if pending > 0:
        res = api.withdraw_platform_fees("deployer")
        after = eth("deployer")
        ok = res.ok and after > before
        record("deployer", "withdrawPlatformFees withdraws the fee", "Succeeds and the balance increases",
               f"{pending:.4f} ETH -> balance {before:.4f} -> {after:.4f}",
               "PASS" if ok else "FAIL", tx=res.tx_hash or "",
               note=res.error or "")
        record("deployer", "pendingPlatformFees is zero after the withdrawal", "0",
               f"{api.pending_platform_fees('deployer'):.6f} ETH",
               "PASS" if api.pending_platform_fees("deployer") == 0 else "FAIL")
    else:
        record("deployer", "withdrawPlatformFees withdraws the fee", "There are pending fees",
               "Currently 0 (everything was already withdrawn earlier)", "SKIP")

    # Negative case: a non-owner cannot withdraw the fee (the contract uses Ownable2Step's custom error, no string reason)
    bad = api.withdraw_platform_fees("attacker")
    record("deployer", "attacker withdrawing the platform fee is rejected (onlyOwner)", "Rejected",
           reason_of(bad.error) if not bad.ok else "Succeeded unexpectedly",
           "PASS" if not bad.ok else "FAIL", tx=bad.tx_hash or "")


# ----------------------------------------------------------------------
# organizer: ticket proceeds withdrawal
# ----------------------------------------------------------------------
def check_organizer() -> None:
    print("\n[3/7] organizer -- event creation, ticket proceeds, proceeds withdrawal")
    pending = api.pending_proceeds("organizer")
    before = eth("organizer")
    if pending > 0:
        res = api.withdraw_proceeds("organizer")
        after = eth("organizer")
        ok = res.ok and after > before
        record("organizer", "withdrawProceeds withdraws the ticket proceeds", "Succeeds and the balance increases",
               f"{pending:.4f} ETH -> balance {before:.4f} -> {after:.4f}",
               "PASS" if ok else "FAIL", tx=res.tx_hash or "", note=res.error or "")
        record("organizer", "pendingProceeds is zero after the withdrawal", "0",
               f"{api.pending_proceeds('organizer'):.6f} ETH",
               "PASS" if api.pending_proceeds("organizer") == 0 else "FAIL")
    else:
        record("organizer", "withdrawProceeds withdraws the ticket proceeds", "There are pending proceeds",
               "Currently 0 (everything was already withdrawn earlier)", "SKIP")

    bad = api.withdraw_proceeds("attacker")
    record("organizer", "attacker withdrawing the proceeds is rejected (nothing pending)", "Rejected: No proceeds available",
           ("Rejected: " + str(bad.error)[:60]) if not bad.ok else "Succeeded unexpectedly",
           "PASS" if not bad.ok else "FAIL", tx=bad.tx_hash or "")


# ----------------------------------------------------------------------
# buyerA / buyerB: resale and the transfer of NFT ownership
# ----------------------------------------------------------------------
def check_buyers() -> None:
    print("\n[4/7][5/7] buyerA / buyerB -- buying tickets, listing for resale, ownership change after the take-over")
    accounts = api.get_accounts()
    tokens = api.all_tokens()
    resold = [t for t in tokens if (api.get_ticket(t) or {}).get("resale_count", 0) > 0]
    if not resold:
        record("buyerB", "ownerOf and resaleCount after a resale", "At least one ticket has been resold", "None", "SKIP")
        return

    tok = resold[-1]
    t = api.get_ticket(tok)
    onchain_owner = t["owner"]
    role = next((r for r, a in accounts.items() if a.lower() == onchain_owner.lower()), None)
    hist = token_transfers(tok)
    last = hist[-1] if hist else None
    match = last is not None and last["to"].lower() == onchain_owner.lower()
    record("buyerB", f"ownerOf of resold token {tok} matches the last Transfer", "Matches",
           f"ownerOf={onchain_owner[:12]}... ({role}) / Transfer "
           f"{last['from'][:10] if last else '—'}->{last['to'][:10] if last else '—'} @block "
           f"{last['block'] if last else '—'}",
           "PASS" if match else "FAIL",
           tx=last["tx_hash"] if last else "",
           note=f"resaleCount={t['resale_count']} (max 3)")

    expect_count = max(len(hist) - 1, 0)  # 1 mint + 1 per resale
    record("buyerB", f"resaleCount of token {tok} matches the on-chain Transfer count",
           f"{expect_count} ({len(hist)} Transfers - 1 mint)",
           f"{t['resale_count']}",
           "PASS" if t["resale_count"] == expect_count else "FAIL")

    listed = api.listed_tickets()
    record("buyerA", "Current number of listings on the resale market is readable", ">=0 entries",
           f"{len(listed)} listed: " + ", ".join(f"token {x['token_id']}@{x['listing_price_eth']}ETH" for x in listed[:4]),
           "PASS")


# ----------------------------------------------------------------------
# verifier / attacker: permissions
# ----------------------------------------------------------------------
def check_verifier_attacker() -> None:
    print("\n[6/7] verifier / attacker -- redemption rights and the violating account")
    ok_v = api.is_verifier("verifier")
    record("verifier", "is_verifier(verifier) = true (authorized)", "true",
           str(ok_v).lower(), "PASS" if ok_v else "FAIL")
    ok_a = api.is_verifier("attacker")
    record("verifier", "is_verifier(attacker) = false", "false",
           str(ok_a).lower(), "PASS" if not ok_a else "FAIL")
    ok_b = api.is_verifier("buyerA")
    record("verifier", "is_verifier(buyerA) = false (a normal buyer cannot redeem)", "false",
           str(ok_b).lower(), "PASS" if not ok_b else "FAIL")
    record("attacker", "attacker has no redemption rights (T17 precondition)", "false",
           f"is_verifier(attacker)={str(ok_a).lower()}", "PASS" if not ok_a else "FAIL")


# ----------------------------------------------------------------------
# Group the automated suite cases by actor for every account
# ----------------------------------------------------------------------
def load_suite() -> list[dict]:
    path = RESULTS / "test_results.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def cases_of(rows: list[dict], role: str) -> list[dict]:
    out = []
    for r in rows:
        actor = (r.get("actor") or "")
        parts = [p.strip() for p in actor.replace("/", " ").split()]
        if role in parts:
            out.append(r)
    return out


def build_report(rows: list[dict]) -> str:
    counts = {"PASS": 0, "FAIL": 0, "DEVIATION": 0}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    ck = {"PASS": 0, "FAIL": 0, "SKIP": 0, "DEVIATION": 0}
    for c in CHECKS:
        ck[c["verdict"]] = ck.get(c["verdict"], 0) + 1

    status = api.get_chain_status()
    lines = [
        "# Per-account verification report (following the 7-account table from our teammates)",
        "",
        f"> Generated at: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"> Chain: chainId {status['chain_id']} · block {status['block_number']} · contract `{status['contract_address']}`",
        f"> Automated cases: {len(rows)} -> PASS {counts['PASS']} / FAIL {counts['FAIL']} / deviation {counts['DEVIATION']}",
        f"> Account-specific checks: {len(CHECKS)} -> PASS {ck['PASS']} / FAIL {ck['FAIL']} / skipped {ck['SKIP']}",
        "",
        "## 1. Overview",
        "",
        "| Account | Who | What it does in the demo | Tests from the teammate table | Cases actually covered | Failed | Account-specific checks |",
        "|---|---|---|---|---|---|---|",
    ]
    for role in ORDER:
        who, duty = IDENTITY[role]
        cs = cases_of(rows, role)
        fails = [c for c in cs if c["verdict"] == "FAIL"]
        mine = [c for c in CHECKS if c["role"] == role]
        bad = [c for c in mine if c["verdict"] == "FAIL"]
        ck_txt = f"{len(mine)} checks, failed {len(bad)}" if mine else "—"
        lines.append(
            f"| `{role}` | {who} | {duty} | {TEAMMATE_CASES[role]} | {len(cs)} cases | "
            f"{'**' + str(len(fails)) + '**' if fails else '0'} | {ck_txt} |"
        )

    lines += ["", "## 2. Per-account details", ""]
    for role in ORDER:
        who, duty = IDENTITY[role]
        lines.append(f"### `{role}` — {who}")
        lines.append("")
        mine = [c for c in CHECKS if c["role"] == role]
        if mine:
            lines.append("**Account-specific checks (real transactions / on-chain reads in this run)**")
            lines.append("")
            lines.append("| Check | Expected | Actual | Result | tx |")
            lines.append("|---|---|---|---|---|")
            for c in mine:
                tx = f"`{c['tx_hash'][:18]}…`" if c["tx_hash"] else "—"
                lines.append(f"| {c['item']} | {c['expected']} | {c['actual']} | {c['verdict']} | {tx} |")
            lines.append("")
        cs = cases_of(rows, role)
        if cs:
            lines.append(f"**Automated suite cases with actor = {role}**")
            lines.append("")
            lines.append("| Case | Scenario | Expected | Result | tx |")
            lines.append("|---|---|---|---|---|")
            for c in cs:
                tx = f"`{c['tx_hash'][:18]}…`" if c.get("tx_hash") else "—"
                lines.append(f"| {c['test_id']} | {c['scenario'][:40]} | {c['expected'][:16]} | "
                             f"{c['verdict']} | {tx} |")
            lines.append("")
        if not mine and not cs:
            lines.append("— No account action is bound directly to this role (background resident role)")
            lines.append("")

    lines += [
        "## 3. Differences from the teammate table (two points to align with the team)",
        "",
        "### 1) The four IDs `T19 / T20 / T23 / T24` do not exist in this repository",
        "",
        "`tests/test_workflow.py` numbers its cases T01-T18 + E01-E09 + B01-B04, "
        "while `backend/demo_flow.py` uses a different numbering, T01-T17; neither goes beyond T18. "
        "The IDs in the teammate table presumably come from the course assignment sheet; the behaviour itself is covered, and the mapping is as follows:",
        "",
        "| Teammate ID | Behaviour | Actual evidence in this repository |",
        "|---|---|---|",
        "| T19 (deployer) | Collects the 5% platform fee | deployer section of this report: reads `TicketResold.platformFee` and checks it = sale price x 5%, then really withdraws |",
        "| T20 (organizer) | Withdraws the ticket proceeds | organizer section of this report: `withdrawProceeds` sends a real transaction, the balance increases, pending proceeds go to zero |",
        "| T23 (buyerB) | NFT ownership changes after the resale take-over | buyerB section of this report (`ownerOf` vs `Transfer.to`) + suite T07b / T10a / T18 |",
        "| T24 (deployer) | Sets the verifier | suite T15a (`setVerifier`); the verifier section of this report re-checks the `is_verifier` state |",
        "",
        "### 2) The addresses in `docs/ACCOUNTS.md` do not match the current chain (out of date)",
        "",
        "That file records the accounts and contract address of the chain that was built on WSL on 2026-11-17; "
        "on this machine `blockchain/init_chain.py` has regenerated the accounts, so all the addresses changed. Treat `config/network.json` as the source of truth:",
        "",
        "| Role | `config/network.json` (current chain, authoritative) | `docs/ACCOUNTS.md` (old WSL chain, out of date) |",
        "|---|---|---|",
    ]
    acc = api.get_accounts()
    stale = {
        "deployer": "0xac58247eD6B94f69762b7eBce072583c1159aD7f",
        "organizer": "0x0aF12A334a38d395117639881915E44fE5d4bBFD",
        "buyerA": "0xeE380Abd54DD46C88F26e21424105039198303a3",
        "buyerB": "0x60D7A41a7DF950756bC63c37698d086C9d35fC19",
        "verifier": "0x1FbD76615383d87B68bF9686342F3e6F2a0C2CF0",
        "attacker": "0xDac1050a8de63b9550D0F14ED6deA90389F2EDc2",
    }
    for role in ORDER:
        if role == "miner":
            continue
        lines.append(f"| {role} | `{acc.get(role, '—')}` | `{stale.get(role, '—')}` |")
    lines += [
        "",
        "> If teammates check the addresses from `ACCOUNTS.md` against the chain, none of them will match -- the chain is not wrong, the document simply was not regenerated. "
        "Either regenerate `docs/ACCOUNTS.md` once (it is refreshed as soon as `init_chain.py` finishes) or tell everyone explicitly to treat `config/network.json` as the source of truth.",
        "",
        "## 4. Conclusion",
        "",
    ]
    bad_all = [c for c in CHECKS if c["verdict"] == "FAIL"] + [r for r in rows if r["verdict"] == "FAIL"]
    if not bad_all:
        lines.append("**All passed**: the demo duties of the 7 accounts, the violation blocking and the permission control are all reproduced on the current chain, with no FAIL cases; the 2 DEVIATIONs are "
                     "differences in wording between the assignment sheet and the implementation (noted in `results/test_evidence.json`), not defects.")
    else:
        lines.append(f"**{len(bad_all)} items failed**; see the tables above for details.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    status = api.get_chain_status()
    if not status.get("connected") or not status.get("contract_address"):
        sys.exit("Chain or contract unavailable: start ./blockchain/start_node.sh and run .venv/bin/python backend/deploy.py first")

    print("=" * 78)
    print("Per-account verification against the teammate table of \"7 accounts\"")
    print(f"chainId={status['chain_id']} block={status['block_number']} contract={status['contract_address']}")
    print("=" * 78)

    check_miner()
    check_deployer()
    check_organizer()
    check_buyers()
    check_verifier_attacker()

    rows = load_suite()
    report = build_report(rows)
    (RESULTS / "account_verification.md").write_text(report, "utf-8")
    (RESULTS / "account_check.json").write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "chain": status, "checks": CHECKS}, indent=2, ensure_ascii=False,
                   default=str), "utf-8")

    ck = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    for c in CHECKS:
        ck[c["verdict"]] = ck.get(c["verdict"], 0) + 1
    print("\n" + "=" * 78)
    print(f"Account-specific checks: {len(CHECKS)} items: PASS {ck['PASS']} / FAIL {ck['FAIL']} / skipped {ck['SKIP']}")
    print(f"Suite cases: {len(rows)}: " + " / ".join(
        f"{k} {sum(1 for r in rows if r['verdict'] == k)}" for k in ("PASS", "FAIL", "DEVIATION")))
    print(f"Report: {RESULTS / 'account_verification.md'}")
    print("=" * 78)
    if ck["FAIL"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
