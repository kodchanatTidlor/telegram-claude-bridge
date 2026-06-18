from bridge.config import Config
from bridge.store import Store
from bridge import commands, busy, gate


def make_cfg(tmp_path):
    return Config(bot_token="t", allowed_chat_id=1, poll_timeout=1,
                  store_path=tmp_path / "s.json",
                  flag_path=tmp_path / ".enabled",
                  pid_path=tmp_path / ".pid",
                  gate_dir=tmp_path / ".gate",
                  busy_path=tmp_path / ".busy")


def test_is_command():
    assert commands.is_command("/status")
    assert commands.is_command("/cancel")
    assert not commands.is_command("hello")
    assert not commands.is_command("/unknown")


def test_resolve_button_labels_to_commands():
    assert commands.resolve("📊 Status") == "/status"
    assert commands.resolve("🛑 Stop") == "/cancel"
    assert commands.resolve("/status") == "/status"      # typed still works
    assert commands.resolve("nope") is None


def test_command_keyboard_is_commands_only(tmp_path):
    kb = commands.command_keyboard()["keyboard"]
    labels = [b["text"] for row in kb for b in row]
    assert "📊 Status" in labels and "🛑 Stop" in labels
    assert all("📁" not in label for label in labels)   # no session buttons


def test_status_reports_busy_session_and_model(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)
    store.upsert_session("w0:GUID-D33B", 1, "/my/proj", 5)
    store.set_transcript("w0:GUID-D33B", str(tmp_path / "none.jsonl"))
    busy.set_busy(cfg)
    out = commands.build_status(cfg, store)
    assert "working" in out and "/my/proj" in out
    assert "model: ?" in out and "sessions: 1" in out


def test_status_counts_pending(tmp_path):
    cfg = make_cfg(tmp_path)
    gate.register_pending(cfg, 1, {"kind": "permission"})
    gate.register_pending(cfg, 2, {"kind": "question"})
    out = commands.build_status(cfg, Store(cfg.store_path))
    assert "pending: 2" in out


def test_dashboard_has_session_and_new_buttons(tmp_path):
    store = Store((tmp_path / "s.json"))
    store.upsert_session("w0t0p0:AAAA-D33B", 1, "/a/heygoody-web", 5)
    kb = commands.dashboard_keyboard(store)["inline_keyboard"]
    top = [b["callback_data"] for b in kb[0]]
    assert top == ["refresh", "newmenu"]                  # same row
    sw = kb[1][0]
    assert "heygoody-web" in sw["text"] and sw["text"].endswith("D33B")
    assert sw["callback_data"] == "sw:w0t0p0:AAAA-D33B"   # full sid


def test_distinct_cwds_dedupes(tmp_path):
    store = Store((tmp_path / "s.json"))
    store.upsert_session("s1", 1, "/a", 5)
    store.upsert_session("s2", 2, "/a", 6)   # same cwd
    store.upsert_session("s3", 3, "/b", 7)
    assert commands.distinct_cwds(store) == ["/a", "/b"]


def test_newmenu_indexes_cwds_with_back(tmp_path):
    store = Store((tmp_path / "s.json"))
    store.upsert_session("s1", 1, "/x/proj-a", 5)
    store.upsert_session("s2", 2, "/y/proj-b", 6)
    kb = commands.newmenu_keyboard(store)["inline_keyboard"]
    assert kb[0][0]["callback_data"] == "new:0" and "proj-a" in kb[0][0]["text"]
    assert kb[1][0]["callback_data"] == "new:1"
    assert kb[-1][0]["callback_data"] == "back"
