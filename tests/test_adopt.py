"""One wildcard on the page, not two.

The weekly model and the drafter both answer "what do I buy on my wildcard",
and they disagree — on GW6 they differed by four of fifteen. Both answers were
rendered, each labelled the wildcard, and nothing said which one to buy. That
is the worst shape a disagreement can take: it does not look like one.

These tests are about the splice. They check that the plan really does become
the drafted squad from the chip week onwards, that the weeks before it are left
alone, and — the part that matters most — that it refuses to splice at all when
the two are talking about different gameweeks.
"""
from gaffer import wildcard

from tests.test_wildcard import CFG, league


def _week(gw, squad, proj, chip=None, ins=(), outs=(), hits=0):
    """A weekly-plan week, in the shape `optimise.plan` returns."""
    xi = sorted(squad[:11], key=lambda i: -proj[i]["ep"][gw])
    return {
        "gw": gw,
        "in": [proj[i]["name"] for i in ins],
        "out": [proj[i]["name"] for i in outs],
        "in_players": [proj[i] for i in ins],
        "out_players": [proj[i] for i in outs],
        "hits": hits,
        "chip": chip,
        "xi": [proj[i] for i in xi],
        "bench": [proj[i] for i in squad[11:]],
        "captain": proj[xi[0]],
        "ep": 50.0,
    }


def _draft(squad, gws, proj, for_gw, chip_by_gw=None):
    """A drafter result, in the shape `wildcard.finish` returns."""
    chip_by_gw = chip_by_gw or {}
    return {
        "for_gw": for_gw,
        "squad": list(squad),
        "gws": list(gws),
        "weeks": [{
            "gw": g,
            "xi": list(squad[:11]),
            "bench": list(squad[11:]),
            "formation": "4-4-2",
            "captain": squad[0],
            "chip": chip_by_gw.get(g),
            "ep": 60.0 + g,
        } for g in gws],
    }


def _ids(week):
    return sorted(p["id"] for p in week["xi"] + week["bench"])


def _fixture(gws=(1, 2, 3)):
    proj = league(gws=gws)
    ids = sorted(proj)
    mine, theirs = ids[:15], ids[20:35]
    return proj, mine, theirs


def test_the_plan_becomes_the_drafted_squad_from_the_chip_week():
    """The bug this file exists for."""
    proj, mine, theirs = _fixture()
    weeks = [_week(1, mine, proj, chip="Wildcard"),
             _week(2, mine, proj), _week(3, mine, proj)]
    draft = _draft(theirs, (1, 2, 3), proj, for_gw=1)

    out = wildcard.adopt(weeks, draft, proj, mine)
    for w in out:
        assert _ids(w) == sorted(theirs), \
            f"GW{w['gw']} still shows the weekly model's fifteen"


def test_weeks_before_the_chip_are_left_alone():
    """A wildcard in GW2 says nothing about what you play in GW1."""
    proj, mine, theirs = _fixture()
    weeks = [_week(1, mine, proj), _week(2, mine, proj, chip="Wildcard"),
             _week(3, mine, proj)]
    draft = _draft(theirs, (2, 3), proj, for_gw=2)

    out = wildcard.adopt(weeks, draft, proj, mine)
    assert out[0] is weeks[0], "the week before the chip was rewritten"
    assert _ids(out[1]) == sorted(theirs)
    assert _ids(out[2]) == sorted(theirs)


def test_the_chip_week_reports_the_whole_rebuild_as_its_moves():
    """Thirteen in and thirteen out is what a wildcard is. Showing the weekly
    model's one-for-one there would describe a transfer nobody makes."""
    proj, mine, theirs = _fixture()
    weeks = [_week(1, mine, proj, chip="Wildcard")]
    draft = _draft(theirs, (1, 2, 3), proj, for_gw=1)

    out = wildcard.adopt(weeks, draft, proj, mine)[0]
    bought = {p["id"] for p in out["in_players"]}
    sold = {p["id"] for p in out["out_players"]}
    assert bought == set(theirs) - set(mine)
    assert sold == set(mine) - set(theirs)
    assert out["in"] == [p["name"] for p in out["in_players"]]
    assert out["hits"] == 0, "a wildcard does not cost points"


def test_nothing_moves_after_the_rebuild():
    """The drafter scored its horizon holding the fifteen fixed. A plan that
    kept transferring would be reporting a number nobody computed."""
    proj, mine, theirs = _fixture()
    weeks = [_week(1, mine, proj, chip="Wildcard"),
             _week(2, mine, proj, ins=[mine[0]], outs=[mine[1]], hits=1),
             _week(3, mine, proj)]
    draft = _draft(theirs, (1, 2, 3), proj, for_gw=1)

    out = wildcard.adopt(weeks, draft, proj, mine)
    for w in out[1:]:
        assert w["in_players"] == [] and w["out_players"] == []
        assert w["hits"] == 0


