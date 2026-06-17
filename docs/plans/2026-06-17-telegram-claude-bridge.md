# Telegram ↔ Claude Code Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When Claude Code finishes a task in iTerm2, push a recap to Telegram; a reply in Telegram is injected into the live Claude session.

**Architecture:** Two decoupled processes — a Claude `Stop` hook (`recap_hook.py`) that sends recaps, and a long-running daemon (`listener.py`) that polls Telegram and injects replies into iTerm2 via its Python API. A control CLI (`bridgectl.py`) toggles the bridge on/off via a flag file; the hook is a no-op when off. Pure logic lives in small `bridge/` modules so it is unit-testable without network or iTerm.

**Tech Stack:** Python 3.11+, `httpx` (Telegram HTTP), `iterm2` (injection), `pytest` (tests).

## Global Constraints

- Python 3.11+, standard `venv`.
- Standalone repo at `~/telegram-claude-bridge/` — never imports from or writes to any other project.
- Secrets only in `.env` (gitignored); `.env.example` committed with placeholder values.
- The hook MUST always exit 0 — a failure never blocks Claude.
- Single allowlisted `ALLOWED_CHAT_ID`; messages from any other id are dropped silently.
- Recap sends the raw final assistant message (no summarization, no status-only mode).
- Telegram single-chat sends respect `429` `retry_after`; keep under ~1 msg/sec.
- Inject only when the iTerm session foreground job is the live Claude process.
- CLI file is `bridgectl.py` (NOT `bridge.py`) to avoid shadowing the `bridge/` package.

---

## File Structure

- `bridge/__init__.py` — package marker.
- `bridge/config.py` — load `.env`, expose settings + paths, allowlist check.
- `bridge/transcript.py` — parse a transcript JSONL into `(last_user_prompt, last_assistant_message)`.
- `bridge/recap.py` — build the recap text (blockquote + body) with MarkdownV2 escaping.
- `bridge/store.py` — JSON mapping store (sessions, offset).
- `bridge/telegram.py` — `send_message` / `get_updates` over httpx, with `429` backoff.
- `bridge/iterm.py` — guard predicate + iTerm2 send (the only module touching the iterm2 SDK).
- `recap_hook.py` — Stop-hook entrypoint.
- `listener.py` — polling daemon.
- `bridgectl.py` — control CLI (`on` / `off` / `status`).
- `tests/` — one test module per `bridge/` logic module.
- `.env.example`, `requirements.txt`, `.gitignore`, `README.md`.

Naming locked across tasks:
- `Config` fields: `bot_token: str`, `allowed_chat_id: int`, `poll_timeout: int`, `store_path: Path`, `flag_path: Path`, `pid_path: Path`.
- `load_config() -> Config`
- `is_allowed(cfg, chat_id) -> bool`
- `parse_transcript(path) -> tuple[str | None, str | None]`  → `(user_prompt, assistant_text)`
- `build_recap(user_prompt, assistant_text) -> str`
- `escape_md_v2(text) -> str`
- `Store`: `upsert_session(iterm_session_id, job_pid, cwd, recap_message_id)`, `active_session() -> dict | None`, `session_by_recap(message_id) -> dict | None`, `get_offset() -> int`, `set_offset(n)`.
- `send_message(cfg, text, reply_to=None) -> int`
- `get_updates(cfg, offset) -> list[dict]`
- `should_inject(job_name, job_pid, expected_pid) -> bool`
- `CLAUDE_JOB_NAMES = {"claude", "node"}`

---

### Task 1: Project scaffold + dependencies

**Files:** Create `requirements.txt`, `.gitignore`, `.env.example`, `bridge/__init__.py`, `tests/__init__.py`, `pytest.ini`

**Interfaces:** Consumes nothing. Produces an importable `bridge` package + installed deps.

- [ ] **Step 1: `requirements.txt`**
```
httpx==0.27.2
iterm2==2.7
pytest==8.3.3
```
- [ ] **Step 2: `.gitignore`**
```
.env
.enabled
.listener.pid
.store.json
__pycache__/
*.pyc
.venv/
```
- [ ] **Step 3: `.env.example`**
```
BOT_TOKEN=123456:replace-with-botfather-token
ALLOWED_CHAT_ID=000000000
POLL_TIMEOUT=50
```
- [ ] **Step 4: `pytest.ini`**
```ini
[pytest]
testpaths = tests
```
- [ ] **Step 5: empty `bridge/__init__.py` and `tests/__init__.py`**
- [ ] **Step 6:** `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt` → installs OK.
- [ ] **Step 7: Commit** `git commit -m "chore: project scaffold + dependencies"`

---

### Task 2: Config loader + allowlist

