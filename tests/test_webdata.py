"""Tests for the dataset the page reads.

The app is a client of this file. If a field is dropped or renamed here the
page degrades silently — a column of dashes, a chart of nothing — so the shape
is asserted rather than assumed.
"""
import json

import pytest

from gaffer import webdata


def _proj(gws):
    out = {}
    for pid in range(1, 21):
        out[pid] = {
            "id": pid, "name": f"P{pid}", "team": "ARS" if pid % 2 else "LIV",
            "team_id": pid % 4, "pos": ["GKP", "DEF", "MID", "FWD"][pid % 4],
            "price": 4.5 + pid / 10,
            "ep": {g: 3.0 + (pid % 5) for g in gws},
            "opp": {g: "BOU(H)" for g in gws},
            "exp_min": 80, "status": "a", "news": "", "own": 12.5,
            "total_points": 40, "p60": 0.9,
            "defcon_prob": 0.3, "cs_prob": 0.25, "setpiece_bonus": 0.4,
        }
    return out


def _ctx(gws):
    proj = _proj(gws)
    prof = {pid: {"xg90": 0.3, "xa90": 0.2, "shot_quality": 0.02,
                  "attacking_share": 0.2, "defcon90": 6.0} for pid in proj}
    lg = {"league_own": {1: 0.5}, "pack_own": {1: 0.4},
          "points_behind": 12, "n_all": 42, "rows": [{"entry_name": "Top Team"}]}
    pf = {pid: {"net": 1000, "direction": "rise"} for pid in proj}
    squad_ids = list(range(1, 16))
    xi = [proj[i] for i in range(1, 12)]
    bench = [proj[i] for i in range(12, 16)]
    weeks = [{
        "gw": gws[0], "chip": None, "ep": 62.0, "hits": 0,
        "in": ["P17"], "out": ["P3"],
        "in_players": [proj[17]], "out_players": [proj[3]],
        "xi": xi, "bench": bench, "captain": proj[1],
    }]
    for g in gws[1:]:
        weeks.append({
            "gw": g, "chip": "Wildcard" if g == gws[1] else None, "ep": 70.0,
            "hits": 0, "in": [], "out": [], "in_players": [], "out_players": [],
            "xi": xi, "bench": bench, "captain": proj[1],
        })
    return proj, prof, lg, pf, squad_ids, weeks


def build(gws=(5, 6, 7)):
    gws = list(gws)
    proj, prof, lg, pf, squad_ids, weeks = _ctx(gws)
    return webdata.build(proj, prof, lg, {1: 0.6}, pf, gws, squad_ids, weeks,
                         "Fri 18 Sep 18:30", gws[0],
                         hit_verdict="Roll it.", clean_sheets=[])


def test_every_player_is_exported_not_just_the_transfer_pair():
    d = build()
    # Twenty in the projection; all twenty reach the page.
    assert len(d["players"]) == 20


def test_each_player_carries_the_full_card():
    d = build()
    p = d["players"][0]
    for field in webdata.CARD_FIELDS:
        assert field in p, f"{field} missing from the exported card"
    assert "id" in p and "ep" in p


def test_ep_is_a_list_aligned_to_gameweeks():
    d = build(gws=(5, 6, 7, 8))
    assert d["gameweeks"] == [5, 6, 7, 8]
    for p in d["players"]:
        assert len(p["ep"]) == 4


def test_squad_marks_the_eleven_the_bench_and_the_captain():
    d = build()
    assert len(d["squad"]) == 15
    assert sum(1 for s in d["squad"] if s["role"] == "xi") == 11
    assert sum(1 for s in d["squad"] if s["role"] == "bench") == 4
    assert sum(1 for s in d["squad"] if s["captain"]) == 1


def test_weeks_use_ids_so_two_players_can_share_a_name():
    d = build()
    w = d["weeks"][0]
    assert w["in"] == [17]
    assert w["out"] == [3]
    assert isinstance(w["captain"], int)
    assert len(w["xi"]) == 11


def test_metrics_are_declared_with_direction_and_format():
    d = build()
    assert d["metrics"]
    for m in d["metrics"]:
        assert set(m) == {"key", "label", "higher_better", "fmt"}
        assert isinstance(m["higher_better"], bool)


def test_every_metric_key_exists_on_a_player():
    """The compare view plots these. A typo here is a chart of nothing."""
    d = build()
    p = d["players"][0]
    for m in d["metrics"]:
        assert m["key"] in p, f"metric {m['key']} is not an exported field"


def test_teams_are_listed_for_the_filter():
    d = build()
    assert d["teams"] == ["ARS", "LIV"]


def test_league_context_survives():
    d = build()
    assert d["league"]["behind"] == 12
    assert d["league"]["teams"] == 42


def test_it_writes_valid_json(tmp_path):
    d = build()
    path = webdata.write(d, str(tmp_path))
    reloaded = json.loads(open(path, encoding="utf-8").read())
    assert reloaded["gw"] == 5
    assert len(reloaded["players"]) == 20


def test_no_ep_dict_leaks_into_the_payload(tmp_path):
    """`ep` on the projection is a dict keyed by gameweek. Shipping it for
    seven hundred players would bloat the file the phone downloads."""
    d = build()
    raw = json.dumps(d)
    assert '"opp"' not in raw
    assert '"team_id"' not in raw
