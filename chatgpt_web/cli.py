"""`cgweb` — the same tools as the MCP server, for humans and tests. Prints one JSON object."""
from __future__ import annotations

import argparse
import json
import sys

from . import core


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cgweb", description="ChatGPT web conversation tools (CDP-driven)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("doctor")
    s = sub.add_parser("list-chats"); s.add_argument("--query"); s.add_argument("--limit", type=int, default=20)
    s = sub.add_parser("new-chat"); s.add_argument("--title-hint")
    s = sub.add_parser("open-chat"); s.add_argument("chat_url")
    s = sub.add_parser("send"); s.add_argument("chat"); s.add_argument("--text"); s.add_argument("--text-file")
    s.add_argument("--file", action="append", default=[]); s.add_argument("--wait", type=int, default=0)
    s.add_argument("--format", default="largest_markdown")
    s = sub.add_parser("wait"); s.add_argument("chat"); s.add_argument("--timeout", type=int, default=300)
    s.add_argument("--format", default="largest_markdown")
    s = sub.add_parser("get-reply"); s.add_argument("chat"); s.add_argument("--index", type=int, default=-1)
    s.add_argument("--format", default="text")
    s = sub.add_parser("save-reply"); s.add_argument("chat"); s.add_argument("path")
    s.add_argument("--index", type=int, default=-1); s.add_argument("--format", default="largest_markdown")
    s = sub.add_parser("stop"); s.add_argument("chat")
    s = sub.add_parser("close-chat"); s.add_argument("chat")
    s = sub.add_parser("check"); s.add_argument("path")
    a = p.parse_args(argv)

    if a.cmd == "status":
        out = core.status()
    elif a.cmd == "doctor":
        out = core.doctor()
    elif a.cmd == "list-chats":
        out = core.list_chats(a.query, a.limit)
    elif a.cmd == "new-chat":
        out = core.new_chat(a.title_hint)
    elif a.cmd == "open-chat":
        out = core.open_chat(a.chat_url)
    elif a.cmd == "send":
        text = a.text
        if a.text_file:
            with open(a.text_file, encoding="utf-8") as fh:
                text = fh.read()
        if text is None and not sys.stdin.isatty():
            text = sys.stdin.read()
        out = core.send(a.chat, text or "", a.file, a.wait, a.format)
    elif a.cmd == "wait":
        out = core.wait(a.chat, a.timeout, a.format)
    elif a.cmd == "get-reply":
        out = core.get_reply(a.chat, a.index, a.format)
    elif a.cmd == "save-reply":
        out = core.save_reply(a.chat, a.path, a.index, a.format)
    elif a.cmd == "stop":
        out = core.stop(a.chat)
    elif a.cmd == "close-chat":
        out = core.close_chat(a.chat)
    else:
        out = core.check_file(a.path)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