**Files:** Create `bridge/config.py`; Test `tests/test_config.py`

**Interfaces:** Produces `Config`, `load_config() -> Config`, `is_allowed(cfg, chat_id) -> bool`.

- [ ] **Step 1: failing test**
```python
# tests/test_config.py
import pytest
from bridge.config import Config, is_allowed, load_config


def make_cfg(**kw):
    base = dict(bot_token="t", allowed_chat_id=42, poll_timeout=50,
                store_path="s", flag_path="f", pid_path="p")
    base.update(kw)
    return Config(**base)


def test_is_allowed_true_for_matching_id():
    assert is_allowed(make_cfg(), 42) is True


def test_is_allowed_false_for_other_id():
    assert is_allowed(make_cfg(), 99) is False


def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "abc")
    monkeypatch.setenv("ALLOWED_CHAT_ID", "777")
    cfg = load_config()
    assert cfg.bot_token == "abc"
    assert cfg.allowed_chat_id == 777
    assert cfg.poll_timeout == 50


def test_load_config_missing_token_raises(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setenv("ALLOWED_CHAT_ID", "1")
    with pytest.raises(ValueError):
        load_config()
```
Note: `load_config` tests assume no `.env` shadows env vars. Run from a clean checkout (repo `.env` is gitignored).

- [ ] **Step 2:** `pytest tests/test_config.py -v` → FAIL `ModuleNotFoundError: bridge.config`.
- [ ] **Step 3: implementation**
```python
# bridge/config.py
import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    bot_token: str
    allowed_chat_id: int
    poll_timeout: int
    store_path: Path
    flag_path: Path
    pid_path: Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def load_config() -> Config:
    _load_dotenv(BASE_DIR / ".env")
    token = os.environ.get("BOT_TOKEN")
    chat = os.environ.get("ALLOWED_CHAT_ID")
    if not token:
        raise ValueError("BOT_TOKEN missing")
    if not chat:
        raise ValueError("ALLOWED_CHAT_ID missing")
    return Config(
        bot_token=token,
        allowed_chat_id=int(chat),
        poll_timeout=int(os.environ.get("POLL_TIMEOUT", "50")),
        store_path=Path(os.environ.get("STORE_PATH", BASE_DIR / ".store.json")),
        flag_path=BASE_DIR / ".enabled",
        pid_path=BASE_DIR / ".listener.pid",
    )


def is_allowed(cfg: Config, chat_id: int) -> bool:
    return chat_id == cfg.allowed_chat_id
```
- [ ] **Step 4:** `pytest tests/test_config.py -v` → 4 passed.
- [ ] **Step 5: Commit** `git commit -m "feat: config loader + allowlist"`

---

### Task 3: Transcript parser

**Files:** Create `bridge/transcript.py`; Test `tests/test_transcript.py`

**Interfaces:** `parse_transcript(path) -> (user_prompt, assistant_text)`. Last human user prompt (skip tool-result-only user lines) + last assistant text (concatenated text blocks). Either may be `None`.

- [ ] **Step 1: failing test**
```python
# tests/test_transcript.py
import json
from bridge.transcript import parse_transcript


def write_jsonl(tmp_path, rows):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    return str(p)


def test_extracts_last_user_and_assistant(tmp_path):
    rows = [
        {"type": "user", "message": {"role": "user", "content": "first"}},
        {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "text", "text": "hi"}]}},
        {"type": "user", "message": {"role": "user", "content": "second"}},
        {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "text", "text": "done "},
                        {"type": "text", "text": "ok"}]}},
    ]
    user, asst = parse_transcript(write_jsonl(tmp_path, rows))
    assert user == "second"
    assert asst == "done ok"


def test_skips_tool_result_user_lines(tmp_path):
    rows = [
        {"type": "user", "message": {"role": "user", "content": "real prompt"}},
        {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "tool_use", "name": "X"}]}},
        {"type": "user", "message": {"role": "user",
            "content": [{"type": "tool_result", "content": "out"}]}},
        {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "text", "text": "final"}]}},
    ]
    user, asst = parse_transcript(write_jsonl(tmp_path, rows))
    assert user == "real prompt"
    assert asst == "final"


def test_missing_file_returns_none(tmp_path):
    user, asst = parse_transcript(str(tmp_path / "nope.jsonl"))
    assert user is None and asst is None


def test_empty_assistant_text_returns_none(tmp_path):
    rows = [{"type": "assistant", "message": {"role": "assistant",
             "content": [{"type": "tool_use", "name": "X"}]}}]
    user, asst = parse_transcript(write_jsonl(tmp_path, rows))
    assert asst is None
```
- [ ] **Step 2:** `pytest tests/test_transcript.py -v` → FAIL `ModuleNotFoundError`.
- [ ] **Step 3: implementation**
```python
# bridge/transcript.py
import json
from pathlib import Path


def _text_blocks(content) -> str | None:
    if isinstance(content, str):
        return content or None
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        joined = "".join(parts)
        return joined or None
    return None


def _is_tool_result_only(content) -> bool:
    if not isinstance(content, list) or not content:
        return False
    return all(isinstance(b, dict) and b.get("type") == "tool_result"
               for b in content)


def parse_transcript(path: str) -> tuple[str | None, str | None]:
    p = Path(path)
    if not p.exists():
        return None, None
    user_prompt = None
    assistant_text = None
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = row.get("message") or {}
        role = msg.get("role")
        content = msg.get("content")
        if role == "user":
            if _is_tool_result_only(content):
                continue
            text = _text_blocks(content)
            if text is not None:
                user_prompt = text
        elif role == "assistant":
            text = _text_blocks(content)
            if text is not None:
                assistant_text = text
    return user_prompt, assistant_text
```
- [ ] **Step 4:** `pytest tests/test_transcript.py -v` → 4 passed.
- [ ] **Step 5: Commit** `git commit -m "feat: transcript parser"`

