import json
import os

from bridge.config import Config
from bridge.store import Store
from bridge.activity import format_activity
import activity_hook


def make_cfg(tmp_path):
    return Config(bot_token="t", allowed_chat_id=1, poll_timeout=1,
                  store_path=tmp_path / "s.json",
                  flag_path=tmp_path / ".enabled",
                  pid_path=tmp_path / ".pid")


def up(cfg):
    cfg.pid_path.write_text(str(os.getpid()))


def fns(sent, deleted):
    return (lambda c, t, message_thread_id=None: sent.append(t) or (len(sent)),
            lambda c, m: deleted.append(m))                # delete_fn


def test_format_activity_maps_verb_and_arg():
    out = format_activity("Edit", {"file_path": "/x/y.py"})
    assert "editing" in out and "y\\.py" in out


def test_format_activity_unknown_tool_falls_back():
    assert "Frobnicate" in format_activity("Frobnicate", {})


def test_store_activity_roundtrip(tmp_path):
    store = Store((tmp_path / "s.json"))
    store.set_activity("sid", 7)
    assert store.pop_activity("sid") == 7
    assert store.pop_activity("sid") is None


def test_pretooluse_sends_and_stores(tmp_path):
    cfg = make_cfg(tmp_path)
    up(cfg)
    store = Store(cfg.store_path)
    sent, deleted = [], []
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Grep",
                          "tool_input": {"pattern": "foo"}})
    activity_hook.run(payload, {"ITERM_SESSION_ID": "sid"}, cfg, store,
                      *fns(sent, deleted))
    assert sent and "searching" in sent[0]
    assert store.pop_activity("sid") == 1


def test_posttooluse_deletes(tmp_path):
    cfg = make_cfg(tmp_path)
    up(cfg)
    store = Store(cfg.store_path)
    store.set_activity("sid", 44)
    sent, deleted = [], []
    activity_hook.run('{"hook_event_name":"PostToolUse"}',
                      {"ITERM_SESSION_ID": "sid"}, cfg, store, *fns(sent, deleted))
    assert deleted == [44] and store.pop_activity("sid") is None


def test_pretooluse_clears_stale_first(tmp_path):
    cfg = make_cfg(tmp_path)
    up(cfg)
    store = Store(cfg.store_path)
    store.set_activity("sid", 10)          # leftover from a denied tool
    sent, deleted = [], []
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Read",
                          "tool_input": {"file_path": "/a"}})
    activity_hook.run(payload, {"ITERM_SESSION_ID": "sid"}, cfg, store,
                      *fns(sent, deleted))
    assert deleted == [10]                  # stale dropped
    assert store.pop_activity("sid") == 1   # replaced with the new one


def test_stop_deletes_status(tmp_path):
    cfg = make_cfg(tmp_path)
    up(cfg)
    store = Store(cfg.store_path)
    store.set_activity("sid", 99)
    sent, deleted = [], []
    activity_hook.run('{"hook_event_name":"Stop"}', {"ITERM_SESSION_ID": "sid"},
                      cfg, store, *fns(sent, deleted))
    assert deleted == [99] and store.pop_activity("sid") is None


def test_skips_when_listener_down(tmp_path):
    cfg = make_cfg(tmp_path)            # no pid
    sent, deleted = [], []
    activity_hook.run('{"hook_event_name":"PreToolUse"}',
                      {"ITERM_SESSION_ID": "sid"}, cfg, Store(cfg.store_path),
                      *fns(sent, deleted))
    assert sent == []
