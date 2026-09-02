"""The value of waiting.

A wildcard is a bet on fifteen players at once, priced with whatever information
exists on the day you play it. Play it in Gameweek 3 and you are extrapolating
from two matches. Play it after an international break and you know who is fit,
who has lost his place, and which early hot streaks were real.

The optimiser cannot see this on its own: it scores every gameweek with the same
projections, so it always prefers acting sooner. This module supplies the
counterweight — an explicit, tunable estimate of what information is worth.

Nothing here is measured from data. It is a judgement, exposed as a dial rather
than buried in an assumption, and `breakeven()` tells you how large it would have
to be to change your decision.
"""
import math
from datetime import datetime

BREAK_DAYS = 10          # a gap this long between deadlines is an internationals window


def calendar(boot):
    """Deadlines, plus which gameweeks follow an international break."""
    evs = [(e["id"], datetime.fromisoformat(e["deadline_time"].replace("Z", "+00:00")))
           for e in boot["events"]]
    evs.sort()
    out = {}
    for i, (gw, d) in enumerate(evs):
        gap = (d - evs[i - 1][1]).days if i else 7
        out[gw] = {"deadline": d, "gap_days": gap, "after_break": gap >= BREAK_DAYS}
    return out


def info_quality(gw, tau=4.0):
    """How much of what you need to know is knowable by gameweek `gw`.

    Rises fast early — the third match tells you far more than the twentieth —
    then flattens. Bounded 0 to 1."""
    weeks = max(0, gw - 1)
    return 1.0 - math.exp(-weeks / tau)


def wildcard_bonus(gw, cal, info_value=12.0, break_bonus=4.0, tau=4.0):
    """Points to credit a wildcard played in `gw` for the information you will
    have by then, relative to playing it immediately.

    info_value is the total worth of perfect information on a fifteen-player
    rebuild. 12.0 is roughly 0.8 points per player — deliberately conservative.
    break_bonus is added on top for a gameweek straight after an international
    break, when fitness and rotation news has actually resolved."""
    b = info_value * info_quality(gw, tau)
    if cal.get(gw, {}).get("after_break"):
        b += break_bonus
    return b


def breakeven(results, cal, tau=4.0):
    """Given {gw: projected_total}, return how large `info_value` must be for a
    later wildcard to overtake the best early one. This is the number to argue
    about, rather than the projections themselves."""
    best_gw = max(results, key=results.get)
    out = {}
    for gw, total in sorted(results.items()):
        if gw <= best_gw:
            continue
        d_info = info_quality(gw, tau) - info_quality(best_gw, tau)
        extra = 4.0 if cal.get(gw, {}).get("after_break") else 0.0
        need = results[best_gw] - total - extra
        out[gw] = {
            "points_behind": round(results[best_gw] - total, 1),
            "break_credit": extra,
            "info_value_needed": round(need / d_info, 1) if d_info > 1e-6 else None,
            "after_break": cal.get(gw, {}).get("after_break", False),
        }
    return best_gw, out
