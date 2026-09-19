"""Team form: what a side has done lately, not what it has done all season.

The projection already knows about player form — FPL publishes a thirty-day
points average and `projections.build` weighs it against the season rate. Team
strength had no such thing. It was expected goals for and against summed over
every match played, so a side that was poor for a month and has been excellent
for a fortnight scored as mediocre, and stayed mediocre until the average
caught up. By which time the run is over.

Three things this has to get right, or it is worse than nothing:

**Only finished matches count.** A match in progress has a live score attached
to it, and a side three up at half time can finish level. Reading a result
before it has happened is not form, it is wishful thinking with a timestamp.

**Opponent-adjusted, or it just rewards easy fixtures.** Three goals against
the best defence in the league and three against a promoted side are not the
same evidence, and a model that treats them alike will tell you to buy whoever
last played the worst team. Every match is scored against what the season-long
strengths *expected* that team to do in that fixture, home or away, so form
means "better than they should have been", not "scored a lot".

**Shrunk, hard.** Five matches in, one result is a large fraction of the
evidence, and the temptation to read a 3-0 as a new permanent truth is exactly
how a wildcard gets spent on a team that was having a good afternoon. Every
side starts with `prior_games` matches of having performed exactly to
expectation, and the multiplier is clamped besides. This is a tilt, not a
verdict.
"""
import math

# How far a single match may move a team, in either direction. A 6-0 is still
# only one match, and a model that lets it double a team's attack will hand a
# whole squad to whoever won last weekend.
CLAMP = (0.72, 1.38)


def _finished(fixtures):
    """Matches that are over, newest first.

    `finished` rather than `started`: the scoreline of a match in progress is
    not a result. `finished_provisional` is set when the whistle has gone but
    bonus points are still being applied — the score is final by then, which is
    all this needs."""
    done = [x for x in fixtures
            if (x.get("finished") or x.get("finished_provisional"))
            and x.get("team_h_score") is not None
            and x.get("team_a_score") is not None]
    done.sort(key=lambda x: (x.get("kickoff_time") or "", x.get("event") or 0))
    return list(reversed(done))


def recent(boot, fixtures, atk_season, dfn_season, half_life=2.5,
           prior_games=2.5, home_factor=1.14, window=8):
    """Attack and defence form per team, as multipliers around 1.0.

    Above 1.0 on attack means scoring more than the fixtures warranted. Above
    1.0 on defence means conceding more — the same direction as `dfn`, where a
    bigger number is a leakier side.

    `half_life` is in matches: at 2.5, the game before last counts about three
    quarters of the last one, and a month ago counts a third.
    """
    done = _finished(fixtures)
    if not done:
        return {}, {}

    goals = sum(x["team_h_score"] + x["team_a_score"] for x in done)
    mu = goals / (2 * len(done))          # league goals per team per match
    if mu <= 0:
        return {}, {}

    seen = {}
    gf, ef, ga, ea, wt = {}, {}, {}, {}, {}
    for x in done:
        for side, opp, home in ((x["team_h"], x["team_a"], True),
                                (x["team_a"], x["team_h"], False)):
            n = seen.get(side, 0)
            if n >= window:
                continue
            seen[side] = n + 1
            w = 0.5 ** (n / half_life)
            scored = x["team_h_score"] if home else x["team_a_score"]
            let_in = x["team_a_score"] if home else x["team_h_score"]
            ha = home_factor if home else 1 / home_factor
            # What the season-long strengths said this fixture should produce.
            exp_for = mu * atk_season.get(side, 1.0) * dfn_season.get(opp, 1.0) * ha
            exp_ag = mu * atk_season.get(opp, 1.0) * dfn_season.get(side, 1.0) / ha
            gf[side] = gf.get(side, 0.0) + w * scored
            ef[side] = ef.get(side, 0.0) + w * max(0.15, exp_for)
            ga[side] = ga.get(side, 0.0) + w * let_in
            ea[side] = ea.get(side, 0.0) + w * max(0.15, exp_ag)
            wt[side] = wt.get(side, 0.0) + w

    atk, dfn = {}, {}
    for t, w in wt.items():
        if w <= 0:
            continue
        # `prior_games` matches of having performed exactly to expectation,
        # added to both sides of the ratio. Scale-free, and it pulls a team
        # with one match played most of the way back to neutral.
        pad_f = prior_games * (ef[t] / w)
        pad_a = prior_games * (ea[t] / w)
        atk[t] = _clamp((gf[t] + pad_f) / (ef[t] + pad_f))
        dfn[t] = _clamp((ga[t] + pad_a) / (ea[t] + pad_a))
    return atk, dfn


def _clamp(v):
    return max(CLAMP[0], min(CLAMP[1], v))


def blend(season, form, weight):
    """Fold form into a season-long strength, then re-centre on 1.0.

    Geometric rather than additive: `weight` is an exponent, so 0 is the old
    behaviour exactly and 1 applies the form multiplier in full. Everything
    downstream — the clean-sheet lambdas, the per-player multiplier — assumes
    these numbers average one, so blending without re-normalising would quietly
    inflate or deflate the whole league."""
    if not form or weight <= 0:
        return dict(season)
    out = {t: v * (form.get(t, 1.0) ** weight) for t, v in season.items()}
    mean = sum(out.values()) / max(1, len(out))
    if mean <= 0:
        return dict(season)
    return {t: v / mean for t, v in out.items()}


def table(boot, atk_form, dfn_form, limit=None):
    """Who is hot and who is not, for the page.

    Form is the one number here a human can check against what they watched on
    Saturday, so it is worth showing rather than only acting on."""
    names = {t["id"]: t["short_name"] for t in boot["teams"]}
    rows = []
    for tid, name in names.items():
        a = atk_form.get(tid)
        d = dfn_form.get(tid)
        if a is None and d is None:
            continue
        a = a if a is not None else 1.0
        d = d if d is not None else 1.0
        rows.append({
            "team": name,
            "attack": round(a, 3),
            "defence": round(d, 3),
            # One number for sorting: scoring above expectation and conceding
            # below it both count as form, and they trade off evenly.
            "form": round(math.sqrt(a / d), 3),
        })
    rows.sort(key=lambda r: -r["form"])
    return rows[:limit] if limit else rows
