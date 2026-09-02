"""The part that gets smarter over time.

Three models, each answering a question the optimiser cannot answer on its own:

  minutes  — will he actually play 60+? The single largest driver of points,
             and the thing a naive projection gets most wrong.
  price    — will he rise or fall tonight? Drives when to move, and how much
             budget the wildcard will have.
  points   — how many points, given expected minutes, xGI, defensive rate and
             fixture? Trained on outcomes rather than assumed from a prior.

Run `python -m gaffer.learn` to (re)train. Models are cached in models/ and
picked up automatically by projections.py on the next solve.
"""
import json, os
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.model_selection import GroupKFold
import joblib

from . import data

MODELS = "models"

MINUTES_X = ["minutes", "roll_minutes", "starts", "value", "roll_total_points"]
CEILING_X = ["roll_minutes", "roll_total_points", "roll_expected_goal_involvements",
             "roll_bps", "value", "was_home", "expected_goals_conceded",
             "roll_threat", "roll_ict_index"]
BONUS_X = ["roll_bps", "roll_minutes", "roll_expected_goal_involvements",
           "roll_influence", "value", "was_home"]
CS_X = ["roll_goals_conceded", "expected_goals_conceded", "was_home",
        "roll_clean_sheets", "value"]
DEFCON_X = ["roll_defensive_contribution", "roll_minutes", "roll_tackles",
            "roll_recoveries", "value"]
HERD_X = ["net_share", "roll_total_points", "selected", "value", "roll_bps"]
# How many minutes does a player actually get in his first week back, given he
# has been out? "Fit again" and "playing 90" are very different things.
RETURN_X = ["weeks_out", "mins_before_absence", "value", "roll_total_points",
            "roll_minutes"]
# Does a congested schedule cost him minutes? Rest days are the observable
# fingerprint of a midweek European tie.
ROTATION_X = ["rest_days", "next_rest_days", "congested", "roll_minutes",
              "value", "starts", "roll_total_points"]
PRICE_X = ["net_transfers", "net_share", "selected", "value",
           "roll_total_points", "transfers_balance"]
POINTS_X = ["roll_minutes", "roll_total_points", "roll_expected_goal_involvements",
            "roll_bps", "value", "was_home", "expected_goals_conceded"]


def _fit(model, df, xs, y, name, scorer):
    d = df.dropna(subset=xs + [y])
    X, Y = d[xs].astype(float), d[y]
    cv = GroupKFold(n_splits=4)
    scores = []
    for tr, te in cv.split(X, Y, groups=d["season"] + d["GW"].astype(str)):
        model.fit(X.iloc[tr], Y.iloc[tr])
        scores.append(scorer(Y.iloc[te], model, X.iloc[te]))
    model.fit(X, Y)
    os.makedirs(MODELS, exist_ok=True)
    joblib.dump({"model": model, "features": xs}, f"{MODELS}/{name}.joblib")
    return float(np.mean(scores)), len(d)


