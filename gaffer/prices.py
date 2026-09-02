"""Who is about to rise or fall.

FPL never published its price algorithm. This is a net-transfer heuristic
calibrated against players who already moved this gameweek, so it recalibrates
itself every week instead of relying on a hardcoded threshold."""


def calibrate(boot):
    risers = [e for e in boot["elements"] if e["cost_change_event"] > 0]
    nets = sorted(e["transfers_in_event"] - e["transfers_out_event"] for e in risers)
    if len(nets) >= 5:
        return nets[len(nets) // 10]          # 10th percentile of confirmed risers
    return max(80_000, boot.get("total_players", 10_000_000) // 100)


def forecast(boot):
    up = calibrate(boot)
    down = -up * 1.6                          # falls need a bigger flow than rises
    out = {}
    for e in boot["elements"]:
        net = e["transfers_in_event"] - e["transfers_out_event"]
        if net >= up:
            d, prox = "rise", min(1.0, net / (up * 2))
        elif net <= down:
            d, prox = "fall", min(1.0, net / (down * 2))
        else:
            d, prox = "hold", 0.0
        out[e["id"]] = {"net": net, "direction": d, "closeness": round(prox, 2)}
    return out


def squad_drift(forecasts, squad_ids):
    """Net expected team-value change tonight, in tenths of a million."""
    r = sum(1 for i in squad_ids if forecasts.get(i, {}).get("direction") == "rise")
    f = sum(1 for i in squad_ids if forecasts.get(i, {}).get("direction") == "fall")
    return r - f
