"""Expected points per player per gameweek.

Two sources, blended:
  1. Solio's public feed - a genuinely strong model, but only publishes leaders.
  2. A local fallback - shrunk points-per-90 scaled by minutes and fixture.

Never trust either blindly. `confidence` tells the report how firm a number is.
"""
DIFF = {1: 1.35, 2: 1.22, 3: 1.02, 4: 0.86, 5: 0.72}

try:
    from . import learn
except Exception:
    learn = None
try:
    from . import setpieces
except Exception:
    setpieces = None
from . import defence

GOAL_POINTS = {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4}


def _minutes_model(boot, played):
    """If a trained minutes model exists, use it for P(60+). It is the single
    biggest source of projection error, and the model beats the heuristic."""
    if learn is None:
        return None
    bundle = learn.load("minutes")
    if not bundle:
        return None
    import pandas as pd
    rows, ids = [], []
    for e in boot["elements"]:
        rows.append({"minutes": e["minutes"],
                     "roll_minutes": e["minutes"] / played,
                     "starts": e["starts"],
                     "value": e["now_cost"],
                     "roll_total_points": e["total_points"] / played})
        ids.append(e["id"])
    X = pd.DataFrame(rows)[bundle["features"]].astype(float)
    p = bundle["model"].predict_proba(X)[:, 1]
    return dict(zip(ids, p))


def _prior(price, pos):
    if pos == "GKP":
        return 3.2 + (price - 4.0) * 0.50
    if pos == "DEF":
        return 2.6 + (price - 4.0) * 0.90
    if pos == "MID":
        return 2.4 + (price - 4.5) * 0.75
    return 2.6 + (price - 4.5) * 0.55


def _availability(e):
    if e["status"] in ("i", "u", "s", "n"):
        return 0.0
    c = e.get("chance_of_playing_next_round")
    return 1.0 if c is None else c / 100.0


def team_strength(boot, prior_games=6.0):
    """Attack and defence strength from what teams have actually produced, not
    from FPL's fixture difficulty rating.

    FDR is a preseason label on a five-point scale and it does not move when a
    side starts scoring three a game. Expected goals created and conceded do."""
    xg, xgc, mins = {}, {}, {}
    for e in boot["elements"]:
        if e["minutes"] < 45:
            continue
        t = e["team"]
        xg[t] = xg.get(t, 0.0) + float(e["expected_goals"]) + \
            float(e["expected_assists"])
        mins[t] = mins.get(t, 0) + e["minutes"]
        xgc[t] = xgc.get(t, 0.0) + float(e["expected_goals_conceded_per_90"])
    games = {t: max(1.0, m / (11 * 90)) for t, m in mins.items()}
    raw_atk = {t: xg.get(t, 0.0) / games[t] for t in games}
    # Shrink toward the league mean. Two matches will cheerfully claim a side
    # creates twice the league average, and a projection that believes it
    # compounds the error across every player in that team.
    a_mean = sum(raw_atk.values()) / len(raw_atk)
    atk = {t: (games[t] * raw_atk[t] + prior_games * a_mean) / (games[t] + prior_games)
           for t in games}
    n_def = {t: xgc.get(t, 0.0) / max(1, sum(
        1 for e in boot["elements"] if e["team"] == t and e["minutes"] >= 45))
        for t in games}
    a_avg = sum(atk.values()) / len(atk)
    d_avg = sum(n_def.values()) / len(n_def)
    return ({t: v / a_avg for t, v in atk.items()},
            {t: v / d_avg for t, v in n_def.items()})


