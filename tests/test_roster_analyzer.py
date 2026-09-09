"""Tests for roster analyzer verdict logic."""

import pandas as pd

from src import roster_analyzer
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
    """Tests for dev trait recognition in KEEP reasons.

    Exercises the real analyze_roster() verdict logic (not just the
    membership check in isolation) by monkeypatching its roster/cap/
    trade-value dependencies with a single controlled player, so a
    regression in the actual KEEP-reason branch fails this test.
    """

    def _analyze_single_player(self, monkeypatch, player: dict) -> dict:
        roster_df = pd.DataFrame([player])
        monkeypatch.setattr(
            roster_analyzer, "get_roster",
            lambda team, group, extra_players=None: roster_df)
        monkeypatch.setattr(
            roster_analyzer, "get_cap_summary",
            lambda team, extra_players=None: {"players": []})
        monkeypatch.setattr(
            roster_analyzer, "get_trade_value", lambda p: 50.0)
        verdicts = roster_analyzer.analyze_roster("GB")
        assert len(verdicts) == 1
        return verdicts[0]

    def test_young_superstar_x_gets_dev_talent_reason(self, monkeypatch):
        player = {"Name": "Test Rookie", "Pos": "WR", "OVR": 74,
                 "Age": 22, "Dev": "Superstar X"}
        verdict = self._analyze_single_player(monkeypatch, player)
        assert verdict["Verdict"] == "KEEP"
        assert verdict["Reason"] == "Young dev talent — high ceiling"

    def test_young_normal_dev_does_not_get_dev_talent_reason(self, monkeypatch):
        """Same age/OVR but a Normal dev trait should NOT get the high-ceiling reason."""
        player = {"Name": "Test Depth Guy", "Pos": "WR", "OVR": 74,
                 "Age": 22, "Dev": "Normal"}
        verdict = self._analyze_single_player(monkeypatch, player)
        assert verdict["Verdict"] == "KEEP"
        assert verdict["Reason"] == "Roster depth piece"


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
            assert curr >= prev, (
                f"Sort order violated: {v['Verdict']} after previous order {prev}"
            )
            prev = curr
