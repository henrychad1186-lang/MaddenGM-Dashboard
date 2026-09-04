"""
Tests for src/analytics.py — the tab logic that used to be unreachable.

All of this lived inline in `app.py`'s `with tabs[n]:` blocks, so none of
it could be exercised without a browser. These are the cases that decide
an award, an archetype, or a momentum curve.
"""

import pandas as pd
import pytest

from src import analytics


def _game(playbook="WestCoast", result="WIN", pf=28, pa=17, **extra):
    game = {
        "Playbook": playbook,
        "Result": result,
        "Points_For": pf,
        "Points_Against": pa,
        "Score_Diff": pf - pa,
        "Opponent": "CHI",
    }
    game.update(extra)
    return game


def _player(name="A. Player", pos="WR", ovr=80, age=25, dev="Normal",
            savings="$1M", penalty="$1M"):
    return {
        "Name": name, "Pos": pos, "OVR": ovr, "Age": age, "Dev": dev,
        "Team": "GB", "Savings": savings, "Penalty": penalty,
        "SPD": 88, "ACC": 90, "AGI": 88, "COD": 85, "STR": 60, "AWR": 78,
    }


# ──────────────────────────────────────────────
# SCHEME STATS
# ──────────────────────────────────────────────

class TestComputeSchemeStats:

    def test_no_playbook_column_returns_empty(self):
        df = pd.DataFrame([{"Result": "WIN", "Points_For": 30}])
        assert analytics.compute_scheme_stats(df) == {}

    def test_record_and_win_pct(self):
        df = pd.DataFrame([
            _game(result="WIN"), _game(result="WIN"), _game(result="LOSS"),
        ])
        stats = analytics.compute_scheme_stats(df)["WestCoast"]
        assert stats["Games"] == 3
        assert stats["Record"] == "2-1"
        assert stats["Win%"] == pytest.approx(66.7)

    def test_splits_by_playbook(self):
        df = pd.DataFrame([
            _game(playbook="WestCoast", result="WIN"),
            _game(playbook="Spread", result="LOSS"),
        ])
        stats = analytics.compute_scheme_stats(df)
        assert set(stats) == {"WestCoast", "Spread"}
        assert stats["WestCoast"]["Record"] == "1-0"
        assert stats["Spread"]["Record"] == "0-1"

    def test_missing_optional_columns_score_zero_not_nan(self):
        # A log without Pass_Yards must not put NaN into the bar chart.
        df = pd.DataFrame([_game()])
        stats = analytics.compute_scheme_stats(df)["WestCoast"]
        assert stats["Pass YPG"] == 0
        assert stats["Sacks/G"] == 0

    def test_averages_are_rounded(self):
        # Margins are 21-17=4 and 28-17=11, so the average is 7.5.
        df = pd.DataFrame([_game(pf=21), _game(pf=28)])
        stats = analytics.compute_scheme_stats(df)["WestCoast"]
        assert stats["PPG"] == 24.5
        assert stats["Avg Margin"] == 7.5

    def test_comparison_frame_covers_every_scheme_and_metric(self):
        df = pd.DataFrame([_game(playbook="WestCoast"), _game(playbook="Spread")])
        stats = analytics.compute_scheme_stats(df)
        compare = analytics.build_scheme_comparison(stats)
        assert len(compare) == 2 * len(analytics.SCHEME_COMPARE_METRICS)
        assert set(compare["Scheme"]) == {"WestCoast", "Spread"}


# ──────────────────────────────────────────────
# MOMENTUM
# ──────────────────────────────────────────────

class TestMomentum:

    def test_cumulative_win_pct(self):
        df = pd.DataFrame([
            _game(result="WIN"), _game(result="LOSS"), _game(result="WIN"),
        ])
        momentum = analytics.compute_momentum(df)
        assert momentum["Game_Num"].tolist() == [1, 2, 3]
        assert momentum["Win_Pct"].tolist() == [100.0, 50.0, pytest.approx(66.7)]

    def test_rolling_margin_uses_a_three_game_window(self):
        df = pd.DataFrame([
            _game(pf=30, pa=0), _game(pf=30, pa=0), _game(pf=0, pa=30),
        ])
        momentum = analytics.compute_momentum(df)
        # (30 + 30 - 30) / 3 == 10
        assert momentum["Rolling_Margin"].iloc[-1] == 10.0

    def test_rolling_margin_skipped_without_score_diff(self):
        df = pd.DataFrame([{"Result": "WIN"}, {"Result": "LOSS"}])
        assert "Rolling_Margin" not in analytics.compute_momentum(df).columns

    def test_does_not_mutate_the_caller_frame(self):
        df = pd.DataFrame([_game()])
        analytics.compute_momentum(df)
        assert "Game_Num" not in df.columns


