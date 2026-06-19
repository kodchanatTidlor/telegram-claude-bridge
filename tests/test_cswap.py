from bridge import cswap

SAMPLE = """Accounts:
  1: Kodchanat.V@tidlor.com [heygoody]
     | 5h:   0%
     | 7d:  60%   resets Jun 22 13:59  in 3d 0h
     . oauth: fresh, refresh token yes, expires 21:17 in 7h 56m

  2: kodchanat2@gmail.com [kodchanat2@gmail.com's Organization] (active)
     | 5h:  76%   resets 16:59         in 3h 38m
     | 7d:  21%   resets 14:59         in 1h 38m
     . oauth: fresh, refresh token yes, expires 19:20 in 5h 59m

Running instances:
  CLI   ~/telegram-claude-bridge  (1 session)
"""


def test_parse_two_accounts():
    accts = cswap.parse(SAMPLE)
    assert len(accts) == 2                      # running instances ignored
    a1, a2 = accts
    assert a1["email"] == "Kodchanat.V@tidlor.com" and not a1["active"]
    assert a2["email"] == "kodchanat2@gmail.com" and a2["active"]


def test_parse_windows_and_optional_reset():
    a1, a2 = cswap.parse(SAMPLE)
    assert a1["windows"]["5h"] == {"pct": 0, "reset": None, "in": None}
    assert a1["windows"]["7d"]["pct"] == 60
    assert a1["windows"]["7d"]["reset"] == "Jun 22 13:59"
    assert a1["windows"]["7d"]["in"] == "3d 0h"
    assert a2["windows"]["5h"] == {"pct": 76, "reset": "16:59", "in": "3h 38m"}


def test_parse_empty():
    assert cswap.parse("Accounts:\n\nRunning instances:\n") == []


def test_fetch_uses_injected_runner():
    assert cswap.fetch(run=lambda: SAMPLE)[0]["org"] == "heygoody"


def test_switch_to_passes_ident():
    got = []
    cswap.switch_to("2", run=got.append)
    assert got == ["2"]
