from bridge.config import Config
from bridge.store import Store
from bridge import group


def cfg(group_id=0):
    return Config(bot_token="t", allowed_chat_id=42, poll_timeout=1,
                  store_path="s", flag_path="f", pid_path="p", group_id=group_id)


def test_mode_and_target():
    assert group.is_group_mode(cfg()) is False
    assert group.target_chat(cfg()) == 42                 # DM → owner
    g = cfg(group_id=-100)
    assert group.is_group_mode(g) is True
    assert group.target_chat(g) == -100                   # group → group id


def test_is_allowed_group_requires_group_and_owner():
    g = cfg(group_id=-100)
    assert group.is_allowed_group(g, chat_id=-100, user_id=42) is True
    assert group.is_allowed_group(g, chat_id=-100, user_id=999) is False  # other
    assert group.is_allowed_group(g, chat_id=-200, user_id=42) is False   # other grp


def test_resolve_topic_creates_then_reuses_binding(tmp_path):
    store = Store(tmp_path / "s.json")
    created = []
    tid = group.resolve_topic(store, "sA", "/proj", live_sids=["sA"],
                              create_fn=lambda n: created.append(n) or 100)
    assert tid == 100 and created == ["proj"]
    # same session again → no new create
    assert group.resolve_topic(store, "sA", "/proj", ["sA"],
                               lambda n: 999) == 100


def test_resolve_topic_reuses_free_cwd_topic(tmp_path):
    store = Store(tmp_path / "s.json")
    group.resolve_topic(store, "sOld", "/proj", ["sOld"], lambda n: 100)
    # sOld no longer live; new session same cwd → reuse topic 100
    tid = group.resolve_topic(store, "sNew", "/proj", live_sids=["sNew"],
                              create_fn=lambda n: 999)
    assert tid == 100
    assert group.session_of_topic(store, 100) == "sNew"   # rebound, old dropped


def test_resolve_topic_concurrent_same_cwd_gets_suffix(tmp_path):
    store = Store(tmp_path / "s.json")
    names = []
    group.resolve_topic(store, "s1", "/x/proj", ["s1"],
                        lambda n: names.append(n) or 1)
    # s1 still live → s2 same cwd must NOT reuse → new topic "proj #2"
    group.resolve_topic(store, "s2", "/x/proj", live_sids=["s1", "s2"],
                        create_fn=lambda n: names.append(n) or 2)
    assert names == ["proj", "proj #2"]


def test_ensure_topics_creates_for_each_live_session(tmp_path):
    store = Store(tmp_path / "s.json")
    store.upsert_session("sA", 1, "/a", 5)
    store.upsert_session("sB", 2, "/b", 6)
    created = []
    group.ensure_topics(store, lambda n: created.append(n) or len(created))
    assert sorted(created) == ["a", "b"]
    assert store.topic_of("sA") and store.topic_of("sB")
    # idempotent: second call creates nothing new
    group.ensure_topics(store, lambda n: created.append(n) or 0)
    assert sorted(created) == ["a", "b"]


def test_session_of_topic_none_when_unknown(tmp_path):
    assert group.session_of_topic(Store(tmp_path / "s.json"), 5) is None
