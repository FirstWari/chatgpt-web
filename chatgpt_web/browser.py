"""Connect to the already-running, logged-in Chromium over CDP and classify pages.

One `Session` per tool call: connect, do the work, disconnect. Chromium keeps the
tabs, so state survives across calls and across processes (MCP server, CLI).
"""
from __future__ import annotations

import re
import time
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Page, BrowserContext, sync_playwright, Error as PWError

from . import selectors as S
from .config import Config
from .errors import CgError


def first(page: Page, sels: list[str]):
    """First locator in the fallback list that exists on the page (count>0), else None."""
    for s in sels:
        try:
            loc = page.locator(s)
            if loc.count() > 0:
                return loc.first
        except PWError:
            continue
    return None


def visible(page: Page, sels: list[str]) -> bool:
    loc = first(page, sels)
    try:
        return bool(loc and loc.is_visible())
    except PWError:
        return False


class Session:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._pw = None
        self.browser = None
        self.ctx: BrowserContext | None = None

    def __enter__(self) -> "Session":
        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.connect_over_cdp(self.cfg.cdp_url, timeout=15000)
        except Exception as e:  # noqa: BLE001
            self._pw.stop()
            raise CgError("CDP_UNREACHABLE", f"connect_over_cdp({self.cfg.cdp_url}) failed: {e}")
        if not self.browser.contexts:
            self.close()
            raise CgError("CDP_UNREACHABLE", "browser has no contexts")
        self.ctx = self.browser.contexts[0]
        self.ctx.set_default_timeout(15000)
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        try:
            if self.browser:
                self.browser.close()  # only disconnects from CDP; Chromium keeps running
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:  # noqa: BLE001
            pass

    # ---- tabs -----------------------------------------------------------
    def chatgpt_pages(self) -> list[Page]:
        return [p for p in self.ctx.pages if p.url.startswith(self.cfg.base_url)]

    def target_id(self, page: Page) -> str:
        cdp = self.ctx.new_cdp_session(page)
        try:
            return cdp.send("Target.getTargetInfo")["targetInfo"]["targetId"]
        finally:
            cdp.detach()

    def page_for_handle(self, handle: str) -> Page:
        """handle = conversation URL (https://chatgpt.com/c/<id>) or 'tab:<targetId>'."""
        if handle.startswith("tab:"):
            tid = handle[4:]
            for p in self.ctx.pages:
                try:
                    if self.target_id(p) == tid:
                        return p
                except Exception:  # noqa: BLE001
                    continue
            raise CgError("CHAT_NOT_FOUND", f"no open tab {handle}; open the conversation URL with open_chat")
        url = handle.split("#")[0].rstrip("/")
        if not url.startswith(self.cfg.base_url):
            raise CgError("INPUT", f"handle must be a {self.cfg.base_url} URL or tab:<id>, got {handle!r}")
        for p in self.ctx.pages:
            if p.url.split("?")[0].rstrip("/") == url:
                return p
        page = self.new_page()
        self.goto(page, url)
        return page

    def new_page(self) -> Page:
        page = self.ctx.new_page()
        page.set_default_timeout(15000)
        try:
            page.set_viewport_size({"width": 1400, "height": 1000})
        except PWError:
            pass
        return page

    def goto(self, page: Page, url: str):
        page.goto(url, wait_until="domcontentloaded", timeout=self.cfg.nav_timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PWError:
            pass
        self.ensure_usable(page)

    # ---- classification --------------------------------------------------
    def classify(self, page: Page) -> str:
        """logged_in | anonymous | login_required | cloudflare | rate_limited | unknown"""
        url = page.url
        title = ""
        try:
            title = page.title()
        except PWError:
            pass
        if "auth.openai.com" in url or "/auth/" in url or "login" in url.split("?")[0].split("/")[-1]:
            return "login_required"
        if "Just a moment" in title or visible(page, S.CLOUDFLARE_IFRAME):
            return "cloudflare"
        has_prompt = visible(page, S.PROMPT_BOX)
        has_login = visible(page, S.LOGIN_BUTTON)
        has_profile = first(page, S.PROFILE_BUTTON) is not None
        if has_prompt and has_profile:
            return "logged_in"
        if has_prompt and has_login:
            return "anonymous"
        if has_login and not has_prompt:
            return "login_required"
        if has_prompt:
            return "logged_in"
        return "unknown"

    def rate_limited(self, page: Page) -> bool:
        try:
            txt = page.locator('[role="dialog"], [role="alert"], [data-testid*="toast"]').all_inner_texts()
        except PWError:
            return False
        return any(re.search(S.RATE_LIMIT_RE, t, re.I) for t in txt)

    def ensure_usable(self, page: Page):
        """Raise the right CgError unless the page is a usable, logged-in chat page."""
        state = self.classify(page)
        if state == "cloudflare":
            for _ in range(9):
                time.sleep(5)
                if self.classify(page) != "cloudflare":
                    break
            else:
                raise CgError("BOT_CHECK", "Cloudflare challenge did not clear", screenshot=self.shot(page, "botcheck"))
            state = self.classify(page)
        if state == "unknown":
            # SPA still hydrating: give it a moment
            try:
                page.wait_for_selector(S.PROMPT_BOX[0], timeout=15000)
            except PWError:
                pass
            state = self.classify(page)
        if state in ("login_required", "anonymous"):
            raise CgError("SESSION_LOST", f"chatgpt.com session state: {state}", screenshot=self.shot(page, "session"))
        if self.rate_limited(page):
            raise CgError("RATE_LIMIT", "ChatGPT reports a usage limit", screenshot=self.shot(page, "ratelimit"))
        return state

    # ---- debugging -------------------------------------------------------
    def shot(self, page: Page, tag: str) -> str | None:
        try:
            p = Path(self.cfg.debug_dir) / f"{time.strftime('%Y%m%d-%H%M%S')}-{tag}.png"
            page.screenshot(path=str(p), full_page=False)
            return str(p)
        except Exception:  # noqa: BLE001
            return None
