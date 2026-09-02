"""What the best managers in the world are actually doing.

FPL Focal's experts page publishes this, but the page renders client-side and
has no open endpoint. It does not need one: the same thing is computable from
the public API. League 314 is the global Overall league, so its top pages are
the top managers in the world, and their picks are public.

Elite ownership minus overall ownership is the signal. A player at 70% among the
best and 32% overall is a crowd that has not caught up yet.
"""
import time
from collections import Counter

from . import cache, fetch

OVERALL_LEAGUE = 314


def snapshot(gw, top_n=200, page_size=50):
    raw = cache.cached(f"elite:{gw}:{top_n}", lambda: _snapshot(gw, top_n, page_size))
    return {"n": raw["n"],
            "own": {int(k): v for k, v in raw["own"].items()},
            "captains": {int(k): v for k, v in raw["captains"].items()},
            "chips": raw["chips"]}


def _snapshot(gw, top_n=200, page_size=50):
    """Ownership, captaincy and chip usage among the top `top_n` managers."""
    entries = []
    for page in range(1, top_n // page_size + 1):
        d = fetch._get(f"{fetch.FPL}/leagues-classic/{OVERALL_LEAGUE}/standings/"
                       f"?page_standings={page}")
        entries += [r["entry"] for r in d["standings"]["results"]]
        if not d["standings"]["has_next"]:
            break
        time.sleep(0.1)
    entries = entries[:top_n]

    own, cap, chips = Counter(), Counter(), Counter()
    n = 0
    for e in entries:
        try:
            p = fetch.picks(e, gw)
        except Exception:
            continue
        n += 1
        for x in p["picks"]:
            own[x["element"]] += 1
            if x["is_captain"]:
                cap[x["element"]] += 1
        if p.get("active_chip"):
            chips[p["active_chip"]] += 1
        time.sleep(0.06)

    return {"n": n,
            "own": {i: c / max(n, 1) for i, c in own.items()},
            "captains": {i: c / max(n, 1) for i, c in cap.items()},
            "chips": {k: v / max(n, 1) for k, v in chips.items()}}


def buy_signals(boot, elite, min_gap=0.10, limit=20):
    """Where the elite are ahead of the crowd. Positive gap is a buy signal;
    negative means the crowd is holding something the best have moved off."""
    tm = {t["id"]: t["short_name"] for t in boot["teams"]}
    rows = []
    for e in boot["elements"]:
        el = elite["own"].get(e["id"], 0.0)
        crowd = float(e["selected_by_percent"]) / 100
        gap = el - crowd
        if abs(gap) < min_gap:
            continue
        rows.append({"name": e["web_name"], "team": tm[e["team"]],
                     "price": e["now_cost"] / 10, "elite": round(el, 3),
                     "overall": round(crowd, 3), "gap": round(gap, 3),
                     "captain": round(elite["captains"].get(e["id"], 0.0), 3)})
    rows.sort(key=lambda r: -r["gap"])
    return rows[:limit] + rows[-limit:]
