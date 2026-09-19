"""
Tests for the shared season numbering.

The game log counted seasons 1, 2, 3... while the Dynasty archive used
calendar years. Three `st.number_input` calls in `app.py` each declared
their own range, so nothing held them together. These tests pin the
bounds and, more importantly, check that `app.py` still reads them from
one place — the drift is the bug, not either particular range.
"""

import ast
import pathlib

import pytest

from src import season


class TestBounds:

    def test_seasons_are_calendar_years(self):
        assert season.SEASON_MIN >= 1900
        assert season.SEASON_MIN <= season.DEFAULT_SEASON <= season.SEASON_MAX

    def test_weeks_cover_a_full_season_plus_playoffs(self):
        # 18 regular season games leaves room for the postseason.
        assert season.WEEK_MIN == 1
        assert season.WEEK_MAX >= 22


class TestClampSeason:

    def test_a_value_in_range_is_untouched(self):
        assert season.clamp_season(2030) == 2030

    def test_a_legacy_franchise_relative_season_is_pulled_into_range(self):
        # A log written before the move to calendar years holds `1`.
        # st.number_input raises outright when handed a value below its
        # min_value, so an unclamped default would take the tab down.
        assert season.clamp_season(1) == season.SEASON_MIN

    def test_a_season_past_the_ceiling_is_pulled_down(self):
        assert season.clamp_season(9999) == season.SEASON_MAX

    @pytest.mark.parametrize("junk", [None, "", "not a year", float("nan")])
    def test_unparseable_values_fall_back_to_the_default(self, junk):
        assert season.clamp_season(junk) == season.DEFAULT_SEASON

    def test_a_numeric_string_is_accepted(self):
        assert season.clamp_season("2031") == 2031


class TestClampWeek:

    def test_a_value_in_range_is_untouched(self):
        assert season.clamp_week(9) == 9

    def test_week_past_the_end_of_the_postseason_is_pulled_down(self):
        # next_season_week returns max+1, which runs off the end after
        # the final week; the form must still open.
        assert season.clamp_week(season.WEEK_MAX + 1) == season.WEEK_MAX

    def test_zero_and_junk_fall_back_to_the_first_week(self):
        assert season.clamp_week(0) == season.WEEK_MIN
        assert season.clamp_week("nonsense") == season.WEEK_MIN


class TestNothingDeclaresItsOwnRange:
    """The drift is the bug this module exists to prevent.

    Three `st.number_input` calls each hardcoded bounds, so the game log
    and the Dynasty archive disagreed about what a season even was. If a
    fourth appears with its own literals, they will disagree again.
    """

    def _season_week_widgets(self):
        """Every st.number_input in app.py labelled Season or Week."""
        tree = ast.parse(pathlib.Path("app.py").read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute)
                    and func.attr == "number_input"):
                continue
            if not node.args:
                continue
            label = node.args[0]
            if not (isinstance(label, ast.Constant)
                    and isinstance(label.value, str)):
                continue
            if not any(word in label.value for word in ("Season", "Week")):
                continue
            yield label.value, node

    def test_every_season_and_week_widget_was_found(self):
        # Guards the test itself: if the AST walk silently matches
        # nothing, the assertions below would pass vacuously.
        labels = [lbl for lbl, _ in self._season_week_widgets()]
        assert len(labels) >= 4, f"only found {labels}"

    def test_no_widget_hardcodes_its_bounds(self):
        offenders = []
        for label, call in self._season_week_widgets():
            for kw in call.keywords:
                if kw.arg not in ("min_value", "max_value"):
                    continue
                if isinstance(kw.value, ast.Constant):
                    offenders.append(
                        f"{label!r} {kw.arg}={kw.value.value}"
                        f" (line {call.lineno})")
        assert not offenders, (
            "season/week bounds must come from src/season.py, not literals: "
            + "; ".join(offenders))
