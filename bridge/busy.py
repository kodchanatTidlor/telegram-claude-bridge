import time

# Staleness guard: if Claude dies without a Stop hook the flag would linger,
# so a busy flag older than this counts as not-busy. PostToolUse touches it,
# keeping long but active turns fresh.
MAX_BUSY_AGE = 900.0


def set_busy(cfg) -> None:
    cfg.busy_path.write_text(str(time.time()))


def clear_busy(cfg) -> None:
    cfg.busy_path.unlink(missing_ok=True)


def is_busy(cfg, now=None, max_age=MAX_BUSY_AGE) -> bool:
    try:
        ts = float(cfg.busy_path.read_text())
    except (FileNotFoundError, ValueError, OSError):
        return False
    return (time.time() if now is None else now) - ts < max_age
