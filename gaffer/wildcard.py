"""Draft a wildcard squad from nothing.

A wildcard is a different problem from a transfer. The weekly solve asks which
one or two moves beat the friction of making them; this asks what fifteen
players you would buy if you had never owned anyone.

The pool is built by position and price band — the best few in every cell, plus
the cheapest players in the game outright — so the enablers are guaranteed to
exist before the solver starts arguing about money. Be honest about what that
buys: measured against the weekly model's pool (top hundred and thirty by
projected points) on GW6-13 of this season, it was worth **0.36 points**. Five
games in, projections are flat enough that four-pound defenders reach a top-130
cut on their own, so the guarantee is redundant — today. It stops being
redundant once the season separates the cheap end from the expensive end, and a
rebuild that cannot see a 4.0 defender cannot afford three premiums. This is
insurance, not a points gain, and the day it pays is the day nobody is checking.

Three other things differ from the weekly model:

  * The horizon is longer — eight weeks, not five. Worth **1.22 points** on the
    same measurement: the largest of the three, and still small. A wildcard is
    a structural decision and the extra weeks mostly confirm what four already
    said.
  * Chips you have already committed to are known, not decisions. Worth **0.77
    points**, all of it in the Bench Boost week, where the bench pays full
    price and the draft buys one that plays. It also removes every bilinear
    term, which is what makes the bigger pool and longer horizon affordable.
  * Nothing is bought or sold after the draft. The squad is fixed and scored
    forward. Assuming you will also make perfect transfers afterwards flatters
    every squad by roughly the same amount and hides the differences between
    them, which are the only thing this is meant to measure.

Two and a half points over eight gameweeks is the whole modelling case, and it
is not why this module exists. It exists because a rebuild is now an artefact
you can look at, argue with, and re-run — fifteen names with a priced
alternative behind each one — instead of thirteen transfers buried in week two
of a five-week plan.
"""
import pulp

from . import planner
from .optimise import rivalry_weight

SQUAD = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
XI_MIN = {"GKP": 1, "DEF": 3, "MID": 2, "FWD": 1}
XI_MAX = {"GKP": 1, "DEF": 5, "MID": 5, "FWD": 3}
MAX_PER_CLUB = 3
XI_SIZE = 11

# Price bands in millions, as upper bounds. Narrow at the bottom and wide at
# the top on purpose: the difference between a 4.0 and a 4.5 defender is a
# whole premium somewhere else in the squad, while 10.5 and 12.0 are the same
# decision taken twice.
BANDS = (4.5, 5.0, 5.5, 6.5, 8.0, 10.0, 999.0)


def _horizon(p, gws):
    return sum(p["ep"].get(g, 0.0) for g in gws)


def _band(price):
    return next(b for b in BANDS if price <= b)


def pool(proj, gws, cfg, keep=(), ban=()):
    """Candidates for a rebuild: the best few per position and price band.

    Sorting the whole game by projected points and cutting at N answers "who
    is good", which is not the question. A wildcard needs to know who is good
    *at every price*, because the cheap slots are what fund the expensive ones.
    """
    floor = cfg.get("wildcard_min_minutes", 20)
    per_cell = cfg.get("wildcard_per_cell", 14)
    cheapest = cfg.get("wildcard_cheap_per_pos", 6)
    banned = set(ban)

    live = [p for p in proj.values()
            if p["id"] not in banned and p["status"] == "a"
            and p["exp_min"] >= floor]

    cells, by_pos = {}, {}
    for p in live:
        cells.setdefault((p["pos"], _band(p["price"])), []).append(p)
        by_pos.setdefault(p["pos"], []).append(p)

    picked = {}
    for lst in cells.values():
        lst.sort(key=lambda p: -_horizon(p, gws))
        for p in lst[:per_cell]:
            picked[p["id"]] = p

    # Bench fodder is bought on price first and points second, and the very
    # cheapest players can miss their own band's top few on points alone.
    for lst in by_pos.values():
        lst.sort(key=lambda p: (p["price"], -_horizon(p, gws)))
        for p in lst[:cheapest]:
            picked[p["id"]] = p

    # Players you have told it to keep are in the squad whatever the filters
    # think of them — an injury flag on a man you are keeping is your call.
    for pid in keep:
        if pid in proj:
            picked[pid] = proj[pid]
    return list(picked.values())


def bench_value(p, cfg):
    """What a bench slot is worth in a normal week.

    The reserve keeper is the only squad slot that is almost never used, so he
    gets his own weight rather than the outfield average."""
    bw = cfg.get("bench_weights", [0.16, 0.11, 0.06, 0.02])
    return bw[3] if p["pos"] == "GKP" else sum(bw[:3]) / 3


