"""Tests for the GM Chat's trade-engine tools."""

import json

import pandas as pd
import pytest

from src import chat_tools as ct
from src import trade_engine


@pytest.fixture
def ctx():
    return ct.ToolContext(team="GB", rosters=trade_engine.DEMO_ROSTERS)


def test_every_definition_has_a_runner_and_eager_streaming():
    names = [t["name"] for t in ct.TOOL_DEFINITIONS]
    assert sorted(names) == sorted(ct._TOOLS)
    for t in ct.TOOL_DEFINITIONS:
        assert t["eager_input_streaming"] is True
        assert set(t["input_schema"]["required"]) <= set(t["input_schema"]["properties"])


def test_lookup_own_player_includes_verdict_and_cap(ctx):
    (p,) = ct.run(ctx, "lookup_player", {"name": "Parsons"})["players"]
    assert p["Name"] == "M. Parsons" and p["verdict"] == "KEEP"
    assert p["dead_cap_if_moved_M"] == 105.0 and p["trade_value"] > 1000
    json.dumps(p)  # must be serialisable for the tool_result


def test_lookup_other_team_player_has_no_verdict(ctx):
    (p,) = ct.run(ctx, "lookup_player", {"name": "justin jefferson"})["players"]
    assert p["Team"] == "MIN" and "verdict" not in p


def test_lookup_falls_back_to_last_name(ctx):
    # Roster stores "M. Parsons"; users type full names.
    (p,) = ct.run(ctx, "lookup_player", {"name": "Micah Parsons"})["players"]
    assert p["Name"] == "M. Parsons"


def test_unknown_player_is_an_error_not_an_exception(ctx):
    assert "No player matching" in ct.run(ctx, "lookup_player", {"name": "Zzyzx"})["error"]


def test_targets_exclude_own_team_and_sort_by_value(ctx):
    res = ct.run(ctx, "list_trade_targets", {"position": "edge", "min_ovr": 85})
    teams = {t["Team"] for t in res["targets"]}
    assert "GB" not in teams and teams <= {"DET", "CHI", "MIN"}
    vals = [t["trade_value"] for t in res["targets"]]
    assert vals == sorted(vals, reverse=True) and res["teams_modeled"] == ["CHI", "DET", "MIN"]


def test_targets_filters_can_empty_the_list(ctx):
    res = ct.run(ctx, "list_trade_targets", {"position": "EDGE", "max_age": 20})
    assert res["targets"] == [] and "No EDGE" in res["note"]


def test_evaluate_trade_matches_the_engine(ctx):
    res = ct.run(ctx, "evaluate_trade", {"offer": ["J. Jacobs"], "request": ["Justin Jefferson"]})
    assert "DECLINED" in res["verdict"] and res["requested_value"] > res["offered_value"]
    assert "Round Pick" in res["counter_offer"]


def test_evaluate_trade_rejects_wrong_sides(ctx):
    res = ct.run(ctx, "evaluate_trade", {"offer": ["Justin Jefferson"], "request": ["M. Parsons"]})
    assert "only your own players" in res["error"] and "already on GB" in res["error"]


def test_ambiguous_name_asks_for_more(ctx):
    res = ct.run(ctx, "evaluate_trade", {"offer": ["J."], "request": ["Justin Jefferson"]})
    assert "matches several players" in res["error"]


def test_trade_partners_for_own_player_only(ctx):
    res = ct.run(ctx, "find_trade_partners", {"name": "A. Robinson"})
    assert {p["team"] for p in res["partners"]} == {"DET", "CHI", "MIN"}
    assert "pick one of your own" in ct.run(ctx, "find_trade_partners", {"name": "Jefferson"})["error"]


def test_session_players_are_visible(ctx):
    ctx.extra_players = [{"Name": "Rookie Guy", "Pos": "WR", "OVR": 72, "Age": 21,
                          "Dev": "Star", "Team": "GB", "_id": "x"}]
    (p,) = ct.run(ctx, "lookup_player", {"name": "Rookie Guy"})["players"]
    assert p["Team"] == "GB" and "_id" not in p


@pytest.mark.parametrize("name,args,msg", [
    ("nope", {}, "Unknown tool"),
    ("lookup_player", "Parsons", "JSON object"),
    ("lookup_player", {}, "Missing required"),
    ("lookup_player", {"name": "  "}, "non-empty"),
    ("lookup_player", {"name": "x", "extra": 1}, "Unexpected"),
    ("list_trade_targets", {"position": "WR", "min_ovr": "80"}, "integer"),
    ("list_trade_targets", {"position": "WR", "min_ovr": True}, "integer"),
    ("evaluate_trade", {"offer": [], "request": ["x"]}, None),
    ("evaluate_trade", {"offer": ["a", 3], "request": ["x"]}, "list of player names"),
])
def test_validation(name, args, msg):
    err = ct.validate(name, args)
    assert (err is None) if msg is None else (msg in err)


def test_run_never_raises(ctx, monkeypatch):
    monkeypatch.setattr(ct, "_match", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    assert "failed: boom" in ct.run(ctx, "lookup_player", {"name": "x"})["error"]


def test_empty_offer_side_is_reported(ctx):
    assert "each side" in ct.run(ctx, "evaluate_trade", {"offer": [], "request": ["Justin Jefferson"]})["error"]


def test_nan_cells_serialise_as_null():
    assert ct._record(pd.Series({"a": float("nan"), "b": 1}))["a"] is None


def test_cpu_player_lookup_is_strict_json(ctx):
    res = ct.run(ctx, "lookup_player", {"name": "Justin Jefferson"})
    json.dumps(res, allow_nan=False)
