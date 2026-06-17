import json
import os
import sys

from bridge.config import BASE_DIR, load_config
from bridge.recap import build_notify
from bridge.store import Store
from bridge.telegram import send_message


def _listener_alive(pid_path) -> bool:
    # Mirror recap_hook: only notify when the listener is up, otherwise a
    # reply could never be delivered. Listener writes its pid here.
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


def run(stdin_text, env, cfg, store, send_fn) -> int:
    try:
        if not _listener_alive(cfg.pid_path):
            return 0
        iterm_session_id = env.get("ITERM_SESSION_ID")
        if not iterm_session_id:
            return 0
        payload = json.loads(stdin_text or "{}")
        message = payload.get("message", "")
        cwd = payload.get("cwd", "")
        text = build_notify(message)
        message_id = send_fn(cfg, text)
        job_pid = env.get("JOB_PID")
        # Bind message_id to the session so a Telegram reply routes the answer
        # straight back into the waiting prompt (session_by_recap).
        store.upsert_session(iterm_session_id,
                             int(job_pid) if job_pid else None,
                             cwd, message_id)
    except Exception as exc:  # never block Claude
        sys.stderr.write(f"notify_hook error: {exc}\n")
    return 0


def main() -> int:
    pid_path = BASE_DIR / ".listener.pid"
    if not _listener_alive(pid_path):
        return 0
    cfg = load_config()
    store = Store(cfg.store_path)
    return run(sys.stdin.read(), dict(os.environ), cfg, store, send_message)


if __name__ == "__main__":
    sys.exit(main())
