PROMPT_MAX = 300
_SPECIALS = r"_*[]()~`>#+-=|{}.!"


def escape_md_v2(text: str) -> str:
    out = []
    for ch in text:
        out.append("\\" + ch if ch in _SPECIALS else ch)
    return "".join(out)


EMPTY_BODY = escape_md_v2("[done — no reply text]")


def build_recap(user_prompt, assistant_text) -> str:
    body = escape_md_v2(assistant_text) if assistant_text else EMPTY_BODY
    if user_prompt:
        clipped = user_prompt[:PROMPT_MAX]
        lines = clipped.splitlines() or [""]
        quote = "\n".join(">" + escape_md_v2(ln) for ln in lines)
        return f"{quote}\n\n{body}"
    return body
