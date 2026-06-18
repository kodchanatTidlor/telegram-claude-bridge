from bridge.store import Store


def test_upsert_and_active(tmp_path):
    s = Store(tmp_path / "s.json")
    s.upsert_session("sid1", 111, "/cwd", 10)
    a = s.active_session()
    assert a["iterm_session_id"] == "sid1"
    assert a["job_pid"] == 111
    assert a["recap_message_id"] == 10


def test_prune_drops_dead_and_reassigns_active(tmp_path):
    s = Store(tmp_path / "s.json")
    s.upsert_session("live", 1, "/a", 5)
    s.upsert_session("dead", 2, "/b", 6)     # active = dead
    s.set_cursor("dead", 9)
    s.set_activity("dead", 8)
    s.prune({"live"})                         # only 'live' still open
    assert [x["iterm_session_id"] for x in s.sessions()] == ["live"]
    assert s.active_session()["iterm_session_id"] == "live"   # reassigned
    assert s.get_cursor("dead") == 0          # aux cleaned


def test_known_cwds_accumulate_and_survive_prune(tmp_path):
    s = Store(tmp_path / "s.json")
    s.upsert_session("a", 1, "/proj/x", 5)
    s.upsert_session("b", 2, "/proj/y", 6)
    s.upsert_session("c", 3, "/proj/x", 7)   # dup cwd not re-added
    assert s.known_cwds() == ["/proj/x", "/proj/y"]
    s.prune(set())                            # all sessions closed
    assert s.sessions() == []
    assert s.known_cwds() == ["/proj/x", "/proj/y"]   # cwds remembered


def test_prune_to_empty_clears_active(tmp_path):
    s = Store(tmp_path / "s.json")
    s.upsert_session("x", 1, "/a", 5)
    s.prune(set())
    assert s.sessions() == [] and s.active_session() is None


def test_upsert_dedupes_by_guid(tmp_path):
    s = Store(tmp_path / "s.json")
    s.upsert_session("ABCD-GUID", None, "/a", 5)       # bridge pre-register
    s.upsert_session("w0t2p1:ABCD-GUID", 99, "/a", 6)  # hook re-register
    assert len(s.sessions()) == 1                       # same session, not two
    assert s.active_session()["job_pid"] == 99


def test_screen_msgs_add_and_pop(tmp_path):
    s = Store(tmp_path / "s.json")
    s.add_screen(1)
    s.add_screen(2)
    assert s.pop_screens() == [1, 2]
    assert s.pop_screens() == []          # cleared


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
