"""Team form.

The three ways this goes wrong are all testable, and all of them would make
the model worse than leaving it out: reading a match that has not finished,
rewarding a team for playing bad opponents, and letting one result rewrite a
side's rating.
"""
from gaffer import projections, teamform


def boot(n_teams=6):
    return {
        "teams": [{"id": i, "short_name": f"T{i}", "name": f"Team {i}"}
                  for i in range(1, n_teams + 1)],
        "elements": [],
        "element_types": [],
    }


def match(h, a, hs, a_s, event=1, finished=True, kickoff=None):
    return {
        "event": event, "team_h": h, "team_a": a,
        "team_h_score": hs, "team_a_score": a_s,
        "finished": finished, "finished_provisional": False,
        "kickoff_time": kickoff or f"2026-08-{event:02d}T14:00:00Z",
    }


def neutral(n=6):
    """Every side exactly average, so form is the only thing moving."""
    return ({i: 1.0 for i in range(1, n + 1)},
            {i: 1.0 for i in range(1, n + 1)})


def league_of(results, n=6):
    """`results` is a list of (gw, home, away, hs, as)."""
    return [match(h, a, hs, a_s, event=g) for g, h, a, hs, a_s in results]


# --- the three ways this goes wrong ----------------------------------------

def test_a_match_in_progress_is_not_a_result():
    """Brighton three up at half time is not Brighton beating Arsenal 3-0.
    A side can concede three in the last ten minutes, and a model that has
    already banked the win cannot take it back."""
    atk_s, dfn_s = neutral()
    live = [match(1, 2, 3, 0, event=1, finished=False)]
    live[0]["finished_provisional"] = False
    a, d = teamform.recent(boot(), live, atk_s, dfn_s)
    assert a == {} and d == {}, "an unfinished match must not count"

    # The same match, once the whistle has gone.
    done = [match(1, 2, 3, 0, event=1)]
    a2, _ = teamform.recent(boot(), done, atk_s, dfn_s)
    assert a2[1] > 1.0


def test_the_whistle_has_gone_even_if_bonus_has_not():
    """`finished_provisional` means played but bonus still settling. The score
    is final, which is all form needs."""
    atk_s, dfn_s = neutral()
    m = match(1, 2, 3, 0, event=1, finished=False)
    m["finished_provisional"] = True
    a, _ = teamform.recent(boot(), [m], atk_s, dfn_s)
    assert a.get(1, 1.0) > 1.0


def test_form_is_opponent_adjusted_not_just_goals_scored():
    """Three against the best defence in the league beats three against the
    worst. A model that cannot tell them apart will buy whoever last played
    the bottom side."""
    n = 6
    atk_s = {i: 1.0 for i in range(1, n + 1)}
    dfn_s = {i: 1.0 for i in range(1, n + 1)}
    dfn_s[2] = 0.5      # team 2 is miserly
    dfn_s[3] = 1.8      # team 3 leaks

    fx = league_of([(1, 1, 2, 3, 0), (1, 4, 3, 3, 0)])
    a, _ = teamform.recent(boot(), fx, atk_s, dfn_s)
    assert a[1] > a[4], \
        "three past a good defence should read as better form than three past a bad one"


def test_one_result_cannot_rewrite_a_team():
    """The clamp and the prior both exist to stop a single afternoon deciding
    a wildcard."""
    atk_s, dfn_s = neutral()
    a, _ = teamform.recent(boot(), league_of([(1, 1, 2, 7, 0)]), atk_s, dfn_s)
    assert a[1] <= teamform.CLAMP[1]

    # The clamp alone would pass that, so check the prior does its own work on
    # a result the clamp never touches. One 2-0 at home against an average
    # side is scoring about 1.75x expectation; shrunk against 2.5 matches of
    # having been exactly average, it should land nearer 1.2 than 1.75.
    a2, _ = teamform.recent(boot(), league_of([(1, 1, 2, 2, 0)]), atk_s, dfn_s)
    assert 1.05 < a2[1] < 1.30, a2[1]
    assert a2[1] < teamform.CLAMP[1] - 0.05, "not the clamp doing the work"


# --- the mechanics ----------------------------------------------------------

def test_recent_matches_count_more_than_old_ones():
    atk_s, dfn_s = neutral()
    # Same two results, opposite order in time.
    early_good = league_of([(1, 1, 2, 4, 0), (2, 1, 3, 0, 0)])
    late_good = league_of([(1, 1, 2, 0, 0), (2, 1, 3, 4, 0)])
    a_early, _ = teamform.recent(boot(), early_good, atk_s, dfn_s)
    a_late, _ = teamform.recent(boot(), late_good, atk_s, dfn_s)
    assert a_late[1] > a_early[1], "the more recent result must carry more weight"


def test_defence_form_points_the_same_way_as_dfn():
    """Above 1.0 means leakier, matching the season-long convention — get this
    backwards and every clean sheet projection inverts."""
    atk_s, dfn_s = neutral()
    fx = league_of([(1, 1, 2, 0, 4)])
    _, d = teamform.recent(boot(), fx, atk_s, dfn_s)
    assert d[1] > 1.0, "conceding four should raise the defensive number"
    assert d[2] < 1.0, "keeping a clean sheet should lower it"


