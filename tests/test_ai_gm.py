"""Tests for the AI GM Assistant's deterministic scouting engine.

Uses a team name ("TESTTEAM") that doesn't exist in the real roster CSV,
combined with explicit `extra_players`, so every test is fully isolated
from the actual data/packers_roster.csv content instead of depending on
whatever players happen to be on GB's roster today.
"""

from src import ai_gm

TEAM = "TESTTEAM"


def _player(**overrides) -> dict:
    base = {"Name": "Test Player", "Pos": "WR", "Age": 25, "OVR": 78, "Dev": "Normal"}
    base.update(overrides)
    return base


def _roster_of(pos: str, count: int, ovr: int) -> list[dict]:
    """`count` extra players at `pos` with the given OVR, for TEAM."""
    return [
        {"Name": f"Filler {i}", "Pos": pos, "Age": 26, "OVR": ovr,
         "Dev": "Normal", "Team": TEAM}
        for i in range(count)
    ]


class TestValidatePlayer:
    def test_valid_player_has_no_errors(self):
        assert ai_gm.validate_player(_player()) == []

    def test_missing_name(self):
        errors = ai_gm.validate_player(_player(Name=""))
        assert any("Name" in e for e in errors)

    def test_missing_position(self):
        errors = ai_gm.validate_player(_player(Pos=""))
        assert any("Position" in e for e in errors)

    def test_unrecognized_position(self):
        errors = ai_gm.validate_player(_player(Pos="XYZ"))
        assert any("Unrecognized position" in e for e in errors)

    def test_lowercase_normalizable_position_is_valid(self):
        # "redg" normalizes to EDGE, which is scoutable — should pass.
        errors = ai_gm.validate_player(_player(Pos="redg"))
        assert errors == []

    def test_ovr_out_of_range(self):
        errors = ai_gm.validate_player(_player(OVR=150))
        assert any("OVR" in e for e in errors)

    def test_ovr_non_numeric(self):
        errors = ai_gm.validate_player(_player(OVR="not-a-number"))
        assert any("OVR" in e for e in errors)

    def test_age_out_of_range(self):
        errors = ai_gm.validate_player(_player(Age=10))
        assert any("Age" in e for e in errors)

    def test_attribute_out_of_range(self):
        errors = ai_gm.validate_player(_player(SPD=999))
        assert any("SPD" in e for e in errors)

    def test_blank_attribute_is_allowed(self):
        errors = ai_gm.validate_player(_player(SPD=""))
        assert errors == []


class TestNormalizePlayer:
    def test_assigns_a_unique_id_per_call(self):
        p1 = ai_gm.normalize_player(_player(), TEAM)
        p2 = ai_gm.normalize_player(_player(), TEAM)
        assert p1["_id"] != p2["_id"]

    def test_coerces_types_and_normalizes_position(self):
        normalized = ai_gm.normalize_player(_player(Pos="redg", Age="24", OVR="80"), TEAM)
        assert normalized["Pos"] == "EDGE"
        assert normalized["Age"] == 24 and isinstance(normalized["Age"], int)
        assert normalized["OVR"] == 80 and isinstance(normalized["OVR"], int)
        assert normalized["Team"] == TEAM

    def test_fills_in_defaults(self):
        normalized = ai_gm.normalize_player(_player(Dev=None), TEAM)
        assert normalized["Dev"] == "Normal"
        assert normalized["Savings"] == "$0"
        assert normalized["Penalty"] == "$0"
        assert normalized["Scheme"] == "WestCoast"


class TestAddPlayer:
    def test_valid_player_returns_ok_and_normalized_player(self):
        result = ai_gm.add_player(_player(), TEAM)
        assert result["ok"] is True
        assert result["errors"] == []
        assert result["player"]["Name"] == "Test Player"

    def test_invalid_player_returns_errors_and_no_player(self):
        result = ai_gm.add_player(_player(Name=""), TEAM)
        assert result["ok"] is False
        assert result["errors"]
        assert result["player"] is None


