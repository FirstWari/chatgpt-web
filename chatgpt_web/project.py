"""ChatGPT Projects: find the configured project in the sidebar, remember its URL, list its chats."""
from __future__ import annotations

import json
import re
import time

from .pw import Page, Error as PWError

from . import selectors as S
from .browser import Session, first
from .errors import CgError

PROJECT_URL_RE = re.compile(r"https://chatgpt\.com/g/g-p-[A-Za-z0-9-]+(?:/project)?")


def _cache_read(sess: Session) -> dict:
    try:
        return json.loads(sess.cfg.projects_file.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _cache_write(sess: Session, data: dict) -> None:
    try:
        sess.cfg.projects_file.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def cached_url(sess: Session, name: str) -> str | None:
    return _cache_read(sess).get(name)


def _open_sidebar(page: Page) -> None:
    try:
        btn = page.locator('button[aria-label="Open sidebar"]')
        if btn.count() and btn.first.is_visible():
            btn.first.click()
            time.sleep(0.8)
    except PWError:
        pass


def find_project(sess: Session, page: Page, name: str, create: bool = True) -> str:
    """Return the project page URL (…/project), navigating `page` to it. Caches the URL."""
    url = cached_url(sess, name)
    if url:
        sess.goto(page, url)
        if PROJECT_URL_RE.match(page.url):
            return _project_root(page.url)
    # discover via sidebar
    if not page.url.startswith(sess.cfg.base_url):
        sess.goto(page, sess.cfg.base_url + "/")
    _open_sidebar(page)
    opts = page.locator(S.PROJECT_OPTIONS_BUTTON.format(name=name))
    if opts.count() == 0:
        # names may carry a trailing space in aria-label (seen live: "Artificial Intelligence ")
        opts = page.locator(f'button[aria-label^="Open project options for {name}"]')
    if opts.count() > 0:
        # Row layout (2026-09): <li><div class="group/project-unfurl-row"> [link/name] [options button] </div></li>
        # Clicking the options button opens a menu, so click the left part of the row instead.
        row = opts.first.locator("xpath=ancestor::*[contains(@class,'project-unfurl-row') or self::li][1]")
        human = sess.human(page)
        clicked = False
        try:
            if row.count():
                human.click_locator(row.first, x_frac=0.25)  # left part: the name, not the options button
                clicked = True
        except PWError:
            clicked = False
        if not clicked:
            human.click_locator(page.get_by_text(name, exact=True).first)
        _wait_project_url(page, sess)
        root = _project_root(page.url)
        cache = _cache_read(sess)
        cache[name] = root
        _cache_write(sess, cache)
        return root
    if not create:
        raise CgError("PROJECT_NOT_FOUND", f"project {name!r} not in sidebar", screenshot=sess.shot(page, "project"))
    return create_project(sess, page, name)


def create_project(sess: Session, page: Page, name: str) -> str:
    btn = first(page, S.NEW_PROJECT_BUTTON)
    if not btn:
        raise CgError("PROJECT_NOT_FOUND", "no 'New project' button", screenshot=sess.shot(page, "project"))
    human = sess.human(page)
    human.click_locator(btn)
    try:
        # The "Create project" dialog is not always role=dialog; take the newest visible text input.
        page.get_by_text(re.compile(r"^(Create project|Proje oluştur)$")).first.wait_for(timeout=10000)
        box = page.locator("input:visible").last
        box.wait_for(timeout=10000)
        human.click_locator(box)
        human.type_text(name)
        create = page.get_by_role("button", name=re.compile(r"^(Create project|Proje oluştur|Create)$")).first
        create.wait_for(state="visible", timeout=5000)
        human.click_locator(create)
        _wait_project_url(page, sess)
    except PWError as e:
        raise CgError("PROJECT_NOT_FOUND", f"could not create project {name!r}: {e}", screenshot=sess.shot(page, "project"))
    root = _project_root(page.url)
    cache = _cache_read(sess)
    cache[name] = root
    _cache_write(sess, cache)
    return root


def _wait_project_url(page: Page, sess: Session | None = None, timeout: float = 15.0) -> None:
    """Wait until `page` shows a project URL. If ChatGPT opened the project in another tab
    (seen after 'Create project'), adopt that URL in `page` and close the extra tab."""
    end = time.time() + timeout
    while time.time() < end:
        if PROJECT_URL_RE.match(page.url):
            return
        if sess is not None:
            for other in sess.ctx.pages:
                if other is not page and PROJECT_URL_RE.match(other.url):
                    url = _project_root(other.url)
                    try:
                        other.close()
                    except PWError:
                        pass
                    sess.goto(page, url)
                    return
        time.sleep(0.3)
    raise CgError("PROJECT_NOT_FOUND", f"project page did not open (url={page.url})")


def _project_root(url: str) -> str:
    m = PROJECT_URL_RE.match(url)
    base = m.group(0) if m else url
    return base if base.endswith("/project") else base + "/project"


def list_chats(sess: Session, page: Page, project_url: str, query: str | None, limit: int) -> list[dict]:
    if _project_root(page.url) != project_url:
        sess.goto(page, project_url)
    time.sleep(1.5)
    seen: dict[str, str] = {}
    pid = re.search(r"g-p-([A-Za-z0-9]+)", project_url)
    pid = pid.group(1) if pid else ""
    # Project chats are listed in <main> with project-scoped hrefs (/g/g-p-<id>-<slug>/c/<uuid>);
    # the sidebar (nav/aside) lists *all* chats, so it is excluded.
    candidates = page.locator(f"main a[href*='g-p-{pid}'][href*='/c/']").all() if pid else []
    if not candidates:
        candidates = page.locator("main a[href*='/c/']").all()
    for a in candidates:
        try:
            href = a.get_attribute("href") or ""
            title = (a.inner_text() or "").strip().split("\n")[0]
        except PWError:
            continue
        if href and href not in seen:
            seen[href] = title
    out = [{"title": t, "url": sess.cfg.base_url + h} for h, t in seen.items()]
    if query:
        q = query.lower()
        out = [c for c in out if q in c["title"].lower()]
    return out[:limit]
