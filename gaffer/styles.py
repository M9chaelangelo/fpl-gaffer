"""Positional profile: where a player does his work, not just how much.

Two forwards on the same expected goals are not the same asset. One takes six
shots from the edge of the box, the other takes two from six yards. The second
is the better FPL pick, because his goals come from positions that repeat.

Understat's shot-location data would be ideal, but the site now renders
client-side and no longer ships the JSON in its HTML, so it is not reliably
scrapable. Everything below is derived instead from Opta's ICT components,
which FPL publishes directly and which already encode shot location:

  threat      volume and quality of goal attempts, weighted by where they came
              from — the closest public thing to "touches in the box"
  creativity  chance creation, weighted by the quality of chance made
  influence   match-defining actions

Shot quality is the ratio of expected goals to threat: high means his attempts
come from good positions, low means he shoots from distance. Attacking share is
his slice of his own team's expected goal involvement — how central he is.
"""


def _p90(v, minutes):
    return (float(v) / (minutes / 90)) if minutes >= 45 else 0.0


def profile(boot, min_minutes=90):
    pos = {p["id"]: p["singular_name_short"] for p in boot["element_types"]}
    tm = {t["id"]: t["short_name"] for t in boot["teams"]}

    team_xgi = {}
    for e in boot["elements"]:
        team_xgi[e["team"]] = team_xgi.get(e["team"], 0.0) + \
            float(e["expected_goal_involvements"])

    out = {}
    for e in boot["elements"]:
        m = e["minutes"]
        if m < min_minutes:
            continue
        threat90 = _p90(e["threat"], m)
        xg90 = _p90(e["expected_goals"], m)
        xa90 = _p90(e["expected_assists"], m)
        p = pos[e["element_type"]]
        out[e["id"]] = {
            "name": e["web_name"], "team": tm[e["team"]], "pos": p,
            "price": e["now_cost"] / 10,
            "xg90": round(xg90, 3),
            "xa90": round(xa90, 3),
            "xgi90": round(xg90 + xa90, 3),
            "threat90": round(threat90, 1),
            "creativity90": round(_p90(e["creativity"], m), 1),
            "influence90": round(_p90(e["influence"], m), 1),
            # Goal attempts from good positions convert. Attempts from 25 yards
            # mostly do not, however many of them there are.
            "shot_quality": round(xg90 / threat90, 4) if threat90 > 1 else None,
            # How much of his own team's attack runs through him.
            "attacking_share": round(
                float(e["expected_goal_involvements"]) / team_xgi[e["team"]], 3)
            if team_xgi.get(e["team"], 0) > 0 else 0.0,
            "defcon90": round(float(e["defensive_contribution_per_90"]), 1),
            "xgc90": round(float(e["expected_goals_conceded_per_90"]), 2),
            "minutes": m,
        }
    return out


def box_threats(prof, position=("FWD", "MID"), limit=20):
    """Attackers whose shots come from good positions and who carry their team's
    attack. This is the list to buy from, ahead of raw expected goals."""
    rows = [r for r in prof.values()
            if r["pos"] in position and r["shot_quality"] is not None
            and r["xg90"] > 0.15]
    rows.sort(key=lambda r: -(r["shot_quality"] * 100 + r["attacking_share"] * 2))
    return rows[:limit]


def creators(prof, limit=15):
    rows = [r for r in prof.values() if r["xa90"] > 0.1]
    rows.sort(key=lambda r: -(r["xa90"] + r["creativity90"] / 100))
    return rows[:limit]
