"""Mobile audit: every page at phone size via headless Chrome (DevTools Protocol).

For each URL it emulates a 390x844 phone and reports:
  - horizontal overflow (page wider than the screen) and the elements causing it
  - text smaller than 13px, and tap targets smaller than 40px tall
  - inputs with font-size < 16px (iOS zooms the page when they're focused)
and saves a tiled full-page screenshot to tmp/shots/mobile/<slug>.png
(the long page cut into side-by-side columns so it is readable at a glance).

  python scripts/mobile-audit.py [--base https://example.org] [--paths / /visit/ ...] [--chat]
With no --paths it audits every URL in the WordPress sitemap (pages, posts, a few sermons).
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket
from PIL import Image

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
]
OUT = Path(__file__).resolve().parents[1] / "tmp" / "shots" / "mobile"
W, H = 390, 844

PROBE = r"""(() => {
  const vw = window.innerWidth, out = [], small = new Set(), taps = [], zoom = [];
  const name = (el) => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
    [...el.classList].slice(0, 3).map(c => '.' + c).join('');
  const clipped = (el) => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const s = getComputedStyle(p); if (/(hidden|clip|auto|scroll)/.test(s.overflowX)) return true; } return false; };
  for (const el of document.body.querySelectorAll('*')) {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    if (!r.width || s.visibility === 'hidden' || s.display === 'none' || s.position === 'fixed') continue;
    if ((r.right > vw + 1 || r.left < -1) && !clipped(el)) out.push(`${name(el)} [${Math.round(r.left)}..${Math.round(r.right)}]`);
    const direct = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (direct && parseFloat(s.fontSize) < 13 && !el.closest('.screen-reader-text')) small.add(`${name(el)} ${s.fontSize}`);
    if (el.matches('a, button, input, select, textarea, summary') && r.height < 40 && r.height > 0 &&
        !el.closest('p, li, .wp-block-post-excerpt, .asc-footer-legal, .asc-sermon-body, .entry-content, td') )
      taps.push(`${name(el)} ${Math.round(r.width)}x${Math.round(r.height)} "${(el.innerText || el.value || '').trim().slice(0, 25)}"`);
    if (el.matches('input, select, textarea') && parseFloat(s.fontSize) < 16) zoom.push(`${name(el)} ${s.fontSize}`);
  }
  return { overflow: document.documentElement.scrollWidth - vw, height: document.documentElement.scrollHeight,
           offenders: [...new Set(out)].slice(0, 12), small: [...small].slice(0, 10), taps: [...new Set(taps)].slice(0, 10), zoom };
})()"""


class CDP:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=60, suppress_origin=True)
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

    def wait_for(self, expression: str, timeout: float = 20) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            if self.js(expression):
                return True
            time.sleep(0.25)
        return False


def tiled(png: bytes, col_h: int = 1400) -> Image.Image:
    """Cut a tall phone screenshot into side-by-side columns."""
    img = Image.open(io.BytesIO(png)).convert("RGB")
    cols = max(1, -(-img.height // col_h))
    sheet = Image.new("RGB", (cols * (img.width + 12) - 12, min(col_h, img.height)), (60, 60, 60))
    for i in range(cols):
        sheet.paste(img.crop((0, i * col_h, img.width, min(img.height, (i + 1) * col_h))), (i * (img.width + 12), 0))
    return sheet


def capture(cdp: CDP, name: str, max_h: int = 9800) -> None:
    height = min(int(cdp.js("document.documentElement.scrollHeight")), max_h)
    data = cdp.send("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                    clip={"x": 0, "y": 0, "width": W, "height": height, "scale": 1})["data"]
    OUT.mkdir(parents=True, exist_ok=True)
    tiled(base64.b64decode(data)).save(OUT / f"{name}.png")


def slug(path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-") or "home"


def sitemap_paths(base: str) -> list[str]:
    paths = []
    for kind, limit in (("page", 100), ("post", 3), ("sermon", 2)):
        xml = urllib.request.urlopen(f"{base}/wp-sitemap-posts-{kind}-1.xml").read().decode()
        paths += [u.replace(base, "") for u in re.findall(r"<loc>([^<]+)</loc>", xml)][:limit]
    return paths + ["/sermons/"]


def audit(cdp: CDP, base: str, path: str, shots: bool) -> dict:
    cdp.send("Page.navigate", url=base + path)
    time.sleep(0.5)
    cdp.wait_for("document.readyState === 'complete'")
    # Scroll through so lazy images load, then back to the top.
    cdp.js("(async () => { for (let y = 0; y < document.body.scrollHeight; y += 700) { scrollTo(0, y); await new Promise(r => setTimeout(r, 60)); } scrollTo(0, 0); })()")
    time.sleep(0.6)
    result = cdp.js(PROBE) or {}
    if shots:
        capture(cdp, slug(path))
    return result


def menu_check(cdp: CDP, base: str) -> None:
    """Open the mobile navigation overlay (and its first submenu) and screenshot it."""
    cdp.send("Page.navigate", url=base + "/")
    cdp.wait_for("document.readyState === 'complete'")
    cdp.js("document.querySelector('.wp-block-navigation__responsive-container-open').click()")
    time.sleep(0.6)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "menu-open.png").write_bytes(base64.b64decode(cdp.send("Page.captureScreenshot", format="png")["data"]))
    print("menu:", cdp.js(PROBE))


def chat_check(cdp: CDP, base: str) -> None:
    cdp.send("Page.navigate", url=base + "/")
    cdp.wait_for("document.readyState === 'complete' && !document.querySelector('.asc-chat__launcher').hidden")
    cdp.js("sessionStorage.clear(); document.querySelector('.asc-chat__launcher').click()")
    time.sleep(0.4)
    data = cdp.send("Page.captureScreenshot", format="png")["data"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "chat-open.png").write_bytes(base64.b64decode(data))
    cdp.js("(() => { const i = document.getElementById('asc-chat-input'); i.value = \"I'm bringing my kids on Sunday for the first time. What should we know?\"; i.closest('form').requestSubmit(); })()")
    cdp.wait_for("!document.querySelector('.asc-chat__send').disabled && document.querySelectorAll('.asc-chat__msg--bot').length > 1", 60)
    time.sleep(0.3)
    data = cdp.send("Page.captureScreenshot", format="png")["data"]
    (OUT / "chat-answer.png").write_bytes(base64.b64decode(data))
    print("chat:", cdp.js(PROBE))


def main() -> int:
    global W
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://100-52-175-44.sslip.io")
    ap.add_argument("--paths", nargs="*")
    ap.add_argument("--no-shots", action="store_true")
    ap.add_argument("--width", type=int, default=W, help="viewport width (390 phone, 768 tablet)")
    ap.add_argument("--eval", help="JavaScript to run on each page (printed instead of the audit)")
    ap.add_argument("--chat", action="store_true", help="also open the mobile menu, then the assistant, and ask a question")
    args = ap.parse_args()
    W = args.width
    base = args.base.rstrip("/")
    paths = args.paths or sitemap_paths(base)

    chrome = next(p for p in CHROME_PATHS if os.path.exists(p))
    profile = tempfile.mkdtemp(prefix="asc-mobile-")
    proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--remote-debugging-port=9334",
                             f"--user-data-dir={profile}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    problems = 0
    try:
        for _ in range(40):
            try:
                page = next(t for t in json.load(urllib.request.urlopen("http://127.0.0.1:9334/json")) if t["type"] == "page")
                break
            except Exception:  # noqa: BLE001 - Chrome still starting
                time.sleep(0.25)
        cdp = CDP(page["webSocketDebuggerUrl"])
        cdp.send("Page.enable")
        cdp.send("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1, mobile=True)
        cdp.send("Emulation.setTouchEmulationEnabled", enabled=True)
        cdp.send("Emulation.setUserAgentOverride", userAgent="Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")
        # Reduced motion: scroll-reveal content is fully visible in the screenshots.
        cdp.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
        for path in paths:
            if args.eval:
                cdp.send("Page.navigate", url=base + path)
                time.sleep(0.5)
                cdp.wait_for("document.readyState === 'complete'")
                print(path, json.dumps(cdp.js(args.eval), indent=1))
                continue
            r = audit(cdp, base, path, not args.no_shots)
            bad = r.get("overflow", 0) > 1 or r.get("offenders") or r.get("zoom")
            problems += bool(bad)
            print(f"{'✘' if bad else '✔'} {path}  overflow={r.get('overflow')}px height={r.get('height')}")
            for key in ("offenders", "small", "taps", "zoom"):
                if r.get(key):
                    print(f"    {key}: " + " | ".join(r[key]))
        if args.chat:
            menu_check(cdp, base)
            chat_check(cdp, base)
    finally:
        proc.terminate()
    print(f"\n{len(paths)} pages, {problems} with layout problems. Screenshots: {OUT}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
