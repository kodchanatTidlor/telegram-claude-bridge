from bridge.config import Config
from bridge import gate


def make_cfg(tmp_path):
    return Config(bot_token="t", allowed_chat_id=1, poll_timeout=1,
                  store_path=tmp_path / "s.json",
                  flag_path=tmp_path / ".enabled",
                  pid_path=tmp_path / ".pid",
                  gate_dir=tmp_path / ".gate")


# --- pending / answer IPC round-trip ---

def test_pending_resolve_take_roundtrip(tmp_path):
    cfg = make_cfg(tmp_path)
    gate.register_pending(cfg, 100, {"kind": "permission"})
    assert gate.pending_exists(cfg, 100) is True
    # listener side: a reply arrives
    gate.resolve_pending(cfg, 100, "yes")
    assert gate.pending_exists(cfg, 100) is False     # pending cleared
    # hook side: consume the answer
    assert gate.take_answer(cfg, 100) == "yes"
    assert gate.take_answer(cfg, 100) is None          # consumed once


def test_ipc_files_are_private(tmp_path):
    cfg = make_cfg(tmp_path)
    gate.register_pending(cfg, 100, {"kind": "permission"})
    gate.resolve_pending(cfg, 100, "yes")
    ans = cfg.gate_dir / "answer" / "100.json"
    assert (ans.stat().st_mode & 0o077) == 0        # no group/other access
    assert (cfg.gate_dir / "answer").stat().st_mode & 0o077 == 0


def test_clear_pending(tmp_path):
    cfg = make_cfg(tmp_path)
    gate.register_pending(cfg, 7, {"kind": "question"})
    gate.clear_pending(cfg, 7)
    assert gate.pending_exists(cfg, 7) is False


def test_resolve_unknown_pending_is_noop(tmp_path):
    cfg = make_cfg(tmp_path)
    gate.resolve_pending(cfg, 999, "x")        # nothing pending
    assert gate.take_answer(cfg, 999) is None


# --- permission interpretation ---

def test_interpret_permission_allow_variants():
    for t in ["y", "yes", "1", "ok", "Y", " yes "]:
        decision, _ = gate.interpret_permission(t)
        assert decision == "allow"


def test_interpret_permission_deny_variants():
    for t in ["n", "no", "2", "deny"]:
        decision, _ = gate.interpret_permission(t)
        assert decision == "deny"


def test_interpret_permission_freetext_denies_with_reason():
    decision, reason = gate.interpret_permission("no, use ruff instead")
    assert decision == "deny" and "ruff" in reason


# --- question interpretation ---

def test_interpret_question_by_number():
    assert gate.interpret_question("2", ["alpha", "beta"]) == "beta"


def test_interpret_question_by_label():
    assert gate.interpret_question("alpha", ["alpha", "beta"]) == "alpha"


def test_interpret_question_freetext_is_custom():
    assert gate.interpret_question("something else", ["a", "b"]) == "something else"


def test_interpret_question_out_of_range_is_custom():
    assert gate.interpret_question("9", ["a", "b"]) == "9"


# --- message builders ---

def test_build_permission_msg_shows_tool_and_arg():
    out = gate.build_permission_msg("Bash", {"command": "rm -rf x"})
    assert "Bash" in out and "rm" in out


def test_permission_keyboard_has_allow_deny():
    kb = gate.permission_keyboard()["inline_keyboard"][0]
    data = {b["callback_data"] for b in kb}
    assert data == {"y", "n"}


def test_question_keyboard_indexes_options():
    kb = gate.question_keyboard(["alpha", "beta"])["inline_keyboard"]
    assert kb[0][0]["callback_data"] == "1" and "alpha" in kb[0][0]["text"]
    assert kb[1][0]["callback_data"] == "2"


def test_question_keyboard_empty_is_none():
    assert gate.question_keyboard([]) is None
