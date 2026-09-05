"""Diagnostic: list elements whose bounding box matches a size range (find widgets in shadow roots)."""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chatgpt_web.pw import sync_playwright
url = sys.argv[1]
with sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp(os.environ.get("CHATGPT_CDP_URL", "http://127.0.0.1:9222"))
    page = b.contexts[0].new_page(); page.goto(url, wait_until="domcontentloaded"); time.sleep(6)
    res = page.evaluate("""() => {
      const out = [];
      const walk = (root) => {
        for (const el of root.querySelectorAll('*')) {
          const r = el.getBoundingClientRect();
          if (r.width >= 200 && r.width <= 400 && r.height >= 50 && r.height <= 90)
            out.push({tag: el.tagName, id: el.id, cls: String(el.className).slice(0,60), x: r.x, y: r.y, w: r.width, h: r.height, shadow: !!el.shadowRoot});
          if (el.shadowRoot) walk(el.shadowRoot);
        }
      };
      walk(document);
      return out.slice(0, 20);
    }""")
    print(json.dumps(res, indent=0)); page.close(); b.close()
