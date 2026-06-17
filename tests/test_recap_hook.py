import os

from bridge.config import Config
from bridge.store import Store
import recap_hook


def make_cfg(tmp_path):
    return Config(bot_token="t", allowed_chat_id=1, poll_timeout=1,
                  store_path=tmp_path / "s.json",
                  flag_path=tmp_path / ".enabled",
                  pid_path=tmp_path / ".pid")


def _mark_listener_up(cfg):
    cfg.pid_path.write_text(str(os.getpid()))  # this test process is alive


def test_skips_when_listener_down(tmp_path):
    cfg = make_cfg(tmp_path)  # no pid file
    sent = []
    code = recap_hook.run("{}", {}, cfg, Store(cfg.store_path),
                          lambda *a, **k: sent.append(a), lambda p: ("u", "a"))
    assert code == 0 and sent == []


def test_skips_when_listener_pid_dead(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.pid_path.write_text("999999")  # not a live pid
    sent = []
    code = recap_hook.run("{}", {}, cfg, Store(cfg.store_path),
                          lambda *a, **k: sent.append(a), lambda p: ("u", "a"))
    assert code == 0 and sent == []


def test_skips_when_no_iterm_session(tmp_path):
    cfg = make_cfg(tmp_path)
    _mark_listener_up(cfg)
    sent = []
    code = recap_hook.run('{"transcript_path":"x","cwd":"/c"}', {},
                          cfg, Store(cfg.store_path),
                          lambda *a, **k: sent.append(a), lambda p: ("u", "a"))
    assert code == 0 and sent == []


def test_sends_recap_and_stores(tmp_path):
    cfg = make_cfg(tmp_path)
    _mark_listener_up(cfg)
    store = Store(cfg.store_path)
    sent = {}

    def send_fn(c, text, reply_to=None):
        sent["text"] = text
        return 55

    env = {"ITERM_SESSION_ID": "w0t1p0:GUID", "JOB_PID": "321"}
    code = recap_hook.run('{"transcript_path":"x","cwd":"/c"}', env,
                          cfg, store, send_fn, lambda p: ("fix bug", "done"))
    assert code == 0
    assert "fix bug" in sent["text"] and "done" in sent["text"]
    a = store.active_session()
    assert a["iterm_session_id"] == "w0t1p0:GUID"
    assert a["job_pid"] == 321
    assert a["recap_message_id"] == 55


def test_returns_zero_even_if_send_raises(tmp_path):
    cfg = make_cfg(tmp_path)
    _mark_listener_up(cfg)

    def boom(*a, **k):
        raise RuntimeError("net down")

    env = {"ITERM_SESSION_ID": "x:y", "JOB_PID": "1"}
    code = recap_hook.run('{"transcript_path":"x","cwd":"/c"}', env,
                          cfg, Store(cfg.store_path), boom, lambda p: ("u", "a"))
    assert code == 0
