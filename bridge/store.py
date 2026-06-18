import json
import time
from pathlib import Path

from bridge.iterm import strip_session_prefix


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
        # Dedupe by the underlying GUID: the bridge may pre-register a new
        # session by its API id (bare GUID) before its hook re-registers it
        # with the "wXtYpZ:" prefix — both are the same session.
        key = strip_session_prefix(iterm_session_id)
        sessions = [s for s in data["sessions"]
                    if strip_session_prefix(s["iterm_session_id"]) != key]
        sessions.append(entry)
        data["sessions"] = sessions
        data["active"] = iterm_session_id
        # Remember the cwd persistently so a new session can be launched there
        # even after this one closes.
        cwds = data.get("cwds", [])
        if cwd and cwd not in cwds:
            cwds.append(cwd)
            data["cwds"] = cwds
        self._write(data)

    def known_cwds(self):
        return self._read().get("cwds", [])

    def active_session(self):
        data = self._read()
        active = data.get("active")
        for s in reversed(data["sessions"]):
            if s["iterm_session_id"] == active:
                return s
        return None

    def sessions(self):
        return self._read()["sessions"]

    def set_active(self, iterm_session_id) -> None:
        data = self._read()
        data["active"] = iterm_session_id
        self._write(data)

    def prune(self, keep_ids) -> None:
        # Drop sessions no longer open in iTerm (+ their aux state). If the
        # active one is gone, fall back to the most recent survivor.
        keep = set(keep_ids)
        data = self._read()
        data["sessions"] = [s for s in data["sessions"]
                            if s["iterm_session_id"] in keep]
        for k in ("cursors", "activity", "transcripts"):
            if k in data:
                data[k] = {i: v for i, v in data[k].items() if i in keep}
        if data.get("active") not in keep:
            data["active"] = (data["sessions"][-1]["iterm_session_id"]
                              if data["sessions"] else None)
        self._write(data)

    def set_transcript(self, iterm_session_id, path) -> None:
        data = self._read()
        t = data.get("transcripts", {})
        t[iterm_session_id] = path
        data["transcripts"] = t
        self._write(data)

    def get_transcript(self, iterm_session_id):
        return self._read().get("transcripts", {}).get(iterm_session_id)

    def session_by_recap(self, message_id):
        data = self._read()
        for s in reversed(data["sessions"]):
            if s["recap_message_id"] == message_id:
                return s
        return None

    def get_cursor(self, iterm_session_id) -> int:
        # Per-session transcript line cursor: how many lines the streamer has
        # already forwarded, so it never re-sends across turns.
        return int(self._read().get("cursors", {}).get(iterm_session_id, 0))

    def set_cursor(self, iterm_session_id, n) -> None:
        data = self._read()
        cursors = data.get("cursors", {})
        cursors[iterm_session_id] = int(n)
        data["cursors"] = cursors
        self._write(data)

    def set_activity(self, iterm_session_id, message_id) -> None:
        # Track the transient "what tool is doing" message so it can be deleted
        # when the tool finishes.
        data = self._read()
        act = data.get("activity", {})
        act[iterm_session_id] = message_id
        data["activity"] = act
        self._write(data)

    def pop_activity(self, iterm_session_id):
        data = self._read()
        act = data.get("activity", {})
        mid = act.pop(iterm_session_id, None)
        data["activity"] = act
        self._write(data)
        return mid

    def get_offset(self) -> int:
        return int(self._read().get("offset", 0))

    def set_offset(self, n: int) -> None:
        data = self._read()
        data["offset"] = int(n)
        self._write(data)
