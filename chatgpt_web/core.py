"""Tool implementations. Every function returns a JSON-serialisable dict and never
raises for expected failures (they come back as {"ok": false, "error": CODE, ...}).

Used by both the MCP server (mcp_server.py) and the CLI (cli.py).
"""
from __future__ import annotations

import time
import traceback
from functools import wraps
from pathlib import Path

from . import chat, project
from .browser import Session
from .config import Config, load
from .errors import CgError
from .extract import Block, largest_markdown, normalize, sections, word_count
from .lock import browser_lock


def _guard(fn):
    @wraps(fn)
    def inner(*a, **kw):
        try:
            out = fn(*a, **kw)
            out.setdefault("ok", True)
            return out
        except CgError as e:
            return e.to_dict()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": "INTERNAL", "message": f"{type(e).__name__}: {e}",
                    "trace": traceback.format_exc()[-1500:]}
    return inner


def _cfg(cfg: Config | None) -> Config:
    return cfg or load()


def _check_path(cfg: Config, p: str, must_exist: bool) -> Path:
    path = Path(p).expanduser()
    if not path.is_absolute():
        path = cfg.work_dir / path
    path = path.resolve()
    try:
        path.relative_to(cfg.work_dir.resolve())
    except ValueError:
        raise CgError("FILE_NOT_ALLOWED", f"{path} is outside {cfg.work_dir}")
    if must_exist and not path.is_file():
        raise CgError("FILE_NOT_ALLOWED", f"{path} does not exist")
    return path


def _reply_view(reply: dict | None, fmt: str) -> dict | None:
    if reply is None:
        return None
    blocks = [Block(**b) for b in reply.get("blocks", [])]
    lm = largest_markdown(blocks)
    view = {"index": reply.get("index"), "words": reply.get("words"), "block_count": len(blocks)}
    if fmt in ("text", "all"):
        view["text"] = reply.get("text", "")
    if fmt in ("blocks", "all"):
        view["blocks"] = reply.get("blocks", [])
    if fmt in ("largest_markdown", "all"):
        view["largest_markdown"] = normalize(lm.text) if lm else None
        view["largest_markdown_lang"] = lm.lang if lm else None
    return view


# ---------------------------------------------------------------- tools ----
@_guard
def status(cfg: Config | None = None) -> dict:
    cfg = _cfg(cfg)
    with browser_lock(cfg.lock_file, cfg.lock_wait_sec, "status"), Session(cfg) as sess:
        pages = sess.chatgpt_pages()
        page = pages[0] if pages else None
        session_state = sess.classify(page) if page else "no_tab"
        model = chat.current_model_label(page) if page else ""
        open_chats = []
        for p in pages:
            if "/c/" in p.url:
                try:
                    open_chats.append({"url": p.url.split("?")[0], "title": p.title()})
                except Exception:  # noqa: BLE001
                    open_chats.append({"url": p.url.split("?")[0], "title": ""})
        return {
            "session": session_state,
            "model_label": model,
            "model_configured": {"slug": cfg.model_slug, "label": cfg.model_label, "strict": cfg.model_strict},
            "project": {"name": cfg.project, "url": project.cached_url(sess, cfg.project)},
            "open_chats": open_chats,
            "tab_count": len(pages),
            "work_dir": str(cfg.work_dir),
        }


@_guard
def doctor(cfg: Config | None = None) -> dict:
    cfg = _cfg(cfg)
    with browser_lock(cfg.lock_file, cfg.lock_wait_sec, "doctor"), Session(cfg) as sess:
        page = sess.new_page()
        try:
            sess.goto(page, cfg.base_url + "/")
            state = sess.classify(page)
            from .browser import first
            from . import selectors as S
            file_input = first(page, S.FILE_INPUT) is not None
            models = chat.list_models(page)
            proj_url = None
            proj_err = None
            try:
                proj_url = project.find_project(sess, page, cfg.project, create=False)
            except CgError as e:
                proj_err = e.message
            return {"session": state, "model_label": chat.current_model_label(page), "models": models,
                    "file_input_present": file_input, "project": {"name": cfg.project, "url": proj_url, "error": proj_err},
                    "cdp_url": cfg.cdp_url, "tabs": [p.url[:80] for p in sess.ctx.pages]}
        finally:
            try:
                page.close()
            except Exception:  # noqa: BLE001
                pass


