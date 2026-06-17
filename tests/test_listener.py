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
