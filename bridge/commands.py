from bridge.busy import is_busy
from bridge.recap import escape_md_v2
from bridge.usage import latest_model

# Bridge-local commands: handled by the listener, never injected into Claude.
COMMANDS = {
    "/status": "bridge status + session menu",
    "/screen": "snapshot the active session's screen",
    "/cancel": "stop Claude (send ESC)",
    "/help": "list bridge commands",
}
SCREEN_LINES = 40
# Reply-keyboard buttons send their label verbatim, so raw "/status" looks odd.
# Show a friendly label and map it back to the command.
# Order = reply-keyboard layout (left→right); Stop sits far right.
BUTTONS = {"📊 Status": "/status", "📸 Screen": "/screen", "🛑 Stop": "/cancel"}


def resolve(text):
    """Canonical command for a typed command OR a button label, else None."""
    t = (text or "").strip()
    if t in BUTTONS:
        return BUTTONS[t]
    head = t.split(" ", 1)[0]
    return head if head in COMMANDS else None


def is_command(text) -> bool:
    return resolve(text) is not None


def _tag(iterm_session_id) -> str:
    return iterm_session_id[-4:]


def _base(cwd) -> str:
    return (cwd or "").rstrip("/").rsplit("/", 1)[-1] or (cwd or "?")


def distinct_cwds(store):
    # Persistent list — known dirs survive even after their session closes.
    return store.known_cwds()


def _pending_count(cfg) -> int:
    d = cfg.gate_dir / "pending"
    return len(list(d.glob("*.json"))) if d.exists() else 0


def build_status(cfg, store) -> str:
    active = store.active_session()
    cwd = active.get("cwd", "—") if active else "—"
    model = latest_model(store.get_transcript(active["iterm_session_id"])) \
        if active else None
    return "\n".join([
        "🤖 *Bridge* — " + ("working ⚙️" if is_busy(cfg) else "idle"),
        f"active: `{escape_md_v2(cwd)}`",
        f"model: {escape_md_v2(model or '?')}",
        f"pending: {_pending_count(cfg)} · sessions: {len(store.sessions())}",
        "",
        escape_md_v2("🔄 อัปเดต · ♻️ restart bridge"),
        escape_md_v2("📁 สลับ · ➕ เปิดใหม่"),
    ])


def build_help() -> str:
    rows = [f"`{escape_md_v2(c)}` — {escape_md_v2(d)}"
            for c, d in COMMANDS.items()]
    return "*bridge commands*\n" + "\n".join(rows)


def command_keyboard():
    # Persistent reply keyboard: just the quick commands (no session clutter).
    return {"keyboard": [[{"text": label} for label in BUTTONS]],
            "resize_keyboard": True, "is_persistent": True}


def dashboard_keyboard(store):
    # Inline keyboard on the /status message: switch session (sw:<sid>) + open
    # a new one (newmenu).
    rows = [[{"text": "🔄 Refresh", "callback_data": "refresh"},
             {"text": "♻️ Reload", "callback_data": "reload"},
             {"text": "➕ New", "callback_data": "newmenu"}]]
    rows += [[{"text": f"📁 {_base(s.get('cwd'))} ·{_tag(s['iterm_session_id'])}",
               "callback_data": f"sw:{s['iterm_session_id']}"}]
             for s in store.sessions()]
    return {"inline_keyboard": rows}


def screen_block(text) -> str:
    # Wrap the terminal snapshot in a MarkdownV2 code block so monospace keeps
    # the panel's layout. Inside a pre block only ` and \ need escaping.
    lines = (text or "").splitlines()[-SCREEN_LINES:]
    body = "\n".join(lines).replace("\\", "\\\\").replace("`", "\\`")
    return f"```\n{body or '(blank)'}\n```"


def new_session_msg(cwd, sid) -> str:
    return "\n".join([
        "🆕 *New Claude session*",
        f"folder: `{escape_md_v2(cwd)}`",
        f"session ·{_tag(sid)}",
        "reply here to talk to it",
    ])


def newmenu_keyboard(store):
    # Pick a known cwd to launch a fresh Claude session in (new:<index>).
    rows = [[{"text": f"📂 {_base(c)}", "callback_data": f"new:{i}"}]
            for i, c in enumerate(distinct_cwds(store))]
    rows.append([{"text": "⬅ Back", "callback_data": "back"}])
    return {"inline_keyboard": rows}
