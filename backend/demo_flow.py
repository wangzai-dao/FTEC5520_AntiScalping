"""端到端演示 / 证据采集脚本（成员 1、4 联调用）。

依次执行：
    创建活动 → 白名单预售 → 一级购票（成功/失败）→ 直接转账绕过（失败）
    → 超价挂牌（失败）→ 临近演出限价（失败）→ 合法挂牌 → 二手购买
    → 转售次数上限（失败）→ 授权验票 → 首次核销 → 重复核销（失败）→ 未授权核销（失败）

输出：
    results/tx_evidence.json   每条操作的真实 tx_hash / block / gas
    results/demo_report.md     可直接贴进报告的证据表

用法：
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
        "pass": bool(data.get("ok")) == expected.startswith("成功"),
        "tx_hash": data.get("tx_hash"),
        "block_number": data.get("block_number"),
        "gas_used": data.get("gas_used"),
        "error": data.get("error"),
        "note": note,
    }
    STEPS.append(entry)
    flag = "PASS" if entry["pass"] else "FAIL"
    print(f"[{flag}] {test_id} {action:<28} ok={entry['ok']!s:<5} "
          f"tx={entry['tx_hash'] or '—'} gas={entry['gas_used'] or '—'}"
          + (f" err={entry['error']}" if entry["error"] else ""))
    return result


def expect_fail(result: TxResult | dict) -> bool:
    """失败用例：ok=False 才算 PASS。"""
    return not (result.to_dict() if isinstance(result, TxResult) else result).get("ok")


def main() -> None:
    status = api.get_chain_status()
    if not status["connected"] or not status["contract_address"]:
        sys.exit("链或合约不可用，请先 ./blockchain/start_node.sh 和 python backend/deploy.py")

    print("=" * 78)
    print(f"链 {status['chain_id']} · 区块 {status['block_number']} · 合约 {status['contract_address']}")
    print("=" * 78)

    now = datetime.now(timezone.utc)

    # ---------------------------------------------------------------- 活动
    ev1 = api.create_event("FTEC5520 Live Concert 2026", 1, 100, now + timedelta(days=10), 2, False, "organizer")
    record("T01", "创建活动（原价1 ETH / 限量100 / 限购2）", "organizer", ev1, "成功", "演出在 10 天后")
    event1 = api.get_next_event_id() - 1

    ev2 = api.create_event("Last-Minute Night (≤7天)", 0.5, 50, now + timedelta(days=3), 2, False, "organizer")
    record("T01b", "创建临近演出活动（0.5 ETH / 3 天后）", "organizer", ev2, "成功", "用于动态限价 100% 场景")
    event2 = api.get_next_event_id() - 1

    ev3 = api.create_event("Presale Only Event", 0.8, 20, now + timedelta(days=14), 2, True, "organizer")
    record("T01c", "创建预售活动（presaleActive=true）", "organizer", ev3, "成功")
    event3 = api.get_next_event_id() - 1
    record("T02", "白名单批量写入 buyerA / buyerB", "organizer",
           api.set_whitelist(event3, ["buyerA", "buyerB"], True, "organizer"), "成功")

    # ---------------------------------------------------------------- 购票
    r = record("T03", "buyerA 在预售期购票 1 张", "buyerA", api.buy_ticket(event3, "buyerA", 1), "成功")
    presale_token = r.extra.get("first_token_id") if isinstance(r, TxResult) else None

    record("T04", "attacker（非白名单）在预售期购票", "attacker",
           api.buy_ticket(event3, "attacker", 1), "失败", "预期 revert: Wallet is not whitelisted")

    r1 = record("T05a", "buyerA 一级购票 1 张（活动1）", "buyerA", api.buy_ticket(event1, "buyerA", 1), "成功")
    token_a1 = r1.extra.get("first_token_id")
    r2 = record("T05b", "buyerA 再购 1 张（达限购 2）", "buyerA", api.buy_ticket(event1, "buyerA", 1), "成功")
    token_a2 = r2.extra.get("first_token_id")
    record("T05c", "buyerB 一级购票 1 张（活动1）", "buyerB", api.buy_ticket(event1, "buyerB", 1), "成功")
    record("T06", "attacker 超额购买 3 张（限购 2）", "attacker",
           api.buy_ticket(event1, "attacker", 3), "失败", "预期 revert: Wallet limit exceeded")

    # 售罄场景：单独建一个只有 1 张票的活动
    ev4 = api.create_event("Sold Out Test", 0.2, 1, now + timedelta(days=20), 1, False, "organizer")
    event4 = api.get_next_event_id() - 1
    record("T06b", "attacker 买下唯一一张票", "attacker", api.buy_ticket(event4, "attacker", 1), "成功")
    record("T06c", "buyerB 在售罄后继续购买", "buyerB",
           api.buy_ticket(event4, "buyerB", 1), "失败", "预期 revert: Not enough tickets")

    # ---------------------------------------------------------------- 绕过路径
    # 直接调用被 override 的 transferFrom：这里真的发一笔交易，拿到 status=0 的回执作为证据
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
        "holder 直接调用 transferFrom 转票",
        "buyerA",
        {
            "ok": bypass_receipt.status == 1,
            "function": "transferFrom",
            "tx_hash": "0x" + bypass_hash.hex().removeprefix("0x"),
            "block_number": bypass_receipt.blockNumber,
            "gas_used": bypass_receipt.gasUsed,
            "error": "execution reverted（status=0）" if bypass_receipt.status == 0 else None,
        },
        "失败",
        "合约 override 后直接 revert，交易上链但 status=0",
    )

    # ---------------------------------------------------------------- 限价
    record("T08", "buyerA 以 1.5 ETH 挂牌（原价 1 ETH）", "buyerA",
           api.list_ticket(token_a1, 1.5, "buyerA"), "失败", "预期 revert: Price exceeds dynamic limit")
    record("T12", "非票主 attacker 给 token 挂牌", "attacker",
           api.list_ticket(token_a1, 1.1, "attacker"), "失败", "预期 revert: Not the owner")

    # 临近演出活动：上限 = 100%
    record("T09a", "buyerB 买下活动2 的票", "buyerB", api.buy_ticket(event2, "buyerB", 1), "成功")
    token_b2 = api.get_next_token_id() - 1
    record("T09", "距演出 3 天，以 0.6 ETH 挂牌（上限 0.5）", "buyerB",
           api.list_ticket(token_b2, 0.6, "buyerB"), "失败", "预期 revert: Price exceeds dynamic limit")
    record("T09b", "距演出 3 天，以 0.5 ETH（=100%）挂牌", "buyerB",
           api.list_ticket(token_b2, 0.5, "buyerB"), "成功", "临近演出时上限降到原价")

    # ---------------------------------------------------------------- 合法转售
    record("T07a", "buyerA 以 1.2 ETH（=120%）挂牌", "buyerA",
           api.list_ticket(token_a1, 1.2, "buyerA"), "成功")
    r = record("T07", "buyerB 买入转售门票", "buyerB", api.buy_resale(token_a1, "buyerB"), "成功")
    print(f"      转售后 ownerOf({token_a1}) = {api.get_ticket_owner(token_a1)}")

    # ---------------------------------------------------------------- 转售次数（3 次上限）
    # T07 已经完成第 1 次转售，这里再转 2 次，使 resaleCount 达到上限 3
    seller, buyer = "buyerB", "buyerA"
    for i in range(2):
        listed = api.list_ticket(token_a1, 1.1, seller)
        if not listed.ok:
            sys.exit(f"第 {i + 2} 次挂牌意外失败：{listed.error}")
        res = api.buy_resale(token_a1, buyer)
        if not res.ok:
            sys.exit(f"第 {i + 2} 次转售意外失败：{res.error}")
        print(f"      第 {i + 2} 次转售成功: tx={res.tx_hash} gas={res.gas_used} "
              f"resaleCount={api.get_ticket(token_a1)['resale_count']}")
        seller, buyer = buyer, seller

    owner_role = next(
        r for r, a in api.get_accounts().items() if a.lower() == api.get_ticket_owner(token_a1).lower()
    )
    record("T10", "第 4 次挂牌（resaleCount 已达 3）", owner_role,
           api.list_ticket(token_a1, 1.1, owner_role), "失败",
           "预期 revert: Max resale limit reached")

    # ---------------------------------------------------------------- 核销
    record("T17", "attacker（未授权）执行 checkIn", "attacker",
           api.check_in(presale_token, "attacker"), "失败", "预期 revert: Not an authorized verifier")
    record("T13", "owner 授权 verifier", "deployer", api.set_verifier("verifier", True, "deployer"), "成功")
    record("T15", "verifier 首次核销 token", "verifier", api.check_in(presale_token, "verifier"), "成功")
    record("T16", "同一张票再次核销", "verifier", api.check_in(presale_token, "verifier"), "失败",
           "预期 revert: Ticket already used")

    # ---------------------------------------------------------------- 保留一个在售状态给页面展示
    record("T07c", "attacker 为活动1买 1 张作为页面展示品", "attacker",
           api.buy_ticket(event1, "attacker", 1), "成功")
    display_token = api.get_next_token_id() - 1
    record("T07d", "该票以 1.2 ETH 挂牌（留作页面演示）", "attacker",
           api.list_ticket(display_token, 1.2, "attacker"), "成功")

    # ---------------------------------------------------------------- 汇总
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
    print(f"共 {payload['summary']['total']} 条，PASS {payload['summary']['pass']}，"
          f"FAIL {payload['summary']['fail']}")
    print(f"证据文件: {RESULTS / 'tx_evidence.json'}")
    print(f"报告表格: {RESULTS / 'demo_report.md'}")


def write_markdown(payload: dict) -> None:
    net = payload["network"]
    lines = [
        "# FTEC5520 防黄牛票务系统 — 链上运行证据",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 网络：私有链 chainId `{net['chain_id']}`，RPC `{net['rpc_url']}`",
        f"- 合约地址：`{net['contract_address']}`",
        f"- 部署交易：`{net['deploy_tx']}`（区块 {net['deploy_block']}）",
        "",
        "## 测试明细",
        "",
        "| ID | 场景 | 操作账户 | 预期 | 实际 | 结果 | Tx Hash | 区块 | Gas |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in payload["steps"]:
        actual = "成功" if s["ok"] else f"拒绝：{s['error']}"
        lines.append(
            f"| {s['test_id']} | {s['action']} | {s['actor']} | {s['expected']} | {actual} | "
            f"{'✅ PASS' if s['pass'] else '❌ FAIL'} | `{s['tx_hash'] or '—'}` | "
            f"{s['block_number'] or '—'} | {s['gas_used'] or '—'} |"
        )
    lines += [
        "",
        "## 汇总",
        "",
        f"- 用例总数：{payload['summary']['total']}，通过 {payload['summary']['pass']}，"
        f"失败 {payload['summary']['fail']}",
        f"- 最终区块高度：{net['final_block']}",
        f"- 门票总数：{payload['state']['tokens']}，当前在售：{payload['state']['listed']}",
        "",
        "> 说明：`pass` 的判定同时考虑预期方向——预期「失败」的用例必须真的被合约拒绝才算 PASS。",
    ]
    (RESULTS / "demo_report.md").write_text("\n".join(lines), "utf-8")


if __name__ == "__main__":
    main()
