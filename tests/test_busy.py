import time

from bridge.config import Config
from bridge import busy


def make_cfg(tmp_path):
    return Config(bot_token="t", allowed_chat_id=1, poll_timeout=1,
                  store_path=tmp_path / "s.json",
                  flag_path=tmp_path / ".enabled",
                  pid_path=tmp_path / ".pid",
                  busy_path=tmp_path / ".busy")


def test_not_busy_by_default(tmp_path):
    assert busy.is_busy(make_cfg(tmp_path)) is False


def test_set_then_busy(tmp_path):
    cfg = make_cfg(tmp_path)
    busy.set_busy(cfg)
    assert busy.is_busy(cfg) is True


def test_clear_stops_busy(tmp_path):
    cfg = make_cfg(tmp_path)
    busy.set_busy(cfg)
    busy.clear_busy(cfg)
    assert busy.is_busy(cfg) is False


def test_stale_flag_is_not_busy(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.busy_path.write_text(str(time.time() - 10_000))   # far in the past
    assert busy.is_busy(cfg) is False


def test_fresh_within_max_age(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.busy_path.write_text(str(1000.0))
    assert busy.is_busy(cfg, now=1100.0, max_age=900.0) is True
    assert busy.is_busy(cfg, now=2000.0, max_age=900.0) is False


def test_clear_when_absent_is_safe(tmp_path):
    busy.clear_busy(make_cfg(tmp_path))   # no file — must not raise
