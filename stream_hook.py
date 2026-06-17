import json
import os
import sys

from bridge.config import BASE_DIR, load_config
from bridge.store import Store
from bridge.stream import build_stream_text, new_text
from bridge.telegram import send_message


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


def run(stdin_text, env, cfg, store, send_fn, text_fn) -> int:
    try:
        if not _listener_alive(cfg.pid_path):
            return 0
        sid = env.get("ITERM_SESSION_ID")
        if not sid:
            return 0
        payload = json.loads(stdin_text or "{}")
        path = payload.get("transcript_path", "")

        # Forward only what Claude SAID — assistant text written since the last
        # forwarded line. No tool chatter. Fires on PostToolUse (mid-turn
        # commentary) and on Stop (the closing answer), so the turn is mirrored
        # without a separate recap.
        text, new_cursor = text_fn(path, store.get_cursor(sid))
        store.set_cursor(sid, new_cursor)
        if text:
            mid = send_fn(cfg, build_stream_text(text))
            # Bind the message_id so a Telegram reply routes back here.
            job_pid = env.get("JOB_PID")
            store.upsert_session(sid, int(job_pid) if job_pid else None,
                                 payload.get("cwd", ""), mid)
    except Exception as exc:  # never block Claude
        sys.stderr.write(f"stream_hook error: {exc}\n")
    return 0


def main() -> int:
    pid_path = BASE_DIR / ".listener.pid"
    if not _listener_alive(pid_path):
        return 0
    cfg = load_config()
    store = Store(cfg.store_path)
    return run(sys.stdin.read(), dict(os.environ), cfg, store,
               send_message, new_text)


if __name__ == "__main__":
    sys.exit(main())
