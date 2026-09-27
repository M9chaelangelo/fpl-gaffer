"""The category leaderboards.

These are orderings, so the tests are about what wins and why — a board that
silently ranks on the wrong key still looks like a leaderboard.
"""
import math

from gaffer import leaders


def card(pid, name, **kw):
    base = {
        "id": pid, "name": name, "team": "ARS", "pos": "MID", "price": 6.0,
        "ep_next": 5.0, "ep_horizon": 25.0, "ceiling": 0.10,
        "own_overall": 0.10, "exp_minutes": 90, "xg90": 0.3, "xa90": 0.2,
        "defcon_prob": 0.3, "defcon90": 6.0, "net_transfers": 0,
        "price_direction": "hold", "fixtures": ["BOU(H)", "LIV(A)"],
    }
    base.update(kw)
    return base


# --- captains ---------------------------------------------------------------

def test_captain_return_is_the_doubled_number():
    rows = leaders.captains([card(1, "A", ep_next=6.4)], gw=5)
    assert rows[0]["projected"] == 6.4
    assert rows[0]["captain_return"] == 12.8


def test_the_tail_breaks_a_tie_between_captains():
    """Two captains a tenth apart are not the same bet if one hauls twice as
    often. The mean alone cannot say so."""
    steady = card(1, "Steady", ep_next=6.4, ceiling=0.10)
    spiky = card(2, "Spiky", ep_next=6.3, ceiling=0.45)
    rows = leaders.captains([steady, spiky], gw=5)
    assert rows[0]["name"] == "Spiky"
    # But not at any price: a big enough gap on the mean still wins.
    clear = card(3, "Clear", ep_next=8.0, ceiling=0.05)
    rows = leaders.captains([steady, spiky, clear], gw=5)
    assert rows[0]["name"] == "Clear"


# --- differentials ----------------------------------------------------------

def test_leverage_is_points_times_the_field_that_does_not_own_him():
    rows = leaders.differentials([card(1, "A", ep_next=6.0, own_overall=0.05)])
    assert rows[0]["leverage"] == round(6.0 * 0.95, 2)


def test_the_template_is_gated_out_not_merely_ranked_down():
    """A 9.0 owned by half the game still out-leverages a 5.0 owned by nobody,
    so without the gate the differential board is the projection board."""
    template = card(1, "Template", ep_next=9.0, own_overall=0.55)
    punt = card(2, "Punt", ep_next=5.0, own_overall=0.02)
    rows = leaders.differentials([template, punt])
    assert [r["name"] for r in rows] == ["Punt"]


def test_differentials_ignore_players_who_are_not_worth_owning():
    cheap = card(1, "Cheap", ep_next=1.2, own_overall=0.001)
    good = card(2, "Good", ep_next=5.5, own_overall=0.03)
    rows = leaders.differentials([cheap, good])
    assert [r["name"] for r in rows] == ["Good"]


def test_differentials_can_rank_against_your_league_instead():
    """Leverage against the pack above you is a different question from
    leverage against the world, and the board takes either."""
    a = card(1, "A", ep_next=6.0, own_overall=0.02)
    b = card(2, "B", ep_next=6.0, own_overall=0.02)
    a["own_pack"], b["own_pack"] = 0.80, 0.00
    rows = leaders.differentials([a, b], own_key="own_pack")
    assert [r["name"] for r in rows] == ["B"]


# --- rates into a single match ---------------------------------------------

def test_a_per_90_rate_is_scaled_by_minutes_actually_expected():
    """A 0.6 xG per 90 striker who plays an hour is not a 0.6 xG striker."""
    full = card(1, "Full", xg90=0.6, exp_minutes=90)
    sub = card(2, "Sub", xg90=0.6, exp_minutes=45)
    rows = leaders.scorers([full, sub])
    assert rows[0]["xg"] == 0.6
    assert rows[1]["xg"] == 0.3


def test_creators_rank_on_assists_not_goals():
    passer = card(1, "Passer", xg90=0.0, xa90=0.5)
    poacher = card(2, "Poacher", xg90=0.9, xa90=0.05)
    assert leaders.creators([passer, poacher])[0]["name"] == "Passer"
    assert leaders.scorers([passer, poacher])[0]["name"] == "Poacher"


def test_defcon_ranks_on_the_probability_not_the_rate():
    """A high action rate that never crosses the threshold is trivia. The two
    points only arrive when it lands."""
    busy = card(1, "Busy", defcon90=11.0, defcon_prob=0.20)
    reliable = card(2, "Reliable", defcon90=7.5, defcon_prob=0.62)
    rows = leaders.defcon([busy, reliable])
    assert rows[0]["name"] == "Reliable"
    assert rows[0]["expected"] == round(0.62 * 2, 3)


