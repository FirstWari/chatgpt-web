"""Runtime configuration: environment variables with sane defaults.

Every knob is an env var so the same code runs as an MCP stdio server (env from
the host's config) and as the `cgweb` CLI (env from the shell / wrapper).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


@dataclass
class Config:
    cdp_url: str = field(default_factory=lambda: _env("CHATGPT_CDP_URL", "http://127.0.0.1:9222"))
    base_url: str = field(default_factory=lambda: _env("CHATGPT_BASE_URL", "https://chatgpt.com"))
    project: str = field(default_factory=lambda: _env("CHATGPT_PROJECT", "Ders Notları"))
    # Model selection: slug goes into `?model=`, label must appear in the picker button text.
    # Both empty => no model handling (free plan / early test).
    model_slug: str = field(default_factory=lambda: _env("CHATGPT_MODEL_SLUG", ""))
    model_label: str = field(default_factory=lambda: _env("CHATGPT_MODEL_LABEL", ""))
    model_strict: bool = field(default_factory=lambda: _env("CHATGPT_MODEL_STRICT", "0") == "1")
    # Files given to `send` / written by `save_reply` must live under this dir
    # (snap Chromium cannot read hidden dirs under $HOME, and it bounds what the agent can touch).
    work_dir: Path = field(default_factory=lambda: Path(_env("CHATGPT_WORK_DIR", str(Path.home() / "work"))))
    state_dir: Path = field(default_factory=lambda: Path(_env("CHATGPT_STATE_DIR", str(Path.home() / "work" / "chatgpt-web"))))
    debug_dir: Path | None = None
    lock_file: Path | None = None
    projects_file: Path | None = None
    # Timing
    poll_sec: float = field(default_factory=lambda: float(_env("CHATGPT_POLL_SEC", "4")))
    stable_sec: int = field(default_factory=lambda: _env_int("CHATGPT_STABLE_SEC", 20))
    nav_timeout_ms: int = field(default_factory=lambda: _env_int("CHATGPT_NAV_TIMEOUT_MS", 60000))
    upload_timeout_sec: int = field(default_factory=lambda: _env_int("CHATGPT_UPLOAD_TIMEOUT_SEC", 180))
    max_wait_sec: int = field(default_factory=lambda: _env_int("CHATGPT_MAX_WAIT_SEC", 900))
    max_files: int = field(default_factory=lambda: _env_int("CHATGPT_MAX_FILES", 10))
    lock_wait_sec: int = field(default_factory=lambda: _env_int("CHATGPT_LOCK_WAIT_SEC", 120))

    def __post_init__(self) -> None:
        self.work_dir = self.work_dir.expanduser()
        self.state_dir = self.state_dir.expanduser()
        self.debug_dir = self.debug_dir or Path(_env("CHATGPT_DEBUG_DIR", str(self.state_dir / "debug")))
        self.lock_file = self.lock_file or Path(_env("CHATGPT_LOCK", str(self.state_dir / "browser.lock")))
        self.projects_file = self.projects_file or self.state_dir / "projects.json"
        for d in (self.state_dir, self.debug_dir):
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass


def load() -> Config:
    return Config()
