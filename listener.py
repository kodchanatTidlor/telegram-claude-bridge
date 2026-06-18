import asyncio
import os
import shlex
import sys
import time

from bridge.busy import is_busy
from bridge import commands
from bridge.config import is_allowed, load_config
from bridge.gate import resolve_pending
from bridge.iterm import SHELL_JOB_NAMES, should_inject, strip_session_prefix
from bridge.store import Store
from bridge.telegram import (answer_callback, delete_message,
                             edit_message_text, edit_reply_markup, get_updates,
                             send_chat_action, send_message, set_my_commands)

ESC = "\x1b"   # interrupt Claude's current generation (soft stop)

NOT_RUNNING = "claude not running in this session — cancelled"
TYPING_EVERY = 4.0   # the typing bubble lasts ~5s; refresh just under that


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def handle_gate_reply(cfg, update) -> bool:
    """If this is an allowlisted REPLY to a pending gate prompt, hand the raw
    text to the waiting hook and report True (consumed). Otherwise False, so
    the normal inject path runs."""
    message = update.get("message") or {}
    sender = (message.get("from") or {}).get("id")
    if sender is None or not is_allowed(cfg, sender):
        return False
    reply = message.get("reply_to_message")
    if not reply:
        return False
    rid = reply.get("message_id")
    if rid is None:
        return False
    return resolve_pending(cfg, rid, message.get("text", ""))


async def _open_session(connection, cwd):
    """Open a new iTerm window, launch Claude in cwd, return its session id."""
    import iterm2
    window = await iterm2.Window.async_create(connection)
    session = window.current_tab.current_session
    await session.async_send_text(f"cd {shlex.quote(cwd)} && claude\r")
    return session.session_id


def _is_shell(job_name) -> bool:
    if not job_name:
        return True
    return job_name.rsplit("/", 1)[-1].lower() in SHELL_JOB_NAMES


async def _grab_screen(app, sid):
    """Read the visible text of a session's terminal (the live TUI panel)."""
    await app.async_refresh()
    target = strip_session_prefix(sid)
    for w in app.windows:
        for t in w.tabs:
            for s in t.sessions:
                if strip_session_prefix(s.session_id) != target:
                    continue
                c = await s.async_get_screen_contents()
                rows = [c.line(i).string for i in range(c.number_of_lines)]
                return "\n".join(rows)
    return None


def _clear_screens(cfg, store) -> None:
    for mid in store.pop_screens():
        delete_message(cfg, mid)


def _post_screen(cfg, store, text) -> None:
    # Ephemeral: drop the previous snapshot, post the new one, remember it so
    # the next user message clears it.
    _clear_screens(cfg, store)
    if text is None:
        send_message(cfg, "⚠️ session not found")
        return
    store.add_screen(send_message(cfg, commands.screen_block(text)))


async def _prune_dead(app, store) -> None:
    """Drop store sessions whose iTerm tab closed OR dropped back to a bare
    shell (Claude exited) — only sessions actually running Claude survive."""
    await app.async_refresh()
    live = {}
    for w in app.windows:
        for t in w.tabs:
            for s in t.sessions:
                live[strip_session_prefix(s.session_id)] = \
                    await s.async_get_variable("jobName")
    keep = {s["iterm_session_id"] for s in store.sessions()
            if not _is_shell(live.get(strip_session_prefix(s["iterm_session_id"])))
            and strip_session_prefix(s["iterm_session_id"]) in live}
    store.prune(keep)


