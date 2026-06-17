from bridge.recap import build_recap, escape_md_v2, PROMPT_MAX


def test_escape_md_v2_escapes_specials():
    assert escape_md_v2("a_b*c.") == "a\\_b\\*c\\."


def test_build_recap_has_blockquote_and_body():
    out = build_recap("fix the bug", "all done")
    assert out.splitlines()[0].startswith(">")
    assert "fix the bug" in out
    assert "all done" in out


def test_build_recap_truncates_long_prompt():
    out = build_recap("x" * 500, "body")
    assert ("x" * PROMPT_MAX) in out
    assert ("x" * (PROMPT_MAX + 1)) not in out


def test_build_recap_empty_assistant_uses_placeholder():
    assert "no reply text" in build_recap("prompt", None)


def test_build_recap_no_prompt_omits_blockquote():
    out = build_recap(None, "body")
    assert not out.startswith(">")
    assert "body" in out
