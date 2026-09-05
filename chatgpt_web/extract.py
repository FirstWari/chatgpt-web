"""Pure text helpers: fenced-block extraction, word counts, section stats.

No browser dependency, so this is unit-tested on any machine.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

FENCE_RE = re.compile(r"^(?P<fence>`{3,4})[ \t]*(?P<lang>[\w+#.-]*)[ \t]*\r?\n(?P<body>.*?)\r?\n(?P=fence)[ \t]*$",
                      re.MULTILINE | re.DOTALL)
SECTION_RE = re.compile(r"^###[ \t]+B[ÖO]L[ÜU]M[ \t]+(\d+)\b[^\n]*$", re.MULTILINE | re.IGNORECASE)
MD_LANGS = {"markdown", "md"}
CRLF = "\r\n"
LF = "\n"


@dataclass
class Block:
    lang: str
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def blocks_from_text(text: str) -> list[Block]:
    """Fenced code blocks in reply text. Outer 4-backtick fences win over inner 3-backtick ones."""
    out: list[Block] = []
    for m in FENCE_RE.finditer(text.replace(CRLF, LF)):
        out.append(Block(lang=(m.group("lang") or "").lower(), text=m.group("body")))
    return out


def largest_markdown(blocks: list[Block]) -> Block | None:
    """The block most likely to be 'the document': largest markdown-tagged block, else largest block."""
    if not blocks:
        return None
    md = [b for b in blocks if b.lang in MD_LANGS]
    pool = md or blocks
    best = max(pool, key=lambda b: len(b.text))
    return _unwrap(best)


def _unwrap(b: Block) -> Block:
    """If the model double-fenced (```markdown ... ``` inside the block), unwrap once."""
    m = FENCE_RE.fullmatch(b.text.strip().replace(CRLF, LF))
    if m and (m.group("lang") or "").lower() in MD_LANGS:
        return Block(lang="markdown", text=m.group("body"))
    return b


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def prose_word_count(text: str) -> int:
    """Words excluding fenced code and $$ display math."""
    t = FENCE_RE.sub("", text)
    t = re.sub(r"\$\$.*?\$\$", "", t, flags=re.DOTALL)
    return word_count(t)


def sections(text: str, cap: int = 900, floor: int = 600) -> dict:
    """Split on `### BÖLÜM n` markers and report per-section word counts."""
    marks = list(SECTION_RE.finditer(text))
    if not marks:
        return {"section_count": 0, "sections": [], "total_words": word_count(text), "numbering_ok": False}
    out = []
    nums = []
    for i, m in enumerate(marks):
        start = m.start()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[start:end]
        n = int(m.group(1))
        nums.append(n)
        title = re.sub(r"^###\s+B[ÖO]L[ÜU]M\s+\d+\s*[—:\-–]?\s*", "", m.group(0), flags=re.IGNORECASE).strip()
        w = word_count(body)
        out.append({"n": n, "title": title, "words": w, "words_prose": prose_word_count(body),
                    "over_cap": w > cap, "under_min": w < floor})
    return {
        "section_count": len(out),
        "sections": out,
        "total_words": word_count(text),
        "numbering_ok": nums == list(range(1, len(nums) + 1)),
        "over_cap_sections": [s["n"] for s in out if s["over_cap"]],
        "under_min_sections": [s["n"] for s in out if s["under_min"]],
        "preamble_words": word_count(text[: marks[0].start()]),
    }


def normalize(text: str) -> str:
    t = text.replace(CRLF, LF).strip(LF)
    if t.lower().startswith("markdown" + LF):
        t = t.split(LF, 1)[1]
    return t + LF