def evaluate(squad_ids, proj, gws, cfg, pack_own=None, bb_gw=None, tc_gw=None):
    """Score a fifteen forward over the horizon.

    Used for both the draft's reported total and the swap analysis, so the two
    numbers are the same measurement rather than two that nearly agree.

    This is expected points, with no ceiling tilt in it. The tilt belongs to
    the optimiser, where it decides who wears the armband on a Triple Captain
    week; folding it into the score as well would report points the squad
    cannot actually be expected to deliver."""
    pack_own = pack_own or {}
    rivalry = cfg.get("rivalry", 0.0)
    decay = cfg.get("decay", 0.87)
    total = 0.0
    for gi, g in enumerate(gws):
        d = decay ** gi
        team = planner.best_xi(list(squad_ids), proj, g)
        if team is None:
            return float("-inf")
        for pid in team["xi"]:
            p = proj[pid]
            total += d * p["ep"].get(g, 0.0) * rivalry_weight(pid, pack_own, rivalry)
        for pid in team["bench"]:
            p = proj[pid]
            w = 1.0 if g == bb_gw else bench_value(p, cfg)
            total += d * w * p["ep"].get(g, 0.0) \
                * rivalry_weight(pid, pack_own, rivalry)
        cap = captain_for(team["xi"], proj, g, cfg, pack_own,
                          triple=(g == tc_gw))
        if cap is not None:
            mult = 2 if g == tc_gw else 1
            total += d * mult * proj[cap]["ep"].get(g, 0.0) \
                * rivalry_weight(cap, pack_own, rivalry)
    return total


def captain_for(xi, proj, gw, cfg, pack_own=None, triple=False):
    """Who wears it. On a Triple Captain week the tail gets a say.

    Expected points and ceiling rank players differently, and tripling only
    pays when the man hauls — so the armband tilts toward whoever can spike in
    the week the chip is on, and is decided on points alone every other week.
    """
    pack_own = pack_own or {}
    rivalry = cfg.get("rivalry", 0.0)
    best, score = None, None
    for pid in xi:
        p = proj[pid]
        s = p["ep"].get(gw, 0.0) * rivalry_weight(pid, pack_own, rivalry)
        if triple:
            haul = (p.get("ceiling") or {}).get(gw)
            if haul is not None:
                s += cfg.get("ceiling_weight", 6.0) * haul
        if score is None or s > score:
            best, score = pid, s
    return best


