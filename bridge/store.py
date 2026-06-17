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

    def get_offset(self) -> int:
        return int(self._read().get("offset", 0))

    def set_offset(self, n: int) -> None:
        data = self._read()
        data["offset"] = int(n)
        self._write(data)
