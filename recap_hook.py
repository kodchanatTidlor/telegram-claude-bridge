import json
import os
import sys

from bridge.config import BASE_DIR, load_config
from bridge.recap import build_recap
from bridge.store import Store
from bridge.telegram import send_message
from bridge.transcript import parse_transcript


def _listener_alive(pid_path) -> bool:
    # recap is sent only when the listener is up — otherwise a reply could
    # never be delivered. The listener writes its pid here while running.
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


def run(stdin_text, env, cfg, store, send_fn, parse_fn) -> int:
    try:
        if not _listener_alive(cfg.pid_path):
            return 0
        iterm_session_id = env.get("ITERM_SESSION_ID")
        if not iterm_session_id:
            return 0
        payload = json.loads(stdin_text or "{}")
        transcript_path = payload.get("transcript_path", "")
        cwd = payload.get("cwd", "")
        user_prompt, assistant_text = parse_fn(transcript_path)
        text = build_recap(user_prompt, assistant_text)
        message_id = send_fn(cfg, text)
        job_pid = env.get("JOB_PID")
        store.upsert_session(iterm_session_id,
                             int(job_pid) if job_pid else None,
                             cwd, message_id)
    except Exception as exc:  # never block Claude
        sys.stderr.write(f"recap_hook error: {exc}\n")
    return 0


def main() -> int:
    # Cheap pid-file check before loading config, so a stopped listener or
    # missing .env never makes the hook do work or crash on Claude stop.
    pid_path = BASE_DIR / ".listener.pid"
    if not _listener_alive(pid_path):
        return 0
    cfg = load_config()
    store = Store(cfg.store_path)
    return run(sys.stdin.read(), dict(os.environ), cfg, store,
               send_message, parse_transcript)


if __name__ == "__main__":
    sys.exit(main())
