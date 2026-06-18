import json
import os

from bridge.config import Config
from bridge import gate
import gate_hook


def make_cfg(tmp_path):
    return Config(bot_token="t", allowed_chat_id=1, poll_timeout=1,
                  store_path=tmp_path / "s.json",
                  flag_path=tmp_path / ".enabled",
                  pid_path=tmp_path / ".pid",
                  gate_dir=tmp_path / ".gate",
                  busy_path=tmp_path / ".busy")


def remote_up(cfg):
    cfg.pid_path.write_text(str(os.getpid()))   # listener alive == gate active


def test_passthrough_when_listener_down(tmp_path):
    cfg = make_cfg(tmp_path)                     # no pid file
    out = gate_hook.run('{"tool_name":"Bash"}', {"ITERM_SESSION_ID": "s"},
                        cfg, lambda c, t, **k: 1, lambda c, m: "y")
    assert out is None


def test_passthrough_when_auto_accept_mode(tmp_path):
    cfg = make_cfg(tmp_path)
    remote_up(cfg)
    sent = []
    payload = json.dumps({"tool_name": "Edit", "permission_mode": "acceptEdits"})
    out = gate_hook.run(payload, {"ITERM_SESSION_ID": "s"}, cfg,
                        lambda c, t, **k: sent.append(t) or 1, lambda c, m: "y")
    assert out is None and sent == []


def test_passthrough_for_unmatched_tool(tmp_path):
    cfg = make_cfg(tmp_path)
    remote_up(cfg)
    sent = []
    out = gate_hook.run('{"tool_name":"Read"}', {"ITERM_SESSION_ID": "s"},
                        cfg, lambda c, t, **k: sent.append(t) or 1, lambda c, m: "y")
    assert out is None and sent == []


def test_permission_allow(tmp_path):
    cfg = make_cfg(tmp_path)
    remote_up(cfg)
    payload = json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": "ls"}})
    out = gate_hook.run(payload, {"ITERM_SESSION_ID": "s"}, cfg,
                        lambda c, t, **k: 10, lambda c, m: "y")
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_permission_deny(tmp_path):
    cfg = make_cfg(tmp_path)
    remote_up(cfg)
    payload = json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": "rm -rf /"}})
    out = gate_hook.run(payload, {"ITERM_SESSION_ID": "s"}, cfg,
                        lambda c, t, **k: 11, lambda c, m: "n")
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_question_answer_feeds_reason(tmp_path):
    cfg = make_cfg(tmp_path)
    remote_up(cfg)
    payload = json.dumps({"tool_name": "AskUserQuestion", "tool_input": {
        "questions": [{"question": "pick", "options": [
            {"label": "alpha"}, {"label": "beta"}]}]}})
    out = gate_hook.run(payload, {"ITERM_SESSION_ID": "s"}, cfg,
                        lambda c, t, **k: 12, lambda c, m: "2")
    od = out["hookSpecificOutput"]
    assert od["permissionDecision"] == "deny"
    assert "beta" in od["permissionDecisionReason"]
    assert "do not call AskUserQuestion again" in od["permissionDecisionReason"]


def test_timeout_clears_pending_and_passes_through(tmp_path):
    cfg = make_cfg(tmp_path)
    remote_up(cfg)
    sent_id = 99
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "x"}})
    out = gate_hook.run(payload, {"ITERM_SESSION_ID": "s"}, cfg,
                        lambda c, t, **k: sent_id, lambda c, m: None)  # never answers
    assert out is None
    assert gate.pending_exists(cfg, sent_id) is False
