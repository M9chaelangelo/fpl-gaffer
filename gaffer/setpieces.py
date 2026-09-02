"""Set-piece and penalty value.

This is a calculator, not a trained model, and deliberately so: the historical
dataset carries no set-piece order column, so there is nothing to train on. But
FPL publishes the orders directly — `penalties_order`,
`direct_freekicks_order`, `corners_and_indirect_freekicks_order` — and those are
the label everyone else would be trying to predict.

The output is extra expected points per 90, fed into the projection.
"""
PEN_CONVERSION = 0.78          # long-run Premier League penalty conversion
GOAL_POINTS = {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4}
# Penalties won per team per 90, league average. Refined per team once a season
# has enough data.
PENS_PER_90 = 0.11


def _share(order):
    """First taker takes nearly all of them; second taker covers absences."""
    if order == 1:
        return 0.85
    if order == 2:
        return 0.12
    if order == 3:
        return 0.03
    return 0.0


def bonus_per_90(element, pos, team_pens_per_90=PENS_PER_90):
    pts = 0.0
    pen = element.get("penalties_order")
    if pen:
        pts += (team_pens_per_90 * _share(pen) * PEN_CONVERSION
                * GOAL_POINTS.get(pos, 4))
    # Direct free kicks and corners mostly show up as assists and bonus, not
    # goals. A small, deliberately conservative uplift.
    if element.get("direct_freekicks_order") == 1:
        pts += 0.12
    if element.get("corners_and_indirect_freekicks_order") == 1:
        pts += 0.22
    return round(pts, 3)


def takers(boot, limit=25):
    pos = {p["id"]: p["singular_name_short"] for p in boot["element_types"]}
    tm = {t["id"]: t["short_name"] for t in boot["teams"]}
    rows = []
    for e in boot["elements"]:
        if not e.get("penalties_order") and not e.get("direct_freekicks_order") \
                and not e.get("corners_and_indirect_freekicks_order"):
            continue
        rows.append({
            "name": e["web_name"], "team": tm[e["team"]],
            "pos": pos[e["element_type"]], "price": e["now_cost"] / 10,
            "pens": e.get("penalties_order"),
            "fk": e.get("direct_freekicks_order"),
            "corners": e.get("corners_and_indirect_freekicks_order"),
            "bonus90": bonus_per_90(e, pos[e["element_type"]]),
        })
    return sorted(rows, key=lambda r: -r["bonus90"])[:limit]