class TestLongestWinStreak:

    def test_counts_the_longest_run_not_the_last(self):
        assert analytics.longest_win_streak([1, 1, 1, 0, 1]) == 3

    def test_no_wins(self):
        assert analytics.longest_win_streak([0, 0]) == 0

    def test_empty(self):
        assert analytics.longest_win_streak([]) == 0

    def test_accepts_booleans(self):
        assert analytics.longest_win_streak([True, True, False, True]) == 2


# ──────────────────────────────────────────────
# COACH DNA
# ──────────────────────────────────────────────

class TestCoachDNA:

    def _pass_heavy(self, n=5, **extra):
        return pd.DataFrame([
            _game(Pass_Yards=350, Rush_Yards=60, **extra) for _ in range(n)
        ])

    def test_returns_none_below_the_game_minimum(self):
        assert analytics.compute_coach_dna(self._pass_heavy(n=2)) is None

    def test_returns_none_without_pass_rush_columns(self):
        assert analytics.compute_coach_dna(pd.DataFrame([_game()] * 5)) is None

    def test_pass_rush_split_sums_to_100(self):
        dna = analytics.compute_coach_dna(self._pass_heavy())
        assert dna["pass_pct"] + dna["rush_pct"] == pytest.approx(100)

    def test_pass_heavy_high_scoring_is_air_raid(self):
        dna = analytics.compute_coach_dna(self._pass_heavy(pf=38))
        assert dna["archetype"] == "🌩️ Aggressive Air Raid"

    def test_run_heavy_ball_secure_is_ground_and_pound(self):
        df = pd.DataFrame([
            _game(Pass_Yards=150, Rush_Yards=180, Turnovers=0) for _ in range(5)
        ])
        assert analytics.compute_coach_dna(df)["archetype"] == \
            "🗿 Conservative Ground & Pound"

    def test_axes_are_clamped_to_0_100(self):
        df = pd.DataFrame([
            _game(pf=99, Pass_Yards=600, Rush_Yards=1, Turnovers=9,
                  Sacks_For=12, Takeaways=9) for _ in range(5)
        ])
        for value in analytics.compute_coach_dna(df)["axes"].values():
            assert 0 <= value <= 100

    def test_turnovers_destroy_ball_security(self):
        clean = analytics.compute_coach_dna(self._pass_heavy(Turnovers=0))
        sloppy = analytics.compute_coach_dna(self._pass_heavy(Turnovers=3))
        assert clean["axes"]["Ball Security"] == 100
        assert sloppy["axes"]["Ball Security"] == 0


# ──────────────────────────────────────────────
# TRADE VALUE LEADERBOARD
# ──────────────────────────────────────────────

class TestTradeValueTable:

    def test_empty_roster_returns_empty_frame_with_columns(self):
        table = analytics.build_trade_value_table(pd.DataFrame())
        assert table.empty
        assert "Trade Value" in table.columns

    def test_sorted_by_trade_value_descending(self):
        df = pd.DataFrame([
            _player(name="Low", ovr=68), _player(name="High", ovr=95),
        ])
        table = analytics.build_trade_value_table(df)
        assert table["Name"].tolist() == ["High", "Low"]
        assert table["Trade Value"].is_monotonic_decreasing

    def test_ranked_from_one(self):
        df = pd.DataFrame([_player(name="A"), _player(name="B", ovr=90)])
        table = analytics.build_trade_value_table(df)
        assert table.index.name == "Rank"
        assert table.index.tolist() == [1, 2]


# ──────────────────────────────────────────────
# SEASON AWARDS
# ──────────────────────────────────────────────

