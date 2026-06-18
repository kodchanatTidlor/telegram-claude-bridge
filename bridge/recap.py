PROMPT_MAX = 300
_SPECIALS = r"_*[]()~`>#+-=|{}.!"


def escape_md_v2(text: str) -> str:
    out = []
    for ch in text:
        out.append("\\" + ch if ch in _SPECIALS else ch)
    return "".join(out)


NOTIFY_DEFAULT = "Claude is waiting for your input"


def build_notify(message) -> str:
    # Claude paused for input (permission prompt / idle / asking). Reply to
    # this message in Telegram to route the answer back into the session.
    text = (message or NOTIFY_DEFAULT)[:PROMPT_MAX]
    return f"⏸ {escape_md_v2(text)}"
