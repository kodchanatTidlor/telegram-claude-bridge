import httpx
from bridge.config import Config
from bridge import telegram


def make_cfg():
    return Config(bot_token="TOK", allowed_chat_id=5, poll_timeout=1,
                  store_path="s", flag_path="f", pid_path="p")


def test_send_message_returns_message_id(monkeypatch):
    calls = {}

    def fake_post(url, json, timeout):
        calls["url"] = url
        calls["json"] = json
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 77}})

    monkeypatch.setattr(telegram.httpx, "post", fake_post)
    mid = telegram.send_message(make_cfg(), "hello", reply_to=12)
    assert mid == 77
    assert "sendMessage" in calls["url"]
    assert calls["json"]["reply_to_message_id"] == 12
    assert calls["json"]["parse_mode"] == "MarkdownV2"


def test_send_message_retries_on_429(monkeypatch):
    responses = [
        httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 0}}),
        httpx.Response(200, json={"ok": True, "result": {"message_id": 9}}),
    ]
    monkeypatch.setattr(telegram.time, "sleep", lambda s: None)
    monkeypatch.setattr(telegram.httpx, "post", lambda *a, **k: responses.pop(0))
    assert telegram.send_message(make_cfg(), "x") == 9


def test_get_updates_returns_results(monkeypatch):
    def fake_get(url, params, timeout):
        return httpx.Response(200, json={"ok": True, "result": [{"update_id": 1}]})

    monkeypatch.setattr(telegram.httpx, "get", fake_get)
    assert telegram.get_updates(make_cfg(), offset=0) == [{"update_id": 1}]