async def handle_callback(cfg, store, app, connection, update,
                          answer_fn=answer_callback,
                          markup_fn=edit_reply_markup,
                          text_fn=edit_message_text,
                          send_fn=send_message,
                          open_fn=_open_session,
                          prune_fn=_prune_dead) -> bool:
    """Inline-button taps. Dashboard buttons (sw:/new:/newmenu/back) are handled
    here; bare callback_data (y/n/index) routes to the pending gate."""
    cq = update.get("callback_query")
    if not cq:
        return False
    sender = (cq.get("from") or {}).get("id")
    cq_id = cq.get("id")
    if sender is None or not is_allowed(cfg, sender):
        answer_fn(cfg, cq_id, "not allowed")
        return True
    data = cq.get("data", "")
    mid = (cq.get("message") or {}).get("message_id")

    if data == "refresh":
        await prune_fn(app, store)   # drop closed sessions, then re-render
        text_fn(cfg, mid, commands.build_status(cfg, store),
                commands.dashboard_keyboard(store))
        answer_fn(cfg, cq_id, "refreshed")
    elif data == "newmenu":
        markup_fn(cfg, mid, commands.newmenu_keyboard(store))
        answer_fn(cfg, cq_id, "pick a folder")
    elif data == "back":
        markup_fn(cfg, mid, commands.dashboard_keyboard(store))
        answer_fn(cfg, cq_id, "")
    elif data.startswith("sw:"):
        store.set_active(data.split(":", 1)[1])
        text_fn(cfg, mid, commands.build_status(cfg, store),
                commands.dashboard_keyboard(store))
        answer_fn(cfg, cq_id, "active switched")
    elif data.startswith("new:"):
        cwds = commands.distinct_cwds(store)
        idx = int(data.split(":", 1)[1]) if data[4:].isdigit() else -1
        if 0 <= idx < len(cwds):
            cwd = cwds[idx]
            sid = await open_fn(connection, cwd)
            if sid:
                # Bind a message to the new session so a reply routes to it
                # (active also points here until another session streams).
                new_mid = send_fn(cfg, commands.new_session_msg(cwd, sid))
                store.upsert_session(sid, None, cwd, new_mid)
            answer_fn(cfg, cq_id, "opening…")
        else:
            answer_fn(cfg, cq_id, "gone")
        markup_fn(cfg, mid, commands.dashboard_keyboard(store))
    else:
        resolved = resolve_pending(cfg, mid, data) if mid else False
        answer_fn(cfg, cq_id, "got it" if resolved else "expired")
        if resolved:
            markup_fn(cfg, mid)   # strip keyboard so it can't be tapped twice
    return True


def resolve_target(cfg, store, update):
    """Pure routing: return (session_dict, text_with_cr) or None.

    None means drop silently (non-allowlisted / no target). Testable
    without iTerm or network.
    """
    message = update.get("message") or {}
    sender = (message.get("from") or {}).get("id")
    if sender is None or not is_allowed(cfg, sender):
        return None
    text = message.get("text", "")
    reply = message.get("reply_to_message")
    session = None
    if reply:
        session = store.session_by_recap(reply.get("message_id"))
    if session is None:
        session = store.active_session()
    if session is None:
        return None
    return session, text


async def _inject(app, session_id, text, expected_pid, enter=True) -> bool:
    """Inject via the SHARED, already-open iTerm connection (app). enter=False
    sends a raw control sequence (e.g. ESC) without a submitting newline."""
    await app.async_refresh()
    target = strip_session_prefix(session_id)
    for window in app.windows:
        for tab in window.tabs:
            for session in tab.sessions:
                if strip_session_prefix(session.session_id) != target:
                    continue
                job_name = await session.async_get_variable("jobName")
                job_pid_raw = await session.async_get_variable("jobPid")
                job_pid = int(job_pid_raw) if job_pid_raw else None
                if not should_inject(job_name, job_pid, expected_pid):
                    return False
                await session.async_send_text(text)
                if enter:
                    # Send Enter separately (after the paste settles) — a long
                    # message arrives as a bracketed paste, which swallows a
                    # trailing \r into the input instead of submitting.
                    await asyncio.sleep(0.15)
                    await session.async_send_text("\r")
                return True
    return False  # session not found (tab closed)


