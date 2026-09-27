"""The minutes model has to reach the projection.

Minutes are what a projection is made of, and the trained model that predicts
them was — for a while — computed, blended into a variable, and then dropped on
the floor by the loop that does the work. It survived only as a number printed
on the player's card, which is the worst possible failure: it looked wired in
from the outside.

So these tests do not check the arithmetic. They check that turning the model's
answer up and down moves the projection, and by how much.
"""
from gaffer import projections

from tests.test_ceiling import _full_boot


def _fixtures(gws):
    return [{"event": g, "team_h": 1, "team_a": 2,
             "team_h_difficulty": 3, "team_a_difficulty": 3} for g in gws]


def _stub_lambdas(monkeypatch, gws):
    monkeypatch.setattr(
        projections.defence, "lambdas",
        lambda *a, **k: ({1: {g: 1.3 for g in gws}, 2: {g: 1.3 for g in gws}}, {}))


def _with_p60(monkeypatch, value):
    """Force the learned start probability to one number for everybody."""
    monkeypatch.setattr(projections, "_minutes_model",
                        lambda boot, played: {e["id"]: value for e in boot["elements"]})


def test_the_start_probability_changes_the_projection(monkeypatch):
    """The bug this file exists for: the model ran, and nothing moved."""
    gws = [5]
    boot, fx = _full_boot(), _fixtures(gws)
    _stub_lambdas(monkeypatch, gws)

    _with_p60(monkeypatch, 0.05)
    benched = projections.build(boot, fx, gws)
    _with_p60(monkeypatch, 0.95)
    nailed = projections.build(boot, fx, gws)

    moved = [pid for pid in nailed if nailed[pid]["ep"][5] != benched[pid]["ep"][5]]
    assert moved, "the minutes model changed no projection — it is not wired in"
    for pid in moved:
        assert nailed[pid]["ep"][5] > benched[pid]["ep"][5], \
            "a player more likely to start must project higher"


def test_expected_minutes_follow_the_model_too(monkeypatch):
    """`exp_min` is what the distribution and the diagnosis read. If it and the
    projection disagree about whether a man plays, two views of the same squad
    contradict each other."""
    gws = [5]
    boot, fx = _full_boot(), _fixtures(gws)
    _stub_lambdas(monkeypatch, gws)

    _with_p60(monkeypatch, 0.10)
    low = projections.build(boot, fx, gws)
    _with_p60(monkeypatch, 0.90)
    high = projections.build(boot, fx, gws)
    for pid in low:
        assert high[pid]["exp_min"] >= low[pid]["exp_min"]
    assert any(high[pid]["exp_min"] > low[pid]["exp_min"] for pid in low)


def test_a_man_who_never_plays_is_not_given_a_floor(monkeypatch):
    """The old blend assumed a non-starter plays twenty minutes, which put a
    twelve-minute floor under every footballer in the game — including one who
    has played a single minute since August. His cameo is his own average, not
    a constant."""
    gws = [5]
    boot, fx = _full_boot(), _fixtures(gws)
    # One fringe player in a squad of regulars: the realistic shape, and it
    # keeps the team-strength measurement out of the assertion.
    fringe = boot["elements"][0]
    fringe["minutes"], fringe["starts"] = 1, 0
    _stub_lambdas(monkeypatch, gws)
    _with_p60(monkeypatch, 0.02)

    out = projections.build(boot, fx, gws)
    assert out[fringe["id"]]["exp_min"] <= 6, \
        f"one minute since August, projected {out[fringe['id']]['exp_min']}"


def test_a_league_where_nobody_has_played_does_not_crash(monkeypatch):
    """Preseason, or the round before a ball is kicked. Team strength has no
    minutes to measure and used to divide by zero — taking the whole solve
    with it."""
    gws = [5]
    boot, fx = _full_boot(), _fixtures(gws)
    for e in boot["elements"]:
        e["minutes"], e["starts"] = 0, 0
    _stub_lambdas(monkeypatch, gws)
    monkeypatch.setattr(projections, "_minutes_model", lambda boot, played: None)

    atk, dfn = projections.team_strength(boot)
    assert set(atk) and all(v == 1.0 for v in atk.values())
    out = projections.build(boot, fx, gws)
    assert out and all(p["ep"][5] >= 0 for p in out.values())


def test_a_regular_starter_is_not_dragged_down_by_the_cameo(monkeypatch):
    """The other direction: a nailed-on starter should stay near ninety."""
    gws = [5]
    boot, fx = _full_boot(), _fixtures(gws)
    for e in boot["elements"]:
        e["minutes"] = 450
        e["starts"] = 5
    _stub_lambdas(monkeypatch, gws)
    _with_p60(monkeypatch, 0.97)

    out = projections.build(boot, fx, gws)
    for p in out.values():
        assert p["exp_min"] >= 80, f"{p['name']} projected {p['exp_min']} minutes"


def test_an_unavailable_player_still_projects_nothing(monkeypatch):
    """Availability multiplies the blend, not only the heuristic — otherwise a
    suspended man with a high start probability walks back into the side."""
    gws = [5]
    boot, fx = _full_boot(), _fixtures(gws)
    for e in boot["elements"]:
        e["status"] = "i"
    _stub_lambdas(monkeypatch, gws)
    _with_p60(monkeypatch, 0.99)

    out = projections.build(boot, fx, gws)
    for p in out.values():
        assert p["exp_min"] == 0, f"{p['name']} is injured and has minutes"


def test_build_still_works_without_a_trained_minutes_model(monkeypatch):
    """No model, no blend — the heuristic carries it, as it always could."""
    gws = [5]
    boot, fx = _full_boot(), _fixtures(gws)
    _stub_lambdas(monkeypatch, gws)
    monkeypatch.setattr(projections, "_minutes_model", lambda boot, played: None)

    out = projections.build(boot, fx, gws)
    assert out and all(p["ep"][5] >= 0 for p in out.values())
