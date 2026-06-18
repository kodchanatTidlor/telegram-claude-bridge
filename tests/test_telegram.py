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


def test_send_message_includes_reply_markup(monkeypatch):
    calls = {}

    def fake_post(url, json, timeout):
        calls["json"] = json
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    monkeypatch.setattr(telegram.httpx, "post", fake_post)
    kb = {"inline_keyboard": [[{"text": "ok", "callback_data": "y"}]]}
    telegram.send_message(make_cfg(), "x", reply_markup=kb)
    assert calls["json"]["reply_markup"] == kb


def test_send_message_silent(monkeypatch):
    calls = {}
    monkeypatch.setattr(telegram.httpx, "post", lambda url, json, timeout:
                        (calls.update(json=json),
                         httpx.Response(200, json={"ok": True,
                                                   "result": {"message_id": 1}}))[1])
    telegram.send_message(make_cfg(), "x", silent=True)
    assert calls["json"]["disable_notification"] is True


def test_send_photo_uploads_and_returns_id(monkeypatch, tmp_path):
    img = tmp_path / "s.png"
    img.write_bytes(b"PNGDATA")
    calls = {}

    def fake_post(url, data, files, timeout):
        calls["url"] = url
        calls["data"] = data
        calls["files"] = files
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})

    monkeypatch.setattr(telegram.httpx, "post", fake_post)
    mid = telegram.send_photo(make_cfg(), str(img), silent=True)
    assert mid == 7 and "sendPhoto" in calls["url"]
    assert calls["data"]["disable_notification"] == "true"
    assert calls["files"]["photo"][1] == b"PNGDATA"


def test_best_effort_helpers_swallow_errors(monkeypatch):
    def boom(*a, **k):
        raise httpx.TimeoutException("slow")   # NOT an httpx.HTTPError

    monkeypatch.setattr(telegram.httpx, "post", boom)
    cfg = make_cfg()
    # none of these may raise
    telegram.send_chat_action(cfg)
    telegram.answer_callback(cfg, "cq")
    telegram.edit_reply_markup(cfg, 1)
    telegram.delete_message(cfg, 1)
    telegram.set_my_commands(cfg, {"/x": "y"})


def test_get_updates_returns_results(monkeypatch):
    def fake_get(url, params, timeout):
        return httpx.Response(200, json={"ok": True, "result": [{"update_id": 1}]})

    monkeypatch.setattr(telegram.httpx, "get", fake_get)
    assert telegram.get_updates(make_cfg(), offset=0) == [{"update_id": 1}]
