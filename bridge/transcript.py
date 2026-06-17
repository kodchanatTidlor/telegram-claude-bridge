import json
from pathlib import Path
from typing import Optional, Tuple


def _text_blocks(content) -> Optional[str]:
    if isinstance(content, str):
        return content or None
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        joined = "".join(parts)
        return joined or None
    return None


def _is_tool_result_only(content) -> bool:
    if not isinstance(content, list) or not content:
        return False
    return all(isinstance(b, dict) and b.get("type") == "tool_result"
               for b in content)


def parse_transcript(path: str) -> Tuple[Optional[str], Optional[str]]:
    p = Path(path)
    if not p.exists():
        return None, None
    user_prompt = None
    assistant_text = None
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = row.get("message") or {}
        role = msg.get("role")
        content = msg.get("content")
        if role == "user":
            if _is_tool_result_only(content):
                continue
            text = _text_blocks(content)
            if text is not None:
                user_prompt = text
        elif role == "assistant":
            text = _text_blocks(content)
            if text is not None:
                assistant_text = text
    return user_prompt, assistant_text
