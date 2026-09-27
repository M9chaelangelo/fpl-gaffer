"""The points distribution.

A distribution is easy to get subtly wrong and hard to eyeball, so these check
the things that would make the curve a lie: that it is a probability
distribution at all, that its mean is the one the rest of the app quotes, and
that the armband doubles a player rather than cloning him.
"""
import math

from gaffer import distribution as dist


def card(pid=1, **kw):
    base = {
        "id": pid, "name": f"P{pid}", "pos": "MID", "ep_next": 5.0,
        "start_prob": 0.9, "exp_minutes": 85, "xg90": 0.3, "xa90": 0.2,
        "cs_prob": 0.25, "defcon_prob": 0.2,
    }
    base.update(kw)
    return base


# --- it is a distribution ---------------------------------------------------

def test_a_player_pmf_sums_to_one():
    pmf = dist.player_points(card())
    assert abs(sum(pmf) - 1.0) < 1e-9
    assert all(p >= 0 for p in pmf)


def test_the_mean_is_the_projection_every_other_view_quotes():
    """The components do not cover bonus, saves or the concession penalty. The
    gap is added back, so the curve cannot disagree with the number on the
    player's card."""
    for ep in (2.0, 4.5, 7.0, 11.0, 14.0):
        pmf = dist.player_points(card(ep_next=ep))
        # Exact, not rounded. Rounding to the nearest whole point loses up to
        # half a point per player, and eleven of those is four points on the
        # squad total — which is the whole reason the correction is split
        # across two points rather than shifted by one.
        assert abs(dist.mean(pmf) - ep) < 0.01, ep


def test_a_player_with_no_minutes_has_no_distribution():
    assert dist.player_points(card(exp_minutes=0)) is None
    assert dist.player_points(card(start_prob=None)) is None
    assert dist.player_points(card(ep_next=None)) is None


def test_not_starting_puts_mass_at_zero():
    risky = dist.player_points(card(start_prob=0.4, ep_next=3.0))
    safe = dist.player_points(card(start_prob=0.99, ep_next=3.0))
    assert risky[0] > safe[0], "a rotation risk must carry more chance of nothing"


# --- position rules ---------------------------------------------------------

def test_a_defender_gets_more_for_a_clean_sheet_than_a_midfielder():
    d = dist.player_points(card(pos="DEF", cs_prob=0.9, ep_next=5.0))
    m = dist.player_points(card(pos="MID", cs_prob=0.9, ep_next=5.0))
    # Same mean by construction, but the defender's clean sheet is a four-point
    # lump and the midfielder's is one — so the defender's week is spikier.
    assert dist.sd(d) > dist.sd(m)


def test_a_forward_gets_nothing_for_a_clean_sheet():
    with_cs = dist.player_points(card(pos="FWD", cs_prob=0.9))
    without = dist.player_points(card(pos="FWD", cs_prob=0.0))
    assert with_cs == without


def test_goals_are_worth_more_to_a_defender():
    """Six a goal against four, so the same xG makes a defender's tail longer."""
    d = dist.player_points(card(pos="DEF", xg90=0.5, cs_prob=0.0,
                                defcon_prob=0.0, ep_next=5.0))
    f = dist.player_points(card(pos="FWD", xg90=0.5, cs_prob=0.0,
                                defcon_prob=0.0, ep_next=5.0))
    assert dist.sd(d) > dist.sd(f)


# --- the squad --------------------------------------------------------------

def _eleven(**kw):
    return [card(i, **kw) for i in range(1, 12)]


def test_squad_distribution_sums_to_one_and_centres_on_the_sum_of_means():
    cards = _eleven()
    out = dist.squad_points(cards, [c["id"] for c in cards])
    assert abs(sum(out["pmf"]) - 1.0) < 1e-4
    assert out["n"] == 11
    # Eleven players at five points each, nobody captained.
    assert abs(out["mean"] - 55) < 0.1


def test_the_captain_is_doubled_not_cloned():
    """Adding an independent second copy of him would give the same mean and
    the wrong variance — which is exactly the mistake that makes a captaincy
    look safer than it is."""
    cards = _eleven()
    ids = [c["id"] for c in cards]
    plain = dist.squad_points(cards, ids)
    capped = dist.squad_points(cards, ids, captain_id=1)
    assert capped["mean"] > plain["mean"]

    one = dist.player_points(cards[0])
    solo_sd = dist.sd(one)
    # Var(2X) = 4Var(X): doubling adds three times his variance, cloning would
    # add only one.
    gained = capped["sd"] ** 2 - plain["sd"] ** 2
    assert abs(gained - 3 * solo_sd ** 2) < 0.5