@_guard
def list_chats(query: str | None = None, limit: int = 20, cfg: Config | None = None) -> dict:
    cfg = _cfg(cfg)
    with browser_lock(cfg.lock_file, cfg.lock_wait_sec, "list_chats"), Session(cfg) as sess:
        page = sess.new_page()
        try:
            url = project.find_project(sess, page, cfg.project, create=False)
            chats = project.list_chats(sess, page, url, query, limit)
            return {"project_url": url, "chats": chats, "count": len(chats)}
        finally:
            page.close()


@_guard
def new_chat(title_hint: str | None = None, cfg: Config | None = None) -> dict:
    """Open a fresh chat inside the project. The tab is left open; its handle is `chat`."""
    cfg = _cfg(cfg)
    with browser_lock(cfg.lock_file, cfg.lock_wait_sec, "new_chat"), Session(cfg) as sess:
        page = sess.new_page()
        try:
            url = project.find_project(sess, page, cfg.project, create=True)
            model = chat.ensure_model(sess, page, cfg.model_slug, cfg.model_label, cfg.model_strict)
            handle = "tab:" + sess.target_id(page)
        except CgError:
            try:
                page.close()  # do not leave half-opened tabs behind
            except Exception:  # noqa: BLE001
                pass
            raise
        return {"chat": handle, "chat_url": None, "project_url": url, "title_hint": title_hint,
                "note": "send() returns the permanent chat_url after the first message", **model}


@_guard
def open_chat(chat_url: str, cfg: Config | None = None) -> dict:
    cfg = _cfg(cfg)
    with browser_lock(cfg.lock_file, cfg.lock_wait_sec, "open_chat"), Session(cfg) as sess:
        page = sess.page_for_handle(chat_url)
        sess.ensure_usable(page)
        n_a, n_u = chat.assistant_count(page), chat.user_count(page)
        last = chat.read_assistant(page, -1) if n_a else None
        return {"chat": page.url.split("?")[0], "chat_url": page.url.split("?")[0], "assistant_turns": n_a,
                "user_turns": n_u, "generating": chat.is_generating(page),
                "last_reply_preview": (last["text"][:400] if last else None),
                "model_label": chat.current_model_label(page)}


@_guard
def send(chat_handle: str, text: str, files: list[str] | None = None, wait_sec: int = 0,
         reply_format: str = "largest_markdown", cfg: Config | None = None) -> dict:
    cfg = _cfg(cfg)
    if not text or not text.strip():
        raise CgError("INPUT", "text is empty")
    paths = [_check_path(cfg, f, True) for f in (files or [])]
    if len(paths) > cfg.max_files:
        raise CgError("INPUT", f"at most {cfg.max_files} files per message")
    wait_sec = max(0, min(int(wait_sec), cfg.max_wait_sec))
    with browser_lock(cfg.lock_file, cfg.lock_wait_sec, "send"), Session(cfg) as sess:
        page = sess.page_for_handle(chat_handle)
        sess.ensure_usable(page)
        if chat.is_generating(page):
            raise CgError("GENERATION_ERROR", "a reply is still being generated in this chat; call wait first")
        attached = chat.attach_files(sess, page, paths) if paths else []
        baseline = chat.assistant_count(page)
        chat.send_text(sess, page, text)
        # capture the permanent URL (new chats get /c/<id> after the first message)
        chat_url = None
        end = time.time() + 20
        while time.time() < end:
            if "/c/" in page.url:
                chat_url = page.url.split("?")[0]
                break
            time.sleep(0.5)
        out = {"chat": chat_url or chat_handle, "chat_url": chat_url, "attached": attached,
               "baseline_assistant_turns": baseline, "status": "generating", "reply": None}
        if wait_sec > 0:
            res = chat.wait_reply(sess, page, baseline, wait_sec)
            out.update({"status": res["status"], "elapsed_sec": res["elapsed_sec"],
                        "reply": _reply_view(res["reply"], reply_format)})
        # the permanent URL may only appear once the reply starts streaming
        if "/c/" in page.url:
            out["chat_url"] = page.url.split("?")[0]
            out["chat"] = out["chat_url"]
        return out


