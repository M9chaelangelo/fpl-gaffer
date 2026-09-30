"""The bonus model, and the bar it had to clear to be used at all.

The first bonus model regressed the mean. Bonus is 0 for the overwhelming
majority of player-weeks, so predicting the base rate scored an MAE of 0.148
and looked fine. Measured properly it had learned price: sweeping BPS per match
from 0 to 60 moved its answer by 0.06 points, while sweeping price moved it by
0.35 — and BPS is the quantity FPL actually awards bonus on.

So these tests are mostly about refusing. The projection already had a crude
bonus term that tracked BPS monotonically, and anything replacing it has to be
the classifier, with the features it was trained on, or the heuristic stands.
"""
import numpy as np
import pytest

from gaffer import data, learn, leaders, projections

from tests.test_ceiling import _element, _full_boot


def _mixed_boot():
    """Every position across two clubs. The shared fixture is eight midfielders,
    and bonus is a defender's term — a test on it would pass by having nothing
    to check."""
    els = []
    for i, pos_id in enumerate([1, 2, 2, 3, 3, 4, 1, 2, 3, 4], start=1):
        els.append(_element(i, 1 if i % 2 else 2, pos_id=pos_id))
    boot = _full_boot()
    boot["elements"] = els
    return boot


class _Classifier:
    """Predicts a fixed distribution over 0/1/2/3."""

    classes_ = np.array([0, 1, 2, 3])

    def __init__(self, probs=(0.7, 0.2, 0.07, 0.03)):
        self._p = probs

    def predict_proba(self, X):
        return np.tile(np.array(self._p, dtype=float), (len(X), 1))


class _Regressor:
    """The old model: a number, no distribution. No `predict_proba`."""

    def predict(self, X):
        return np.full(len(X), 0.26)


FEATS = ["roll_bps", "roll_minutes", "roll_expected_goal_involvements",
         "roll_influence", "roll_threat", "value", "was_home",
         "pos_code", "expected_goals_conceded"]


def _fixtures(gws, n=1):
    return [{"event": g, "team_h": 1, "team_a": 2,
             "team_h_difficulty": 3, "team_a_difficulty": 3}
            for g in gws for _ in range(n)]


def _stub_lambdas(monkeypatch, gws):
    monkeypatch.setattr(
        projections.defence, "lambdas",
        lambda *a, **k: ({1: {g: 1.3 for g in gws}, 2: {g: 1.3 for g in gws}}, {}))


# --- the arithmetic -------------------------------------------------------

def test_expected_bonus_is_the_mean_of_the_distribution():
    import pandas as pd
    m = _Classifier((0.5, 0.3, 0.15, 0.05))
    got = learn.expected_bonus(m, pd.DataFrame({"a": [1.0, 2.0]}))
    assert got == pytest.approx([0.75, 0.75])          # 0+0.3+0.30+0.15


def test_a_certainty_of_three_is_three():
    import pandas as pd
    m = _Classifier((0.0, 0.0, 0.0, 1.0))
    assert learn.expected_bonus(m, pd.DataFrame({"a": [1.0]})) == pytest.approx([3.0])


# --- what it refuses ------------------------------------------------------

def test_the_old_regressor_is_refused(monkeypatch):
    """The test this file exists for. A bundle without a distribution is the
    model that learned price, and using it would make defenders worse while
    looking wired in from the outside."""
    monkeypatch.setattr(learn, "load",
                        lambda n: {"model": _Regressor(), "features": FEATS})
    gws = [5]
    boot = _full_boot()
    out = projections._bonus_model(
        boot, 5, {1: {5: [(3, True, 2)]}, 2: {5: [(3, False, 1)]}},
        {1: {5: 1.3}, 2: {5: 1.3}}, gws,
        {p["id"]: p["singular_name_short"] for p in boot["element_types"]})
    assert out is None


def test_a_missing_model_is_refused(monkeypatch):
    monkeypatch.setattr(learn, "load", lambda n: None)
    boot = _full_boot()
    assert projections._bonus_model(
        boot, 5, {1: {5: [(3, True, 2)]}, 2: {5: [(3, False, 1)]}},
        {1: {5: 1.3}, 2: {5: 1.3}}, [5],
        {p["id"]: p["singular_name_short"] for p in boot["element_types"]}) is None


def test_a_model_wanting_features_we_cannot_build_is_refused(monkeypatch):
    """A feature row half-assembled from zeros predicts confidently and wrongly.
    Better to say nothing."""
    monkeypatch.setattr(
        learn, "load",
        lambda n: {"model": _Classifier(), "features": FEATS + ["moon_phase"]})
    boot = _full_boot()
    assert projections._bonus_model(
        boot, 5, {1: {5: [(3, True, 2)]}, 2: {5: [(3, False, 1)]}},
        {1: {5: 1.3}, 2: {5: 1.3}}, [5],
        {p["id"]: p["singular_name_short"] for p in boot["element_types"]}) is None


# --- what it does ---------------------------------------------------------

def test_two_matches_in_a_week_are_two_goes_at_bonus(monkeypatch):
    """The opposite of the ceiling model, where the question is whether he
    hauls at all. Getting the two the same way round would quietly halve every
    double gameweek."""
    monkeypatch.setattr(learn, "load",
                        lambda n: {"model": _Classifier((0.0, 1.0, 0.0, 0.0)),
                                   "features": FEATS})
    boot = _full_boot()
    postypes = {p["id"]: p["singular_name_short"] for p in boot["element_types"]}
    single = projections._bonus_model(
        boot, 5, {1: {5: [(3, True, 2)]}, 2: {5: [(3, False, 1)]}},
        {1: {5: 1.3}, 2: {5: 1.3}}, [5], postypes)
    double = projections._bonus_model(
        boot, 5, {1: {5: [(3, True, 2), (3, False, 2)]}, 2: {5: [(3, False, 1)]}},
        {1: {5: 1.3}, 2: {5: 1.3}}, [5], postypes)
    one = next(e["id"] for e in boot["elements"] if e["team"] == 1)
    assert single[one][5] == pytest.approx(1.0)
    assert double[one][5] == pytest.approx(2.0)