def test_thresholds_are_upper_tails_and_decrease():
    cards = _eleven()
    out = dist.squad_points(cards, [c["id"] for c in cards])
    t = out["thresholds"]
    assert 0.0 <= t["80"] <= t["60"] <= t["40"] <= 1.0
    # Fifty-five expected: beating forty should be likely, eighty should not.
    assert t["40"] > 0.7
    assert t["80"] < 0.2


def test_bench_boost_counts_the_bench():
    cards = [card(i) for i in range(1, 16)]
    xi = [c["id"] for c in cards[:11]]
    bench = [c["id"] for c in cards[11:]]
    plain = dist.squad_points(cards, xi, bench_ids=bench)
    boosted = dist.squad_points(cards, xi, bench_ids=bench, chip="bb")
    assert boosted["n"] == 15 and plain["n"] == 11
    assert boosted["mean"] > plain["mean"]


def test_triple_captain_trebles_rather_than_doubles():
    cards = _eleven()
    ids = [c["id"] for c in cards]
    double = dist.squad_points(cards, ids, captain_id=1)
    treble = dist.squad_points(cards, ids, captain_id=1, chip="tc")
    one = dist.player_points(cards[0])
    assert abs((treble["mean"] - double["mean"]) - dist.mean(one)) < 0.5


def test_median_is_reported_and_sits_inside_the_support():
    cards = _eleven()
    out = dist.squad_points(cards, [c["id"] for c in cards])
    assert 0 <= out["median"] < len(out["pmf"])
    # Points are skewed right, so the median sits at or below the mean.
    assert out["median"] <= math.ceil(out["mean"])


def test_a_squad_of_unmodellable_players_returns_nothing():
    cards = [card(i, exp_minutes=0) for i in range(1, 12)]
    assert dist.squad_points(cards, [c["id"] for c in cards]) is None


def test_unknown_ids_are_skipped_not_fatal():
    cards = _eleven()
    out = dist.squad_points(cards, [c["id"] for c in cards] + [999])
    assert out["n"] == 11


# --- where the points come from ---------------------------------------------

def test_the_buckets_sum_to_the_projection():
    """Points DNA is a decomposition, not an estimate. If the parts do not add
    up to the whole, the chart is telling a different story from the number
    printed above it."""
    for ep in (2.0, 4.0, 6.5, 9.0, 13.0):
        for pos in ("GKP", "DEF", "MID", "FWD"):
            broken = dist.player_components(card(pos=pos, ep_next=ep))
            assert abs(sum(broken["points"].values()) - ep) < 0.02, (pos, ep)


def test_a_forward_earns_nothing_from_clean_sheets():
    broken = dist.player_components(card(pos="FWD", cs_prob=0.8))
    assert broken["points"]["clean_sheets"] == 0.0


def test_appearance_is_worth_two_when_he_always_starts():
    broken = dist.player_components(card(start_prob=1.0, ep_next=8.0))
    assert abs(broken["points"]["appearance"] - 2.0) < 1e-9


def test_events_are_counts_not_points():
    """The page shows '~16.4 goals' beside the points they were worth, so the
    two columns must not be the same number in different clothes."""
    broken = dist.player_components(card(pos="DEF", ep_next=6.0, xg90=0.3))
    g_points = broken["points"]["goals"]
    g_events = broken["events"]["goals"]
    assert abs(g_points - g_events * dist.GOAL["DEF"]) < 1e-9
    assert g_events < g_points, "a defender's goal is worth six"


def test_squad_dna_totals_the_squad_projection():
    cards = _eleven()
    ids = [c["id"] for c in cards]
    dna = dist.points_dna(cards, ids)
    assert dna["n"] == 11
    assert abs(dna["total"] - 55.0) < 0.2
    assert abs(sum(r["points"] for r in dna["rows"]) - dna["total"]) < 0.2
    assert abs(sum(r["share"] for r in dna["rows"]) - 1.0) < 1e-3


def test_squad_dna_counts_the_captain_at_his_multiplier():
    """A breakdown that ignored the armband would not add up to the total
    printed beside it."""
    cards = _eleven()
    ids = [c["id"] for c in cards]
    plain = dist.points_dna(cards, ids)
    capped = dist.points_dna(cards, ids, captain_id=1)
    one = dist.player_components(cards[0])
    assert abs((capped["total"] - plain["total"])
               - sum(one["points"].values())) < 0.2


def test_squad_dna_matches_the_distribution_mean():
    """Two views of the same eleven, from the same fit. They have to agree."""
    cards = _eleven()
    ids = [c["id"] for c in cards]
    dna = dist.points_dna(cards, ids, captain_id=3)
    curve = dist.squad_points(cards, ids, captain_id=3)
    assert abs(dna["total"] - curve["mean"]) < 0.3
