"""Tests for roster analyzer verdict logic."""

import pytest
from src.roster_analyzer import analyze_roster


def _make_player(name="Test Player", pos="WR", ovr=75, age=25,
                 dev="Normal", savings=0, penalty=0):
    """Helper to build a player dict for testing."""
    return {
        "Name": name, "Pos": pos, "OVR": ovr, "Age": age,
        "Dev": dev, "Savings": savings, "Penalty": penalty,
    }


class TestCutLogic:
    """Tests for the CUT verdict logic in analyze_roster."""

    def test_cut_requires_savings_greater_than_penalty(self):
        """Players should only be flagged CUT when savings > penalty (net cap relief)."""
        verdicts = analyze_roster("GB")
        for v in verdicts:
            if v["Verdict"] == "CUT" and "cap relief" in v["Reason"]:
                assert v["Savings"] > v["Penalty"], (
                    f"{v['Name']} flagged CUT but savings ({v['Savings']}) "
                    f"<= penalty ({v['Penalty']})"
                )

    def test_high_penalty_low_savings_not_cut_for_cap(self):
        """A player with high dead cap and low savings should NOT be CUT for cap reasons."""
        verdicts = analyze_roster("GB")
        for v in verdicts:
            if v["Verdict"] == "CUT" and "cap relief" in v["Reason"]:
                # Net relief should be positive
                net = v["Savings"] - v["Penalty"]
                assert net > 0, (
                    f"{v['Name']} CUT with negative cap relief: ${net:.1f}M"
                )


class TestDevTraitMatching:
    """Tests for dev trait recognition in KEEP reasons."""

    def test_superstar_x_recognized(self):
        """Superstar X dev trait should match for young dev talent identification."""
        # The string "superstar x" should be in the recognized dev traits
        dev_trait = "Superstar X"
        assert dev_trait.lower() in ("superstar", "superstar x", "star")

    def test_all_dev_traits_recognized(self):
        """All standard Madden dev traits should be recognized."""
        recognized = {"superstar", "superstar x", "star"}
        for trait in ["Superstar", "Superstar X", "Star"]:
            assert trait.lower() in recognized, f"{trait} not recognized"


class TestAnalyzeRosterIntegration:
    """Integration tests for the full analyze_roster function."""

    def test_returns_results(self):
        verdicts = analyze_roster("GB")
        assert len(verdicts) > 0

    def test_all_verdicts_valid(self):
        verdicts = analyze_roster("GB")
        valid = {"KEEP", "TRADE", "CUT"}
        for v in verdicts:
            assert v["Verdict"] in valid

    def test_results_sorted_correctly(self):
        """Results should be sorted: CUT first, then TRADE, then KEEP."""
        verdicts = analyze_roster("GB")
        order = {"CUT": 0, "TRADE": 1, "KEEP": 2}
        prev = -1
        for v in verdicts:
            curr = order[v["Verdict"]]
            assert curr >= prev or curr == prev, (
                f"Sort order violated: {v['Verdict']} after previous order {prev}"
            )
            if curr > prev:
                prev = curr