class TestSeasonAwards:

    def _by_title(self, awards):
        return {a["title"]: a["player"] for a in awards}

    def test_empty_roster_still_returns_all_five_slots(self):
        awards = analytics.select_season_awards(pd.DataFrame())
        assert len(awards) == 5
        assert all(a["player"] is None for a in awards)

    def test_mvp_is_the_highest_trade_value(self):
        df = pd.DataFrame([
            _player(name="Star QB", pos="QB", ovr=95, age=25),
            _player(name="Old K", pos="K", ovr=70, age=38),
        ])
        awards = self._by_title(analytics.select_season_awards(df))
        assert awards["🏆 MVP"]["Name"] == "Star QB"

    def test_dpoy_only_considers_defenders(self):
        df = pd.DataFrame([
            _player(name="Elite WR", pos="WR", ovr=99),
            _player(name="Good CB", pos="CB", ovr=84),
        ])
        awards = self._by_title(analytics.select_season_awards(df))
        assert awards["🛡️ DPOY"]["Name"] == "Good CB"

    def test_no_defenders_leaves_dpoy_empty(self):
        df = pd.DataFrame([_player(name="Only WR", pos="WR")])
        awards = self._by_title(analytics.select_season_awards(df))
        assert awards["🛡️ DPOY"] is None

    def test_roy_is_capped_at_age_22(self):
        df = pd.DataFrame([
            _player(name="Vet", ovr=99, age=23),
            _player(name="Rookie", ovr=75, age=22),
        ])
        awards = self._by_title(analytics.select_season_awards(df))
        assert awards["⭐ ROY"]["Name"] == "Rookie"

    def test_iron_man_needs_both_age_and_ovr(self):
        df = pd.DataFrame([
            _player(name="Old And Weak", ovr=70, age=35),
            _player(name="Old And Good", ovr=82, age=31),
            _player(name="Young And Good", ovr=90, age=24),
        ])
        awards = self._by_title(analytics.select_season_awards(df))
        assert awards["💪 Iron Man"]["Name"] == "Old And Good"

    def test_sub_million_dead_cap_is_not_read_as_millions(self):
        # Regression: the old inline parser stripped the "K" without
        # dividing, so "$600K" scored as $600M of dead cap and the roster's
        # best-value contract was ranked its worst.
        df = pd.DataFrame([
            _player(name="Cheap Deal", ovr=80, penalty="$600K"),
            _player(name="Costly Deal", ovr=80, penalty="$20M"),
        ])
        awards = self._by_title(analytics.select_season_awards(df))
        assert awards["💰 Best Contract"]["Name"] == "Cheap Deal"

    def test_best_contract_empty_when_nobody_carries_dead_cap(self):
        df = pd.DataFrame([_player(name="Free", penalty="$0")])
        awards = self._by_title(analytics.select_season_awards(df))
        assert awards["💰 Best Contract"] is None

    def test_does_not_mutate_the_caller_frame(self):
        df = pd.DataFrame([_player()])
        analytics.select_season_awards(df)
        assert "TV" not in df.columns and "_pen" not in df.columns


# ──────────────────────────────────────────────
# FRANCHISE HOME
# ──────────────────────────────────────────────

class TestFranchiseHome:

    def test_top_needs_puts_critical_first(self):
        needs = [
            {"pos": "QB", "level": "Moderate", "avg_ovr": 70.0},
            {"pos": "WR", "level": "Set", "avg_ovr": 88.0},
            {"pos": "MLB", "level": "Critical", "avg_ovr": 72.0},
        ]
        assert [n["pos"] for n in analytics.top_needs(needs)] == ["MLB", "QB"]

    def test_top_needs_breaks_ties_on_worst_ovr(self):
        needs = [
            {"pos": "QB", "level": "Critical", "avg_ovr": 75.0},
            {"pos": "FB", "level": "Critical", "avg_ovr": 60.0},
        ]
        assert [n["pos"] for n in analytics.top_needs(needs)] == ["FB", "QB"]

    def test_top_needs_excludes_set_positions(self):
        needs = [{"pos": "WR", "level": "Set", "avg_ovr": 90.0}]
        assert analytics.top_needs(needs) == []

    def test_top_needs_respects_the_limit(self):
        needs = [
            {"pos": p, "level": "Critical", "avg_ovr": 60.0}
            for p in ["QB", "HB", "WR", "TE"]
        ]
        assert len(analytics.top_needs(needs, limit=3)) == 3

    def test_actionable_moves_drops_keeps_and_preserves_order(self):
        verdicts = [
            {"Name": "A", "Verdict": "CUT"},
            {"Name": "B", "Verdict": "TRADE"},
            {"Name": "C", "Verdict": "KEEP"},
        ]
        moves = analytics.actionable_moves(verdicts)
        assert [m["Name"] for m in moves] == ["A", "B"]

    def test_record_from_log(self):
        df = pd.DataFrame([
            _game(result="WIN"), _game(result="WIN"), _game(result="LOSS"),
        ])
        assert analytics.record_from_log(df) == (2, 1)

    def test_record_without_result_column_is_zero_zero(self):
        assert analytics.record_from_log(pd.DataFrame([{"Points_For": 20}])) == (0, 0)
