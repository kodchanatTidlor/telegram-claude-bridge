# Telegram ↔ Claude Code Bridge — Design

**Date:** 2026-06-17
**Scope:** User-scope tool (global, all projects). Standalone repo at `~/telegram-claude-bridge/`. Not part of any project codebase.

## Goal

When Claude Code on the Mac finishes a task, a Telegram bot sends a recap to the user. When the user replies to that message in Telegram, the reply is injected into the *live* Claude Code session in iTerm2 — exactly as if the user typed it in the terminal. The conversation continues, the next completion fires another recap, and so on.

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| Goal type | A — Telegram as a remote interface to Claude Code |
| Where Claude runs | Local Mac, only while on (no 24/7 server) |
| Bridge language | Python, standalone (outside any project repo) |
| Continuation target | B — inject into the **live** iTerm2 TUI (not headless) |
| Injection mechanism | iTerm2 Python API (`iterm2` package) — `async_send_text()` |
| Recap content | Raw final assistant message + the triggering user prompt as a Telegram blockquote |
| Architecture | A — two-process: Stop hook + listener daemon, decoupled via a mapping file |
| On/off control | Manual toggle CLI (`bridge on/off/status`) + flag file; hook is a no-op when disabled. Used only while AFK |
| Data-leak risk | Accepted: solo allowlist, user reads alone, no PII in scope. (Telegram bot API is not E2E; content transits/stored on Telegram servers) |
| Spec / repo location | `~/telegram-claude-bridge/` (its own git repo) |

## Architecture

Two decoupled processes, communicating through a small on-disk mapping store.

```
~/telegram-claude-bridge/
├── bridge.py            # control CLI: on / off / status
├── recap_hook.py        # Claude Stop-hook entrypoint (short-lived)
├── listener.py          # long-running daemon (poll Telegram, inject)
├── bridge/
│   ├── config.py        # load .env, allowlist, flag path
│   ├── telegram.py      # sendMessage / getUpdates (httpx)
│   ├── transcript.py    # parse last assistant msg + last user prompt from JSONL
│   ├── store.py         # mapping file read/write (json + file lock)
│   └── iterm.py         # iterm2 API → jobName/jobPid guard + async_send_text
├── .enabled             # presence = bridge ON (gitignored)
├── .env                 # BOT_TOKEN, ALLOWED_CHAT_ID  (gitignored)
├── .env.example
├── requirements.txt     # iterm2, httpx
└── README.md
```

Hook registration in `~/.claude/settings.json` (global — fires for every project):

```json
{ "hooks": { "Stop": [{ "hooks": [{ "type": "command",
  "command": "python3 ~/telegram-claude-bridge/recap_hook.py" }] }] } }
```

## Components

- **bridge.py** — control CLI. `on` → start the listener daemon + create the `.enabled` flag. `off` → stop the daemon + remove the flag. `status` → report daemon + flag state. The bridge is used only while AFK; off by default.
- **recap_hook.py** — invoked by Claude on the `Stop` event. **First checks the `.enabled` flag; if absent, exits 0 immediately (no Telegram traffic).** Otherwise receives hook JSON on stdin (`session_id`, `transcript_path`, `cwd`), reads `$ITERM_SESSION_ID` + `jobPid` from env, parses the transcript for the last assistant message and triggering user prompt, sends the recap to Telegram, and upserts the mapping. Skips silently when `$ITERM_SESSION_ID` is absent (headless/cron sessions). **Always exits 0** so a failure never blocks Claude.
- **listener.py** — long-running daemon. Long-polls Telegram `getUpdates`, filters by allowlist, handles `/off`, resolves the target iTerm2 session, applies the inject guard, and injects the reply text.
- **bridge/config.py** — loads `.env`, exposes `BOT_TOKEN`, `ALLOWED_CHAT_ID`, optional `POLL_TIMEOUT`, `STORE_PATH`, and the `.enabled` flag path. Fails fast if required vars missing.
- **bridge/telegram.py** — thin wrappers over `sendMessage` and `getUpdates`. Handles MarkdownV2 escaping and respects `429` `retry_after` with backoff.
- **bridge/transcript.py** — given a transcript JSONL path, returns `(last_user_prompt, last_assistant_message)`.
- **bridge/store.py** — JSON mapping file with file locking. Records per-session `{iterm_session_id, job_pid, cwd, recap_message_id, ts}` plus a pointer to the most-recent active session. Persists the `getUpdates` offset.
- **bridge/iterm.py** — connects to the iTerm2 API, finds a session by id, runs the **inject guard** (verify foreground `jobName` ∈ {`claude`, `node`} and/or `jobPid` matches the recorded pid), then calls `async_send_text(text + "\n")`. Aborts + signals the caller if the guard fails.

## Data Flow

### Task done → recap