@_guard
def wait(chat_handle: str, timeout_sec: int = 300, reply_format: str = "largest_markdown",
         cfg: Config | None = None) -> dict:
    cfg = _cfg(cfg)
    timeout_sec = max(1, min(int(timeout_sec), cfg.max_wait_sec))
    with browser_lock(cfg.lock_file, cfg.lock_wait_sec, "wait"), Session(cfg) as sess:
        page = sess.page_for_handle(chat_handle)
        sess.ensure_usable(page)
        n = chat.assistant_count(page)
        if n == 0:
            raise CgError("INPUT", "this chat has no assistant turn yet; send a message first")
        # baseline = n-1 so the newest turn is the one we judge
        res = chat.wait_reply(sess, page, n - 1, timeout_sec)
        return {"chat": page.url.split("?")[0], "status": res["status"], "elapsed_sec": res["elapsed_sec"],
                "reply": _reply_view(res["reply"], reply_format),
                "hint": None if res["status"] == "done" else "still generating; call wait again"}


@_guard
def get_reply(chat_handle: str, index: int = -1, reply_format: str = "text", cfg: Config | None = None) -> dict:
    cfg = _cfg(cfg)
    with browser_lock(cfg.lock_file, cfg.lock_wait_sec, "get_reply"), Session(cfg) as sess:
        page = sess.page_for_handle(chat_handle)
        sess.ensure_usable(page)
        r = chat.read_assistant(page, index)
        return {"chat": page.url.split("?")[0], "generating": chat.is_generating(page),
                "assistant_turns": chat.assistant_count(page), "reply": _reply_view(r, reply_format)}


@_guard
def save_reply(chat_handle: str, path: str, index: int = -1, reply_format: str = "largest_markdown",
               cfg: Config | None = None) -> dict:
    cfg = _cfg(cfg)
    dest = _check_path(cfg, path, False)
    with browser_lock(cfg.lock_file, cfg.lock_wait_sec, "save_reply"), Session(cfg) as sess:
        page = sess.page_for_handle(chat_handle)
        sess.ensure_usable(page)
        r = chat.read_assistant(page, index)
    blocks = [Block(**b) for b in r.get("blocks", [])]
    if reply_format == "largest_markdown":
        lm = largest_markdown(blocks)
        content = normalize(lm.text) if lm else None
        if content is None:
            content = normalize(r["text"])
            used = "text (no fenced block found)"
        else:
            used = f"largest_markdown ({lm.lang or 'untagged'})"
    else:
        content = normalize(r["text"])
        used = "text"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    stats = sections(content)
    return {"path": str(dest), "bytes": len(content.encode("utf-8")), "words": word_count(content), "used": used,
            "section_count": stats["section_count"], "over_cap_sections": stats.get("over_cap_sections", []),
            "numbering_ok": stats["numbering_ok"]}


@_guard
def stop(chat_handle: str, cfg: Config | None = None) -> dict:
    cfg = _cfg(cfg)
    from .browser import first
    from . import selectors as S
    with browser_lock(cfg.lock_file, cfg.lock_wait_sec, "stop"), Session(cfg) as sess:
        page = sess.page_for_handle(chat_handle)
        btn = first(page, S.STOP_BUTTON)
        if btn and btn.is_visible():
            sess.human(page).click_locator(btn)
            return {"stopped": True}
        return {"stopped": False, "note": "nothing was generating"}


@_guard
def close_chat(chat_handle: str, cfg: Config | None = None) -> dict:
    cfg = _cfg(cfg)
    with browser_lock(cfg.lock_file, cfg.lock_wait_sec, "close_chat"), Session(cfg) as sess:
        try:
            page = sess.page_for_handle(chat_handle)
        except CgError as e:
            if e.code == "CHAT_NOT_FOUND":
                return {"closed": False, "note": "no such tab"}
            raise
        url = page.url
        page.close()
        return {"closed": True, "url": url}


@_guard
def check_file(path: str, cfg: Config | None = None) -> dict:
    """Offline: section/word statistics of a saved notes file."""
    cfg = _cfg(cfg)
    p = _check_path(cfg, path, True)
    txt = p.read_text(encoding="utf-8")
    return {"path": str(p), **sections(txt)}
