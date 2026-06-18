import os
import subprocess
import sys
from pathlib import Path

from bridge.config import load_config

BASE_DIR = Path(__file__).resolve().parent
VENV_PY = BASE_DIR / ".venv" / "bin" / "python"


def _python() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def _reap() -> None:
    # Telegram allows only one getUpdates poller per bot (else 409 Conflict).
    subprocess.run(["pkill", "-f", str(BASE_DIR / "listener.py")],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def listener_alive(pid_path) -> bool:
    try:
        pid = int(Path(pid_path).read_text().strip())
        os.kill(pid, 0)
        return True
    except (FileNotFoundError, ValueError, ProcessLookupError):
        return False
    except PermissionError:
        return True


def cmd_serve(cfg) -> None:
    # Foreground only: live log to this terminal, Ctrl+C to stop. Closing the
    # terminal stops the bridge — recap auto-disables (it gates on liveness).
    _reap()
    print("serving — Ctrl+C to stop\n")
    os.execv(_python(), [_python(), str(BASE_DIR / "listener.py")])


def cmd_status(cfg) -> str:
    # listener up == mirror + gate active; down == fully local. No separate
    # toggle: run `serve` to go remote, stop it to stay local.
    live = listener_alive(cfg.pid_path)
    state = "ON (listener up)" if live else "OFF (listener down)"
    return f"listener: {'RUNNING' if live else 'STOPPED'} | mirror+gate: {state}"


def cmd_update(cfg) -> None:
    # Pull latest code + refresh deps. Restart `serve` afterwards to load it.
    print("pulling latest...")
    if subprocess.run(["git", "-C", str(BASE_DIR), "pull", "--ff-only"]).returncode:
        print("git pull failed (stash/commit local changes first).")
        return
    print("updating dependencies...")
    subprocess.run([_python(), "-m", "pip", "install", "-q", "-r",
                    str(BASE_DIR / "requirements.txt")])
    print("updated. restart `python bridgectl.py serve` to load the new code.")


def main() -> int:
    cfg = load_config()
    arg = sys.argv[1] if len(sys.argv) > 1 else "status"
    if arg == "serve":
        cmd_serve(cfg)
    elif arg == "update":
        cmd_update(cfg)
    else:
        print(cmd_status(cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
