"""Read Claude quota from `cswap` (Multi-Account Switcher for Claude Code).

cswap already tracks every managed account's 5h/7d quota via the OAuth tokens
it manages, so `/usage` can pull it straight from `cswap --list --token-status`
— no claude.ai session cookie to paste, and it covers all accounts at once.
"""
import re
import shutil
import subprocess

# "  2: foo@bar.com [Org Name] (active)"
_ACCT = re.compile(r"^\s*(\d+):\s*(\S+)\s*\[(.*?)\]\s*(\(active\))?\s*$")
# "     ├ 5h:  76%   resets 16:59   in 3h 38m"  (resets/in optional)
_WIN = re.compile(
    r"\b(5h|7d):\s*(\d+)%(?:\s+resets\s+(.+?)\s{2,}in\s+(\S.*?))?\s*$")


def available() -> bool:
    return shutil.which("cswap") is not None


def _run() -> str:
    return subprocess.run(["cswap", "--list", "--token-status"],
                          capture_output=True, text=True,
                          timeout=20, check=True).stdout


def parse(text: str) -> list:
    """Parse `cswap --list --token-status` into account dicts. The trailing
    "Running instances:" section has no [org]/window lines, so it's ignored."""
    accounts, cur = [], None
    for line in text.splitlines():
        m = _ACCT.match(line)
        if m:
            cur = {"num": int(m.group(1)), "email": m.group(2),
                   "org": m.group(3), "active": bool(m.group(4)),
                   "windows": {}}
            accounts.append(cur)
            continue
        if cur is None:
            continue
        w = _WIN.search(line)
        if w:
            cur["windows"][w.group(1)] = {
                "pct": int(w.group(2)),
                "reset": (w.group(3) or "").strip() or None,
                "in": (w.group(4) or "").strip() or None,
            }
    return accounts


def fetch(run=_run) -> list:
    return parse(run())


def _switch(ident) -> None:
    subprocess.run(["cswap", "--switch-to", str(ident)],
                   capture_output=True, text=True, timeout=20, check=True)


def switch_to(ident, run=_switch) -> None:
    """Make the given account (number or email) the active Claude account."""
    run(ident)