---

### Task 4: Recap builder + MarkdownV2 escaping

**Files:** Create `bridge/recap.py`; Test `tests/test_recap.py`

**Interfaces:** `escape_md_v2(text) -> str`, `build_recap(user_prompt, assistant_text) -> str`, `PROMPT_MAX`. Prompt truncated to `PROMPT_MAX`, rendered as MarkdownV2 blockquote (`>` per line); body follows. Empty assistant text → placeholder.

- [ ] **Step 1: failing test**
```python
# tests/test_recap.py
from bridge.recap import build_recap, escape_md_v2, PROMPT_MAX


def test_escape_md_v2_escapes_specials():
    assert escape_md_v2("a_b*c.") == "a\\_b\\*c\\."


def test_build_recap_has_blockquote_and_body():
    out = build_recap("fix the bug", "all done")
    assert out.splitlines()[0].startswith(">")
    assert "fix the bug" in out
    assert "all done" in out


def test_build_recap_truncates_long_prompt():
    out = build_recap("x" * 500, "body")
    assert ("x" * PROMPT_MAX) in out
    assert ("x" * (PROMPT_MAX + 1)) not in out


def test_build_recap_empty_assistant_uses_placeholder():
    assert "no reply text" in build_recap("prompt", None)


def test_build_recap_no_prompt_omits_blockquote():
    out = build_recap(None, "body")
    assert not out.startswith(">")
    assert "body" in out
```
- [ ] **Step 2:** `pytest tests/test_recap.py -v` → FAIL `ModuleNotFoundError`.
- [ ] **Step 3: implementation**
```python
# bridge/recap.py
PROMPT_MAX = 300
_SPECIALS = r"_*[]()~`>#+-=|{}.!"
EMPTY_BODY = "[done \\— no reply text]"


def escape_md_v2(text: str) -> str:
    out = []
    for ch in text:
        out.append("\\" + ch if ch in _SPECIALS else ch)
    return "".join(out)


def build_recap(user_prompt, assistant_text) -> str:
    body = escape_md_v2(assistant_text) if assistant_text else EMPTY_BODY
    if user_prompt:
        clipped = user_prompt[:PROMPT_MAX]
        lines = clipped.splitlines() or [""]
        quote = "\n".join(">" + escape_md_v2(ln) for ln in lines)
        return f"{quote}\n\n{body}"
    return body
```
Note: `EMPTY_BODY` pre-escapes its `—` so it is valid MarkdownV2.
- [ ] **Step 4:** `pytest tests/test_recap.py -v` → 5 passed.
- [ ] **Step 5: Commit** `git commit -m "feat: recap builder + markdownv2 escaping"`

---

### Task 5: Mapping store

**Files:** Create `bridge/store.py`; Test `tests/test_store.py`

**Interfaces:** `Store(path)` with `upsert_session(iterm_session_id, job_pid, cwd, recap_message_id)`, `active_session()`, `session_by_recap(message_id)`, `get_offset()`, `set_offset(n)`. Session keys: `iterm_session_id`, `job_pid`, `cwd`, `recap_message_id`, `ts`.

- [ ] **Step 1: failing test**
```python
# tests/test_store.py
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
```
- [ ] **Step 2:** `pytest tests/test_store.py -v` → FAIL `ModuleNotFoundError`.
- [ ] **Step 3: implementation**
```python
# bridge/store.py
import json
import time
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = Path(path)

    def _read(self) -> dict:
        if not self.path.exists():
            return {"sessions": [], "active": None, "offset": 0}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {"sessions": [], "active": None, "offset": 0}

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(self.path)

    def upsert_session(self, iterm_session_id, job_pid, cwd, recap_message_id):
        data = self._read()
        entry = {
            "iterm_session_id": iterm_session_id,
            "job_pid": job_pid,
            "cwd": cwd,
            "recap_message_id": recap_message_id,
            "ts": time.time(),
        }
        sessions = [s for s in data["sessions"]
                    if s["iterm_session_id"] != iterm_session_id]
        sessions.append(entry)
        data["sessions"] = sessions
        data["active"] = iterm_session_id
        self._write(data)

    def active_session(self):
        data = self._read()
        active = data.get("active")
        for s in reversed(data["sessions"]):
            if s["iterm_session_id"] == active:
                return s
        return None

    def session_by_recap(self, message_id):
        data = self._read()
        for s in reversed(data["sessions"]):
            if s["recap_message_id"] == message_id:
                return s
        return None

    def get_offset(self) -> int:
        return int(self._read().get("offset", 0))

    def set_offset(self, n: int) -> None:
        data = self._read()
        data["offset"] = int(n)
        self._write(data)
