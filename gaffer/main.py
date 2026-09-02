"""Run the gaffer. `python -m gaffer.main` — everything else is automatic."""
import argparse, json, os, sys
from datetime import datetime, timezone

import yaml

from . import (fetch, league, projections, prices, optimise, report, timing,
               styles, elite, explain, defence, calibrate, rotation)


def purchase_prices(boot, entry_id, squad_ids):
    """Rebuild what you paid, so selling prices are right."""
    els = {e["id"]: e for e in boot["elements"]}
    paid = {i: (els[i]["now_cost"] - els[i]["cost_change_start"]) / 10
            for i in squad_ids if i in els}
    try:
        for t in reversed(fetch.transfers(entry_id)):
            if t["element_in"] in paid:
                paid[t["element_in"]] = t["element_in_cost"] / 10
    except Exception:
        pass
    return paid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--free-transfers", default=None)
    ap.add_argument("--only-on-deadline-day", action="store_true",
                    help="exit quietly unless a deadline falls today")
    args = ap.parse_args()
    cfg = yaml.safe_load(open(args.config))

    print("fetching…")
    boot = fetch.bootstrap()
    fx = fetch.fixtures()
    gw = fetch.current_gw(boot)
    gws = [g for g in range(gw, gw + cfg["horizon"])
           if any(e["id"] == g for e in boot["events"])]
    ev = next(e for e in boot["events"] if e["id"] == gw)
    deadline = datetime.fromisoformat(
        ev["deadline_time"].replace("Z", "+00:00")).strftime("%a %d %b %H:%M UTC")

    if args.only_on_deadline_day:
        d = datetime.fromisoformat(ev["deadline_time"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        hours = (d - now).total_seconds() / 3600
        state_path = os.path.join(cfg["out_dir"], "state.json")
        try:
            done = json.load(open(state_path)).get("solved_gw")
        except Exception:
            done = None
        # FPL can move a deadline, but never within 24 hours of it. So: always
        # solve on the day, and also solve early if this gameweek has no plan yet
        # and the deadline is close. That way a deadline shifting onto a Sunday
        # or a Tuesday cannot slip past us.
        if d.date() != now.date() and not (done != gw and 0 < hours < 72):
            print(f"nothing due — GW{gw} closes {d:%a %d %b %H:%M} UTC "
                  f"({hours:.0f}h away, plan on file for GW{done})")
            return
    print(f"gameweek {gw}, planning {gws}")
    feed = fetch.solio(cfg["solio_url"])
    mins_mult = rotation.congestion(
        boot, cfg.get("european_teams", ()), cfg.get("european_weeks", ()),
        cfg.get("european_haircut", 0.12), cfg.get("midweek_haircut", 0.06))
    proj = projections.build(boot, fx, gws, feed, cfg["solio_weight"],
                             cfg.get("form_weight", 0.30),
                             cfg.get("strength_weight", 0.5), mins_mult)
    if cfg.get("calibrate_to_solio", True):
        scale, n = calibrate.fit(proj, feed, gw)
        if n:
            print(f"  calibration vs Solio: x{scale:.3f} on {n} shared players")
        proj = calibrate.apply(proj, scale, gws)

    last = gw - 1
    my = fetch.picks(cfg["entry_id"], last)
    squad_ids = [p["element"] for p in my["picks"]]
    bank = my["entry_history"]["bank"] / 10

    # FPL's public API shows last gameweek's squad and does not expose transfers
    # you have already made for the upcoming one. If you have moved this week,
    # list the current fifteen in config as `current_squad` — otherwise the
    # solver plans from a team you no longer own.
    override = cfg.get("current_squad")
    if override:
        by_name = {}
        for i, p in proj.items():
            by_name.setdefault(p["name"].lower(), []).append(i)
        resolved, missing = [], []
        for nm in override:
            hit = by_name.get(str(nm).lower())
            if hit:
                resolved.append(max(hit, key=lambda i: proj[i]["total_points"]))
            else:
                missing.append(nm)
        if missing:
            print(f"  !! could not resolve in current_squad: {missing}")
        if len(resolved) == 15:
            gone = [proj[i]["name"] for i in squad_ids if i not in resolved]
            added = [proj[i]["name"] for i in resolved if i not in squad_ids]
            if gone or added:
                print(f"  using current_squad override (out: {gone}, in: {added})")
            bank = float(cfg.get("bank", bank))
            squad_ids = resolved
        else:
            print(f"  !! current_squad has {len(resolved)} valid names, need 15 — "
                  f"falling back to the API squad")
    ft = int(args.free_transfers) if (args.free_transfers or "").strip() \
        else cfg.get("free_transfers", 1)

    paid = purchase_prices(boot, cfg["entry_id"], squad_ids)
    sell = {i: optimise.selling_price(paid.get(i, proj[i]["price"]), proj[i]["price"])
            for i in squad_ids}

    print("reading your mini-league…")
    lg = league.snapshot(cfg["league_id"], cfg["entry_id"], last,
                         cfg.get("rival_depth", 10))

    cal = timing.calendar(boot)

    # Anyone injured, suspended or gone. The solver already refuses to start
    # them; this decides whether they deserve a squad slot at all.
    flagged = []
    for i in squad_ids:
        p = proj[i]
        if p["status"] == "a":
            continue
        horizon_ep = sum(p["ep"][g] for g in gws)
        flagged.append({
            "name": p["name"], "status": p["status"], "news": p["news"],
            "ep": p["ep"][gw],
            "verdict": ("sell — no return inside the horizon" if horizon_ep < 4
                        else "hold — he is back before this plan ends"),
        })

    # A locked chip plan. Once you have decided, the weekly run should execute
    # that decision rather than re-litigating it every deadline on three more
    # days of noise.
    plan_chips = cfg.get("chip_plan") or {}
    forced = None
    forced_wc = plan_chips.get("wc") if plan_chips.get("wc") in gws else None
    for which in ("tc", "bb", "fh"):
        if plan_chips.get(which) in gws:
            forced = (which, plan_chips[which])
            break
    if plan_chips:
        pending = {k: v for k, v in plan_chips.items() if v in gws}
        print(f"  chip plan in force: {plan_chips}"
              + (f" — active this horizon: {pending}" if pending else ""))

    print("solving…")
    weeks = optimise.plan(proj, squad_ids, sell, bank, gws, ft, cfg,
                          lg["pack_own"], calendar=cal,
                          force_wc_gw=forced_wc, force_chip=forced)
    gain, _ = optimise.value_of_hit(proj, squad_ids, sell, bank, gws, ft, cfg,
                                    lg["pack_own"], weeks, cal)
    thr = cfg.get("hit_threshold", 6.0)
    verdict = (f"Taking a hit gains about {gain} points over {len(gws)} gameweeks. "
               + ("Worth it." if gain >= thr else
                  f"Not worth it — the bar is {thr}. Roll the transfer instead."))

    atk, _ = projections.team_strength(boot)
    lams, tmn = defence.lambdas(boot, fx, gws, atk, fetch.solio(cfg["solio_url"]))
    cs_table = defence.table(boot, lams, tmn, gw, limit=12)

    prof = styles.profile(boot)
    try:
        el = elite.snapshot(last, top_n=cfg.get("elite_sample", 100))
        elite_own = el["own"]
    except Exception as e:
        print(f"  elite sample unavailable ({e})")
        elite_own = {}

    pf = prices.forecast(boot)
    watch = sorted(
        [{"name": proj[i]["name"],
          "where": "your squad" if i in squad_ids else "target",
          "net": pf[i]["net"], "direction": pf[i]["direction"]}
         for i in proj if pf[i]["direction"] != "hold"
         and (i in squad_ids or proj[i]["own"] > 3)],
        key=lambda r: -abs(r["net"]))

    gems = sorted(
        [{"name": p["name"], "team": p["team"], "price": p["price"],
          "proj": p["ep"][gw], "league": lg["league_own"].get(i, 0.0),
          "pack": lg["pack_own"].get(i, 0.0)}
         for i, p in proj.items()
         if lg["league_own"].get(i, 0.0) <= 0.10 and i not in squad_ids
         and p["exp_min"] >= 60 and p["status"] == "a"],
        key=lambda g: -g["proj"])

    behind = lg["points_behind"]
    line = (f"You are {behind} points off the top of {lg['rows'][0]['entry_name']} "
            f"in a {lg['n_all']}-team league." if behind is not None else "")

    rationale = []
    for w in weeks:
        rationale.append({
            "gw": w["gw"], "chip": w["chip"],
            "captain": explain.captain(w, proj, prof, lg["pack_own"], elite_own, gws),
            "transfers": explain.transfers(w, proj, prof, lg["league_own"],
                                           lg["pack_own"], elite_own, pf, gws),
        })

    os.makedirs(cfg["out_dir"], exist_ok=True)
    out = os.path.join(cfg["out_dir"], "index.html")
    report.render({"weeks": weeks, "deadline": deadline, "gems": gems,
                   "prices": watch, "hit_verdict": verdict, "flagged": flagged,
                   "pack_own": lg["pack_own"], "league_line": line,
                   "rationale": rationale, "clean_sheets": cs_table}, out)
    json.dump({"gw": gw, "generated": datetime.now(timezone.utc).isoformat(),
               "weeks": [{k: v for k, v in w.items()
                          if k in ("gw", "in", "out", "hits", "chip", "ep")}
                         for w in weeks],
               "hit_verdict": verdict, "gems": gems[:20],
               "rationale": rationale},
              open(os.path.join(cfg["out_dir"], "plan.json"), "w"), indent=1)
    json.dump({"solved_gw": gw, "deadline": ev["deadline_time"],
               "solved_at": datetime.now(timezone.utc).isoformat()},
              open(os.path.join(cfg["out_dir"], "state.json"), "w"), indent=1)
    print(f"wrote {out}; next deadline GW{gw} {deadline}")


if __name__ == "__main__":
    main()
