"""The wildcard drafter.

The thing worth testing here is not that a MILP returns fifteen names. It is
that the squad is legal, that it fits the money, and that the three levers
Michael actually pulls — keep, ban, and a chip in a known week — change the
answer in the direction he would expect.
"""
import pytest

from gaffer import wildcard


CFG = {
    "decay": 0.9,
    "bench_weights": [0.16, 0.11, 0.06, 0.02],
    "rivalry": 0.0,
    "ceiling_weight": 6.0,
    "wildcard_time_limit": 30,
    "wildcard_min_minutes": 20,
}


def player(pid, pos, price, ep, team_id=None, *, exp_min=80, status="a",
           ceiling=None, name=None, gws=(1, 2, 3)):
    """One projection record, shaped like the real ones."""
    return {
        "id": pid,
        "name": name or f"p{pid}",
        "team": f"T{team_id if team_id is not None else pid % 10}",
        "team_id": team_id if team_id is not None else pid % 10,
        "pos": pos,
        "price": price,
        "ep": {g: ep for g in gws} if not isinstance(ep, dict) else ep,
        "exp_min": exp_min,
        "status": status,
        "own": 5.0,
        "ceiling": ceiling or {},
    }


def league(gws=(1, 2, 3)):
    """A small but realistic game: every position at every price, spread over
    enough clubs that the three-per-club rule is satisfiable."""
    proj, pid = {}, 1
    shape = {"GKP": 8, "DEF": 20, "MID": 24, "FWD": 14}
    for pos, n in shape.items():
        for k in range(n):
            # Price rises with quality, and points rise with price but with
            # diminishing returns — so cheap players are the efficient buy and
            # the solver has a real decision to make.
            price = round(4.0 + 0.5 * k, 1)
            ep = round(2.0 + 1.6 * (k ** 0.6), 2)
            proj[pid] = player(pid, pos, price, ep, team_id=pid % 12, gws=gws)
            pid += 1
    return proj


def test_pool_keeps_the_cheap_players_a_points_cut_would_drop():
    proj = league()
    gws = [1, 2, 3]
    cheapest = min(p["price"] for p in proj.values())
    picked = wildcard.pool(proj, gws, {**CFG, "wildcard_per_cell": 2})
    assert any(p["price"] == cheapest for p in picked), \
        "a rebuild is funded by the cheap end; it has to be in the pool"
    # And the expensive end survives too — this is a stratified sample, not a
    # preference for fodder.
    assert max(p["price"] for p in picked) == max(p["price"] for p in proj.values())


def test_pool_respects_ban_and_minutes_floor():
    proj = league()
    proj[1]["exp_min"] = 5                       # a body, not a footballer
    proj[2]["status"] = "i"
    ids = {p["id"] for p in wildcard.pool(proj, [1, 2, 3], CFG, ban=[3])}
    assert 1 not in ids and 2 not in ids and 3 not in ids


def test_pool_keeps_a_flagged_player_you_insist_on():
    proj = league()
    proj[4]["status"] = "i"
    ids = {p["id"] for p in wildcard.pool(proj, [1, 2, 3], CFG, keep=[4])}
    assert 4 in ids, "keep is your call, not the filter's"


def test_draft_is_a_legal_squad_inside_the_budget():
    proj = league()
    out = wildcard.draft(proj, [1, 2, 3], 100.0, CFG)
    assert len(out["squad"]) == 15
    counts = {}
    for pid in out["squad"]:
        counts[proj[pid]["pos"]] = counts.get(proj[pid]["pos"], 0) + 1
    assert counts == wildcard.SQUAD
    clubs = {}
    for pid in out["squad"]:
        clubs[proj[pid]["team_id"]] = clubs.get(proj[pid]["team_id"], 0) + 1
    assert max(clubs.values()) <= wildcard.MAX_PER_CLUB
    assert out["cost"] <= 100.0 + 1e-9
    assert out["in_bank"] == round(100.0 - out["cost"], 1)