```
Note: `tmp.replace()` is atomic on the same filesystem; hook writes sessions, daemon writes offset; last-writer-wins on distinct keys is acceptable for this single-user tool.
- [ ] **Step 4:** `pytest tests/test_store.py -v` → 5 passed.
- [ ] **Step 5: Commit** `git commit -m "feat: mapping store with offset persistence"`

---

### Task 6: Telegram client (send/getUpdates + 429 backoff)

**Files:** Create `bridge/telegram.py`; Test `tests/test_telegram.py`

**Interfaces:** `send_message(cfg, text, reply_to=None) -> int`, `get_updates(cfg, offset) -> list`. httpx; `send_message` retries once on `429` honoring `retry_after`; `parse_mode=MarkdownV2`.

- [ ] **Step 1: failing test**
```python
# tests/test_telegram.py
import httpx
from bridge.config import Config
from bridge import telegram


def make_cfg():
    return Config(bot_token="TOK", allowed_chat_id=5, poll_timeout=1,
                  store_path="s", flag_path="f", pid_path="p")


def test_send_message_returns_message_id(monkeypatch):
    calls = {}

    def fake_post(url, json, timeout):
        calls["url"] = url
        calls["json"] = json
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 77}})

    monkeypatch.setattr(telegram.httpx, "post", fake_post)
    mid = telegram.send_message(make_cfg(), "hello", reply_to=12)
    assert mid == 77
    assert "sendMessage" in calls["url"]
    assert calls["json"]["reply_to_message_id"] == 12
    assert calls["json"]["parse_mode"] == "MarkdownV2"


def test_send_message_retries_on_429(monkeypatch):
    responses = [
        httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 0}}),
        httpx.Response(200, json={"ok": True, "result": {"message_id": 9}}),
    ]
    monkeypatch.setattr(telegram.time, "sleep", lambda s: None)
    monkeypatch.setattr(telegram.httpx, "post", lambda *a, **k: responses.pop(0))
    assert telegram.send_message(make_cfg(), "x") == 9


def test_get_updates_returns_results(monkeypatch):
    def fake_get(url, params, timeout):
        return httpx.Response(200, json={"ok": True, "result": [{"update_id": 1}]})

    monkeypatch.setattr(telegram.httpx, "get", fake_get)
    assert telegram.get_updates(make_cfg(), offset=0) == [{"update_id": 1}]
```
- [ ] **Step 2:** `pytest tests/test_telegram.py -v` → FAIL `ModuleNotFoundError`.
- [ ] **Step 3: implementation**
```python
# bridge/telegram.py
import time

import httpx

API = "https://api.telegram.org/bot{token}/{method}"


def _url(cfg, method):
    return API.format(token=cfg.bot_token, method=method)


def send_message(cfg, text, reply_to=None) -> int:
    payload = {
        "chat_id": cfg.allowed_chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
    }
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to

    for _ in range(2):
        resp = httpx.post(_url(cfg, "sendMessage"), json=payload, timeout=15)
        if resp.status_code == 429:
            retry = resp.json().get("parameters", {}).get("retry_after", 1)
            time.sleep(retry)
            continue
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"telegram send failed: {data}")
        return data["result"]["message_id"]
    raise RuntimeError("telegram send failed after retry")


def get_updates(cfg, offset) -> list:
    params = {"offset": offset, "timeout": cfg.poll_timeout}
    resp = httpx.get(_url(cfg, "getUpdates"), params=params,
                     timeout=cfg.poll_timeout + 10)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"telegram getUpdates failed: {data}")
    return data["result"]
