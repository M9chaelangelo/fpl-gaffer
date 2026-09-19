"""What your team might actually score, as a distribution.

Every number on the page until now has been a mean. A mean tells you where the
middle is and nothing about whether the week is likely to be quietly adequate
or to swing — and that difference is most of what a manager is deciding when
he picks a captain or plays a chip.

This builds a points distribution per player from the components that make up
an FPL score, then convolves them into a squad total. Exact, not simulated:
the per-player supports are small integers, so a convolution gives the whole
distribution in milliseconds and there is no sampling error to explain away.

What is modelled, from numbers the export already carries:

  * **Appearance.** Two states — he starts and plays the hour (probability
    `start_prob`), or he does not play at all.
  * **Goals**, Poisson on his expected goals for this match: his per-90 rate
    over the minutes he is expected to play.
  * **Assists**, likewise.
  * **Clean sheet**, a coin weighted by `cs_prob`, worth four to a keeper or
    defender and one to a midfielder.
  * **Defensive contribution**, a coin weighted by `defcon_prob`, worth two.

What is not: bonus, saves, the goals-conceded penalty, cards. Rather than
pretend those are zero, the modelled mean is compared against the projection
the rest of the app quotes and the gap is added back as a constant. The shape
comes from the components; the mean stays the one number every view agrees on.

Two limits worth stating plainly. The two-state appearance model has no
cameos, so it understates the middle-left of the curve. And the convolution
assumes players are independent, which is wrong in the direction that matters:
when a side wins 4-0 its attackers return together. The real distribution is
wider than this one — read the spread as a floor.
"""
import math

GOAL = {"GKP": 6, "DEF": 6, "MID": 5, "FWD": 4}
CLEAN_SHEET = {"GKP": 4, "DEF": 4, "MID": 1, "FWD": 0}
ASSIST = 3
DEFCON = 2

# Beyond this a single player's contribution stops being worth tracking; a
# twenty-five point return is already a once-a-season afternoon for one man.
CAP = 40


def _poisson_pmf(lam, k_max):
    """Probabilities of 0..k_max events, with the tail folded into the last."""
    out, acc = [], 0.0
    for k in range(k_max):
        p = math.exp(-lam) * lam ** k / math.factorial(k)
        out.append(p)
        acc += p
    out.append(max(0.0, 1.0 - acc))
    return out


def _convolve(a, b, cap):
    out = [0.0] * (cap + 1)
    for i, pa in enumerate(a):
        if pa <= 0.0:
            continue
        for j, pb in enumerate(b):
            if pb <= 0.0:
                continue
            out[min(cap, i + j)] += pa * pb
    return out


def _scale(pmf, factor, cap):
    """The same player's score, multiplied — the armband, not a second copy of
    him. Adding an independent duplicate would understate the variance a
    captaincy actually carries."""
    out = [0.0] * (cap + 1)
    for i, p in enumerate(pmf):
        out[min(cap, i * factor)] += p
    return out


def _shift(pmf, by, cap):
    out = [0.0] * (cap + 1)
    for i, p in enumerate(pmf):
        out[max(0, min(cap, i + by))] += p
    return out


def _spread(count_pmf, points_each, cap):
    """A distribution over a count of events becomes one over points."""
    out = [0.0] * (cap + 1)
    for k, p in enumerate(count_pmf):
        out[min(cap, k * points_each)] += p
    return out


def _coin(p, points, cap):
    out = [0.0] * (cap + 1)
    out[0] += 1.0 - p
    out[min(cap, points)] += p
    return out


def mean(pmf):
    return sum(i * p for i, p in enumerate(pmf))


def sd(pmf):
    m = mean(pmf)
    return math.sqrt(sum((i - m) ** 2 * p for i, p in enumerate(pmf)))


