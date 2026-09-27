"""The category leaderboards — who leads on what, and why.

The page already lets you sort seven hundred players by any column, which
answers "who is best at X" if you already know which X you care about. These
answer the questions people actually arrive with: who do I captain, where is
the leverage, who scores, who keeps it out.

Each board is a different ordering of the same projections, and each carries
the number it was ranked on rather than only the rank — a leaderboard whose
sort key is invisible is a list you have to trust instead of read.
"""
import math


def _rank(rows, key, limit):
    rows = [r for r in rows if r.get(key) is not None]
    rows.sort(key=lambda r: -r[key])
    return rows[:limit]


def _base(p):
    return {"id": p["id"], "name": p["name"], "team": p["team"],
            "pos": p["pos"], "price": p["price"]}


def captains(cards, gw, limit=15):
    """Ranked on the armband's actual return, which is double.

    Doubling every projection changes no ordering by itself — it is shown
    because the number you are choosing between is the doubled one, and
    reading 6.4 when you will receive 12.8 is a needless translation. The
    ordering comes from the tail as a tie-break: two captains a tenth apart
    are not the same bet if one of them hauls twice as often."""
    out = []
    for p in cards:
        ep = p.get("ep_next")
        if ep is None:
            continue
        r = _base(p)
        r["projected"] = round(ep, 2)
        r["captain_return"] = round(ep * 2, 2)
        r["haul"] = p.get("ceiling")
        r["own"] = p.get("own_overall")
        r["fixture"] = (p.get("fixtures") or [None])[0]
        # Tenths of a point apart on the mean, decided on how often he hauls.
        r["_sort"] = ep * 2 + 0.6 * (p.get("ceiling") or 0.0)
        out.append(r)
    out.sort(key=lambda r: -r["_sort"])
    for r in out:
        r.pop("_sort", None)
    return out[:limit]


def differentials(cards, own_key="own_overall", limit=15, min_ep=3.0,
                  max_own=0.15):
    """Leverage: projected points times the share of the field that does not
    own him.

    A player everyone owns cannot gain you rank — he can only stop you losing
    it. Leverage is what a haul is worth *relative to the field*, which is the
    thing a mini-league is actually played on.

    `max_own` is the gate, not the ranking. Without it the board fills with
    the same premiums as every other board, because a 9.0 projection owned by
    half the game still out-leverages a 5.0 owned by nobody."""
    out = []
    for p in cards:
        ep = p.get("ep_next")
        own = p.get(own_key)
        if ep is None or own is None or ep < min_ep or own > max_own:
            continue
        r = _base(p)
        r["projected"] = round(ep, 2)
        r["own"] = round(own, 4)
        r["leverage"] = round(ep * (1 - own), 2)
        r["haul"] = p.get("ceiling")
        r["fixture"] = (p.get("fixtures") or [None])[0]
        out.append(r)
    return _rank(out, "leverage", limit)


def _per_game(p, per90_key):
    """A per-90 rate turned into what he is expected to do in one match."""
    rate = p.get(per90_key)
    mins = p.get("exp_minutes")
    if rate is None or mins is None:
        return None
    return float(rate) * (float(mins) / 90.0)


def scorers(cards, limit=15):
    """Expected goals this gameweek: the per-90 rate over the minutes he is
    expected to play. A 0.6 xG per 90 striker who plays an hour is not a 0.6
    xG striker."""
    out = []
    for p in cards:
        xg = _per_game(p, "xg90")
        if xg is None:
            continue
        r = _base(p)
        r["xg"] = round(xg, 3)
        r["xg90"] = p.get("xg90")
        r["minutes"] = p.get("exp_minutes")
        r["fixture"] = (p.get("fixtures") or [None])[0]
        out.append(r)
    return _rank(out, "xg", limit)


def creators(cards, limit=15):
    out = []
    for p in cards:
        xa = _per_game(p, "xa90")
        if xa is None:
            continue
        r = _base(p)
        r["xa"] = round(xa, 3)
        r["xa90"] = p.get("xa90")
        r["minutes"] = p.get("exp_minutes")
        r["fixture"] = (p.get("fixtures") or [None])[0]
        out.append(r)
    return _rank(out, "xa", limit)


