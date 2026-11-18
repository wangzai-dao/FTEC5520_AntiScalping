"""用 Chrome DevTools Protocol 给 Streamlit 页面拍全页截图。

!! 已标注为遗留脚本（legacy），不再维护：
   - 其中的 CHROME 路径是 macOS 专用；
   - 页面路由与中文按钮文本写于界面汉化时期，现已改为英文界面，点击序列会对不上；
   - 交付的 6 张截图是手工截取的（步骤见 docs/DEMO_SCRIPT.md）。
保留本文件仅供追溯，组内如需要可自行改造。

为什么要 CDP：`chrome --screenshot` 在 load 事件后立刻截图，而 Streamlit 是
websocket 驱动的客户端渲染，截到的是骨架屏。这里显式等待页面渲染完成，
并且可以按脚本点击按钮（生成二维码、跳转验票页、执行核验），把交互结果一起拍下来。

用法:
    .venv/bin/python scripts/capture_screenshots.py            # 全部页面
    .venv/bin/python scripts/capture_screenshots.py --only 04  # 只拍某一页
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

# (文件名, 起始路由, 点击序列)
SHOTS = [
    ("01_总览", "/", []),
    ("02_活动管理", "/activity", []),
    ("03_购票", "/buy?account=buyerB", ["立即购买"]),
    ("04_我的门票", "/my_tickets?account=buyerA", ["生成签名二维码"]),
    ("05_二手市场", "/resale", []),
    ("06_工作人员验票", "/my_tickets?account=buyerB", ["生成签名二维码", "送验票页", "验证票根", "首次核销"]),
]


class CDP:
    def __init__(self, ws_url: str) -> None:
        # Chrome 会拒绝带 Origin 头的 CDP 握手，必须 suppress_origin
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
    raise RuntimeError("Chrome 调试端口没起来")


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
            print(f"[shot] 警告：没找到按钮「{text}」")
        time.sleep(4.5)  # 等 Streamlit rerun + 链上交易回执
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
    ap.add_argument("--only", default="", help="只截某个页面，如 04")
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
