"""Correcting our own model against a better one.

Solio publishes projections for the upcoming gameweek only. That is enough: if
our numbers are systematically high against theirs on the sixty players they
cover this week, they are systematically high on everyone next week too.

So we fit the correction where the two overlap and apply it everywhere. This is
how a free model borrows the calibration of a paid one without pretending to
match its internals.
"""


def fit(local_proj, solio_feed, gw, min_overlap=12):
    """Median ratio of their projection to ours, on the players both cover.

    Median rather than mean because a couple of wild disagreements should not
    move the correction."""
    if not solio_feed:
        return 1.0, 0
    theirs = {}
    for key in ("topProjected", "topCaptains", "topDifferentials", "topGoals",
                "topAssists", "topBonus", "topDefCon"):
        for r in solio_feed.get(key, []):
            theirs[(r["name"], r["team"])] = max(
                theirs.get((r["name"], r["team"]), 0.0), r["prPoints"])
    ratios = []
    for p in local_proj.values():
        t = theirs.get((p["name"], p["team"]))
        if t and p["ep"].get(gw, 0) > 1.0:
            ratios.append(t / p["ep"][gw])
    if len(ratios) < min_overlap:
        return 1.0, len(ratios)
    ratios.sort()
    return ratios[len(ratios) // 2], len(ratios)


def apply(proj, scale, gws, skip_first=True):
    """Scale every projection. The upcoming gameweek is already blended with
    Solio directly, so by default it is left alone."""
    if abs(scale - 1.0) < 0.01:
        return proj
    for p in proj.values():
        for g in gws:
            if skip_first and g == gws[0]:
                continue
            p["ep"][g] = round(p["ep"][g] * scale, 3)
    return proj
