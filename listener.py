import asyncio
import os
import sys
import time

from bridge.config import is_allowed, load_config
from bridge.gate import resolve_pending
from bridge.iterm import should_inject, strip_session_prefix
from bridge.store import Store
from bridge.telegram import get_updates, send_message

NOT_RUNNING = "claude not running in this session — cancelled"


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


async def _inject(app, session_id, text, expected_pid) -> bool:
    """Inject via the SHARED, already-open iTerm connection (app)."""
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
                # Send Enter separately (after the paste settles) — a long
                # message arrives as a bracketed paste, which swallows a
                # trailing \r into the input instead of submitting.
                await asyncio.sleep(0.15)
                await session.async_send_text("\r")
                return True
    return False  # session not found (tab closed)


async def _amain(connection) -> None:
    import iterm2

    cfg = load_config()
    store = Store(cfg.store_path)
    cfg.pid_path.write_text(str(os.getpid()))
    app = await iterm2.async_get_app(connection)
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
                store.set_offset(update["update_id"] + 1)
                if handle_gate_reply(cfg, update):
                    _log("  gate reply -> answered hook")
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
    finally:
        cfg.pid_path.unlink(missing_ok=True)
        _log("listener down")


def poll_loop() -> None:
    import iterm2
    # run_until_complete owns the event loop + one connection; retry=True
    # rebuilds it if the iTerm websocket drops.
    iterm2.run_until_complete(_amain, retry=True)


if __name__ == "__main__":
    poll_loop()
