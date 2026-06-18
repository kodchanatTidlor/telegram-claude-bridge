import json
import os
import sys
import time

from bridge.config import BASE_DIR, load_config
from bridge.proc import listener_alive as _listener_alive
from bridge.store import Store
from bridge.stream import build_stream_text, new_text
from bridge.telegram import send_message

# On Stop the closing assistant message can still be mid-write — poll briefly
# so the final answer isn't missed (it would otherwise surface late, bundled
# with the next turn's first tool commentary).
STOP_FLUSH_TRIES = 15
STOP_FLUSH_WAIT = 0.2


def run(stdin_text, env, cfg, store, send_fn, text_fn, sleep_fn=time.sleep) -> int:
    try:
        if not _listener_alive(cfg.pid_path):
            return 0
        sid = env.get("ITERM_SESSION_ID")
        if not sid:
            return 0
        payload = json.loads(stdin_text or "{}")
        path = payload.get("transcript_path", "")
        if path:
            store.set_transcript(sid, path)   # so /status can read the model

        # Forward only what Claude SAID — assistant text written since the last
        # forwarded line. No tool chatter. Fires on PostToolUse (mid-turn
        # commentary) and on Stop (the closing answer), so the turn is mirrored
        # without a separate recap.
        is_stop = payload.get("hook_event_name") == "Stop"
        cursor = store.get_cursor(sid)
        text, new_cursor = text_fn(path, cursor)
        if not text and is_stop:
            for _ in range(STOP_FLUSH_TRIES):
                sleep_fn(STOP_FLUSH_WAIT)
                text, new_cursor = text_fn(path, cursor)
                if text:
                    break
        store.set_cursor(sid, new_cursor)
        if text:
            # Mid-turn commentary is silent; only the closing answer (Stop)
            # makes a sound.
            mid = send_fn(cfg, build_stream_text(text), silent=not is_stop)
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
