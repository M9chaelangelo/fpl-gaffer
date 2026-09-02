"""Historical data. Free, and the only way the models get to learn anything.

Source: vaastav/Fantasy-Premier-League on GitHub — every gameweek of every
season since 2016, one row per player per gameweek, including xG, xA, xGC,
price, ownership and transfer flow. That last group is what makes price-change
and herd-behaviour modelling possible at all.
"""
import io, os
import numpy as np
import pandas as pd
import requests

RAW = ("https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League"
       "/master/data/{season}/gws/merged_gw.csv")
SEASONS = ["2023-24", "2024-25", "2025-26"]
CACHE = ".cache"


def season(name, refresh=False):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{name}.csv")
    if refresh or not os.path.exists(path):
        r = requests.get(RAW.format(season=name), timeout=120)
        r.raise_for_status()
        open(path, "wb").write(r.content)
    df = pd.read_csv(path)
    df["season"] = name
    return df


def history(seasons=None, refresh=False):
    frames = []
    for s in (seasons or SEASONS):
        try:
            frames.append(season(s, refresh))
        except Exception as e:
            print(f"  skipping {s}: {e}")
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values(["season", "element", "GW"])
    return df


def panel(df):
    """Adds the next-gameweek targets the models are trying to predict."""
    g = df.groupby(["season", "element"])
    df["next_value"] = g["value"].shift(-1)
    df["next_minutes"] = g["minutes"].shift(-1)
    df["next_points"] = g["total_points"].shift(-1)
    df["price_move"] = (df["next_value"] - df["value"]).fillna(0)
    df["price_dir"] = df["price_move"].apply(
        lambda v: 1 if v > 0 else (-1 if v < 0 else 0))
    df["started"] = (df["next_minutes"] >= 60).astype(float)

    # Rolling form, computed only from the past so there is no leakage.
    for col, win in [("minutes", 4), ("total_points", 4),
                     ("expected_goal_involvements", 6), ("bps", 4)]:
        df[f"roll_{col}"] = (g[col].transform(
            lambda s: s.shift(1).rolling(win, min_periods=1).mean()))
    df["net_transfers"] = df["transfers_in"] - df["transfers_out"]
    df["net_share"] = df["net_transfers"] / df["selected"].clip(lower=1)
    g = df.groupby(["season", "element"])

    # Extra targets, all shifted so they describe the NEXT gameweek.
    df["hauled"] = (df["next_points"] >= 10).astype(float)
    df["next_bonus"] = g["bonus"].shift(-1)
    df["next_clean_sheet"] = g["clean_sheets"].shift(-1)
    df["next_net_share"] = g["net_share"].shift(-1)
    if "defensive_contribution" in df.columns:
        df["next_defcon"] = (g["defensive_contribution"].shift(-1) > 0).astype(float)
    else:
        df["next_defcon"] = np.nan

    # --- congestion and rotation features -----------------------------------
    if "kickoff_time" in df.columns:
        ko = pd.to_datetime(df["kickoff_time"], errors="coerce", utc=True)
        df["kickoff"] = ko
        df["rest_days"] = g["kickoff"].diff().dt.total_seconds() / 86400
        df["next_rest_days"] = g["rest_days"].shift(-1)
        # Three league games inside 10 days means a midweek fixture somewhere,
        # which in practice means Europe for the clubs that are in it.
        df["congested"] = (df["rest_days"] < 4.5).astype(float)
        df["next_congested"] = g["congested"].shift(-1)
    else:
        for c in ("rest_days", "next_rest_days", "congested", "next_congested"):
            df[c] = np.nan

    # --- absence / return features ------------------------------------------
    df["blank"] = (df["minutes"] == 0).astype(int)
    df["weeks_out"] = g["blank"].transform(
        lambda s: s.groupby((s != s.shift()).cumsum()).cumcount().add(1) * s)
    df["mins_before_absence"] = g["minutes"].transform(
        lambda s: s.where(s > 0).ffill().shift(1))
    df["returning"] = ((df["blank"] == 1) & (df["next_minutes"] > 0)).astype(float)

    for col, win in [("threat", 4), ("ict_index", 4), ("influence", 4),
                     ("goals_conceded", 4), ("clean_sheets", 6),
                     ("defensive_contribution", 4), ("tackles", 4),
                     ("recoveries", 4)]:
        if col in df.columns:
            df[f"roll_{col}"] = g[col].transform(
                lambda s: s.shift(1).rolling(win, min_periods=1).mean())
        else:
            df[f"roll_{col}"] = np.nan
    return df.dropna(subset=["next_value"])