# --- movers -----------------------------------------------------------------

def test_movers_rank_on_size_not_direction():
    """A player haemorrhaging owners matters as much as one being bought —
    more, if you hold him."""
    rising = card(1, "Rising", net_transfers=40000, price_direction="rise")
    falling = card(2, "Falling", net_transfers=-90000, price_direction="fall")
    held = card(3, "Held", net_transfers=500, price_direction="hold")
    rows = leaders.movers([rising, falling, held])
    assert [r["name"] for r in rows] == ["Falling", "Rising"]


# --- the haul distribution --------------------------------------------------

def test_haul_distribution_is_a_real_distribution():
    cards = [card(i, f"P{i}", ceiling=0.2) for i in range(1, 12)]
    d = leaders.haul_distribution(cards, [c["id"] for c in cards])
    assert d["n"] == 11
    # The pmf is rounded to five places on the way out — it is downloaded on a
    # phone — so twelve entries can drift a few parts in a million from one.
    assert abs(sum(d["pmf"]) - 1.0) < 1e-4
    # Eleven independent coins at 0.2 each.
    assert abs(d["expected"] - 11 * 0.2) < 0.01
    assert abs(d["sd"] - math.sqrt(11 * 0.2 * 0.8)) < 0.01


def test_haul_distribution_matches_the_binomial_it_reduces_to():
    """With equal probabilities the Poisson-binomial IS the binomial, which is
    a free check on the convolution."""
    n, p = 6, 0.3
    cards = [card(i, f"P{i}", ceiling=p) for i in range(1, n + 1)]
    d = leaders.haul_distribution(cards, [c["id"] for c in cards])
    for k in range(n + 1):
        want = math.comb(n, k) * p ** k * (1 - p) ** (n - k)
        assert abs(d["pmf"][k] - want) < 1e-5, k      # 5dp on the wire


def test_haul_distribution_handles_unequal_probabilities():
    cards = [card(1, "A", ceiling=0.5), card(2, "B", ceiling=0.1)]
    d = leaders.haul_distribution(cards, [1, 2])
    assert abs(d["pmf"][0] - 0.5 * 0.9) < 1e-9
    assert abs(d["pmf"][1] - (0.5 * 0.9 + 0.5 * 0.1)) < 1e-9
    assert abs(d["pmf"][2] - 0.5 * 0.1) < 1e-9
    assert abs(d["at_least_one"] - (1 - 0.45)) < 1e-9
    assert abs(d["at_least_two"] - 0.05) < 1e-9


def test_haul_distribution_skips_players_with_no_ceiling():
    cards = [card(1, "A", ceiling=0.3), card(2, "B", ceiling=None)]
    d = leaders.haul_distribution(cards, [1, 2])
    assert d["n"] == 1


def test_no_ceilings_at_all_means_no_distribution():
    cards = [card(1, "A", ceiling=None)]
    assert leaders.haul_distribution(cards, [1]) is None


# --- the whole set ----------------------------------------------------------

def test_build_returns_every_board():
    cards = [card(i, f"P{i}", ep_next=3.0 + i * 0.4,
                  own_overall=0.02 * i, ceiling=0.05 * i)
             for i in range(1, 12)]
    out = leaders.build(cards, gw=5, xi_ids=[c["id"] for c in cards],
                        captain_id=11, clean_sheets=[{"team": "ARS"}])
    for key in ("projected", "captains", "differentials", "goals", "assists",
                "defcon", "movers", "clean_sheets", "hauls"):
        assert key in out, key
    assert out["hauls"]["captain"] == 11
    assert out["clean_sheets"] == [{"team": "ARS"}]
    # Every board carries the number it was ranked on, so the sort is readable
    # rather than something you have to trust.
    assert "projected" in out["projected"][0]
    assert "leverage" in out["differentials"][0]
    assert "captain_return" in out["captains"][0]
    assert "xg" in out["goals"][0]
    assert "expected" in out["defcon"][0]


def test_build_survives_missing_fields():
    """Cards come from the export, and a metric the model could not compute is
    None rather than absent. A board that throws on that takes the page with
    it."""
    thin = [{"id": 1, "name": "Thin", "team": "ARS", "pos": "MID",
             "price": 5.0, "ep_next": None, "ceiling": None,
             "own_overall": None, "exp_minutes": None, "xg90": None,
             "xa90": None, "defcon_prob": None, "net_transfers": None,
             "price_direction": None, "fixtures": None}]
    out = leaders.build(thin, gw=5, xi_ids=[1])
    assert out["captains"] == [] and out["goals"] == []
    assert out["hauls"] is None
