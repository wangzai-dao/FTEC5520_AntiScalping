#!/usr/bin/env python
"""Part 5: build the defence deck (presentation/final_presentation.pptx).

The deck follows the speaking order of the five members (Part 1 -> Part 5).
Typography is deliberately large - body 12.5-15 pt, tables 12-13 pt, titles 24-30
pt - and the layouts fill the 16:9 canvas, so the slides read from the back of a
lecture room. There are no handover strips; the part badge and the divider pages
carry the structure. Every slide has speaker notes with a short script.

All numbers come from results/test_evidence.json, results/chart_data.json,
config/network.json, results/charts/ and results/screenshots/ - the same run as
the Final Report.

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
MARGIN = 1.7

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


def text(slide, x, y, w, h, content, size=14, bold=False, color=DARK, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, line_spacing=1.15, italic=False):
    box = slide.shapes.add_textbox(Cm(x), Cm(y), Cm(w), Cm(h))
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
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


def title_bar(slide, title, kicker=None, part_idx=None, page=None):
    rect(slide, 0, 0, 33.87, 0.24, NAVY, shape=MSO_SHAPE.RECTANGLE)
    size = 30 if len(title) <= 42 else (27 if len(title) <= 54 else 24)
    text(slide, MARGIN, 0.6, 27.4, 1.55, title, size=size, bold=True, color=NAVY)
    if kicker:
        text(slide, MARGIN, 2.2, 30.4, 0.9, kicker, size=14, color=GREY)
    if part_idx:
        num, _t, short, color, _d = PARTS[part_idx - 1]
        text(slide, 22.8, 0.42, 9.4, 0.8, f"Part {num} of 5  -  {short}", size=11.5, bold=True,
             color=color, align=PP_ALIGN.RIGHT)
    if page:
        text(slide, 31.4, 18.25, 1.9, 0.7, str(page), size=11, color=GREY, align=PP_ALIGN.RIGHT)


def table(slide, x, y, w, headers, rows, col_ratios, font_size=12.5, header_size=12.5,
          row_h=1.8, header_fill=NAVY, center_cols=()):
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
        cell.margin_left = cell.margin_right = Cm(0.18)
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
        for j, value in enumerate(row):
            cell = tbl.cell(i, j)
            cell.text = ""
            cell.fill.solid()
            cell.fill.fore_color.rgb = LIGHT if i % 2 == 0 else WHITE
            cell.margin_left = cell.margin_right = Cm(0.18)
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
             size=11, color=RED)
        return
    if w:
        slide.shapes.add_picture(str(path), Cm(x), Cm(y), width=Cm(w))
    else:
        slide.shapes.add_picture(str(path), Cm(x), Cm(y), height=Cm(h))


def kpi(slide, x, y, w, h, value, label, color=BLUE, value_size=32, label_size=11.5):
    rect(slide, x, y, w, h, LIGHT)
    rect(slide, x, y, 0.18, h, color, shape=MSO_SHAPE.RECTANGLE)
    text(slide, x + 0.5, y + 0.3, w - 0.9, 1.7, value, size=value_size, bold=True, color=color)
    text(slide, x + 0.5, y + h - 1.45, w - 0.9, 1.2, label, size=label_size, color=GREY,
         line_spacing=1.1)


def band(slide, y, h, color, message, size=14):
    rect(slide, MARGIN, y, 30.5, h, LIGHT)
    rect(slide, MARGIN, y, 0.18, h, color, shape=MSO_SHAPE.RECTANGLE)
    text(slide, MARGIN + 0.55, y, 29.3, h, message, size=size, bold=True, color=NAVY,
         anchor=MSO_ANCHOR.MIDDLE)


def section_slide(prs, idx: int) -> None:
    """Divider for one part: the number is the headline, the topic sits under it."""
    num, title, _short, color, delivers = PARTS[idx - 1]
    slide = blank(prs)
    rect(slide, 0, 0, 13.6, 19.05, color, shape=MSO_SHAPE.RECTANGLE)
    text(slide, 1.6, 1.7, 10.4, 0.9, "Presentation outline", size=13, bold=True,
         color=RGBColor(0xCF, 0xD8, 0xDC))
    text(slide, 1.3, 2.7, 11.6, 3.6, f"Part {num}", size=58, bold=True, color=WHITE)
    text(slide, 1.6, 8.2, 10.6, 3.9, title, size=14, color=RGBColor(0xE3, 0xEA, 0xEE),
         line_spacing=1.25)
    text(slide, 1.6, 12.5, 10.6, 0.7, "Where this part sits" if num != "5"
         else "Where this part sits - all three layers", size=10.5, bold=True,
         color=RGBColor(0xCF, 0xD8, 0xDC))
    owned = {"1": {"Interface"}, "2": {"Contract"}, "3": {"Contract"},
             "4": {"Presentation"}, "5": {"Presentation", "Interface", "Contract"}}[num]
    for i, layer in enumerate(["Presentation", "Interface", "Contract"]):
        y = 13.25 + i * 1.4
        active = layer in owned
        chip = rect(slide, 1.6, y, 10.4, 1.25, WHITE if active else color,
                    shape=MSO_SHAPE.ROUNDED_RECTANGLE, adj=0.18)
        if not active:
            chip.fill.background()
            chip.line.color.rgb = RGBColor(0xCF, 0xD8, 0xDC)
            chip.line.width = Pt(0.75)
        text(slide, 2.0, y, 9.8, 1.25,
             layer + ("  -  this part" if active and num != "5" else ""),
             size=11.5, bold=active, color=color if active else RGBColor(0xCF, 0xD8, 0xDC),
             anchor=MSO_ANCHOR.MIDDLE)

    text(slide, 15.4, 2.3, 17.2, 0.8, "What this part delivers", size=13, bold=True, color=color)
    text(slide, 15.4, 3.2, 17.0, 3.8, delivers, size=21, color=DARK, line_spacing=1.2)
    text(slide, 15.4, 7.7, 17.2, 0.8, "The five parts, in order", size=13, bold=True, color=GREY)
    for i, (n2, _t2, short2, *_rest) in enumerate(PARTS, start=1):
        y = 8.7 + (i - 1) * 2.0
        active = i == idx
        rect(slide, 15.4, y, 17.4, 1.75, color if active else LIGHT,
             shape=MSO_SHAPE.ROUNDED_RECTANGLE, adj=0.2)
        text(slide, 15.8, y, 3.2, 1.75, f"Part {n2}", size=12.5, bold=True,
             color=WHITE if active else GREY, anchor=MSO_ANCHOR.MIDDLE)
        text(slide, 19.1, y, 13.4, 1.75, short2, size=12.5,
             bold=active, color=WHITE if active else DARK, anchor=MSO_ANCHOR.MIDDLE)
    notes(slide,
          f"Part {num} begins. Opening line: 'Part {num}: {title}.' "
          f"What this part proves: {delivers}. Ten seconds on this slide - it exists only to make the "
          f"change of speaker visible.")


# ----------------------------------------------------------------------
def build() -> Path:
    d = load()
    s, env, net, rows = d["s"], d["env"], d["net"], d["rows"]
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

    # ---------------------------------------------------------------- cover
    slide = blank(prs)
    next_page()
    rect(slide, 0, 0, 33.87, 19.05, NAVY, shape=MSO_SHAPE.RECTANGLE)
    rect(slide, 0, 14.15, 33.87, 0.14, BLUE, shape=MSO_SHAPE.RECTANGLE)
    text(slide, 2.6, 2.1, 28, 1, "FTEC5520 Applied Blockchain and Cryptocurrencies", size=15,
         color=RGBColor(0xB0, 0xBE, 0xC5))
    text(slide, 2.6, 3.2, 30.6, 2.2, "Anti-Scalping Concert Ticketing System", size=37, bold=True,
         color=WHITE)
    text(slide, 2.6, 5.7, 30, 1.1, "Five parts, five speakers, one running private chain", size=18,
         color=RGBColor(0xCF, 0xD8, 0xDC))
    text(slide, 2.6, 7.0, 30, 1.0,
         "Geth Clique chain  -  ERC-721 tickets  -  price-capped resale  -  on-chain check-in",
         size=13.5, color=RGBColor(0x90, 0xCA, 0xF9))
    for i, (num, _title, short, _color, _delivers) in enumerate(PARTS):
        x = 2.6 + i * 5.9
        rect(slide, x, 8.5, 5.5, 4.2, RGBColor(0x2B, 0x48, 0x78))
        text(slide, x + 0.4, 8.8, 4.8, 0.9, f"Part {num}", size=15, bold=True, color=WHITE)
        text(slide, x + 0.4, 9.9, 4.8, 2.6, short, size=11,
             color=RGBColor(0xB0, 0xBE, 0xC5), line_spacing=1.15)
    text(slide, 2.6, 15.0, 30, 1.0,
         f"Group 18 (five members)  -  contract "
         f"{net['contract_address'][:10]}...{net['contract_address'][-4:]}  -  "
         f"{s['total_cases']} test cases, pass rate {s['pass_rate']}%",
         size=13.5, color=RGBColor(0xCF, 0xD8, 0xDC))
    text(slide, 2.6, 16.2, 30, 1.0,
         "All figures in this deck come from one continuous run on the chain",
         size=12, color=RGBColor(0x90, 0xCA, 0xF9), italic=True)
    notes(slide,
          "Opening speaker. One sentence on the project: we moved five ticketing rules from a database "
          "into a smart contract, then tried to break them. Announce the format: five parts, each speaker "
          "covers their own work. About 20 minutes, demo at the end.")

    # ---------------------------------------------------------------- agenda
    slide = blank(prs)
    next_page()
    title_bar(slide, "Agenda: five parts, in the order we built them",
              "Each part ends where the next one begins", page=page)
    body = [[num, title, delivers] for num, title, _s, _c, delivers in PARTS]
    table(slide, MARGIN, 3.0, 30.5, ["Part", "What the part covers", "Delivers to the next part"], body,
          [1.8, 13.8, 14.9], font_size=12.5, row_h=2.0, center_cols=(0,))
    text(slide, MARGIN, 15.6, 30.5, 2.4,
         ["Then: one live end-to-end demo (seven actions) and Q & A.",
          "Every number can be traced to a transaction hash in results/test_evidence.json."],
         size=13.5, color=GREY, line_spacing=1.35)
    notes(slide,
          "Walk the table left to right. Two things to stress: the parts follow the real development "
          "order, and every part ends with something handed over. Roughly four minutes per part.")

    # ---------------------------------------------------------------- problem
    slide = blank(prs)
    next_page()
    title_bar(slide, "The problem: scalping is three different attacks",
              "One shared statement before the five parts", page=page)
    cards = [
        ("1. Bulk buying", "Scripts and many wallets\nsweep the stock at on-sale time.",
         "Countermeasure: per-wallet counter", RED),
        ("2. Markup resale", "Listed at 3-5x; platforms\nonly suggest a cap.",
         "Countermeasure: dynamic cap + transfer override", AMBER),
        ("3. Duplicate entry", "A QR screenshot can be\nforwarded and reused.",
         "Countermeasure: one-time check-in + signed QR", BLUE),
    ]
    for i, (head, body_txt, fix, color) in enumerate(cards):
        x = MARGIN + i * 10.5
        rect(slide, x, 3.0, 9.9, 10.4, LIGHT)
        rect(slide, x, 3.0, 9.9, 0.24, color, shape=MSO_SHAPE.RECTANGLE)
        text(slide, x + 0.55, 3.5, 9.0, 1.1, head, size=22, bold=True, color=color)
        text(slide, x + 0.55, 5.0, 9.0, 3.6, body_txt.split("\n"), size=17, color=DARK,
             line_spacing=1.3)
        rect(slide, x + 0.55, 8.9, 8.8, 0.03, RGBColor(0xCF, 0xD8, 0xDC), shape=MSO_SHAPE.RECTANGLE)
        text(slide, x + 0.55, 9.3, 9.0, 3.6, fix, size=15, bold=True, color=NAVY, line_spacing=1.25)
    band(slide, 14.1, 2.5, GREEN,
         "A rule in an operator's database is a policy. A require in the EVM is a fact.", size=17)
    text(slide, MARGIN, 17.1, 30.5, 1.4,
         "So the goal is not a nicer website: it is a system where 'skip the website' cannot work.",
         size=15, color=GREY, align=PP_ALIGN.CENTER)
    notes(slide,
          "Shared context, one minute. The three columns are the running theme: Part 2 attacks column 1, "
          "Part 3 attacks columns 2 and 3, Part 4 builds the credential, Part 5 measures the refusals. "
          "Close on the band - it is the sentence the deck proves.")

    # ================================================================ PART 1
    section_slide(prs, 1)
    next_page()

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 1: the chain and the deployment",
              "Nothing here is real until it is mined", 1, page)
    kpi(slide, MARGIN, 3.0, 7.3, 4.0, str(env["chain"]["chain_id"]),
        "chainId - Clique PoA", BLUE, 30, 11)
    kpi(slide, 9.2, 3.0, 7.3, 4.0, f"{env['contract']['deploy_gas_used']:,}",
        "gas for the deployment", TEAL, 30, 11)
    kpi(slide, 16.7, 3.0, 7.3, 4.0, f"{env['contract']['deployed_bytes']:,}",
        "bytes of runtime code", NAVY, 30, 11)
    kpi(slide, 24.2, 3.0, 7.9, 4.0, str(env["contract"]["abi_items"]),
        "ABI entries to Part 4", GREEN, 30, 11)
    text(slide, MARGIN, 7.5, 15.2, 0.8, "What this part built", size=15, bold=True, color=BLUE)
    bullets = ["Genesis with seven funded accounts",
               "start_node.sh / stop_node.sh",
               "compile.py: solc 0.8.20, paris",
               "deploy.py: writes config/network.json"]
    for i, item in enumerate(bullets):
        text(slide, MARGIN, 8.5 + i * 2.45, 15.4, 2.2, "-  " + item, size=15, color=DARK,
             line_spacing=1.2)
    text(slide, 17.6, 7.5, 14.4, 0.8, "What the chain provides", size=15, bold=True, color=BLUE)
    text(slide, 17.6, 8.5, 14.2, 9.4,
         ["No business logic - it executes.",
          "",
          "-  a fixed address during the demo",
          "-  a receipt for every tx, failures too",
          "-  blocks fast enough to show live state",
          "",
          "So every later claim ends with a tx hash."],
         size=15, color=DARK, line_spacing=1.45)
    notes(slide,
          "Part 1, two minutes. Geth 1.13.15, Clique, chainId 1337, two-second blocks, seven funded "
          "accounts. Then the four numbers: 3.3 million gas to deploy, 14,339 bytes of runtime code, "
          "67 ABI entries. The point: what the next parts receive is an address and an ABI.")

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 1: one interface, one return shape",
              "No page builds a raw transaction", 1, page)
    text(slide, MARGIN, 3.0, 15.4, 0.8, "Six functions every part calls", size=14, bold=True,
         color=BLUE)
    body = [["get_ticket_owner", "read", "current owner"],
            ["buy_ticket", "write", "purchase and mint"],
            ["list_ticket", "write", "list for resale"],
            ["buy_resale", "write", "buy a listing"],
            ["check_in", "write", "on-chain check-in"],
            ["get_receipt", "read", "mined? what gas?"]]
    table(slide, MARGIN, 3.9, 15.4, ["Function", "", "What it does"], body,
          [6.0, 1.8, 7.0], font_size=13, row_h=2.0, center_cols=(1,))
    text(slide, 17.9, 3.0, 14.2, 0.8, "Every write returns one struct", size=14, bold=True,
         color=BLUE)
    rect(slide, 17.9, 3.9, 14.2, 3.6, LIGHT)
    text(slide, 18.3, 4.15, 13.4, 3.1,
         ["TxResult( ok, tx_hash,",
          "          block_number, gas_used,",
          "          status, error )"],
         size=14, color=NAVY, line_spacing=1.4)
    text(slide, 17.9, 8.2, 14.2, 9.4,
         ["Why it matters:",
          "",
          "-  every later slide quotes the same fields",
          "-  estimate_gas runs first, so a doomed",
          "   call costs no gas",
          "-  failures are data, not silence"],
         size=14, color=DARK, line_spacing=1.5)
    notes(slide,
          "Part 1, two minutes. The page layer may only call these six, which is why the interface can be "
          "tested without Streamlit. Then the TxResult struct: one shape for every write means the same "
          "evidence on every later slide.")

    # ================================================================ PART 2
    section_slide(prs, 2)
    next_page()

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 2: who may buy, how many, at what price",
              "Tickets mint inside the purchase", 2, page)
    body = [["createEvent", "anyone; caller becomes organizer", "T01"],
            ["setWhitelist", "organizer only, per event", "T03 / T04"],
            ["purchaseTickets", "stock, limit, whitelist, payment", "T05 / T06"],
            ["canPurchase", "read-only pre-check", "used by Part 4"],
            ["withdrawProceeds", "pull payment by organizer", "T01"]]
    table(slide, MARGIN, 3.0, 18.6, ["Function", "Rule in the contract", "Test"], body,
          [4.4, 10.4, 3.8], font_size=12, row_h=1.85, center_cols=(2,))
    text(slide, 21.0, 2.95, 11.2, 0.8, "Measured in this run", size=14, bold=True, color=TEAL)
    ev = [["T01", "event created", gas("T01")],
          ["T05a", "2 tickets = the limit", gas("T05a")],
          ["T05b", "3rd ticket rejected", gas("T05b")],
          ["T06a", "last ticket sold", gas("T06a")],
          ["T06b", "sold out, rejected", gas("T06b")]]
    table(slide, 21.0, 3.85, 11.2, ["Case", "What it proves", "Gas"], ev,
          [1.8, 6.6, 2.8], font_size=11.5, row_h=1.7, center_cols=(0, 2))
    text(slide, MARGIN, 14.3, 30.5, 2.8,
         ["T02b is a deliberate deviation: createEvent has no access control, so anyone can create an event.",
          "canPurchase is the read-only pre-check the page calls; T04, T05b and T06b assert the same rules on chain."],
         size=12.5, color=GREY, line_spacing=1.35)
    notes(slide,
          "Part 2, two and a half minutes. Two design choices to name: tickets mint inside the purchase, so "
          "ids map to sale order; revenue is pull-based, so a recipient that rejects ETH cannot block a "
          "sale. Then the caveat on T02b - raising it yourself is stronger than being asked.")

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 2: the purchase path, and where it ends",
              "The handover to Part 3 is a data structure", 2, page)
    steps = [("1", "Read the event", "price, supply, limit, presale flag"),
             ("2", "Pre-check", "canPurchase returns the reason"),
             ("3", "Charge exactly", "msg.value = price x quantity"),
             ("4", "Book the money", "credit pendingProceeds"),
             ("5", "Mint", "one ERC-721 per ticket")]
    for i, (num, head, detail) in enumerate(steps):
        y = 3.0 + i * 2.6
        rect(slide, MARGIN, y, 1.5, 2.0, TEAL, shape=MSO_SHAPE.OVAL)
        text(slide, MARGIN, y + 0.42, 1.5, 1.1, num, size=15, bold=True, color=WHITE,
             align=PP_ALIGN.CENTER)
        text(slide, MARGIN + 2.1, y + 0.05, 7.2, 0.9, head, size=15, bold=True, color=NAVY)
        text(slide, MARGIN + 2.1, y + 1.0, 13.0, 0.9, detail, size=12.5, color=DARK)
    rect(slide, 17.6, 3.0, 14.6, 13.4, LIGHT)
    text(slide, 18.1, 3.3, 13.6, 0.9, "What Part 3 inherits", size=14, bold=True, color=TEAL)
    text(slide, 18.1, 4.3, 13.6, 11.4,
         ["ticketToEvent[tokenId]",
          "  -  the event, so the cap follows its price",
          "",
          "tickets[tokenId] =",
          "  {isListed, listingPrice,",
          "   resaleCount, used}",
          "  -  four fields resale and check-in mutate",
          "",
          "require order:",
          "  stock -> limit -> whitelist -> payment"],
         size=12.5, color=DARK, line_spacing=1.3)
    notes(slide,
          "Part 2, two minutes. Five steps, one sentence each. The right-hand box is the real handover: "
          "Part 3 needs no new model, it mutates four fields that already exist.")

    # ================================================================ PART 3
    section_slide(prs, 3)
    next_page()

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 3: the price cap follows the clock",
              "Two regimes, one boundary, a counter that cannot reset", 3, page)
    body = [["More than 7 days out", "120% of the original price", "T08"],
            ["7 days or less", "100% of the original price", "T09a-T09c"],
            ["Exactly 7 days", "cap switches to 100%", "T09d"],
            ["Resale #1 to #3", "allowed, counter increments", "T07 / T10a"],
            ["A fourth listing", "rejected: max resale limit", "T10b"]]
    table(slide, MARGIN, 3.0, 17.4, ["Condition", "Enforced effect", "Test"], body,
          [6.2, 8.2, 3.6], font_size=12, row_h=2.05, center_cols=(2,))
    text(slide, 19.4, 2.95, 12.8, 0.8, "Why it must be time-based", size=14, bold=True, color=NAVY)
    text(slide, 19.4, 3.85, 12.8, 4.6,
         ["A flat 120% cap invites arbitrage:",
          "wait for the last week, when demand",
          "peaks, and still charge a premium.",
          "",
          "block.timestamp closes that window."],
         size=14, color=DARK, line_spacing=1.4)
    rect(slide, 19.4, 8.8, 12.8, 6.6, LIGHT)
    text(slide, 19.8, 9.05, 12.0, 6.0,
         ["Measured:",
          f"  T09b  list 0.51, cap 0.50",
          f"           -> rejected ({gas('T09b')})",
          f"  T09c  list exactly 0.50",
          f"           -> accepted ({gas('T09c')})",
          f"  T10b  4th listing at 3",
          f"           -> rejected ({gas('T10b')})"],
         size=12.5, color=DARK, line_spacing=1.55)
    notes(slide,
          "Part 3, two and a half minutes. Two regimes and the exact boundary: T09d proves the switch by "
          "listing 1.00 and 1.01 ETH against a 1.00 cap. Then the counter: three resales, the fourth "
          "listing reverts.")

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 3: closing the escape hatch, one-time entry",
              "A cap inside buyResale is useless if the token can move", 3, page)
    text(slide, MARGIN, 3.0, 15.4, 0.9, "The escape hatch we closed", size=15, bold=True,
         color=RED)
    text(slide, MARGIN, 3.95, 15.4, 4.6,
         ["ERC-721 ships with transferFrom and",
          "safeTransferFrom. If they stay callable,",
          "the owner moves the token and every",
          "resale rule is skipped.",
          "Both entry points are overridden to revert."],
         size=14, color=DARK, line_spacing=1.35)
    body = [["T11a", "transferFrom", "mined, status=0", gas("T11a")],
            ["T11b", "safeTransferFrom", "mined, status=0", gas("T11b")],
            ["B02", "same, raw Web3.py", "mined, status=0", gas("B02")]]
    table(slide, MARGIN, 8.7, 15.4, ["Case", "Attempt", "Result", "Gas"], body,
          [1.6, 6.2, 4.4, 2.8], font_size=12.5, row_h=1.65, center_cols=(0, 2, 3))
    text(slide, MARGIN, 15.6, 15.4, 2.2,
         ["Gas is still charged: the transaction exists,",
          "the state did not change."],
         size=13, color=GREY, line_spacing=1.35)
    text(slide, 18.0, 3.0, 14.2, 0.9, "Check-in: one ticket, one entry", size=15, bold=True,
         color=NAVY)
    body2 = [["T15b", "first check-in", "used = true"],
             ["T16", "second check-in", "already used"],
             ["T17", "no verifier role", "not authorised"],
             ["E09", "check-in while listed", "listing cleared"],
             ["T07b", "5% fee on 1.2 ETH", "0.06 ETH"]]
    table(slide, 18.0, 3.95, 14.2, ["Case", "Action", "Observed"], body2,
          [2.2, 6.8, 5.2], font_size=11.5, row_h=1.7, center_cols=(0,))
    notes(slide,
          "Part 3, three minutes - the heart of the story. Start from the escape hatch: ERC-721 gives "
          "everyone a transfer function, so a cap inside buyResale alone would be theatre. Then the three "
          "rows: all mined, all status=0, all paid gas. Finish with check-in.")

    # ================================================================ PART 4
    section_slide(prs, 4)
    next_page()

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 4: six pages that only display the chain",
              "None of them caches a business decision", 4, page)
    text(slide, MARGIN, 2.95, 18.2, 0.7,
         "Buy Tickets: pre-check, transaction, ownerOf read-back", size=11.5, bold=True, color=BLUE)
    picture(slide, SHOTS / "03_buy_tickets.png", MARGIN, 3.65, w=18.2)
    text(slide, 20.8, 2.9, 12.0, 0.8, "What each page shows", size=14, bold=True, color=BLUE)
    text(slide, 20.8, 3.8, 11.9, 9.0,
         ["Overview - chainId, block,",
          "contract, balances, transfers.",
          "",
          "Events - create an event, toggle",
          "sale, batch whitelist, settle.",
          "",
          "Resale - the live cap, list, buy,",
          "cancel; over-price fails on purpose."],
         size=12, color=DARK, line_spacing=1.3)
    for i, (fname, label) in enumerate([("01_overview.png", "Overview"),
                                        ("02_events.png", "Events"),
                                        ("05_resale_market.png", "Resale")]):
        x = MARGIN + i * 10.4
        picture(slide, SHOTS / fname, x, 13.2, w=9.8)
        text(slide, x, 17.9, 9.8, 0.6, label, size=10.5, bold=True, color=GREY)
    notes(slide,
          "Part 4, two minutes. Start with the hero screenshot: the buy page is where the pre-check and "
          "the transaction appear together. Then the three small ones, one sentence each.")

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 4: the QR is a signed claim, not a token id",
              "A forwarded screenshot, an old owner, a repeat entry: all fail", 4, page)
    picture(slide, SHOTS / "04_my_tickets.png", MARGIN, 2.95, h=11.4)
    text(slide, 9.4, 2.95, 10.6, 0.8, "What the QR carries", size=14, bold=True, color=BLUE)
    rect(slide, 9.4, 3.85, 10.6, 2.5, LIGHT)
    text(slide, 9.65, 4.05, 10.1, 2.2,
         ["{ v, token_id, holder, nonce,",
          "  issued_at, expires_at, sig }"],
         size=12.5, color=NAVY, line_spacing=1.35)
    text(slide, 9.4, 6.95, 10.6, 0.8, "Five checks, in this order", size=14, bold=True, color=BLUE)
    checks = [["1", "version", "T13"], ["2", "signer == holder", "T14a"],
              ["3", "not expired (180 s)", "T14b"], ["4", "holder == ownerOf", "T14c"],
              ["5", "used is still false", "T15b"]]
    table(slide, 9.4, 7.85, 10.6, ["", "Check", "Case"], checks, [0.9, 6.9, 2.8],
          font_size=12.5, row_h=1.65, center_cols=(0, 2))
    picture(slide, SHOTS / "06_staff_checkin.png", 20.8, 2.95, w=13.0)
    text(slide, 20.8, 10.2, 13.0, 7.4,
         ["Three attacks, three checks:",
          "",
          "-  forwarded screenshot -> expiry",
          "-  previous owner -> ownerOf",
          "-  second entry -> used",
          "",
          "Off-chain proves the holder;",
          "the chain does the check-in."],
         size=12, color=DARK, line_spacing=1.35)
    notes(slide,
          "Part 4, two and a half minutes. Read the payload once, then map each check to the attack it "
          "kills. Close on the boundary: off-chain proves possession, on-chain performs the check-in.")

    # ================================================================ PART 5
    section_slide(prs, 5)
    next_page()

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 5: 48 cases, two kinds of evidence",
              "Every negative case is forced on chain", 5, page)
    kpi(slide, MARGIN, 3.0, 7.3, 4.0, str(s["total_cases"]), "cases: T01-T18 + 16", BLUE, 30, 11)
    kpi(slide, 9.2, 3.0, 7.3, 4.0, f"{s['pass_rate']}%", "46 PASS / 0 FAIL", GREEN, 30, 11)
    kpi(slide, 16.7, 3.0, 7.3, 4.0, str(s["on_chain_failed_txs"]), "rejected but mined", RED, 30, 11)
    kpi(slide, 24.2, 3.0, 7.9, 4.0, f"{s['on_chain_failed_gas_total']:,}",
        "gas burned by refusals", AMBER, 30, 11)
    picture(slide, CHARTS / "01_test_results_by_module.png", MARGIN, 7.6, w=19.4)
    text(slide, 21.9, 7.5, 10.3, 0.8, "Judging rules", size=14, bold=True, color=GREEN)
    text(slide, 21.9, 8.5, 10.3, 9.0,
         ["-  a case expected to fail",
          "   passes only when the",
          "   contract rejects it",
          "-  positive cases also read",
          "   on-chain state",
          "-  each case makes its own event",
          "-  two deviations documented"],
         size=12, color=DARK, line_spacing=1.4)
    notes(slide,
          "Part 5, two and a half minutes. Do not list cases - explain the two decisions that make the "
          "numbers trustworthy: the judging rule for negative cases, and forcing every negative case on "
          "chain so we own a status=0 receipt.")

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 5: what each rule costs",
              "Medians of real receipts, not estimates", 5, page)
    picture(slide, CHARTS / "02_gas_comparison.png", MARGIN, 3.0, w=21.9)
    text(slide, 24.2, 2.95, 8.0, 0.8, "Three takeaways", size=14, bold=True, color=GREEN)
    text(slide, 24.2, 3.9, 8.0, 10.6,
         ["1.  Issuance and purchase",
          "     dominate: 168k / 156k.",
          "",
          "2.  Enforcement is cheap:",
          "     list 80k, check-in 52k.",
          "",
          "3.  A second ticket adds",
          "     only ~56k, so batching",
          "     pays - why scalpers batch."],
         size=12, color=DARK, line_spacing=1.35)
    band(slide, 15.2, 1.9, GREEN,
         "The rules are cheap to enforce; issuing and selling is what costs.", size=14)
    notes(slide,
          "Part 5, one minute. One number per point: 168k, 156k, 52k, and the 56k marginal cost of the "
          "second ticket.")

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 5: what a refused call costs",
              "The same operations, once accepted and once rejected", 5, page)
    picture(slide, CHARTS / "03_coverage_and_failed_tx.png", MARGIN, 3.0, w=22.6)
    text(slide, 25.0, 2.95, 7.2, 0.8, "Why it matters", size=14, bold=True, color=RED)
    text(slide, 25.0, 3.9, 7.2, 10.6,
         ["Left: 19 normal and",
          "27 negative cases -",
          "the value is in the",
          "refusals.",
          "",
          "Right: rejected buy",
          "~41k gas, listing ~34k,",
          "check-in ~24k.",
          "",
          "24 refusals = 782,049 gas.",
          "Hence the pre-check."],
         size=11.5, color=DARK, line_spacing=1.3)
    band(slide, 15.2, 1.9, RED,
         "A refusal is mined, status=0, and still costs gas.", size=14)
    notes(slide,
          "Part 5, one and a half minutes. Left panel: why negative cases outnumber positive ones. Right "
          "panel: a refused call is still mined and still charges gas.")

    slide = blank(prs)
    next_page()
    title_bar(slide, "Part 5: three findings and the honest limits",
              "A report that is entirely green would not be credible", 5, page)
    body = [["T02b", "createEvent is permissionless", "spec deviation", "add approval or a stake"],
            ["E07", "cap view underflows after the event", "contract defect",
             "check the timestamp first"],
            ["D01", "stale addresses in network.json", "deployment defect",
             "fixed: derive from the keys"]]
    table(slide, MARGIN, 3.0, 30.5, ["Id", "Finding", "Nature", "Handling"], body,
          [1.8, 13.0, 5.2, 10.5], font_size=13, row_h=1.9, center_cols=(0, 2))
    text(slide, MARGIN, 11.2, 14.6, 0.8, "What the chain does not fix", size=15, bold=True, color=RED)
    text(slide, MARGIN, 12.2, 14.6, 5.8,
         ["-  one person, many wallets",
          "-  cash top-ups, wallet transfers",
          "-  server-side signing is not user signing",
          "-  one Clique signer is not a trust model"],
         size=13.5, color=DARK, line_spacing=1.4)
    text(slide, 17.8, 11.2, 14.2, 0.8, "What it does fix", size=15, bold=True, color=GREEN)
    text(slide, 17.8, 12.2, 14.2, 5.8,
         ["-  ticket ownership is public state",
          "-  the five rules cannot be bypassed",
          "-  every refusal is an auditable receipt",
          "   (24 of them, with gas)"],
         size=13.5, color=DARK, line_spacing=1.4)
    notes(slide,
          "Part 5, two and a half minutes. Present the three findings as work, not problems. Then split the "
          "board: what the chain guarantees, what it cannot. We are not claiming scalping is eliminated.")

    # ---------------------------------------------------------------- conclusion
    slide = blank(prs)
    next_page()
    title_bar(slide, "Conclusion: what the five parts proved", "Four sentences", page=page)
    conclusions = [
        ("The rules are enforced", "Over-buying, over-pricing, direct transfer and duplicate check-in "
                                   "are all rejected - website bypassed", GREEN),
        ("The rules are verifiable", "Every claim maps to a hash, plus a state read-back", BLUE),
        ("The cost is real", "Rejected writes cost gas, so pre-checks are a requirement", AMBER),
        ("The boundary is clear", "The chain governs tickets; people need identity and law", NAVY),
    ]
    for i, (head, body_txt, color) in enumerate(conclusions):
        y = 3.0 + i * 3.55
        rect(slide, MARGIN, y, 0.2, 2.9, color, shape=MSO_SHAPE.RECTANGLE)
        text(slide, MARGIN + 0.7, y + 0.15, 9.0, 1.3, head, size=19, bold=True, color=color)
        text(slide, 11.4, y + 0.15, 19.8, 2.8, body_txt, size=16, color=DARK, line_spacing=1.3)
    notes(slide,
          "Whoever closes, about one minute. Four sentences: enforced, verifiable, costly, bounded. Then "
          "hand over to the live demo.")

    # ---------------------------------------------------------------- demo
    slide = blank(prs)
    next_page()
    title_bar(slide, "Live demo: seven actions, in this order",
              "Success paths first; failures need an unused ticket", page=page)
    demo_steps = [("1", "Organizer creates an event", "createEvent", "Part 2"),
                  ("2", "buyerA buys ticket #1", "purchaseTickets", "Part 2"),
                  ("3", "buyerA lists at 120%", "listForResale", "Part 3"),
                  ("4", "buyerB buys, ownerOf changes", "buyResale", "Part 3"),
                  ("5", "Over-price and direct transfer rejected", "revert, status=0", "Part 3"),
                  ("6", "QR verified, verifier checks in", "checkIn", "Part 4"),
                  ("7", "Second check-in rejected", "revert", "Parts 3/4")]
    for i, (num, action, fn, owner) in enumerate(demo_steps):
        y = 2.95 + i * 2.1
        rect(slide, MARGIN, y + 0.1, 1.35, 1.35, BLUE, shape=MSO_SHAPE.OVAL)
        text(slide, MARGIN, y + 0.32, 1.35, 0.95, num, size=14, bold=True, color=WHITE,
             align=PP_ALIGN.CENTER)
        text(slide, MARGIN + 1.9, y + 0.2, 14.2, 1.3, action, size=15, color=DARK)
        text(slide, 18.0, y + 0.2, 8.4, 1.3, fn, size=13, color=GREY)
        text(slide, 26.6, y + 0.2, 4.6, 1.3, owner, size=12.5, color=RGBColor(0x90, 0xA4, 0xAE))
    text(slide, MARGIN, 17.2, 30.5, 1.2,
         "Fallback: results/screenshots/ and results/demo_report.md", size=11.5, color=GREY)
    notes(slide,
          "Demo, about three minutes, driver = whoever owns the step. Success path first (1-4), then the "
          "two refusals (5), then check-in (6) and the duplicate (7). Punchline at step 5: mined, "
          "status=0, so the refusal came from the contract.")

    # ---------------------------------------------------------------- Q&A
    slide = blank(prs)
    next_page()
    rect(slide, 0, 0, 33.87, 19.05, NAVY, shape=MSO_SHAPE.RECTANGLE)
    text(slide, 3.0, 4.0, 27.9, 2.4, "Q & A", size=50, bold=True, color=WHITE)
    text(slide, 3.0, 7.2, 27.9, 1.0, "Thank you - the five parts are ready for questions", size=17,
         color=RGBColor(0x90, 0xCA, 0xF9))
    facts = [f"Contract {net['contract_address'][:12]}...  -  deploy gas "
             f"{env['contract']['deploy_gas_used']:,}",
             f"{s['total_cases']} cases / {s['pass_rate']}% pass rate / "
             f"{s['on_chain_failed_txs']} real status=0 transactions",
             "Every number traceable in results/test_evidence.json",
             "Deliverables: report/final_report.docx, demo/demo_steps.md"]
    for i, fact in enumerate(facts):
        text(slide, 3.0, 9.5 + i * 1.5, 27.9, 1.1, "- " + fact, size=13.5,
             color=RGBColor(0xCF, 0xD8, 0xDC))
    text(slide, 3.0, 16.0, 27.9, 1.0,
         "Part 1 chain  -  Part 2 issuance  -  Part 3 resale  -  Part 4 interface  -  Part 5 evidence",
         size=11.5, color=RGBColor(0x90, 0xCA, 0xF9))
    notes(slide,
          "Closing slide for the whole group. The footer keeps the five-part order so any question can be "
          "routed to the right speaker immediately.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    print(f"[pptx] written to {OUT}")
    print(f"[pptx] {len(prs.slides._sldIdLst)} slides")
    return OUT


if __name__ == "__main__":
    build()