1. Claude finishes → `Stop` hook fires, hook JSON on stdin (`session_id`, `transcript_path`, `cwd`). **If the `.enabled` flag is absent, exit 0 immediately.** If `$ITERM_SESSION_ID` is absent (headless/cron), exit 0.
2. `recap_hook` reads `$ITERM_SESSION_ID` + `jobPid` and parses `transcript_path` → last assistant message + triggering user prompt.
3. Build the recap message:
   ```
   > <user prompt, truncated ~300 chars>

   <final assistant message>
   ```
   User prompt rendered as a Telegram blockquote (MarkdownV2 `>` or HTML `<blockquote>`), properly escaped.
4. `sendMessage` → Telegram (`ALLOWED_CHAT_ID`); store the returned `message_id`.
5. `store` upserts `{iterm_session_id, cwd, recap_message_id, ts}` and updates the active-session pointer.
6. Hook exits 0 regardless of outcome.

### Reply → inject

1. `listener` long-polls `getUpdates`.
2. On a new message, check `from.id == ALLOWED_CHAT_ID`; otherwise drop silently.
3. Handle commands: `/off` → stop the daemon + clear the `.enabled` flag, ack, exit.
4. Resolve the target session: if the message is a reply to a recap, look it up by `recap_message_id`; otherwise use the active-session pointer.
5. **Inject guard:** query the iTerm session foreground `jobName` (and compare `jobPid` to the recorded pid). If it is not the live Claude process (e.g. dropped to `zsh`/`bash`), **do not inject** — reply `claude not running in this session — cancelled`.
6. Guard passes → `iterm.async_send_text(text + "\n")` into that session → text appears in the live TUI.
7. Claude processes it → `Stop` hook fires → new recap (loop).

### iTerm session id note

`$ITERM_SESSION_ID` looks like `"w0t2p0:GUID"`, but the iTerm2 API `Session.session_id` is just the `GUID`. Strip the `w…:` prefix before matching.

## Security

- **Allowlist** a single `ALLOWED_CHAT_ID`. Messages from any other id are dropped silently.
- `.env` is gitignored; only `.env.example` is committed.
- The bot can type arbitrary text into the terminal → a leaked `BOT_TOKEN` lets an attacker run commands on the Mac. Treat the token as a high-value secret.
- Enable bot privacy mode in BotFather.
- No injection sanitization by design (the user *is* the one typing); the allowlist is the security boundary.
- **Inject guard** ensures replies only reach a live Claude process — never a bare shell — preventing replies from being executed as shell commands.
- **Data residency (accepted):** recap content (raw assistant text) is sent over the Telegram Bot API, which is **not end-to-end encrypted** — Telegram servers transit and store it. Accepted because: solo allowlist, user reads alone, no PII in scope. A leaked token also exposes prior recaps via `getUpdates`.
- **Off by default:** the bridge sends nothing unless explicitly turned on (`bridge on`); intended for AFK windows only.

## Error Handling

- Transcript missing or last assistant message empty → send `[done — no reply text]`.
- iTerm session not found (tab closed) → reply to Telegram: `session lost — open claude again`.
- Inject guard fails (foreground is not Claude) → reply `claude not running in this session — cancelled`; do not send text.
- Telegram `429` → respect `retry_after` header and back off; for single-chat sends keep under ~1 msg/sec.
- Telegram API failure → listener retries with backoff; the hook logs and stays silent (never blocks Claude).
- `getUpdates` offset persisted to disk to avoid reprocessing messages.
- Daemon crash → manual restart for now; a launchd plist can be added later for auto-start.

## Testing

- **Unit:** transcript parse against sample JSONL (prompt + assistant extraction), store upsert + offset persistence, allowlist filter, flag-gating (hook no-ops when `.enabled` absent), inject guard (jobName/jobPid mismatch → abort), Telegram payload build with MarkdownV2 escaping + `429` retry_after handling (mock httpx), iTerm send (mock iterm2 connection).
- **Manual e2e:** `bridge on` → run a task → recap arrives in Telegram → reply → text appears in the live iTerm session → next recap arrives → `bridge off` (or `/off`) → tasks send nothing.

## Config / Env

| Var | Purpose |
|-----|---------|
| `BOT_TOKEN` | Telegram bot token (secret) |
| `ALLOWED_CHAT_ID` | the only chat id allowed to drive the bot |
| `POLL_TIMEOUT` | optional, long-poll timeout seconds |
| `STORE_PATH` | optional, mapping file path |

## Out of Scope (YAGNI)

- 24/7 server / remote hosting
- Headless `claude -p --resume` continuation (rejected in favor of live TUI injection)
- Multi-user support
- Recap summarization / status-only mode (send raw final message — explicitly rejected)
- Auto-start daemon (launchd) — deferred
- Per-project opt-in (global flag toggle covers the AFK use case)