def test_draft_spends_the_money_it_is_given():
    """A tighter budget has to produce a cheaper squad. If it does not, the
    budget constraint is decorative."""
    proj = league()
    rich = wildcard.draft(proj, [1, 2, 3], 100.0, CFG)
    poor = wildcard.draft(proj, [1, 2, 3], 80.0, CFG)
    assert poor["cost"] <= 80.0 + 1e-9
    assert poor["cost"] < rich["cost"]
    assert poor["score"] < rich["score"]


def test_keep_forces_a_player_in_and_ban_keeps_him_out():
    proj = league()
    # Someone the solver would never pick on merit: dear and useless.
    dud = 999
    proj[dud] = player(dud, "DEF", 9.5, 1.0, team_id=31)
    free = wildcard.draft(proj, [1, 2, 3], 100.0, CFG)
    assert dud not in free["squad"]
    forced = wildcard.draft(proj, [1, 2, 3], 100.0, CFG, keep=[dud])
    assert dud in forced["squad"]
    assert forced["score"] <= free["score"], "forcing a pick cannot improve it"

    star = free["squad"][0]
    without = wildcard.draft(proj, [1, 2, 3], 100.0, CFG, ban=[star])
    assert star not in without["squad"]


def test_an_unbuyable_budget_says_so():
    proj = league()
    with pytest.raises(ValueError) as e:
        wildcard.draft(proj, [1, 2, 3], 40.0, CFG)
    assert "budget" in str(e.value)


def test_bench_boost_week_buys_a_bench_that_plays():
    """Without the chip the bench is worth a sixth of its points, so the
    solver buys fodder. With it, the bench pays full price and the squad
    should get stronger where it sits."""
    proj = league()
    plain = wildcard.draft(proj, [1, 2, 3], 100.0, CFG)
    boosted = wildcard.draft(proj, [1, 2, 3], 100.0, CFG, bb_gw=2)

    def bench_points(out, gw):
        week = next(w for w in out["weeks"] if w["gw"] == gw)
        return sum(proj[i]["ep"][gw] for i in week["bench"])

    assert bench_points(boosted, 2) > bench_points(plain, 2)


def test_triple_captain_week_lets_the_tail_pick_the_armband():
    """Two comparable captains, one of whom hauls. Expected points cannot tell
    them apart; the ceiling can, and only in the week the chip is on."""
    proj = league()
    # Both above everything else in the game, so the armband is between these
    # two and nobody else.
    steady = player(900, "MID", 12.0, 20.0, team_id=20, ceiling={1: 0.10, 2: 0.10, 3: 0.10})
    spiky = player(901, "MID", 12.0, 19.9, team_id=21, ceiling={1: 0.55, 2: 0.55, 3: 0.55})
    proj[900], proj[901] = steady, spiky
    squad = wildcard.draft(proj, [1, 2, 3], 100.0, CFG,
                           keep=[900, 901], tc_gw=2)["weeks"]
    normal = next(w for w in squad if w["gw"] == 1)
    triple = next(w for w in squad if w["gw"] == 2)
    assert normal["captain"] == 900, "no chip, no tilt — the armband is on points"
    assert triple["captain"] == 901, "on the chip week the haul rate decides"


def test_weekly_points_include_the_chip():
    proj = league()
    out = wildcard.draft(proj, [1, 2, 3], 100.0, CFG, bb_gw=2, tc_gw=3)
    w2 = next(w for w in out["weeks"] if w["gw"] == 2)
    w3 = next(w for w in out["weeks"] if w["gw"] == 3)
    xi2 = sum(proj[i]["ep"][2] for i in w2["xi"])
    bench2 = sum(proj[i]["ep"][2] for i in w2["bench"])
    assert w2["ep"] == round(xi2 + proj[w2["captain"]]["ep"][2] + bench2, 1)
    xi3 = sum(proj[i]["ep"][3] for i in w3["xi"])
    assert w3["ep"] == round(xi3 + 2 * proj[w3["captain"]]["ep"][3], 1)
    assert w2["chip"] == "Bench Boost" and w3["chip"] == "Triple Captain"


