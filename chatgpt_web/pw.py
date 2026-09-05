"""Playwright import shim: prefer Patchright (no Runtime.enable leak), fall back to Playwright."""
try:
    from patchright.sync_api import sync_playwright, Page, BrowserContext, Error  # type: ignore
    ENGINE = "patchright"
except ImportError:  # pragma: no cover
    from playwright.sync_api import sync_playwright, Page, BrowserContext, Error  # type: ignore
    ENGINE = "playwright"

__all__ = ["sync_playwright", "Page", "BrowserContext", "Error", "ENGINE"]
