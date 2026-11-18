#!/usr/bin/env python
"""Member 5: build the defence deck (presentation/final_presentation.pptx, 16:9, 15 slides).

All figures come from results/ and config/network.json - the same numbers as the Final Report.
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
OUT = ROOT / "presentation" / "final_presentation.pptx"

FONT = "Arial"
NAVY = RGBColor(0x1F, 0x38, 0x64)
BLUE = RGBColor(0x15, 0x65, 0xC0)
DARK = RGBColor(0x26, 0x32, 0x38)
GREY = RGBColor(0x60, 0x6B, 0x72)
LIGHT = RGBColor(0xF4, 0xF6, 0xF8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x2E, 0x7D, 0x32)
AMBER = RGBColor(0xF9, 0xA8, 0x25)
RED = RGBColor(0xC6, 0x28, 0x28)

W, H = Cm(33.87), Cm(19.05)   # 16:9


def load() -> dict:
    ev = json.loads((RESULTS / "test_evidence.json").read_text("utf-8"))
    demo = json.loads((RESULTS / "tx_evidence.json").read_text("utf-8"))
    net = json.loads((ROOT / "config/network.json").read_text("utf-8"))
    chart = json.loads((RESULTS / "chart_data.json").read_text("utf-8"))
    return {"ev": ev, "demo": demo, "net": net, "chart": chart,
            "s": ev["summary"], "env": ev["environment"]}


def blank(prs: Presentation):
    return prs.slides.add_slide(prs.slide_layouts[6])


def text(slide, x, y, w, h, content, size=16, bold=False, color=DARK, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, line_spacing=1.25):
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
        run.font.color.rgb = color
        run.font.name = FONT
    return box


def rect(slide, x, y, w, h, fill, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE):
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
        shp.adjustments[0] = 0.06
    return shp


def title_bar(slide, title, kicker=None, page=None):
    rect(slide, 0, 0, 33.87, 0.22, NAVY, shape=MSO_SHAPE.RECTANGLE)
    # English titles are longer than the Chinese originals: shrink instead of wrapping into content
    size = 27 if len(title) <= 46 else (23 if len(title) <= 58 else 20)
    text(slide, 1.6, 0.75, 30.4, 1.3, title, size=size, bold=True, color=NAVY)
    if kicker:
        text(slide, 1.6, 2.0, 30, 0.9, kicker, size=13, color=GREY)
    if page:
        text(slide, 30.4, 17.9, 2.4, 0.8, str(page), size=10, color=GREY, align=PP_ALIGN.RIGHT)


def table(slide, x, y, w, headers, rows, col_ratios, font_size=11, header_size=11,
          row_h=0.95, header_fill=NAVY):
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
        cell.margin_top = cell.margin_bottom = Cm(0.08)
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
            cell.margin_top = cell.margin_bottom = Cm(0.06)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            par = cell.text_frame.paragraphs[0]
            par.alignment = PP_ALIGN.CENTER if j else PP_ALIGN.LEFT
            run = par.add_run()
            run.text = str(value)
            run.font.size = Pt(font_size)
            run.font.color.rgb = DARK
            run.font.name = FONT
    return tbl


def picture(slide, path, x, y, w=None, h=None):
    if not Path(path).exists():
        text(slide, x, y, 12, 1, f"[missing {Path(path).name}]", size=12, color=RED)
        return
    if w:
        slide.shapes.add_picture(str(path), Cm(x), Cm(y), width=Cm(w))
    else:
        slide.shapes.add_picture(str(path), Cm(x), Cm(y), height=Cm(h))


def kpi(slide, x, y, w, value, label, color=BLUE):
    rect(slide, x, y, w, 3.5, LIGHT)
    rect(slide, x, y, 0.14, 3.5, color, shape=MSO_SHAPE.RECTANGLE)
    text(slide, x + 0.5, y + 0.55, w - 0.9, 1.6, value, size=30, bold=True, color=color)
    text(slide, x + 0.5, y + 2.25, w - 0.8, 1.3, label, size=10.5, color=GREY, line_spacing=1.15)


# ----------------------------------------------------------------------
def build() -> Path:
    d = load()
    s, env, net = d["s"], d["env"], d["net"]
    g = d["chart"]["gas_median"]
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H

    # 1 title -----------------------------------------------------------
    slide = blank(prs)
    rect(slide, 0, 0, 33.87, 19.05, NAVY, shape=MSO_SHAPE.RECTANGLE)
    rect(slide, 0, 13.4, 33.87, 0.12, BLUE, shape=MSO_SHAPE.RECTANGLE)
    text(slide, 2.6, 3.2, 28, 1, "FTEC5520 Applied Blockchain and Cryptocurrencies", size=14,
         color=RGBColor(0xB0, 0xBE, 0xC5))
    text(slide, 2.6, 4.9, 30, 2.4, "Anti-Scalping Concert Ticketing System", size=40, bold=True,
         color=WHITE)
    text(slide, 2.6, 7.6, 28, 1.2, "Putting ticketing rules on chain with ERC-721, Geth and Web3.py",
         size=17, color=RGBColor(0xCF, 0xD8, 0xDC))
    text(slide, 2.6, 9.6, 28, 1.4,
         "Geth private chain - ERC-721 tickets - price-capped resale - on-chain check-in", size=15,
         color=RGBColor(0x90, 0xCA, 0xF9))
    text(slide, 2.6, 14.3, 28, 1,
         f"Final presentation - Group 18 (five members) - contract "
         f"{net['contract_address'][:10]}...{net['contract_address'][-4:]}",
         size=12, color=RGBColor(0xCF, 0xD8, 0xDC))
    text(slide, 2.6, 15.6, 28, 1,
         f"Test campaign: {s['total_cases']} cases - PASS {s['pass']} - FAIL {s['fail']} - "
         f"pass rate {s['pass_rate']}%",
         size=12, color=RGBColor(0x90, 0xCA, 0xF9))

    # 2 problem ---------------------------------------------------------
    slide = blank(prs)
    title_bar(slide, "Scalping is not one problem, it is three",
              "Each path needs a different technical countermeasure", 2)
    cards = [
        ("1. Bulk buying",
         "Scripts and many accounts sweep the stock\nLimits are per account and accounts are cheap",
         "Countermeasure: per-wallet limit on chain", RED),
        ("2. Markup resale",
         "Listed at 3-5x; platforms only suggest a cap\nOff-platform transfers bypass the market",
         "Countermeasure: dynamic cap + transfer override", AMBER),
        ("3. Duplicate entry",
         "A QR screenshot can be forwarded\nCheck-in state sits in a database",
         "Countermeasure: one-time check-in + signed QR", BLUE),
    ]
    for i, (head, body, fix, color) in enumerate(cards):
        x = 1.7 + i * 10.4
        rect(slide, x, 3.3, 9.6, 9.2, LIGHT)
        rect(slide, x, 3.3, 9.6, 0.2, color, shape=MSO_SHAPE.RECTANGLE)
        text(slide, x + 0.5, 3.8, 8.6, 0.9, head, size=19, bold=True, color=color)
        text(slide, x + 0.5, 5.0, 8.6, 2.8, body.split("\n"), size=12.5, color=DARK, line_spacing=1.5)
        rect(slide, x + 0.5, 8.2, 8.6, 0.03, RGBColor(0xCF, 0xD8, 0xDC), shape=MSO_SHAPE.RECTANGLE)
        text(slide, x + 0.5, 8.6, 8.6, 1.6, fix, size=12.5, bold=True, color=NAVY)
    rect(slide, 1.7, 13.6, 30.4, 3.0, LIGHT)
    text(slide, 2.3, 13.6, 29.2, 3.0,
         "Core claim: a rule in an operator's database is a policy; a require executed by the EVM is a fact.",
         size=15, bold=True, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)

    # 3 architecture ----------------------------------------------------
    slide = blank(prs)
    title_bar(slide, "Three layers, rules only in the bottom one",
              "The pages are a remote control and a display, not a security boundary", 3)
    layers = [
        ("Presentation", "Streamlit, six pages",
         "Overview / Events / Buy / My Tickets / Resale / Check-in", BLUE),
        ("Interface", "Web3.py wrapper",
         "nonce, gas, signing, receipts, exceptions -> TxResult", RGBColor(0x00, 0x89, 0x7B)),
        ("Contract", "ConcertTicket.sol",
         "wallet limit, price cap, resale counter, no direct transfer, one-time check-in", NAVY),
    ]
    for i, (name, sub, detail, color) in enumerate(layers):
        y = 3.4 + i * 3.9
        rect(slide, 1.7, y, 9.6, 3.2, color)
        text(slide, 2.2, y + 0.55, 8.6, 0.9, name, size=15, bold=True, color=WHITE)
        text(slide, 2.2, y + 1.5, 8.6, 1.4, sub, size=13, color=WHITE)
        rect(slide, 11.9, y, 20.2, 3.2, LIGHT)
        text(slide, 12.4, y, 19.2, 3.2, detail, size=13.5, color=DARK, anchor=MSO_ANCHOR.MIDDLE)
    text(slide, 1.7, 15.4, 30.4, 2.2,
         ["The page may pre-check on the client (canPurchase / getMaxResalePrice) to avoid sending a",
          "transaction that must fail - but the answer to 'may I buy' always comes from the contract."],
         size=12.5, color=GREY, line_spacing=1.4)

    # 4 rules -----------------------------------------------------------
    slide = blank(prs)
    title_bar(slide, "Every rule sits in a specific function",
              "Reviewers can check this line by line instead of trusting a claim", 4)
    table(slide, 1.7, 3.3, 30.4,
          ["Business rule", "Contract implementation", "Test"],
          [["Per-wallet limit", "purchasedByWallet + walletLimit", "T05a / T05b"],
           ["Stock cap", "sold + quantity <= maxSupply", "T06a / T06b"],
           ["Presale whitelist", "whitelist[eventId][msg.sender]", "T03 / T04"],
           ["Dynamic price cap", "getMaxResalePrice: >7 days 120%, <=7 days 100%", "T08 / T09a-T09d"],
           ["Resale count <= 3", "ticket.resaleCount < 3", "T10a / T10b"],
           ["No direct transfer", "transferFrom / safeTransferFrom -> revert", "T11a / T11b / B02"],
           ["One-time check-in", "ticket.used = true", "T15b / T16"],
           ["Verifier permission", "verifiers[msg.sender] == true", "T17 / B03"]],
          [3.4, 7.2, 3.0], font_size=12, row_h=1.5)

    # 5 roles and flow --------------------------------------------------
    slide = blank(prs)
    title_bar(slide, "Roles and the path of one purchase",
              "Six test accounts; each permission maps to a require", 5)
    table(slide, 1.7, 3.3, 14.6,
          ["Role", "On-chain rights"],
          [["deployer", "Contract owner: authorise verifiers, withdraw fees"],
           ["organizer", "Create events, toggle sale, whitelist, withdraw"],
           ["buyerA / buyerB", "Purchase, list, buy resale"],
           ["verifier", "checkIn (after authorisation)"],
           ["attacker", "No special rights (negative testing)"]],
          [3.2, 7.4], font_size=11.5, row_h=1.45)
    steps = ["Click buy", "Read concertEvents for the price", "estimate_gas pre-check",
             "Sign locally -> send", "Wait for the receipt", "Read ownerOf back"]
    for i, step in enumerate(steps):
        y = 3.5 + i * 2.15
        rect(slide, 17.2, y, 15.0, 1.6, LIGHT)
        text(slide, 17.7, y, 14.2, 1.6, f"{i + 1}. {step}", size=12.5, color=DARK,
             anchor=MSO_ANCHOR.MIDDLE)
    text(slide, 17.2, 16.4, 15.2, 1.4, "A failed pre-check returns the revert reason: no transaction, no gas",
         size=11.5, color=GREY)

    # 6 method ----------------------------------------------------------
    slide = blank(prs)
    title_bar(slide, "Method: 48 cases, two kinds of evidence",
              "All 18 scenarios of the brief plus adversarial tests", 6)
    kpi(slide, 1.7, 3.4, 7.2, str(s["total_cases"]), "test cases", BLUE)
    kpi(slide, 9.5, 3.4, 7.2, f"{s['pass_rate']}%", "pass rate - 46 PASS / 0 FAIL", GREEN)
    kpi(slide, 17.3, 3.4, 7.2, str(s["on_chain_failed_txs"]), "real status=0 transactions", RED)
    kpi(slide, 25.1, 3.4, 6.9, f"{s['on_chain_failed_gas_total']:,}", "gas burned by rejected calls", AMBER)
    bullets = [
        "State isolation: every case creates its own event, so the suite repeats without redeploying",
        "Judging: a case expected to fail only passes when the contract really rejects it",
        "Dual evidence: the estimate_gas revert plus a forced status=0 receipt",
        "Assertions on state: not just ok=True, but ownerOf / resaleCount / used / platform fee",
        "Adversarial: B01-B04 never touch the website or the backend wrapper",
    ]
    for i, item in enumerate(bullets):
        text(slide, 1.9, 8.4 + i * 1.55, 30, 1.3, "- " + item, size=13, color=DARK)

    # 7 results ---------------------------------------------------------
    slide = blank(prs)
    title_bar(slide, "Results: 46 PASS / 0 FAIL / 2 deviations",
              "A deviation is not a bug: the contract differs from an assumption in the brief (T02b, E07)", 7)
    picture(slide, CHARTS / "01_test_results_by_module.png", 1.6, 3.2, w=19.6)
    table(slide, 22.0, 3.4, 10.4,
          ["Module", "Cases", "PASS"],
          [[m, v["total"], v["PASS"]] for m, v in s["by_module"].items()],
          [6.2, 2.0, 2.0], font_size=10.5, row_h=1.4)
    text(slide, 22.0, 12.0, 10.4, 4.4,
         ["What zero FAIL means:", "every attack that should fail did fail;",
          "every action that should succeed left the expected state on chain."],
         size=11.5, color=GREY, line_spacing=1.5)

    # 8 gas -------------------------------------------------------------
    slide = blank(prs)
    title_bar(slide, "Gas: the cost of writing state", "Medians from real receipts, not estimates", 8)
    picture(slide, CHARTS / "02_gas_comparison.png", 1.5, 3.1, w=20.4)
    facts = [("Create event", f"{g.get('createEvent'):,}"),
             ("Buy 1 ticket", f"{g.get('purchaseTickets(1)'):,}"),
             ("Buy 2 tickets", f"{g.get('purchaseTickets(2)'):,}"),
             ("List for resale", f"{g.get('listForResale'):,}"),
             ("Buy resale", f"{g.get('buyResale'):,}"),
             ("Check in", f"{g.get('checkIn'):,}")]
    for i, (name, value) in enumerate(facts):
        y = 3.4 + i * 2.2
        rect(slide, 22.6, y, 9.6, 1.7, LIGHT)
        text(slide, 23.0, y, 5.6, 1.7, name, size=12, color=DARK, anchor=MSO_ANCHOR.MIDDLE)
        text(slide, 27.6, y, 4.2, 1.7, value, size=13, bold=True, color=NAVY,
             anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.RIGHT)
    text(slide, 22.6, 16.6, 9.6, 1.4, "The second ticket costs only about 55k gas", size=11, color=GREY)

    # 9 failure cost ----------------------------------------------------
    slide = blank(prs)
    title_bar(slide, "Rejected calls still cost gas",
              "Why that is evidence that the rules live on chain", 9)
    picture(slide, CHARTS / "03_coverage_and_failed_tx.png", 1.4, 3.6, w=21.4)
    text(slide, 22.8, 3.6, 9.4, 9.6,
         ["The transaction was mined,", "it just returned status=0.", "",
          "If the rejection came from our", "script, those transactions would", "never appear on chain.", "",
          f"{s['on_chain_failed_txs']} rejected calls burned", f"{s['on_chain_failed_gas_total']:,} gas - ",
          "hence the canPurchase pre-check."],
         size=12.5, color=DARK, line_spacing=1.6)
    text(slide, 1.6, 14.4, 21.4, 1.8,
         "Left: 19 normal-path and 27 negative-path cases - for this system the value is in the refusals",
         size=11.5, color=GREY)

    # 10 bypass ---------------------------------------------------------
    slide = blank(prs)
    title_bar(slide, "Bypass the website: all four attacks failed",
              "B01-B04 import no business interface and start no page; only raw Web3.py", 10)
    table(slide, 1.7, 3.4, 30.4,
          ["ID", "Attack", "Result", "On-chain receipt"],
          [["B01", "List at 2.0 ETH (original 0.6)", "rejected", "Price exceeds dynamic limit"],
           ["B02", "Change the owner with transferFrom", "rejected", "status=0, ownerOf unchanged"],
           ["B03", "Call checkIn without the verifier role", "rejected", "status=0, used still false"],
           ["B04", "Pay 0.1 ETH for a 0.6 ETH ticket", "rejected", "Incorrect ETH amount"]],
          [1.6, 10.4, 2.4, 9.0], font_size=12.5, row_h=1.55)
    text(slide, 1.7, 12.0, 30.4, 5.0,
         ["Counter-evidence: had the rules lived in the UI, all four would have succeeded.",
          "T11a/T11b go further: the legitimate holder calls the standard ERC-721 transferFrom and",
          "safeTransferFrom entry points and both revert - 'sell it privately' does not work."],
         size=13, color=DARK, line_spacing=1.6)

    # 11 findings -------------------------------------------------------
    slide = blank(prs)
    title_bar(slide, "We found three real problems",
              "A test report that is entirely green is not credible", 11)
    table(slide, 1.6, 3.4, 30.6,
          ["Finding", "Nature", "Handling"],
          [["createEvent is permissionless: any address can create an event (T02b)", "spec deviation",
            "Recommend organizer approval or a stake"],
           ["getMaxResalePrice reverts after the event starts (E07)", "contract defect",
            "Check the timestamp first; the UI already guards it"],
           ["After regenerating accounts, network.json kept stale addresses -> insufficient funds",
            "deployment defect", "Fixed: addresses derive from the private keys"]],
          [13.0, 4.2, 9.4], font_size=12, row_h=2.3)
    text(slide, 1.6, 12.4, 30.4, 4.6,
         ["The third one matters most: it is invisible in a code review and only appears on the",
          "real path 'reset chain -> regenerate accounts -> deploy'.",
          "That is the value of testing: it makes hidden assumptions visible."],
         size=12.5, color=GREY, line_spacing=1.6)

    # 12 limitations ----------------------------------------------------
    slide = blank(prs)
    title_bar(slide, "Limits: what the chain can and cannot enforce",
              "Stating the boundary is more credible than claiming scalping is eliminated", 12)
    left = ["One person, many wallets: the limit is per address",
            "Event creation is permissionless: fake events are possible",
            "Server-side signing: not real user authorisation",
            "Single-node private chain: no censorship resistance"]
    right = ["Cash top-ups: the chain cannot police off-chain price",
             "Whole-wallet transfer: selling the key sells the ticket",
             "The QR protects credentials, not a stolen private key",
             "Not built: refunds, cancellation, seating, audit, upgradeability"]
    rect(slide, 1.7, 3.4, 14.6, 11.6, LIGHT)
    rect(slide, 17.3, 3.4, 15.4, 11.6, LIGHT)
    text(slide, 2.2, 3.7, 13.6, 0.9, "What the chain enforces", size=14, bold=True, color=GREEN)
    text(slide, 17.8, 3.7, 14.4, 0.9, "What it cannot enforce", size=14, bold=True, color=RED)
    for i, item in enumerate(left):
        text(slide, 2.2, 4.9 + i * 2.4, 13.6, 2.1, "- " + item, size=12, color=DARK, line_spacing=1.35)
    for i, item in enumerate(right):
        text(slide, 17.8, 4.9 + i * 2.4, 14.4, 2.1, "- " + item, size=12, color=DARK, line_spacing=1.35)
    text(slide, 1.7, 15.6, 30.6, 1.4,
         "Conclusion: the chain guarantees ticket uniqueness and non-bypassable rules, not that people "
         "stop hoarding.", size=13, bold=True, color=NAVY)

    # 13 conclusion -----------------------------------------------------
    slide = blank(prs)
    title_bar(slide, "Conclusion", "Four sentences", 13)
    conclusions = [
        ("The rules are enforced", "Over-buying, over-pricing, direct transfer, duplicate and unauthorised "
                                   "check-in are all rejected - with the website bypassed", GREEN),
        ("The rules are verifiable", "Every claim maps to a transaction hash; positive cases add a state "
                                     "read-back", BLUE),
        ("The cost is real", "Writes cost gas and rejected writes cost gas too, so pre-checks and "
                             "off-chain data are requirements", AMBER),
        ("The boundary is clear", "The chain governs tickets; people need identity and law", NAVY),
    ]
    for i, (head, body, color) in enumerate(conclusions):
        y = 3.3 + i * 3.4
        rect(slide, 1.7, y, 0.16, 2.9, color, shape=MSO_SHAPE.RECTANGLE)
        text(slide, 2.3, y + 0.25, 8.4, 1.2, head, size=16, bold=True, color=color)
        text(slide, 10.2, y + 0.25, 21.6, 2.4, body, size=12.5, color=DARK, line_spacing=1.4)

    # 14 demo -----------------------------------------------------------
    slide = blank(prs)
    title_bar(slide, "Live demo: seven actions",
              "Success paths first - the failure paths need an unused ticket", 14)
    demo_steps = [
        ("1", "Organizer creates an event", "createEvent", "02_events.png"),
        ("2", "buyerA buys ticket #1", "purchaseTickets", "03_buy_tickets.png"),
        ("3", "buyerA lists at 120%", "listForResale", "05_resale_market.png"),
        ("4", "buyerB buys it, ownerOf changes", "buyResale", "05_resale_market.png"),
        ("5", "Over-priced listing / direct transfer rejected", "revert", "05_resale_market.png"),
        ("6", "buyerB shows the QR, first check-in", "checkIn", "06_staff_checkin.png"),
        ("7", "Second check-in rejected", "revert", "06_staff_checkin.png"),
    ]
    for i, (num, action, fn, shot) in enumerate(demo_steps):
        y = 3.2 + i * 1.95
        rect(slide, 1.7, y + 0.15, 1.1, 1.1, BLUE, shape=MSO_SHAPE.OVAL)
        text(slide, 1.7, y + 0.32, 1.1, 0.8, num, size=13, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
        text(slide, 3.2, y + 0.2, 12.4, 1.2, action, size=13, color=DARK)
        text(slide, 15.8, y + 0.2, 8.4, 1.2, fn, size=11.5, color=GREY)
        text(slide, 24.4, y + 0.2, 8.0, 1.2, shot, size=10.5, color=RGBColor(0x90, 0xA4, 0xAE))
    text(slide, 1.7, 17.1, 30.4, 1.2,
         "Fallback evidence if the node misbehaves: results/screenshots/ and results/demo_report.md",
         size=11, color=GREY)

    # 15 Q&A ------------------------------------------------------------
    slide = blank(prs)
    rect(slide, 0, 0, 33.87, 19.05, NAVY, shape=MSO_SHAPE.RECTANGLE)
    text(slide, 3.0, 5.6, 27.9, 2.4, "Q & A", size=48, bold=True, color=WHITE)
    text(slide, 3.0, 8.6, 27.9, 1.2, "Thank you", size=20, color=RGBColor(0x90, 0xCA, 0xF9))
    facts = [f"Contract {net['contract_address'][:12]}...",
             f"Deployment gas {env['contract']['deploy_gas_used']:,}",
             f"{s['total_cases']} cases / {s['pass_rate']}% pass rate",
             "Every number traceable to a transaction hash"]
    for i, fact in enumerate(facts):
        text(slide, 3.0, 11.4 + i * 1.4, 27.9, 1.1, "- " + fact, size=13,
             color=RGBColor(0xCF, 0xD8, 0xDC))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    print(f"[pptx] written to {OUT}")
    print(f"[pptx] {len(prs.slides._sldIdLst)} slides")
    return OUT


if __name__ == "__main__":
    build()
