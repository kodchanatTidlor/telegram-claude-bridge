import json
import os
import sys
from functools import partial

from bridge import group
from bridge.activity import format_activity
from bridge.config import BASE_DIR, load_config
from bridge.proc import listener_alive as _listener_alive
from bridge.store import Store
from bridge.telegram import create_forum_topic, delete_message, send_message

# Tool finished / turn ended → remove the status message.
CLEAR_EVENTS = {"PostToolUse", "Stop"}


def _clear(cfg, store, sid, delete_fn) -> None:
    mid = store.pop_activity(sid)
    if mid is not None:
        delete_fn(cfg, mid)


def run(stdin_text, env, cfg, store, send_fn, delete_fn) -> int:
    """PreToolUse: post a (silent) status of what Claude is doing. PostToolUse/
    Stop: delete it. One self-cleaning line per tool, no chat clutter."""
    try:
        if not _listener_alive(cfg.pid_path):
            return 0
        sid = env.get("ITERM_SESSION_ID")
        if not sid:
            return 0
        payload = json.loads(stdin_text or "{}")
        event = payload.get("hook_event_name", "")
        if event == "PreToolUse":
            # Drop any leftover first (e.g. a denied tool never fires
            # PostToolUse), so at most one status is ever live.
            _clear(cfg, store, sid, delete_fn)
            thread = group.thread_for(
                cfg, store, sid, payload.get("cwd", ""),
                [s["iterm_session_id"] for s in store.sessions()],
                lambda n: create_forum_topic(cfg, n))
            mid = send_fn(cfg, format_activity(payload.get("tool_name", ""),
                                               payload.get("tool_input")),
                          message_thread_id=thread)
            store.set_activity(sid, mid)
        elif event in CLEAR_EVENTS:
            _clear(cfg, store, sid, delete_fn)
    except Exception as exc:  # never block Claude
        sys.stderr.write(f"activity_hook error: {exc}\n")
    return 0


def main() -> int:
    if not _listener_alive(BASE_DIR / ".listener.pid"):
        return 0
    cfg = load_config()
    store = Store(cfg.store_path)
    # Status pings shouldn't make a sound — they fire on every tool.
    silent_send = partial(send_message, silent=True)
    return run(sys.stdin.read(), dict(os.environ), cfg, store,
               silent_send, delete_message)


if __name__ == "__main__":
    sys.exit(main())
