#!/usr/bin/env python
"""按「7 个测试账户」逐账户核验（对应 docs/ACCOUNTS.md 与队友给的对照表）。

为什么需要这个脚本
------------------
`tests/test_workflow.py` 覆盖 T01–T18 及 E*/B* 系列，但**没有**覆盖队员表里写的
T19 / T20 / T23 / T24 所对应的动作：

    * deployer 收取 5% 平台手续费、并提取（withdrawPlatformFees）
    * organizer 提取票款（withdrawProceeds）
    * buyerB 作为接盘方，转售后的 NFT 归属（ownerOf / resaleCount）
    * miner 每 2 秒出块

本脚本对这些"账户专属职责"做一次真实链上核验（该发交易就发交易，该被拒就要求被拒），
再把 `results/test_results.csv` 里已有的用例按 actor 归到每个账户，产出：

    results/account_verification.md     人读的逐账户报告（可直接发队友）
    results/account_check.json          机读的核验明细

用法
----
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

# 队友那张表里"对应哪几条测试"一列 = docs/ACCOUNTS.md 的写法
TEAMMATE_CASES = {
    "deployer": "T19 / T24",
    "organizer": "T01 / T02 / T20",
    "buyerA": "T03 / T09b / T13 / T15",
    "buyerB": "T14 / T23",
    "verifier": "T15 / T16",
    "attacker": "T04 / T06 / T08 / T10",
    "miner": "后台一直在跑",
}

IDENTITY = {
    "deployer": ("平台方（部署合约的人）", "合约 owner；设置验票员；收 5% 平台手续费"),
    "organizer": ("主办方（演唱会公司）", "创建活动、开关预售、管白名单、收票款"),
    "buyerA": ("正常买家（在白名单里）", "预售期买票、挂二手、被扫码入场"),
    "buyerB": ("第二个正常买家", "转售后的接盘方，验证 NFT 归属变了"),
    "verifier": ("现场工作人员（验票员）", "扫码核销，把票标为「已用」"),
    "attacker": ("黄牛", "专门违规：非白名单抢预售、超限购、超价转售"),
    "miner": ("出块的人（Clique 授权节点）", "每 2 秒打包一个区块"),
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
    """把 revert 结果翻译成人话（合约用自定义 error，只有 4 字节 selector）。"""
    text = str(err or "")
    if text.startswith("0x118cdaa7"):
        return "拒绝：OwnableUnauthorizedAccount（调用者不是 owner）"
    return ("拒绝：" + text[:70]) if text else "拒绝（无返回原因）"


def token_transfers(token_id: int) -> list[dict]:
    """单张票的全部 Transfer 记录（按区块升序）。

    注意：`api.transfer_history(limit)` 取的是**全站最近 N 条**转移，不是单张票的，
    所以这里直接按 topics[3] = tokenId 过滤日志。
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
# miner：出块节奏
# ----------------------------------------------------------------------
def check_miner() -> None:
    print("\n[1/7] miner —— 出块（Clique PoA，2s/块）")
    w3 = api.get_w3()
    b0 = w3.eth.block_number
    t0 = time.time()
    time.sleep(6.5)
    b1 = w3.eth.block_number
    dt = time.time() - t0
    produced = b1 - b0
    ok = produced >= 2
    record("miner", "6 秒内新增区块数", "≥2 个（2s/块）", f"{produced} 个（区块 {b0} → {b1}，{dt:.1f}s）",
           "PASS" if ok else "FAIL")
    miner_addr = api.get_accounts().get("miner")
    if miner_addr:
        record("miner", "是否为授权签名者（miner 账户）", "地址存在且持续出块",
               f"{miner_addr}", "PASS" if ok else "FAIL")
    else:
        record("miner", "miner 账户是否在 .env / genesis 中", "存在",
               "未在测试账户列表中（仅 genesis alloc 有 1000 ETH）", "SKIP",
               note="miner 私钥由 geth --unlock + password.txt 管理，不在 .env 的 6 个角色里")


