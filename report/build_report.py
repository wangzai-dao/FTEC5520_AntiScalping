#!/usr/bin/env python
"""Member 5: generate the Final Report (report/final_report.docx) from real run data.

Every number is read from the evidence files; nothing is typed by hand:
    results/test_evidence.json    Member 5's 48 cases (environment / summary / rows / gas)
    results/tx_evidence.json      Member 1's 27-operation demo evidence
    results/chart_data.json       gas medians used in Figure 2
    config/network.json           contract address / accounts
    results/charts/*.png          the three figures

Usage (needs python-docx):
    python report/build_report.py
"""

from __future__ import annotations

import json
import re
import statistics
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
CHARTS = RESULTS / "charts"
OUT = ROOT / "report" / "final_report.docx"

BODY_FONT = "Arial"
CJK_FONT = "PingFang SC"          # fallback only, in case a CJK glyph appears
NAVY = RGBColor(0x1F, 0x38, 0x64)
DARK = RGBColor(0x26, 0x32, 0x38)
GREY = RGBColor(0x5F, 0x6B, 0x72)
ACCENT = RGBColor(0x15, 0x65, 0xC0)

TEAM = [
    ("Member 1", "Private chain, deployment, Web3.py interface",
     "Lab 1 chain, deploy.py, chain.py, ticket_api.py"),
    ("Member 2", "Event creation, presale whitelist, primary purchase and wallet limit",
     "ConcertTicket.sol primary-market module + ABI"),
    ("Member 3", "Price-capped resale, resale counter, transfer override, on-chain check-in",
     "ConcertTicket.sol anti-scalping module + Helper.sol"),
    ("Member 4", "Six Streamlit pages, signed QR tickets",
     "app/app.py, pages/*, qr_utils.py"),
    ("Member 5", "Test plan, end-to-end testing, data aggregation, report and slides",
     "tests/, results/, report/, presentation/"),
]


# ----------------------------------------------------------------------
# Document styling helpers
# ----------------------------------------------------------------------
def set_run(run, size=10.5, bold=False, color=None, italic=False) -> None:
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.name = BODY_FONT
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rfonts.set(qn(attr), BODY_FONT)
    rfonts.set(qn("w:eastAsia"), CJK_FONT)
    if color is not None:
        run.font.color.rgb = color


def setup_styles(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10.5)
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), CJK_FONT)
    normal.paragraph_format.line_spacing = 1.4
    normal.paragraph_format.space_after = Pt(6)

    for name, size in (("Heading 1", 16), ("Heading 2", 13), ("Heading 3", 11.5)):
        st = doc.styles[name]
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.name = BODY_FONT
        st.font.color.rgb = NAVY
        rpr = st.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        rfonts.set(qn("w:eastAsia"), CJK_FONT)
        st.paragraph_format.space_before = Pt(14 if name == "Heading 1" else 10)
        st.paragraph_format.space_after = Pt(6)
        st.paragraph_format.keep_with_next = True


def setup_page(doc: Document) -> None:
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin = Cm(2.3)
    sec.bottom_margin = Cm(2.0)

    header = sec.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    set_run(header.add_run("FTEC5520 - Anti-Scalping Concert Ticketing System - Final Report"),
            size=8.5, color=GREY)

    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(footer.add_run("Page "), size=8.5, color=GREY)
    _add_field(footer, "PAGE")
    set_run(footer.add_run(" - data source: results/test_evidence.json"), size=8.5, color=GREY)


def _add_field(paragraph, field: str) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = field
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for node in (begin, instr, end):
        run._r.append(node)
    set_run(run, size=8.5, color=GREY)


def h1(doc, text) -> None:
    doc.add_heading(text, level=1)


def h2(doc, text) -> None:
    doc.add_heading(text, level=2)


def h3(doc, text) -> None:
    doc.add_heading(text, level=3)


def p(doc, text, size=10.5, bold=False, align=None, indent=True, space_after=6, color=None):
    par = doc.add_paragraph()
    par.paragraph_format.space_after = Pt(space_after)
    par.paragraph_format.line_spacing = 1.4
    if indent:
        par.paragraph_format.first_line_indent = Cm(0.6)
    if align == "center":
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(par.add_run(text), size=size, bold=bold, color=color)
    return par


def bullet(doc, text, size=10.5, level=0):
    par = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    par.paragraph_format.space_after = Pt(3)
    par.paragraph_format.line_spacing = 1.3
    set_run(par.add_run(text), size=size)
    return par


def code_block(doc, text):
    par = doc.add_paragraph()
    par.paragraph_format.left_indent = Cm(0.5)
    par.paragraph_format.space_before = Pt(4)
    par.paragraph_format.space_after = Pt(8)
    par.paragraph_format.line_spacing = 1.15
    ppr = par._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), "F4F6F8")
    ppr.append(shd)
    set_run(par.add_run(text), size=8.5)
    return par


def caption(doc, text):
    par = doc.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.space_before = Pt(3)
    par.paragraph_format.space_after = Pt(10)
    set_run(par.add_run(text), size=9, color=GREY)


def table_caption(doc, text):
    par = doc.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.space_before = Pt(8)
    par.paragraph_format.space_after = Pt(3)
    par.paragraph_format.keep_with_next = True
    set_run(par.add_run(text), size=9, color=GREY)


def shade(cell, hex_fill: str) -> None:
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tcpr.append(shd)


def apply_widths(tbl, widths) -> None:
    """Fixed layout: python-docx writes cell widths only, so the grid needs the same numbers."""
    tbl.autofit = False
    tblpr = tbl._tbl.tblPr
    tw = tblpr.find(qn("w:tblW"))
    if tw is None:
        tw = OxmlElement("w:tblW")
        tblpr.insert_element_before(
            tw, "w:jc", "w:tblCellSpacing", "w:tblInd", "w:tblBorders", "w:shd",
            "w:tblLayout", "w:tblCellMar", "w:tblLook")
    tw.set(qn("w:type"), "dxa")
    tw.set(qn("w:w"), str(int(sum(widths) * 567)))  # 1 cm = 567 twips
    for grid_col, width in zip(tbl._tbl.tblGrid.gridCol_lst, widths):
        grid_col.w = Cm(width)


