import json

from gateway.config import PlatformConfig
from gateway.platforms.feishu import (
    FeishuAdapter,
    _build_markdown_post_payload,
    _build_markdown_post_rows,
    _build_markdown_table_card_payload,
    _extract_first_markdown_table,
    _normalize_feishu_card_markdown,
)

# Helper: schema 2.0 cards use body.elements instead of top-level elements
def _els(parsed_card):
    return parsed_card["body"]["elements"]


def test_extract_first_markdown_table_basic():
    content = "Intro\n\n| Name | Value |\n|---|---:|\n| A | 1 |\n| B | 2 |\n\nOutro"
    table = _extract_first_markdown_table(content)
    assert table is not None
    assert table.before.strip() == "Intro"
    assert table.after.strip() == "Outro"
    assert table.headers == ["Name", "Value"]
    assert table.rows == [["A", "1"], ["B", "2"]]


def test_build_markdown_table_card_payload_uses_column_set():
    payload = json.loads(_build_markdown_table_card_payload("| A | B |\n|---|---|\n| x | y |"))
    assert payload["config"]["width_mode"] == "fill"
    assert payload["schema"] == "2.0"
    elements = _els(payload)
    # Tables now use markdown block (native pipe table rendering)
    # instead of column_set (which had row alignment drift)
    assert any(e.get("tag") == "markdown" for e in elements)
    markdown_block = next(e for e in elements if e.get("tag") == "markdown")
    assert "| A | B |" in markdown_block["content"]
    assert "| x | y |" in markdown_block["content"]


def test_build_markdown_table_card_payload_converts_multiple_tables():
    content = """## 第一段

| 项 | 值 |
|---|---|
| A | 1 |

中间文字

| 项 | 值 |
|---|---|
| B | 2 |

## 结尾"""
    payload = json.loads(_build_markdown_table_card_payload(content))
    elements = _els(payload)
    # Each table becomes a markdown block
    assert sum(1 for element in elements if element.get("tag") == "markdown") == 2
    rendered = json.dumps(payload, ensure_ascii=False)
    # markdown block preserves the pipe table separator
    assert "|---|" in rendered
    assert "## 第一段" not in rendered
    assert "## 结尾" not in rendered
    assert "**第一段**" in rendered
    assert "**结尾**" in rendered


def test_build_markdown_table_card_payload_keeps_headings_inside_code_blocks_literal():
    content = """## 标题

```md
## code heading
| not | table |
|---|---|
```

| A | B |
|---|---|
| x | y |"""
    payload = json.loads(_build_markdown_table_card_payload(content))
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "**标题**" in rendered
    assert "## code heading" in rendered
    assert "| not | table |" in rendered
    assert sum(1 for element in _els(payload) if element.get("tag") == "markdown") == 1


def test_normalize_converts_headings_preserves_backticks():
    normalized = _normalize_feishu_card_markdown(
        "## 使用 `hermes` 命令\n表格单元格 `ok` 和残留 `单点"
    )
    assert normalized == "**使用 `hermes` 命令**\n表格单元格 `ok` 和残留 `单点"


def test_normalize_keeps_code_block_literal():
    content = """普通 `inline`
```md
## code heading
`literal`
```
结尾 `done`"""
    normalized = _normalize_feishu_card_markdown(content)
    assert "普通 `inline`" in normalized
    assert "```md" in normalized
    assert "`literal`" in normalized
    assert "结尾 `done`" in normalized


def test_normalize_preserves_unmatched_backtick():
    normalized = _normalize_feishu_card_markdown("残留 `单点")
    assert "`单点" in normalized


def test_table_card_preserves_backticks_in_table_cells():
    payload = json.loads(
        _build_markdown_table_card_payload("## 标题 `cmd`\n\n| 项 | 值 |\n|---|---|\n| 命令 | `hermes status` |")
    )
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "`cmd`" in rendered
    assert "`hermes status`" in rendered
    assert sum(1 for element in _els(payload) if element.get("tag") == "markdown") == 1


def test_post_payload_preserves_backticks():
    payload = json.loads(_build_markdown_post_payload("请运行 `hermes status`，再看 **粗体** 和 [链接](https://x.test)"))
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "`hermes status`" in rendered
    assert "**粗体**" in rendered
    assert "[链接](https://x.test)" in rendered


def test_post_rows_preserve_backticks():
    rows = _build_markdown_post_rows("""普通 `inline`
```bash
echo `date`
```
结尾 `done`""")
    assert rows[0][0]["text"] == "普通 `inline`"
    assert "```bash" in rows[1][0]["text"]
    assert "echo `date`" in rows[1][0]["text"]
    assert rows[2][0]["text"] == "结尾 `done`"


# ---- _build_outbound_payload routing tests ----

def test_inline_code_only_uses_schema2_markdown_block():
    adapter = FeishuAdapter(PlatformConfig())
    msg_type, payload = adapter._build_outbound_payload("只有行内 `code`，没有其它 Markdown")
    assert msg_type == "interactive"
    parsed = json.loads(payload)
    assert parsed["schema"] == "2.0"
    els = _els(parsed)
    assert els[0]["tag"] == "markdown"
    assert "`code`" in els[0]["content"]


def test_plain_text_stays_text():
    adapter = FeishuAdapter(PlatformConfig())
    msg_type, payload = adapter._build_outbound_payload(r"普通文本，路径 C:\\tmp\\x")
    assert msg_type == "text"
    parsed = json.loads(payload)
    assert parsed["text"] == r"普通文本，路径 C:\\tmp\\x"


def test_fenced_code_block_uses_markdown_block():
    adapter = FeishuAdapter(PlatformConfig())
    msg_type, payload = adapter._build_outbound_payload("```bash\necho hello\n```")
    assert msg_type == "interactive"
    parsed = json.loads(payload)
    assert parsed["schema"] == "2.0"
    els = _els(parsed)
    assert els[0]["tag"] == "markdown"
    assert "echo hello" in els[0]["content"]


def test_fenced_code_plus_inline_code_uses_markdown_block():
    adapter = FeishuAdapter(PlatformConfig())
    msg_type, payload = adapter._build_outbound_payload("普通 `inline`\n```bash\necho `date`\n```")
    assert msg_type == "interactive"
    parsed = json.loads(payload)
    assert parsed["schema"] == "2.0"
    els = _els(parsed)
    assert els[0]["tag"] == "markdown"
    content = els[0]["content"]
    assert "`inline`" in content
    assert "echo `date`" in content


def test_table_with_code_uses_interactive_card():
    adapter = FeishuAdapter(PlatformConfig())
    msg_type, payload = adapter._build_outbound_payload("## 标题 `cmd`\n\n| 项 | 值 |\n|---|---|\n| 命令 | `hermes status` |")
    assert msg_type == "interactive"
    rendered = json.dumps(json.loads(payload), ensure_ascii=False)
    # markdown block preserves pipe table syntax for native rendering
    assert "|---|" in rendered
    assert "## 标题" not in rendered
    assert "`cmd`" in rendered
    assert "`hermes status`" in rendered


def test_table_inside_fence_stays_verbatim_in_markdown_block():
    adapter = FeishuAdapter(PlatformConfig())
    msg_type, payload = adapter._build_outbound_payload("```md\n| A | B |\n|---|---|\n```")
    assert msg_type == "interactive"
    parsed = json.loads(payload)
    assert parsed["schema"] == "2.0"
    els = _els(parsed)
    assert els[0]["tag"] == "markdown"
    assert "|---|---|" in els[0]["content"]
