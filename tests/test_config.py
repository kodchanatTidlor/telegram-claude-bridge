import pytest
from bridge.config import Config, is_allowed, load_config


def make_cfg(**kw):
    base = dict(bot_token="t", allowed_chat_id=42, poll_timeout=50,
                store_path="s", flag_path="f", pid_path="p")
    base.update(kw)
    return Config(**base)


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch):
    # Tests must not be shadowed by a real .env on the dev machine.
    monkeypatch.setattr("bridge.config._load_dotenv", lambda p: None)


def test_is_allowed_true_for_matching_id():
    assert is_allowed(make_cfg(), 42) is True


def test_is_allowed_false_for_other_id():
    assert is_allowed(make_cfg(), 99) is False


def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "abc")
    monkeypatch.setenv("ALLOWED_CHAT_ID", "777")
    cfg = load_config()
    assert cfg.bot_token == "abc"
    assert cfg.allowed_chat_id == 777
    assert cfg.poll_timeout == 50


def test_load_config_missing_token_raises(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setenv("ALLOWED_CHAT_ID", "1")
    with pytest.raises(ValueError):
        load_config()