class TestRemoveFromList:
    def test_removes_only_the_matching_id(self):
        players = [
            {"_id": "a", "Name": "Same Name"},
            {"_id": "b", "Name": "Same Name"},
        ]
        result = ai_gm.remove_from_list(players, "a")
        assert len(result) == 1
        assert result[0]["_id"] == "b"

    def test_missing_id_is_a_no_op(self):
        players = [{"_id": "a", "Name": "X"}]
        assert ai_gm.remove_from_list(players, "does-not-exist") == players


class TestPositionalNeeds:
    def test_empty_position_is_critical(self):
        needs = {n["pos"]: n for n in ai_gm.positional_needs(TEAM, [])}
        assert needs["QB"]["level"] == "Critical"
        assert needs["QB"]["count"] == 0

    def test_single_weak_starter_is_critical(self):
        extra = _roster_of("CB", count=1, ovr=70)
        needs = {n["pos"]: n for n in ai_gm.positional_needs(TEAM, extra)}
        assert needs["CB"]["level"] == "Critical"

    def test_deep_strong_room_is_set(self):
        extra = _roster_of("WR", count=4, ovr=85)
        needs = {n["pos"]: n for n in ai_gm.positional_needs(TEAM, extra)}
        assert needs["WR"]["level"] == "Set"

    def test_two_deep_is_moderate_even_if_strong(self):
        extra = _roster_of("TE", count=2, ovr=90)
        needs = {n["pos"]: n for n in ai_gm.positional_needs(TEAM, extra)}
        assert needs["TE"]["level"] == "Moderate"


class TestScoutPlayerVerdicts:
    def test_fills_critical_need(self):
        # No existing players at all -> every position is Critical.
        report = ai_gm.scout_player(_player(Pos="WR", OVR=70, Age=30), TEAM, [])
        assert report["verdict"] == "SIGN — Fills Critical Need"

    def test_upgrades_a_set_starting_room(self):
        extra = _roster_of("WR", count=3, ovr=80)  # -> "Set"
        report = ai_gm.scout_player(_player(Pos="WR", OVR=85, Age=27), TEAM, extra)
        assert report["verdict"] == "SIGN & START"

    def test_young_dev_talent_gets_stashed(self):
        extra = _roster_of("WR", count=3, ovr=85)  # -> "Set", high bar to "start"
        report = ai_gm.scout_player(
            _player(Pos="WR", OVR=80, Age=21, Dev="Superstar"), TEAM, extra)
        assert report["verdict"] == "SIGN & DEVELOP"

    def test_average_depth_piece(self):
        extra = _roster_of("WR", count=3, ovr=85)
        report = ai_gm.scout_player(
            _player(Pos="WR", OVR=75, Age=28, Dev="Normal"), TEAM, extra)
        assert report["verdict"] == "ROTATIONAL DEPTH"

    def test_below_replacement_is_a_pass(self):
        extra = _roster_of("WR", count=3, ovr=85)
        report = ai_gm.scout_player(
            _player(Pos="WR", OVR=68, Age=28, Dev="Normal"), TEAM, extra)
        assert report["verdict"] == "PASS"

    def test_elite_and_weak_attributes_are_labeled(self):
        report = ai_gm.scout_player(
            _player(SPD=95, STR=50), TEAM, [])
        assert any("Speed" in s for s in report["strengths"])
        assert any("Strength" in w for w in report["weaknesses"])

    def test_blurb_mentions_the_verdict(self):
        report = ai_gm.scout_player(_player(), TEAM, [])
        assert report["verdict"] in report["blurb"]


class TestBuildContextSummary:
    def test_contains_expected_sections(self):
        summary = ai_gm.build_context_summary(TEAM, [])
        assert "TEAM: TESTTEAM" in summary
        assert "POSITION GRADES:" in summary
        assert "POSITIONAL NEEDS:" in summary
        assert "CAP:" in summary
        assert "FULL ROSTER" in summary

    def test_notes_session_additions_when_present(self):
        extra = _roster_of("QB", count=1, ovr=80)
        summary = ai_gm.build_context_summary(TEAM, extra)
        assert "AI GM Assistant" in summary

    def test_no_note_when_no_additions(self):
        summary = ai_gm.build_context_summary(TEAM, [])
        assert "AI GM Assistant" not in summary
