import json
from pathlib import Path

import telegramify_markdown

from bridge.recap import escape_md_v2

STREAM_MAX = 3000        # Telegram hard cap is 4096; leave room for escaping.


def new_text(path, start_line):
    """Join assistant text blocks in lines[start_line:].

    Returns (text_or_None, total_line_count). The line count is the new
    cursor — advance past everything read so the next call starts fresh.
    """
    p = Path(path)
    if not p.exists():
        return None, start_line
    lines = p.read_text().splitlines()
    parts = []
    for line in lines[start_line:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = row.get("message") or {}
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            if content.strip():
                parts.append(content)
        elif isinstance(content, list):
            for b in content:
                if (isinstance(b, dict) and b.get("type") == "text"
                        and b.get("text", "").strip()):
                    parts.append(b["text"])
    text = "\n\n".join(parts) if parts else None
    return text, len(lines)


def build_stream_text(text) -> str:
    # Claude writes CommonMark; Telegram wants MarkdownV2. telegramify converts
    # and escapes (bold/headers/lists/code/blockquote). Fall back to a plain
    # escape if conversion ever fails, so a turn is never dropped.
    clipped = text[:STREAM_MAX]
    try:
        return telegramify_markdown.markdownify(clipped)
    except Exception:
        return escape_md_v2(clipped)