async def handle_bridge_command(cfg, store, app, update) -> bool:
    """Bridge-local commands + session-switch buttons — answered here, never
    injected into Claude. Returns True if consumed."""
    message = update.get("message") or {}
    sender = (message.get("from") or {}).get("id")
    if sender is None or not is_allowed(cfg, sender):
        return False
    cmd = commands.resolve(message.get("text", ""))
    if cmd is None:
        return False

    if cmd == "/cancel":
        active = store.active_session()
        if active:
            ok = await _inject(app, active["iterm_session_id"], ESC,
                               active.get("job_pid"), enter=False)
            await asyncio.to_thread(send_message, cfg,
                                    "🛑 ESC sent" if ok else "⚠️ no live session")
        else:
            await asyncio.to_thread(send_message, cfg, "⚠️ no active session")
    elif cmd == "/status":
        await _prune_dead(app, store)   # show only live sessions
        await asyncio.to_thread(send_message, cfg, commands.build_status(cfg, store),
                                reply_markup=commands.dashboard_keyboard(store))
    elif cmd == "/screen":
        active = store.active_session()
        text = await _grab_screen(app, active["iterm_session_id"]) \
            if active else None
        await asyncio.to_thread(_post_screen, cfg, store, text)
    else:   # /help
        await asyncio.to_thread(send_message, cfg, commands.build_help())
    return True


async def _typing_loop(cfg) -> None:
    # Show a typing bubble while Claude is working; its absence is the "your
    # turn" signal, so no explicit waiting message is needed.
    while True:
        if is_busy(cfg):
            await asyncio.to_thread(send_chat_action, cfg)
        await asyncio.sleep(TYPING_EVERY)


async def _amain(connection) -> None:
    import iterm2

    cfg = load_config()
    store = Store(cfg.store_path)
    cfg.pid_path.write_text(str(os.getpid()))
    app = await iterm2.async_get_app(connection)
    await asyncio.to_thread(set_my_commands, cfg, commands.COMMANDS)
    # Set the persistent reply keyboard (quick commands) once; it sticks.
    await asyncio.to_thread(send_message, cfg, "🤖 bridge up",
                            reply_markup=commands.command_keyboard(), silent=True)
    typing = asyncio.ensure_future(_typing_loop(cfg))
    _log(f"listener up (pid {os.getpid()}), long-polling Telegram...")

    try:
        while True:
            try:
                updates = await asyncio.to_thread(
                    get_updates, cfg, store.get_offset())
            except Exception as exc:
                _log(f"getUpdates error: {exc}")
                await asyncio.sleep(5)
                continue

            for update in updates:
                # One bad update (e.g. an iTerm API error in _inject) must not
                # take the whole listener down — log it and move on.
                try:
                    store.set_offset(update["update_id"] + 1)
                    if await handle_callback(cfg, store, app, connection, update):
                        _log("  button tap")
                        continue
                    # Any user message clears the previous screen snapshot.
                    if (update.get("message") or {}).get("text"):
                        await asyncio.to_thread(_clear_screens, cfg, store)
                    if handle_gate_reply(cfg, update):
                        _log("  gate reply -> answered hook")
                        continue
                    if await handle_bridge_command(cfg, store, app, update):
                        _log("  bridge command")
                        continue
                    target = resolve_target(cfg, store, update)
                    if target is None:
                        continue
                    session, text = target
                    sid = session["iterm_session_id"]
                    _log(f"recv {text.rstrip()!r} -> inject {sid[:18]}")
                    ok = await _inject(app, sid, text, session.get("job_pid"))
                    if ok:
                        _log("  injected OK")
                    else:
                        _log("  blocked/not found -> notify")
                        await asyncio.to_thread(send_message, cfg, NOT_RUNNING)
                except Exception as exc:
                    _log(f"  update error: {exc}")
    finally:
        typing.cancel()
        cfg.pid_path.unlink(missing_ok=True)
        _log("listener down")


def poll_loop() -> None:
    import iterm2
    # run_until_complete owns the event loop + one connection; retry=True
    # rebuilds it if the iTerm websocket drops.
    iterm2.run_until_complete(_amain, retry=True)


if __name__ == "__main__":
    poll_loop()