def player_points(card, cap=CAP):
    """One player's gameweek, as a probability per whole point.

    None when the card carries too little to model — a projection with no
    minutes behind it is a number, not a distribution.
    """
    ep = card.get("ep_next")
    start = card.get("start_prob")
    mins = card.get("exp_minutes")
    if ep is None or start is None or mins is None or float(mins) <= 0:
        return None
    pos = card.get("pos") or "MID"
    start = max(0.01, min(1.0, float(start)))

    def per_start(rate):
        """Per-90 rates are unconditional. Conditioning them on the start keeps
        the unconditional mean where the projection put it."""
        if rate is None:
            return 0.0
        return max(0.0, float(rate) * (float(mins) / 90.0) / start)

    lam_g = per_start(card.get("xg90"))
    lam_a = per_start(card.get("xa90"))
    p_cs = (max(0.0, min(1.0, float(card["cs_prob"])))
            if card.get("cs_prob") is not None and CLEAN_SHEET[pos] else 0.0)
    p_dc = (max(0.0, min(1.0, float(card["defcon_prob"])))
            if card.get("defcon_prob") is not None else 0.0)

    def assemble(k):
        """The week, with every return scaled by `k`."""
        out = [0.0] * (cap + 1)
        out[2] = 1.0                                       # the hour played
        out = _convolve(out, _spread(_poisson_pmf(lam_g * k, 4), GOAL[pos], cap), cap)
        out = _convolve(out, _spread(_poisson_pmf(lam_a * k, 3), ASSIST, cap), cap)
        if p_cs:
            out = _convolve(out, _coin(min(1.0, p_cs * k), CLEAN_SHEET[pos], cap), cap)
        if p_dc:
            out = _convolve(out, _coin(min(1.0, p_dc * k), DEFCON, cap), cap)
        pmf = [start * p for p in out]
        pmf[0] += 1.0 - start
        return pmf

    target = float(ep)
    pmf = assemble(1.0)
    gap = target - mean(pmf)

    # Bonus, saves, the concession penalty and cards are not modelled, so the
    # components rarely land on the projection the rest of the app quotes. The
    # correction has to keep that mean exactly, because a curve that disagrees
    # with the number on the player's card is worse than no curve.
    if gap > 0:
        # The missing parts — bonus above all — are non-negative, so they go on
        # as an extra component. Split across two whole points so the mean is
        # exact rather than rounded: rounding loses up to half a point per
        # player, and eleven of those is four points on the squad total.
        lo = math.floor(gap)
        frac = gap - lo
        pmf = [(1 - frac) * a + frac * b
               for a, b in zip(_shift(pmf, lo, cap), _shift(pmf, lo + 1, cap))]
    elif gap < -0.01:
        # The components out-produce the projection, which means the projection
        # disagrees with this player's own rates. Trust the projection and
        # scale the returns down to meet it — shifting the curve left instead
        # would pile mass onto zero and not move the mean where it was asked
        # to go, because points do not go below it.
        lo, hi = 0.0, 1.0
        for _ in range(24):
            mid = (lo + hi) / 2
            if mean(assemble(mid)) > target:
                hi = mid
            else:
                lo = mid
        pmf = assemble((lo + hi) / 2)
    return pmf


def squad_points(cards, xi_ids, captain_id=None, bench_ids=(), chip=None,
                 thresholds=(40, 60, 80), cap=200):
    """What the eleven score this gameweek, as a whole distribution.

    `chip` of "bb" counts the bench too; "tc" trebles the armband instead of
    doubling it.
    """
    by_id = {c["id"]: c for c in cards}
    playing = list(xi_ids) + (list(bench_ids) if chip == "bb" else [])
    multiplier = 3 if chip == "tc" else 2

    total = [0.0] * (cap + 1)
    total[0] = 1.0
    modelled = 0
    for pid in playing:
        card = by_id.get(pid)
        if card is None:
            continue
        pmf = player_points(card)
        if pmf is None:
            continue
        if pid == captain_id:
            pmf = _scale(pmf, multiplier, cap)
        total = _convolve(total, pmf, cap)
        modelled += 1

    if not modelled:
        return None

    m = mean(total)
    out = {
        "n": modelled,
        "mean": round(m, 2),
        "sd": round(sd(total), 2),
        "pmf": [round(p, 6) for p in total],
        "thresholds": {str(t): round(sum(total[t:]), 4) for t in thresholds},
        "chip": chip,
    }
    # The score you beat half the time. On a distribution this skewed it says
    # more than the mean it is usually quoted beside.
    running = 0.0
    for i, p in enumerate(total):
        running += p
        if running >= 0.5:
            out["median"] = i
            break
    return out
