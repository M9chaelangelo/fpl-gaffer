"""Smoke test for the plan section of the page.

The report is a long string builder with no return value worth asserting on,
so the test renders a whole page and checks that the plan actually reaches the
HTML — including the two things that are easy to break silently: a violation
message, and the chip-move table.
"""
import pathlib

from gaffer import report


def _player(pid, name, pos, ep, gw):
    return {"id": pid, "name": name, "pos": pos, "team": "ARS", "price": 5.0,
            "ep": {gw: ep}, "opp": {gw: "BOU(H)"}, "exp_min": 85,
            "status": "a", "news": "", "own": 5.0}


def _ctx(planner_block):
    gw = 5
    xi = [_player(i, f"P{i}", "MID", 5.0, gw) for i in range(1, 12)]
    bench = [_player(i, f"B{i}", "DEF", 2.0, gw) for i in range(12, 16)]
    week = {"gw": gw, "chip": None, "in": ["Gibbs-White"], "out": ["Wirtz"],
            "captain": {"id": 1, "name": "P1"}, "ep": 60.0,
            "xi": xi, "bench": bench, "hits": 0}
    return {
        "weeks": [week], "deadline": "Fri 18 Sep 18:30", "gems": [],
        "prices": [], "hit_verdict": "Roll it.", "flagged": [],
        "pack_own": {}, "league_line": "", "rationale": [],
        "clean_sheets": [], "planner": planner_block,
    }


def _planner(legal=True, violations=(), move_gain=3.2):
    return {
        "plan": {
            "legal": legal, "total_ep": 180.0, "total_hits": -4,
            "weeks": [
                {"gw": 5, "chip": None, "ep": 60.0, "hit": 0,
                 "free_transfers": 1, "bank": 1.4, "squad": [], "xi": [],
                 "bench": [], "captain": 1, "formation": "3-4-3", "transfers": 1},
                {"gw": 6, "chip": "wc", "ep": 62.0, "hit": 0,
                 "free_transfers": 1, "bank": 0.6, "squad": [], "xi": [],
                 "bench": [], "captain": 1, "formation": "3-4-3", "transfers": 5},
            ],
            "violations": list(violations),
        },
        "steps": {5: {"out": [1], "in": [12], "chip": None},
                  6: {"out": [], "in": [], "chip": "wc"}},
        "unresolved": [],
        "chips": {
            "bb": {"name": "Bench Boost", "ranked": [{"gw": 9, "gain": 11.0}],
                   "current_gw": 7, "best_gw": 9, "best_gain": 11.0,
                   "gain_here": 11.0 - move_gain, "move_gain": move_gain,
                   "placed": True},
        },
        "horizon": {"from": 5, "to": 9},
        "solver_total": 184.0,
        "gap": -4.0,
    }


def test_plan_section_reaches_the_page(tmp_path):
    out = tmp_path / "index.html"
    report.render(_ctx(_planner()), str(out))
    html = out.read_text(encoding="utf-8")

    assert "Your plan" in html
    assert "Chip weeks" in html
    # The gap against the solver is the number the section exists for.
    assert "4.0 behind the solver" in html
    # Chip move is shown with its sign.
    assert "+3.2" in html
    assert "GW9" in html


def test_a_broken_plan_shows_its_violations(tmp_path):
    out = tmp_path / "index.html"
    violations = [{"gw": 7, "code": "over-budget",
                   "message": "GW7 is 2.3m over budget."}]
    report.render(_ctx(_planner(legal=False, violations=violations)), str(out))
    html = out.read_text(encoding="utf-8")

    assert "cannot be played as written" in html
    assert "GW7: GW7 is 2.3m over budget." in html


def test_page_renders_without_a_plan(tmp_path):
    """No `my_plan` in config must not break the page."""
    out = tmp_path / "index.html"
    ctx = _ctx(None)
    report.render(ctx, str(out))
    html = out.read_text(encoding="utf-8")
    assert "Your plan" not in html
    assert "Your team this week" in html
