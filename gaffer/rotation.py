"""Minutes risk from fixture congestion.

A projection that assumes ninety minutes is wrong for exactly the players you
most want to captain. Erling Haaland against Ipswich looks like the best fixture
of the first half — until you notice it sits between two Champions League ties,
at which point the question is not how many he scores but how long he is on the
pitch.

The Premier League fixture API knows nothing about European football, so the
competing teams and their matchweeks are declared in config. Everything else —
domestic congestion from midweek league rounds — is inferred from the calendar.
"""


def congestion(boot, european_teams=(), european_weeks=(), haircut=0.12,
               midweek_haircut=0.06):
    """Minutes multiplier per team per gameweek.

    european_weeks are the Premier League gameweeks that sit between European
    matchdays for the clubs in european_teams. A haircut of 0.12 means expected
    minutes drop by 12%, which for a striker on 85 minutes is about ten minutes
    and roughly half a point of projection."""
    names = {t["short_name"] for t in boot["teams"]}
    unknown = [t for t in european_teams if t not in names]
    if unknown:
        print(f"  !! unknown teams in european_teams: {unknown}")

    ids = {t["id"]: t["short_name"] for t in boot["teams"]}
    mult = {tid: {} for tid in ids}

    # Domestic midweek rounds hit everybody.
    from datetime import datetime
    evs = sorted((e["id"], datetime.fromisoformat(
        e["deadline_time"].replace("Z", "+00:00"))) for e in boot["events"])
    midweek = {gw for gw, d in evs if d.weekday() in (1, 2, 3)}

    for tid, short in ids.items():
        for gw, _ in evs:
            m = 1.0
            if gw in midweek:
                m -= midweek_haircut
            if short in european_teams and gw in european_weeks:
                m -= haircut
            mult[tid][gw] = m
    return mult


def describe(boot, mult, gw):
    ids = {t["id"]: t["short_name"] for t in boot["teams"]}
    hit = [(ids[t], m[gw]) for t, m in mult.items() if m.get(gw, 1.0) < 0.999]
    return sorted(hit, key=lambda r: r[1])
