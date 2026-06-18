import time
from datetime import datetime

from bridge.busy import is_busy
from bridge.recap import escape_md_v2
from bridge.usage import latest_model, usage_since

# Bridge-local commands: handled by the listener, never injected into Claude.
COMMANDS = {
    "/status": "bridge status + session menu",
    "/usage": "token usage in the last 5h (all sessions)",
    "/screen": "snapshot the active session's screen",
    "/cancel": "stop Claude (send ESC)",
    "/help": "list bridge commands",
}
SCREEN_LINES = 40
USAGE_WINDOW = 5 * 3600   # the ~5-hour quota block ccusage tracks


def _k(n) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def build_usage_local(cfg, now=None) -> str:
    """Permission-free fallback: 5h token totals from local transcripts."""
    now = time.time() if now is None else now
    u = usage_since(cfg.projects_dir, now - USAGE_WINDOW)
    return "\n".join([
        "📊 *Local usage* — last 5h \\(tokens, all sessions\\)",
        f"output: {escape_md_v2(_k(u['output']))} · "
        f"input: {escape_md_v2(_k(u['input']))}",
        f"cache: {escape_md_v2(_k(u['cache_read'] + u['cache_creation']))} · "
        f"total: {escape_md_v2(_k(u['total']))}",
    ])


def usage_help(cfg, now=None) -> str:
    """No session key set — tell the user how to add one for official %, and
    still show the local token estimate so /usage isn't empty."""
    return "\n".join([
        "🔑 *No CLAUDE\\_SESSION\\_KEY set*",
        escape_md_v2("ดู quota % ทางการ ต้องใส่ session key:"),
        escape_md_v2("1. เปิด claude.ai → DevTools → Application → Cookies"),
        escape_md_v2("2. ก็อปค่า sessionKey (sk-ant-sid…)"),
        escape_md_v2("3. ใส่ใน .env: CLAUDE_SESSION_KEY=sk-ant-sid…  แล้ว ♻️ Reload"),
        "",
        build_usage_local(cfg, now),
    ])


def _first(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return None


def _severity(pct) -> str:
    return "🔴" if pct >= 80 else "🟡" if pct >= 50 else "🟢"


def _reset_epoch(window):
    iso = _first(window, "resets_at", "reset_at", "resetsAt", "resets")
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, AttributeError):
        return None


def _fmt_in(epoch, now) -> str:
    secs = int(epoch - now)
    if secs <= 0:
        return "now"
    h, m = divmod(secs // 60, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def _window_line(label, window, now, with_in) -> str:
    pct = _first(window, "utilization", "percent", "used_pct", "percentage")
    if pct is None:
        return ""
    parts = [f"{_severity(pct)} {label}: {escape_md_v2(str(pct))}\\%"]
    rst = _reset_epoch(window)
    if rst:
        at = datetime.fromtimestamp(rst).strftime(
            "%H:%M" if label == "5h" else "%a %H:%M")
        parts.append(f"reset {escape_md_v2(at)}")
        if with_in:
            parts.append(f"in {escape_md_v2(_fmt_in(rst, now))}")
    return " · ".join(parts)


def format_official(data, now=None) -> str:
    """Render 5h + 7d windows with severity-colored emoji. Field names are
    guessed (flexible lookup); raw-dumps if neither window is found, for a
    spike with a real key."""
    import json
    now = time.time() if now is None else now
    five = _first(data, "five_hour", "fiveHour", "5h")
    seven = _first(data, "seven_day", "sevenDay", "7d")
    lines = ["📊 *Usage*"]
    fh = _window_line("5h", five, now, with_in=True)
    sd = _window_line("7d", seven, now, with_in=False)
    if fh:
        lines.append(fh)
    if sd:
        lines.append(sd)
    if fh or sd:
        return "\n".join(lines)
    raw = json.dumps(data)[:1500].replace("\\", "\\\\").replace("`", "\\`")
    return f"📊 *Usage \\(raw — refine parser\\)*\n```\n{raw}\n```"
# Reply-keyboard buttons send their label verbatim, so raw "/status" looks odd.
# Show a friendly label and map it back to the command.
# Order = reply-keyboard layout (left→right); Stop sits far right.
BUTTONS = {"📊 Status": "/status", "📈 Usage": "/usage",
           "📸 Screen": "/screen", "🛑 Stop": "/cancel"}


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
