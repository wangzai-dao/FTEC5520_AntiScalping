#!/usr/bin/env python
"""Part 5: build the defence deck (presentation/final_presentation.pptx).

The deck follows the speaking order of the five members (1 -> 2 -> 3 -> 4 -> 5).
Each part has
  * a divider slide: who is speaking, what they own, what they hand over;
  * one to three content slides with their implementation and their own evidence;
  * a handover strip naming what the next member starts from.
Every slide carries speaker notes (View > Notes Page) with a short script, so each
member knows exactly which slide is theirs and what to say on it.

All numbers come from results/test_evidence.json, results/chart_data.json,
config/network.json and results/screenshots/ - the same run as the Final Report.

Usage:
    python presentation/build_pptx.py
"""

from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Cm, Pt

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
CHARTS = RESULTS / "charts"
SHOTS = RESULTS / "screenshots"
OUT = ROOT / "presentation" / "final_presentation.pptx"

FONT = "Arial"
NAVY = RGBColor(0x1F, 0x38, 0x64)
BLUE = RGBColor(0x15, 0x65, 0xC0)
TEAL = RGBColor(0x00, 0x89, 0x7B)
DARK = RGBColor(0x26, 0x32, 0x38)
GREY = RGBColor(0x60, 0x6B, 0x72)
LIGHT = RGBColor(0xF4, 0xF6, 0xF8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x2E, 0x7D, 0x32)
AMBER = RGBColor(0xF9, 0xA8, 0x25)
RED = RGBColor(0xC6, 0x28, 0x28)

W, H = Cm(33.87), Cm(19.05)   # 16:9
MARGIN = 1.6

# Body text was set for a 16:9 slide read on a laptop; on a projector it is too small.
# Everything drawn through text()/table() is scaled here, with a ceiling so the big
# "Part N" headline on the dividers does not run away.
SCALE = 1.22
MAX_PT = 46

PARTS = [
    ("1", "Private chain, deployment and the Web3.py interface", "Chain and interface", BLUE,
     "A running chain, a deployed contract and six Python functions"),
    ("2", "Events, presale whitelist and the primary market", "Issuance and limits", TEAL,
     "The rules for who may buy, how many, and at what price"),
    ("3", "Price-capped resale, transfer blocking, on-chain check-in", "Resale and check-in", NAVY,
     "The anti-scalping layer every ticket must travel through"),
    ("4", "Six Streamlit pages and the signed QR ticket", "Pages and the QR ticket", BLUE,
     "A usable interface plus a credential that cannot be screenshotted"),
    ("5", "Testing, evidence, report and this deck", "Testing and evidence", GREEN,
     "48 measured cases and the numbers behind every claim"),
]


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def load() -> dict:
    ev = json.loads((RESULTS / "test_evidence.json").read_text("utf-8"))
    net = json.loads((ROOT / "config/network.json").read_text("utf-8"))
    chart = json.loads((RESULTS / "chart_data.json").read_text("utf-8"))
    rows = {r["test_id"]: r for r in ev["rows"]}
    return {"ev": ev, "net": net, "chart": chart, "rows": rows,
            "s": ev["summary"], "env": ev["environment"]}


def blank(prs: Presentation):
    return prs.slides.add_slide(prs.slide_layouts[6])


def text(slide, x, y, w, h, content, size=16, bold=False, color=DARK, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, line_spacing=1.25, italic=False):
    box = slide.shapes.add_textbox(Cm(x), Cm(y), Cm(w), Cm(h))
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    size = min(size * SCALE, MAX_PT)
    lines = content if isinstance(content, list) else [content]
    for i, line in enumerate(lines):
        par = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        par.alignment = align
        par.line_spacing = line_spacing
        run = par.add_run()
        run.text = line
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = color
        run.font.name = FONT
    return box


