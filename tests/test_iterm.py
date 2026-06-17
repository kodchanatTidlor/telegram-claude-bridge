from bridge.iterm import should_inject, strip_session_prefix, SHELL_JOB_NAMES


def test_strip_session_prefix():
    assert strip_session_prefix("w0t2p0:ABC-123") == "ABC-123"
    assert strip_session_prefix("ABC-123") == "ABC-123"


def test_inject_allowed_for_caffeinate():
    assert should_inject("caffeinate", 100, None) is True


def test_inject_allowed_for_node():
    assert should_inject("node", 100, None) is True


def test_inject_allowed_for_claude_subprocess():
    # while Claude works, jobName is whatever it spawned (git, python, ...)
    assert should_inject("git", 100, None) is True
    assert should_inject("python3.9", 100, None) is True


def test_inject_blocked_for_shells():
    for sh in ("zsh", "-zsh", "bash", "-bash", "sh", "fish", "login"):
        assert should_inject(sh, 100, None) is False, sh


def test_inject_blocked_when_job_unknown():
    assert should_inject(None, 100, None) is False


def test_inject_blocked_on_pid_mismatch():
    assert should_inject("caffeinate", 200, 100) is False


def test_shell_set_has_common_shells():
    assert {"zsh", "bash"} <= SHELL_JOB_NAMES
