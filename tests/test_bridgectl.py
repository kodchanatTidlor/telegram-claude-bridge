import os

from bridge.config import Config
import bridgectl as cli


def make_cfg(tmp_path):
    return Config(bot_token="t", allowed_chat_id=1, poll_timeout=1,
                  store_path=tmp_path / "s.json",
                  flag_path=tmp_path / ".enabled",
                  pid_path=tmp_path / ".pid",
                  gate_dir=tmp_path / ".gate")


def test_listener_alive_false_when_no_pidfile(tmp_path):
    assert cli.listener_alive(tmp_path / ".pid") is False


def test_listener_alive_false_for_dead_pid(tmp_path):
    p = tmp_path / ".pid"
    p.write_text("999999")
    assert cli.listener_alive(p) is False


def test_listener_alive_true_for_live_pid(tmp_path):
    p = tmp_path / ".pid"
    p.write_text(str(os.getpid()))
    assert cli.listener_alive(p) is True


def test_status_reports_stopped(tmp_path):
    assert "STOPPED" in cli.cmd_status(make_cfg(tmp_path))


def test_status_reports_running(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.pid_path.write_text(str(os.getpid()))
    s = cli.cmd_status(cfg)
    assert "RUNNING" in s and "mirror+gate: ON" in s
