import time

import httpx

API = "https://api.telegram.org/bot{token}/{method}"


def _url(cfg, method):
    return API.format(token=cfg.bot_token, method=method)


def send_message(cfg, text, reply_to=None) -> int:
    payload = {
        "chat_id": cfg.allowed_chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
    }
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to

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


def get_updates(cfg, offset) -> list:
    params = {"offset": offset, "timeout": cfg.poll_timeout}
    resp = httpx.get(_url(cfg, "getUpdates"), params=params,
                     timeout=cfg.poll_timeout + 10)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"telegram getUpdates failed: {data}")
    return data["result"]
