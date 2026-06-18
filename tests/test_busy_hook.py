import json

from bridge.config import Config
from bridge import busy
import busy_hook


def make_cfg(tmp_path):
    return Config(bot_token="t", allowed_chat_id=1, poll_timeout=1,
                  store_path=tmp_path / "s.json",
                  flag_path=tmp_path / ".enabled",
                  pid_path=tmp_path / ".pid",
                  busy_path=tmp_path / ".busy")


def test_user_prompt_sets_busy(tmp_path):
    cfg = make_cfg(tmp_path)
    busy_hook.run(json.dumps({"hook_event_name": "UserPromptSubmit"}), cfg)
    assert busy.is_busy(cfg) is True


def test_post_tool_use_keeps_busy(tmp_path):
    cfg = make_cfg(tmp_path)
    busy_hook.run(json.dumps({"hook_event_name": "PostToolUse"}), cfg)
    assert busy.is_busy(cfg) is True


def test_stop_clears_busy(tmp_path):
    cfg = make_cfg(tmp_path)
    busy.set_busy(cfg)
    busy_hook.run(json.dumps({"hook_event_name": "Stop"}), cfg)
    assert busy.is_busy(cfg) is False


def test_notification_clears_busy(tmp_path):
    cfg = make_cfg(tmp_path)
    busy.set_busy(cfg)
    busy_hook.run(json.dumps({"hook_event_name": "Notification"}), cfg)
    assert busy.is_busy(cfg) is False


def test_unknown_event_is_noop(tmp_path):
    cfg = make_cfg(tmp_path)
    busy.set_busy(cfg)
    busy_hook.run(json.dumps({"hook_event_name": "PreToolUse"}), cfg)
    assert busy.is_busy(cfg) is True   # left unchanged
