import json

from bridge.stream import build_stream_text, new_text


def write_jsonl(tmp_path, rows):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    return str(p)


def test_new_text_joins_assistant_blocks_after_cursor(tmp_path):
    rows = [
        {"message": {"role": "user", "content": "go"}},
        {"message": {"role": "assistant",
                     "content": [{"type": "text", "text": "checking"}]}},
        {"message": {"role": "assistant",
                     "content": [{"type": "text", "text": "now editing"}]}},
    ]
    path = write_jsonl(tmp_path, rows)
    text, cursor = new_text(path, 0)
    assert text == "checking\n\nnow editing"
    assert cursor == 3


def test_new_text_respects_cursor(tmp_path):
    rows = [
        {"message": {"role": "assistant",
                     "content": [{"type": "text", "text": "old"}]}},
        {"message": {"role": "assistant",
                     "content": [{"type": "text", "text": "fresh"}]}},
    ]
    path = write_jsonl(tmp_path, rows)
    text, cursor = new_text(path, 1)
    assert text == "fresh" and cursor == 2


def test_new_text_ignores_tool_use_and_user(tmp_path):
    rows = [
        {"message": {"role": "user", "content": "x"}},
        {"message": {"role": "assistant",
                     "content": [{"type": "tool_use", "name": "Bash"}]}},
    ]
    text, cursor = new_text(write_jsonl(tmp_path, rows), 0)
    assert text is None and cursor == 2


def test_new_text_missing_file(tmp_path):
    text, cursor = new_text(str(tmp_path / "nope.jsonl"), 5)
    assert text is None and cursor == 5


def test_build_stream_text_clips_and_escapes():
    out = build_stream_text("a." * 5000)
    assert "\\." in out and len(out) < 7000          # dot escaped for MarkdownV2


def test_build_stream_text_renders_markdown():
    out = build_stream_text("**bold** and `code`")
    assert "*bold*" in out and "`code`" in out        # CommonMark -> MarkdownV2