```
- [ ] **Step 4:** `pytest tests/test_telegram.py -v` → 3 passed.
- [ ] **Step 5: Commit** `git commit -m "feat: telegram client with 429 backoff"`

---

### Task 7: iTerm inject guard + sender

**Files:** Create `bridge/iterm.py`; Test `tests/test_iterm.py`

**Interfaces:** `should_inject(job_name, job_pid, expected_pid) -> bool`, `CLAUDE_JOB_NAMES`, `strip_session_prefix(env_value) -> str`, async `send_text(session_id, text, expected_pid) -> bool` (SDK; not unit-tested). Inject allowed when job name is a Claude job AND (no expected pid OR pid matches).

- [ ] **Step 1: failing test**
```python
# tests/test_iterm.py
from bridge.iterm import should_inject, strip_session_prefix, CLAUDE_JOB_NAMES


def test_strip_session_prefix():
    assert strip_session_prefix("w0t2p0:ABC-123") == "ABC-123"
    assert strip_session_prefix("ABC-123") == "ABC-123"


def test_should_inject_true_for_claude_job_matching_pid():
    assert should_inject("claude", 100, 100) is True


def test_should_inject_true_when_no_expected_pid():
    assert should_inject("node", 100, None) is True


def test_should_inject_false_for_shell():
    assert should_inject("zsh", 100, 100) is False
    assert should_inject("bash", 100, None) is False


def test_should_inject_false_on_pid_mismatch():
    assert should_inject("claude", 200, 100) is False


def test_should_inject_false_when_job_unknown():
    assert should_inject(None, 100, None) is False


def test_claude_job_names():
    assert "claude" in CLAUDE_JOB_NAMES and "node" in CLAUDE_JOB_NAMES
```
- [ ] **Step 2:** `pytest tests/test_iterm.py -v` → FAIL `ModuleNotFoundError`.
- [ ] **Step 3: implementation**
```python
# bridge/iterm.py
CLAUDE_JOB_NAMES = {"claude", "node"}


def strip_session_prefix(env_value: str) -> str:
    return env_value.split(":", 1)[1] if ":" in env_value else env_value


def should_inject(job_name, job_pid, expected_pid) -> bool:
    if job_name is None:
        return False
    base = job_name.rsplit("/", 1)[-1].lower()
    if base not in CLAUDE_JOB_NAMES:
        return False
    if expected_pid is not None and job_pid != expected_pid:
        return False
    return True


async def send_text(session_id: str, text: str, expected_pid=None) -> bool:
    """Connect to iTerm2, find the session, apply guard, send text.

    Returns True if injected, False if guard blocked it. Touches the
    iterm2 SDK; covered by manual e2e, not unit tests.
    """
    import iterm2

    sent = {"ok": False}
    target = strip_session_prefix(session_id)

    async def main(connection):
        app = await iterm2.async_get_app(connection)
        for window in app.windows:
            for tab in window.tabs:
                for session in tab.sessions:
                    if strip_session_prefix(session.session_id) != target:
                        continue
                    job_name = await session.async_get_variable("jobName")
                    job_pid_raw = await session.async_get_variable("jobPid")
                    job_pid = int(job_pid_raw) if job_pid_raw else None
                    if not should_inject(job_name, job_pid, expected_pid):
                        return
                    await session.async_send_text(text)
                    sent["ok"] = True
                    return

    connection = await iterm2.Connection.async_create()
    await main(connection)
    return sent["ok"]
```
Note: pure functions are the unit-tested contract; `send_text` wires them to the SDK (e2e in Task 11). If the installed `iterm2` needs `iterm2.run_until_complete`, adapt the connection bootstrap — guard logic stays unchanged.
- [ ] **Step 4:** `pytest tests/test_iterm.py -v` → 7 passed.
- [ ] **Step 5: Commit** `git commit -m "feat: iterm inject guard + sender"`

---

### Task 8: Recap hook entrypoint

**Files:** Create `recap_hook.py`; Test `tests/test_recap_hook.py`

**Interfaces:** `run(stdin_text, env, cfg, store, send_fn, parse_fn) -> int`. Always returns 0. Skips when flag absent or `ITERM_SESSION_ID` missing.

- [ ] **Step 1: failing test**
```python
# tests/test_recap_hook.py
from bridge.config import Config
from bridge.store import Store
import recap_hook


def make_cfg(tmp_path):
    return Config(bot_token="t", allowed_chat_id=1, poll_timeout=1,
                  store_path=tmp_path / "s.json",
                  flag_path=tmp_path / ".enabled",
                  pid_path=tmp_path / ".pid")


