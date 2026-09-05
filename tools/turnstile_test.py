"""Interactive Cloudflare Turnstile demo: click the checkbox inside the challenge iframe with the humanize engine.

Usage: python turnstile_test.py [--url https://nopecha.com/demo/turnstile] [--out DIR]
Success = page text / iframe shows 'Success' or a token appears in [name=cf-turnstile-response].
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chatgpt_web.humanize import Human  # noqa: E402
from chatgpt_web.pw import sync_playwright  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://nopecha.com/demo/turnstile")
    ap.add_argument("--out", default="debug/fp/turnstile-human")
    ap.add_argument("--wait", type=int, default=20)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cdp = os.environ.get("CHATGPT_CDP_URL", "http://127.0.0.1:9222")
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(cdp, timeout=15000)
        page = browser.contexts[0].new_page()
        page.goto(a.url, wait_until="domcontentloaded", timeout=60000)
        human = Human(page, out)
        human.think(1500, 0.3)
        # Turnstile renders its iframe inside a *closed* shadow root, so target the host container.
        frame_el = page.locator('iframe[title*="Cloudflare security challenge"], iframe[src*="challenges.cloudflare.com"]').first
        result = {"clicked": False, "token": None, "text": "", "note": ""}
        try:
            frame_el.wait_for(state="attached", timeout=20000)  # aria-hidden makes it "hidden" for Playwright
            time.sleep(2.5)  # let the widget decide between managed/interactive
            # The visible widget lives in a closed shadow root; measure its host element instead
            # (Patchright runs evaluate in an isolated world, so this is not observable by the page).
            box = page.evaluate("""() => {
                const host = document.querySelector('.cf-turnstile, [data-sitekey], #cf-turnstile, [id^=cf-turnstile]');
                const el = host || document.querySelector('iframe[title*="Cloudflare"]');
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {x: r.x, y: r.y, width: r.width, height: r.height, tag: el.tagName, id: el.id, cls: el.className};
            }""")
            result["note"] = f"host box={box}"
            if box and box["width"] < 50:
                box = None
            if box:
                # checkbox sits at the left edge of the widget (~28px from left, vertically centred)
                x = box["x"] + 28 + human.rng.uniform(-3, 3)
                y = box["y"] + box["height"] / 2 + human.rng.uniform(-3, 3)
                human.move_to(x, y, width=24)
                time.sleep(human.rng.uniform(0.05, 0.15))
                page.mouse.down()
                time.sleep(0.09)
                page.mouse.up()
                result["clicked"] = True
        except Exception as e:  # noqa: BLE001
            result["note"] = f"container wait failed: {e}"
        deadline = time.time() + a.wait
        while time.time() < deadline:
            try:
                tok = page.locator('[name="cf-turnstile-response"]').first
                if tok.count():
                    v = tok.input_value()
                    if v:
                        result["token"] = v[:24] + "..."
                        break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1)
        page.screenshot(path=str(out / "shot.png"))
        try:
            result["text"] = (page.inner_text("body") or "")[:300]
        except Exception:  # noqa: BLE001
            pass
        page.close()
        browser.close()
    print(result)
    return 0 if result["token"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
