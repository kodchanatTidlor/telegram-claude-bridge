import asyncio

from bridge.config import Config
from bridge.store import Store
from bridge import gate
import listener


def make_cfg(tmp_path):
    return Config(bot_token="t", allowed_chat_id=1, poll_timeout=1,
                  store_path=tmp_path / "s.json",
                  flag_path=tmp_path / ".enabled",
                  pid_path=tmp_path / ".pid",
                  gate_dir=tmp_path / ".gate")


def msg(text, chat_id=1, reply_to=None):
    m = {"message": {"from": {"id": chat_id}, "chat": {"id": chat_id},
                     "text": text}}
    if reply_to:
        m["message"]["reply_to_message"] = {"message_id": reply_to}
    return m


def test_drops_non_allowlisted(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)
    store.upsert_session("sid", 1, "/c", 10)
    assert listener.resolve_target(cfg, store, msg("hi", chat_id=999)) is None


def test_no_session_returns_none(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)  # empty
    assert listener.resolve_target(cfg, store, msg("hi")) is None


def test_reply_routes_to_session_by_recap(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)
    store.upsert_session("sidA", 11, "/a", 10)
    store.upsert_session("sidB", 22, "/b", 20)
    session, text = listener.resolve_target(cfg, store, msg("go on", reply_to=10))
    assert session["iterm_session_id"] == "sidA"
    assert session["job_pid"] == 11
    assert text == "go on"  # Enter is sent separately by _inject


def test_plain_message_routes_to_active(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)
    store.upsert_session("sidA", 11, "/a", 10)
    store.upsert_session("sidB", 22, "/b", 20)
    session, text = listener.resolve_target(cfg, store, msg("hi"))
    assert session["iterm_session_id"] == "sidB"


def test_reply_to_unknown_recap_falls_back_to_active(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)
    store.upsert_session("sidA", 11, "/a", 10)
    session, _ = listener.resolve_target(cfg, store, msg("hi", reply_to=999))
    assert session["iterm_session_id"] == "sidA"


def test_gate_reply_consumes_pending(tmp_path):
    cfg = make_cfg(tmp_path)
    gate.register_pending(cfg, 50, {"kind": "permission"})
    assert listener.handle_gate_reply(cfg, msg("y", reply_to=50)) is True
    assert gate.take_answer(cfg, 50) == "y"          # handed to the hook


def test_gate_reply_ignores_non_reply(tmp_path):
    cfg = make_cfg(tmp_path)
    gate.register_pending(cfg, 50, {"kind": "permission"})
    assert listener.handle_gate_reply(cfg, msg("y")) is False


def test_gate_reply_ignores_reply_without_pending(tmp_path):
    cfg = make_cfg(tmp_path)
    assert listener.handle_gate_reply(cfg, msg("y", reply_to=12345)) is False


def test_gate_reply_drops_non_allowlisted(tmp_path):
    cfg = make_cfg(tmp_path)
    gate.register_pending(cfg, 50, {"kind": "permission"})
    assert listener.handle_gate_reply(cfg, msg("y", reply_to=50,
                                               chat_id=999)) is False


def gcfg(tmp_path):
    return Config(bot_token="t", allowed_chat_id=1, poll_timeout=1,
                  store_path=tmp_path / "s.json", flag_path=tmp_path / ".e",
                  pid_path=tmp_path / ".p", group_id=-100)


def gmsg(text, thread, user=1, chat=-100):
    return {"message": {"from": {"id": user}, "chat": {"id": chat},
                        "message_thread_id": thread, "text": text}}


def test_group_resolve_target_routes_by_topic(tmp_path):
    cfg = gcfg(tmp_path)
    store = Store(cfg.store_path)
    store.upsert_session("sX", 1, "/p", 5)
    store.set_topic("sX", 77, "/p")
    sess, text = listener.resolve_target(cfg, store, gmsg("go", thread=77))
    assert sess["iterm_session_id"] == "sX" and text == "go"


def test_group_rejects_other_member_and_chat(tmp_path):
    cfg = gcfg(tmp_path)
    store = Store(cfg.store_path)
    store.upsert_session("sX", 1, "/p", 5)
    store.set_topic("sX", 77, "/p")
    assert listener.resolve_target(cfg, store,
                                   gmsg("x", 77, user=999)) is None   # other user
    assert listener.resolve_target(cfg, store,
                                   gmsg("x", 77, chat=-200)) is None   # other group


def test_group_general_falls_back_to_active(tmp_path):
    cfg = gcfg(tmp_path)
    store = Store(cfg.store_path)
    store.upsert_session("sA", 1, "/a", 5)            # active, no topic bound
    sess, _ = listener.resolve_target(cfg, store, gmsg("hi", thread=None))
    assert sess["iterm_session_id"] == "sA"           # General → active


def test_group_no_session_no_route(tmp_path):
    cfg = gcfg(tmp_path)
    store = Store(cfg.store_path)                       # empty
    assert listener.resolve_target(cfg, store, gmsg("x", thread=999)) is None


def callback(data, on_message=60, chat_id=1, cq_id="cq1"):
    return {"callback_query": {"id": cq_id, "from": {"id": chat_id},
                               "data": data,
                               "message": {"message_id": on_message}}}


