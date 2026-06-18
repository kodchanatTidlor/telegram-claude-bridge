import json
from datetime import datetime, timezone

from bridge.usage import latest_model, usage_since


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


def _asst(ts, out, inp=0, cr=0, cc=0):
    return {"timestamp": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
            "message": {"role": "assistant", "model": "claude-opus-4-8",
                        "usage": {"output_tokens": out, "input_tokens": inp,
                                  "cache_read_input_tokens": cr,
                                  "cache_creation_input_tokens": cc}}}


def test_usage_since_sums_window_across_files(tmp_path):
    proj = tmp_path / "projects" / "p1"
    proj.mkdir(parents=True)
    now = 1_000_000.0
    rows = [
        _asst(now - 100, out=10, inp=5, cr=3, cc=2),    # in window
        _asst(now - 30_000, out=999),                   # >5h old → excluded
    ]
    (proj / "a.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    (proj / "b.jsonl").write_text(json.dumps(_asst(now - 50, out=7)))  # other file
    u = usage_since(tmp_path / "projects", since_ts=now - 5 * 3600)
    assert u["output"] == 17 and u["input"] == 5
    assert u["cache_read"] == 3 and u["cache_creation"] == 2
    assert u["total"] == 17 + 5 + 3 + 2 and u["messages"] == 2


def test_usage_since_missing_dir():
    u = usage_since("/nope/projects", since_ts=0)
    assert u["total"] == 0 and u["messages"] == 0


def test_fetch_usage_resolves_org_then_usage():
    from bridge import usage_api
    calls = []

    def fake_get(path, key):
        calls.append((path, key))
        if path == "/organizations":
            return [{"uuid": "ORG123"}]
        return {"five_hour": {"utilization": 50}}

    out = usage_api.fetch_usage("sk-ant-sid-x", get=fake_get)
    assert calls[0] == ("/organizations", "sk-ant-sid-x")
    assert calls[1] == ("/organizations/ORG123/usage", "sk-ant-sid-x")
    assert out["five_hour"]["utilization"] == 50
