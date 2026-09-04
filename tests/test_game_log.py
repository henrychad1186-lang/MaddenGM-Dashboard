"""
Tests for the game-log preparation and sidebar filtering.

Both were inline in `app.py` — `prepare_game_log` inside a cached loader
and the filter chain inside a sidebar expander — so neither could run
without a Streamlit session. They're plain functions in `views/sidebar.py`
now; importing that module is safe outside a runtime.
"""

import pandas as pd

from views.sidebar import apply_filters, prepare_game_log


class TestPrepareGameLog:

    def test_splits_legacy_score_final(self):
        df, warnings = prepare_game_log(
            pd.DataFrame([{"Score_Final": "34-10"}, {"Score_Final": "17-21"}]))
        assert df["Points_For"].tolist() == [34, 17]
        assert df["Points_Against"].tolist() == [10, 21]
        assert df["Score_Diff"].tolist() == [24, -4]
        assert df["Result"].tolist() == ["WIN", "LOSS"]
        assert warnings == []

    def test_unparseable_score_warns_instead_of_raising(self):
        df, warnings = prepare_game_log(
            pd.DataFrame([{"Score_Final": "not a score"}]))
        assert len(warnings) == 1
        assert "Score_Final" in warnings[0]
        assert len(df) == 1  # the row survives, just underived

    def test_normalizes_single_letter_results(self):
        df, _ = prepare_game_log(pd.DataFrame([
            {"Points_For": 30, "Points_Against": 10, "Result": "W"},
            {"Points_For": 10, "Points_Against": 30, "Result": "L"},
        ]))
        assert df["Result"].tolist() == ["WIN", "LOSS"]

    def test_derives_result_when_the_column_is_absent(self):
        df, _ = prepare_game_log(
            pd.DataFrame([{"Points_For": 30, "Points_Against": 10}]))
        assert df["Result"].tolist() == ["WIN"]

    def test_unrecognized_result_falls_back_to_loss(self):
        df, _ = prepare_game_log(pd.DataFrame([
            {"Points_For": 30, "Points_Against": 10, "Result": "TIE"},
        ]))
        assert df["Result"].tolist() == ["LOSS"]

    def test_top_string_becomes_decimal_minutes(self):
        df, _ = prepare_game_log(pd.DataFrame([{"TOP": "27:45"}]))
        assert df["TOP_Mins"].iloc[0] == 27 + 45 / 60

    def test_malformed_top_becomes_none(self):
        df, _ = prepare_game_log(pd.DataFrame([{"TOP": "aa:bb"}]))
        assert df["TOP_Mins"].iloc[0] is None

    def test_does_not_mutate_the_caller_frame(self):
        raw = pd.DataFrame([{"Score_Final": "34-10"}])
        prepare_game_log(raw)
        assert "Points_For" not in raw.columns


class TestApplyFilters:

    def _log(self):
        return pd.DataFrame([
            {"Result": "WIN", "Playbook": "WestCoast", "Game": 1},
            {"Result": "LOSS", "Playbook": "Spread", "Game": 2},
            {"Result": "WIN", "Playbook": "Spread", "Game": 3},
            {"Result": "WIN", "Playbook": "WestCoast", "Game": 4},
        ])

    def test_filters_by_result(self):
        out = apply_filters(self._log(), ["WIN"], ["WestCoast", "Spread"],
                            "All Games")
        assert out["Game"].tolist() == [1, 3, 4]

    def test_filters_by_playbook(self):
        out = apply_filters(self._log(), ["WIN", "LOSS"], ["Spread"],
                            "All Games")
        assert out["Game"].tolist() == [2, 3]

    def test_games_window_takes_the_most_recent(self):
        out = apply_filters(self._log(), ["WIN", "LOSS"],
                            ["WestCoast", "Spread"], "Last 2")
        assert out["Game"].tolist() == [3, 4]

    def test_deselecting_every_result_yields_nothing(self):
        # An empty selection means "none", not "no filter" — the KPIs
        # should read zero rather than silently showing every game.
        out = apply_filters(self._log(), [], ["WestCoast", "Spread"],
                            "All Games")
        assert out.empty

    def test_deselecting_every_playbook_yields_nothing(self):
        out = apply_filters(self._log(), ["WIN", "LOSS"], [], "All Games")
        assert out.empty

    def test_none_playbooks_means_no_playbook_filter(self):
        # The sidebar passes None when the log has no playbook values at
        # all, which must not be mistaken for "user deselected them".
        out = apply_filters(self._log(), ["WIN", "LOSS"], None, "All Games")
        assert len(out) == 4

    def test_filters_compose(self):
        out = apply_filters(self._log(), ["WIN"], ["WestCoast"], "All Games")
        assert out["Game"].tolist() == [1, 4]

    def test_window_applies_after_the_other_filters(self):
        out = apply_filters(self._log(), ["WIN"], ["WestCoast", "Spread"],
                            "Last 2")
        assert out["Game"].tolist() == [3, 4]

    def test_does_not_mutate_the_caller_frame(self):
        log = self._log()
        apply_filters(log, ["WIN"], ["WestCoast"], "All Games")
        assert len(log) == 4
