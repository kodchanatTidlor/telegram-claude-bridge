import httpx

# claude.ai web API (same one Usage4Claude calls). Auth = the session cookie
# `sessionKey=sk-ant-sid…` the user supplies via CLAUDE_SESSION_KEY.
BASE = "https://claude.ai/api"


def _get(path, key):
    resp = httpx.get(
        BASE + path,
        headers={"Cookie": f"sessionKey={key}",
                 "Accept": "application/json",
                 "User-Agent": "telegram-claude-bridge"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_usage(key, get=_get):
    """Return the org's usage payload from claude.ai, or raise. `get` is
    injectable for tests. Endpoint shape is unverified — refine after a spike
    with a real key."""
    orgs = get("/organizations", key)
    org = orgs[0]["uuid"]
    return get(f"/organizations/{org}/usage", key)