def _run_cb(cfg, store, update, new_sid="newGUID"):
    opened, pruned, sent, reloaded = [], [], [], []

    async def fake_open(conn, cwd):
        opened.append(cwd)
        return new_sid

    async def fake_prune(app, st):
        pruned.append(True)
    answered, markups, texts = [], [], []
    ok = asyncio.run(listener.handle_callback(
        cfg, store, "APP", "CONN", update,
        answer_fn=lambda c, i, t="": answered.append(t),
        markup_fn=lambda c, m, mk=None: markups.append(mk),
        text_fn=lambda c, m, t, mk=None: texts.append(t),
        send_fn=lambda c, t: sent.append(t) or 777,
        open_fn=fake_open, prune_fn=fake_prune,
        exec_fn=lambda: reloaded.append(True)))
    return ok, answered, markups, texts, opened, pruned, sent, reloaded


def test_callback_gate_resolves_and_strips(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)
    gate.register_pending(cfg, 60, {"kind": "permission"})
    ok, answered, markups, *_ = _run_cb(cfg, store, callback("y"))
    assert ok is True
    assert gate.take_answer(cfg, 60) == "y"
    assert markups == [None]                     # keyboard stripped


def test_callback_switch_sets_active(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)
    store.upsert_session("w0:AAAA", 1, "/a", 5)
    store.upsert_session("w1:BBBB", 2, "/b", 6)   # active now BBBB
    *_, sent, _ = _run_cb(cfg, store, callback("sw:w0:AAAA"))
    a = store.active_session()
    assert a["iterm_session_id"] == "w0:AAAA"
    assert sent and "Switched" in sent[0] and "/a" in sent[0]   # bound msg
    assert a["recap_message_id"] == 777            # reply routes here


def test_callback_new_opens_session_at_cwd(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)
    store.upsert_session("s1", 1, "/proj/alpha", 5)
    ok, _, _, _, opened, _, sent, _ = _run_cb(cfg, store, callback("new:0"),
                                              new_sid="freshGUID")
    assert ok and opened == ["/proj/alpha"]
    assert sent and "New Claude" in sent[0]                  # binding msg sent
    a = store.active_session()
    assert a["iterm_session_id"] == "freshGUID"              # bound + active
    assert a["recap_message_id"] == 777


class _FakeSession:
    def __init__(self, sid, job):
        self.session_id = sid
        self._job = job

    async def async_get_variable(self, name):
        return self._job


class _FakeApp:
    def __init__(self, sessions):
        tab = type("T", (), {"sessions": sessions})()
        win = type("W", (), {"tabs": [tab]})()
        self.windows = [win]

    async def async_refresh(self):
        pass


class _Line:
    def __init__(self, s):
        self.string = s


class _Contents:
    def __init__(self, lines):
        self._lines = [_Line(x) for x in lines]
        self.number_of_lines = len(self._lines)

    def line(self, i):
        return self._lines[i]


class _ScreenSession(_FakeSession):
    def __init__(self, sid, lines):
        super().__init__(sid, "claude")
        self._lines = lines

    async def async_get_screen_contents(self):
        return _Contents(self._lines)


def test_grab_screen_reads_visible_lines(tmp_path):
    app = _FakeApp([_ScreenSession("live", ["line1", "line2", "panel"])])
    assert asyncio.run(listener._grab_screen(app, "w:live")) == "line1\nline2\npanel"


def test_post_screen_replaces_previous(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)
    store.add_screen(11)                      # an old snapshot
    sent, deleted = [], []
    orig_send, orig_del = listener.send_message, listener.delete_message
    listener.send_message = lambda c, t: sent.append(t) or 22
    listener.delete_message = lambda c, m: deleted.append(m)
    try:
        listener._post_screen(cfg, store, "screen text")
    finally:
        listener.send_message, listener.delete_message = orig_send, orig_del
    assert deleted == [11]                     # old removed
    assert store.pop_screens() == [22]         # new tracked


def test_prune_dead_keeps_only_running_claude(tmp_path):
    store = Store(tmp_path / "s.json")
    store.upsert_session("w:live", 1, "/a", 5)    # claude running
    store.upsert_session("w:shell", 2, "/b", 6)   # claude exited -> zsh
    store.upsert_session("w:closed", 3, "/c", 7)  # tab gone
    app = _FakeApp([_FakeSession("live", "claude"),
                    _FakeSession("shell", "-zsh")])
    asyncio.run(listener._prune_dead(app, store))
    assert [s["iterm_session_id"] for s in store.sessions()] == ["w:live"]


def test_callback_refresh_prunes_and_rerenders(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)
    store.upsert_session("s1", 1, "/a", 5)
    ok, answered, _, texts, _, pruned, _, _ = _run_cb(cfg, store,
                                                      callback("refresh"))
    assert ok and pruned == [True]      # dead sessions dropped
    assert texts and "Bridge" in texts[0]   # dashboard re-rendered


def test_callback_reload_reexecs(tmp_path):
    cfg = make_cfg(tmp_path)
    ok, _, _, _, _, _, sent, reloaded = _run_cb(cfg, Store(cfg.store_path),
                                                callback("reload"))
    assert ok and reloaded == [True]              # process re-exec triggered
    assert sent and "reloading" in sent[0]


def test_callback_non_reply_ignored(tmp_path):
    cfg = make_cfg(tmp_path)
    ok, *_ = _run_cb(cfg, Store(cfg.store_path), msg("hi"))
    assert ok is False


def test_callback_non_allowlisted_rejected(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)
    gate.register_pending(cfg, 60, {"kind": "permission"})
    ok, answered, *_ = _run_cb(cfg, store, callback("y", chat_id=999))
    assert ok is True and answered == ["not allowed"]
    assert gate.take_answer(cfg, 60) is None