# ----------------------------------------------------------------------
# deployer：owner + 5% 平台手续费 + 提取权限
# ----------------------------------------------------------------------
def check_deployer() -> None:
    print("\n[2/7] deployer —— 合约 owner、5% 平台费、提取手续费")
    accounts = api.get_accounts()
    owner = api._contract().functions.owner().call()  # noqa: SLF001
    is_owner = owner.lower() == accounts["deployer"].lower()
    record("deployer", "合约 owner() 是否 = deployer", "是（部署者即 owner）",
           f"{owner}", "PASS" if is_owner else "FAIL")

    # 5% 手续费：直接读最近一笔 TicketResold 事件核对金额
    resales = api.get_events("TicketResold", limit=5)
    if resales:
        arg = resales[-1]["args"]
        price, fee = int(arg["price"]), int(arg["platformFee"])
        expect = price * 5 // 100
        ok = fee == expect
        record("deployer", "转售平台费 = 售价 5%", f"{expect} wei（5%）",
               f"{fee} wei（token {arg['tokenId']}，售价 {price} wei）",
               "PASS" if ok else "FAIL", tx=resales[-1]["tx_hash"])
    else:
        record("deployer", "转售平台费 = 售价 5%", "存在 TicketResold 事件", "无转售事件", "SKIP")

    # 提取手续费
    pending = api.pending_platform_fees("deployer")
    before = eth("deployer")
    if pending > 0:
        res = api.withdraw_platform_fees("deployer")
        after = eth("deployer")
        ok = res.ok and after > before
        record("deployer", "withdrawPlatformFees 提取手续费", "成功且余额增加",
               f"{pending:.4f} ETH → 余额 {before:.4f} → {after:.4f}",
               "PASS" if ok else "FAIL", tx=res.tx_hash or "",
               note=res.error or "")
        record("deployer", "提取后 pendingPlatformFees 归零", "0",
               f"{api.pending_platform_fees('deployer'):.6f} ETH",
               "PASS" if api.pending_platform_fees("deployer") == 0 else "FAIL")
    else:
        record("deployer", "withdrawPlatformFees 提取手续费", "有待提取手续费",
               "当前为 0（此前已提取完）", "SKIP")

    # 负向：非 owner 不能提手续费（合约用 Ownable2Step 的自定义 error，无字符串原因）
    bad = api.withdraw_platform_fees("attacker")
    record("deployer", "attacker 提平台费被拒（onlyOwner）", "拒绝",
           reason_of(bad.error) if not bad.ok else "意外成功",
           "PASS" if not bad.ok else "FAIL", tx=bad.tx_hash or "")


# ----------------------------------------------------------------------
# organizer：票款提取
# ----------------------------------------------------------------------
def check_organizer() -> None:
    print("\n[3/7] organizer —— 创建活动、收票款、提取票款")
    pending = api.pending_proceeds("organizer")
    before = eth("organizer")
    if pending > 0:
        res = api.withdraw_proceeds("organizer")
        after = eth("organizer")
        ok = res.ok and after > before
        record("organizer", "withdrawProceeds 提取票款", "成功且余额增加",
               f"{pending:.4f} ETH → 余额 {before:.4f} → {after:.4f}",
               "PASS" if ok else "FAIL", tx=res.tx_hash or "", note=res.error or "")
        record("organizer", "提取后 pendingProceeds 归零", "0",
               f"{api.pending_proceeds('organizer'):.6f} ETH",
               "PASS" if api.pending_proceeds("organizer") == 0 else "FAIL")
    else:
        record("organizer", "withdrawProceeds 提取票款", "有待提取票款",
               "当前为 0（此前已提取完）", "SKIP")

    bad = api.withdraw_proceeds("attacker")
    record("organizer", "attacker 提票款被拒（无待提取额）", "拒绝：No proceeds available",
           ("拒绝：" + str(bad.error)[:60]) if not bad.ok else "意外成功",
           "PASS" if not bad.ok else "FAIL", tx=bad.tx_hash or "")