def defcon(cards, limit=15):
    """Defensive contribution: the two points for hitting the threshold, times
    the chance of hitting it. A rate without a probability attached is a
    trivia fact — it is the probability that is worth points."""
    out = []
    for p in cards:
        pr = p.get("defcon_prob")
        if pr is None:
            continue
        r = _base(p)
        r["defcon_prob"] = round(pr, 3)
        r["defcon90"] = p.get("defcon90")
        # DefCon pays two points when it lands.
        r["expected"] = round(pr * 2, 3)
        r["fixture"] = (p.get("fixtures") or [None])[0]
        out.append(r)
    return _rank(out, "expected", limit)


def movers(cards, limit=12):
    """Who the field is buying and selling, and who is about to change price.

    Ranked on the size of the move rather than its direction, because a player
    haemorrhaging owners matters as much as one being bought — more, if you
    hold him."""
    out = []
    for p in cards:
        net = p.get("net_transfers")
        if net is None or p.get("price_direction") in (None, "hold"):
            continue
        r = _base(p)
        r["net_transfers"] = net
        r["direction"] = p.get("price_direction")
        r["own"] = p.get("own_overall")
        r["_sort"] = abs(net)
        out.append(r)
    out.sort(key=lambda r: -r["_sort"])
    for r in out:
        r.pop("_sort", None)
    return out[:limit]


def haul_distribution(cards, xi_ids, captain_id=None):
    """How many of your eleven go double-digit, as a distribution.

    A squad total is a mean, and a mean cannot tell you whether a week is
    likely to be quietly adequate or to swing. This is the exact
    Poisson-binomial over the eleven ceiling probabilities — computed by
    convolution, not sampled — so the answer is a distribution rather than a
    point estimate.

    The one assumption is independence between team-mates, which is wrong in
    the direction that matters: when a side wins 4-0 its attackers haul
    together. So read the spread as a floor on how wide the real one is, not
    as the real one.
    """
    by_id = {p["id"]: p for p in cards}
    probs = []
    for pid in xi_ids:
        c = (by_id.get(pid) or {}).get("ceiling")
        if c is None:
            continue
        # The captain's score is doubled, so his ten becomes twenty — but he
        # also clears ten whenever he would have on his own. The armband does
        # not change whether he hauls, only what it is worth.
        probs.append(float(c))
    if not probs:
        return None

    dist = [1.0]
    for pr in probs:
        nxt = [0.0] * (len(dist) + 1)
        for k, acc in enumerate(dist):
            nxt[k] += acc * (1 - pr)
            nxt[k + 1] += acc * pr
        dist = nxt

    mean = sum(k * v for k, v in enumerate(dist))
    var = sum((k - mean) ** 2 * v for k, v in enumerate(dist))
    return {
        "n": len(probs),
        "pmf": [round(v, 5) for v in dist],
        "expected": round(mean, 2),
        "sd": round(math.sqrt(var), 2),
        "at_least_one": round(1 - dist[0], 4),
        "at_least_two": round(1 - dist[0] - (dist[1] if len(dist) > 1 else 0), 4),
        "captain": captain_id,
    }


def build(cards, gw, xi_ids=None, captain_id=None, clean_sheets=None,
          limit=15):
    """Every board, in one dict the page can render without arithmetic."""
    return {
        "projected": _rank([{**_base(p), "projected": p.get("ep_next"),
                             "horizon": p.get("ep_horizon"),
                             "haul": p.get("ceiling"),
                             "own": p.get("own_overall"),
                             "fixture": (p.get("fixtures") or [None])[0]}
                            for p in cards], "projected", limit),
        "captains": captains(cards, gw, limit),
        "differentials": differentials(cards, limit=limit),
        "goals": scorers(cards, limit),
        "assists": creators(cards, limit),
        "defcon": defcon(cards, limit),
        "movers": movers(cards),
        "clean_sheets": clean_sheets or [],
        "hauls": (haul_distribution(cards, xi_ids, captain_id)
                  if xi_ids else None),
    }
