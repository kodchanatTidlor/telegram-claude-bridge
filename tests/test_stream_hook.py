import json
import os

from bridge.config import Config
from bridge.store import Store
import stream_hook


def make_cfg(tmp_path):
    return Config(bot_token="t", allowed_chat_id=1, poll_timeout=1,
                  store_path=tmp_path / "s.json",
                  flag_path=tmp_path / ".enabled",
                  pid_path=tmp_path / ".pid")


def up(cfg):
    cfg.pid_path.write_text(str(os.getpid()))


def transcript(tmp_path, rows):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    return str(p)


def test_stream_skips_when_listener_down(tmp_path):
    cfg = make_cfg(tmp_path)
    sent = []
    code = stream_hook.run("{}", {}, cfg, Store(cfg.store_path),
                           lambda *a: sent.append(a) or 1, lambda p, c: (None, c))
    assert code == 0 and sent == []


def test_stream_sends_commentary_and_tool(tmp_path):
    cfg = make_cfg(tmp_path)
    up(cfg)
    store = Store(cfg.store_path)
    path = transcript(tmp_path, [
        {"message": {"role": "assistant",
                     "content": [{"type": "text", "text": "checking"}]}},
    ])
    sent = []

    def send_fn(c, text):
        sent.append(text)
        return len(sent)

    from bridge.stream import new_text
    env = {"ITERM_SESSION_ID": "s1", "JOB_PID": "7"}
    payload = json.dumps({"transcript_path": path, "cwd": "/c"})
    code = stream_hook.run(payload, env, cfg, store, send_fn, new_text)
    assert code == 0
    assert len(sent) == 1 and "checking" in sent[0]  # only what Claude said
    assert store.get_cursor("s1") == 1               # cursor advanced
    assert store.active_session()["recap_message_id"] == 1


def test_stream_no_text_sends_nothing(tmp_path):
    cfg = make_cfg(tmp_path)
    up(cfg)
    store = Store(cfg.store_path)
    sent = []
    payload = json.dumps({"transcript_path": str(tmp_path / "none")})
    code = stream_hook.run(payload, {"ITERM_SESSION_ID": "s1"}, cfg, store,
                           lambda c, t: sent.append(t) or 1,
                           lambda p, c: (None, c))
    assert code == 0 and sent == []
