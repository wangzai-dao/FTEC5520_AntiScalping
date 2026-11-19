#!/usr/bin/env python
"""Member 5: build the report / slide charts from the real test data.

Inputs (produced by tests/test_workflow.py)
    results/test_results.csv
    results/gas_data.csv
    results/test_evidence.json

Outputs
    results/charts/01_test_results_by_module.png   PASS / deviation / FAIL by module
    results/charts/02_gas_comparison.png           gas comparison of key operations
    results/charts/03_coverage_and_failed_tx.png   case-type coverage + cost of rejected calls

Usage:
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
from matplotlib import font_manager, ticker  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
CHARTS = RESULTS / "charts"

PASS_C, DEV_C, FAIL_C = "#2E7D32", "#F9A825", "#C62828"
BLUE = "#1565C0"
FONT_FILES = [
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
]


def setup_font() -> None:
    """Register a font with wide glyph coverage; falls back to the matplotlib default."""
    for path in FONT_FILES:
        if Path(path).exists():
            font_manager.fontManager.addfont(path)
            name = font_manager.FontProperties(fname=path).get_name()
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
            print(f"[chart] using font {name} ({path})")
            return
    print("[chart] no suitable font found, using the matplotlib default")


def load_rows() -> list[dict]:
    with open(RESULTS / "test_results.csv", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_gas() -> list[dict]:
    with open(RESULTS / "gas_data.csv", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _status(gas_row: dict) -> int:
    """status=0 is falsy - never write `status or 1`, or rejected txs look successful."""
    value = gas_row.get("status")
    return 1 if value in (None, "") else int(value)


def chart_module_results(rows: list[dict], summary: dict) -> Path:
    # barh draws bottom-up, so reverse the lists to keep "Member 2" on top
    modules = ["M2 Primary market", "M3 Anti-scalping", "M4 Check-in/QR",
               "M5 Bypass", "M5 End-to-end"][::-1]
    labels = ["Primary market", "Anti-scalping", "Check-in / QR",
              "Front-end bypass", "End-to-end"][::-1]
    colors = {"PASS": PASS_C, "DEVIATION": DEV_C, "FAIL": FAIL_C}
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    left = [0] * len(modules)
    for verdict, label in (("PASS", "PASS"), ("DEVIATION", "Deviation (spec gap)"), ("FAIL", "FAIL")):
        values = [sum(1 for r in rows if r["module"] == m and r["verdict"] == verdict) for m in modules]
        bars = ax.barh(labels, values, left=left, color=colors[verdict], label=label, height=0.6)
        for bar, value in zip(bars, values):
            if value:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_y() + bar.get_height() / 2,
                        str(value), ha="center", va="center", color="white", fontsize=9, weight="bold")
        left = [a + b for a, b in zip(left, values)]
    for i, total in enumerate(left):
        ax.text(total + 0.12, i, f"{total} case" + ("s" if total != 1 else ""), va="center",
                fontsize=9, color="#37474F")
    ax.set_xlabel("Number of cases", fontsize=9.5)
    ax.legend(loc="lower right", frameon=False, fontsize=8.5)
    ax.tick_params(labelsize=9)
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
    """Median gas per operation; only operations that actually succeeded are plotted."""
    mapping = [
        ("createEvent", "Create event", "setup"),
        ("setWhitelistBatch(1)", "Set whitelist", "setup"),
        ("purchaseTickets(1)", "Buy 1 ticket", "success"),
        ("purchaseTickets(2)", "Buy 2 tickets", "success"),
        ("listForResale", "List for resale", "success"),
        ("buyResale", "Buy resale", "success"),
        ("checkIn", "Check in", "success"),
    ]
    ops, values, colors = [], [], []
    stats: dict[str, int] = {}
    for op, label, _kind in mapping:
        vals = [int(g["gas_used"]) for g in gas if g["operation"] == op and _status(g) == 1]
        if not vals:
            continue
        med = int(statistics.median(vals))
        stats[op] = med
        ops.append(f"{label}\n(n={len(vals)})")
        values.append(med)
        colors.append(BLUE if op in ("createEvent", "setWhitelistBatch(1)") else PASS_C)

    failed = [int(g["gas_used"]) for g in gas if _status(g) == 0]
    if failed:
        stats["_failed_tx_median"] = int(statistics.median(failed))
        stats["_failed_tx_count"] = len(failed)
        ops.append("Rejected\n(status=0)")
        values.append(int(statistics.median(failed)))
        colors.append(FAIL_C)

    fig, ax = plt.subplots(figsize=(7.2, 3.7))
    bars = ax.bar(ops, values, color=colors, width=0.62)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + max(values) * 0.015,
                f"{value:,}", ha="center", va="bottom", fontsize=8.5, weight="bold")
    ax.set_ylabel("Gas used (median)", fontsize=9.5)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.set_ylim(0, max(values) * 1.18)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=8.5)
    fig.tight_layout()
    out = CHARTS / "02_gas_comparison.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out, stats


def chart_coverage(rows: list[dict], gas: list[dict]) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.4), gridspec_kw={"width_ratios": [1.0, 1.2]})

    # left: normal vs negative coverage
    normal = sum(1 for r in rows if r["kind"] == "normal")
    negative = sum(1 for r in rows if r["kind"] == "negative")
    deviation = sum(1 for r in rows if r["kind"] == "deviation")
    ax = axes[0]
    bars = ax.bar(["Normal path\n(should succeed)", "Negative path\n(should be rejected)",
                   "Deviation\n(spec gap)"],
                  [normal, negative, deviation], color=[PASS_C, BLUE, DEV_C], width=0.55)
    for bar, value in zip(bars, [normal, negative, deviation]):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.25, str(value),
                ha="center", va="bottom", fontsize=9.5, weight="bold")
    ax.set_ylabel("Cases", fontsize=9)
    ax.tick_params(labelsize=8)
    ax.set_ylim(0, max(normal, negative, deviation) * 1.25)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    # right: success vs rejection for the same operation (failures still cost gas)
    pairs = [("purchaseTickets", "Buy"), ("listForResale", "List"),
             ("buyResale", "Resale"), ("checkIn", "Check-in")]
    ok_vals, bad_vals, labels = [], [], []
    for prefix, label in pairs:
        ok = [int(g["gas_used"]) for g in gas
              if g["operation"].startswith(prefix) and _status(g) == 1]
        bad = [int(g["gas_used"]) for g in gas
               if g["operation"].startswith(prefix) and _status(g) == 0]
        if not ok or not bad:
            continue
        labels.append(label)
        ok_vals.append(int(statistics.median(ok)))
        bad_vals.append(int(statistics.median(bad)))

    ax = axes[1]
    if labels:
        xs = range(len(labels))
        w = 0.36
        b1 = ax.bar([x - w / 2 for x in xs], ok_vals, width=w, color=PASS_C,
                    label="Success (status=1)")
        b2 = ax.bar([x + w / 2 for x in xs], bad_vals, width=w, color=FAIL_C,
                    label="Rejected (status=0)")
        for bars in (b1, b2):
            for bar in bars:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 1.03,
                        f"{int(round(bar.get_height() / 1000))}k", ha="center", va="bottom",
                        fontsize=7.5)
        ax.set_xticks(list(xs))
        ax.set_xticklabels(labels, fontsize=8.5)
        ax.set_ylabel("Gas used", fontsize=9)
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
        ax.set_ylim(0, max(ok_vals + bad_vals) * 1.24)
        ax.legend(fontsize=7.5, frameon=False, loc="upper right")
        ax.tick_params(axis="y", labelsize=7.5)
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
    print("[chart] gas medians: " + ", ".join(f"{k}={v:,}" for k, v in gas_stats.items()))


if __name__ == "__main__":
    main()
