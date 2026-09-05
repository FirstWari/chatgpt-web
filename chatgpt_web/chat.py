"""Drive one conversation page: model, attachments, send, wait, read turns."""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

from playwright.sync_api import Page, Error as PWError

from . import selectors as S
from .browser import Session, first, visible
from .errors import CgError
from .extract import Block, blocks_from_text


# ---- model ---------------------------------------------------------------
def current_model_label(page: Page) -> str:
    loc = first(page, S.MODEL_SWITCHER)
    if not loc:
        return ""
    try:
        return (loc.inner_text() or "").strip().replace("\n", " ")
    except PWError:
        return ""


def ensure_model(sess: Session, page: Page, slug: str, label: str, strict: bool) -> dict:
    """Make the picker show `label`. Returns {model_label, model_ok, model_note}."""
    if not label and not slug:
        return {"model_label": current_model_label(page), "model_ok": None, "model_note": "no model configured"}
    want = (label or slug).lower()
    cur = current_model_label(page)
    if cur and want in cur.lower():
        return {"model_label": cur, "model_ok": True, "model_note": ""}
    note = []
    if slug and "/c/" not in page.url:
        sep = "&" if "?" in page.url else "?"
        try:
            sess.goto(page, page.url.split("#")[0] + f"{sep}model={slug}")
            cur = current_model_label(page)
            if cur and want in cur.lower():
                return {"model_label": cur, "model_ok": True, "model_note": "selected via ?model="}
            note.append(f"?model={slug} gave {cur!r}")
        except CgError:
            raise
        except Exception as e:  # noqa: BLE001
            note.append(f"?model= nav failed: {e}")
    picker = first(page, S.MODEL_SWITCHER)
    if picker:
        try:
            picker.click()
            page.wait_for_selector('[role="menu"], [role="listbox"]', timeout=8000)
            items = page.get_by_role("menuitem")
            target = items.filter(has_text=re.compile(re.escape(label or slug), re.I))
            if target.count() == 0:
                more = items.filter(has_text=re.compile(r"more models|legacy|diğer modeller|other models", re.I))
                if more.count():
                    more.first.hover()
                    more.first.click()
                    time.sleep(0.8)
                    target = page.get_by_role("menuitem").filter(has_text=re.compile(re.escape(label or slug), re.I))
            if target.count():
                target.first.click()
                time.sleep(1.0)
                cur = current_model_label(page)
                if cur and want in cur.lower():
                    return {"model_label": cur, "model_ok": True, "model_note": "selected via picker"}
            else:
                page.keyboard.press("Escape")
            note.append(f"picker has no item matching {label or slug!r}")
        except PWError as e:
            note.append(f"picker failed: {e}")
            try:
                page.keyboard.press("Escape")
            except PWError:
                pass
    else:
        note.append("no model picker on this page (free plan?)")
    res = {"model_label": cur, "model_ok": False, "model_note": "; ".join(note)}
    if strict:
        raise CgError("MODEL_MISMATCH", res["model_note"], model_label=cur, screenshot=sess.shot(page, "model"))
    return res


def list_models(page: Page) -> list[str]:
    picker = first(page, S.MODEL_SWITCHER)
    if not picker:
        return []
    names: list[str] = []
    try:
        picker.click()
        page.wait_for_selector('[role="menu"], [role="listbox"]', timeout=8000)
        for it in page.get_by_role("menuitem").all():
            t = (it.inner_text() or "").strip().replace("\n", " · ")
            if t:
                names.append(t)
    except PWError:
        pass
    finally:
        try:
            page.keyboard.press("Escape")
        except PWError:
            pass
    return names