def rect(slide, x, y, w, h, fill, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, adj=0.06):
    shp = slide.shapes.add_shape(shape, Cm(x), Cm(y), Cm(w), Cm(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(0.75)
    shp.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        shp.adjustments[0] = adj
    return shp


def notes(slide, script: str) -> None:
    slide.notes_slide.notes_text_frame.text = script


def part_badge(slide, part_idx: int) -> None:
    """'Part 2 / 5 - Part 2' in the top right corner of a content slide."""
    num, _title, short, color, _delivers = PARTS[part_idx - 1]
    text(slide, 22.6, 0.55, 10.0, 0.8, f"Part {num} of 5  -  {short}", size=9.5, bold=True,
         color=color, align=PP_ALIGN.RIGHT)


def title_bar(slide, title, kicker=None, part_idx=None, page=None):
    rect(slide, 0, 0, 33.87, 0.22, NAVY, shape=MSO_SHAPE.RECTANGLE)
    size = 24 if len(title) <= 44 else (20 if len(title) <= 56 else 18)
    text(slide, MARGIN, 0.75, 26.6, 1.45, title, size=size, bold=True, color=NAVY)
    if kicker:
        text(slide, MARGIN, 2.25, 29.4, 0.8, kicker, size=11, color=GREY)
    if part_idx:
        part_badge(slide, part_idx)
    if page:
        text(slide, 30.6, 17.95, 2.6, 0.8, str(page), size=10, color=GREY, align=PP_ALIGN.RIGHT)


def table(slide, x, y, w, headers, rows, col_ratios, font_size=10.5, header_size=10.5,
          row_h=1.0, header_fill=NAVY, highlight_rows=(), center_cols=()):
    font_size = font_size * SCALE
    header_size = header_size * SCALE
    row_h = row_h * 1.12
    shape = slide.shapes.add_table(len(rows) + 1, len(headers), Cm(x), Cm(y), Cm(w),
                                   Cm(row_h * (len(rows) + 1)))
    tbl = shape.table
    total = sum(col_ratios)
    for i, ratio in enumerate(col_ratios):
        tbl.columns[i].width = Cm(w * ratio / total)
    for j, head in enumerate(headers):
        cell = tbl.cell(0, j)
        cell.text = ""
        cell.fill.solid()
        cell.fill.fore_color.rgb = header_fill
        cell.margin_left = cell.margin_right = Cm(0.16)
        cell.margin_top = cell.margin_bottom = Cm(0.06)
        par = cell.text_frame.paragraphs[0]
        par.alignment = PP_ALIGN.CENTER
        run = par.add_run()
        run.text = head
        run.font.size = Pt(header_size)
        run.font.bold = True
        run.font.color.rgb = WHITE
        run.font.name = FONT
    for i, row in enumerate(rows, start=1):
        if (i - 1) in highlight_rows:
            row_fill = RGBColor(0xE8, 0xF5, 0xE9)
        else:
            row_fill = LIGHT if i % 2 == 0 else WHITE
        for j, value in enumerate(row):
            cell = tbl.cell(i, j)
            cell.text = ""
            cell.fill.solid()
            cell.fill.fore_color.rgb = row_fill
            cell.margin_left = cell.margin_right = Cm(0.16)
            cell.margin_top = cell.margin_bottom = Cm(0.05)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            par = cell.text_frame.paragraphs[0]
            par.alignment = PP_ALIGN.CENTER if j in center_cols else PP_ALIGN.LEFT
            run = par.add_run()
            run.text = str(value)
            run.font.size = Pt(font_size)
            run.font.color.rgb = DARK
            run.font.name = FONT
    return tbl


def picture(slide, path, x, y, w=None, h=None):
    if not Path(path).exists():
        rect(slide, x, y, w or 6, h or 3, LIGHT)
        text(slide, x + 0.3, y + 0.3, (w or 6) - 0.6, 1, f"[missing {Path(path).name}]",
             size=10, color=RED)
        return
    if w:
        slide.shapes.add_picture(str(path), Cm(x), Cm(y), width=Cm(w))
    else:
        slide.shapes.add_picture(str(path), Cm(x), Cm(y), height=Cm(h))


def kpi(slide, x, y, w, value, label, color=BLUE, value_size=28):
    rect(slide, x, y, w, 3.3, LIGHT)
    rect(slide, x, y, 0.13, 3.3, color, shape=MSO_SHAPE.RECTANGLE)
    text(slide, x + 0.45, y + 0.45, w - 0.8, 1.5, value, size=value_size, bold=True, color=color)
    text(slide, x + 0.45, y + 2.0, w - 0.7, 1.35, label, size=8.5, color=GREY, line_spacing=1.12)


def handoff(slide, who: str, what: str, color: RGBColor) -> None:
    """The strip at the bottom of a member's last slide: what they pass on."""
    rect(slide, MARGIN, 16.05, 30.6, 1.35, LIGHT)
    rect(slide, MARGIN, 16.05, 0.14, 1.35, color, shape=MSO_SHAPE.RECTANGLE)
    text(slide, MARGIN + 0.45, 16.05, 3.4, 1.35, f"Handover to {who}", size=10.5, bold=True,
         color=color, anchor=MSO_ANCHOR.MIDDLE)
    text(slide, MARGIN + 3.95, 16.05, 26.1, 1.35, what, size=10.5, color=DARK,
         anchor=MSO_ANCHOR.MIDDLE)


def section_slide(prs, idx: int) -> None:
    """Divider that opens one part of the talk. The part number is the headline;
    the topic underneath says what the part covers."""
    num, title, _short, color, delivers = PARTS[idx - 1]
    slide = blank(prs)
    rect(slide, 0, 0, 13.2, 19.05, color, shape=MSO_SHAPE.RECTANGLE)
    text(slide, 1.5, 3.0, 10.5, 1.2, "Presentation outline", size=13, bold=True,
         color=RGBColor(0xCF, 0xD8, 0xDC))
    text(slide, 1.3, 4.1, 11.2, 3.6, f"Part {num}", size=54, bold=True, color=WHITE)
    text(slide, 1.5, 9.0, 10.4, 3.2, title, size=11.5, color=RGBColor(0xE3, 0xEA, 0xEE),
         line_spacing=1.3)

    # three-layer stack: shows where this part sits, and that rules live in the contract
    text(slide, 1.5, 12.5, 10.4, 0.55,
         "Where this part sits" if num != "5" else "Where this part sits - all three layers",
         size=9, bold=True, color=RGBColor(0xCF, 0xD8, 0xDC))
    owned = {"1": {"Interface"}, "2": {"Contract"}, "3": {"Contract"},
             "4": {"Presentation"}, "5": {"Presentation", "Interface", "Contract"}}[num]
    for i, layer in enumerate(["Presentation", "Interface", "Contract"]):
        y = 13.05 + i * 1.2
        active = layer in owned
        chip = rect(slide, 1.5, y, 10.4, 1.0, WHITE if active else color,
                    shape=MSO_SHAPE.ROUNDED_RECTANGLE, adj=0.18)
        if not active:
            chip.fill.background()
            chip.line.color.rgb = RGBColor(0xCF, 0xD8, 0xDC)
            chip.line.width = Pt(0.75)
        text(slide, 1.85, y, 9.8, 1.0,
             layer + ("  -  this part" if active and num != "5" else ""),
             size=8.5, bold=active, color=color if active else RGBColor(0xCF, 0xD8, 0xDC),
             anchor=MSO_ANCHOR.MIDDLE)
    text(slide, 15.0, 3.9, 17.6, 0.9, "What this part delivers", size=12, bold=True, color=color)
    text(slide, 15.0, 4.9, 17.4, 3.2, delivers, size=19, color=DARK, line_spacing=1.35)
    text(slide, 15.0, 8.9, 17.4, 0.9, "The five parts, in order", size=12, bold=True, color=GREY)
    for i, (n2, _t2, short2, *_) in enumerate(PARTS, start=1):
        y = 9.75 + (i - 1) * 1.45
        active = i == idx
        rect(slide, 15.0, y, 17.4, 1.2, color if active else LIGHT,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, adj=0.2)
        text(slide, 15.4, y, 2.6, 1.2, f"Part {n2}", size=9.5, bold=True,
             color=WHITE if active else GREY, anchor=MSO_ANCHOR.MIDDLE)
        text(slide, 18.1, y, 14.2, 1.2, short2, size=9.5,
             bold=active, color=WHITE if active else DARK, anchor=MSO_ANCHOR.MIDDLE)
    notes(slide,
          f"Part {num} begins. Opening line: 'Part {num}: {title}.' "
          f"What this part proves: {delivers}. Keep this slide to about ten seconds - it exists only to "
          f"make the change of speaker visible to the audience.")


# ----------------------------------------------------------------------
def build() -> Path:
    d = load()
    s, env, net, rows = d["s"], d["env"], d["net"], d["rows"]
    g = d["chart"]["gas_median"]
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    page = 0

    def next_page() -> int:
        nonlocal page
        page += 1
        return page

    def gas(test_id: str) -> str:
        value = rows.get(test_id, {}).get("gas_used")
        return f"{int(value):,}" if value not in ("", None) else "n/a"

    # ---------------------------------------------------------------- 1 cover
    slide = blank(prs)
    next_page()
    rect(slide, 0, 0, 33.87, 19.05, NAVY, shape=MSO_SHAPE.RECTANGLE)
    rect(slide, 0, 13.1, 33.87, 0.12, BLUE, shape=MSO_SHAPE.RECTANGLE)
    text(slide, 2.6, 2.6, 28, 1, "FTEC5520 Applied Blockchain and Cryptocurrencies", size=13,
         color=RGBColor(0xB0, 0xBE, 0xC5))
    text(slide, 2.6, 3.9, 30.6, 1.8, "Anti-Scalping Concert Ticketing System", size=29, bold=True,
         color=WHITE)
    text(slide, 2.6, 6.0, 30, 1.0, "Five parts, five speakers, one running private chain", size=15,
         color=RGBColor(0xCF, 0xD8, 0xDC))
    text(slide, 2.6, 7.2, 30, 1.0,
         "Geth Clique chain  -  ERC-721 tickets  -  price-capped resale  -  on-chain check-in",
         size=11.5, color=RGBColor(0x90, 0xCA, 0xF9))
    for i, (num, _title, short, _color, _delivers) in enumerate(PARTS):
        x = 2.6 + i * 5.75
        rect(slide, x, 8.9, 5.35, 2.9, RGBColor(0x2B, 0x48, 0x78))
        text(slide, x + 0.35, 9.05, 4.7, 0.7, f"Part {num}", size=10.5, bold=True, color=WHITE)
        text(slide, x + 0.35, 9.8, 4.7, 1.8, short, size=8,
             color=RGBColor(0xB0, 0xBE, 0xC5), line_spacing=1.15)
    text(slide, 2.6, 12.6, 28, 0.9,
         f"Group 18 (five members)  -  contract "
         f"{net['contract_address'][:10]}...{net['contract_address'][-4:]}  -  "
         f"{s['total_cases']} test cases, pass rate {s['pass_rate']}%",
         size=12, color=RGBColor(0xCF, 0xD8, 0xDC))
    text(slide, 2.6, 13.6, 28, 0.9,
         "All figures in this deck come from one continuous run on the chain",
         size=11, color=RGBColor(0x90, 0xCA, 0xF9), italic=True)
    notes(slide,
          "Opening speaker (usually Part 1). One sentence on the project: we moved five ticketing rules "
          "from a database into a smart contract, then tried to break them. Announce the format: five parts, "
          "each speaker covers their own work and hands over to the next. About 20 minutes, demo at the end.")

    # ---------------------------------------------------------------- 2 agenda
    slide = blank(prs)
    next_page()
    title_bar(slide, "Agenda: who speaks, in what order, with what proof",
              "Each part ends with a handover, because that is how the work actually moved", page=page)
    body = [[num, title, delivers] for num, title, _s, _c, delivers in PARTS]
    table(slide, MARGIN, 3.15, 30.6, ["Part", "What the part covers", "Delivers to the next part"], body,
          [1.9, 14.2, 14.5], font_size=9.5, row_h=1.5, center_cols=(0,))
    text(slide, MARGIN, 14.3, 30.6, 2.4,
         ["Then: one live end-to-end demo (seven actions) and Q & A.",
          "Evidence for every claim is in results/test_results.csv and results/test_evidence.json,",
          "so any number on a slide can be traced to a transaction hash."],
         size=11.5, color=GREY, line_spacing=1.45)
    notes(slide,
          "Walk the table left to right. Stress two things: the parts follow the real development order, so "
          "the audience always knows what already exists when the next person starts; and every part ends "
          "with something handed over - a contract, an ABI, an address, a passing test list. Roughly four "
          "minutes per part.")

    # ---------------------------------------------------------------- 3 problem
    slide = blank(prs)
    next_page()
    title_bar(slide, "The problem: scalping is three different attacks",
              "One shared statement before the five parts, so each speaker can refer back to it", page=page)
    cards = [
        ("1. Bulk buying", "Scripts and many wallets sweep the stock at on-sale time\n"
                           "Limits are per account and accounts are cheap",
         "Countermeasure: per-wallet counter on chain", RED),
        ("2. Markup resale", "Listed at 3-5x; platforms only suggest a cap\n"
                             "Off-platform transfers ignore the market entirely",
         "Countermeasure: dynamic cap + transfer override", AMBER),
        ("3. Duplicate entry", "A QR screenshot can be forwarded\n"
                               "Check-in state sits in a database",
         "Countermeasure: one-time check-in + signed QR", BLUE),
    ]
    for i, (head, body_txt, fix, color) in enumerate(cards):
        x = MARGIN + i * 10.5
        rect(slide, x, 3.2, 9.8, 8.6, LIGHT)
        rect(slide, x, 3.2, 9.8, 0.2, color, shape=MSO_SHAPE.RECTANGLE)
        text(slide, x + 0.45, 3.65, 8.9, 0.9, head, size=17, bold=True, color=color)
        text(slide, x + 0.45, 4.7, 8.9, 3.2, body_txt.split("\n"), size=10, color=DARK,
             line_spacing=1.4)
        rect(slide, x + 0.45, 8.0, 8.9, 0.03, RGBColor(0xCF, 0xD8, 0xDC),
             shape=MSO_SHAPE.RECTANGLE)
        text(slide, x + 0.45, 8.5, 8.9, 2.6, fix, size=10, bold=True, color=NAVY)
    rect(slide, MARGIN, 12.6, 30.6, 3.3, LIGHT)
    text(slide, MARGIN + 0.5, 12.6, 29.6, 3.3,
         ["Working hypothesis: a rule in an operator's database is a policy;",
          "a require executed by the EVM is a fact. The goal is therefore not a pretty site but a system",
          "in which 'skip the website' is technically impossible."],
         size=11, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE, line_spacing=1.45)
    notes(slide,
          "Shared context, about one minute. Use the three columns as the running theme: Part 2 attacks "
          "column 1, Part 3 attacks columns 2 and 3, Part 4 builds the credential, Part 5 measures whether "
          "the refusals really happen. Close with the bottom band - it is the sentence the deck proves.")

    # ================================================================ PART 1
    section_slide(prs, 1)
    next_page()

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 1: the chain, the deployment and the evidence",
              "Nothing in this project is real until it is mined - this part makes it real", 1, page)
    kpi(slide, MARGIN, 3.15, 7.3, str(env["chain"]["chain_id"]),
        "chainId - Clique PoA, 2 s blocks", BLUE, 24)
    kpi(slide, 9.2, 3.15, 7.3, f"{env['contract']['deploy_gas_used']:,}",
        "gas for the deployment transaction", TEAL, 24)
    kpi(slide, 16.8, 3.15, 7.3, f"{env['contract']['deployed_bytes']:,}",
        "bytes of runtime contract code", NAVY, 24)
    kpi(slide, 24.4, 3.15, 7.8, str(env["contract"]["abi_items"]),
        "ABI entries handed to Part 4", GREEN, 24)
    text(slide, MARGIN, 7.0, 15.0, 0.8, "What I built", size=12.5, bold=True, color=BLUE)
    bullets_left = [
        "genesis.json with seven funded accounts; the Clique signer is written into extradata",
        "start_node.sh / stop_node.sh: one command to rebuild or stop a node",
        "compile.py: solc 0.8.20, evmVersion paris (no PUSH0 on an older chain)",
        "deploy.py: deploys, then writes config/network.json - the only source of the address",
    ]
    for i, item in enumerate(bullets_left):
        text(slide, MARGIN, 7.7 + i * 1.7, 15.4, 1.6, "- " + item, size=9.5, color=DARK,
             line_spacing=1.2)
    text(slide, 17.6, 7.0, 14.2, 0.8, "What the chain actually provides", size=12.5, bold=True,
         color=BLUE)
    text(slide, 17.6, 7.8, 13.8, 7.0,
         ["No business logic of its own - it is the executor.",
          "What it gives the other parts:",
          "",
          "-  a fixed address, unchanged during the demo",
          "-  a receipt for every transaction, failures too",
          "-  blocks fast enough to show live state",
          "",
          "So every later claim can end with a tx hash."],
         size=9.5, color=DARK, line_spacing=1.4)
    handoff(slide, "Parts 2 and 3", "ABI + bytecode (contracts/build/ConcertTicket.json) and a deployed "
                                   "address the interface can call", BLUE)
    notes(slide,
          "Part 1, about two minutes. Introduce the chain in one breath: Geth 1.13.15, Clique proof of "
          "authority, chainId 1337, two-second blocks, seven funded accounts. Then the four numbers: the "
          "deployment cost about 3.3 million gas, produced 14,339 bytes of runtime code and 67 ABI entries. "
          "Close on the handover strip: what the next members receive is an address and an ABI, not a "
          "screenshot.")

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 1: one interface, one return shape",
              "So no page ever builds a raw transaction and no page ever guesses a result", 1, page)
    text(slide, MARGIN, 2.95, 15.0, 0.8, "The six functions every later part calls", size=11,
         bold=True, color=BLUE)
    body = [["get_ticket_owner(tokenId)", "read", "current owner, the single source of truth"],
            ["buy_ticket(eventId, buyer, qty)", "write", "purchase and mint"],
            ["list_ticket(tokenId, price, seller)", "write", "list for resale"],
            ["buy_resale(tokenId, buyer)", "write", "buy a listing"],
            ["check_in(tokenId, verifier)", "write", "on-chain check-in"],
            ["get_receipt(txHash)", "read", "was it mined, and what did it cost"]]
    table(slide, MARGIN, 3.9, 15.2, ["Function", "Kind", "What it does"], body,
          [7.0, 1.4, 6.8], font_size=10, row_h=1.35, center_cols=(1,))
    text(slide, 17.8, 3.1, 14.0, 0.8, "Every write returns the same struct", size=12.5, bold=True,
         color=BLUE)
    rect(slide, 17.8, 3.95, 14.0, 2.6, LIGHT)
    text(slide, 18.2, 4.2, 13.2, 2.2,
         ["TxResult( ok, tx_hash, block_number,",
          "          gas_used, status, error )"],
         size=11.5, color=NAVY, line_spacing=1.5)
    text(slide, 17.8, 6.9, 14.0, 6.4,
         ["Why it matters:",
          "",
          "-  every later slide quotes the same fields",
          "-  estimate_gas runs first, so a doomed call costs",
          "   no gas and returns the contract's own reason",
          "-  failures are data, not silence: status=0"],
         size=9.5, color=DARK, line_spacing=1.4)
    handoff(slide, "Part 4", "RPC url, chain id, contract address, ABI and these functions - the page "
                               "layer only calls them", BLUE)
    notes(slide,
          "Part 1, about two minutes. Do not read the six functions; say that the page layer may only call "
          "these, which is why the interface can be tested without Streamlit. Then the TxResult struct: one "
          "shape for every write means the same evidence on every later slide. Mention the pre-check: "
          "estimate_gas first, so a doomed call returns the revert reason without spending gas.")

    # ================================================================ PART 2
    section_slide(prs, 2)
    next_page()

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 2: who may buy, how many, and at what price",
              "Tickets are minted inside the purchase, so tokenId equals 'the n-th ticket sold'", 2, page)
    body = [["createEvent", "anyone may create; the caller becomes that event's organizer", "T01"],
            ["setWhitelist / Batch", "organizer only; presale list per event", "T03 / T04"],
            ["purchaseTickets", "stock, wallet limit, whitelist, exact payment, then mint", "T05 / T06"],
            ["canPurchase", "read-only pre-check returning (bool, reason)", "used by Part 4"],
            ["withdrawProceeds", "pull payment: the organizer withdraws, the sale never blocks", "T01"]]
    table(slide, MARGIN, 3.25, 18.4, ["Function", "Rule encoded in the contract", "Test"], body,
          [4.4, 11.6, 2.4], font_size=9, row_h=1.4, center_cols=(2,))
    text(slide, 20.8, 2.95, 11.2, 0.75, "Measured in this run", size=11, bold=True, color=TEAL)
    ev = [["T01", "event created, fields readable", gas("T01")],
          ["T05a", "2 tickets in one call = the limit", gas("T05a")],
          ["T05b", "3rd ticket rejected", gas("T05b")],
          ["T06a", "last ticket sold", gas("T06a")],
          ["T06b", "purchase after sell-out rejected", gas("T06b")]]
    table(slide, 20.8, 3.8, 11.2, ["Case", "What it proves", "Gas"], ev,
          [1.5, 6.6, 2.2], font_size=8.5, row_h=1.15, center_cols=(0, 2))
    text(slide, MARGIN, 13.15, 30.6, 2.8,
         ["T02b is a deliberate deviation: createEvent has no access control, so anyone can create an event.",
          "canPurchase is the read-only pre-check the page calls; T04, T05b and T06b assert the same rules on chain."],
         size=9, color=GREY, line_spacing=1.35)
    handoff(slide, "Part 3", "Ticket state (ownerOf, tokenToEvent) and the purchase path that the resale "
                               "rules must reuse - one ticket struct, not two", TEAL)
    notes(slide,
          "Part 2, about two and a half minutes. Walk the table top to bottom: creation, whitelist, "
          "purchase, pre-check, settlement. Two design choices worth naming: tickets are minted inside the "
          "purchase transaction, so ids map to sale order and reconciliation is trivial; revenue is "
          "pull-based, so a recipient that rejects ETH cannot block a sale. Then the honest caveat on T02b - "
          "raising it yourself is stronger than being asked about it.")

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 2: the purchase path, and where my part ends",
              "The handover to Part 3 is a data structure, not a document", 2, page)
    steps = [("1", "Read the event", "price, supply, limit, presale flag, start time"),
             ("2", "Pre-check", "canPurchase returns the reason, the UI shows it before sending"),
             ("3", "Charge exactly", "msg.value must equal price x quantity - no rounding, no discounts"),
             ("4", "Book the money", "credit pendingProceeds[organizer]; nothing is pushed out yet"),
             ("5", "Mint", "one ERC-721 per ticket, then emit TicketPurchased")]
    for i, (num, head, detail) in enumerate(steps):
        y = 3.2 + i * 2.35
        rect(slide, MARGIN, y, 1.4, 1.8, TEAL, shape=MSO_SHAPE.OVAL)
        text(slide, MARGIN, y + 0.35, 1.4, 0.9, num, size=13, bold=True, color=WHITE,
             align=PP_ALIGN.CENTER)
        text(slide, MARGIN + 1.9, y + 0.05, 6.4, 0.8, head, size=12.5, bold=True, color=NAVY)
        text(slide, MARGIN + 1.9, y + 0.85, 12.2, 1.0, detail, size=10.5, color=DARK)
    rect(slide, 17.4, 3.2, 14.4, 12.2, LIGHT)
    text(slide, 17.9, 3.45, 13.4, 0.9, "What Part 3 inherits", size=12.5, bold=True, color=TEAL)
    text(slide, 17.9, 4.45, 13.4, 10.6,
         ["ticketToEvent[tokenId]",
          "  -  the event a ticket belongs to, so the price cap",
          "     can be derived from that event's price",
          "",
          "tickets[tokenId] =",
          "  {isListed, listingPrice, resaleCount, used}",
          "  -  the four fields resale and check-in mutate",
          "",
          "require order:",
          "  stock -> limit -> whitelist -> payment",
          "  (it decides which error a user sees)"],
         size=9, color=DARK, line_spacing=1.32)
    handoff(slide, "Part 3", "One ticket struct with four mutable fields, and a purchase path that "
                               "already enforces stock, limit, whitelist and payment", TEAL)
    notes(slide,
          "Part 2, about two minutes. Five steps, one sentence each: read, pre-check, charge exactly, book "
          "the money, mint. The right-hand box is the real handover - Part 3 needs no new ticket model, it "
          "mutates four fields that already exist. The parenthetical on require order is a 'we really ran "
          "it' detail: a test had to be rewritten because the wallet limit fires before the payment check.")

    # ================================================================ PART 3
    section_slide(prs, 3)
    next_page()

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 3: the price cap follows the clock",
              "Two regimes, one boundary, and a resale counter that cannot be reset", 3, page)

    body = [["More than 7 days out", "120% of the original price", "T08 / T08b"],
            ["7 days or less", "100% of the original price", "T09a / T09b / T09c"],
            ["Exactly 7 days", "cap switches to 100% (boundary)", "T09d"],
            ["Resale #1 to #3", "allowed, the counter increments", "T07a / T07b / T10a"],
            ["A fourth listing", "rejected: Max resale limit reached", "T10b"]]
    table(slide, MARGIN, 3.3, 15.4, ["Condition", "Enforced cap / effect", "Test"], body,
          [5.2, 7.6, 3.0], font_size=8.8, row_h=1.32, center_cols=(2,))
    text(slide, 17.8, 3.3, 14.0, 0.8, "Why the rule must be time-based", size=11, bold=True,
         color=NAVY)
    text(slide, 17.8, 4.05, 13.9, 4.2,
         ["A flat 120% cap invites the obvious arbitrage:",
          "wait for the last week, when demand peaks, and",
          "still charge a 20% premium.",
          "",
          "Tying the cap to block.timestamp closes that",
          "window - and the chain reads the clock, not the page."],
         size=9.5, color=DARK, line_spacing=1.4)
    rect(slide, 17.8, 8.5, 13.9, 5.1, LIGHT)
    text(slide, 18.2, 8.75, 13.1, 4.7,
         ["Measured:",
          f"  T09b  list 0.51, cap 0.50  -> rejected ({gas('T09b')})",
          f"  T09c  list exactly 0.50    -> accepted ({gas('T09c')})",
          f"  T10b  4th listing at 3     -> rejected ({gas('T10b')})"],
         size=9, color=DARK, line_spacing=1.5)
    handoff(slide, "Part 4", "listForResale / buyResale / cancelListing and getMaxResalePrice - the page "
                               "only displays the cap the contract returns", NAVY)
    notes(slide,
          "Part 3, about two and a half minutes. Lead with the two regimes and the exact boundary: more "
          "than seven days is 120%, seven days or less is 100%, and T09d proves the switch by listing 1.00 "
          "and 1.01 ETH against a 1.00 cap. Then the counter: three resales allowed, the fourth listing "
          "reverts. Point at the three measured lines: claiming a cap is not the same as demonstrating one.")

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 3: closing the escape hatch, then one-time entry",
              "A price cap inside buyResale is useless if the token can still be transferred", 3, page)
    text(slide, MARGIN, 3.05, 15.2, 0.8, "The escape hatch we had to close", size=12.5, bold=True,
         color=RED)
    text(slide, MARGIN, 3.85, 15.2, 3.2,
         ["ERC-721 ships with transferFrom and safeTransferFrom. If they stay",
          "callable, an owner simply moves the token and every resale rule is",
          "skipped - the cap, the counter, the platform fee, all of it.",
          "",
          "Both entry points are overridden to revert."],
         size=10.5, color=DARK, line_spacing=1.4)
    body = [["T11a", "holder calls transferFrom", "mined, status=0", gas("T11a")],
            ["T11b", "holder calls safeTransferFrom", "mined, status=0", gas("T11b")],
            ["B02", "same attack, no UI, raw Web3.py", "mined, status=0", gas("B02")]]
    table(slide, MARGIN, 7.7, 15.2, ["Case", "Attempt", "Result", "Gas"], body,
          [1.3, 6.4, 4.0, 1.8], font_size=8.5, row_h=1.25, center_cols=(0, 2, 3))
    text(slide, MARGIN, 13.6, 15.2, 2.2,
         ["Gas is still charged on all three: the transaction exists,",
          "the state did not change. That is 'the rule is on chain'."],
         size=9, color=GREY, line_spacing=1.35)
    text(slide, 17.6, 2.95, 14.2, 0.8, "Check-in: one ticket, one entry", size=11, bold=True,
         color=NAVY)
    body2 = [["T15b", "authorised verifier, first check-in", "used = true"],
             ["T16", "same ticket, second check-in", "Ticket already used"],
             ["T17 / B03", "account without the verifier role", "Not an authorized verifier"],
             ["E09", "check-in while listed", "listing cleared automatically"],
             ["T07b", "5% platform fee on a 1.2 ETH resale", "0.06 ETH booked to the owner"]]
    table(slide, 17.6, 3.85, 14.2, ["Case", "Action", "Observed"], body2,
          [1.9, 6.9, 5.4], font_size=8.5, row_h=1.25, center_cols=(0,))
    handoff(slide, "Parts 4 and 5", "A ticket that cannot move outside the rules, one Boolean that proves "
                                   "entry, and five cases for Part 5 to re-run", NAVY)
    notes(slide,
          "Part 3, about three minutes - the heart of the anti-scalping story. Start from the escape "
          "hatch: ERC-721 gives everyone a transfer function, so a cap inside buyResale alone would be "
          "theatre. Then the three rows: all mined, all status=0, all still paid gas. Finish with check-in: "
          "first time succeeds, second time reverts, unauthorised callers rejected, a listed ticket gets "
          "de-listed. Hand the five cases to Part 5.")

    # ================================================================ PART 4
    section_slide(prs, 4)
    next_page()

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 4: six pages that only display the chain",
              "Every screen reads ownerOf or tickets() - none of them caches a business decision", 4, page)
    text(slide, MARGIN, 2.8, 17.6, 0.45,
         "Buy Tickets: pre-check, transaction and ownerOf read-back on one screen",
         size=8.5, bold=True, color=BLUE)
    picture(slide, SHOTS / "03_buy_tickets.png", MARGIN, 3.5, w=17.6)
    text(slide, 20.0, 2.95, 12.4, 0.6, "What to look at on each page", size=10, bold=True, color=BLUE)
    text(slide, 20.0, 3.7, 12.4, 8.4,
         ["Overview - chainId, block number, contract,",
          "balances, recent transfers.",
          "",
          "Events - create an event, toggle the sale",
          "switch, batch whitelist, settle.",
          "",
          "Resale - the live cap, list, buy, cancel;",
          "the over-price button fails on purpose."],
         size=9, color=DARK, line_spacing=1.4)
    for i, (fname, label) in enumerate([("01_overview.png", "Overview"),
                                        ("02_events.png", "Events"),
                                        ("05_resale_market.png", "Resale market")]):
        x = MARGIN + i * 10.4
        picture(slide, SHOTS / fname, x, 12.75, w=9.6)
        text(slide, x, 17.5, 9.6, 0.5, label, size=8, bold=True, color=GREY)
    notes(slide,
          "Part 4, about two minutes. Start with the hero screenshot: the buy page is the one screen where the "
          "pre-check and the transaction appear together, so it is the best single example of the "
          "'page only reports the chain' claim. Then the three small ones, one sentence each: the overview "
          "reads chainId and Transfer logs, the events page writes the rules, the resale page shows the cap "
          "that getMaxResalePrice returned. Do not read the UI text aloud.")

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 4: the QR is a signed claim, not a token id",
              "A screenshot must fail; a resold ticket must fail; a repeat entry must fail", 4, page)
    picture(slide, SHOTS / "04_my_tickets.png", MARGIN, 3.15, h=10.6)
    text(slide, 9.35, 3.15, 10.5, 0.8, "What the QR payload carries", size=10.5, bold=True, color=BLUE)
    rect(slide, 9.35, 3.85, 10.5, 2.5, LIGHT)
    text(slide, 9.55, 4.0, 10.1, 2.2,
         ["{ v, token_id, holder, nonce,",
          "  issued_at, expires_at, sig }",
          "sig = holder's EIP-191 signature"],
         size=8.5, color=NAVY, line_spacing=1.45)
    text(slide, 9.35, 6.55, 10.5, 0.75, "Five checks, in this order", size=10.5, bold=True, color=BLUE)
    checks = [["1", "version", "T13"], ["2", "recovered signer == holder", "T14a"],
              ["3", "not expired (180 s)", "T14b"], ["4", "holder == on-chain ownerOf", "T14c"],
              ["5", "used is still false", "T15b"]]
    table(slide, 9.35, 7.35, 10.5, ["", "Check", "Case"], checks, [0.9, 7.2, 2.4],
          font_size=8.5, row_h=1.05, center_cols=(0, 2))
    picture(slide, SHOTS / "06_staff_checkin.png", 20.4, 3.15, w=13.0)
    text(slide, 20.4, 10.0, 13.0, 5.0,
         ["Three attacks, three different checks:",
          "",
          "-  forwarded screenshot -> expiry",
          "-  previous owner      -> ownerOf",
          "-  second entry        -> used",
          "",
          "Off-chain proves who holds it; the chain",
          "does the irreversible check-in."],
         size=9, color=DARK, line_spacing=1.35)
    handoff(slide, "Part 5", "Six pages, a signed QR flow and the check-in page - plus the screenshots "
                               "used in the report", BLUE)
    notes(slide,
          "Part 4, about two and a half minutes. Read the payload line once, then focus on the five checks "
          "and the attack each one kills: a forwarded screenshot dies on expiry, the previous owner dies on "
          "ownerOf, a repeat entry dies on used. Then state the boundary: the off-chain half proves who "
          "holds the ticket, the on-chain half performs the irreversible check-in.")

    # ================================================================ PART 5
    section_slide(prs, 5)
    next_page()

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 5: 48 cases, two kinds of evidence each",
              "Every negative case is forced on chain, so a refusal is a receipt and not an opinion", 5, page)
    kpi(slide, MARGIN, 3.15, 7.2, str(s["total_cases"]),
        "cases: T01-T18 + 12 extra + the B01-B04 bypass tests", BLUE, 22)
    kpi(slide, 9.1, 3.15, 7.2, f"{s['pass_rate']}%", "pass rate: PASS 46 / FAIL 0", GREEN, 22)
    kpi(slide, 16.5, 3.15, 7.2, str(s["on_chain_failed_txs"]), "rejected but mined (status=0)", RED, 22)
    kpi(slide, 23.9, 3.15, 8.3, f"{s['on_chain_failed_gas_total']:,}", "gas burned by those refusals",
        AMBER, 22)
    picture(slide, CHARTS / "01_test_results_by_module.png", MARGIN, 7.0, w=16.8)
    text(slide, 19.0, 7.0, 13.2, 0.8, "Judging rules I kept to", size=11.5, bold=True, color=GREEN)
    text(slide, 19.0, 7.85, 13.2, 7.4,
         ["-  a case expected to fail passes only",
          "   when the contract really rejects it",
          "-  positive cases also read ownerOf,",
          "   resaleCount, used and the fee balance",
          "-  each case makes its own event, so the",
          "   suite repeats without redeploying",
          "-  two deviations documented, not hidden"],
         size=9, color=DARK, line_spacing=1.4)
    handoff(slide, "Everyone", "One CSV and one JSON that Parts 1 to 4 can point at: 48 rows, each with a "
                               "transaction hash, a block and a gas figure", GREEN)
    notes(slide,
          "Part 5, about two and a half minutes. Do not list cases - explain the two decisions that make "
          "the numbers trustworthy: the judging rule for negative cases, and forcing every negative case on "
          "chain so we own a status=0 receipt. Then the odd-looking number: 24 transactions were rejected "
          "and still cost 782,049 gas, which is exactly the cost argument for rules on chain.")

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 5: what each rule costs",
              "Medians of real receipts - not estimates, and not gas limits", 5, page)
    picture(slide, CHARTS / "02_gas_comparison.png", MARGIN, 3.2, w=20.6)
    text(slide, 22.9, 3.3, 9.3, 12.2,
         ["Three things to take away",
          "",
          "1.  Issuance and purchase dominate: 168k to",
          "     create an event, 156k to buy one ticket.",
          "",
          "2.  Enforcement is cheap: listing 80k, check-in",
          "     52k - the rules are not where the money goes.",
          "",
          "3.  The second ticket adds only ~56k, so batching",
          "     is cheaper per ticket - which is exactly why",
          "     scalpers batch."],
         size=10.5, color=DARK, line_spacing=1.4)
    rect(slide, MARGIN, 15.1, 30.6, 1.5, LIGHT)
    rect(slide, MARGIN, 15.1, 0.14, 1.5, GREEN, shape=MSO_SHAPE.RECTANGLE)
    text(slide, MARGIN + 0.5, 15.1, 29.6, 1.5,
         "The rules are cheap to enforce - what costs is issuing and selling the ticket in the first place.",
         size=11.5, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)
    notes(slide,
          "Part 5, about one minute. One number per point: 168k, 156k, 52k, and the 56k marginal cost of the "
          "second ticket. The point the audience should remember: the expensive operations are issuance and "
          "purchase; enforcing the rules is comparatively cheap, so the rules are not what makes this "
          "system costly.")

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 5: what a refused call costs",
              "The same operations, measured twice: once accepted, once rejected", 5, page)
    picture(slide, CHARTS / "03_coverage_and_failed_tx.png", MARGIN, 3.2, w=21.6)
    text(slide, 23.1, 3.3, 9.1, 12.2,
         ["Left panel: 19 normal-path and 27 negative-path",
          "cases. For this system the value is in the",
          "refusals, so negative cases outnumber them.",
          "",
          "Right panel: a rejected purchase still burns ~41k",
          "gas, a rejected listing ~34k, a rejected check-in",
          "~24k.",
          "",
          "In total 24 refused calls cost 782,049 gas - which",
          "is why Part 2 pre-checks with canPurchase."],
         size=10.5, color=DARK, line_spacing=1.4)
    rect(slide, MARGIN, 15.1, 30.6, 1.5, LIGHT)
    rect(slide, MARGIN, 15.1, 0.14, 1.5, RED, shape=MSO_SHAPE.RECTANGLE)
    text(slide, MARGIN + 0.5, 15.1, 29.6, 1.5,
         "A refusal is not something we made up: the transaction is mined, status=0, and gas is still charged.",
         size=11.5, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)
    notes(slide,
          "Part 5, about one and a half minutes. The left panel explains why negative cases outnumber "
          "positive ones. The right panel is the important one: a refused call is still mined and still "
          "charges gas, so the refusal came from the EVM rather than from our script - and that is also the "
          "reason the interface pre-checks before sending.")

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 5: three real findings and the boundary of the claim",
              "A report that is entirely green is not credible - these are the honest limits", 5, page)
    body = [["T02b", "createEvent is permissionless: any address can create an event",
             "spec deviation", "recommend approval or staking"],
            ["E07", "getMaxResalePrice reverts once the event has started (unsigned underflow)",
             "contract defect", "check the timestamp first"],
            ["-", "After regenerating accounts, network.json kept stale addresses",
             "deployment defect", "fixed: addresses derive from the keys"]]
    table(slide, MARGIN, 3.2, 30.6, ["Id", "Finding", "Nature", "Handling"], body,
          [1.4, 14.0, 4.4, 10.8], font_size=8.5, row_h=1.3, center_cols=(0, 2))
    text(slide, MARGIN, 10.6, 14.6, 0.8, "What the chain does not fix", size=10, bold=True,
         color=RED)
    text(slide, MARGIN, 11.4, 14.6, 4.6,
         ["-  one person, many wallets: limit is per address",
          "-  cash top-ups and whole-wallet transfers",
          "-  server-side signing is not user signing",
          "-  one Clique signer is not a trust model"],
         size=9, color=DARK, line_spacing=1.45)
    text(slide, 17.6, 10.6, 14.2, 0.8, "What it does fix", size=10, bold=True, color=GREEN)
    text(slide, 17.6, 11.4, 14.2, 4.6,
         ["-  ticket ownership is public state",
          "-  the five rules cannot be bypassed",
          "-  every refusal is an auditable receipt",
          "   (24 of them, with gas attached)"],
         size=9, color=DARK, line_spacing=1.45)
    notes(slide,
          "Part 5, about two and a half minutes. Present the three findings as work, not problems: two are "
          "contract-level (a deviation and a defect we found by attacking our own system) and one was a "
          "deployment bug we fixed. Then split the board: on the right what the chain genuinely guarantees, "
          "on the left what it cannot. Say explicitly that we are not claiming scalping is eliminated.")

    # ---------------------------------------------------------------- conclusion
    slide = blank(prs)
    next_page()
    title_bar(slide, "Conclusion: what each part proved",
              "Four sentences, in the order the audience just heard them", page=page)
    conclusions = [
        ("The rules are enforced", "Over-buying, over-pricing, direct transfer and duplicate check-in "
                                   "are all rejected - website bypassed", GREEN),
        ("The rules are verifiable", "Every claim maps to a transaction hash, plus a state read-back",
         BLUE),
        ("The cost is real", "Rejected writes cost gas too, so pre-checks are a requirement", AMBER),
        ("The boundary is clear", "The chain governs tickets; people need identity and law", NAVY),
    ]
    for i, (head, body_txt, color) in enumerate(conclusions):
        y = 3.2 + i * 3.2
        rect(slide, MARGIN, y, 0.15, 2.7, color, shape=MSO_SHAPE.RECTANGLE)
        text(slide, MARGIN + 0.55, y + 0.2, 8.2, 1.1, head, size=13, bold=True, color=color)
        text(slide, 9.9, y + 0.2, 21.2, 2.3, body_txt, size=10, color=DARK, line_spacing=1.4)
    notes(slide,
          "Whoever closes the five parts, about one minute. Four sentences, no new material: enforced, "
          "verifiable, costly, bounded. Then hand over to the live demo.")

    # ---------------------------------------------------------------- demo
    slide = blank(prs)
    next_page()
    title_bar(slide, "Live demo: seven actions, in this order",
              "Success paths first - the failure paths need an unused ticket", page=page)
    demo_steps = [("1", "Organizer creates an event", "createEvent", "Part 2"),
                  ("2", "buyerA buys ticket #1", "purchaseTickets", "Part 2"),
                  ("3", "buyerA lists at 120%", "listForResale", "Part 3"),
                  ("4", "buyerB buys it, ownerOf changes", "buyResale", "Part 3"),
                  ("5", "Over-priced listing and direct transfer rejected", "revert, status=0", "Part 3"),
                  ("6", "buyerB shows the QR, verifier checks in", "checkIn", "Part 4"),
                  ("7", "Second check-in rejected", "revert", "Parts 3 and 4")]
    for i, (num, action, fn, owner) in enumerate(demo_steps):
        y = 2.95 + i * 1.95
        rect(slide, MARGIN, y + 0.15, 1.1, 1.1, BLUE, shape=MSO_SHAPE.OVAL)
        text(slide, MARGIN, y + 0.32, 1.1, 0.8, num, size=12, bold=True, color=WHITE,
             align=PP_ALIGN.CENTER)
        text(slide, MARGIN + 1.5, y + 0.2, 13.0, 1.1, action, size=10, color=DARK)
        text(slide, 16.6, y + 0.2, 8.0, 1.1, fn, size=9, color=GREY)
        text(slide, 24.8, y + 0.2, 6.4, 1.1, owner, size=8.5, color=RGBColor(0x90, 0xA4, 0xAE))
    text(slide, MARGIN, 16.7, 30.6, 1.4,
         "Fallback if the node misbehaves: results/screenshots/ and results/demo_report.md - "
         "every conclusion has offline evidence", size=10.5, color=GREY)
    notes(slide,
          "Demo, about three minutes, driver = whichever member owns the step. Run the success path first "
          "(1-4), then the two refusals (5), then check-in (6) and the duplicate (7). Punchline at step 5: "
          "the transaction is mined and it is status=0, so the refusal came from the contract. If the node "
          "dies, switch to the screenshots and demo_report.md and keep the same narrative.")

    # ---------------------------------------------------------------- Q&A
    slide = blank(prs)
    next_page()
    rect(slide, 0, 0, 33.87, 19.05, NAVY, shape=MSO_SHAPE.RECTANGLE)
    text(slide, 3.0, 4.4, 27.9, 2.2, "Q & A", size=44, bold=True, color=WHITE)
    text(slide, 3.0, 7.1, 27.9, 1.0, "Thank you - the five parts are ready to take questions",
         size=16, color=RGBColor(0x90, 0xCA, 0xF9))
    facts = [f"Contract {net['contract_address'][:12]}...  -  deploy gas "
             f"{env['contract']['deploy_gas_used']:,}",
             f"{s['total_cases']} cases / {s['pass_rate']}% pass rate / "
             f"{s['on_chain_failed_txs']} real status=0 transactions",
             "Every number traceable to a transaction hash in results/test_evidence.json"]
    for i, fact in enumerate(facts):
        text(slide, 3.0, 9.9 + i * 1.35, 27.9, 1.0, "- " + fact, size=12,
             color=RGBColor(0xCF, 0xD8, 0xDC))
    text(slide, 3.0, 14.8, 27.9, 1.0,
         "Part 1 chain  -  Part 2 issuance  -  Part 3 resale  -  Part 4 interface  -  Part 5 evidence",
         size=10.5, color=RGBColor(0x90, 0xCA, 0xF9))
    notes(slide,
          "Closing slide for the whole group. Keep the five-part order in the footer so any question can be "
          "routed to the right member immediately. If a question is about a number, open "
          "results/test_evidence.json or results/test_results.csv on the projector.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    print(f"[pptx] written to {OUT}")
    print(f"[pptx] {len(prs.slides._sldIdLst)} slides")
    return OUT


if __name__ == "__main__":
    build()
