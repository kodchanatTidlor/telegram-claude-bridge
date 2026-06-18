import time

import httpx

API = "https://api.telegram.org/bot{token}/{method}"


def _url(cfg, method):
    return API.format(token=cfg.bot_token, method=method)


def _chat(cfg):
    # Group mode targets the supergroup; DM mode (group_id 0) the owner — so
    # every existing call site keeps working unchanged.
    return cfg.group_id or cfg.allowed_chat_id


def send_message(cfg, text, reply_to=None, reply_markup=None,
                 silent=False, message_thread_id=None) -> int:
    payload = {
        "chat_id": _chat(cfg),
        "text": text,
        "parse_mode": "MarkdownV2",
    }
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if silent:
        payload["disable_notification"] = True
    if message_thread_id is not None:
        payload["message_thread_id"] = message_thread_id

    for _ in range(2):
        resp = httpx.post(_url(cfg, "sendMessage"), json=payload, timeout=15)
        if resp.status_code == 429:
            retry = resp.json().get("parameters", {}).get("retry_after", 1)
            time.sleep(retry)
            continue
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"telegram send failed: {data}")
        return data["result"]["message_id"]
    raise RuntimeError("telegram send failed after retry")


def _best_effort(method, payload) -> None:
    # Cosmetic side-channels (typing, reactions, status edits): never raise.
    # Catch broadly — httpx timeouts are NOT httpx.HTTPError, and a raised
    # timeout here would kill callers like the listener's typing loop.
    def _send(cfg):
        try:
            httpx.post(_url(cfg, method), json=payload(cfg), timeout=10)
        except Exception:
            pass
    return _send


def send_chat_action(cfg, action="typing") -> None:
    # A typing bubble lasts ~5s, so the listener repeats it while Claude works.
    _best_effort("sendChatAction",
                 lambda c: {"chat_id": _chat(c), "action": action})(cfg)


def answer_callback(cfg, callback_query_id, text="") -> None:
    _best_effort("answerCallbackQuery",
                 lambda c: {"callback_query_id": callback_query_id,
                            "text": text})(cfg)


def edit_reply_markup(cfg, message_id, markup=None) -> None:
    # Swap a message's inline keyboard (None = strip it, e.g. after a gate tap).
    _best_effort("editMessageReplyMarkup",
                 lambda c: {"chat_id": _chat(c),
                            "message_id": message_id,
                            "reply_markup": markup or {"inline_keyboard": []}})(cfg)


def edit_message_text(cfg, message_id, text, reply_markup=None) -> None:
    def payload(c):
        p = {"chat_id": _chat(c), "message_id": message_id,
             "text": text, "parse_mode": "MarkdownV2"}
        if reply_markup is not None:
            p["reply_markup"] = reply_markup
        return p
    _best_effort("editMessageText", payload)(cfg)


def delete_message(cfg, message_id) -> None:
    _best_effort("deleteMessage",
                 lambda c: {"chat_id": _chat(c),
                            "message_id": message_id})(cfg)


def set_my_commands(cfg, commands) -> None:
    # Register the "/" slash menu. commands: {"/status": "desc", ...}.
    cmds = [{"command": c.lstrip("/"), "description": d}
            for c, d in commands.items()]
    _best_effort("setMyCommands", lambda c: {"commands": cmds})(cfg)


def create_forum_topic(cfg, name) -> int:
    # Create a forum topic in the group; returns its message_thread_id.
    resp = httpx.post(_url(cfg, "createForumTopic"),
                      json={"chat_id": _chat(cfg), "name": name}, timeout=15)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"telegram createForumTopic failed: {data}")
    return data["result"]["message_thread_id"]


def get_updates(cfg, offset) -> list:
    params = {"offset": offset, "timeout": cfg.poll_timeout}
    resp = httpx.get(_url(cfg, "getUpdates"), params=params,
                     timeout=cfg.poll_timeout + 10)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"telegram getUpdates failed: {data}")
    return data["result"]
