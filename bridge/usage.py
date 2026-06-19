import json
from pathlib import Path


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
