"""Reading a squad for what is wrong with it.

Each of these is a diagnosis someone will act on, so the tests are about the
constraints that make a row actionable — same position, affordable, not
already owned — rather than about the arithmetic.
"""
from gaffer import analysis


def card(pid, **kw):
    base = {
        "id": pid, "name": f"P{pid}", "team": "ARS", "pos": "MID", "price": 6.0,
        "ep_next": 5.0, "start_prob": 0.95, "exp_minutes": 85, "xg90": 0.3,
        "xa90": 0.2, "cs_prob": 0.25, "defcon_prob": 0.2, "own_overall": 0.10,
        "status": "a",
    }
    base.update(kw)
    return base


# --- weak spots -------------------------------------------------------------

def test_a_weak_spot_needs_a_cheaper_or_similar_alternative():
    """A row you cannot afford is not a weak spot, it is a daydream."""
    mine = card(1, ep_next=3.5, price=5.0)
    dear = card(2, ep_next=9.0, price=12.0)
    rows = analysis.weak_spots([mine, dear], [1], bank=0.0)
    assert rows == []
    # With the money in the bank it becomes a real move.
    rows = analysis.weak_spots([mine, dear], [1], bank=7.0)
    assert rows[0]["in"] == 2 and rows[0]["gain"] == 5.5


def test_a_weak_spot_must_be_the_same_position():
    mine = card(1, pos="DEF", ep_next=3.0)
    better = card(2, pos="MID", ep_next=8.0, price=6.0)
    assert analysis.weak_spots([mine, better], [1], bank=5.0) == []


def test_players_you_already_own_are_not_alternatives():
    mine = card(1, ep_next=3.0)
    also_mine = card(2, ep_next=8.0)
    rows = analysis.weak_spots([mine, also_mine], [1, 2], squad_ids=[1, 2])
    assert rows == []


def test_flagged_players_are_not_offered_as_upgrades():
    mine = card(1, ep_next=3.0)
    crocked = card(2, ep_next=9.0, status="i")
    assert analysis.weak_spots([mine, crocked], [1]) == []


def test_weak_spots_rank_on_the_gap():
    a = card(1, ep_next=3.0)
    b = card(2, ep_next=4.0)
    up_a = card(3, ep_next=7.0, price=6.0)
    up_b = card(4, ep_next=5.0, price=6.0)
    rows = analysis.weak_spots([a, b, up_a, up_b], [1, 2])
    assert [r["out"] for r in rows] == [1, 2]
    assert rows[0]["gain"] > rows[1]["gain"]


def test_a_starter_nobody_beats_is_not_listed():
    best = card(1, ep_next=9.0)
    rest = [card(i, ep_next=4.0) for i in range(2, 6)]
    assert analysis.weak_spots([best] + rest, [1]) == []


# --- autosubs ---------------------------------------------------------------

def test_the_chance_of_any_autosub_rises_with_the_squad():
    one = analysis.autosub_risk([card(1, start_prob=0.9)], [1], [])
    many = analysis.autosub_risk([card(i, start_prob=0.9) for i in range(1, 12)],
                                 list(range(1, 12)), [])
    assert one["any_autosub"] < many["any_autosub"]
    # Eleven independent players at 10% each, to the four places it reports.
    assert abs(many["any_autosub"] - (1 - 0.9 ** 11)) < 1e-4


def test_a_reliable_eleven_costs_nothing():
    cards = [card(i, start_prob=1.0) for i in range(1, 12)]
    out = analysis.autosub_risk(cards, list(range(1, 12)), [])
    assert out["any_autosub"] == 0.0
    assert out["expected_points_lost"] == 0.0
    assert out["riskiest"] == []


def test_a_good_bench_reduces_the_damage_not_the_risk():
    """This is the distinction the number exists to make: cover does not stop
    a player being unavailable, it stops it costing you."""
    starters = [card(i, start_prob=0.8, ep_next=5.0) for i in range(1, 12)]
    thin = [card(20 + i, ep_next=0.5) for i in range(4)]
    deep = [card(30 + i, ep_next=4.8) for i in range(4)]
    a = analysis.autosub_risk(starters + thin, list(range(1, 12)),
                              [c["id"] for c in thin])
    b = analysis.autosub_risk(starters + deep, list(range(1, 12)),
                              [c["id"] for c in deep])
    assert a["any_autosub"] == b["any_autosub"]
    assert b["expected_points_lost"] < a["expected_points_lost"]


def test_the_riskiest_starters_are_named_worst_first():
    cards = [card(1, start_prob=0.5), card(2, start_prob=0.75),
             card(3, start_prob=1.0)]
    out = analysis.autosub_risk(cards, [1, 2, 3], [])
    assert [r["id"] for r in out["riskiest"]] == [1, 2]


# --- exposure ---------------------------------------------------------------

def test_exposure_compares_you_against_the_field():
    mine = card(1, team="LIV", own_overall=0.30)
    theirs = card(2, team="LIV", own_overall=0.60)
    rows = {r["team"]: r for r in analysis.exposure([mine, theirs], [1])}
    assert rows["LIV"]["you"] == 1.0
    assert rows["LIV"]["field"] == 0.9
    assert rows["LIV"]["diff"] == 0.1


