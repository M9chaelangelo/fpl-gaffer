"""The rebuild, in the page that works without JavaScript.

The app is the thing Michael will actually look at, but the plain report is
what still works when the app breaks — and a wildcard is the one decision you
cannot re-run at the deadline if the page is blank. So it renders here too,
and the test proves it rather than assuming it.
"""
from gaffer import report


def _player(pid, name, pos, ep, gw, price=5.0):
    return {"id": pid, "name": name, "pos": pos, "team": "ARS", "price": price,
            "ep": {gw: ep}, "opp": {gw: "BOU(H)"}, "exp_min": 85,
            "status": "a", "news": "", "own": 5.0}


def _ctx(wildcard=None, proj=None):
    gw = 5
    xi = [_player(i, f"P{i}", "MID", 5.0, gw) for i in range(1, 12)]
    bench = [_player(i, f"B{i}", "DEF", 2.0, gw) for i in range(12, 16)]
    week = {"gw": gw, "chip": None, "in": [], "out": [],
            "captain": {"id": 1, "name": "P1"}, "ep": 60.0,
            "xi": xi, "bench": bench, "hits": 0}
    return {
        "weeks": [week], "deadline": "Fri 18 Sep 18:30", "gems": [],
        "prices": [], "hit_verdict": "Roll it.", "flagged": [],
        "pack_own": {}, "league_line": "", "rationale": [],
        "clean_sheets": [], "planner": None,
        "wildcard": wildcard, "proj": proj,
    }


def _draft():
    gw = 6
    proj = {}
    for i in range(1, 20):
        proj[i] = _player(i, f"W{i}", ["GKP", "DEF", "MID", "FWD"][i % 4],
                          4.0 + i / 10, gw, price=4.0 + i / 10)
    squad = list(range(1, 16))
    wc = {
        "for_gw": 6, "squad": squad, "cost": 99.4, "budget": 100.0,
        "in_bank": 0.6, "gws": [6, 7, 8], "score": 410.2, "optimal": True,
        "pool_size": 188, "assumes_no_transfers": True,
        "spend": {"GKP": 9.0, "DEF": 25.0, "MID": 40.0, "FWD": 25.4},
        "weeks": [{"gw": 6, "xi": squad[:11], "bench": squad[11:],
                   "formation": "3-5-2", "captain": 1, "chip": None,
                   "ep": 71.0}],
        "swaps": [{"out": 3, "in": 17, "gap": 0.42},
                  {"out": 5, "in": None, "gap": None}],
        "change": {"keep": [1], "sell": [90], "buy": [2, 3]},
    }
    proj[90] = _player(90, "Sold Man", "MID", 1.0, gw)
    return wc, proj


def test_the_draft_reaches_the_page(tmp_path):
    out = tmp_path / "index.html"
    wc, proj = _draft()
    report.render(_ctx(wc, proj), str(out))
    html = out.read_text(encoding="utf-8")

    assert "The GW6 wildcard" in html
    assert "99.4m spent" in html
    assert "0.6m in the bank" in html
    # Every drafted player is named, not just the eleven.
    for pid in wc["squad"]:
        assert proj[pid]["name"] in html
    assert "Sold Man" in html
    # The closest calls, including the slot with no affordable alternative.
    assert "The closest calls" in html
    assert "0.42" in html


def test_the_assumption_is_printed_not_buried(tmp_path):
    """The budget is today's squad value. If the wildcard is weeks away that
    is an assumption, and a page that hides it is lying quietly."""
    out = tmp_path / "index.html"
    wc, proj = _draft()
    report.render(_ctx(wc, proj), str(out))
    assert "no transfers before the wildcard" in out.read_text(encoding="utf-8")

    out2 = tmp_path / "now.html"
    wc["assumes_no_transfers"] = False
    report.render(_ctx(wc, proj), str(out2))
    assert "no transfers before the wildcard" not in out2.read_text(encoding="utf-8")


def test_a_timed_out_solve_says_so(tmp_path):
    out = tmp_path / "index.html"
    wc, proj = _draft()
    wc["optimal"] = False
    report.render(_ctx(wc, proj), str(out))
    assert "time limit" in out.read_text(encoding="utf-8")


def test_page_renders_without_a_wildcard(tmp_path):
    out = tmp_path / "index.html"
    report.render(_ctx(None), str(out))
    html = out.read_text(encoding="utf-8")
    assert "wildcard" not in html.lower().split("when to wildcard")[0]
    assert "Your team this week" in html
