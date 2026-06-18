import os


def listener_alive(pid_path) -> bool:
    # Hooks only do work while the listener (which owns the Telegram poller and
    # sends side-channel messages) is up. Shared by every hook entry point.
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