def test_the_eleven_is_a_legal_formation_every_week():
    proj = league()
    out = wildcard.draft(proj, [1, 2, 3], 100.0, CFG)
    for w in out["weeks"]:
        assert len(w["xi"]) == 11 and len(w["bench"]) == 4
        counts = {}
        for pid in w["xi"]:
            counts[proj[pid]["pos"]] = counts.get(proj[pid]["pos"], 0) + 1
        assert counts["GKP"] == 1
        for pos in ("DEF", "MID", "FWD"):
            assert wildcard.XI_MIN[pos] <= counts.get(pos, 0) <= wildcard.XI_MAX[pos]
        assert w["captain"] in w["xi"]
        # The reserve keeper cannot come on for an outfielder, so he is last.
        assert proj[w["bench"][-1]]["pos"] == "GKP"


def test_horizon_actually_changes_the_squad():
    """A player who is useless now and excellent later has to be bought on the
    long horizon and ignored on the short one. If not, the extra weeks are
    decoration."""
    gws = [1, 2, 3, 4, 5, 6]
    proj = league(gws=gws)
    late = player(950, "FWD", 7.0, {1: 0.1, 2: 0.1, 3: 0.1, 4: 14.0, 5: 14.0, 6: 14.0},
                  team_id=30, gws=gws)
    proj[950] = late
    short = wildcard.draft(proj, [1, 2, 3], 100.0, CFG)
    long = wildcard.draft(proj, gws, 100.0, CFG)
    assert 950 not in short["squad"]
    assert 950 in long["squad"]


def test_swaps_price_every_slot_against_its_nearest_alternative():
    proj = league()
    out = wildcard.draft(proj, [1, 2, 3], 100.0, CFG)
    rows = wildcard.swaps(out["squad"], proj, [1, 2, 3], 100.0, CFG)
    assert len(rows) == 15
    for r in rows:
        assert r["out"] in out["squad"]
        if r["in"] is not None:
            assert r["in"] not in out["squad"]
            assert proj[r["in"]]["pos"] == proj[r["out"]]["pos"]
            # The draft was optimal, so no single swap can improve on it.
            assert r["gap"] >= -1e-6
    # Sorted with the most replaceable player first — that is the row you read.
    gaps = [r["gap"] for r in rows if r["gap"] is not None]
    assert gaps == sorted(gaps)


def test_swaps_respect_the_budget_and_the_club_limit():
    proj = league()
    out = wildcard.draft(proj, [1, 2, 3], 100.0, CFG)
    rows = wildcard.swaps(out["squad"], proj, [1, 2, 3], 100.0, CFG)
    cost = sum(proj[i]["price"] for i in out["squad"])
    for r in rows:
        if r["in"] is None:
            continue
        after = cost - proj[r["out"]]["price"] + proj[r["in"]]["price"]
        assert after <= 100.0 + 1e-9
        clubs = {}
        for pid in out["squad"]:
            if pid == r["out"]:
                continue
            clubs[proj[pid]["team_id"]] = clubs.get(proj[pid]["team_id"], 0) + 1
        assert clubs.get(proj[r["in"]]["team_id"], 0) < wildcard.MAX_PER_CLUB


def test_summarise_splits_the_rebuild():
    proj = league()
    out = wildcard.draft(proj, [1, 2, 3], 100.0, CFG)
    keep_one = out["squad"][0]
    old = [keep_one, 4, 5, 6]
    s = wildcard.summarise(out, proj, old)
    assert keep_one in s["keep"]
    assert set(s["sell"]) == {4, 5, 6} - set(out["squad"])
    assert set(s["buy"]) == set(out["squad"]) - {keep_one}
    assert not (set(s["keep"]) & set(s["sell"]))


def test_evaluate_is_the_number_the_draft_reports():
    proj = league()
    out = wildcard.draft(proj, [1, 2, 3], 100.0, CFG)
    again = wildcard.evaluate(out["squad"], proj, [1, 2, 3], CFG)
    assert out["score"] == round(again, 2)
