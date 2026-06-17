import json
import os

from bridge.config import Config
from bridge.recap import build_notify
from bridge.store import Store
import notify_hook


def make_cfg(tmp_path):
    return Config(bot_token="t", allowed_chat_id=1, poll_timeout=1,
                  store_path=tmp_path / "s.json",
                  flag_path=tmp_path / ".enabled",
                  pid_path=tmp_path / ".pid")


def test_build_notify_default_and_prefix():
    assert build_notify("").startswith("⏸")
    assert "waiting" in build_notify("")
    assert "permission" in build_notify("need permission")


def test_skips_when_listener_down(tmp_path):
    cfg = make_cfg(tmp_path)
    sent = []
    code = notify_hook.run('{"message":"x"}', {"ITERM_SESSION_ID": "s"},
                           cfg, Store(cfg.store_path),
                           lambda c, t: sent.append(t))
    assert code == 0 and sent == []


def test_sends_and_binds_session(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.pid_path.write_text(str(os.getpid()))
    store = Store(cfg.store_path)
    sent = []
    payload = json.dumps({"message": "needs permission to use Bash",
                          "cwd": "/c"})
    code = notify_hook.run(payload, {"ITERM_SESSION_ID": "s1", "JOB_PID": "3"},
                           cfg, store, lambda c, t: sent.append(t) or 11)
    assert code == 0
    assert "permission" in sent[0]
    assert store.active_session()["recap_message_id"] == 11
