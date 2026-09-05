"""Single-operation lock around the shared browser.

Two callers (e.g. the MCP server and the CLI) must not drive chatgpt.com at the
same time: they would both read "the last assistant turn". The lock is held only
for the duration of one tool call; long waits release and re-acquire it between
polls so a `status` call can still get through.
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

from .errors import CgError

try:  # POSIX
    import fcntl
except ImportError:  # Windows: best-effort via msvcrt
    fcntl = None
    import msvcrt


@contextmanager
def net_shared_lock(path: Path | None):
    """Shared (read) lock on the network lock file: many tools may hold it at once,
    warp-rotate needs it exclusively and therefore waits/refuses while any tool works."""
    if path is None or fcntl is None:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_SH)
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        fh.close()


@contextmanager
def browser_lock(path: Path, wait_sec: int = 120, label: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+")
    deadline = time.time() + wait_sec
    while True:
        try:
            if fcntl:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            break
        except OSError:
            if time.time() >= deadline:
                fh.seek(0)
                owner = fh.read().strip()
                fh.close()
                raise CgError("LOCKED", f"another chatgpt-web operation is running ({owner or 'unknown'})")
            time.sleep(0.5)
    try:
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid={os.getpid()} since={time.strftime('%H:%M:%S')} {label}")
        fh.flush()
        yield
    finally:
        try:
            if fcntl:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            else:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        fh.close()
