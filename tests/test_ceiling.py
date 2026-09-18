"""Tests for the ceiling model wiring.

The model was trained, scored and committed months ago and then loaded by
nothing. These tests exist so that cannot happen again quietly: they assert the
model is reachable, that its prediction survives into the projection, and that
it reaches the two places that consume it — the Triple Captain armband and the
page.
"""
import json

import pytest

from gaffer import explain, learn, projections, webdata


# --- the model itself ---------------------------------------------------


def test_the_trained_ceiling_model_is_committed_and_loadable():
    """If this fails the repo is shipping a model nobody can use."""
    bundle = learn.load("ceiling")
    assert bundle is not None, "models/ceiling.joblib missing"
    assert "model" in bundle and "features" in bundle


def test_its_features_match_what_training_declared():
    bundle = learn.load("ceiling")
    assert list(bundle["features"]) == list(learn.CEILING_X)


def test_it_scored_well_enough_to_be_worth_trusting():
    scores = json.load(open("models/scores.json", encoding="utf-8"))
    assert scores["ceiling"]["metric"] == "AUC"
    # Below chance-plus-a-bit it should not be steering an armband.
    assert scores["ceiling"]["value"] > 0.70


# --- the prediction pass ------------------------------------------------


def _boot(n=6):
    """Players 1..n, odd ids on team 1 and even on team 2.

    Spelled out rather than computed: an expression like `1 + (i % 2)` reads as
    "alternating" and actually puts player 1 on team 2, which is exactly the
    kind of thing a test fixture should not make you work out.
    """
    els = []
    for i in range(1, n + 1):
        els.append({
            "id": i, "web_name": f"P{i}", "team": 1 if i % 2 else 2,
            "element_type": 3, "now_cost": 50 + i,
            "minutes": 400, "starts": 4, "total_points": 20 + i,
            "bps": 100 + i, "threat": str(50 + i), "ict_index": str(40 + i),
            "expected_goal_involvements": str(1.0 + i / 10),
            "status": "a", "news": "", "selected_by_percent": "5.0",
        })
    return {"elements": els,
            "teams": [{"id": 1, "short_name": "ARS"}, {"id": 2, "short_name": "LIV"}],
            "element_types": [{"id": 3, "singular_name_short": "MID"}]}


def _fx(gws):
    # Team 1 home, team 2 away, every gameweek.
    return {1: {g: [(2, True, 2)] for g in gws},
            2: {g: [(2, False, 1)] for g in gws}}


def test_it_predicts_a_probability_for_every_player_and_gameweek():
    gws = [5, 6]
    boot = _boot()
    lams = {1: {g: 1.2 for g in gws}, 2: {g: 1.6 for g in gws}}
    out = projections._ceiling_model(boot, 4, _fx(gws), lams, gws)
    assert out is not None, "model present but produced nothing"
    for e in boot["elements"]:
        for g in gws:
            p = out[e["id"]][g]
            assert 0.0 <= p <= 1.0


def test_a_double_gameweek_combines_the_two_chances():
    """Two fixtures in one week is P(haul in either), not the last one seen."""
    gws = [5]
    boot = _boot(2)
    fx = {1: {5: [(2, True, 2), (3, False, 2)]}, 2: {5: [(2, False, 1)]}}
    lams = {1: {5: 1.2}, 2: {5: 1.4}}
    double = projections._ceiling_model(boot, 4, fx, lams, gws)

    single = projections._ceiling_model(
        boot, 4, {1: {5: [(2, True, 2)]}, 2: {5: [(2, False, 1)]}}, lams, gws)

    # Player 1 is on team 1 and plays twice; his haul chance must rise.
    assert double[1][5] > single[1][5]
    assert double[1][5] <= 1.0


def test_a_player_with_no_fixture_gets_no_entry():
    gws = [5]
    boot = _boot(2)
    fx = {1: {5: [(2, True, 2)]}, 2: {5: []}}      # team 2 blanks
    lams = {1: {5: 1.2}, 2: {5: 1.4}}
    out = projections._ceiling_model(boot, 4, fx, lams, gws)
    blank = [e["id"] for e in boot["elements"] if e["team"] == 2]
    for pid in blank:
        assert 5 not in out.get(pid, {})


def test_missing_model_degrades_instead_of_failing(monkeypatch):
    """An untrained repo must still solve, just without the tilt."""
    monkeypatch.setattr(learn, "load", lambda name: None)
    out = projections._ceiling_model(_boot(), 4, _fx([5]), {1: {5: 1.0}, 2: {5: 1.0}}, [5])
    assert out is None


# --- what consumes it ---------------------------------------------------


def test_the_player_card_carries_the_ceiling():
    proj = {1: {"name": "X", "team": "ARS", "pos": "MID", "price": 7.0,
                "ep": {5: 6.0}, "opp": {5: "BOU(H)"}, "p60": 0.9, "exp_min": 85,
                "ceiling_next": 0.23, "own": 10.0, "status": "a", "news": "",
                "defcon_prob": 0.2, "cs_prob": 0.3, "setpiece_bonus": 0.1}}
    card = explain.player_card(1, proj, {}, {}, {}, {}, {}, [5])
    assert card["ceiling"] == 0.23


