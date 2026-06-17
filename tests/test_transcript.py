import json
from bridge.transcript import parse_transcript


def write_jsonl(tmp_path, rows):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    return str(p)


def test_extracts_last_user_and_assistant(tmp_path):
    rows = [
        {"type": "user", "message": {"role": "user", "content": "first"}},
        {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "text", "text": "hi"}]}},
        {"type": "user", "message": {"role": "user", "content": "second"}},
        {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "text", "text": "done "},
                        {"type": "text", "text": "ok"}]}},
    ]
    user, asst = parse_transcript(write_jsonl(tmp_path, rows))
    assert user == "second"
    assert asst == "done ok"


def test_skips_tool_result_user_lines(tmp_path):
    rows = [
        {"type": "user", "message": {"role": "user", "content": "real prompt"}},
        {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "tool_use", "name": "X"}]}},
        {"type": "user", "message": {"role": "user",
            "content": [{"type": "tool_result", "content": "out"}]}},
        {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "text", "text": "final"}]}},
    ]
    user, asst = parse_transcript(write_jsonl(tmp_path, rows))
    assert user == "real prompt"
    assert asst == "final"


def test_missing_file_returns_none(tmp_path):
    user, asst = parse_transcript(str(tmp_path / "nope.jsonl"))
    assert user is None and asst is None


def test_empty_assistant_text_returns_none(tmp_path):
    rows = [{"type": "assistant", "message": {"role": "assistant",
             "content": [{"type": "tool_use", "name": "X"}]}}]
    user, asst = parse_transcript(write_jsonl(tmp_path, rows))
    assert asst is None