def draft(proj, gws, budget, cfg, pack_own=None, keep=(), ban=(),
          bb_gw=None, tc_gw=None, candidates=None):
    """The fifteen to buy, and how they line up each week.

    `budget` is what the rebuild has to spend: your bank plus the selling value
    of everything you own. `keep` forces players in, `ban` keeps them out —
    both by id, so you can argue with the model without editing it.
    """
    pack_own = pack_own or {}
    rivalry = cfg.get("rivalry", 0.0)
    decay = cfg.get("decay", 0.87)
    keep = [k for k in keep if k in proj]

    cand = candidates if candidates is not None else pool(proj, gws, cfg, keep, ban)
    P = {p["id"]: p for p in cand}
    for pid in keep:
        P.setdefault(pid, proj[pid])

    m = pulp.LpProblem("wildcard", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x{i}", cat="Binary") for i in P}
    y = {(i, g): pulp.LpVariable(f"y{i}_{g}", cat="Binary") for i in P for g in gws}
    c = {(i, g): pulp.LpVariable(f"c{i}_{g}", cat="Binary") for i in P for g in gws}

    obj = []
    for gi, g in enumerate(gws):
        d = decay ** gi
        for i, p in P.items():
            ep = p["ep"].get(g, 0.0) * rivalry_weight(i, pack_own, rivalry) * d
            obj.append(ep * y[(i, g)])
            obj.append(ep * c[(i, g)])                       # captain doubles
            # A Bench Boost week is a week where the bench pays full price.
            # Because the week is already decided, that is a coefficient rather
            # than another binary multiplied by another binary.
            bench = 1.0 if g == bb_gw else bench_value(p, cfg)
            obj.append(ep * bench * (x[i] - y[(i, g)]))
            if g == tc_gw:
                obj.append(ep * c[(i, g)])                   # and again
                haul = (p.get("ceiling") or {}).get(g)
                if haul is not None:
                    obj.append(cfg.get("ceiling_weight", 6.0) * haul * d
                               * c[(i, g)])
    m += pulp.lpSum(obj)

    m += pulp.lpSum(x.values()) == 15
    for pos, n in SQUAD.items():
        m += pulp.lpSum(x[i] for i in P if P[i]["pos"] == pos) == n
    for t in {p["team_id"] for p in P.values()}:
        m += pulp.lpSum(x[i] for i in P if P[i]["team_id"] == t) <= MAX_PER_CLUB
    m += pulp.lpSum(x[i] * P[i]["price"] for i in P) <= budget
    for pid in keep:
        m += x[pid] == 1

    for g in gws:
        m += pulp.lpSum(y[(i, g)] for i in P) == XI_SIZE
        m += pulp.lpSum(c[(i, g)] for i in P) == 1
        for pos in SQUAD:
            s = pulp.lpSum(y[(i, g)] for i in P if P[i]["pos"] == pos)
            m += s >= XI_MIN[pos]
            m += s <= XI_MAX[pos]
        for i in P:
            m += y[(i, g)] <= x[i]
            m += c[(i, g)] <= y[(i, g)]

    m.solve(pulp.PULP_CBC_CMD(msg=0,
                              timeLimit=cfg.get("wildcard_time_limit", 180)))
    status = pulp.LpStatus[m.status]
    squad = [i for i in P if (x[i].value() or 0) > 0.5]
    if len(squad) != 15:
        # Almost always the budget: a squad that cannot be bought is not a
        # modelling subtlety, and saying so beats returning fourteen players.
        raise ValueError(
            f"no legal wildcard squad for {budget:.1f}m from {len(P)} candidates "
            f"(solver said {status}, picked {len(squad)}) — check the budget "
            f"and the keep list")

    return finish(squad, proj, gws, cfg, pack_own, bb_gw, tc_gw, budget,
                  optimal=(status == "Optimal"))


def finish(squad, proj, gws, cfg, pack_own=None, bb_gw=None, tc_gw=None,
           budget=None, optimal=True):
    """Turn fifteen ids into the thing you can actually read."""
    weeks = []
    for g in gws:
        team = planner.best_xi(list(squad), proj, g)
        cap = captain_for(team["xi"], proj, g, cfg, pack_own, triple=(g == tc_gw))
        # What the week actually scores, chip included — a Bench Boost week
        # that reported eleven players' points would hide the reason it is
        # being played there.
        ep = sum(proj[i]["ep"].get(g, 0.0) for i in team["xi"])
        ep += proj[cap]["ep"].get(g, 0.0) * (2 if g == tc_gw else 1)
        if g == bb_gw:
            ep += sum(proj[i]["ep"].get(g, 0.0) for i in team["bench"])
        weeks.append({
            "gw": g,
            "xi": team["xi"],
            "bench": team["bench"],
            "formation": team["formation"],
            "captain": cap,
            "chip": ("Bench Boost" if g == bb_gw else
                     "Triple Captain" if g == tc_gw else None),
            "ep": round(ep, 1),
        })
    cost = round(sum(proj[i]["price"] for i in squad), 1)
    spend = {}
    for pos in SQUAD:
        spend[pos] = round(sum(proj[i]["price"] for i in squad
                               if proj[i]["pos"] == pos), 1)
    return {
        "squad": squad,
        "weeks": weeks,
        "cost": cost,
        "budget": (round(budget, 1) if budget is not None else None),
        "in_bank": (round(budget - cost, 1) if budget is not None else None),
        "spend": spend,
        "score": round(evaluate(squad, proj, gws, cfg, pack_own, bb_gw, tc_gw), 2),
        "gws": list(gws),
        "optimal": optimal,
    }


def swaps(squad, proj, gws, budget, cfg, pack_own=None, bb_gw=None, tc_gw=None,
          candidates=None, depth=40):
    """For every player drafted, the closest alternative and what he costs.

    A squad with no argument attached to it is a squad you cannot correct. This
    answers, per slot: who else could stand here for the money, and how many
    points does taking him cost over the horizon.

    Exact for a single swap rather than a re-solve — it holds the other
    fourteen fixed, which is what "should I take this one instead" means when
    you are looking at a finished draft.
    """
    pack_own = pack_own or {}
    base = evaluate(squad, proj, gws, cfg, pack_own, bb_gw, tc_gw)
    cost = sum(proj[i]["price"] for i in squad)
    cand = candidates if candidates is not None else pool(proj, gws, cfg, squad)
    held = set(squad)

    out = []
    for pid in squad:
        free = budget - cost + proj[pid]["price"]
        clubs = {}
        for i in squad:
            if i != pid:
                clubs[proj[i]["team_id"]] = clubs.get(proj[i]["team_id"], 0) + 1
        alts = [q for q in cand
                if q["id"] not in held
                and q["pos"] == proj[pid]["pos"]
                and q["price"] <= free + 1e-9
                and clubs.get(q["team_id"], 0) < MAX_PER_CLUB]
        alts.sort(key=lambda q: -_horizon(q, gws))
        best, best_score = None, None
        for q in alts[:depth]:
            trial = [q["id"] if i == pid else i for i in squad]
            s = evaluate(trial, proj, gws, cfg, pack_own, bb_gw, tc_gw)
            if best_score is None or s > best_score:
                best, best_score = q["id"], s
        out.append({
            "out": pid,
            "in": best,
            # Positive means the draft is better than its nearest alternative.
            # Near zero means the slot is a coin toss and you should take the
            # player you actually want to watch.
            "gap": (round(base - best_score, 2) if best is not None else None),
        })
    out.sort(key=lambda r: (r["gap"] is None, r["gap"]))
    return out


def summarise(drafted, proj, squad_ids):
    """What changes: who survives the rebuild, who is sold, who arrives."""
    now = set(squad_ids or [])
    new = set(drafted["squad"])
    return {
        "keep": sorted(now & new, key=lambda i: -proj[i]["price"]),
        "sell": sorted(now - new, key=lambda i: -proj[i]["price"]),
        "buy": sorted(new - now, key=lambda i: -proj[i]["price"]),
    }
