"""MCP stdio server exposing the ChatGPT web conversation tools.

Run: python -m chatgpt_web.mcp_server   (never prints to stdout; logs go to stderr)
Hermes config:
  mcp_servers:
    chatgpt:
      command: /home/hermes/work/chatgpt-web/.venv/bin/python
      args: ["-m", "chatgpt_web.mcp_server"]
      env: {CHATGPT_PROJECT: "Ders Notları", CHATGPT_MODEL_LABEL: "Pro"}
      timeout: 900
"""
from __future__ import annotations

import logging
import sys
from typing import Any

import anyio
from mcp.server import MCPServer

from . import core

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("chatgpt-web")

INSTRUCTIONS = """Tools that drive the user's logged-in ChatGPT web session (a persistent Chromium on this
server) inside one fixed ChatGPT Project. Typical flow: status -> new_chat (or list_chats/open_chat)
-> send(chat, text, files) -> wait(chat) until status=done -> save_reply(chat, path) or get_reply.
Handles: `chat` is either a conversation URL (https://chatgpt.com/c/...) or `tab:<id>` for a brand-new
chat before its first message; `send` returns the permanent chat_url. Files must live under the work dir.
Long replies (Pro thinking) can take up to ~45 min: keep calling wait(timeout_sec<=900) until done.
Do NOT open chatgpt.com with any other browser tool; only these tools may touch that session."""

mcp = MCPServer(
    "chatgpt-web",
    title="ChatGPT Web",
    description="Chat with the user's ChatGPT web session (projects, files, long Pro replies) over CDP.",
    instructions=INSTRUCTIONS,
    version="0.1.0",
)


async def _run(fn, *a, **kw) -> dict[str, Any]:
    # Playwright's sync API must not run on the event-loop thread.
    return await anyio.to_thread.run_sync(lambda: fn(*a, **kw))


@mcp.tool(name="status", description="Session state (logged_in/anonymous/login_required), current model label, "
                                     "configured project, open chat tabs. Cheap; call first.")
async def status() -> dict:
    return await _run(core.status)


@mcp.tool(name="doctor", description="Health check: CDP reachable, session state, file input present, available "
                                     "model names, whether the configured project exists. Use when something fails.")
async def doctor() -> dict:
    return await _run(core.doctor)


@mcp.tool(name="list_chats", description="List conversations inside the configured ChatGPT project "
                                         "(title + url). Optional substring filter on title.")
async def list_chats(query: str | None = None, limit: int = 20) -> dict:
    return await _run(core.list_chats, query, limit)


@mcp.tool(name="new_chat", description="Open a new conversation inside the configured project and select the "
                                       "configured model. Returns a temporary handle `chat` (tab:<id>); after "
                                       "the first send you get the permanent chat_url.")
async def new_chat(title_hint: str | None = None) -> dict:
    return await _run(core.new_chat, title_hint)


@mcp.tool(name="open_chat", description="Open an existing conversation by URL (https://chatgpt.com/c/...) so you "
                                        "can continue it. Returns turn counts and a preview of the last reply.")
async def open_chat(chat_url: str) -> dict:
    return await _run(core.open_chat, chat_url)


@mcp.tool(name="send", description="Send a message (optionally with files under the work dir, max 10) to a chat. "
                                   "Returns immediately with status=generating unless wait_sec>0 (max 900). "
                                   "reply_format: largest_markdown | text | blocks | all.")
async def send(chat: str, text: str, files: list[str] | None = None, wait_sec: int = 0,
               reply_format: str = "largest_markdown") -> dict:
    return await _run(core.send, chat, text, files, wait_sec, reply_format)


@mcp.tool(name="wait", description="Wait for the newest reply in a chat to finish (poll). timeout_sec<=900; if it "
                                   "returns status=generating call wait again. Returns the reply in reply_format.")
async def wait(chat: str, timeout_sec: int = 300, reply_format: str = "largest_markdown") -> dict:
    return await _run(core.wait, chat, timeout_sec, reply_format)


@mcp.tool(name="get_reply", description="Read an assistant reply without waiting. index=-1 is the newest. "
                                        "reply_format: text | blocks | largest_markdown | all.")
async def get_reply(chat: str, index: int = -1, reply_format: str = "text") -> dict:
    return await _run(core.get_reply, chat, index, reply_format)


@mcp.tool(name="save_reply", description="Write a reply to a file under the work dir without passing the whole text "
                                         "through the model. reply_format largest_markdown extracts the biggest "
                                         "```markdown block (falls back to full text). Returns word/section stats.")
async def save_reply(chat: str, path: str, index: int = -1, reply_format: str = "largest_markdown") -> dict:
    return await _run(core.save_reply, chat, path, index, reply_format)


@mcp.tool(name="stop", description="Stop the reply currently being generated in a chat.")
async def stop(chat: str) -> dict:
    return await _run(core.stop, chat)


@mcp.tool(name="close_chat", description="Close the browser tab of a chat (the conversation stays in ChatGPT).")
async def close_chat(chat: str) -> dict:
    return await _run(core.close_chat, chat)


@mcp.tool(name="check_file", description="Offline: word count per `### BÖLÜM n` section of a saved notes file.")
async def check_file(path: str) -> dict:
    return await _run(core.check_file, path)


def main() -> None:
    log.info("chatgpt-web MCP server starting (stdio)")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
