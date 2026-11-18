#!/usr/bin/env python
"""成员 5 交付 —— 端到端 / 异常 / 对抗测试套件。

覆盖任务书第 09 节的 18 项测试（T01–T18），并补充：
  * 绕过前端（直接用 Web3.py 打合约）的对抗测试  —— 证明规则不在页面里；
  * 边界测试（恰好 7 天、售罄、已核销再挂牌、自买自卖、错误付款金额、演出开始后操作）；
  * 真实"失败交易"上链证据 —— 强制用固定 gas 发交易，拿到 status=0 的回执与 gas 消耗。

设计原则
--------
1. 每个用例单独创建活动，用例之间不共享状态，可重复运行（重复 run 只会产生新的
   eventId / tokenId，不需要重部署合约）。
2. 判定口径与任务书一致：预期「失败」的用例必须真的被合约拒绝才算 PASS。
3. 每条用例都记录：预期 / 实际 / PASS-FAIL / tx_hash / block / gas / revert 原因。
4. 负向用例同时记录两条证据：
   - 预检路径（estimate_gas 捕获 revert，不发交易、不花 gas）；
   - 强制上链路径（固定 gas 发交易，得到 status=0 的真实回执，gas 确实被扣除）。
   这两者正好构成报告里"为什么要有链上规则 + 失败也要付 gas"的实证。

输出
----
    results/test_results.csv       测试结果总表（UTF-8 BOM，Excel 可直接打开）
    results/test_evidence.json     完整证据（含环境、每一步的 tx/gas、汇总统计）
    results/test_environment.json  测试环境快照
    results/gas_data.csv           Gas 对比用的原始数据

用法
----
    ./blockchain/start_node.sh            # 启动私有链
    python backend/deploy.py              # 部署合约（首次或换链后）
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
ZERO = "0x0000000000000000000000000000000000000000"

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
# 记录与判定
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
    icon = {"PASS": "✅", "FAIL": "❌", "DEVIATION": "⚠️"}.get(verdict, "•")
    print(
        f"[{icon} {verdict:<9}] {test_id:<7} {scenario[:44]:<46} "
        f"tx={row['tx_hash'][:12] + '…' if row['tx_hash'] else '—':<14} "
        f"gas={row['gas_used'] or '—':<8}"
        + (f" reason={revert_reason}" if revert_reason else "")
    )
    return row


def case_ok(test_id, module, owner, scenario, actor, input_desc, result: TxResult | dict,
            expected="成功", checks: dict | None = None, screenshot="", note="", kind="normal"):
    """正向用例：必须 ok=True。checks 为额外的链上状态断言。"""
    data = result.to_dict() if isinstance(result, TxResult) else dict(result)
    ok = bool(data.get("ok"))
    failed_checks = {k: v for k, v in (checks or {}).items() if not v}
    verdict = "PASS" if ok and not failed_checks else "FAIL"
    actual = "成功"
    if not ok:
        actual = f"被拒绝：{data.get('error')}"
    elif failed_checks:
        actual = f"交易成功但状态断言失败：{', '.join(failed_checks)}"
    return record(
        test_id, module, owner, scenario, actor, input_desc, expected, actual, verdict,
        tx=data, revert_reason="" if ok else (data.get("error") or ""),
        screenshot=screenshot, kind=kind,
        note=note + ("; " + json.dumps({k: bool(v) for k, v in checks.items()}, ensure_ascii=False)
                     if checks else ""),
    )


def case_reject(test_id, module, owner, scenario, actor, input_desc, result, expected_reason: str,
                tx: dict | None = None, expected="拒绝", checks: dict | None = None,
                screenshot="", note="", kind="negative"):
    """负向用例：必须 ok=False，且 revert 原因命中 expected_reason。"""
    data = result.to_dict() if isinstance(result, TxResult) else dict(result)
    ok = bool(data.get("ok"))
    reason = data.get("error") or ""
    reason_hit = expected_reason.lower() in reason.lower() if expected_reason else True
    failed_checks = {k: v for k, v in (checks or {}).items() if not v}
    verdict = "PASS" if (not ok and reason_hit and not failed_checks) else "FAIL"
    if ok:
        actual = "⚠️ 交易竟然成功——规则没有生效"
    elif not reason_hit:
        actual = f"被拒绝，但原因不符：{reason}"
    elif failed_checks:
        actual = f"被拒绝，但状态断言失败：{', '.join(failed_checks)}"
    else:
        actual = f"拒绝：{reason}"
    # 负向用例的 tx 信息优先取"强制上链"的那一笔
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
        except Exception:  # noqa: BLE001  预检路径没有 tx，忽略
            pass
    return record(
        test_id, module, owner, scenario, actor, input_desc, expected, actual, verdict,
        tx=merged, revert_reason=reason, screenshot=screenshot, kind=kind,
        note=note + ("; " + json.dumps({k: bool(v) for k, v in checks.items()}, ensure_ascii=False)
                     if checks else ""),
    )


def case_deviation(test_id, module, owner, scenario, actor, input_desc, actual, note="",
                   expected="按任务书：应被拒绝"):
    return record(test_id, module, owner, scenario, actor, input_desc,
                  expected, actual, "DEVIATION", note=note, kind="deviation")


# ----------------------------------------------------------------------
# 链上辅助
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
    """建一个专用活动，返回 eventId（用例之间互不干扰）。"""
    r = api.create_event(name, price, supply, now() + timedelta(days=days), limit, presale, "organizer")
    if not r.ok:
        sys.exit(f"创建活动失败：{r.error}")
    _collect_gas("createEvent", r, "setup")
    return int(r.extra["event_id"])


def buy(event_id: int, role: str, qty: int = 1):
    """一级购票，返回 (TxResult, 第一张 tokenId)。"""
    r = api.buy_ticket(event_id, role, qty)
    token = int(r.extra["first_token_id"]) if r.ok else None
    return r, token


def precheck(fn, role: str, value: int = 0) -> str:
    """只读预检：模拟调用，拿到 revert 原因，不发交易、不花 gas。"""
    try:
        fn.estimate_gas({"from": addr(role), "value": value})
        return ""
    except Exception as exc:  # noqa: BLE001
        return clean_revert(exc)


def force_send(fn, role: str, value: int = 0, gas: int = 500_000) -> dict:
    """绕过 backend 的封装，直接用固定 gas 发交易。

    用于制造真实的 status=0 回执：证明失败的交易同样上链、同样消耗 gas。
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
    return {
        "tx_hash": hx(tx_hash),
        "block_number": receipt.blockNumber,
        "gas_used": receipt.gasUsed,
        "status": receipt.status,
        "ok": receipt.status == 1,
        "error": "" if receipt.status == 1 else "execution reverted（status=0）",
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
# 环境快照
# ----------------------------------------------------------------------
def environment() -> dict:
    status = api.get_chain_status()
    settings = api.get_settings()
    build = json.loads((ROOT / "contracts/build/ConcertTicket.json").read_text("utf-8"))
    try:
        geth_version = subprocess.run(
            [str(ROOT / "tools/geth"), "version"], capture_output=True, text=True, timeout=20
        ).stdout.splitlines()[0]
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
            "consensus": "Clique PoA（2 秒出块，单节点）",
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
# 用例
# ======================================================================
def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def test_primary_market():
    """成员 2：活动创建、权限、白名单预售、限购、库存。"""
    section("成员 2 · 一级市场（T01–T06）")

    before_token = api.get_next_token_id()
    ev = fresh_event("T01 Anti-Scalping Live 2026", 1, 10, 10, 2)
    event = api.get_event(ev)
    case_ok(
        "T01", "M2 一级市场", "成员2", "主办方创建活动（1 ETH / 10 张 / 限购 2 / 10 天后）", "organizer",
        f"createEvent(name, price=1 ETH, maxSupply=10, eventTime=+10d, walletLimit=2, presale=false) → eventId={ev}",
        {"ok": event is not None},
        expected="成功，eventId / 库存 / 票价可读",
        checks={
            "eventId 返回": ev >= 1,
            "名称一致": (event or {}).get("name") == "T01 Anti-Scalping Live 2026",
            "票价 1 ETH": (event or {}).get("price_eth") == 1.0,
            "总票数 10": (event or {}).get("max_supply") == 10,
            "限购 2": (event or {}).get("wallet_limit") == 2,
            "默认开售": bool((event or {}).get("active")),
            "未售出": (event or {}).get("sold") == 0,
            "剩余 10": api.remaining_supply(ev) == 10,
        },
        screenshot="02_events.png",
        note=f"nextTokenId 建活动前={before_token}；活动创建不铸造门票，铸造发生在购票时",
    )

    # T02 权限：非 organizer 管理他人活动
    reject = api.set_event_active(ev, False, "attacker")
    tx = force_send(contract().functions.setEventActive(ev, False), "attacker", gas=120_000)
    case_reject(
        "T02", "M2 一级市场", "成员2", "非主办方修改他人活动售票状态", "attacker",
        f"setEventActive({ev}, false) 由 attacker 调用",
        reject, "Not event manager", tx=tx,
        checks={"活动仍为开售": bool(api.get_event(ev)["active"])},
        note="同时验证 setWhitelist 同样受 onlyEventManager 保护（见 note_steps）",
    )
    whitelist_reject = api.set_whitelist(ev, "attacker", True, "attacker")
    STEPS.append({"step": "T02-whitelist", "ok": not whitelist_reject.ok,
                  "error": whitelist_reject.error})
    print(f"       └ 非主办方写白名单：{whitelist_reject.error}")

    # T02 偏差：createEvent 是 permissionless（成员 2 的设计）
    own = api.create_event("Attacker Owned Event", 0.1, 5, now() + timedelta(days=5), 1, False, "attacker")
    case_deviation(
        "T02b", "M2 一级市场", "成员5", "普通账户（非平台主办方）自行创建活动", "attacker",
        "createEvent(...) 由 attacker 调用",
        f"成功：eventId={own.extra.get('event_id')}，attacker 成为该活动 organizer"
        if own.ok else f"被拒绝：{own.error}",
        note="合约设计为 permissionless 发活动（成员 2 交接文档 §3.1）；"
             "只有该活动的 organizer 能管理它，不影响购票/转售/核销规则，但报告需说明“假活动”风险",
    )

    # T03 / T04 预售白名单
    ev_pre = fresh_event("T03 Presale Only Event", 0.8, 20, 14, 2, presale=True)
    wl = api.set_whitelist(ev_pre, ["buyerA"], True, "organizer")
    _collect_gas("setWhitelistBatch(1)", wl, "setup")
    r3, tok3 = buy(ev_pre, "buyerA", 1)
    _collect_gas("purchaseTickets(1)", r3, "T03")
    case_ok(
        "T03", "M2 一级市场", "成员2", "白名单用户在预售期购票", "buyerA",
        f"setWhitelist({ev_pre}, buyerA, true) → purchaseTickets({ev_pre}, 1) value=0.8 ETH",
        r3, expected="成功，ownerOf 更新为 buyerA",
        checks={"ownerOf == buyerA": tok3 is not None and api.get_ticket_owner(tok3) == addr("buyerA"),
                "票属于该活动": api.get_ticket(tok3)["event_id"] == ev_pre,
                "已售 1": api.get_event(ev_pre)["sold"] == 1},
        screenshot="03_buy_tickets.png",
        note=f"铸造 tokenId={tok3}",
    )

    r4 = api.buy_ticket(ev_pre, "attacker", 1)
    tx4 = force_send(contract().functions.purchaseTickets(ev_pre, 1), "attacker", value=wei(0.8), gas=300_000)
    case_reject(
        "T04", "M2 一级市场", "成员2", "非白名单用户在预售期购票", "attacker",
        f"purchaseTickets({ev_pre}, 1) value=0.8 ETH（attacker 不在白名单）",
        r4, "Wallet is not whitelisted", tx=tx4,
        checks={"库存未被扣减": api.get_event(ev_pre)["sold"] == 1},
        screenshot="03_buy_tickets.png",
    )

    # T05 限购
    ev_lim = fresh_event("T05 Wallet Limit Event", 0.5, 10, 10, 2)
    r5a, _ = buy(ev_lim, "buyerA", 2)  # 一次买满 2 张
    _collect_gas("purchaseTickets(2)", r5a, "T05")
    case_ok("T05a", "M2 一级市场", "成员2", "一次购买 2 张（等于限购上限）", "buyerA",
            f"purchaseTickets({ev_lim}, 2) value=1.0 ETH", r5a,
            checks={"purchasedByWallet == 2": api.purchased_count(ev_lim, "buyerA") == 2},
            note="同时作为 purchaseTickets 批量铸造的 gas 样本")
    r5b = api.buy_ticket(ev_lim, "buyerA", 1)
    tx5 = force_send(contract().functions.purchaseTickets(ev_lim, 1), "buyerA", value=wei(0.5), gas=300_000)
    case_reject(
        "T05b", "M2 一级市场", "成员2", "超过每钱包限购（已买 2 张，再买 1 张）", "buyerA",
        f"purchaseTickets({ev_lim}, 1) value=0.5 ETH", r5b, "Wallet limit exceeded", tx=tx5,
        checks={"购买计数仍为 2": api.purchased_count(ev_lim, "buyerA") == 2},
        screenshot="03_buy_tickets.png",
    )

    # T06 售罄
    ev_sold = fresh_event("T06 Sold Out Event", 0.2, 1, 20, 1)
    r6a, _ = buy(ev_sold, "buyerB", 1)
    case_ok("T06a", "M2 一级市场", "成员2", "售罄前最后一张被买走", "buyerB",
            f"purchaseTickets({ev_sold}, 1) value=0.2 ETH", r6a,
            checks={"剩余 0": api.remaining_supply(ev_sold) == 0})
    r6b = api.buy_ticket(ev_sold, "attacker", 1)
    tx6 = force_send(contract().functions.purchaseTickets(ev_sold, 1), "attacker", value=wei(0.2), gas=300_000)
    case_reject(
        "T06b", "M2 一级市场", "成员2", "库存售罄后继续购买", "attacker",
        f"purchaseTickets({ev_sold}, 1) value=0.2 ETH", r6b, "Not enough tickets", tx=tx6,
        screenshot="03_buy_tickets.png",
    )

    # E04 付款金额错误（任务书外补充）
    ev_pay = fresh_event("E04 Wrong Payment Event", 0.3, 5, 10, 2)
    wrong = contract().functions.purchaseTickets(ev_pay, 1)
    reason = precheck(wrong, "attacker", value=wei(0.1))
    tx_pay = force_send(wrong, "attacker", value=wei(0.1), gas=200_000)
    case_reject(
        "E04", "M2 一级市场", "成员5", "付款金额与「票价 × 数量」不一致", "attacker",
        f"purchaseTickets({ev_pay}, 1) value=0.1 ETH（应付 0.3 ETH）",
        {"ok": False, "error": reason}, "Incorrect ETH amount", tx=tx_pay,
        note="合约用 msg.value == price*quantity 严格校验，不存在少付款的路径",
    )


def test_anti_scalping():
    """成员 3：限价转售、次数上限、防绕过、核销。"""
    section("成员 3 · 防黄牛转售与核销（T07–T12、T15–T17）")

    ev = fresh_event("T07 Resale Market Event", 1, 10, 10, 2)
    _, token = buy(ev, "buyerA", 1)
    fee_before = pending_fee_wei()  # 5% 平台手续费
    bal_before = balance("buyerA")

    # T08 超价（先做负向，避免污染 T07 的挂牌状态）
    over = api.list_ticket(token, 1.3, "buyerA")
    tx8 = force_send(contract().functions.listForResale(token, wei(1.3)), "buyerA", gas=200_000)
    case_reject(
        "T08", "M3 防黄牛", "成员3", "挂牌价超过静态上限（120%）", "buyerA",
        f"listForResale({token}, 1.3 ETH)，原价 1 ETH，上限 1.2 ETH",
        over, "Price exceeds dynamic limit", tx=tx8,
        checks={"未产生挂牌": not api.get_ticket(token)["is_listed"]},
        screenshot="05_resale_market.png",
    )

    cap = api.get_max_resale_price(token)
    case_ok("T08b", "M3 防黄牛", "成员3", "读取动态限价（距演出 10 天 → 120%）", "只读",
            f"getMaxResalePrice({token})", {"ok": True},
            expected="返回 1.2 ETH",
            checks={"上限 = 1.2 ETH": cap.get("max_price_eth") == 1.2},
            note=f"返回 {cap.get('max_price_eth')} ETH")

    # T12 非票主挂牌
    t12 = api.list_ticket(token, 1.1, "attacker")
    tx12 = force_send(contract().functions.listForResale(token, wei(1.1)), "attacker", gas=200_000)
    case_reject(
        "T12", "M3 防黄牛", "成员3", "非票主给他人门票挂牌", "attacker",
        f"listForResale({token}, 1.1 ETH) 由 attacker 调用（票主是 buyerA）",
        t12, "Not the owner", tx=tx12,
        screenshot="05_resale_market.png",
    )

    # T07 合法转售
    r7 = api.list_ticket(token, 1.2, "buyerA")
    _collect_gas("listForResale", r7, "T07")
    case_ok("T07a", "M3 防黄牛", "成员3", "持票人以 120% 上限挂牌", "buyerA",
            f"listForResale({token}, 1.2 ETH)", r7,
            checks={"isListed=true": api.get_ticket(token)["is_listed"],
                    "挂牌价 1.2": api.get_ticket(token)["listing_price_eth"] == 1.2},
            screenshot="05_resale_market.png")

    r7b = api.buy_resale(token, "buyerB")
    _collect_gas("buyResale", r7b, "T07")
    ticket_after = api.get_ticket(token)
    bal_after = balance("buyerA")
    fee_delta = (pending_fee_wei() - fee_before) / 1e18
    case_ok("T07b", "M3 防黄牛", "成员3", "他人买入转售门票（所有权变更 + 次数 +1）", "buyerB",
            f"buyResale({token}) value=1.2 ETH", r7b,
            expected="成功，ownerOf 改变，resaleCount +1",
            checks={"ownerOf == buyerB": ticket_after["owner"] == addr("buyerB"),
                    "resaleCount == 1": ticket_after["resale_count"] == 1,
                    "挂牌已取消": not ticket_after["is_listed"],
                    "平台费 = 0.06 ETH": abs(fee_delta - 0.06) < 1e-9},
            screenshot="05_resale_market.png",
            note=f"卖方到账 +{(bal_after - bal_before):.4f} ETH（1.2 − 5% 平台费，未计自身 gas）")

    # E08 / E05 重复挂牌 + 取消后购买
    again = api.list_ticket(token, 1.1, "buyerB")
    tx_again = force_send(contract().functions.listForResale(token, wei(1.1)), "buyerB", gas=200_000)
    case_reject("E08", "M3 防黄牛", "成员5", "同一张票重复挂牌", "buyerB",
                f"先 listForResale({token}, 1.1) 再调用一次同一函数",
                again, "Already listed", tx=tx_again,
                note="第二次调用被拒（第一次挂牌已成功）")

    cancel = api.cancel_listing(token, "buyerB")
    case_ok("E05a", "M3 防黄牛", "成员3", "票主取消挂牌", "buyerB",
            f"cancelListing({token})", cancel,
            checks={"isListed=false": not api.get_ticket(token)["is_listed"]})
    buy_cancelled = api.buy_resale(token, "buyerA")
    tx_cancel = force_send(contract().functions.buyResale(token), "buyerA", value=wei(1.1), gas=300_000)
    case_reject("E05b", "M3 防黄牛", "成员5", "购买已取消挂牌的门票", "buyerA",
                f"buyResale({token}) value=1.1 ETH（该票已取消挂牌）",
                buy_cancelled, "Not listed for resale", tx=tx_cancel)

    # T10 转售次数上限（3 次）：当前 resaleCount = 1，再转 2 次
    seller, buyer = "buyerB", "buyerA"
    for i in (2, 3):
        listed = api.list_ticket(token, 1.1, seller)
        if not listed.ok:
            sys.exit(f"第 {i} 次挂牌意外失败：{listed.error}")
        res = api.buy_resale(token, buyer)
        if not res.ok:
            sys.exit(f"第 {i} 次转售意外失败：{res.error}")
        _collect_gas("buyResale", res, f"T10-{i}")
        print(f"       └ 第 {i} 次转售 ok，resaleCount={api.get_ticket(token)['resale_count']}")
        seller, buyer = buyer, seller
    case_ok("T10a", "M3 防黄牛", "成员3", "连续转售至第 3 次（上限）", "buyerA/buyerB",
            "listForResale → buyResale ×2", {"ok": True},
            expected="成功，resaleCount = 3",
            checks={"resaleCount == 3": api.get_ticket(token)["resale_count"] == 3},
            note="累计第 1 次来自 T07b，本步完成第 2、3 次")
    owner_role = "buyerB" if api.get_ticket_owner(token) == addr("buyerB") else "buyerA"
    fourth = api.list_ticket(token, 1.1, owner_role)
    tx10 = force_send(contract().functions.listForResale(token, wei(1.1)), owner_role, gas=200_000)
    case_reject("T10b", "M3 防黄牛", "成员3", "第 4 次挂牌（已达转售次数上限 3）", owner_role,
                f"listForResale({token}, 1.1 ETH)", fourth, "Max resale limit reached",
                tx=tx10, checks={"仍未挂牌": not api.get_ticket(token)["is_listed"]})

    # T11 直接转移绕过（两个入口都试）
    _, token_bypass = buy(ev, "buyerA", 1)
    tf = contract().functions["transferFrom(address,address,uint256)"]
    tx11a = force_send(tf(addr("buyerA"), addr("attacker"), token_bypass), "buyerA", gas=150_000)
    case_reject(
        "T11a", "M3 防黄牛", "成员3", "持票人直接调用 ERC-721 transferFrom 绕过转售规则", "buyerA",
        f"transferFrom(buyerA → attacker, tokenId={token_bypass})，固定 gas 150k 强制上链",
        {"ok": tx11a["status"] == 1, "error": "execution reverted（status=0）"}, "execution reverted",
        tx=tx11a,
        checks={"ownerOf 未变": api.get_ticket_owner(token_bypass) == addr("buyerA")},
        screenshot="05_resale_market.png",
        note="交易真实上链但 status=0；gas 照扣——这是最有力的一条「规则在链上」证据",
    )
    stf = contract().functions["safeTransferFrom(address,address,uint256)"]
    tx11b = force_send(stf(addr("buyerA"), addr("attacker"), token_bypass), "buyerA", gas=150_000)
    case_reject(
        "T11b", "M3 防黄牛", "成员3", "持票人直接调用 safeTransferFrom 绕过转售规则", "buyerA",
        f"safeTransferFrom(buyerA → attacker, tokenId={token_bypass})",
        {"ok": tx11b["status"] == 1, "error": "execution reverted（status=0）"}, "execution reverted",
        tx=tx11b,
        checks={"ownerOf 未变": api.get_ticket_owner(token_bypass) == addr("buyerA")},
        note="两个转账入口都被 override 成 revert；页面/脚本都无法绕过",
    )

    # T09 动态限价：临近演出（3 天）上限降到 100%
    ev_near = fresh_event("T09 Near-Event (3 days)", 0.5, 10, 3, 2)
    _, token_near = buy(ev_near, "buyerB", 1)
    near_cap = api.get_max_resale_price(token_near)
    case_ok("T09a", "M3 防黄牛", "成员3", "读取动态限价（距演出 3 天 → 100%）", "只读",
            f"getMaxResalePrice({token_near})（原价 0.5 ETH）", {"ok": True},
            expected="返回 0.5 ETH",
            checks={"上限 = 0.5 ETH": near_cap.get("max_price_eth") == 0.5},
            note=f"返回 {near_cap.get('max_price_eth')} ETH")
    over_near = api.list_ticket(token_near, 0.51, "buyerB")
    tx9 = force_send(contract().functions.listForResale(token_near, wei(0.51)), "buyerB", gas=200_000)
    case_reject("T09b", "M3 防黄牛", "成员3", "临近演出时超过动态上限挂牌", "buyerB",
                f"listForResale({token_near}, 0.51 ETH)，7 天内上限 0.5 ETH",
                over_near, "Price exceeds dynamic limit", tx=tx9,
                screenshot="05_resale_market.png")
    ok_near = api.list_ticket(token_near, 0.5, "buyerB")
    case_ok("T09c", "M3 防黄牛", "成员3", "临近演出时刚好等于上限（0.5 ETH）挂牌", "buyerB",
            f"listForResale({token_near}, 0.5 ETH)", ok_near,
            checks={"isListed=true": api.get_ticket(token_near)["is_listed"]},
            note="边界值：price <= maxPrice 允许")
    api.cancel_listing(token_near, "buyerB")

    # T09d 恰好 7 天的边界
    ev_edge = fresh_event("T09d Exactly 7 Days", 1, 4, 7, 2)
    _, tok_edge = buy(ev_edge, "buyerA", 2)
    tok_edge2 = tok_edge + 1          # 第二张票用于超价比对，避免"重复挂牌"干扰判定
    edge_cap = api.get_max_resale_price(tok_edge)
    edge_ok = api.list_ticket(tok_edge, 1.0, "buyerA")
    edge_over = api.list_ticket(tok_edge2, 1.01, "buyerA")
    case_ok("T09d", "M3 防黄牛", "成员5", "距演出恰好 7 天的限价边界", "buyerA",
            f"getMaxResalePrice({tok_edge}) → 1.0 ETH；token{tok_edge} list 1.0 成功 / "
            f"token{tok_edge2} list 1.01 被拒",
            edge_ok,
            expected="上限切到 100%：1.0 可挂牌，1.01 被拒",
            checks={"上限 = 1.0 ETH": edge_cap.get("max_price_eth") == 1.0,
                    "超 1 wei 被拒": not edge_over.ok},
            note=f"挂牌 1.0 结果 {'成功' if edge_ok.ok else edge_ok.error}；"
                 f"挂牌 1.01 结果 {edge_over.error or '成功'}")
    api.cancel_listing(tok_edge, "buyerA")

    return token, token_bypass, ev


def test_qr_and_checkin(token_owner_ctx: dict):
    """成员 4 的二维码 + 成员 3 的核销。"""
    section("成员 4 / 成员 3 · 二维码验票与链上核销（T13–T17）")

    ev = fresh_event("T13 QR Check-in Event", 0.3, 5, 10, 2)
    _, token = buy(ev, "buyerB", 1)
    holder = addr("buyerB")

    # T13 合法 QR
    payload = qr_utils.create_ticket_qr(token, holder, api.signing_key("buyerB"), ttl=180)
    png = qr_utils.make_qr_png(payload)
    result = qr_utils.verify_payload(payload, api.get_ticket(token))
    case_ok(
        "T13", "M4 验票/QR", "成员4", "合法持票人生成短时二维码并验签", "buyerB",
        f"create_ticket_qr(token={token}, holder=buyerB, ttl=180) → verify_payload",
        {"ok": result["ok"]},
        expected="5 项检查全部通过",
        checks={c["check"]: c["ok"] for c in result["checks"]},
        screenshot="04_my_tickets.png",
        note=f"二维码 PNG {len(png)} bytes；payload 含 token_id/holder/nonce/expires_at/EIP-191 签名",
    )

    # T14a 伪签
    forged = qr_utils.create_ticket_qr(token, holder, api.signing_key("attacker"), ttl=180)
    res_forged = qr_utils.verify_payload(forged, api.get_ticket(token))
    case_reject("T14a", "M4 验票/QR", "成员4", "攻击者伪造持票人签名", "attacker",
                "用 attacker 私钥签 buyerB 的 holder 字段",
                {"ok": res_forged["ok"], "error": "signature mismatch"},
                "signature mismatch",
                checks={"签名校验失败": not _check_ok(res_forged, "Signature matches holder")},
                note=f"recovered={res_forged['recovered']}")
    # T14b 过期
    expired = qr_utils.create_ticket_qr(token, holder, api.signing_key("buyerB"), ttl=-30)
    res_expired = qr_utils.verify_payload(expired, api.get_ticket(token))
    case_reject("T14b", "M4 验票/QR", "成员4", "二维码已过期（截图转发场景）", "buyerB",
                "ttl=-30 生成，expires_at 已过期",
                {"ok": res_expired["ok"], "error": "expired"}, "expired",
                checks={"有效期校验失败": not _check_ok(res_expired, "Not expired")})
    # T14c 旧票主：把票转售后再用旧 QR
    ev_old = fresh_event("T14 Old Owner Event", 0.4, 5, 10, 2)
    _, tok_old = buy(ev_old, "buyerA", 1)
    old_qr = qr_utils.create_ticket_qr(tok_old, addr("buyerA"), api.signing_key("buyerA"), ttl=180)
    api.list_ticket(tok_old, 0.48, "buyerA")   # 120% = 0.48
    resale = api.buy_resale(tok_old, "buyerB")
    if not resale.ok:
        sys.exit(f"T14c 转售失败：{resale.error}")
    res_old = qr_utils.verify_payload(old_qr, api.get_ticket(tok_old))
    case_reject("T14c", "M4 验票/QR", "成员4", "转售成功后旧票主的二维码", "buyerA",
                "buyerA 生成 QR → 转售给 buyerB → 用旧 QR 验票",
                {"ok": res_old["ok"], "error": "ownerOf mismatch"}, "ownerOf mismatch",
                checks={"链上票主校验失败": not _check_ok(res_old, "Matches on-chain ownerOf")},
                note=f"当前 ownerOf={api.get_ticket_owner(tok_old)}，QR holder={addr('buyerA')}")

    # T17 未授权核销
    unauth = api.check_in(token, "attacker")
    tx17 = force_send(contract().functions.checkIn(token), "attacker", gas=150_000)
    case_reject("T17", "M4 验票/QR", "成员3", "无核销权限的账户调用 checkIn", "attacker",
                f"checkIn({token}) 由 attacker 调用", unauth, "Not an authorized verifier",
                tx=tx17, checks={"used 仍为 false": not api.get_ticket(token)["used"]},
                screenshot="06_staff_checkin.png")

    # T15 授权 + 首次核销
    grant = api.set_verifier("verifier", True, "deployer")
    case_ok("T15a", "M4 验票/QR", "成员3", "合约 owner 授权验票员", "deployer",
            "setVerifier(verifier, true)", grant,
            checks={"verifiers[verifier] = true": api.is_verifier("verifier")})
    first = api.check_in(token, "verifier")
    _collect_gas("checkIn", first, "T15")
    case_ok("T15b", "M4 验票/QR", "成员3", "授权 verifier 首次核销", "verifier",
            f"checkIn({token}) 由 verifier 调用", first,
            expected="成功，used = true",
            checks={"used = true": api.get_ticket(token)["used"]},
            screenshot="06_staff_checkin.png")

    # T16 重复核销
    second = api.check_in(token, "verifier")
    tx16 = force_send(contract().functions.checkIn(token), "verifier", gas=150_000)
    case_reject("T16", "M4 验票/QR", "成员3", "同一张票第二次核销", "verifier",
                f"checkIn({token}) 再次调用", second, "Ticket already used", tx=tx16,
                screenshot="06_staff_checkin.png")

    # E01 已核销的门票再挂牌
    used_list = api.list_ticket(token, 0.3, "buyerB")
    tx_e1 = force_send(contract().functions.listForResale(token, wei(0.3)), "buyerB", gas=200_000)
    case_reject("E01", "M3 防黄牛", "成员5", "已核销门票再次挂牌出售", "buyerB",
                f"listForResale({token}, 0.3 ETH)，该票 used=true", used_list,
                "Ticket already used", tx=tx_e1)

    # E09 核销自动解除挂牌
    _, tok_listed = buy(ev, "buyerA", 1)
    api.list_ticket(tok_listed, 0.33, "buyerA")
    listed_before = api.get_ticket(tok_listed)["is_listed"]
    check = api.check_in(tok_listed, "verifier")
    case_ok("E09", "M3 防黄牛", "成员3", "核销已挂牌门票时自动取消挂牌", "verifier",
            f"listForResale({tok_listed}, 0.33) → checkIn({tok_listed})", check,
            checks={"核销前在售": listed_before,
                    "核销后在售状态已清除": not api.get_ticket(tok_listed)["is_listed"],
                    "used = true": api.get_ticket(tok_listed)["used"]})

    # E02 自买自卖
    _, tok_self = buy(ev, "buyerA", 1)
    api.list_ticket(tok_self, 0.33, "buyerA")
    selfbuy = api.buy_resale(tok_self, "buyerA")
    tx_e2 = force_send(contract().functions.buyResale(tok_self), "buyerA", value=wei(0.33), gas=300_000)
    case_reject("E02", "M3 防黄牛", "成员5", "票主购买自己挂牌的门票（刷单）", "buyerA",
                f"buyResale({tok_self}) value=0.33 ETH，msg.sender == seller", selfbuy,
                "Cannot buy your own ticket", tx=tx_e2)
    api.cancel_listing(tok_self, "buyerA")


def test_presale_resale_whitelist():
    """E03：预售期内二手交易同样受白名单约束。"""
    section("补充用例 · 预售期二手市场的白名单约束（E03）")
    ev = fresh_event("E03 Presale Resale Event", 0.8, 10, 14, 2, presale=True)
    api.set_whitelist(ev, ["buyerA"], True, "organizer")
    _, token = buy(ev, "buyerA", 1)
    listed = api.list_ticket(token, 0.9, "buyerA")   # 120% = 0.96
    case_ok("E03a", "M3 防黄牛", "成员5", "白名单持票人在预售期挂牌", "buyerA",
            f"listForResale({token}, 0.9 ETH)", listed,
            checks={"isListed=true": api.get_ticket(token)["is_listed"]},
            note="预售期内允许挂牌（合约未禁止），限制落在买入方")
    blocked = api.buy_resale(token, "attacker")
    tx = force_send(contract().functions.buyResale(token), "attacker", value=wei(0.9), gas=300_000)
    case_reject("E03b", "M3 防黄牛", "成员5", "非白名单账户在预售期购买二手票", "attacker",
                f"buyResale({token}) value=0.9 ETH", blocked,
                "Buyer not in presale whitelist", tx=tx)
    api.cancel_listing(token, "buyerA")


def test_bypass_frontend():
    """对抗测试：完全不经过 Streamlit / ticket_api，直接用 Web3.py 打合约。"""
    section("对抗测试 · 绕过网站直接调用合约（成员 5 重点）")
    ev = fresh_event("Bypass Frontend Event", 0.6, 8, 10, 2)
    _, first = buy(ev, "buyerA", 2)     # 一次买 2 张：第 2 张用于 B02 的直转测试
    token, token2 = first, first + 1

    # B01 直接超价挂牌
    over = contract().functions.listForResale(token, wei(2.0))
    reason = precheck(over, "buyerA")
    tx = force_send(over, "buyerA", gas=200_000)
    case_reject("B01", "M5 对抗绕过", "成员5", "绕过页面直接以 2.0 ETH 挂牌（原价 0.6）", "buyerA",
                "web3 直调 listForResale，不经过 backend/ticket_api.py", {"ok": False, "error": reason},
                "Price exceeds dynamic limit", tx=tx,
                note="页面按钮 + 后端封装都不是安全边界，规则在合约里")

    # B02 直转（已覆盖 T11，这里用另一张票复现一次，作为独立证据）
    t = contract().functions["transferFrom(address,address,uint256)"](
        addr("buyerA"), addr("attacker"), token2)
    tx2 = force_send(t, "buyerA", gas=150_000)
    case_reject("B02", "M5 对抗绕过", "成员5", "绕过页面直接 transferFrom 改票主", "buyerA",
                f"transferFrom(buyerA → attacker, {token2})",
                {"ok": tx2["status"] == 1, "error": "execution reverted（status=0）"},
                "execution reverted", tx=tx2,
                checks={"ownerOf 未变": api.get_ticket_owner(token2) == addr("buyerA")})

    # B03 非 verifier 直接核销
    tx3 = force_send(contract().functions.checkIn(token), "attacker", gas=150_000)
    case_reject("B03", "M5 对抗绕过", "成员5", "绕过验票页面直接调用 checkIn", "attacker",
                f"checkIn({token})", {"ok": tx3["status"] == 1, "error": "execution reverted（status=0）"},
                "execution reverted", tx=tx3,
                checks={"used 仍为 false": not api.get_ticket(token)["used"]})

    # B04 付错金额买票（合约里限购的检查排在付款之前，所以换一个没买过的账户）
    wrong = contract().functions.purchaseTickets(ev, 1)
    reason4 = precheck(wrong, "attacker", value=wei(0.1))
    tx4 = force_send(wrong, "attacker", value=wei(0.1), gas=250_000)
    case_reject("B04", "M5 对抗绕过", "成员5", "绕过页面付错金额买票（0.1 ETH 买 0.6 ETH 的票）", "attacker",
                "purchaseTickets(ev, 1) value=0.1 ETH", {"ok": False, "error": reason4},
                "Incorrect ETH amount", tx=tx4,
                checks={"库存未变": api.get_event(ev)["sold"] == 2},
                note="合约 require 顺序：库存/限购/白名单在付款之前，故用未买过的 attacker 才能命中金额校验")


def test_time_rules():
    """时间规则：演出开始后停止售票/挂牌；getMaxResalePrice 的边界缺陷。"""
    section("补充用例 · 时间规则（E06 / E07）")
    ev = fresh_event("E06 Event Starts Soon", 0.1, 3, 25 / 86400, 2)  # 25 秒后开场
    r, token = buy(ev, "buyerA", 1)
    case_ok("E06a", "M2 一级市场", "成员5", "开场前可以正常购票", "buyerA",
            f"purchaseTickets({ev}, 1) value=0.1 ETH（活动 25 秒后开始）", r,
            checks={"sold == 1": api.get_event(ev)["sold"] == 1})

    event_time = api.get_event(ev)["event_time"]
    wait = max(event_time - int(time.time()) + 6, 0)
    print(f"       └ 等待 {wait}s 让活动开场（链上时间）…")
    time.sleep(wait)

    late = api.buy_ticket(ev, "attacker", 1)
    tx_late = force_send(contract().functions.purchaseTickets(ev, 1), "attacker", value=wei(0.1), gas=250_000)
    case_reject("E06b", "M2 一级市场", "成员5", "活动开始后继续购票", "attacker",
                f"purchaseTickets({ev}, 1)（block.timestamp ≥ eventTime）", late,
                "Event already started", tx=tx_late)
    late_list = api.list_ticket(token, 0.1, "buyerA")
    tx_late2 = force_send(contract().functions.listForResale(token, wei(0.1)), "buyerA", gas=200_000)
    case_reject("E06c", "M3 防黄牛", "成员5", "活动开始后挂牌转售", "buyerA",
                f"listForResale({token}, 0.1 ETH)", late_list, "Event already started", tx=tx_late2)

    cap = api.get_max_resale_price(token)
    case_deviation(
        "E07", "M3 防黄牛", "成员5", "活动开始后读取 getMaxResalePrice", "只读",
        f"getMaxResalePrice({token})，eventTime 已过",
        f"调用 revert（{str(cap.get('error'))[:80]}）—— eventTime - block.timestamp 下溢",
        expected="只读调用应正常返回（例如 0），而不是 panic",
        note="成员 3 合约的实现缺陷：演出开始后该视图函数 panic；页面已有 try/except 兜底，"
             "但正确的实现应先判断 block.timestamp >= eventTime 再返回 0 或 revert 自定义错误",
    )


def test_end_to_end():
    """T18 完整流程 + Gas 采样。"""
    section("端到端 · T18 创建 → 购票 → 转售 → 入场")
    ev = fresh_event("T18 Full Flow Concert", 0.6, 6, 9, 1)
    rows = []

    r1 = api.get_event(ev)
    rows.append(("创建活动", r1 is not None, f"eventId={ev}, 剩余 {api.remaining_supply(ev)}"))
    r2, token = buy(ev, "buyerA", 1)
    _collect_gas("purchaseTickets(1)", r2, "T18")
    rows.append(("buyerA 购票", r2.ok and api.get_ticket_owner(token) == addr("buyerA"),
                 f"tokenId={token}, tx={r2.tx_hash}"))
    r3 = api.list_ticket(token, 0.72, "buyerA")   # 120% of 0.6
    _collect_gas("listForResale", r3, "T18")
    rows.append(("buyerA 以 0.72 ETH 挂牌", r3.ok and api.get_ticket(token)["is_listed"],
                 f"tx={r3.tx_hash}"))
    r4 = api.buy_resale(token, "buyerB")
    _collect_gas("buyResale", r4, "T18")
    rows.append(("buyerB 买入", r4.ok and api.get_ticket_owner(token) == addr("buyerB"),
                 f"tx={r4.tx_hash}, resaleCount={api.get_ticket(token)['resale_count']}"))
    qr = qr_utils.create_ticket_qr(token, addr("buyerB"), api.signing_key("buyerB"))
    v = qr_utils.verify_payload(qr, api.get_ticket(token))
    rows.append(("buyerB 生成 QR 并验签", v["ok"], f"{len(v['checks'])} 项检查全部通过" if v["ok"] else "验签失败"))
    r5 = api.check_in(token, "verifier")
    _collect_gas("checkIn", r5, "T18")
    rows.append(("verifier 核销", r5.ok and api.get_ticket(token)["used"], f"tx={r5.tx_hash}"))
    r6 = api.check_in(token, "verifier")
    rows.append(("再次核销被拒", not r6.ok and "already used" in (r6.error or "").lower(), f"原因：{r6.error}"))

    all_ok = all(ok for _, ok, _ in rows)
    case_ok(
        "T18", "M5 端到端", "成员1/4/5", "完整流程：创建 → 购票 → 挂牌 → 转售 → QR → 核销 → 重复核销", "多账户",
        "依次调用 7 个链上操作 + 1 次 QR 验签", {"ok": all_ok},
        expected="7 步全部符合预期",
        checks={f"步骤{i + 1} {name}": ok for i, (name, ok, _) in enumerate(rows)},
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
        sys.exit("私有链不可用：请先执行 ./blockchain/start_node.sh")
    if not status.get("contract_address"):
        sys.exit("合约未部署：请先执行 python backend/deploy.py")

    print("=" * 78)
    print("FTEC5520 防黄牛票务系统 · 成员 5 自动化测试")
    print(f"链 chainId={status['chain_id']} 区块={status['block_number']} 合约={status['contract_address']}")
    print(f"起始时间 {START_TS.isoformat(timespec='seconds')}")
    print("=" * 78)

    test_primary_market()
    token, token_bypass, ev = test_anti_scalping()
    test_qr_and_checkin({"token": token, "token_bypass": token_bypass, "event": ev})
    test_presale_resale_whitelist()
    test_bypass_frontend()
    test_end_to_end()
    test_time_rules()

    # ---------------------------------------------------------------- 汇总
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

    failed_tx_gas = [r for r in GAS if r.get("status") == 0]
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
            writer.writerow({**row, "status": row.get("status", 1)})

    (RESULTS / "test_environment.json").write_text(
        json.dumps(env, indent=2, ensure_ascii=False), "utf-8")
    (RESULTS / "test_evidence.json").write_text(
        json.dumps({"environment": env, "summary": summary, "rows": ROWS,
                    "gas": GAS, "steps": STEPS},
                   indent=2, ensure_ascii=False), "utf-8")

    print("\n" + "=" * 78)
    print(f"用例 {summary['total_cases']} 条：PASS {summary['pass']} / FAIL {summary['fail']} / "
          f"偏差 {summary['deviation']}，通过率 {summary['pass_rate']}%")
    by_op: dict[str, list[int]] = {}
    for row in GAS:
        by_op.setdefault(row["operation"], []).append(row["gas_used"])
    for op, values in by_op.items():
        print(f"  gas {op:<24} n={len(values):<2} avg={sum(values) // len(values):>8,}")
    print(f"真实的失败交易（status=0）：{summary['on_chain_failed_txs']} 笔，"
          f"合计 gas {summary['on_chain_failed_gas_total']:,}")
    print(f"耗时 {summary['duration_seconds']}s，最终区块 {summary['final_block']}")
    print(f"结果表：{RESULTS / 'test_results.csv'}")
    print(f"证据：  {RESULTS / 'test_evidence.json'}")
    print("=" * 78)

    if summary["fail"]:
        print("\n存在 FAIL 用例：")
        for row in ROWS:
            if row["verdict"] == "FAIL":
                print(f"  - {row['test_id']} {row['scenario']}：{row['actual']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
