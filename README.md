# chatgpt-web

Drive **your own logged-in ChatGPT web session** from an AI agent: an MCP stdio server
(`mcp_chatgpt_*` tools) and a `cgweb` CLI built on the same core. It attaches over CDP to a Chromium
that is already running with your profile, so there is no password handling, no headless login and
no scraping of a second account. Built for Hermes Agent on a Linux server; works with any MCP host.

What it gives the agent:

- one fixed ChatGPT **Project** (found by name, created if missing, URL cached)
- `new_chat` / `list_chats` / `open_chat` — new or existing conversation, handle = conversation URL
- `send` with file attachments (transcripts, images), `wait` that polls long Pro replies in ≤15-minute
  slices, `get_reply` / `save_reply` (extracts the biggest ```markdown block to a file), `stop`, `close_chat`
- model selection by URL slug + picker label with verification (`CHATGPT_MODEL_SLUG/LABEL`)
- clear error codes (`SESSION_LOST`, `RATE_LIMIT`, `UPLOAD_UNAVAILABLE`, …) returned as tool results

## Requirements

- A Chromium/Chrome started with `--remote-debugging-port=9222 --remote-allow-origins=*` and a profile
  that is logged in to chatgpt.com (on a server: Xvfb + noVNC for the one-time login).
- Python ≥ 3.11. `pip install -e .` installs `playwright` (no `playwright install` needed — we only
  connect over CDP) and the `mcp` SDK.

## Install (server, as the agent's user)

```bash
cd ~/work && git clone https://github.com/FirstWari/chatgpt-web && cd chatgpt-web
uv venv .venv && uv pip install -e .
.venv/bin/cgweb doctor          # session, models, project, file input
```

Hermes (`~/.hermes/config.yaml`):

```yaml
mcp_servers:
  chatgpt:
    command: /home/hermes/work/chatgpt-web/.venv/bin/python
    args: ["-m", "chatgpt_web.mcp_server"]
    env:
      CHATGPT_PROJECT: "Ders Notları"
      CHATGPT_MODEL_LABEL: "Pro"        # substring expected in the model picker; empty = don't touch the model
      CHATGPT_MODEL_SLUG: ""            # optional ?model= slug
      CHATGPT_WORK_DIR: "/home/hermes/work/lore-engine/results"   # data-only: never the tool/venv/cookie root
    timeout: 900
    connect_timeout: 60
```

Then copy `SKILL.md` (and `prompts/`) to `~/.hermes/skills/research/chatgpt-web/` and restart the gateway.
Claude Desktop / Claude Code / Codex use the same `command`/`args`/`env` shape in their own config files.

## Environment variables

| Var | Default | Meaning |
|---|---|---|
| `CHATGPT_CDP_URL` | `http://127.0.0.1:9222` | CDP endpoint |
| `CHATGPT_PROJECT` | `Ders Notları` | Project name in the sidebar |
| `CHATGPT_MODEL_LABEL` / `_SLUG` | empty | Model to select; `CHATGPT_MODEL_STRICT=1` turns a mismatch into an error |
| `CHATGPT_WORK_DIR` | `~/work` | Only files under here may be attached (`send`) or written (`save_reply`). **Set it to a data-only dir (e.g. the lecture-results dir), never a directory that also contains code, venvs or cookie files** — it is the trust boundary for a prompt-injected reply. |
| `CHATGPT_STATE_DIR` | `~/work/chatgpt-web` | lock, `projects.json`, `debug/` screenshots |
| `CHATGPT_STABLE_SEC` | `20` | Reply must be unchanged this long (and show a Copy button) to count as finished |
| `CHATGPT_MAX_WAIT_SEC` | `900` | Upper bound for one `wait`/`send --wait` call |

## CLI

```bash
cgweb status | doctor | list-chats [--query X]
cgweb new-chat                                  # -> {"chat": "tab:...", ...}
cgweb send tab:... --text "Merhaba" --file ~/work/x.txt --wait 300
cgweb wait https://chatgpt.com/c/<id> --timeout 900
cgweb save-reply https://chatgpt.com/c/<id> ~/work/out/notes.md
cgweb check ~/work/out/notes.md                 # words per "### BÖLÜM n"
```

## Design notes

- Stateless per call: each tool connects, acts, disconnects. Chromium keeps the tabs, so the handle
  (`tab:<targetId>` before the first message, the `/c/<uuid>` URL after) survives across processes.
- A file lock serialises browser operations (MCP server and CLI can coexist).
- Completion heuristic: no stop button, no "Thinking" indicator, text hash stable for `STABLE_SEC`,
  Copy button present; "Continue generating" is clicked automatically; one automatic Regenerate on
  "Something went wrong".
- All selectors live in `chatgpt_web/selectors.py` with ordered fallbacks.
- ChatGPT's terms treat UI automation as a grey area; this tool uses your own account, one conversation
  at a time, with human-like pacing. Use at your own risk.

## Stealth measures (measured, 2026-09)

- Engine: **Patchright** over `connect_over_cdp` — no `Runtime.enable`/`Console.enable`, so Brotector and
  rebrowser-bot-detector stay clean (plain Playwright is flagged `runtime.enabled` within 300 ms).
- Input: `humanize.py` — cubic Bezier paths with minimum-jerk timing, Fitts-law durations
  (MacKenzie 1991 constants), tremor, occasional overshoot; log-normal key hold/flight; typed ≤400 chars,
  pasted above. Clicks pass `isTrusted`; the interactive Turnstile demo is solved by a humanized click.
- Browser environment (server side, not in this repo): headful Chromium on Xvfb 1920×1080, WebGL via
  ANGLE/SwiftShader (`--use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader`), 200+ font
  families, `WebRtcIPHandling=disable_non_proxied_udp` policy (no real-IP leak next to the proxy), no
  viewport override (inner ≤ outer), consistent Linux UA/platform.
- Network: `tools/warp-rotate` — safe WARP egress rotation (shared `net.lock`, cooldown, daily cap,
  geo health check against Google's `location=unsupported` gate); `chatgpt-web` rotates once automatically
  when a Cloudflare challenge does not clear.
- Measurement tools: `tools/fpcheck_all.sh` (Brotector, rebrowser, browserscan, CreepJS, Turnstile in
  raw/playwright/patchright modes), `tools/turnstile_test.py`, `tools/dom_dump.py`.

## Tests

`pytest` covers the text layer (fence extraction, section stats). Browser behaviour is checked with
`cgweb doctor` and a real conversation.

## License

MIT