def test_the_model_moves_the_defender_projection(monkeypatch):
    """Wired in means the number changes. The minutes model once passed every
    test while changing nothing, because it was only ever read for display."""
    gws = [5]
    boot, fx = _mixed_boot(), _fixtures(gws)
    _stub_lambdas(monkeypatch, gws)
    monkeypatch.setattr(projections, "_minutes_model", lambda b, p: None)

    monkeypatch.setattr(projections, "_bonus_model",
                        lambda *a, **k: None)
    without = projections.build(boot, fx, gws)
    monkeypatch.setattr(
        projections, "_bonus_model",
        lambda boot, *a, **k: {e["id"]: {5: 2.0} for e in boot["elements"]})
    with_model = projections.build(boot, fx, gws)

    backs = [p for p in without.values() if p["pos"] in ("GKP", "DEF")]
    assert backs, "the fixture has no defenders to check"
    moved = [p["id"] for p in backs
             if with_model[p["id"]]["ep"][5] != p["ep"][5]]
    assert moved, "the bonus model changed no defender — it is not wired in"
    for pid in moved:
        assert with_model[pid]["ep"][5] > without[pid]["ep"][5]


def test_attackers_are_left_alone(monkeypatch):
    """Their points rate already contains the bonus they have earned. Adding a
    model term on top would count it twice."""
    gws = [5]
    boot, fx = _mixed_boot(), _fixtures(gws)
    _stub_lambdas(monkeypatch, gws)
    monkeypatch.setattr(projections, "_minutes_model", lambda b, p: None)

    monkeypatch.setattr(projections, "_bonus_model", lambda *a, **k: None)
    without = projections.build(boot, fx, gws)
    monkeypatch.setattr(
        projections, "_bonus_model",
        lambda boot, *a, **k: {e["id"]: {5: 2.0} for e in boot["elements"]})
    with_model = projections.build(boot, fx, gws)

    for p in without.values():
        if p["pos"] in ("MID", "FWD"):
            assert with_model[p["id"]]["ep"][5] == pytest.approx(p["ep"][5]), \
                f"{p['name']} is a {p['pos']} and his bonus was counted twice"


def test_the_heuristic_still_runs_without_a_model(monkeypatch):
    gws = [5]
    boot, fx = _full_boot(), _fixtures(gws)
    _stub_lambdas(monkeypatch, gws)
    monkeypatch.setattr(projections, "_minutes_model", lambda b, p: None)
    monkeypatch.setattr(projections, "_bonus_model", lambda *a, **k: None)
    out = projections.build(boot, fx, gws)
    assert out and all(p["ep"][5] >= 0 for p in out.values())
    assert all(p["bonus_exp"] is None for p in out.values())


# --- the codes have to agree ----------------------------------------------

def test_the_position_codes_match_the_training_panel():
    """Nothing raises if these drift. The model is simply told every defender
    is a forward, and the projection quietly changes."""
    import inspect
    src = inspect.getsource(data.panel)
    for name, code in projections.POS_CODE.items():
        assert f'"{name}": {code}' in src, \
            f"{name} is {code} in projections and something else in the panel"


# --- the board ------------------------------------------------------------

def _card(pid, **kw):
    c = {"id": pid, "name": f"p{pid}", "team": "T", "pos": "DEF", "price": 5.0,
         "ep_next": 4.0, "exp_minutes": 80, "fixtures": ["AVL(H)"],
         "bonus_exp": None, "bps90": None}
    c.update(kw)
    return c


def test_the_board_ranks_on_the_model_when_it_is_trained():
    rows = leaders.bonus([_card(1, bonus_exp=0.2, bps90=40.0),
                          _card(2, bonus_exp=0.9, bps90=10.0)])
    assert [r["id"] for r in rows] == [2, 1]
    assert all(r["basis"] == "model" for r in rows)


def test_the_board_falls_back_to_bps_not_to_zero():
    """A board of zeros reads as "nobody gets bonus", which is a claim. "We
    ranked on BPS" is the truth."""
    rows = leaders.bonus([_card(1, bps90=12.0), _card(2, bps90=31.0)])
    assert [r["id"] for r in rows] == [2, 1]
    assert all(r["basis"] == "bps" for r in rows)
    assert all(r["bonus_exp"] is None for r in rows)


def test_the_board_puts_both_on_one_scale():
    """Mixed rows are the dangerous case: a raw BPS of 31 next to an expected
    bonus of 0.9 would sort the wrong way round."""
    rows = leaders.bonus([_card(1, bonus_exp=0.9), _card(2, bps90=20.0)])
    assert [r["id"] for r in rows] == [1, 2]          # 0.90 beats 20/34 = 0.59
    # And the raw numbers must not be what decides it: 20 > 0.9.
    assert rows[0]["bonus_exp"] == 0.9 and rows[1]["bps90"] == 20.0


def test_a_player_with_neither_is_left_off():
    assert leaders.bonus([_card(1), _card(2, bps90=0.0)]) == []


def test_the_board_is_in_the_set():
    cards = [_card(1, bonus_exp=0.5)]
    assert "bonus" in leaders.build(cards, gw=6)
