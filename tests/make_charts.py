#!/usr/bin/env python
"""成员 5：用真实测试数据生成报告 / PPT 用的图表。

输入（都由 tests/test_workflow.py 生成）
    results/test_results.csv
    results/gas_data.csv
    results/test_evidence.json

输出
    results/charts/01_test_results_by_module.png   各模块 PASS / 偏差 / FAIL
    results/charts/02_gas_comparison.png           关键操作 Gas 对比
    results/charts/03_coverage_and_failed_tx.png   正常 vs 异常覆盖 + 失败交易 gas 成本

用法：
    .venv/bin/python tests/make_charts.py
"""

from __future__ import annotations

import csv
import json
import os
import statistics
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[1] / ".mplconfig"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
CHARTS = RESULTS / "charts"

PASS_C, DEV_C, FAIL_C = "#2E7D32", "#F9A825", "#C62828"
GREY = "#546E7A"
CJK_FONTS = [
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
]


def setup_font() -> None:
    """注册一个中文字体，避免图里出现方块。"""
    for path in CJK_FONTS:
        if Path(path).exists():
            font_manager.fontManager.addfont(path)
            name = font_manager.FontProperties(fname=path).get_name()
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
            print(f"[chart] 使用字体 {name}（{path}）")
            return
    print("[chart] 未找到中文字体，图上中文可能显示为方块")


def load_rows() -> list[dict]:
    path = RESULTS / "test_results.csv"
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_gas() -> list[dict]:
    path = RESULTS / "gas_data.csv"
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def chart_module_results(rows: list[dict], summary: dict) -> Path:
    modules = ["M2 一级市场", "M3 防黄牛", "M4 验票/QR", "M5 对抗绕过", "M5 端到端"]
    labels = ["成员2\n一级市场", "成员3\n防黄牛/转售", "成员4\n二维码/验票",
              "成员5\n绕过前端对抗", "成员5\n端到端全流程"]
    colors = {"PASS": PASS_C, "DEVIATION": DEV_C, "FAIL": FAIL_C}
    fig, ax = plt.subplots(figsize=(9.6, 5.2))
    left = [0] * len(modules)
    for verdict, label in (("PASS", "PASS"), ("DEVIATION", "偏差（需求不符）"), ("FAIL", "FAIL")):
        values = [sum(1 for r in rows if r["module"] == m and r["verdict"] == verdict) for m in modules]
        bars = ax.barh(labels, values, left=left, color=colors[verdict], label=label, height=0.6)
        for bar, value in zip(bars, values):
            if value:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_y() + bar.get_height() / 2,
                        str(value), ha="center", va="center", color="white", fontsize=11, weight="bold")
        left = [a + b for a, b in zip(left, values)]
    for i, total in enumerate(left):
        ax.text(total + 0.15, i, f"{total} 例", va="center", fontsize=10, color="#37474F")
    ax.set_xlabel("用例数量")
    ax.set_title(
        f"图 1  T01–T18 与扩展用例：按模块统计（PASS {summary['pass']} / FAIL {summary['fail']} / "
        f"偏差 {summary['deviation']}，通过率 {summary['pass_rate']}%）",
        fontsize=12, pad=12,
    )
    ax.legend(loc="lower right", frameon=False)
    ax.set_xlim(0, max(left) + 3)
    ax.grid(axis="x", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    out = CHARTS / "01_test_results_by_module.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def chart_gas(gas: list[dict]) -> tuple[Path, dict]:
    """关键操作的平均 gas（每个成功操作取一次代表值）。"""
    mapping = [
        ("createEvent", "创建活动\ncreateEvent", "setup"),
        ("setWhitelistBatch(1)", "写白名单\nsetWhitelistBatch", "setup"),
        ("purchaseTickets(1)", "购票 1 张\npurchaseTickets", "success"),
        ("purchaseTickets(2)", "购票 2 张\npurchaseTickets", "success"),
        ("listForResale", "挂牌\nlistForResale", "success"),
        ("buyResale", "买二手票\nbuyResale", "success"),
        ("checkIn", "核销\ncheckIn", "success"),
    ]
    ops, values, colors = [], [], []
    stats: dict[str, int] = {}
    for op, label, _kind in mapping:
        vals = [int(g["gas_used"]) for g in gas if g["operation"] == op and int(g.get("status") or 1) == 1]
        if not vals:
            continue
        med = int(statistics.median(vals))
        stats[op] = med
        ops.append(f"{label}\n(n={len(vals)})")
        values.append(med)
        colors.append("#1565C0" if op in ("createEvent", "setWhitelistBatch(1)") else "#2E7D32")

    failed = [int(g["gas_used"]) for g in gas if int(g.get("status") or 1) == 0]
    if failed:
        stats["_failed_tx_median"] = int(statistics.median(failed))
        stats["_failed_tx_count"] = len(failed)
        ops.append(f"被拒绝的交易\nrevert, status=0\n(n={len(failed)})")
        values.append(int(statistics.median(failed)))
        colors.append(FAIL_C)

    fig, ax = plt.subplots(figsize=(10.4, 5.2))
    bars = ax.bar(ops, values, color=colors, width=0.62)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + max(values) * 0.015,
                f"{value:,}", ha="center", va="bottom", fontsize=10, weight="bold")
    ax.set_ylabel("Gas used（中位数）")
    ax.set_title("图 2  关键操作 Gas 对比：写状态的链上成本（Clique 私有链真实回执）", fontsize=12, pad=12)
    ax.set_ylim(0, max(values) * 1.18)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(axis="x", labelsize=9)
    fig.tight_layout()
    out = CHARTS / "02_gas_comparison.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out, stats


