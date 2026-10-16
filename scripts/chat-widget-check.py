"""Browser check for the chatbot widget (vanilla JS) via the Chrome DevTools Protocol.

Opens the site in headless Chrome at phone and desktop sizes, opens the assistant,
asks a question, waits for the answer, checks keyboard behaviour (Escape closes,
focus returns), and saves screenshots to tmp/shots/.

  python scripts/chat-widget-check.py [--url http://allsaints.ddev.site/]
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]
OUT = Path(__file__).resolve().parents[1] / "tmp" / "shots"


class CDP:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
        self.n = 0

    def send(self, method: str, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def js(self, expression: str):
        res = self.send("Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True)
        return res.get("result", {}).get("value")

    def wait_for(self, expression: str, timeout: float = 20):
        end = time.time() + timeout
        while time.time() < end:
            if self.js(expression):
                return True
            time.sleep(0.25)
        return False

    def shot(self, name: str):
        data = self.send("Page.captureScreenshot", format="png")["data"]
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / name).write_bytes(base64.b64decode(data))


def run(cdp: CDP, url: str, width: int, height: int, mobile: bool, label: str) -> list[str]:
    failures = []
    cdp.send("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=mobile)
    cdp.send("Page.navigate", url=url)
    cdp.wait_for("document.readyState === 'complete'")
    cdp.wait_for("!document.querySelector('.asc-chat__launcher').hidden")

    overflow = cdp.js("document.documentElement.scrollWidth - window.innerWidth")
    if overflow and overflow > 1:
        failures.append(f"{label}: page overflows horizontally by {overflow}px")

    cdp.js("document.querySelector('.asc-chat__launcher').click()")
    if not cdp.wait_for("!document.querySelector('.asc-chat__panel').hidden && document.activeElement.id === 'asc-chat-input'"):
        failures.append(f"{label}: panel did not open with focus in the input")
    cdp.js("""(() => { const i = document.getElementById('asc-chat-input'); i.value = 'What time is Sunday worship?';
              i.closest('form').requestSubmit(); })()""")
    if not cdp.wait_for("document.querySelectorAll('.asc-chat__msg--bot').length >= 2 && !document.querySelector('.asc-chat__typing')"):
        failures.append(f"{label}: no answer rendered")
    answer = cdp.js("[...document.querySelectorAll('.asc-chat__msg--bot')].pop().innerText") or ""
    if "8:15" not in answer:
        failures.append(f"{label}: answer missing service time: {answer[:120]!r}")
    if not cdp.js("!!document.querySelector('.asc-chat__sources a')"):
        failures.append(f"{label}: no source links rendered")
    cdp.shot(f"chat-{label}.png")

    cdp.js("document.querySelector('.asc-chat__panel').dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
    if not cdp.wait_for("document.querySelector('.asc-chat__panel').hidden && document.activeElement.classList.contains('asc-chat__launcher')", 3):
        failures.append(f"{label}: Escape did not close the panel and restore focus")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://allsaints.ddev.site/")
    args = ap.parse_args()
    chrome = next((p for p in CHROME_PATHS if os.path.exists(p)), None)
    if not chrome:
        print("Chrome/Edge not found")
        return 2
    profile = tempfile.mkdtemp(prefix="asc-cdp-")
    proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--remote-debugging-port=9333",
                             f"--user-data-dir={profile}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json"))
                page = next(t for t in tabs if t["type"] == "page")
                break
            except Exception:  # noqa: BLE001 - Chrome still starting
                time.sleep(0.25)
        cdp = CDP(page["webSocketDebuggerUrl"])
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        failures = run(cdp, args.url, 390, 844, True, "phone") + run(cdp, args.url, 1280, 900, False, "desktop")
    finally:
        proc.terminate()
    for f in failures:
        print("✘", f)
    print("✔ chatbot widget OK (phone + desktop)" if not failures else f"{len(failures)} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
