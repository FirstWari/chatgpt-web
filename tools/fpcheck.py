"""Open a URL through Playwright or Patchright (connect_over_cdp), wait, save text + screenshot.

Usage: python fpcheck.py --mode playwright|patchright --url URL --out DIR [--wait 25] [--click SELECTOR]
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["playwright", "patchright"], required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--wait", type=int, default=25)
    ap.add_argument("--click", default=None, help="optional selector to click after load (e.g. turnstile box)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.mode == "patchright":
        from patchright.sync_api import sync_playwright
    else:
        from playwright.sync_api import sync_playwright
    cdp = os.environ.get("CHATGPT_CDP_URL", "http://127.0.0.1:9222")
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(cdp, timeout=15000)
        ctx = browser.contexts[0]
        page = ctx.new_page()
        t0 = time.time()
        page.goto(a.url, wait_until="domcontentloaded", timeout=60000)
        if a.click:
            try:
                page.wait_for_selector(a.click, timeout=15000)
                page.click(a.click)
            except Exception as e:  # noqa: BLE001
                print("click failed:", e)
        time.sleep(a.wait)
        text = page.inner_text("body") if page.locator("body").count() else ""
        page.screenshot(path=str(out / "shot.png"))
        (out / "page.txt").write_text(text, encoding="utf-8")
        page.close()
        browser.close()
    print(json.dumps({"mode": a.mode, "url": a.url, "outdir": str(out), "chars": len(text), "sec": round(time.time() - t0, 1)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