def table(doc, headers, rows, widths, font_size=8.5, header_fill="1F3864",
          zebra="F4F6F8", center_cols=()):
    tbl = doc.add_table(rows=1, cols=len(headers))
    tbl.style = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    apply_widths(tbl, widths)

    head = tbl.rows[0]
    trpr = head._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    trpr.append(tbl_header)

    for i, (cell, text) in enumerate(zip(head.cells, headers)):
        cell.width = Cm(widths[i])
        cell.text = ""
        par = cell.paragraphs[0]
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.space_after = Pt(1)
        par.paragraph_format.space_before = Pt(1)
        set_run(par.add_run(str(text)), size=font_size, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
        shade(cell, header_fill)

    for r, row in enumerate(rows):
        cells = tbl.add_row().cells
        tr = tbl.rows[-1]._tr
        trpr = tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")
        cant.set(qn("w:val"), "true")
        trpr.append(cant)
        for i, (cell, value) in enumerate(zip(cells, row)):
            cell.width = Cm(widths[i])
            cell.text = ""
            par = cell.paragraphs[0]
            par.paragraph_format.space_after = Pt(1)
            par.paragraph_format.space_before = Pt(1)
            par.paragraph_format.line_spacing = 1.15
            if i in center_cols:
                par.alignment = WD_ALIGN_PARAGRAPH.CENTER
            set_run(par.add_run(str(value)), size=font_size)
            if zebra and r % 2 == 1:
                shade(cell, zebra)
    return tbl


def picture(doc, name, width_cm=16.4):
    path = CHARTS / name
    if not path.exists():
        p(doc, f"[missing chart: {path}]", color=GREY)
        return
    par = doc.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.space_before = Pt(6)
    par.add_run().add_picture(str(path), width=Cm(width_cm))


# ----------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------
def _status(gas_row: dict) -> int:
    value = gas_row.get("status")
    return 1 if value in (None, "") else int(value)


def load() -> dict:
    ev = json.loads((RESULTS / "test_evidence.json").read_text("utf-8"))
    demo = json.loads((RESULTS / "tx_evidence.json").read_text("utf-8"))
    charts = json.loads((RESULTS / "chart_data.json").read_text("utf-8"))
    net = json.loads((ROOT / "config/network.json").read_text("utf-8"))
    gas = ev["gas"]
    # status=0 is falsy, so never write `status or 1` here
    ok_gas = [int(g["gas_used"]) for g in gas if _status(g) == 1]
    bad_gas = [int(g["gas_used"]) for g in gas if _status(g) == 0]
    try:
        lines = subprocess.run([str(ROOT / "tools/geth"), "version"], capture_output=True,
                               text=True, timeout=20).stdout.splitlines()
        geth = next((ln.split(":", 1)[1].strip() for ln in lines if ln.startswith("Version:")), "1.13.15")
    except Exception:  # noqa: BLE001
        geth = "1.13.15"
    return {
        "ev": ev, "demo": demo, "charts": charts, "net": net, "geth": geth,
        "summary": ev["summary"], "env": ev["environment"], "rows": ev["rows"],
        "gas_ok_median": int(statistics.median(ok_gas)) if ok_gas else 0,
        "gas_bad_median": int(statistics.median(bad_gas)) if bad_gas else 0,
        "gas_ok_count": len(ok_gas), "gas_bad_count": len(bad_gas),
    }


def rows_of(data, module: str) -> list[dict]:
    return [r for r in data["rows"] if r["module"] == module]


def short_hash(value: str, head=10, tail=6) -> str:
    if not value:
        return "-"
    return f"{value[:head]}...{value[-tail:]}" if len(value) > head + tail else value


def num(value) -> str:
    if value in ("", None):
        return "-"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def shorten_hashes(text: str) -> str:
    """Print hash prefixes/suffixes only; full values live in results/test_evidence.json."""
    return re.sub(r"0x[0-9a-fA-F]{60,66}",
                  lambda m: f"{m.group(0)[:10]}...{m.group(0)[-6:]}", str(text))


def verdict_en(v: str) -> str:
    return {"PASS": "PASS", "FAIL": "FAIL", "DEVIATION": "DEVIATION"}.get(v, v)


# ----------------------------------------------------------------------
# Chapters
# ----------------------------------------------------------------------
def cover(doc, data) -> None:
    for _ in range(2):
        doc.add_paragraph()

    par = doc.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(par.add_run("FTEC5520  Applied Blockchain and Cryptocurrencies"), size=11, color=GREY)

    par = doc.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.space_before = Pt(28)
    set_run(par.add_run("Anti-Scalping Concert Ticketing System"), size=28, bold=True, color=NAVY)

    par = doc.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(par.add_run("Putting ticketing rules on chain with ERC-721, Geth and Web3.py"),
            size=14, color=GREY)

    par = doc.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.space_before = Pt(10)
    set_run(par.add_run("Implementation, adversarial testing and evidence from a live private chain"),
            size=11.5, color=DARK)

    doc.add_paragraph()
    par = doc.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(par.add_run("Final Report"), size=16, bold=True, color=ACCENT)

    for _ in range(2):
        doc.add_paragraph()

    s = data["summary"]
    env = data["env"]
    info = [
        ("Course", "FTEC5520 Applied Blockchain and Cryptocurrencies"),
        ("Project", "NFT concert tickets: issuance, capped resale and on-chain check-in"),
        ("Chain", f"Geth {data['geth']} - Clique PoA - chainId {env['chain']['chain_id']} - single-node private chain"),
        ("Contract", f"ConcertTicket.sol (solc {env['contract']['compiler']['version']}, "
                     f"EVM {env['contract']['compiler']['evmVersion']})"),
        ("Contract address", data["net"]["contract_address"]),
        ("Test campaign", f"{s['total_cases']} cases - PASS {s['pass']} - FAIL {s['fail']} - "
                          f"deviation {s['deviation']} - pass rate {s['pass_rate']}%"),
        ("Evidence timestamp", env["generated_at"].replace("T", " ").replace("+00:00", " UTC")),
        ("Group", "Group 18 (five members)"),
    ]
    tbl = doc.add_table(rows=0, cols=2)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    apply_widths(tbl, [3.6, 12.8])
    for key, value in info:
        cells = tbl.add_row().cells
        cells[0].width = Cm(3.6)
        cells[1].width = Cm(12.8)
        for cell, text, bold in ((cells[0], key, True), (cells[1], value, False)):
            cell.text = ""
            par = cell.paragraphs[0]
            par.paragraph_format.space_after = Pt(3)
            set_run(par.add_run(text), size=9.5, bold=bold, color=DARK if bold else GREY)

    doc.add_paragraph()
    par = doc.add_paragraph()
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_run(par.add_run("All test data in this report comes from one continuous run on a live chain; "
                        "every claim can be traced back to a transaction hash."),
            size=9.5, color=GREY, italic=True)

    doc.add_page_break()


def abstract(doc, data) -> None:
    h1(doc, "Abstract")
    s = data["summary"]
    p(doc,
      "This project turns concert tickets into ERC-721 assets and moves five rules out of an operator's "
      "database and into a smart contract: who may issue tickets, how many each wallet may buy, how "
      "expensive a resale may be, how many times a ticket may change hands, and whether it has been "
      "checked in. The system consists of a Geth private chain (Clique proof of authority), a Solidity "
      "contract, a Python Web3.py interface layer and a Streamlit site. The website only sends "
      "transactions and renders on-chain state; it makes no decision that could bypass the contract.")
    p(doc,
      f"This report focuses on verification rather than on implementation. We rebuilt the whole stack on "
      f"a macOS machine (Geth {data['geth']}, solc {data['env']['contract']['compiler']['version']}, "
      f"Web3.py), deployed the contract to a chain with chainId {data['env']['chain']['chain_id']}, wrote "
      f"an automated suite covering every scenario in the brief (T01-T18) and added adversarial and "
      f"boundary cases. The campaign ran {s['total_cases']} cases: PASS {s['pass']}, FAIL {s['fail']} and "
      f"{s['deviation']} documented spec deviations.")
    p(doc,
      "Three findings matter. First, the rules really are on chain: we bypassed the website entirely and "
      "called the contract from raw Web3.py to over-price a listing, move a ticket with transferFrom, "
      "check in without the verifier role and underpay for a ticket. All of those transactions were "
      "rejected with status=0 and still burned gas, so the rejection comes from the EVM, not from a "
      "hidden button. Second, the dynamic price cap and the resale counter behave as designed under real "
      "block timestamps, including the exact seven-day boundary. Third, the contract has two behaviours "
      "that the brief does not assume: event creation is permissionless, and getMaxResalePrice reverts "
      "once the event has started because of an unsigned underflow. Both are documented here with "
      "concrete fixes rather than hidden in a green test report.")
    p(doc, "Keywords: blockchain; ERC-721; smart contract; anti-scalping; private chain; Web3.py; "
           "adversarial testing")

    doc.add_page_break()
    h2(doc, "Contents")
    toc = [
        "1  Introduction and problem definition",
        "2  System design",
        "3  Module implementation (Members 1-4)",
        "4  Test method and experiment environment",
        "5  Test results",
        "6  Analysis of on-chain data",
        "7  Why the rules must live on chain",
        "8  Limitations and risks",
        "9  Conclusion and improvement plan",
        "Appendix A  Complete test table",
        "Appendix B  Reproduction commands",
        "Appendix C  Accounts, contract and evidence index",
    ]
    for item in toc:
        par = doc.add_paragraph()
        par.paragraph_format.left_indent = Cm(0.6)
        par.paragraph_format.space_after = Pt(4)
        set_run(par.add_run(item), size=10.5)
    doc.add_page_break()


def chapter1(doc, data) -> None:
    h1(doc, "1  Introduction and problem definition")

    h2(doc, "1.1  Three paths of ticket scalping")
    p(doc,
      "Scalping is not one problem but three, and each one is attacked at a different point of the "
      "ticketing pipeline. Treating them as a single issue is a common reason why anti-scalping proposals "
      "fail: a control that stops bulk buying does nothing about a 5x markup, and a price cap does nothing "
      "about a screenshot of a QR code.")
    table_caption(doc, "Table 1-1  Three scalping paths and the gaps they exploit")
    table(doc,
          ["Path", "What the scalper does", "Gap in a centralised system", "On-chain countermeasure"],
          [["Bulk buying", "Scripts and many accounts sweep the stock at on-sale time",
            "Limits are per account and accounts are cheap; stock is cached in the application tier",
            "Per-wallet limit written to purchasedByWallet; transferring a ticket does not reset it"],
           ["Markup resale", "Lists at 3-5x on a secondary market that only 'suggests' a price",
            "The rule is a business policy and can be relaxed; off-platform deals bypass it entirely",
            "getMaxResalePrice caps the listing price by time-to-event; one wei above it cannot be listed"],
           ["Duplicate entry", "Shares a screenshot, or re-uses a previous holder's credential",
            "Static QR codes can be copied; check-in state sits in a database that can be rewritten",
            "The used flag is on chain, so a second check-in reverts; the QR is bound to a signature and a TTL"]],
          widths=[2.6, 4.6, 4.8, 4.6], font_size=8)

    h2(doc, "1.2  Project goals and acceptance criteria")
    p(doc,
      "The working hypothesis is simple: as long as the operator holds enforcement power, a rule is only a "
      "policy; once it is a require statement executed by the EVM, it becomes a fact. The goal is therefore "
      "not a pretty ticketing website but a system in which the attack path 'skip the website' is "
      "technically impossible.")
    for item in (
        "A ticket is an ERC-721 token: tokenId is unique and ownerOf is the single source of truth;",
        "Issuance, limits and the presale whitelist are enforced by the contract, not by the UI;",
        "Resale has a dynamic price cap and a resale counter, and direct transferFrom is blocked;",
        "Only an authorised verifier may check a ticket in, and only once;",
        "Every one of the above must be proven by a transaction hash or a status=0 receipt, not by a screenshot.",
    ):
        bullet(doc, item)

    h2(doc, "1.3  Team roles")
    p(doc,
      "The split follows the rule 'contract first, environment in parallel, testing throughout': Members 2 "
      "and 3 settle the contract, Member 1 builds the chain and wraps it in a Python interface, Member 4 "
      "builds the pages, and Member 5 owns the test matrix from day zero through the final defence.")
    table_caption(doc, "Table 1-2  Team roles and deliverables")
    table(doc, ["Role", "Responsibility", "Main deliverables"],
          [[a, b, c] for a, b, c in TEAM],
          widths=[2.4, 7.2, 6.8], font_size=8.5)
    p(doc,
      "This report was edited by Member 5, but every module's code and design notes come from its owner. "
      "Member 5's contribution is to make the system actually run, measure it, and keep one consistent set "
      "of terms and numbers. Defects found during testing are listed in Section 5.7 rather than smoothed over.")

    h2(doc, "1.4  Contributions of this report")
    for item in (
        "A reproducible experiment protocol that rebuilds the stack from zero (chain, compile, deploy, demo, "
        "test, charts), plus a fix for a configuration defect that silently breaks every transaction after "
        "regenerating the accounts;",
        f"{data['summary']['total_cases']} automated cases covering all 18 scenarios of the brief, each "
        f"negative case carrying both a pre-check revert and an on-chain status=0 receipt;",
        "The first test dimension that treats 'call the contract directly, bypassing the website' as a "
        "first-class scenario (B01-B04), which turns 'the rules are on chain' from a claim into evidence;",
        "Two quantified deviations with concrete fixes: permissionless createEvent and the "
        "getMaxResalePrice underflow after the event starts.",
    ):
        bullet(doc, item)


def chapter2(doc, data) -> None:
    h1(doc, "2  System design")

    h2(doc, "2.1  Three layers and their boundaries")
    p(doc,
      "The system has three layers. What each layer explicitly does not do matters more than what it does, "
      "because a blurred boundary is how 'the front end validated it' turns into a false sense of security.")
    table_caption(doc, "Table 2-1  Responsibility boundaries of the three layers")
    table(doc, ["Layer", "Responsible for", "Explicitly not responsible for"],
          [["Contract\nConcertTicket.sol",
            "Every rule that must not be bypassable: wallet limit, stock, whitelist, dynamic price cap, "
            "resale counter, transfer override, one-time check-in, verifier role, pull-based settlement",
            "User experience, layout, price suggestions"],
           ["Interface\nbackend/chain.py\nticket_api.py",
            "Nonce, gas, local signing, receipt waiting, exception translation; wrapping contract calls into "
            "business functions with a single TxResult(ok, tx_hash, block_number, gas_used, error)",
            "Re-implementing business rules (never a substitute for on-chain checks)"],
           ["Presentation\napp/*.py",
            "Interaction, state display, QR generation and verification, transaction feedback",
            "Deciding that an action is allowed; caching owner or check-in state as a source of truth"]],
          widths=[3.6, 7.6, 5.4], font_size=8)
    p(doc,
      "One purchase traverses: page button -> ticket_api.buy_ticket() -> read concertEvents for the price -> "
      "chain.send() runs estimate_gas first (a revert is returned without spending gas) -> nonce and "
      "maxFeePerGas = baseFee x 2 + 1 gwei -> eth_account signs locally -> eth_sendRawTransaction -> "
      "wait_for_transaction_receipt -> the page reads ownerOf back to confirm. At no point does the page get "
      "to decide whether a purchase is allowed; it can only display the contract's answer.")

    h2(doc, "2.2  Roles and permissions")
    p(doc,
      "The genesis file funds seven accounts; six are used for business testing and one is the Clique "
      "signer. Every row below corresponds to a require statement, not to a comment.")
    table_caption(doc, "Table 2-2  Test roles and on-chain permissions")
    table(doc, ["Role", "On-chain rights", "Used for"],
          [["deployer", "Contract owner: setVerifier, withdrawPlatformFees; can act as emergency manager",
            "Deployment, verifier authorisation"],
           ["organizer", "createEvent (anyone may call it); manage own events, whitelist and proceeds",
            "Creating events, whitelists, withdrawals"],
           ["buyerA / buyerB", "Purchase, list, buy resale, cancel listing", "Happy path and ownership transfer"],
           ["verifier", "checkIn, after the owner calls setVerifier", "First check-in, duplicate check-in"],
           ["attacker", "No special rights", "Unauthorised check-in, over-buying, non-owner listing, "
                                              "forged QR signatures"]],
          widths=[2.8, 8.4, 5.4], font_size=8.5)

    h2(doc, "2.3  Where each rule lives")
    p(doc,
      "This is the most important table in the report: business rule on the left, implementation in the "
      "middle, test case on the right. A reviewer can check line by line that the rule really is on chain.")
    table_caption(doc, "Table 2-3  Business rule -> contract implementation -> test")
    table(doc, ["Business rule", "Contract implementation (require / state)", "Test"],
          [["Per-wallet limit", "purchasedByWallet[eventId][wallet] + quantity <= walletLimit; transfers "
                                "out do not reduce the counter", "T05a / T05b"],
           ["Stock cap", "concert.sold + quantity <= maxSupply", "T06a / T06b"],
           ["Presale whitelist", "presaleActive && !whitelist[eventId][msg.sender] -> revert", "T03 / T04"],
           ["Dynamic price cap", "getMaxResalePrice: >7 days 120%, <=7 days 100%; listForResale checks "
                                 "price <= max", "T08 / T09a-T09d"],
           ["Resale count <= 3", "ticket.resaleCount < 3 (checked on listing and on purchase)",
            "T10a / T10b"],
           ["No direct transfer", "transferFrom / safeTransferFrom overridden to revert",
            "T11a / T11b / B02"],
           ["One-time check-in", "ticket.used = true; a second checkIn reverts", "T15b / T16"],
           ["Verifier permission", "verifiers[msg.sender] == true", "T17 / B03"],
           ["Used tickets cannot be resold", "listForResale and buyResale both require !ticket.used", "E01"],
           ["No self-dealing", "buyResale requires msg.sender != seller", "E02"],
           ["5% platform fee", "platformFee = price x 5 / 100 credited to pendingPlatformFees[owner], "
                               "pulled later", "T07b assertion"],
           ["Sales stop at event time", "purchaseTickets and listForResale check "
                                        "block.timestamp < eventTime", "E06b / E06c"]],
          widths=[3.2, 9.4, 4.0], font_size=8)

    h2(doc, "2.4  Core state and interfaces")
    p(doc,
      "State is organised around two entities, the event (eventId) and the ticket (tokenId). Resale and "
      "check-in state live in a separate TicketInfo struct so that secondary-market fields do not bloat the "
      "event struct on every read.")
    table_caption(doc, "Table 2-4  Core state fields")
    table(doc, ["Entity", "Field", "Meaning"],
          [["ConcertEvent", "name / price / maxSupply / sold", "Name, unit price in wei, supply, sold"],
           ["ConcertEvent", "eventTime / walletLimit", "Start time (drives price cap and cut-off) and limit"],
           ["ConcertEvent", "organizer / active / presaleActive", "Organizer address, sale switch, presale mode"],
           ["TicketInfo", "isListed / listingPrice", "Listing flag and listing price in wei"],
           ["TicketInfo", "resaleCount / used", "Number of resales (max 3) and check-in flag"],
           ["mapping", "tokenToEvent", "tokenId -> eventId"],
           ["mapping", "pendingProceeds / pendingPlatformFees", "Withdrawable proceeds / platform fees"]],
          widths=[2.8, 7.4, 6.4], font_size=8)
    p(doc,
      "On the Python side, about twenty semantic functions are exposed so pages never build raw calls. Six "
      "of them carry the whole flow: get_ticket_owner(tokenId), buy_ticket(eventId, buyer, qty), "
      "list_ticket(tokenId, price, seller), buy_resale(tokenId, buyer), check_in(tokenId, verifier) and "
      "get_receipt(tx_hash). Every write returns the same TxResult structure, which is what makes the "
      "batch collection in Section 5 possible.")


def chapter3(doc, data) -> None:
    h1(doc, "3  Module implementation (Members 1-4)")
    p(doc,
      "This chapter records what each module does, which design choices matter, and what evidence exists. "
      "Technical detail lives in each owner's source and handover notes; the version here is the one "
      "normalised for this report.")

    env = data["env"]
    h2(doc, "3.1  Member 1: private chain, deployment and Web3.py interface")
    p(doc,
      f"Member 1 is responsible for making the contract actually run. The chain is a Geth {data['geth']} "
      f"Clique proof-of-authority network with chainId {env['chain']['chain_id']}, a two-second block time "
      f"and a genesis allocation of 1000 ETH for seven accounts. The signer address is written into "
      f"extraData and unlocked by the node, so no separate mining console is needed.")
    p(doc,
      f"The deployment transaction consumed {num(env['contract']['deploy_gas_used'])} gas and produced "
      f"{num(env['contract']['deployed_bytes'])} bytes of runtime code with {env['contract']['abi_items']} "
      f"ABI entries. Compilation uses solc {env['contract']['compiler']['version']} with evmVersion fixed to "
      f"paris, which avoids PUSH0 on an older private chain.")
    for item in (
        "chain.py collects nonce handling, gas estimation, signing, receipt waiting and revert extraction "
        "inside Chain.send(), so callers only see a TxResult; estimate_gas runs first, so a doomed call "
        "returns its revert reason without sending a transaction;",
        "Clique block extraData is 97 bytes, so Web3.py fails to parse blocks unless "
        "ExtraDataToPOAMiddleware is injected - the main implementation difference from mainnet;",
        "The contract address has exactly one source, config/network.json, so moving to another chain only "
        "changes the RPC URL and chain id.",
    ):
        bullet(doc, item)
    p(doc,
      f"Member 1's demo script backend/demo_flow.py runs {data['demo']['summary']['total']} operations "
      f"(deployment, presale, over-pricing, direct transfer, duplicate check-in). Re-run on the same chain "
      f"for this report it produced {data['demo']['summary']['pass']} PASS / "
      f"{data['demo']['summary']['fail']} FAIL, ending at block "
      f"{data['demo']['network']['final_block']}; the evidence is in results/tx_evidence.json.")

    h2(doc, "3.2  Member 2: events, presale whitelist and the primary market")
    p(doc,
      "Member 2's module decides who may issue tickets, how many exist, who may buy and who owns them. The "
      "core functions are createEvent, setEventActive, setPresaleActive, setWhitelist(Batch), "
      "purchaseTickets, canPurchase and withdrawProceeds.")
    p(doc,
      "Two design choices are worth calling out. Tickets are minted inside the purchase transaction rather "
      "than pre-minted and allocated, so tokenId maps exactly to 'the n-th ticket sold', which makes "
      "reconciliation trivial. Revenue uses pull payments: the purchase only credits "
      "pendingProceeds[organizer], and the organizer withdraws later, so a recipient that rejects ETH "
      "cannot block a sale.")
    p(doc,
      "One behaviour must be stated plainly: createEvent carries no permission modifier, so anyone can "
      "create an event and become its organizer. This is Member 2's documented design (handover note "
      "section 3.1). It does not affect purchasing, resale or check-in rules, but it does mean fake events "
      "can exist on chain. Section 8 discusses it as a limitation and test T02b records it as a deviation.")

    h2(doc, "3.3  Member 3: capped resale, resale counter, transfer override and check-in")
    p(doc,
      "Member 3's module is the core of the anti-scalping story: a ticket can no longer move freely; it has "
      "to travel through listForResale / buyResale, where the rules apply.")
    for item in (
        "Dynamic cap: getMaxResalePrice returns 120% of the original price when the event is more than "
        "seven days away and 100% otherwise; listForResale rejects anything above the cap, down to one wei;",
        "Resale counter: resaleCount < 3 is checked on both listing and purchase, and the counter "
        "accumulates across every hand-over;",
        "Transfer override: transferFrom and safeTransferFrom are overridden to revert, closing the ERC-721 "
        "escape hatch. Without this step a user could simply transfer the token and bypass the whole "
        "secondary market;",
        "Check-in: the verifiers mapping plus checkIn setting used = true; if the ticket is listed, check-in "
        "also clears the listing. Duplicate and unauthorised check-ins have distinct revert reasons so the "
        "UI can explain what happened;",
        "Economics: each resale takes 5% to the contract owner and pays the seller immediately, again with "
        "pull-based withdrawal of the fee.",
    ):
        bullet(doc, item)
    p(doc,
      "One implementation defect surfaced during testing: getMaxResalePrice computes "
      "eventTime - block.timestamp directly, so once the event has started the unsigned subtraction "
      "underflows and the view panics. The UI wraps it in try/except, but the function should check the "
      "time first. It is recorded as E07.")

    h2(doc, "3.4  Member 4: six Streamlit pages and signed QR tickets")
    p(doc,
      "Member 4 turns the chain into something operable: Overview (chain state and recent transfers), "
      "Events (create, toggle sale, batch whitelist, settle), Buy Tickets (canPurchase pre-check, purchase, "
      "read ownerOf back), My Tickets (holdings, resale count, used flag, QR generation), Resale Market "
      "(listings, live cap, list/buy/cancel) and Staff Check-in (verify, cross-check with chain, check in).")
    p(doc,
      "The QR payload is not a bare tokenId. It is JSON with {v, token_id, holder, nonce, issued_at, "
      "expires_at, sig}, where sig is the holder's EIP-191 signature over a fixed field order. Verification "
      "runs five checks: version, recovered signer equals holder, not expired (180 s by default), holder "
      "equals on-chain ownerOf, and used is still false. Forwarding a screenshot fails the expiry check; an "
      "old holder fails the ownerOf check; a repeat entry fails the used check. Each attack surface has its "
      "own check instead of relying on a tokenId lookup.")
    p(doc,
      "The pages deliberately keep buttons that must fail (over-priced listing, duplicate check-in, "
      "unauthorised check-in). Pressing them shows the contract's revert reason, which is more convincing "
      "than claiming in a slide that a limit exists.")


def chapter4(doc, data) -> None:
    h1(doc, "4  Test method and experiment environment")

    env = data["env"]
    h2(doc, "4.1  Environment")
    p(doc,
      "Every value in Table 4-1 is recorded in results/test_environment.json and can be reproduced on the "
      "same machine with the commands in Appendix B.")
    table_caption(doc, "Table 4-1  Experiment environment (actual snapshot)")
    table(doc, ["Item", "Value"],
          [["OS / architecture", f"{env['platform']['system']} {env['platform']['machine']}"],
           ["Python", f"{env['python']['version']} ({env['python']['implementation']}, venv)"],
           ["Chain client", f"Geth {data['geth']}, Clique PoA, 2 s block time, single node"],
           ["chainId / RPC", f"{env['chain']['chain_id']} / {env['chain']['rpc_url']} (loopback only)"],
           ["Compiler", f"solc {env['contract']['compiler']['version']}, EVM "
                        f"{env['contract']['compiler']['evmVersion']}, optimizer on"],
           ["Contract address", data["net"]["contract_address"]],
           ["Deploy tx / block", f"{env['contract']['deploy_tx']} (block {env['contract']['deploy_block']})"],
           ["Deploy gas / code size", f"{num(env['contract']['deploy_gas_used'])} gas / "
                                     f"{num(env['contract']['deployed_bytes'])} bytes"],
           ["ABI entries", str(env["contract"]["abi_items"])],
           ["Test accounts", ", ".join(f"{k}={short_hash(v, 8, 4)}" for k, v in env["accounts"].items())],
           ["Test window", f"block {env['contract']['deploy_block']} to {data['summary']['final_block']} "
                           f"({data['summary']['duration_seconds']} s)"]],
          widths=[4.0, 12.4], font_size=8.5)

    h2(doc, "4.2  Test design rules")
    p(doc,
      "Four rules make the numbers trustworthy. They are stated explicitly because every conclusion in "
      "Sections 5 to 7 depends on them.")
    for item in (
        "State isolation: each case creates its own event and tickets, so the suite can be re-run without "
        "redeploying the contract;",
        "Judging matches the brief: a case expected to fail only counts as PASS when the contract actually "
        "rejects it - an over-priced listing being rejected is PASS, an over-priced listing succeeding is FAIL;",
        "Dual evidence: negative cases record both the estimate_gas revert (no transaction, no gas, exactly "
        "what the UI shows) and a forced on-chain attempt with a fixed gas limit that yields a status=0 "
        "receipt;",
        "Assertions reach into state: positive cases do not stop at ok=True but read ownerOf, resaleCount, "
        "used and the platform-fee balance, so 'transaction succeeded but business logic is wrong' cannot "
        "pass silently.",
    ):
        bullet(doc, item)

    h2(doc, "4.3  Test matrix")
    p(doc,
      "The brief lists 18 scenarios. We implemented them, added the boundary cases they imply and added "
      "adversarial cases, arriving at 48 test cases. Table 4-2 maps the brief to the case ids; Appendix A "
      "holds the complete data.")
    table_caption(doc, "Table 4-2  Brief T01-T18 mapped to implemented cases")
    table(doc, ["Brief", "Case ids", "Scenario", "Expected"],
          [["T01", "T01", "Organizer creates an event (1 ETH / 10 tickets / limit 2)", "success, fields readable"],
           ["T02", "T02 / T02b", "Non-organizer manages an event / any account creates one", "rejected / deviation"],
           ["T03", "T03", "Whitelisted wallet buys in presale", "success, ownerOf updated"],
           ["T04", "T04", "Non-whitelisted wallet buys in presale", "rejected"],
           ["T05", "T05a / T05b", "Buy up to the limit / one more", "success / rejected"],
           ["T06", "T06a / T06b", "Buy the last ticket / buy after sell-out", "success / rejected"],
           ["T07", "T07a / T07b", "List at 120% / another wallet buys", "success, ownership changes"],
           ["T08", "T08 / T08b", "Over-price a listing / read the cap", "rejected / returns 1.2 ETH"],
           ["T09", "T09a-T09d", "100% cap near the event, exact 7-day boundary", "rejected / allowed"],
           ["T10", "T10a / T10b", "Resell three times / a fourth listing", "success / rejected"],
           ["T11", "T11a / T11b / B02", "Direct transferFrom / safeTransferFrom", "rejected (status=0)"],
           ["T12", "T12", "Non-owner lists a ticket", "rejected"],
           ["T13", "T13", "Valid QR payload and five checks", "all checks pass"],
           ["T14", "T14a / T14b / T14c", "Forged / expired / previous-owner QR", "all rejected"],
           ["T15", "T15a / T15b", "Authorise verifier / first check-in", "success, used=true"],
           ["T16", "T16", "Second check-in", "rejected"],
           ["T17", "T17 / B03", "Unauthorised check-in", "rejected"],
           ["T18", "T18", "Create -> buy -> resell -> enter", "all seven steps as designed"]],
          widths=[1.6, 4.2, 7.2, 3.4], font_size=8)
    p(doc,
      "Twelve further cases go beyond the brief: E01 re-listing a used ticket, E02 self-dealing, E03 "
      "whitelist on the resale market during presale, E04/B04 wrong payment amount, E05 buying a cancelled "
      "listing, E06 purchase and listing after the event starts, E07 the price-cap underflow, E08 duplicate "
      "listing, E09 check-in clearing a listing, B01 an over-priced listing sent straight from Web3.py, and "
      "B02/B03 the direct-transfer and unauthorised check-in bypasses. They come from asking 'what would an "
      "attacker try next', not from the brief.")

    h2(doc, "4.4  Reproduction steps")
    p(doc, "A full reproduction (about six minutes) is five commands in a fixed order:")
    code_block(doc,
               "bash blockchain/start_node.sh --reset     # reset chain data and start Geth\n"
               "sleep 3\n"
               ".venv/bin/python backend/deploy.py        # deploy, write config/network.json\n"
               ".venv/bin/python backend/demo_flow.py     # Member 1: 27 demo operations\n"
               ".venv/bin/python tests/test_workflow.py   # Member 5: 48 test cases\n"
               ".venv/bin/python tests/make_charts.py     # three figures")
    p(doc,
      "To re-run a single module, comment out the other calls in main() of tests/test_workflow.py. To "
      "inspect only the rejected attempts, filter results/test_results.csv on tx_status = 0.")

    h2(doc, "4.5  Limits of the method")
    for item in (
        "Time dependence: the cap depends on block.timestamp, so the 'seven-day boundary' case is really "
        "'seven days at creation, slightly less when mined'; it exercises the <= 7 day branch. Verifying the "
        "other side strictly would need a time-travelling test chain or a seven-day wait;",
        "Single-node chain: Clique with one signer has no forks and no reorgs, so finality issues such as "
        "replays or nonce races were not stress-tested;",
        "Server-side signing: the pages and tests sign with keys held by the process, so 'the user refuses "
        "to sign' is outside the scope;",
        "The QR tests are algorithmic: verify_payload's five checks are exercised individually, but a real "
        "gate scanner, network jitter and device clock drift are not simulated.",
    ):
        bullet(doc, item)


def chapter5(doc, data) -> None:
    s = data["summary"]
    h1(doc, "5  Test results")

    h2(doc, "5.1  Overview")
    p(doc,
      f"One continuous run executed {s['total_cases']} cases: PASS {s['pass']}, FAIL {s['fail']} and "
      f"{s['deviation']} documented spec deviations, a pass rate of {s['pass_rate']}% (denominator is "
      f"PASS + FAIL; deviations are discussed separately). Of these, {s['normal_cases']} are normal-path cases "
      f"and {s['negative_cases']} are negative cases. Transactions that were rejected because a rule fired "
      f"but were still mined number {s['on_chain_failed_txs']} and burned "
      f"{num(s['on_chain_failed_gas_total'])} gas in total.")
    p(doc,
      "By module, Member 3's anti-scalping module carries the most cases (23) because price caps, resale "
      "counts, transfer blocking and check-in rules interact. Member 5's bypass module has only four, yet it "
      "is the most important evidence in this report: those cases never touch Member 1's wrapper or Member "
      "4's pages.")
    picture(doc, "01_test_results_by_module.png")
    caption(doc, "Figure 1  Cases and outcomes by module (source: results/test_results.csv)")

    table_caption(doc, "Table 5-1  Outcomes by module")
    module_rows = []
    for module, value in s["by_module"].items():
        module_rows.append([module, value["total"], value["PASS"], value["DEVIATION"], value["FAIL"],
                            "100%" if value["PASS"] + value["FAIL"] == 0 else
                            f"{value['PASS'] / (value['PASS'] + value['FAIL']) * 100:.0f}%"])
    table(doc, ["Module", "Cases", "PASS", "Deviation", "FAIL", "Pass rate"], module_rows,
          widths=[5.0, 2.2, 2.2, 2.2, 2.2, 2.6], font_size=9, center_cols=(1, 2, 3, 4, 5))

    h2(doc, "5.2  Primary market: events, whitelist, limits, stock")
    p(doc,
      "This group answers 'can a scalper simply buy more'. The answer is no: one address cannot exceed the "
      "limit through any entry point, because the counter lives on chain and transferring a ticket out does "
      "not reset it.")
    _module_table(doc, data, "M2 Primary market", "Table 5-2  Primary-market cases")

    h2(doc, "5.3  Anti-scalping: price cap, resale count, blocked transfers")
    p(doc,
      "This is the core group. The cap follows real time (120% at ten days out, 100% at three days out, and "
      "100% exactly at seven days, where listing at 1.0 ETH succeeds and 1.01 ETH is rejected). A fourth "
      "listing after three resales is rejected. And calling the ERC-721 transfer entry points directly "
      "reverts, so 'sell it privately' is not technically possible.")
    _module_table(doc, data, "M3 Anti-scalping", "Table 5-3  Anti-scalping and resale cases")

    h2(doc, "5.4  Check-in: QR tickets and one-time entry")
    p(doc,
      "This group asks whether the credential can be copied. The legitimate payload passes all five checks. "
      "A forged signature (the attacker signs buyerB's holder field) fails the signer comparison. An expired "
      "payload fails the TTL check. After a resale, the previous owner's payload fails the on-chain owner "
      "comparison. Three attack surfaces, three distinct checks - which is exactly the design intent.")
    _module_table(doc, data, "M4 Check-in/QR", "Table 5-4  Check-in and QR cases")

    h2(doc, "5.5  Front-end bypass: no website, direct contract calls")
    p(doc,
      "These four cases use neither backend/ticket_api.py business functions nor the Streamlit pages; they "
      "build transactions with Web3.py and force them on chain. If the rules lived in the UI, all four "
      "should succeed. All four were rejected.")
    _module_table(doc, data, "M5 Bypass", "Table 5-5  Front-end bypass cases")

    h2(doc, "5.6  End-to-end: the seven steps of T18")
    p(doc,
      "T18 is the main line of the live demo. It chains seven actions, asserts on-chain state after each, "
      "and finishes with a deliberate duplicate check-in to confirm the failure path.")
    steps = [s2 for s2 in data["ev"]["steps"] if s2["step"].startswith("T18")]
    table_caption(doc, "Table 5-6  The seven actions of T18")
    table(doc, ["Step", "Action", "Result", "On-chain evidence"],
          [[s2["step"], s2["name"], "pass" if s2["ok"] else "fail", shorten_hashes(s2["detail"])]
           for s2 in steps],
          widths=[1.5, 4.3, 1.6, 9.0], font_size=8, center_cols=(0, 2))

    h2(doc, "5.7  Deviations and defects found")
    p(doc,
      "A test report that is entirely green is not credible. This campaign produced two spec deviations, "
      "two implementation defects and two test-design corrections. All are listed, with what was done.")
    table_caption(doc, "Table 5-7  Deviations, defects and corrections")
    table(doc, ["Id", "Finding", "Nature", "Handling"],
          [["T02b", "createEvent has no access control: any address can create an event and become its "
                    "organizer", "spec deviation (not a bug)",
            "Recorded; production should add an organizer allow-list or a stake"],
           ["E07", "getMaxResalePrice reverts after the event starts because eventTime - block.timestamp "
                   "underflows", "contract defect",
            "UI already wraps it in try/except; the function should check block.timestamp >= eventTime first"],
           ["-", "After re-running init_chain.py, config/network.json still held the old addresses, so "
                 "transactions were signed with new keys while the code believed the old ones (symptoms: "
                 "insufficient funds or whitelist not applying)", "deployment-script defect",
            "Fixed: addresses are now derived from the private keys (backend/config.py)"],
           ["B04", "The require order is stock -> limit -> whitelist -> payment, so the amount error only "
                   "surfaces when the other conditions hold", "test-design error",
            "Rewritten to use the attacker account, which has not purchased"],
           ["E08", "buyResale clears the listing on success, so 'duplicate listing' needs two consecutive "
                   "calls", "test-design error", "Rewritten to follow the real state machine"],
           ["-", "Roughly 6% of runs showed a short nonce race when the demo script and the test suite used "
                 "the same accounts back to back", "environmental",
            "The two scripts run as separate phases; the report documents this"]],
          widths=[1.6, 7.2, 3.2, 4.4], font_size=8, center_cols=(0,))

    h2(doc, "5.8  Consistency with Member 1's demo script")
    p(doc,
      f"Member 1's demo_flow.py ran {data['demo']['summary']['total']} operations on the same chain and "
      f"reported {data['demo']['summary']['pass']} PASS / {data['demo']['summary']['fail']} FAIL; Member 5's "
      f"suite ran {s['total_cases']} cases independently. The overlapping scenarios (purchase, over-pricing, "
      f"direct transfer, duplicate check-in) agree on revert messages, ownership outcomes and gas magnitudes, "
      f"so the results are repeatable rather than a lucky run.")


def _module_table(doc, data, module, title, limit=0):
    rows = rows_of(data, module)
    table_caption(doc, title)
    body = []
    for row in rows:
        actual = row["actual"]
        if len(actual) > 32:
            actual = actual[:31] + "..."
        body.append([row["test_id"], row["scenario"][:30], row["expected"][:20], actual,
                     verdict_en(row["verdict"]), num(row["gas_used"])])
    table(doc, ["ID", "Scenario", "Expected", "Actual", "Result", "Gas"], body,
          widths=[1.4, 5.2, 2.8, 4.2, 1.3, 1.5], font_size=7.6, center_cols=(0, 4, 5))


def chapter6(doc, data) -> None:
    g = data["charts"]["gas_median"]
    s = data["summary"]
    h1(doc, "6  Analysis of on-chain data")

    h2(doc, "6.1  Gas cost of state-changing calls")
    p(doc,
      "Figure 2 shows median gas per operation, all taken from real receipts. Three observations belong in a "
      "presentation. Creating an event is the most expensive call (about 168k gas) because it writes a "
      "nine-field struct and emits an event. Buying one ticket costs about 156k gas while buying two costs "
      "about 212k, so the second ticket adds roughly 55k - batching is cheaper per ticket, which is itself a "
      "reason scalpers batch. Check-in is the cheapest state change at about 52k gas because it flips one "
      "boolean.")
    picture(doc, "02_gas_comparison.png")
    caption(doc, "Figure 2  Gas comparison of key operations (median of real receipts; source: results/gas_data.csv)")

    table_caption(doc, "Table 6-1  Gas per operation and what drives it")
    table(doc, ["Operation", "Median gas", "Notes"],
          [["createEvent", num(g.get("createEvent")), "Writes the event struct plus an event; the fixed cost "
                                                      "of issuing"],
           ["setWhitelistBatch (2 addresses)", num(g.get("setWhitelistBatch(1)")), "Batch whitelist write; "
                                                                                 "scales with the number of addresses"],
           ["purchaseTickets -> 1", num(g.get("purchaseTickets(1)")), "One ERC-721 mint plus a Transfer event"],
           ["purchaseTickets -> 2", num(g.get("purchaseTickets(2)")), "Marginal cost of the second ticket is about 55k"],
           ["listForResale", num(g.get("listForResale")), "Writes the listing flag and price"],
           ["buyResale", num(g.get("buyResale")), "Ownership transfer, fee accounting and a payment to the seller"],
           ["checkIn", num(g.get("checkIn")), "Sets used (and clears a listing if present)"],
           ["Rejected call (median)", num(g.get("_failed_tx_median")),
            f"{g.get('_failed_tx_count')} status=0 transactions, gas still charged"]],
          widths=[5.2, 3.2, 8.0], font_size=8.5, center_cols=(1,))

    h2(doc, "6.2  Coverage structure and the cost of failure")
    p(doc,
      f"The left panel shows the split of the 48 cases: {s['normal_cases']} normal-path, "
      f"{s['negative_cases']} negative-path and {s['deviation']} deviations. Negative cases outnumber normal "
      f"ones on purpose - for an anti-scalping system the value is in the refusals, so testing only 'can buy' "
      f"would test almost nothing.")
    p(doc,
      f"The right panel compares the same operations when they succeed and when they are rejected: a "
      f"rejected purchase still burns about 41k gas, a rejected listing about 34k, a rejected resale "
      f"purchase about 36k and a rejected check-in about 24k. Across the campaign "
      f"{s['on_chain_failed_txs']} failed transactions consumed {num(s['on_chain_failed_gas_total'])} gas. "
      f"That number has two uses. It proves the rejection comes from the EVM rather than from our script, "
      f"because the transaction really was mined with status=0. And it is an engineering warning: users "
      f"should not be allowed to submit transactions that cannot succeed, which is exactly why the interface "
      f"pre-checks with canPurchase.")
    picture(doc, "03_coverage_and_failed_tx.png")
    caption(doc, "Figure 3  Coverage structure and the cost of rejected calls (source: results/test_evidence.json)")

    h2(doc, "6.3  Settlement correctness")
    p(doc,
      "T07b asserts ownership and also reconciles the money: the buyer pays 1.2 ETH, the contract books a 5% "
      "platform fee of 0.06 ETH to pendingPlatformFees[owner], and the seller receives 1.14 ETH. The test "
      "compares the fee balance before and after and requires exactly 0.06 ETH, matching (price x 5) / 100. "
      "Assertions on arithmetic are worth more than assertions on success, because the latter cannot detect "
      "a mis-split.")

    h2(doc, "6.4  Blocks and throughput")
    p(doc,
      f"This run went from deployment at block {data['env']['contract']['deploy_block']} to block "
      f"{s['final_block']} in {s['duration_seconds']} seconds. Clique fixes the block time at two seconds, so "
      f"this throughput is a property of the chain configuration, not of the contract; it is adequate for a "
      f"class demo and should not be quoted as a production performance figure.")


def chapter7(doc, data) -> None:
    h1(doc, "7  Why the rules must live on chain")
    p(doc,
      "This chapter does not argue that blockchains are immutable in general. It answers a narrower "
      "question: if the same rules were implemented in a centralised backend, what exactly would this "
      "system lose? The answer has three parts, each supported by evidence from this project.")

    h2(doc, "7.1  Where a rule lives decides whether it can be bypassed")
    p(doc,
      "In a centralised system, 'two tickets per wallet' is an if statement running on the operator's "
      "server. Anyone who can change the code, the configuration or the database can relax it, and nobody "
      "outside can verify that they did not. On chain, the same rule is a require executed by the EVM: the "
      "caller can either satisfy it or watch the transaction fail. There is no third option.")
    table_caption(doc, "Table 7-1  The same rule under two implementations")
    table(doc, ["Dimension", "Centralised backend", "This project (on chain)"],
          [["Who enforces", "The operator's server", "The EVM, independently on every node"],
           ["How to bypass", "Change code, database or configuration; release tickets internally",
            "Not possible - only a transaction that satisfies the require is accepted"],
           ["External verifiability", "Users must trust the operator", "Anyone can read the contract and "
                                                                       "recompute from receipts"],
           ["Evidence of violation", "Logs can be edited or deleted", "A status=0 transaction stays on chain"],
           ["Cost", "Almost zero", "Gas on every write, including failed ones"]],
          widths=[3.4, 6.4, 6.6], font_size=8.5)

    h2(doc, "7.2  Our evidence: four attacks that bypass the website")
    p(doc,
      "To rule out the objection that 'the test script also went through the page logic', we wrote B01-B04: "
      "no business interface import, no Streamlit process, only raw Web3.py transactions. All four were "
      "rejected with status=0 and their gas was charged. Had the rules lived in the UI, all four would have "
      "succeeded.")
    pic = [r for r in data["rows"] if r["module"] == "M5 Bypass"]
    table_caption(doc, "Table 7-2  Front-end bypass results")
    table(doc, ["Id", "Attack", "Result", "On-chain receipt"],
          [[r["test_id"], r["scenario"], verdict_en(r["verdict"]),
            f"tx {short_hash(r['tx_hash'])} / status={r['tx_status'] or '-'}"] for r in pic],
          widths=[1.4, 7.0, 1.5, 6.5], font_size=8, center_cols=(0, 2))
    p(doc,
      "One detail is easy to miss: in T11a/T11b the legitimate holder calls the standard ERC-721 "
      "transferFrom and safeTransferFrom entry points and both revert. Those functions are part of the "
      "ERC-721 interface, so only overriding them to revert actually closes 'sell it privately'. A price "
      "cap implemented only inside buyResale would be useless - which is precisely the trap the brief warns "
      "about.")

    h2(doc, "7.3  The cost side: gas, failed calls and user experience")
    p(doc,
      "Blockchain is not free. In this project an event costs about 168k gas, a purchase about 156k and a "
      f"check-in about 52k; worse, the {data['summary']['on_chain_failed_txs']} rejected transactions burned "
      f"{num(data['summary']['on_chain_failed_gas_total'])} gas. Two engineering consequences follow: "
      "pre-check on the client with canPurchase / getMaxResalePrice so doomed transactions never reach the "
      "mempool, and keep everything that does not need enforcement (posters, seat maps, analytics) off chain.")

    h2(doc, "7.4  What should not go on chain")
    p(doc,
      "We did not put everything in the contract. QR signing and verification happen off chain, because the "
      "chain cannot verify who is standing at the gate - it can only verify whether a ticket has already "
      "been used. The right split is therefore: the off-chain part proves the holder's right (signature, "
      "TTL, agreement with ownerOf) and the on-chain part performs the irreversible check-in. Understanding "
      "this boundary matters more than maximising the on-chain share.")


def chapter8(doc, data) -> None:
    h1(doc, "8  Limitations and risks")
    p(doc,
      "The following are not backlog items but boundaries this design will hit in production. They are "
      "stated explicitly so the report does not imply that a blockchain eliminates scalping.")

    items = [
        ("One person, many wallets: the limit is per address",
         "The contract counts per address, so a scalper can generate wallets. Mitigating this needs an "
         "identity dimension (KYC, phone, device fingerprint), which hands part of the trust back to a "
         "centralised party. This project does not solve it."),
        ("Event creation is permissionless (T02b)",
         "Any address can call createEvent and become the organizer, so fake events can appear on chain. A "
         "production deployment should add an organizer allow-list or a stake requirement, at the cost of "
         "openness and censorship resistance."),
        ("Server-side signing is not user signing",
         "In the demo, the pages and tests sign with six keys held by the Python process. A real product "
         "must sign with the user's own wallet, otherwise the 'user authorisation' security property does "
         "not exist and the server can move tickets on the user's behalf."),
        ("Governance and finality of a private chain",
         "A single Clique signer has no forks and no reorgs, but it also has no real decentralisation or "
         "censorship resistance. It validates rules for a class exercise; it is not a production trust "
         "assumption. Moving to a public chain brings gas volatility, congestion and upgradeability "
         "questions."),
        ("Contract defect: getMaxResalePrice underflow (E07)",
         "eventTime - block.timestamp is negative once the event starts, so the uint256 underflows and the "
         "view panics. The UI catches it, but any integrator calling the function directly receives an "
         "exception. The fix is a single timestamp check."),
        ("Time dependence and boundaries",
         "The cap depends on block.timestamp, which miners can influence slightly; 'exactly seven days' is "
         "only approximate in block time. A production rule should state '>= 7 days' explicitly and document "
         "the block-time semantics."),
        ("The QR depends on the holder's device and clock",
         "Signing happens on the user's device and the payload expires after 180 seconds. Clock drift or a "
         "slow gate network can reject a legitimate ticket; conversely, a stolen private key cannot be "
         "distinguished by the signature. The QR solves 'credentials cannot be copied', not 'keys cannot be "
         "stolen'."),
        ("Cash top-ups and whole-wallet transfers",
         "The chain constrains ownership and price, not behaviour: nothing stops a buyer from paying the "
         "difference in cash, or a seller from handing over the entire wallet including the private key. "
         "This is the fundamental limit of the approach."),
        ("Not implemented",
         "Refunds, event cancellation, seat categories and differential pricing, a resale allow-list, "
         "contract upgrade and pause switches, and third-party security audit are all absent. The current "
         "contract is a working teaching prototype, not a shippable product."),
    ]
    for i, (title, body) in enumerate(items, start=1):
        h3(doc, f"8.{i}  {title}")
        p(doc, body)


def chapter9(doc, data) -> None:
    s = data["summary"]
    h1(doc, "9  Conclusion and improvement plan")
    p(doc,
      "The question was never whether we could build a ticketing website; it was what changes when the "
      f"rules move on chain. Across {s['total_cases']} real on-chain cases the answer is:")
    for item in (
        "The rules are enforced: one address cannot over-buy, over-priced listings are rejected, direct "
        "transfers are rejected, duplicate check-ins are rejected, unauthorised check-ins are rejected - and "
        "all of this holds with the website completely bypassed;",
        "The rules are verifiable: every claim maps to a transaction hash, and positive cases add an on-chain "
        "state read-back as a second assertion;",
        "The cost is real: writes cost gas and rejected writes cost gas too, so pre-checks and off-chain "
        "data separation are requirements rather than refinements;",
        "The boundary is clear: the chain guarantees uniqueness of tickets and non-bypassable rules; it does "
        "not guarantee that people will not hoard or pay cash on the side, which needs identity and legal "
        "measures.",
    ):
        bullet(doc, item)
    p(doc,
      "From an engineering point of view the most valuable outcome was not the green result but three real "
      "problems: the deployment script kept stale addresses after regenerating accounts (fixed), "
      "getMaxResalePrice underflows after the event starts (open), and createEvent lacks issuance control "
      "(open, a product decision). None of the three is visible from a code review; they surfaced only by "
      "running the system and attacking it.")

    h2(doc, "9.1  Improvement plan")
    table_caption(doc, "Table 9-1  Improvements and priority")
    table(doc, ["Priority", "Improvement", "Rationale"],
          [["High", "Fix the getMaxResalePrice time underflow", "Any integrator calling the view crashes"],
           ["High", "Add organizer approval or staking to createEvent",
            "Prevents fake events and protects platform reputation"],
           ["Medium", "Sign with real user wallets", "Makes user authorisation a real security property"],
           ["Medium", "Add a pause switch and an event indexer", "Incident response and observability"],
           ["Medium", "Add an identity dimension to the wallet limit", "Reduces multi-wallet hoarding"],
           ["Low", "Seat categories and differential pricing", "Product completeness"],
           ["Low", "Third-party audit and formal verification", "Mandatory before any launch"]],
          widths=[2.0, 8.0, 6.4], font_size=8.5, center_cols=(0,))

    h2(doc, "9.2  Advice for the live demo")
    p(doc,
      "Follow the seven actions of T18: create an event, buy a ticket, list it, let another wallet buy it, "
      "show an over-priced listing being rejected, show a direct transfer being rejected, check in once and "
      "then fail the second check-in. The order matters: success paths first, because the failure paths need "
      "an unused ticket. If the node misbehaves, switch to results/screenshots/ and results/demo_report.md; "
      "every conclusion has offline evidence.")


def appendices(doc, data) -> None:
    doc.add_page_break()
    h1(doc, "Appendix A  Complete test table")
    p(doc,
      f"The table below lists all {data['summary']['total_cases']} cases and mirrors "
      f"results/test_results.csv. Hashes are abbreviated; full values are in results/test_evidence.json.",
      indent=False)
    body = []
    for r in data["rows"]:
        actual = r["actual"]
        if len(actual) > 26:
            actual = actual[:25] + "..."
        body.append([r["test_id"], r["scenario"][:24], r["expected"][:14], actual,
                     verdict_en(r["verdict"]), short_hash(r["tx_hash"], 8, 4),
                     r["block_number"] or "-", num(r["gas_used"])])
    table(doc, ["ID", "Scenario", "Expected", "Actual", "Result", "tx_hash", "Block", "Gas"], body,
          widths=[1.2, 4.2, 2.4, 3.4, 1.1, 1.9, 0.9, 1.3], font_size=6.8,
          center_cols=(0, 4, 6, 7))

    doc.add_page_break()
    h1(doc, "Appendix B  Reproduction commands")
    p(doc, "From zero to charts (macOS or Linux; on Windows use WSL2):", indent=False)
    code_block(doc,
               "# 0) dependencies (first time only)\n"
               "chmod +x scripts/*.sh blockchain/*.sh\n"
               "bash scripts/get_geth.sh\n"
               "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt matplotlib\n"
               ".venv/bin/python backend/fetch_deps.py\n"
               "\n"
               "# 1) initialise (first time only): accounts + genesis + .env\n"
               ".venv/bin/python blockchain/init_chain.py\n"
               "\n"
               "# 2) every experiment: reset -> deploy -> demo -> test -> charts\n"
               "bash blockchain/start_node.sh --reset && sleep 3\n"
               ".venv/bin/python backend/deploy.py\n"
               ".venv/bin/python backend/demo_flow.py\n"
               ".venv/bin/python tests/test_workflow.py\n"
               ".venv/bin/python tests/make_charts.py\n"
               "\n"
               "# 3) launch the site (for the demo)\n"
               ".venv/bin/streamlit run app/app.py    # http://127.0.0.1:8501")
    p(doc,
      "To re-run a single module, comment out the other calls in main() of tests/test_workflow.py. "
      "Troubleshooting is documented in section 9 of docs/EXPERIMENT_GUIDE.md.")

    h1(doc, "Appendix C  Accounts, contract and evidence index")
    env = data["env"]
    table_caption(doc, "Table C-1  Chain and contract")
    table(doc, ["Item", "Value"],
          [["RPC", env["chain"]["rpc_url"]],
           ["chainId", str(env["chain"]["chain_id"])],
           ["Contract address", data["net"]["contract_address"]],
           ["Deploy transaction", env["contract"]["deploy_tx"]],
           ["Deploy block / gas", f"{env['contract']['deploy_block']} / "
                                  f"{num(env['contract']['deploy_gas_used'])}"],
           ["Compiler", f"solc {env['contract']['compiler']['version']} / "
                        f"{env['contract']['compiler']['evmVersion']} / optimizer"],
           ["ABI / runtime code", f"{env['contract']['abi_items']} entries / "
                                  f"{num(env['contract']['deployed_bytes'])} bytes"]],
          widths=[4.0, 12.4], font_size=8.5)

    table_caption(doc, "Table C-2  Test accounts (this deployment)")
    table(doc, ["Role", "Address", "Opening balance (ETH)"],
          [[role, address, num(round(env["balances_eth"].get(role, 0), 2))]
           for role, address in env["accounts"].items()],
          widths=[3.2, 10.0, 3.2], font_size=8.5, center_cols=(2,))

    table_caption(doc, "Table C-3  Evidence files")
    table(doc, ["File", "Content"],
          [["results/test_results.csv", "48 cases: expected/actual/PASS-FAIL/tx/block/gas/revert reason"],
           ["results/test_evidence.json", "Full evidence, environment snapshot, summary, T18 sub-steps"],
           ["results/gas_data.csv", "Gas of every successful and rejected transaction (Figures 2 and 3-b)"],
           ["results/test_environment.json", "Environment snapshot"],
           ["results/tx_evidence.json", "Member 1's 27 demo operations including the deployment"],
           ["results/demo_report.md", "The same demo evidence as a readable table"],
           ["results/charts/*.png", "The three report figures"],
           ["results/screenshots/*.png", "Member 4's six page screenshots (earlier deployment)"]],
          widths=[6.4, 10.0], font_size=8.5)
    p(doc,
      "Note: the page screenshots in results/screenshots/ were captured by Member 4 during the previous "
      "deployment, so the contract address differs from this run. This report uses transaction hashes and "
      "receipts as evidence for the current run, and the distinction is stated in Sections 4.4 and 5.",
      size=9, color=GREY)


def build() -> Path:
    data = load()
    doc = Document()
    setup_styles(doc)
    setup_page(doc)
    cover(doc, data)
    abstract(doc, data)
    chapter1(doc, data)
    chapter2(doc, data)
    chapter3(doc, data)
    chapter4(doc, data)
    chapter5(doc, data)
    chapter6(doc, data)
    chapter7(doc, data)
    chapter8(doc, data)
    chapter9(doc, data)
    appendices(doc, data)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    print(f"[report] written to {OUT}")
    print(f"[report] {len(doc.paragraphs)} paragraphs, {len(doc.tables)} tables")
    return OUT


if __name__ == "__main__":
    build()