def test_skips_when_flag_absent(tmp_path):
    cfg = make_cfg(tmp_path)
    sent = []
    code = recap_hook.run("{}", {}, cfg, Store(cfg.store_path),
                          lambda *a, **k: sent.append(a), lambda p: ("u", "a"))
    assert code == 0 and sent == []


def test_skips_when_no_iterm_session(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.flag_path.write_text("1")
    sent = []
    code = recap_hook.run('{"transcript_path":"x","cwd":"/c"}', {},
                          cfg, Store(cfg.store_path),
                          lambda *a, **k: sent.append(a), lambda p: ("u", "a"))
    assert code == 0 and sent == []


def test_sends_recap_and_stores(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.flag_path.write_text("1")
    store = Store(cfg.store_path)
    sent = {}

    def send_fn(c, text, reply_to=None):
        sent["text"] = text
        return 55

    env = {"ITERM_SESSION_ID": "w0t1p0:GUID", "JOB_PID": "321"}
    code = recap_hook.run('{"transcript_path":"x","cwd":"/c"}', env,
                          cfg, store, send_fn, lambda p: ("fix bug", "done"))
    assert code == 0
    assert "fix bug" in sent["text"] and "done" in sent["text"]
    a = store.active_session()
    assert a["iterm_session_id"] == "w0t1p0:GUID"
    assert a["job_pid"] == 321
    assert a["recap_message_id"] == 55


def test_returns_zero_even_if_send_raises(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.flag_path.write_text("1")

    def boom(*a, **k):
        raise RuntimeError("net down")

    env = {"ITERM_SESSION_ID": "x:y", "JOB_PID": "1"}
    code = recap_hook.run('{"transcript_path":"x","cwd":"/c"}', env,
                          cfg, Store(cfg.store_path), boom, lambda p: ("u", "a"))
    assert code == 0
```
- [ ] **Step 2:** `pytest tests/test_recap_hook.py -v` → FAIL `ModuleNotFoundError: recap_hook`.
- [ ] **Step 3: implementation**
```python
# recap_hook.py
import json
import os
import sys

from bridge.config import load_config
from bridge.recap import build_recap
from bridge.store import Store
from bridge.telegram import send_message
from bridge.transcript import parse_transcript


def run(stdin_text, env, cfg, store, send_fn, parse_fn) -> int:
    try:
        if not cfg.flag_path.exists():
            return 0
        iterm_session_id = env.get("ITERM_SESSION_ID")
        if not iterm_session_id:
            return 0
        payload = json.loads(stdin_text or "{}")
        transcript_path = payload.get("transcript_path", "")
        cwd = payload.get("cwd", "")
        user_prompt, assistant_text = parse_fn(transcript_path)
        text = build_recap(user_prompt, assistant_text)
        message_id = send_fn(cfg, text)
        job_pid = env.get("JOB_PID")
        store.upsert_session(iterm_session_id,
                             int(job_pid) if job_pid else None,
                             cwd, message_id)
    except Exception as exc:  # never block Claude
        sys.stderr.write(f"recap_hook error: {exc}\n")
    return 0


def main() -> int:
    cfg = load_config()
    store = Store(cfg.store_path)
    return run(sys.stdin.read(), dict(os.environ), cfg, store,
               send_message, parse_transcript)


if __name__ == "__main__":
    sys.exit(main())
```
- [ ] **Step 4:** `pytest tests/test_recap_hook.py -v` → 4 passed.
- [ ] **Step 5: Commit** `git commit -m "feat: recap hook entrypoint"`

---

### Task 9: Listener message routing

**Files:** Create `listener.py`; Test `tests/test_listener.py`

**Interfaces:** `handle_update(cfg, store, update, inject_fn, send_fn, stop_fn) -> None`. `inject_fn(session_id, text, expected_pid) -> bool`. Drops non-allowlisted; handles `/off`; resolves target (reply_to → `session_by_recap`, else `active_session`); injects; on `False`, sends "not running" notice.

- [ ] **Step 1: failing test**
```python
# tests/test_listener.py
from bridge.config import Config
from bridge.store import Store
import listener


def make_cfg(tmp_path):
    return Config(bot_token="t", allowed_chat_id=1, poll_timeout=1,
                  store_path=tmp_path / "s.json",
                  flag_path=tmp_path / ".enabled",
                  pid_path=tmp_path / ".pid")


def msg(text, chat_id=1, reply_to=None):
    m = {"message": {"from": {"id": chat_id}, "chat": {"id": chat_id},
                     "text": text}}
    if reply_to:
        m["message"]["reply_to_message"] = {"message_id": reply_to}
    return m


def test_drops_non_allowlisted(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)
    store.upsert_session("sid", 1, "/c", 10)
    injected = []
    listener.handle_update(cfg, store, msg("hi", chat_id=999),
                           lambda *a: injected.append(a) or True,
                           lambda *a, **k: None, lambda: None)
    assert injected == []


def test_off_command_calls_stop(tmp_path):
    cfg = make_cfg(tmp_path)
    stopped = []
    listener.handle_update(cfg, Store(cfg.store_path), msg("/off"),
                           lambda *a: True, lambda *a, **k: None,
                           lambda: stopped.append(True))
    assert stopped == [True]


def test_reply_routes_to_session_by_recap(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)
    store.upsert_session("sidA", 11, "/a", 10)
    store.upsert_session("sidB", 22, "/b", 20)
    captured = {}

    def inject(session_id, text, expected_pid):
        captured["sid"] = session_id
        captured["pid"] = expected_pid
        return True

    listener.handle_update(cfg, store, msg("go on", reply_to=10),
                           inject, lambda *a, **k: None, lambda: None)
    assert captured["sid"] == "sidA" and captured["pid"] == 11


def test_plain_message_routes_to_active(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)
    store.upsert_session("sidA", 11, "/a", 10)
    store.upsert_session("sidB", 22, "/b", 20)
    captured = {}
    listener.handle_update(cfg, store, msg("hi"),
                           lambda sid, t, p: captured.update(sid=sid) or True,
                           lambda *a, **k: None, lambda: None)
    assert captured["sid"] == "sidB"


def test_inject_blocked_sends_notice(tmp_path):
    cfg = make_cfg(tmp_path)
    store = Store(cfg.store_path)
    store.upsert_session("sidA", 11, "/a", 10)
    notices = []
    listener.handle_update(cfg, store, msg("hi"),
                           lambda *a: False,
                           lambda c, text, **k: notices.append(text),
                           lambda: None)
    assert any("not running" in n for n in notices)
```
- [ ] **Step 2:** `pytest tests/test_listener.py -v` → FAIL `ModuleNotFoundError: listener`.
- [ ] **Step 3: implementation**
```python
# listener.py
import sys

from bridge.config import is_allowed, load_config
from bridge.store import Store

NOT_RUNNING = "claude not running in this session — cancelled"


def handle_update(cfg, store, update, inject_fn, send_fn, stop_fn) -> None:
    message = update.get("message") or {}
    sender = (message.get("from") or {}).get("id")
    if sender is None or not is_allowed(cfg, sender):
        return
    text = message.get("text", "")
    if text.strip() == "/off":
        stop_fn()
        return

    reply = message.get("reply_to_message")
    session = None
    if reply:
        session = store.session_by_recap(reply.get("message_id"))
    if session is None:
        session = store.active_session()
    if session is None:
        return

    ok = inject_fn(session["iterm_session_id"], text + "\n",
                   session.get("job_pid"))
    if not ok:
        send_fn(cfg, NOT_RUNNING)


def _inject_sync(session_id, text, expected_pid) -> bool:
    import asyncio

    from bridge.iterm import send_text
    return asyncio.run(send_text(session_id, text, expected_pid))


def _stop():
    cfg = load_config()
    cfg.flag_path.unlink(missing_ok=True)
    sys.exit(0)


def poll_loop() -> None:
    from bridge.telegram import get_updates, send_message
    cfg = load_config()
    store = Store(cfg.store_path)
    while cfg.flag_path.exists():
        try:
            updates = get_updates(cfg, store.get_offset())
        except Exception as exc:
            sys.stderr.write(f"getUpdates error: {exc}\n")
            continue
        for update in updates:
            store.set_offset(update["update_id"] + 1)
            handle_update(cfg, store, update, _inject_sync,
                          send_message, _stop)


if __name__ == "__main__":
    poll_loop()
```
- [ ] **Step 4:** `pytest tests/test_listener.py -v` → 5 passed.
- [ ] **Step 5: Commit** `git commit -m "feat: listener message routing"`

---

### Task 10: Control CLI (on / off / status)

**Files:** Create `bridgectl.py`; Test `tests/test_bridgectl.py`

**Interfaces:** `cmd_on(cfg, spawn_fn)`, `cmd_off(cfg, kill_fn)`, `cmd_status(cfg) -> str`.

- [ ] **Step 1: failing test**
```python
# tests/test_bridgectl.py
from bridge.config import Config
import bridgectl as cli


def make_cfg(tmp_path):
    return Config(bot_token="t", allowed_chat_id=1, poll_timeout=1,
                  store_path=tmp_path / "s.json",
                  flag_path=tmp_path / ".enabled",
                  pid_path=tmp_path / ".pid")


def test_on_writes_flag_and_pid(tmp_path):
    cfg = make_cfg(tmp_path)
    cli.cmd_on(cfg, spawn_fn=lambda: 4242)
    assert cfg.flag_path.exists()
    assert cfg.pid_path.read_text().strip() == "4242"


def test_off_removes_flag_and_kills(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.flag_path.write_text("1")
    cfg.pid_path.write_text("4242")
    killed = []
    cli.cmd_off(cfg, kill_fn=lambda pid: killed.append(pid))
    assert not cfg.flag_path.exists()
    assert killed == [4242]


def test_status_reports_off(tmp_path):
    assert "off" in cli.cmd_status(make_cfg(tmp_path)).lower()


def test_status_reports_on(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.flag_path.write_text("1")
    assert "on" in cli.cmd_status(cfg).lower()
```
- [ ] **Step 2:** `pytest tests/test_bridgectl.py -v` → FAIL `ModuleNotFoundError: bridgectl`.
- [ ] **Step 3: implementation**
```python
# bridgectl.py
import os
import signal
import subprocess
import sys
from pathlib import Path

from bridge.config import load_config

BASE_DIR = Path(__file__).resolve().parent


def _spawn_listener() -> int:
    proc = subprocess.Popen(
        [sys.executable, str(BASE_DIR / "listener.py")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)
    return proc.pid


def cmd_on(cfg, spawn_fn=_spawn_listener) -> None:
    cfg.flag_path.write_text("1")
    pid = spawn_fn()
    cfg.pid_path.write_text(str(pid))
    print(f"bridge ON (listener pid {pid})")


def _kill(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def cmd_off(cfg, kill_fn=_kill) -> None:
    cfg.flag_path.unlink(missing_ok=True)
    if cfg.pid_path.exists():
        kill_fn(int(cfg.pid_path.read_text().strip()))
        cfg.pid_path.unlink(missing_ok=True)
    print("bridge OFF")


def cmd_status(cfg) -> str:
    on = cfg.flag_path.exists()
    pid = cfg.pid_path.read_text().strip() if cfg.pid_path.exists() else "-"
    return f"bridge: {'ON' if on else 'OFF'} (listener pid {pid})"


def main() -> int:
    cfg = load_config()
    arg = sys.argv[1] if len(sys.argv) > 1 else "status"
    if arg == "on":
        cmd_on(cfg)
    elif arg == "off":
        cmd_off(cfg)
    else:
        print(cmd_status(cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```
- [ ] **Step 4:** `pytest tests/test_bridgectl.py -v` → 4 passed.
- [ ] **Step 5: Commit** `git commit -m "feat: control CLI on/off/status"`

---

### Task 11: Wiring, README, manual e2e

**Files:** Create `README.md`; Modify `~/.claude/settings.json` (register Stop hook)

- [ ] **Step 1:** `pytest -v` → all tests pass.
- [ ] **Step 2: Register Stop hook in `~/.claude/settings.json`** (merge, do not clobber; append if `Stop` exists):
```json
{
  "hooks": {
    "Stop": [
      { "hooks": [
        { "type": "command",
          "command": "$HOME/telegram-claude-bridge/.venv/bin/python $HOME/telegram-claude-bridge/recap_hook.py" }
      ] }
    ]
  }
}
```
Invoke via the venv interpreter so `httpx` is importable.
- [ ] **Step 3: `README.md`** — setup (venv, .env, iTerm Enable Python API, hook registration), usage (`bridgectl.py on/status/off`, `/off`), security notes.
- [ ] **Step 4: Manual e2e**
  1. `python bridgectl.py on`
  2. Run Claude in an iTerm tab, finish a small task.
  3. Recap arrives in Telegram (blockquote prompt + final message).
  4. Reply → text appears in the live Claude session.
  5. Exit Claude to shell → reply → Telegram says "not running"; nothing typed into shell.
  6. `python bridgectl.py off` → finish a task → no Telegram message.
- [ ] **Step 5: Commit** `git commit -m "docs: README + wiring instructions"`

---

## Self-Review

**Spec coverage:** two-process (T8+T9), iTerm inject (T7), recap raw+blockquote (T3+T4), on/off flag-gated (T10+T8), inject guard (T7+T9), allowlist (T2+T9), 429 (T6), skip headless (T8), offset persist (T5+T9), hook exits 0 (T8), error notices (T4+T9). ✓

**Type consistency:** `should_inject`, `session_by_recap`, `active_session`, `upsert_session(iterm_session_id, job_pid, cwd, recap_message_id)`, `send_message(cfg, text, reply_to=)`, `build_recap(user_prompt, assistant_text)`, `inject_fn(session_id, text, expected_pid) -> bool` consistent across tasks. CLI is `bridgectl.py` (no package shadowing).

**Open follow-up (not blocking):** launchd auto-start out of scope; daemon restarts manually.
