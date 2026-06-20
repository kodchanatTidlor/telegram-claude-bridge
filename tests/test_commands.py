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


def test_usage_command_registered():
    assert commands.is_command("/usage") and commands.resolve("/usage") == "/usage"


def test_severity_buckets():
    assert commands._severity(0) == "⚪️"             # <5
    assert commands._severity(4) == "⚪️"
    assert commands._severity(5) == "🟢"             # <50
    assert commands._severity(49) == "🟢"
    assert commands._severity(50) == "🟡"            # <70
    assert commands._severity(69) == "🟡"
    assert commands._severity(70) == "🟠"            # <90
    assert commands._severity(89) == "🟠"
    assert commands._severity(90) == "🔴"            # ≥90
    assert commands._severity(100) == "🔴"


def test_format_cswap_renders_accounts_and_severity():
    accts = [
        {"email": "a@x.com", "active": False,
         "windows": {"5h": {"pct": 2, "reset": None, "in": None},
                     "7d": {"pct": 60, "reset": "Jun 22 13:59", "in": "3d 0h"}}},
        {"email": "b@y.com", "active": True,
         "windows": {"5h": {"pct": 95, "reset": "16:59", "in": "3h"}}},
    ]
    out = commands.format_cswap(accts)
    assert "2 account" in out
    assert "a@x\\.com" in out and "b@y\\.com" in out
    assert "✅" in out                               # active flagged
    assert "⚪️ 5h: 2" in out and "🟡 7d: 60" in out   # buckets
    assert "🔴 5h: 95" in out                        # ≥90 red
    assert "reset Jun 22 13:59" in out and "in 3d 0h" in out


def test_usage_keyboard_one_button_per_account():
    accts = [{"num": 1, "email": "a@x.com", "active": False},
             {"num": 2, "email": "b@y.com", "active": True}]
    kb = commands.usage_keyboard(accts)["inline_keyboard"]
    assert len(kb) == 2                                   # no refresh row
    assert kb[0][0]["callback_data"] == "cswap:1" and "🔀" in kb[0][0]["text"]
    assert kb[1][0]["callback_data"] == "cswap:2" and "✅" in kb[1][0]["text"]


def test_resolve_button_labels_to_commands():
    assert commands.resolve("📊 Status") == "/status"
    assert commands.resolve("🛑 Stop") == "/cancel"
    assert commands.resolve("/status") == "/status"      # typed still works
    assert commands.resolve("nope") is None


def test_resolve_strips_botname_suffix():
    assert commands.resolve("/screen@john_junoir_bot") == "/screen"
    assert commands.resolve("/cancel@some_bot arg") == "/cancel"


def test_command_keyboard_is_commands_only(tmp_path):
    kb = commands.command_keyboard()["keyboard"]
    labels = [b["text"] for row in kb for b in row]
    assert labels == ["📊 Status", "📈 Usage", "📸 Screen", "🛑 Stop"]  # 4, 1 row
    assert all("📁" not in label for label in labels)        # no session buttons




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
    assert top == ["refresh", "reload", "newmenu"]        # same row
    sw = kb[1][0]
    assert "heygoody-web" in sw["text"] and sw["text"].endswith("D33B")
    assert sw["callback_data"] == "sw:w0t0p0:AAAA-D33B"   # full sid


def test_screen_block_fences_and_escapes():
    out = commands.screen_block("a`b\\c")
    assert out == "```\na\\`b\\\\c\n```"        # fenced + ` and \ escaped


def test_dashboard_top_row_has_reload(tmp_path):
    store = Store(tmp_path / "s.json")
    top = [b["callback_data"]
           for b in commands.dashboard_keyboard(store)["inline_keyboard"][0]]
    assert top == ["refresh", "reload", "newmenu"]


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


def test_reload_msg_escapes_cwd_and_email():
    out = commands.reload_msg("/home/u/proj", "a.b@x.com")
    assert "resumed" in out and "`proj`" in out
    assert "a\\.b@x\\.com" in out                     # md-escaped account
