from chatgpt_web import extract as x

REPLY_4 = """Here you go:

````markdown
# Ders: Risk

### BÖLÜM 1 — Giriş
Metin metin.

```python
print("hi")
```

### BÖLÜM 2 — Devam
Daha fazla metin.
````
Bitti."""

REPLY_3 = """```markdown
# Başlık
### BÖLÜM 1 — Tek
içerik
```"""

REPLY_MULTI = """```python
x = 1
```
Some prose
```md
### BÖLÜM 1 — A
aaa aaa
### BÖLÜM 2 — B
bbb
```"""


def test_four_backtick_outer_fence_keeps_inner_block():
    blocks = x.blocks_from_text(REPLY_4)
    assert [b.lang for b in blocks] == ["markdown"]
    body = blocks[0].text
    assert "```python" in body and "### BÖLÜM 2" in body


def test_three_backtick():
    b = x.largest_markdown(x.blocks_from_text(REPLY_3))
    assert b and b.lang == "markdown" and b.text.startswith("# Başlık")


def test_largest_markdown_prefers_md_lang():
    b = x.largest_markdown(x.blocks_from_text(REPLY_MULTI))
    assert b.lang == "md" and "BÖLÜM 2" in b.text


def test_no_fence_returns_none():
    assert x.largest_markdown(x.blocks_from_text("plain text")) is None


def test_sections_and_counts():
    body = x.largest_markdown(x.blocks_from_text(REPLY_4)).text
    s = x.sections(body, cap=5, floor=1)
    assert s["section_count"] == 2 and s["numbering_ok"]
    assert s["sections"][0]["title"] == "Giriş"
    assert s["sections"][0]["words"] > s["sections"][0]["words_prose"]  # code counted only in `words`
    assert s["preamble_words"] == 3  # "# Ders: Risk"


def test_numbering_broken():
    s = x.sections("### BÖLÜM 1 — a\nx\n### BÖLÜM 3 — b\ny")
    assert not s["numbering_ok"]


def test_double_fence_unwrap():
    outer = x.blocks_from_text("````markdown\n```markdown\n# X\n### BÖLÜM 1 — a\nbody\n```\n````")
    b = x.largest_markdown(outer)
    assert b.text.startswith("# X")


def test_normalize_strips_language_line():
    assert x.normalize("markdown\n# T\n") == "# T\n"