# ---- attachments -----------------------------------------------------------
def attach_files(sess: Session, page: Page, paths: list[Path]) -> list[str]:
    inp = first(page, S.FILE_INPUT)
    if not inp:
        plus = first(page, S.COMPOSER_PLUS)
        if plus:
            try:
                plus.click()
                time.sleep(0.5)
                page.keyboard.press("Escape")
            except PWError:
                pass
        inp = first(page, S.FILE_INPUT)
    if not inp:
        raise CgError("UPLOAD_UNAVAILABLE", "no file input on the page", screenshot=sess.shot(page, "upload"))
    try:
        inp.set_input_files([str(p) for p in paths])
    except PWError as e:
        raise CgError("UPLOAD_UNAVAILABLE", f"set_input_files failed: {e}", screenshot=sess.shot(page, "upload"))
    # wait until every file is visible in the composer, nothing says "Uploading", send is enabled
    names = [p.name for p in paths]
    img_names = [n for n in names if n.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "gif", "webp")]
    doc_names = [n for n in names if n not in img_names]
    end = time.time() + sess.cfg.upload_timeout_sec
    form = page.locator("form").first
    settled_since = None
    while time.time() < end:
        dismiss_dialogs(page)
        try:
            txt = form.inner_text() if form.count() else ""
        except PWError:
            txt = ""
        docs_ok = sum(1 for n in doc_names if n in txt or n.rsplit(".", 1)[0] in txt) >= len(doc_names)
        try:
            imgs_ok = form.locator("img").count() >= len(img_names)
        except PWError:
            imgs_ok = not img_names
        uploading = bool(re.search(S.UPLOADING_RE, txt, re.I)) or page.locator('form [role="progressbar"]').count() > 0
        send = first(page, S.SEND_BUTTON)
        send_ok = False
        try:
            send_ok = bool(send and send.is_enabled())
        except PWError:
            pass
        if docs_ok and imgs_ok and not uploading and send_ok:
            # give thumbnails/processing 3 more seconds to settle
            settled_since = settled_since or time.time()
            if time.time() - settled_since >= 3:
                return names
        else:
            settled_since = None
        if re.search(r"(can't upload|cannot upload|not supported|desteklenmiyor|yükleyemez)", txt, re.I):
            raise CgError("UPLOAD_UNAVAILABLE", "ChatGPT rejected an attachment", screenshot=sess.shot(page, "upload"))
        time.sleep(1.0)
    raise CgError("UPLOAD_UNAVAILABLE", f"upload did not settle in {sess.cfg.upload_timeout_sec}s",
                  screenshot=sess.shot(page, "upload"))


DIALOG_DISMISS_RE = re.compile(r"(added to chat only|storage space|depolama|sohbete eklendi|Got it|Tamam)", re.I)


def dismiss_dialogs(page: Page) -> list[str]:
    """Close informational modals (e.g. free-plan 'File added to chat only'). Returns their titles."""
    seen: list[str] = []
    try:
        dialogs = page.locator('[role="dialog"], [role="alertdialog"]')
        for i in range(dialogs.count()):
            d = dialogs.nth(i)
            if not d.is_visible():
                continue
            txt = (d.inner_text() or "").strip()
            if not DIALOG_DISMISS_RE.search(txt):
                continue
            seen.append(txt.split("\n")[0][:80])
            closed = False
            for sel in ('button[aria-label="Close"]', 'button[aria-label="Kapat"]', 'button:has-text("Got it")',
                        'button:has-text("Tamam")', 'button:has-text("OK")'):
                b = d.locator(sel)
                if b.count():
                    b.first.click()
                    closed = True
                    break
            if not closed:
                page.keyboard.press("Escape")
            time.sleep(0.5)
    except PWError:
        pass
    return seen


# ---- turns -----------------------------------------------------------------
def assistant_count(page: Page) -> int:
    try:
        return page.locator(S.ASSISTANT_TURN[0]).count()
    except PWError:
        return 0


def user_count(page: Page) -> int:
    try:
        return page.locator(S.USER_TURN[0]).count()
    except PWError:
        return 0


def read_assistant(page: Page, index: int = -1) -> dict:
    """Text + fenced blocks of one assistant turn (default: last)."""
    turns = page.locator(S.ASSISTANT_TURN[0])
    n = turns.count()
    if n == 0:
        return {"index": None, "text": "", "blocks": [], "words": 0}
    i = index if index >= 0 else n + index
    if i < 0 or i >= n:
        raise CgError("INPUT", f"assistant turn index {index} out of range (have {n})")
    t = turns.nth(i)
    text = t.inner_text()
    blocks: list[Block] = []
    # DOM-based blocks are more reliable than regex over innerText (header labels, copy buttons…)
    try:
        for pre in t.locator("pre").all():
            code = pre.locator("code").first
            lang = ""
            try:
                cls = code.get_attribute("class") or ""
                m = re.search(r"language-([\w+#.-]+)", cls)
                if m:
                    lang = m.group(1).lower()
                else:
                    head = pre.locator("div").first.inner_text().strip().split("\n")[0]
                    if head and len(head) < 20:
                        lang = head.lower()
            except PWError:
                pass
            body = code.inner_text() if code.count() else pre.inner_text()
            blocks.append(Block(lang=lang, text=body))
    except PWError:
        blocks = []
    if not blocks:
        blocks = blocks_from_text(text)
    return {"index": i, "text": text, "blocks": [b.to_dict() for b in blocks], "words": len(text.split())}