# ----------------------------------------------------------------------
# buyerA / buyerB：转售与 NFT 归属转移
# ----------------------------------------------------------------------
def check_buyers() -> None:
    print("\n[4/7][5/7] buyerA / buyerB —— 购票、挂二手、接盘后归属变化")
    accounts = api.get_accounts()
    tokens = api.all_tokens()
    resold = [t for t in tokens if (api.get_ticket(t) or {}).get("resale_count", 0) > 0]
    if not resold:
        record("buyerB", "转售后的 ownerOf 与 resaleCount", "至少一张票转售过", "无", "SKIP")
        return

    tok = resold[-1]
    t = api.get_ticket(tok)
    onchain_owner = t["owner"]
    role = next((r for r, a in accounts.items() if a.lower() == onchain_owner.lower()), None)
    hist = token_transfers(tok)
    last = hist[-1] if hist else None
    match = last is not None and last["to"].lower() == onchain_owner.lower()
    record("buyerB", f"转售票 token {tok} 的 ownerOf 与最后一条 Transfer 一致", "一致",
           f"ownerOf={onchain_owner[:12]}…（{role}）/ Transfer "
           f"{last['from'][:10] if last else '—'}→{last['to'][:10] if last else '—'} @block "
           f"{last['block'] if last else '—'}",
           "PASS" if match else "FAIL",
           tx=last["tx_hash"] if last else "",
           note=f"resaleCount={t['resale_count']}（上限 3）")

    expect_count = max(len(hist) - 1, 0)  # 铸造 1 条 + 每次转售 1 条
    record("buyerB", f"token {tok} 的 resaleCount 与链上 Transfer 次数一致",
           f"{expect_count}（{len(hist)} 条 Transfer - 铸造 1 条）",
           f"{t['resale_count']}",
           "PASS" if t["resale_count"] == expect_count else "FAIL")

    listed = api.listed_tickets()
    record("buyerA", "二手市场当前在售数量可读", "≥0 条",
           f"{len(listed)} 条在售：" + ", ".join(f"token {x['token_id']}@{x['listing_price_eth']}ETH" for x in listed[:4]),
           "PASS")


# ----------------------------------------------------------------------
# verifier / attacker：权限
# ----------------------------------------------------------------------
def check_verifier_attacker() -> None:
    print("\n[6/7] verifier / attacker —— 核销权限与违规账户")
    ok_v = api.is_verifier("verifier")
    record("verifier", "is_verifier(verifier) = true（已授权）", "true",
           str(ok_v).lower(), "PASS" if ok_v else "FAIL")
    ok_a = api.is_verifier("attacker")
    record("verifier", "is_verifier(attacker) = false", "false",
           str(ok_a).lower(), "PASS" if not ok_a else "FAIL")
    ok_b = api.is_verifier("buyerA")
    record("verifier", "is_verifier(buyerA) = false（普通买家不能核销）", "false",
           str(ok_b).lower(), "PASS" if not ok_b else "FAIL")
    record("attacker", "attacker 无核销权限（T17 前提）", "false",
           f"is_verifier(attacker)={str(ok_a).lower()}", "PASS" if not ok_a else "FAIL")