def test_home_and_away_are_not_the_same_evidence():
    atk_s, dfn_s = neutral()
    home = league_of([(1, 1, 2, 2, 0)])
    away = league_of([(1, 2, 1, 0, 2)])
    a_home, _ = teamform.recent(boot(), home, atk_s, dfn_s)
    a_away, _ = teamform.recent(boot(), away, atk_s, dfn_s)
    assert a_away[1] > a_home[1], "two away is better evidence than two at home"


def test_blend_is_a_no_op_at_zero_weight():
    season = {1: 1.4, 2: 0.7, 3: 1.0}
    form = {1: 0.72, 2: 1.38, 3: 1.0}
    assert teamform.blend(season, form, 0.0) == season
    assert teamform.blend(season, {}, 0.9) == season


def test_blend_keeps_the_league_centred_on_one():
    """Everything downstream assumes these average one. Blending without
    re-normalising would inflate or deflate every projection in the game."""
    season = {1: 1.4, 2: 0.7, 3: 1.0, 4: 0.9}
    form = {1: 1.38, 2: 1.38, 3: 1.38, 4: 1.38}     # the whole league "hot"
    out = teamform.blend(season, form, 1.0)
    assert abs(sum(out.values()) / len(out) - 1.0) < 1e-9


def test_blend_moves_a_team_the_right_way():
    season = {1: 1.0, 2: 1.0, 3: 1.0}
    form = {1: 1.3, 2: 1.0, 3: 1.0}
    out = teamform.blend(season, form, 0.5)
    assert out[1] > out[2] == out[3]


def test_window_caps_how_far_back_it_looks():
    atk_s, dfn_s = neutral()
    many = league_of([(g, 1, 2, 0, 0) for g in range(1, 12)]
                     + [(12, 1, 3, 5, 0)])
    a, _ = teamform.recent(boot(), many, atk_s, dfn_s, window=2)
    # Only the last two matches are in scope, and the 5-0 is the newest.
    assert a[1] > 1.1


def test_table_ranks_the_hot_teams_first():
    rows = teamform.table(boot(3), {1: 1.3, 2: 1.0, 3: 0.8},
                          {1: 0.8, 2: 1.0, 3: 1.3})
    assert [r["team"] for r in rows] == ["T1", "T2", "T3"]
    assert rows[0]["form"] > 1.0 > rows[-1]["form"]
    assert abs(rows[1]["form"] - 1.0) < 1e-9


def test_no_finished_matches_means_no_form():
    atk_s, dfn_s = neutral()
    a, d = teamform.recent(boot(), [], atk_s, dfn_s)
    assert a == {} and d == {}


# --- the wiring -------------------------------------------------------------

def _boot_with_players(n_teams=4):
    b = boot(n_teams)
    for t in range(1, n_teams + 1):
        for k in range(11):
            b["elements"].append({
                "id": t * 100 + k, "team": t, "minutes": 450,
                "expected_goals": 0.5, "expected_assists": 0.4,
                "expected_goals_conceded_per_90": 1.2,
            })
    return b


def test_team_strength_is_unchanged_at_zero_weight():
    """The default has to be the old behaviour exactly, or every existing
    projection shifts the day this lands."""
    b = _boot_with_players()
    fx = league_of([(1, 1, 2, 5, 0)], n=4)
    base = projections.team_strength(b)
    assert projections.team_strength(b, fixtures=fx, form_weight=0.0) == base
    assert projections.team_strength(b, fixtures=None, form_weight=0.9) == base


def test_team_strength_moves_a_team_in_form():
    b = _boot_with_players()
    fx = league_of([(1, 1, 2, 4, 0), (2, 1, 3, 3, 0)], n=4)
    plain_atk, plain_dfn = projections.team_strength(b)
    form_atk, form_dfn = projections.team_strength(b, fixtures=fx, form_weight=0.6)
    assert form_atk[1] > plain_atk[1], "a side scoring freely should rate higher"
    assert form_dfn[1] < plain_dfn[1], "and two clean sheets should rate tighter"
    # The league still averages one.
    assert abs(sum(form_atk.values()) / len(form_atk) - 1.0) < 1e-9


def test_build_carries_team_form_all_the_way_to_a_projection(monkeypatch):
    """The wiring is the point. `team_strength` moving in isolation proves
    nothing if `build` calls it without the fixtures, which is exactly the
    shape of bug that leaves a feature switched off in production."""
    from tests.test_ceiling import _full_boot

    gws = [5, 6]
    b = _full_boot()
    # Season form identical for both sides; team 1 has been winning lately.
    played = [match(1, 2, 3, 0, event=g) for g in (3, 4)]
    upcoming = [{"event": g, "team_h": 1, "team_a": 2,
                 "team_h_difficulty": 3, "team_a_difficulty": 2} for g in gws]
    monkeypatch.setattr(
        projections.defence, "lambdas",
        lambda *a, **k: ({1: {g: 1.25 for g in gws}, 2: {g: 1.60 for g in gws}}, {}))

    off = projections.build(b, played + upcoming, gws, team_form_weight=0.0)
    on = projections.build(b, played + upcoming, gws, team_form_weight=0.8)

    t1 = [p for p in off.values() if p["team_id"] == 1]
    assert t1, "fixture has no team-1 players"
    moved = [pid for pid in off
             if off[pid]["team_id"] == 1 and on[pid]["ep"][5] != off[pid]["ep"][5]]
    assert moved, "team form changed nothing — build is not passing the fixtures"
    for pid in moved:
        assert on[pid]["ep"][5] > off[pid]["ep"][5], \
            "a side scoring three a game should project higher, not lower"
