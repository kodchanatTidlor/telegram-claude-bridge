import json
from pathlib import Path

from bridge.recap import escape_md_v2

# Tools whose calls are gated to Telegram in remote mode. AskUserQuestion is
# always a question; the rest are the state-changing tools worth approving.
PERMISSION_TOOLS = {"Bash", "Write", "Edit", "NotebookEdit", "MultiEdit"}
QUESTION_TOOL = "AskUserQuestion"

_ALLOW_WORDS = {"y", "yes", "ok", "okay", "1", "allow", "approve", "👍"}
_DENY_WORDS = {"n", "no", "2", "deny", "stop", "👎"}
ARG_MAX = 200
_ARG_KEYS = ("command", "file_path", "path", "pattern", "url")


# --- IPC: one file per request, keyed by the Telegram message_id ----------

def _key(message_id) -> str:
    # Coerce to a plain integer string: forecloses any path-traversal via a
    # malformed id, even though Telegram message_ids are always integers.
    return str(int(message_id))


def _pending_path(cfg, message_id) -> Path:
    return cfg.gate_dir / "pending" / f"{_key(message_id)}.json"


def _answer_path(cfg, message_id) -> Path:
    return cfg.gate_dir / "answer" / f"{_key(message_id)}.json"


def _write_private(path: Path, data: str) -> None:
    # 0o700 dir / 0o600 file: IPC payloads carry tool args + the user's reply,
    # keep them off a shared machine's world-readable default.
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(data)
    path.chmod(0o600)


def register_pending(cfg, message_id, record) -> None:
    _write_private(_pending_path(cfg, message_id), json.dumps(record))


def pending_exists(cfg, message_id) -> bool:
    return _pending_path(cfg, message_id).exists()


def resolve_pending(cfg, message_id, text) -> bool:
    """listener side: a reply arrived — hand the raw text to the waiting hook.

    Returns False if nothing was pending for this id.
    """
    if not pending_exists(cfg, message_id):
        return False
    _write_private(_answer_path(cfg, message_id), json.dumps({"text": text}))
    _pending_path(cfg, message_id).unlink(missing_ok=True)
    return True


def take_answer(cfg, message_id):
    """hook side: consume the answer text once, or None if not yet there."""
    a = _answer_path(cfg, message_id)
    if not a.exists():
        return None
    try:
        text = json.loads(a.read_text()).get("text")
    except (json.JSONDecodeError, OSError):
        text = None
    a.unlink(missing_ok=True)
    return text


def clear_pending(cfg, message_id) -> None:
    _pending_path(cfg, message_id).unlink(missing_ok=True)
    _answer_path(cfg, message_id).unlink(missing_ok=True)


# --- answer interpretation -----------------------------------------------

def interpret_permission(text):
    """Map a Telegram reply to (decision, reason). Ambiguous → deny (safe)."""
    norm = (text or "").strip().lower()
    if norm in _ALLOW_WORDS:
        return "allow", ""
    if norm in _DENY_WORDS:
        return "deny", "User declined via Telegram."
    # Free text: treat as a denial that carries instructions back to Claude.
    return "deny", (text or "").strip()


def interpret_question(text, options):
    """Number → option label; exact label → itself; anything else → custom."""
    raw = (text or "").strip()
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return options[idx]
        return raw
    for opt in options:
        if raw.lower() == opt.lower():
            return opt
    return raw


# --- message builders -----------------------------------------------------

def _tool_arg(tool_input):
    inp = tool_input or {}
    for key in _ARG_KEYS:
        val = inp.get(key)
        if val:
            return str(val).splitlines()[0][:ARG_MAX]
    return ""


def build_permission_msg(tool_name, tool_input) -> str:
    arg = _tool_arg(tool_input)
    head = f"🔐 *{escape_md_v2(tool_name or 'tool')}* needs permission"
    body = f"\n`{escape_md_v2(arg)}`" if arg else ""
    return f"{head}{body}\n\nreply *y* / *n* \\(or tell Claude what to do\\)"


def build_question_msg(tool_input) -> str:
    inp = tool_input or {}
    lines = ["❓ *Claude is asking*"]
    for q in inp.get("questions") or []:
        lines.append(escape_md_v2(q.get("question", "")))
        for i, opt in enumerate(q.get("options") or [], 1):
            lines.append(f"{i}\\. {escape_md_v2(opt.get('label', ''))}")
    lines.append("\nreply with a number or your own answer")
    return "\n".join(lines)


def question_options(tool_input):
    """Flat list of option labels across all questions (first question wins
    for the common single-question case)."""
    inp = tool_input or {}
    out = []
    for q in inp.get("questions") or []:
        for opt in q.get("options") or []:
            out.append(opt.get("label", ""))
    return out