def test_the_captain_counts_double():
    a = card(1, team="LIV", own_overall=0.0)
    plain = {r["team"]: r for r in analysis.exposure([a], [1])}
    capped = {r["team"]: r for r in analysis.exposure([a], [1], captain_id=1)}
    assert capped["LIV"]["you"] == 2 * plain["LIV"]["you"]


def test_a_club_you_do_not_own_still_swings_you():
    """Being absent from a popular club is exposure, in the other direction —
    and a model that only looked at what you hold would miss it entirely."""
    mine = card(1, team="ARS", own_overall=0.05)
    popular = card(2, team="MCI", own_overall=0.70)
    rows = {r["team"]: r for r in analysis.exposure([mine, popular], [1])}
    assert rows["MCI"]["you"] == 0.0
    assert rows["MCI"]["diff"] < 0
    assert rows["MCI"]["swing"] > 0


def test_shares_sum_to_one():
    cards = [card(i, team=t, own_overall=0.1 * i)
             for i, t in enumerate(["ARS", "LIV", "MCI", "CHE"], start=1)]
    rows = analysis.exposure(cards, [1, 2])
    assert abs(sum(r["share"] for r in rows) - 1.0) < 1e-3


# --- template ---------------------------------------------------------------

def test_template_share_counts_the_widely_owned():
    cards = [card(1, own_overall=0.55), card(2, own_overall=0.40),
             card(3, own_overall=0.02), card(4, own_overall=0.01)]
    out = analysis.template(cards, [1, 2, 3, 4])
    assert out["share"] == 0.5
    assert abs(out["mean_ownership"] - 0.245) < 1e-9


def test_template_is_none_without_ownership():
    cards = [card(1, own_overall=None)]
    assert analysis.template(cards, [1]) is None


# --- the whole diagnosis ----------------------------------------------------

def test_build_returns_every_section():
    cards = [card(i) for i in range(1, 16)]
    out = analysis.build(cards, list(range(1, 12)),
                         bench_ids=list(range(12, 16)), captain_id=1,
                         squad_ids=list(range(1, 16)))
    for key in ("weak_spots", "autosubs", "exposure", "template"):
        assert key in out, key
    assert out["autosubs"]["any_autosub"] >= 0


# --- fixture matrix ---------------------------------------------------------

def _strengths():
    """Nine clubs, cleanly ordered, so the thirds land three apiece."""
    return {f"T{i}": {"overall": 2.0 - i * 0.2} for i in range(1, 10)}


def test_tiers_are_cut_by_rank_not_by_a_fixed_threshold():
    """Strong means strong for this division. A hard cut-off would drift as
    the league's overall level moved."""
    tiers = analysis.tier_teams(_strengths())
    assert tiers["T1"] == "Strong" and tiers["T9"] == "Weak"
    counts = {}
    for t in tiers.values():
        counts[t] = counts.get(t, 0) + 1
    assert counts == {"Strong": 3, "Medium": 3, "Weak": 3}


def test_the_matrix_totals_the_projected_points():
    cards = [card(i, team=f"T{i}", ep_next=4.0, fixtures=[f"T{10-i}(H)"])
             for i in range(1, 10)]
    m = analysis.fixture_matrix(cards, [c["id"] for c in cards], _strengths())
    assert abs(m["total"] - 36.0) < 1e-6
    assert abs(sum(m["row_totals"].values()) - m["total"]) < 1e-6
    assert abs(sum(m["col_totals"].values()) - m["total"]) < 1e-6


def test_favourable_means_a_mismatch_in_your_favour():
    """Strong against weak is favourable. Strong against strong is even, and
    counting it as favourable would make every good team look well-fixtured."""
    strong_v_weak = [card(1, team="T1", ep_next=5.0, fixtures=["T9(H)"])]
    m = analysis.fixture_matrix(strong_v_weak, [1], _strengths())
    assert m["favourable"] == 1.0

    strong_v_strong = [card(1, team="T1", ep_next=5.0, fixtures=["T2(H)"])]
    m = analysis.fixture_matrix(strong_v_strong, [1], _strengths())
    assert m["favourable"] == 0.0

    weak_v_strong = [card(1, team="T9", ep_next=5.0, fixtures=["T1(A)"])]
    m = analysis.fixture_matrix(weak_v_strong, [1], _strengths())
    assert m["favourable"] == 0.0


def test_the_captain_counts_twice_in_the_matrix():
    cards = [card(1, team="T1", ep_next=5.0, fixtures=["T9(H)"])]
    plain = analysis.fixture_matrix(cards, [1], _strengths())
    capped = analysis.fixture_matrix(cards, [1], _strengths(), captain_id=1)
    assert capped["total"] == 2 * plain["total"]
    assert capped["grid"]["Strong"]["Weak"]["count"] == 2


def test_an_unknown_opponent_is_counted_as_unplaced_not_dropped_silently():
    cards = [card(1, team="T1", ep_next=5.0, fixtures=["ZZZ(H)"])]
    m = analysis.fixture_matrix(cards, [1], _strengths())
    assert m["unplaced"] == 1
    assert m["total"] == 0.0