# ---- send / wait -------------------------------------------------------------
def send_text(sess: Session, page: Page, text: str) -> None:
    dismiss_dialogs(page)
    box = first(page, S.PROMPT_BOX)
    if not box:
        raise CgError("SESSION_LOST", "no prompt box", screenshot=sess.shot(page, "nobox"))
    box.click()
    try:
        page.keyboard.insert_text(text)
    except PWError:
        box.fill(text)
    time.sleep(0.3)
    try:
        got = len(box.inner_text())
        if got < 0.8 * len(text):
            raise CgError("INTERNAL", f"prompt only partially inserted ({got}/{len(text)} chars)")
    except PWError:
        pass
    users_before = user_count(page)
    send = first(page, S.SEND_BUTTON)
    try:
        if send:
            send.wait_for(state="visible", timeout=10000)
            send.click()
        else:
            page.keyboard.press("Enter")
    except PWError:
        page.keyboard.press("Enter")
    end = time.time() + 20
    while time.time() < end:
        if user_count(page) > users_before:
            return
        # toast: message too long / rate limit
        try:
            alerts = " ".join(page.locator('[role="alert"], [role="dialog"]').all_inner_texts())
        except PWError:
            alerts = ""
        if re.search(S.TOO_LONG_RE, alerts, re.I):
            raise CgError("MESSAGE_TOO_LONG", alerts[:300], screenshot=sess.shot(page, "toolong"))
        if re.search(S.RATE_LIMIT_RE, alerts, re.I):
            raise CgError("RATE_LIMIT", alerts[:300], screenshot=sess.shot(page, "ratelimit"))
        time.sleep(0.5)
    raise CgError("GENERATION_ERROR", "message did not appear as a user turn after send", screenshot=sess.shot(page, "send"))


def is_generating(page: Page) -> bool:
    if visible(page, S.STOP_BUTTON):
        return True
    try:
        turns = page.locator(S.ASSISTANT_TURN[0])
        n = turns.count()
        if n:
            last = turns.nth(n - 1)
            txt = last.inner_text()
            if len(txt.strip()) < 200 and re.search(S.THINKING_RE, txt, re.I | re.M):
                return True
            if last.locator('[class*="result-streaming"], [class*="streaming"]').count():
                return True
    except PWError:
        pass
    return False


def wait_reply(sess: Session, page: Page, baseline_assistant: int, timeout_sec: int) -> dict:
    """Poll until the newest assistant turn (after baseline) is complete or timeout.

    Returns {"status": "done"|"generating", "reply": {...} | None, "elapsed_sec": n}
    """
    start = time.time()
    last_hash = ""
    stable_since = None
    regenerated = False
    poll = sess.cfg.poll_sec
    while True:
        state = sess.classify(page)
        if state in ("login_required", "anonymous"):
            raise CgError("SESSION_LOST", f"session state {state} while waiting", screenshot=sess.shot(page, "session"))
        if sess.rate_limited(page):
            raise CgError("RATE_LIMIT", "usage limit while waiting", screenshot=sess.shot(page, "ratelimit"))
        n = assistant_count(page)
        if n > baseline_assistant:
            cont = first(page, S.CONTINUE_BUTTON)
            try:
                if cont and cont.is_visible():
                    cont.click()
                    stable_since = None
                    time.sleep(2)
                    continue
            except PWError:
                pass
            turns = page.locator(S.ASSISTANT_TURN[0])
            last = turns.nth(n - 1)
            try:
                txt = last.inner_text()
            except PWError:
                txt = ""
            if re.search(S.GENERATION_ERROR_RE, txt, re.I) and len(txt) < 400:
                regen = first(page, S.REGENERATE_BUTTON)
                if regen and not regenerated:
                    regenerated = True
                    try:
                        regen.click()
                        stable_since = None
                        time.sleep(3)
                        continue
                    except PWError:
                        pass
                raise CgError("GENERATION_ERROR", txt[:300], screenshot=sess.shot(page, "generr"))
            generating = is_generating(page)
            h = hashlib.sha1(txt.encode("utf-8", "ignore")).hexdigest()
            if not generating and txt.strip():
                if h != last_hash:
                    last_hash, stable_since = h, time.time()
                elif stable_since and time.time() - stable_since >= sess.cfg.stable_sec:
                    has_copy = False
                    try:
                        art = last.locator("xpath=ancestor::article[1]")
                        has_copy = any(art.locator(s).count() > 0 for s in S.COPY_BUTTON) if art.count() else False
                    except PWError:
                        pass
                    if has_copy or time.time() - stable_since >= 2 * sess.cfg.stable_sec:
                        return {"status": "done", "reply": read_assistant(page, -1),
                                "elapsed_sec": round(time.time() - start, 1)}
            else:
                last_hash, stable_since = h, None
        if time.time() - start >= timeout_sec:
            return {"status": "generating", "reply": None, "elapsed_sec": round(time.time() - start, 1)}
        time.sleep(poll)