def chart_coverage(rows: list[dict], gas: list[dict]) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6), gridspec_kw={"width_ratios": [1.15, 1]})

    # 左：正常 / 异常覆盖
    normal = sum(1 for r in rows if r["kind"] == "normal")
    negative = sum(1 for r in rows if r["kind"] == "negative")
    deviation = sum(1 for r in rows if r["kind"] == "deviation")
    ax = axes[0]
    bars = ax.bar(["正常路径\n（应成功）", "异常路径\n（应被拒绝）", "偏差\n（需求不符）"],
                  [normal, negative, deviation], color=["#2E7D32", "#1565C0", DEV_C], width=0.55)
    for bar, value in zip(bars, [normal, negative, deviation]):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.25, str(value),
                ha="center", va="bottom", fontsize=12, weight="bold")
    ax.set_ylabel("用例数")
    ax.set_title(f"图 3-a  用例类型覆盖（共 {len(rows)} 条）", fontsize=11)
    ax.set_ylim(0, max(normal, negative, deviation) * 1.25)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    # 右：失败交易 vs 成功交易 gas（证明"失败也要付 gas"）
    ok_gas = [int(g["gas_used"]) for g in gas if int(g.get("status") or 1) == 1]
    bad_gas = [int(g["gas_used"]) for g in gas if int(g.get("status") or 1) == 0]
    ax = axes[1]
    if ok_gas and bad_gas:
        ax.boxplot([ok_gas, bad_gas], tick_labels=["成功交易", "被拒绝交易\n(status=0)"],
                   patch_artist=True,
                   boxprops={"facecolor": "#C8E6C9"},
                   medianprops={"color": "#1B5E20"})
        for patch in ax.patches[1::2]:
            patch.set_facecolor("#FFCDD2")
        ax.set_ylabel("Gas used")
        ax.set_title("图 3-b  交易被拒绝时仍然消耗 Gas", fontsize=11)
        ax.text(0.5, 0.92,
                f"成功 {len(ok_gas)} 笔 · 中位数 {int(statistics.median(ok_gas)):,}\n"
                f"被拒 {len(bad_gas)} 笔 · 中位数 {int(statistics.median(bad_gas)):,}",
                transform=ax.transAxes, ha="center", va="top", fontsize=9, color="#37474F",
                bbox={"boxstyle": "round,pad=0.4", "fc": "#F5F5F5", "ec": "#B0BEC5"})
        ax.grid(axis="y", linestyle=":", alpha=0.4)
        ax.set_axisbelow(True)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)

    fig.tight_layout()
    out = CHARTS / "03_coverage_and_failed_tx.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def main() -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    setup_font()
    rows = load_rows()
    gas = load_gas()
    summary = json.loads((RESULTS / "test_evidence.json").read_text("utf-8"))["summary"]

    p1 = chart_module_results(rows, summary)
    p2, gas_stats = chart_gas(gas)
    p3 = chart_coverage(rows, gas)
    print(f"[chart] {p1}\n[chart] {p2}\n[chart] {p3}")

    (RESULTS / "chart_data.json").write_text(
        json.dumps({"gas_median": gas_stats, "cases": len(rows), "summary": summary},
                   indent=2, ensure_ascii=False), "utf-8")
    print("[chart] gas 中位数：" + ", ".join(f"{k}={v:,}" for k, v in gas_stats.items()))


if __name__ == "__main__":
    main()
