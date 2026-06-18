# Telegram Group + Topics Mode

Branch: `telegram-group`

## Problem
With 2+ concurrent Claude sessions, all messages (stream / activity / gate /
usage) interleave in one Telegram DM → hard to tell which session is which.

## Goal
Run sessions in a single private Telegram **supergroup**, one **forum topic per
project (cwd)**, so each session has its own "room". DM mode stays unchanged.

## Mode selection
- New env **`GROUP_CHAT_ID`** (the supergroup id, negative).
- **Set → group mode**: every bridge message goes to `GROUP_CHAT_ID` (+ a
  `message_thread_id`). Nothing is sent to the DM chat.
- **Unset → DM mode**: current behavior, untouched.
- `ALLOWED_CHAT_ID` keeps its meaning — the **owner's user id**, used only to
  identify the sender (both modes). It is NOT a send target in group mode.

## Auth (leak prevention)
- DM mode (unchanged): accept if `from.id == ALLOWED_CHAT_ID`.
- Group mode: accept only if `chat.id == GROUP_CHAT_ID` **AND**
  `from.id == ALLOWED_CHAT_ID` → other group members cannot drive Claude.

## Operator prerequisites (group mode)
1. Bot **privacy mode OFF** (BotFather `/setprivacy` → Disable) — else the bot
   only sees commands/mentions, not plain replies.
2. Bot is a **group admin** with **Manage Topics**.
3. Supergroup has **Topics (forum)** enabled.

## Topic ↔ session mapping
- Store: `session_id → topic_id` (+ remember each topic's `cwd` and basename).
- Assign a topic when a session first sends a message (`resolve_topic`):
  - If a topic for this `cwd` exists and is **free** (its previous session is
    gone/pruned) → **reuse** it.
  - Else `createForumTopic(name = basename(cwd))`; if a **live** topic already
    uses that basename, suffix `#N` (`proj #2`, `proj #3`).
- Topics persist in Telegram; pruning a dead session only frees its binding so
  the topic can be reused later (reopen same cwd → same room).

## Routing
- **Outbound:** every send path (stream / activity / gate / usage / bridge
  replies) resolves its session's topic and posts with `message_thread_id`.
  `send_message` / `send_photo`-style calls gain an optional `message_thread_id`
  and, in group mode, target `GROUP_CHAT_ID`.
- **Inbound:** a reply/message arrives with `message_thread_id` → map
  `topic → session` → inject into that session. The topic identifies the
  session (reply-binding still works but is no longer required in group mode).

## Concurrency
- Two hooks for a brand-new session could race to create its topic. Guard
  `resolve_topic` with a cheap check-and-set (file lock or store-level guard);
  a rare duplicate topic is cosmetic, not a correctness break — log if it
  happens.

## Telegram API additions
- `createForumTopic(chat_id, name)` → topic id.
- `send_message` / `send_photo`: optional `message_thread_id`; `chat_id` =
  `GROUP_CHAT_ID` in group mode.
- (Optional) `closeForumTopic` on session end — deferred; topics stay open.

## Additive constraint (IMPORTANT)
- **Do not remove or rewrite DM logic.** Add group-mode branches alongside it,
  touching as few files / as locally as possible.
- New features land on `main` first, then `main` merges into this branch — so
  keep the diff small and localized to avoid merge conflicts.
- A single `cfg` helper (e.g. `cfg.group_id` / `is_group_mode(cfg)`) gates the
  new path; everything else stays on the existing code.

## Out of scope (for now)
- Per-session sub-rooms when two live sessions share one cwd → handled by
  `#N` topics (decided), no further splitting.
- Closing/archiving topics, topic renaming UI, official quota per topic.

## Testable units
- `is_allowed` group variant (chat + sender).
- `resolve_topic` (reuse-when-free, `#N` collision) — pure over store + a
  create callback.
- topic↔session inbound routing.
- send target selection (group vs DM) + `message_thread_id` threading.