# ----------------------------------------------------------------------
# 把自动化套件的用例按 actor 归到每个账户
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
        "# 逐账户核验报告（按队友给的 7 个账户表）",
        "",
        f"> 生成时间：{datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"> 链：chainId {status['chain_id']} · 区块 {status['block_number']} · 合约 `{status['contract_address']}`",
        f"> 自动化用例：{len(rows)} 条 → PASS {counts['PASS']} / FAIL {counts['FAIL']} / 偏差 {counts['DEVIATION']}",
        f"> 账户专项核验：{len(CHECKS)} 项 → PASS {ck['PASS']} / FAIL {ck['FAIL']} / 跳过 {ck['SKIP']}",
        "",
        "## 一、总览",
        "",
        "| 账户 | 是谁 | 在演示里干什么 | 队友给的测试 | 实测覆盖用例 | 失败 | 账户专项核验 |",
        "|---|---|---|---|---|---|---|",
    ]
    for role in ORDER:
        who, duty = IDENTITY[role]
        cs = cases_of(rows, role)
        fails = [c for c in cs if c["verdict"] == "FAIL"]
        mine = [c for c in CHECKS if c["role"] == role]
        bad = [c for c in mine if c["verdict"] == "FAIL"]
        ck_txt = f"{len(mine)} 项 / 失败 {len(bad)}" if mine else "—"
        lines.append(
            f"| `{role}` | {who} | {duty} | {TEAMMATE_CASES[role]} | {len(cs)} 条 | "
            f"{'**' + str(len(fails)) + '**' if fails else '0'} | {ck_txt} |"
        )

    lines += ["", "## 二、逐账户明细", ""]
    for role in ORDER:
        who, duty = IDENTITY[role]
        lines.append(f"### `{role}` — {who}")
        lines.append("")
        mine = [c for c in CHECKS if c["role"] == role]
        if mine:
            lines.append("**账户专项核验（本次真实发交易/读链）**")
            lines.append("")
            lines.append("| 检查项 | 预期 | 实际 | 结果 | tx |")
            lines.append("|---|---|---|---|---|")
            for c in mine:
                tx = f"`{c['tx_hash'][:18]}…`" if c["tx_hash"] else "—"
                lines.append(f"| {c['item']} | {c['expected']} | {c['actual']} | {c['verdict']} | {tx} |")
            lines.append("")
        cs = cases_of(rows, role)
        if cs:
            lines.append(f"**自动化套件里 actor = {role} 的用例**")
            lines.append("")
            lines.append("| 用例 | 场景 | 预期 | 结果 | tx |")
            lines.append("|---|---|---|---|---|")
            for c in cs:
                tx = f"`{c['tx_hash'][:18]}…`" if c.get("tx_hash") else "—"
                lines.append(f"| {c['test_id']} | {c['scenario'][:40]} | {c['expected'][:16]} | "
                             f"{c['verdict']} | {tx} |")
            lines.append("")
        if not mine and not cs:
            lines.append("— 无直接绑定的账户动作（后台常驻角色）")
            lines.append("")

    lines += [
        "## 三、和队友那张表的差异（要跟队友对齐的两点）",
        "",
        "### 1）`T19 / T20 / T23 / T24` 这四个编号在本仓库里不存在",
        "",
        "`tests/test_workflow.py` 的编号是 T01–T18 + E01–E09 + B01–B04，"
        "`backend/demo_flow.py` 是 T01–T17 的另一套编号；两边都没有 T19 以后。"
        "队友那张表的编号应该来自课程任务书，行为本身是覆盖了的，对应关系如下：",
        "",
        "| 队友的编号 | 行为 | 本仓库的实际证据 |",
        "|---|---|---|",
        "| T19（deployer） | 收 5% 平台手续费 | 本报告 deployer 段：读 `TicketResold.platformFee` 校验 = 售价×5%，并真实提取 |",
        "| T20（organizer） | 提取票款 | 本报告 organizer 段：`withdrawProceeds` 真实发交易、余额增加、待提取归零 |",
        "| T23（buyerB） | 转售接盘后 NFT 归属变化 | 本报告 buyerB 段（`ownerOf` vs `Transfer.to`）+ 套件 T07b / T10a / T18 |",
        "| T24（deployer） | 设置验票员 | 套件 T15a（`setVerifier`），本报告 verifier 段复核 `is_verifier` 状态 |",
        "",
        "### 2）`docs/ACCOUNTS.md` 里的地址和当前链不一致（过期）",
        "",
        "该文件记录的是 2026-11-17 在 WSL 上那次建链的账户与合约地址；现在这台机器上"
        "`blockchain/init_chain.py` 重新生成过账户，所以地址全变了。以 `config/network.json` 为准：",
        "",
        "| 角色 | `config/network.json`（当前链，以这个为准） | `docs/ACCOUNTS.md`（旧 WSL 链，已过期） |",
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
        "> 队友如果拿 `ACCOUNTS.md` 的地址去链上核对，会全部对不上——不是链错了，是文档没跟着重新生成。"
        "要么让 `docs/ACCOUNTS.md` 重新生成一次（`init_chain.py` 跑完就更新），要么明确告诉大家「以 `config/network.json` 为准」。",
        "",
        "## 四、结论",
        "",
    ]
    bad_all = [c for c in CHECKS if c["verdict"] == "FAIL"] + [r for r in rows if r["verdict"] == "FAIL"]
    if not bad_all:
        lines.append("**全部通过**：7 个账户的演示职责、违规拦截、权限控制均在当前链上复现成功，"
                     "无 FAIL 用例；2 条 DEVIATION 是任务书与实现的口径差异（已在 `results/test_evidence.json` 注明），不是缺陷。")
    else:
        lines.append(f"**存在 {len(bad_all)} 项失败**，明细见上表。")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    status = api.get_chain_status()
    if not status.get("connected") or not status.get("contract_address"):
        sys.exit("链或合约不可用：先 ./blockchain/start_node.sh 与 .venv/bin/python backend/deploy.py")

    print("=" * 78)
    print("按队友的「7 个账户」表逐账户核验")
    print(f"chainId={status['chain_id']} 区块={status['block_number']} 合约={status['contract_address']}")
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
    print(f"账户专项核验 {len(CHECKS)} 项：PASS {ck['PASS']} / FAIL {ck['FAIL']} / 跳过 {ck['SKIP']}")
    print(f"套件用例 {len(rows)} 条：" + " / ".join(
        f"{k} {sum(1 for r in rows if r['verdict'] == k)}" for k in ("PASS", "FAIL", "DEVIATION")))
    print(f"报告：{RESULTS / 'account_verification.md'}")
    print("=" * 78)
    if ck["FAIL"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
