# Inject guard: a reply must reach a live Claude session, never a bare shell.
# We use a BLOCKLIST, not an allowlist: the session's foreground jobName is
# the deepest foreground process of the tty, which while Claude works is
# whatever subprocess Claude spawned (git, python, node, a bash tool, or
# `caffeinate` when idle) — too many to allowlist. But when Claude has
# EXITED, the tty drops back to the login shell. So we block only shells.
SHELL_JOB_NAMES = {
    "zsh", "-zsh", "bash", "-bash", "sh", "-sh",
    "fish", "-fish", "login", "tcsh", "-tcsh",
}


def strip_session_prefix(env_value: str) -> str:
    return env_value.split(":", 1)[1] if ":" in env_value else env_value


def should_inject(job_name, job_pid, expected_pid) -> bool:
    if job_name is None:
        return False
    base = job_name.rsplit("/", 1)[-1].lower()
    if base in SHELL_JOB_NAMES:
        return False  # dropped to a bare shell — Claude is gone
    if expected_pid is not None and job_pid != expected_pid:
        return False
    return True