def test_the_compare_view_plots_it():
    keys = [m["key"] for m in webdata.METRICS]
    assert "ceiling" in keys, "ceiling is exported but never charted"
    assert "ceiling" in webdata.CARD_FIELDS


def test_the_captain_rationale_states_the_tail():
    proj = {
        1: {"id": 1, "name": "Haaland", "ep": {5: 9.0}, "opp": {5: "SUN(H)"},
            "ceiling": {5: 0.31}},
        2: {"id": 2, "name": "Spiky", "ep": {5: 6.2}, "opp": {5: "BOU(A)"},
            "ceiling": {5: 0.44}},
    }
    week = {"gw": 5, "captain": dict(proj[1]),
            "xi": [{"id": 1}, {"id": 2}]}
    out = explain.captain(week, proj, {}, {}, {}, [5])
    text = " ".join(out["reasons"])
    assert "31%" in text
    # And it names the bigger tail rather than hiding it.
    assert "Spiky" in text and "44%" in text


# --- end to end through build() -----------------------------------------


def _element(i, team, pos_id=3):
    """A bootstrap element with every field build() reads."""
    return {
        "id": i, "web_name": f"P{i}", "team": team, "element_type": pos_id,
        "now_cost": 55 + i, "minutes": 400, "starts": 4,
        "total_points": 24 + i, "bps": 120 + i,
        "threat": str(45 + i), "ict_index": str(38 + i),
        "creativity": "30.0", "influence": "40.0", "form": "4.0",
        "expected_goals": "1.2", "expected_assists": "0.8",
        "expected_goal_involvements": "2.0",
        "expected_goals_per_90": "0.30", "expected_assists_per_90": "0.20",
        "expected_goal_involvements_per_90": "0.50",
        "expected_goals_conceded_per_90": "1.10",
        "defensive_contribution_per_90": "4.0",
        "saves_per_90": "0.0", "clean_sheets": 1, "goals_conceded": 4,
        "clearances_blocks_interceptions": 12, "tackles": 6, "recoveries": 20,
        "saves": 0, "defensive_contribution": 18,
        "status": "a", "news": "", "selected_by_percent": "8.0",
        "chance_of_playing_next_round": None,
        "penalties_order": None, "corners_and_indirect_freekicks_order": None,
        "direct_freekicks_order": None,
    }


def _full_boot():
    return {
        "elements": [_element(i, 1 if i % 2 else 2) for i in range(1, 9)],
        "teams": [{"id": 1, "short_name": "ARS"}, {"id": 2, "short_name": "LIV"}],
        "element_types": [
            {"id": 1, "singular_name_short": "GKP"},
            {"id": 2, "singular_name_short": "DEF"},
            {"id": 3, "singular_name_short": "MID"},
            {"id": 4, "singular_name_short": "FWD"},
        ],
    }


def test_build_puts_the_ceiling_on_every_player(monkeypatch):
    """The wiring test. _ceiling_model working in isolation proves nothing if
    build() computes it before `lams` exists or drops it from the record."""
    gws = [5, 6]
    boot = _full_boot()
    fixtures = [
        {"event": g, "team_h": 1, "team_a": 2,
         "team_h_difficulty": 3, "team_a_difficulty": 2}
        for g in gws
    ]
    # defence.lambdas reaches for Solio and match odds; the ceiling wiring is
    # what is under test, so the expected-goals table is stubbed.
    monkeypatch.setattr(
        projections.defence, "lambdas",
        lambda *a, **k: ({1: {g: 1.25 for g in gws}, 2: {g: 1.60 for g in gws}}, {}),
    )

    out = projections.build(boot, fixtures, gws)

    assert out, "build produced no players"
    for pid, p in out.items():
        assert "ceiling" in p, f"player {pid} has no ceiling"
        assert "ceiling_next" in p
        for g in gws:
            assert 0.0 <= p["ceiling"][g] <= 1.0
        assert p["ceiling_next"] == p["ceiling"][gws[0]]


def test_build_survives_without_a_trained_ceiling(monkeypatch):
    """An untrained repo still solves; the field is simply empty."""
    gws = [5]
    boot = _full_boot()
    fixtures = [{"event": 5, "team_h": 1, "team_a": 2,
                 "team_h_difficulty": 3, "team_a_difficulty": 2}]
    monkeypatch.setattr(
        projections.defence, "lambdas",
        lambda *a, **k: ({1: {5: 1.25}, 2: {5: 1.60}}, {}))
    real_load = learn.load          # bind before patching, or the lambda recurses
    monkeypatch.setattr(projections.learn, "load",
                        lambda name: None if name == "ceiling" else real_load(name))

    out = projections.build(boot, fixtures, gws)
    for p in out.values():
        assert p["ceiling"] == {}
        assert p["ceiling_next"] is None
