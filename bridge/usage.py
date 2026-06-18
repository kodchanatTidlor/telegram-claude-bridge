import json
from datetime import datetime
from pathlib import Path


def _parse_ts(s):
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def usage_since(projects_dir, since_ts):
    """Sum token usage across ALL transcripts for assistant messages newer than
    since_ts — same data source ccusage reads (~/.claude/projects/**/*.jsonl)."""
    agg = {"input": 0, "output": 0, "cache_read": 0,
           "cache_creation": 0, "messages": 0}
    p = Path(projects_dir)
    if not p.exists():
        return {**agg, "total": 0}
    for f in p.rglob("*.jsonl"):
        try:
            lines = f.read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _parse_ts(row.get("timestamp"))
            if ts is None or ts < since_ts:
                continue
            msg = row.get("message") or {}
            if msg.get("role") != "assistant":
                continue
            u = msg.get("usage") or {}
            agg["input"] += u.get("input_tokens", 0)
            agg["output"] += u.get("output_tokens", 0)
            agg["cache_read"] += u.get("cache_read_input_tokens", 0)
            agg["cache_creation"] += u.get("cache_creation_input_tokens", 0)
            agg["messages"] += 1
    agg["total"] = (agg["input"] + agg["output"]
                    + agg["cache_read"] + agg["cache_creation"])
    return agg


def latest_model(path):
    """The model of the most recent assistant message in the transcript, or
    None. Short name (drops the 'claude-' prefix) for display."""
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    model = None
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = row.get("message") or {}
        if msg.get("role") == "assistant" and msg.get("model"):
            model = msg["model"]
    return model.replace("claude-", "") if model else None
