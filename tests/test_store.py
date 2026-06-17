from bridge.store import Store


def test_upsert_and_active(tmp_path):
    s = Store(tmp_path / "s.json")
    s.upsert_session("sid1", 111, "/cwd", 10)
    a = s.active_session()
    assert a["iterm_session_id"] == "sid1"
    assert a["job_pid"] == 111
    assert a["recap_message_id"] == 10


def test_active_is_most_recent(tmp_path):
    s = Store(tmp_path / "s.json")
    s.upsert_session("sid1", 1, "/a", 10)
    s.upsert_session("sid2", 2, "/b", 11)
    assert s.active_session()["iterm_session_id"] == "sid2"


def test_session_by_recap(tmp_path):
    s = Store(tmp_path / "s.json")
    s.upsert_session("sid1", 1, "/a", 10)
    s.upsert_session("sid2", 2, "/b", 11)
    assert s.session_by_recap(10)["iterm_session_id"] == "sid1"
    assert s.session_by_recap(999) is None


def test_offset_roundtrip(tmp_path):
    s = Store(tmp_path / "s.json")
    assert s.get_offset() == 0
    s.set_offset(42)
    assert Store(tmp_path / "s.json").get_offset() == 42


def test_persists_across_instances(tmp_path):
    Store(tmp_path / "s.json").upsert_session("sid1", 1, "/a", 10)
    assert Store(tmp_path / "s.json").active_session()["iterm_session_id"] == "sid1"
