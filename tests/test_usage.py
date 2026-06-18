import json

from bridge.usage import latest_model


def write(tmp_path, rows):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    return str(p)


def test_latest_model_short_name(tmp_path):
    rows = [
        {"message": {"role": "assistant", "model": "claude-sonnet-4-6",
                     "content": []}},
        {"message": {"role": "assistant", "model": "claude-opus-4-8",
                     "content": []}},
    ]
    assert latest_model(write(tmp_path, rows)) == "opus-4-8"   # last wins, trimmed


def test_latest_model_none_when_no_assistant(tmp_path):
    rows = [{"message": {"role": "user", "content": "hi"}}]
    assert latest_model(write(tmp_path, rows)) is None


def test_latest_model_missing_file():
    assert latest_model("/nope.jsonl") is None
    assert latest_model(None) is None
