import json
import os
import sys
import time

from bridge.config import BASE_DIR, load_config
from bridge.gate import (PERMISSION_TOOLS, QUESTION_TOOL, build_permission_msg,
                         build_question_msg, clear_pending, interpret_permission,
                         interpret_question, question_options,
                         register_pending, take_answer)
from bridge.telegram import send_message

WAIT_TIMEOUT = 540.0   # < the hook's settings.json timeout (600s)
POLL_EVERY = 0.5

# PreToolUse fires for matched tools regardless of whether the tool would
# actually prompt. Only "default" mode prompts; the others auto-accept (or
# don't execute), so gating them would nag for approvals nobody asked for.
GATED_MODES = {"default", ""}


def _listener_alive(pid_path) -> bool:
    try:
        pid = int(pid_path.read_text().strip())
    except (FileNotFoundError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _decision(decision, reason):
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}


def wait_for_answer(cfg, message_id):
    # Poll the answer file the listener writes when the user replies. The
    # listener owns the single Telegram poller, so we never call getUpdates.
    deadline = time.monotonic() + WAIT_TIMEOUT
    while time.monotonic() < deadline:
        answer = take_answer(cfg, message_id)
        if answer is not None:
            return answer
        time.sleep(POLL_EVERY)
    return None


def run(stdin_text, env, cfg, send_fn, wait_fn):
    """Return a PreToolUse decision dict, or None to defer to normal flow."""
    try:
        if not _listener_alive(cfg.pid_path):
            return None
        if not env.get("ITERM_SESSION_ID"):
            # listener is up but this isn't an iTerm session it can reach — the
            # gate can't fire. Surface it so the operator isn't lulled.
            sys.stderr.write("gate_hook: listener up but no ITERM_SESSION_ID"
                             " — gate inactive, tool runs locally\n")
            return None
        payload = json.loads(stdin_text or "{}")
        if payload.get("permission_mode", "") not in GATED_MODES:
            return None   # acceptEdits / bypassPermissions / plan → don't nag
        tool_name = payload.get("tool_name", "")
        tool_input = payload.get("tool_input") or {}

        if tool_name == QUESTION_TOOL:
            kind = "question"
            msg = build_question_msg(tool_input)
        elif tool_name in PERMISSION_TOOLS:
            kind = "permission"
            msg = build_permission_msg(tool_name, tool_input)
        else:
            return None

        message_id = send_fn(cfg, msg)
        register_pending(cfg, message_id, {"kind": kind})
        answer = wait_fn(cfg, message_id)
        if answer is None:
            clear_pending(cfg, message_id)   # timeout → TUI menu shows locally
            return None

        if kind == "permission":
            decision, reason = interpret_permission(answer)
            return _decision(decision, reason)

        # question: deny is the only channel back, so the reason both carries
        # the answer AND stops Claude re-asking THIS question (would re-trigger).
        chosen = interpret_question(answer, question_options(tool_input))
        reason = (f"User answered via Telegram: {chosen}. "
                  "Use this answer and do not call AskUserQuestion again "
                  "for this question.")
        return _decision("deny", reason)
    except Exception as exc:  # never block Claude
        sys.stderr.write(f"gate_hook error: {exc}\n")
        return None


def main() -> int:
    pid_path = BASE_DIR / ".listener.pid"
    if not _listener_alive(pid_path):
        return 0
    cfg = load_config()
    result = run(sys.stdin.read(), dict(os.environ), cfg,
                 send_message, wait_for_answer)
    if result is not None:
        sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
