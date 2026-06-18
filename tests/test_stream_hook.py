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

    def send_fn(c, text, silent=False):
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
                           lambda c, t, silent=False: sent.append(t) or 1,
                           lambda p, c: (None, c))
    assert code == 0 and sent == []


def test_stop_retries_until_final_text_flushes(tmp_path):
    cfg = make_cfg(tmp_path)
    up(cfg)
    store = Store(cfg.store_path)
    sent, slept = [], []
    # transcript empty for the first 2 reads, then the closing text appears
    seq = [(None, 0), (None, 0), ("final answer", 5)]

    def text_fn(p, c):
        return seq.pop(0) if len(seq) > 1 else seq[0]

    payload = json.dumps({"hook_event_name": "Stop", "transcript_path": "x"})
    code = stream_hook.run(payload, {"ITERM_SESSION_ID": "s1"}, cfg, store,
                           lambda c, t, silent=False: sent.append(t) or 1, text_fn,
                           sleep_fn=lambda s: slept.append(s))
    assert code == 0
    assert sent and "final answer" in sent[0]   # retried, then flushed
    assert len(slept) >= 2                       # waited for the write
    assert store.get_cursor("s1") == 5


def test_silent_midturn_loud_on_stop(tmp_path):
    cfg = make_cfg(tmp_path)
    up(cfg)
    store = Store(cfg.store_path)
    seen = []

    def send_fn(c, t, silent=False):
        seen.append(silent)
        return 1

    # PostToolUse commentary -> silent
    stream_hook.run(json.dumps({"hook_event_name": "PostToolUse",
                                "transcript_path": "x"}),
                    {"ITERM_SESSION_ID": "s1"}, cfg, store, send_fn,
                    lambda p, c: ("commentary", c + 1))
    # Stop final -> loud
    stream_hook.run(json.dumps({"hook_event_name": "Stop",
                                "transcript_path": "x"}),
                    {"ITERM_SESSION_ID": "s2"}, cfg, store, send_fn,
                    lambda p, c: ("final", c + 1))
    assert seen == [True, False]


def test_non_stop_does_not_retry(tmp_path):
    cfg = make_cfg(tmp_path)
    up(cfg)
    store = Store(cfg.store_path)
    slept = []
    payload = json.dumps({"hook_event_name": "PostToolUse",
                          "transcript_path": "x"})
    stream_hook.run(payload, {"ITERM_SESSION_ID": "s1"}, cfg, store,
                    lambda c, t, silent=False: 1, lambda p, c: (None, c),
                    sleep_fn=lambda s: slept.append(s))
    assert slept == []                           # PostToolUse: single pass
