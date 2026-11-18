"""Take full-page screenshots of the Streamlit pages via the Chrome DevTools Protocol.

!! Marked as legacy; no longer maintained:
   - the CHROME path inside is macOS-only;
   - the page routes and Chinese button labels date from the interface-localisation period,
     the UI is English now, so the click sequences will not match;
   - the 6 delivered screenshots were captured by hand (steps in docs/DEMO_SCRIPT.md).
Kept for traceability only; the team can rework it if needed.

Why CDP: `chrome --screenshot` captures right after the load event, while Streamlit is a
websocket-driven, client-rendered app, so what you get is the skeleton screen. Here we
explicitly wait for the page to finish rendering, and we can also click buttons from the
script (generate the QR code, jump to the verification page, run the check), capturing the
interaction results as well.

Usage:
    .venv/bin/python scripts/capture_screenshots.py            # all pages
    .venv/bin/python scripts/capture_screenshots.py --only 04  # capture a single page
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import time
import urllib.parse
from pathlib import Path

import requests
import websocket

ROOT = Path(__file__).resolve().parents[1]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9333
OUT = ROOT / "results" / "screenshots"

# (file name, start route, click sequence)
SHOTS = [
    ("01_overview", "/", []),
    ("02_activity_management", "/activity", []),
    ("03_ticket_purchase", "/buy?account=buyerB", ["Buy now"]),
    ("04_my_tickets", "/my_tickets?account=buyerA", ["Generate signed QR code"]),
    ("05_resale_market", "/resale", []),
    ("06_staff_verification", "/my_tickets?account=buyerB", ["Generate signed QR code", "Send to verification page", "Verify ticket stub", "First redemption"]),
]


class CDP:
    def __init__(self, ws_url: str) -> None:
        # Chrome rejects a CDP handshake that carries an Origin header, so suppress_origin is required
        self.ws = websocket.create_connection(ws_url, timeout=90, suppress_origin=True)
        self.seq = 0

    def call(self, method: str, **params):
        self.seq += 1
        self.ws.send(json.dumps({"id": self.seq, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.seq:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def eval_js(self, expression: str):
        res = self.call("Runtime.evaluate", expression=expression, returnByValue=True)
        return res.get("result", {}).get("value")

    def ready(self, timeout: float = 45) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            ok = self.eval_js(
                "(() => { const t = document.body ? document.body.innerText : '';"
                " return t.length > 300 && !!document.querySelector('[data-testid=\"stAppViewContainer\"]'); })()"
            )
            if ok:
                return True
            time.sleep(0.5)
        return False

    def click(self, text: str, timeout: float = 30) -> bool:
        expr = (
            "(() => { const btns=[...document.querySelectorAll('button')];"
            f" const b=btns.find(x=>x.innerText.replace(/\\s/g,'').includes({json.dumps(text.replace(' ', ''))}));"
            " if(!b) return false; b.click(); return true; })()"
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.eval_js(expr):
                return True
            time.sleep(0.5)
        return False


def start_chrome() -> subprocess.Popen:
    subprocess.run(["pkill", "-f", f"remote-debugging-port={PORT}"], capture_output=True)
    time.sleep(0.5)
    proc = subprocess.Popen(
        [
            CHROME,
            "--headless=new",
            f"--remote-debugging-port={PORT}",
            "--user-data-dir=/tmp/chrome-shot",
            "--no-sandbox",
            "--remote-allow-origins=*",
            "--disable-gpu",
            "--disable-crash-reporter",
            "--disable-breakpad",
            "--crash-dumps-dir=/tmp/chrome-shot/crash",
            "--hide-scrollbars",
            "--no-first-run",
            "--window-size=1440,1000",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        try:
            requests.get(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
            return proc
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    raise RuntimeError("the Chrome debugging port did not come up")


def new_tab() -> str:
    resp = requests.put(f"http://127.0.0.1:{PORT}/json/new?about:blank", timeout=10)
    return resp.json()["webSocketDebuggerUrl"]


def page_height(cdp: CDP) -> int:
    h = cdp.eval_js(
        "(() => { const sels=['[data-testid=\"stMain\"]','section.main',"
        "'[data-testid=\"stAppViewContainer\"]','body']; let h=0;"
        "for (const s of sels){const el=document.querySelector(s); if(el) h=Math.max(h, el.scrollHeight);}"
        "return Math.max(h, document.documentElement.scrollHeight, 900); })()"
    )
    return min(int(h or 1000) + 60, 6000)


def shoot(cdp: CDP, base: str, name: str, route: str, clicks: list[str]) -> None:
    url = base + route
    cdp.call("Page.enable")
    cdp.call("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=2, mobile=False)
    cdp.call("Page.navigate", url=url)
    cdp.ready()

    for text in clicks:
        if not cdp.click(text):
            print(f"[shot] warning: button \"{text}\" not found")
        time.sleep(4.5)  # wait for the Streamlit rerun + the on-chain transaction receipt
        cdp.ready(timeout=30)

    time.sleep(2)
    height = page_height(cdp)
    cdp.call("Emulation.setDeviceMetricsOverride", width=1440, height=height, deviceScaleFactor=2, mobile=False)
    cdp.eval_js("window.scrollTo(0,0)")
    time.sleep(1.2)

    shot = cdp.call("Page.captureScreenshot", format="png", captureBeyondViewport=False)
    out = OUT / f"{name}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(shot["data"]))
    print(f"[shot] {out.relative_to(ROOT)}  (1440x{height})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8501")
    ap.add_argument("--only", default="", help="capture only one page, e.g. 04")
    args = ap.parse_args()

    proc = start_chrome()
    try:
        for name, route, clicks in SHOTS:
            if args.only and args.only not in name:
                continue
            cdp = CDP(new_tab())
            try:
                shoot(cdp, args.base, name, route, clicks)
            finally:
                cdp.ws.close()
    finally:
        proc.terminate()
        subprocess.run(["pkill", "-f", f"remote-debugging-port={PORT}"], capture_output=True)


if __name__ == "__main__":
    main()