def build(boot, fixtures, gws, solio_feed=None, solio_weight=0.7,
          form_weight=0.30, strength_weight=0.5, minutes_mult=None):
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    atk, dfn = team_strength(boot)
    # Expected goals conceded per team per gameweek, calibrated against Solio.
    lams, _ = defence.lambdas(boot, fixtures, gws, atk, solio_feed)
    postypes = {p["id"]: p["singular_name_short"] for p in boot["element_types"]}
    # The 'finished' flag lags, so infer rounds played from actual minutes.
    played = max(1, round(max(e["minutes"] for e in boot["elements"]) / 90))

    p60 = _minutes_model(boot, played)

    fx = {t["id"]: {g: [] for g in gws} for t in boot["teams"]}
    for x in fixtures:
        g = x["event"]
        if g in gws:
            fx[x["team_h"]][g].append((x["team_h_difficulty"], True, x["team_a"]))
            fx[x["team_a"]][g].append((x["team_a_difficulty"], False, x["team_h"]))

    # Solio publishes name+team, so key on that.
    solio = {}
    if solio_feed:
        for key in ("topProjected", "topCaptains", "topDifferentials", "topGoals",
                    "topAssists", "topBonus", "topDefCon"):
            for r in solio_feed.get(key, []):
                k = (r["name"], r["team"])
                solio[k] = max(solio.get(k, 0.0), r.get("prPoints", 0.0))

    out = {}
    for e in boot["elements"]:
        price = e["now_cost"] / 10
        pos = postypes[e["element_type"]]
        mins = e["minutes"]
        avg_min = mins / played
        exp_min = (0.8 * avg_min + 0.2 * 90) if avg_min >= 70 else 0.85 * avg_min
        exp_min = min(90.0, exp_min) * _availability(e)
        base_exp_min = exp_min
        if p60 is not None and mins > 0:
            # Blend the heuristic with the learned start probability.
            exp_min = 0.4 * exp_min + 0.6 * (p60[e["id"]] * 82 + (1 - p60[e["id"]]) * 20)
            exp_min *= _availability(e)

        # Shrink hard early in the season; trust observed rate more as minutes accrue.
        w = min(0.55, mins / 1200)
        rate = (e["total_points"] / (mins / 90)) if mins >= 45 else _prior(price, pos)
        base = w * rate + (1 - w) * _prior(price, pos)

        # Form. FPL's `form` field is points per match over the last 30 days.
        # Against the season rate it says whether a player is trending up or
        # down — something a season total flattens away entirely.
        season_ppg = e["total_points"] / max(1, played)
        form = float(e["form"] or 0)
        if season_ppg > 0.5 and form > 0:
            ratio = max(0.6, min(1.6, form / season_ppg))
            base *= (1 - form_weight) + form_weight * ratio
        base = max(0.5, base)

        saves90 = float(e["saves_per_90"] or 0)
        defcon_p = defence.defcon_probability(e, pos)
        bps90 = e["bps"] / max(1e-9, mins / 90) if mins >= 45 else 0.0

        sol = solio.get((e["web_name"], teams[e["team"]]))
        ep, opp, conf = {}, {}, "low" if mins < 90 else "medium"
        for g in gws:
            tot, labels = 0.0, []
            lam = lams.get(e["team"], {}).get(g)
            # Congestion and European commitments cost minutes, and minutes are
            # what a projection is really made of.
            exp_min = base_exp_min * (minutes_mult.get(e["team"], {}).get(g, 1.0)
                                      if minutes_mult else 1.0)
            for (d, home, o) in fx[e["team"]][g]:
                mult = DIFF[d] * (1.045 if home else 0.955)
                # Blend the coarse fixture rating with measured strength: how
                # well this side is actually creating, and how leaky the
                # opponent actually is. A preseason FDR does not move when a
                # team starts scoring three a game; expected goals do.
                if pos in ("MID", "FWD"):
                    s = atk.get(e["team"], 1.0) * dfn.get(o, 1.0)
                else:
                    s = 1.0 / max(0.5, atk.get(o, 1.0))
                mult *= ((1 - strength_weight)
                         + strength_weight * max(0.6, min(1.7, s)))
                if pos in ("GKP", "DEF") and lam is not None:
                    # Defenders are built from components, not from a scaled
                    # points rate. Clean sheets and goals conceded are the bulk
                    # of their scoring and they are genuinely forecastable, so
                    # modelling them directly beats multiplying last month's
                    # points by a fixture rating.
                    per90 = 2.0
                    per90 += defence.defensive_points(
                        pos, lam, saves90, defcon_p)
                    per90 += (float(e["expected_goals_per_90"]) * GOAL_POINTS[pos]
                              + float(e["expected_assists_per_90"]) * 3)
                    per90 += bps90 / 34.0          # rough bonus-point yield
                    tot += per90 * (exp_min / 90)
                else:
                    tot += base * (exp_min / 90) * mult
                    if pos == "MID" and lam is not None:
                        tot += defence.clean_sheet(lam) * (exp_min / 90)
                        tot += 2.0 * defcon_p * (exp_min / 90)
                labels.append(f"{teams[o]}({'H' if home else 'A'})")
            if sol is not None and g == min(gws):
                tot = solio_weight * sol + (1 - solio_weight) * tot
                conf = "high"
            if setpieces:
                tot += setpieces.bonus_per_90(e, pos) * (exp_min / 90)
            ep[g] = round(tot, 3)
            opp[g] = "+".join(labels) if labels else "BLANK"

        out[e["id"]] = {
            "id": e["id"], "name": e["web_name"], "team": teams[e["team"]],
            "team_id": e["team"], "pos": pos, "price": price, "ep": ep, "opp": opp,
            "exp_min": round(base_exp_min), "status": e["status"], "news": e["news"],
            "own": float(e["selected_by_percent"]), "total_points": e["total_points"],
            "confidence": conf, "solio": sol,
            "p60": round(float(p60[e["id"]]), 3) if p60 is not None else None,
            "xgi90": float(e["expected_goal_involvements_per_90"]),
            "setpiece_bonus": (setpieces.bonus_per_90(e, pos)
                               if setpieces else 0.0),
            "defcon90": float(e["defensive_contribution_per_90"]),
            "defcon_prob": round(defcon_p, 3),
            "cs_prob": (round(defence.clean_sheet(lams[e["team"]][gws[0]]), 3)
                        if lams.get(e["team"], {}).get(gws[0]) else None),
            "xgc90": float(e["expected_goals_conceded_per_90"]),
        }
    return out
