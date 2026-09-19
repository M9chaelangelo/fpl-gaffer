"""Reading a squad for what is wrong with it.

The solver answers "what should I do". These answer the questions you ask when
you are staring at a team you have already picked: which starters are being
out-scored by someone cheaper, how likely the bench is to be needed, and which
clubs the week actually turns on.

Everything here is a diagnosis, not a recommendation. It names the weakness and
leaves the decision where it belongs.
"""
from . import distribution


def weak_spots(cards, xi_ids, bank=0.0, squad_ids=(), limit=6, min_gain=0.3):
    """Starters out-projected by a similar-priced or cheaper alternative.

    The comparison is deliberately narrow: same position, no dearer than the
    man plus whatever is in the bank, and not already in the squad. That makes
    every row an actual single move you could make this week rather than a
    reminder that Haaland is better than your fourth defender.

    Ranked on the gap, which is the number that decides whether it is worth a
    transfer.
    """
    by_id = {c["id"]: c for c in cards}
    held = set(squad_ids) or set(xi_ids)
    rows = []
    for pid in xi_ids:
        mine = by_id.get(pid)
        if mine is None or mine.get("ep_next") is None:
            continue
        budget = (mine.get("price") or 0) + bank
        best, gain = None, 0.0
        for other in cards:
            if other["id"] in held or other.get("ep_next") is None:
                continue
            if other["pos"] != mine["pos"]:
                continue
            if (other.get("price") or 0) > budget + 1e-9:
                continue
            if (other.get("status") or "a") != "a":
                continue
            d = other["ep_next"] - mine["ep_next"]
            if d > gain:
                best, gain = other, d
        if best is not None and gain >= min_gain:
            rows.append({
                "out": pid,
                "out_name": mine.get("name"),
                "out_ep": round(mine["ep_next"], 2),
                "in": best["id"],
                "in_name": best.get("name"),
                "in_ep": round(best["ep_next"], 2),
                "in_price": best.get("price"),
                "gain": round(gain, 2),
            })
    rows.sort(key=lambda r: -r["gain"])
    return rows[:limit]


def autosub_risk(cards, xi_ids, bench_ids):
    """How likely the bench is needed, and what it costs when it is.

    Two numbers matter and they are different. The chance *somebody* does not
    play is what makes a week feel fragile; the points it costs is what it
    actually does to you — and a deep bench makes the second small while
    leaving the first alone.

    The points lost assume the best legal replacement comes on. Real autosubs
    follow bench order and formation rules, so this is the optimistic end.
    """
    by_id = {c["id"]: c for c in cards}
    starters = [by_id[p] for p in xi_ids if p in by_id]
    bench = [by_id[p] for p in bench_ids if p in by_id]
    if not starters:
        return None

    misses = []
    for p in starters:
        s = p.get("start_prob")
        misses.append(0.0 if s is None else max(0.0, min(1.0, 1.0 - float(s))))

    # The chance at least one of them does not play. Independence again, and
    # again it understates: a postponed match takes several at once.
    none_missing = 1.0
    for m in misses:
        none_missing *= (1 - m)

    lost = 0.0
    for p, m in zip(starters, misses):
        if m <= 0:
            continue
        cover = [b for b in bench
                 if b.get("ep_next") is not None
                 and (b["pos"] == p["pos"] or p["pos"] != "GKP" and b["pos"] != "GKP")]
        best = max((b["ep_next"] for b in cover), default=0.0)
        lost += m * max(0.0, (p.get("ep_next") or 0.0) - best)

    return {
        "any_autosub": round(1 - none_missing, 4),
        "avg_miss": round(sum(misses) / len(misses), 4),
        "expected_points_lost": round(lost, 2),
        "riskiest": sorted(
            [{"id": p["id"], "name": p.get("name"),
              "miss": round(m, 4), "ep": p.get("ep_next")}
             for p, m in zip(starters, misses) if m > 0.02],
            key=lambda r: -r["miss"])[:5],
    }


def exposure(cards, xi_ids, captain_id=None, limit=None):
    """Which clubs the week turns on — yours against the field's.

    "You" is how many of a club's players you are effectively carrying, with
    the captain counted at his multiplier because that is what he is worth.
    "Field" is the same figure for the average manager, summed from overall
    ownership. The difference is your exposure: positive means you win when
    that club has a good afternoon and lose when it does not, negative means
    the reverse, and near zero means the club cannot move you either way.

    `swing` weights that difference by how much the players involved actually
    vary, so a gap on a volatile forward counts for more than the same gap on
    a goalkeeper who scores three every week. It is this module's definition,
    not a reproduction of anyone else's.
    """
    by_id = {c["id"]: c for c in cards}
    mine, field, vol = {}, {}, {}

    for c in cards:
        own = c.get("own_overall")
        if own is None:
            continue
        field[c["team"]] = field.get(c["team"], 0.0) + float(own)

    for pid in xi_ids:
        c = by_id.get(pid)
        if c is None:
            continue
        w = 2.0 if pid == captain_id else 1.0
        mine[c["team"]] = mine.get(c["team"], 0.0) + w
        pmf = distribution.player_points(c)
        if pmf is not None:
            vol[c["team"]] = max(vol.get(c["team"], 0.0), distribution.sd(pmf))

    rows = []
    for team in set(mine) | set(field):
        you = mine.get(team, 0.0)
        them = field.get(team, 0.0)
        # A club you do not own still swings you — against you — so the
        # absolute difference is the exposure, not the amount you hold.
        rows.append({
            "team": team,
            "you": round(you, 2),
            "field": round(them, 2),
            "diff": round(you - them, 2),
            "swing": abs(you - them) * vol.get(team, 1.0),
        })
    total = sum(r["swing"] for r in rows) or 1.0
    for r in rows:
        r["share"] = round(r["swing"] / total, 4)
        r["swing"] = round(r["swing"], 3)
    rows.sort(key=lambda r: -r["swing"])
    return rows[:limit] if limit else rows


def template(cards, xi_ids, threshold=0.30):
    """How much of your eleven the field also owns.

    A template team cannot gain rank and cannot lose it. The number is the
    share of your starters owned by more than `threshold` of the game."""
    by_id = {c["id"]: c for c in cards}
    owned = [by_id[p].get("own_overall") for p in xi_ids if p in by_id]
    owned = [o for o in owned if o is not None]
    if not owned:
        return None
    return {
        "share": round(sum(1 for o in owned if o >= threshold) / len(owned), 4),
        "mean_ownership": round(sum(owned) / len(owned), 4),
        "threshold": threshold,
    }


def build(cards, xi_ids, bench_ids=(), captain_id=None, squad_ids=(), bank=0.0):
    """Everything the diagnosis view needs, in one dict."""
    return {
        "weak_spots": weak_spots(cards, xi_ids, bank=bank, squad_ids=squad_ids),
        "autosubs": autosub_risk(cards, xi_ids, bench_ids),
        "exposure": exposure(cards, xi_ids, captain_id, limit=14),
        "template": template(cards, xi_ids),
    }