def test_a_draft_for_another_gameweek_is_refused():
    """The one case where doing nothing is right. A GW3 rebuild spliced into a
    GW1 wildcard would stop looking like two answers and start looking like
    one — which is worse, because then nobody checks."""
    proj, mine, theirs = _fixture()
    weeks = [_week(1, mine, proj, chip="Wildcard"), _week(2, mine, proj)]
    draft = _draft(theirs, (3,), proj, for_gw=3)

    assert wildcard.adopt(weeks, draft, proj, mine) is weeks


def test_a_plan_with_no_wildcard_week_is_untouched():
    proj, mine, theirs = _fixture()
    weeks = [_week(1, mine, proj), _week(2, mine, proj, chip="Bench Boost")]
    draft = _draft(theirs, (1, 2), proj, for_gw=1)

    assert wildcard.adopt(weeks, draft, proj, mine) is weeks


def test_no_draft_at_all_is_untouched():
    proj, mine, _ = _fixture()
    weeks = [_week(1, mine, proj, chip="Wildcard")]
    assert wildcard.adopt(weeks, None, proj, mine) is weeks
    assert wildcard.adopt([], _draft(mine, (1,), proj, 1), proj, mine) == []


def test_a_draft_that_stops_short_of_the_plan_is_refused():
    """Half a spliced plan is the one outcome worse than leaving both up."""
    proj, mine, theirs = _fixture()
    weeks = [_week(1, mine, proj, chip="Wildcard"), _week(2, mine, proj),
             _week(3, mine, proj)]
    draft = _draft(theirs, (1, 2), proj, for_gw=1)      # no GW3

    assert wildcard.adopt(weeks, draft, proj, mine) is weeks


def test_the_week_carries_the_drafters_points_and_captain():
    """`ep` has to come from the drafter too. Keeping the weekly model's number
    on the drafter's eleven would report a score for a squad that was never
    played."""
    proj, mine, theirs = _fixture()
    weeks = [_week(1, mine, proj, chip="Wildcard")]
    draft = _draft(theirs, (1, 2, 3), proj, for_gw=1)

    out = wildcard.adopt(weeks, draft, proj, mine)[0]
    assert out["ep"] == 61.0
    assert out["captain"]["id"] == theirs[0]
    assert out["chip"] == "Wildcard"


def test_the_eleven_is_ordered_by_points_like_the_weekly_model():
    """The report draws the pitch straight off this order."""
    proj, mine, theirs = _fixture()
    weeks = [_week(1, mine, proj, chip="Wildcard")]
    draft = _draft(theirs, (1, 2, 3), proj, for_gw=1)

    xi = wildcard.adopt(weeks, draft, proj, mine)[0]["xi"]
    eps = [p["ep"][1] for p in xi]
    assert eps == sorted(eps, reverse=True)


def test_a_chip_in_a_later_week_survives_the_splice():
    """The drafter was told where the Triple Captain goes; the plan says so
    too. Losing the label would make the week's points look inexplicable."""
    proj, mine, theirs = _fixture()
    weeks = [_week(1, mine, proj, chip="Wildcard"),
             _week(2, mine, proj, chip="Triple Captain"), _week(3, mine, proj)]
    draft = _draft(theirs, (1, 2, 3), proj, for_gw=1,
                   chip_by_gw={2: "Triple Captain"})

    out = wildcard.adopt(weeks, draft, proj, mine)
    assert [w["chip"] for w in out] == ["Wildcard", "Triple Captain", None]


def test_the_input_is_not_modified():
    proj, mine, theirs = _fixture()
    weeks = [_week(1, mine, proj, chip="Wildcard"), _week(2, mine, proj)]
    before = [_ids(w) for w in weeks]
    wildcard.adopt(weeks, _draft(theirs, (1, 2, 3), proj, 1), proj, mine)
    assert [_ids(w) for w in weeks] == before


def test_transfers_before_the_chip_decide_what_is_sold():
    """If the plan already moved someone out in GW1, he is not yours to sell on
    the GW2 wildcard. The comparison is the week before the chip, not today."""
    proj, mine, theirs = _fixture()
    ids = sorted(proj)
    swapped = mine[:-1] + [ids[60]]          # GW1 brings in a player you lack
    weeks = [_week(1, swapped, proj, ins=[ids[60]], outs=[mine[-1]]),
             _week(2, swapped, proj, chip="Wildcard")]
    draft = _draft(theirs, (2, 3), proj, for_gw=2)

    out = wildcard.adopt(weeks, draft, proj, mine)[1]
    sold = {p["id"] for p in out["out_players"]}
    assert mine[-1] not in sold, "sold a player the plan had already moved on"
    assert ids[60] in sold, "kept a player the rebuild does not buy"