def train(seasons=None):
    print("loading history…")
    df = data.panel(data.history(seasons))
    print(f"{len(df):,} player-gameweeks")
    out = {}

    auc, n = _fit(HistGradientBoostingClassifier(max_iter=250), df, MINUTES_X,
                  "started", "minutes",
                  lambda y, m, X: roc_auc_score(y, m.predict_proba(X)[:, 1]))
    out["minutes"] = {"metric": "AUC", "value": round(auc, 3), "rows": n}

    d = df[df["price_dir"] != 0].copy()
    d["rise"] = (d["price_dir"] > 0).astype(int)
    auc, n = _fit(HistGradientBoostingClassifier(max_iter=250), d, PRICE_X,
                  "rise", "price",
                  lambda y, m, X: roc_auc_score(y, m.predict_proba(X)[:, 1]))
    out["price"] = {"metric": "AUC", "value": round(auc, 3), "rows": n}

    mae, n = _fit(HistGradientBoostingRegressor(max_iter=300), df, POINTS_X,
                  "next_points", "points",
                  lambda y, m, X: -mean_absolute_error(y, m.predict(X)))
    out["points"] = {"metric": "MAE", "value": round(-mae, 3), "rows": n}

    # Captaincy is not about the average. It is about the tail: how likely is a
    # double-digit haul? Expected points and ceiling rank players differently,
    # and the Triple Captain chip only cares about the second one.
    auc, n = _fit(HistGradientBoostingClassifier(max_iter=250), df, CEILING_X,
                  "hauled", "ceiling",
                  lambda y, m, X: roc_auc_score(y, m.predict_proba(X)[:, 1]))
    out["ceiling"] = {"metric": "AUC", "value": round(auc, 3), "rows": n,
                      "target": "P(10+ points next gameweek)"}

    mae, n = _fit(HistGradientBoostingRegressor(max_iter=200), df, BONUS_X,
                  "next_bonus", "bonus",
                  lambda y, m, X: -mean_absolute_error(y, m.predict(X)))
    out["bonus"] = {"metric": "MAE", "value": round(-mae, 3), "rows": n}

    dd = df[df["position"].isin(["DEF", "GK", "GKP"])]
    auc, n = _fit(HistGradientBoostingClassifier(max_iter=200), dd, CS_X,
                  "next_clean_sheet", "cleansheet",
                  lambda y, m, X: roc_auc_score(y, m.predict_proba(X)[:, 1]))
    out["cleansheet"] = {"metric": "AUC", "value": round(auc, 3), "rows": n}

    dc = df.dropna(subset=["roll_defensive_contribution"])
    if len(dc) > 2000 and dc["next_defcon"].nunique() > 1:
        auc, n = _fit(HistGradientBoostingClassifier(max_iter=200), dc, DEFCON_X,
                      "next_defcon", "defcon",
                      lambda y, m, X: roc_auc_score(y, m.predict_proba(X)[:, 1]))
        out["defcon"] = {"metric": "AUC", "value": round(auc, 3), "rows": n,
                         "target": "P(hits DefCon threshold)"}

    # Herd momentum: who the crowd buys next. Drives price moves and, in a
    # mini-league, tells you which differentials are about to stop being ones.
    mae, n = _fit(HistGradientBoostingRegressor(max_iter=200), df, HERD_X,
                  "next_net_share", "herd",
                  lambda y, m, X: -mean_absolute_error(y, m.predict(X)))
    out["herd"] = {"metric": "MAE", "value": round(-mae, 4), "rows": n,
                   "target": "next gameweek net transfers as share of owners"}

    # The number that matters: does the model beat "he'll score what he averaged"?
    base = df.dropna(subset=["roll_total_points", "next_points"])
    naive = mean_absolute_error(base["next_points"], base["roll_total_points"])
    out["points"]["naive_baseline_mae"] = round(float(naive), 3)
    out["points"]["beats_baseline"] = bool(-mae < naive)

    # Injury return: rows where the player blanked, predicting next minutes.
    ret = df[(df["blank"] == 1) & df["mins_before_absence"].notna()]
    if len(ret) > 3000:
        mae, n = _fit(HistGradientBoostingRegressor(max_iter=200), ret, RETURN_X,
                      "next_minutes", "injury_return",
                      lambda y, m, X: -mean_absolute_error(y, m.predict(X)))
        out["injury_return"] = {"metric": "MAE (minutes)", "value": round(-mae, 1),
                                "rows": n, "target": "minutes in the week back"}

    rot = df.dropna(subset=["rest_days", "next_rest_days"])
    if len(rot) > 5000:
        mae, n = _fit(HistGradientBoostingRegressor(max_iter=200), rot, ROTATION_X,
                      "next_minutes", "rotation",
                      lambda y, m, X: -mean_absolute_error(y, m.predict(X)))
        out["rotation"] = {"metric": "MAE (minutes)", "value": round(-mae, 1),
                           "rows": n, "target": "minutes under fixture congestion"}

    json.dump(out, open(f"{MODELS}/scores.json", "w"), indent=1)
    for k, v in out.items():
        print(f"  {k:8} {v}")
    return out


def load(name):
    p = f"{MODELS}/{name}.joblib"
    return joblib.load(p) if os.path.exists(p) else None


if __name__ == "__main__":
    train()
