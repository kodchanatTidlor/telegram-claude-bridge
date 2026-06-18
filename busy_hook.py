import json
import sys

from bridge.busy import clear_busy, set_busy
from bridge.config import BASE_DIR, load_config
from bridge.proc import listener_alive as _listener_alive

# Working → typing bubble on. Paused/done → off (its absence = "your turn").
# SubagentStop is NOT a turn end — the main agent keeps orchestrating, so it
# must not stop the typing bubble.
SET_EVENTS = {"UserPromptSubmit", "PostToolUse"}
CLEAR_EVENTS = {"Stop", "Notification"}


def run(stdin_text, cfg) -> int:
    try:
        event = json.loads(stdin_text or "{}").get("hook_event_name", "")
        if event in SET_EVENTS:
            set_busy(cfg)
        elif event in CLEAR_EVENTS:
            clear_busy(cfg)
    except Exception as exc:  # never block Claude
        sys.stderr.write(f"busy_hook error: {exc}\n")
    return 0


def main() -> int:
    # Only matters while the listener (which sends the typing action) is up.
    if not _listener_alive(BASE_DIR / ".listener.pid"):
        return 0
    return run(sys.stdin.read(), load_config())


if __name__ == "__main__":
    sys.exit(main())
