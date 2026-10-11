"""
Scheme/playbook vocabulary and the comparison that ranks them.

The behaviour worth pinning here is mostly about *not* fragmenting the
data. The entry form accepts values that aren't in the built-in lists —
that is the point of the lists being defaults — so the only thing
standing between a typed "west coast zone run" and a rival one-game
scheme beside the 22 already logged is `normalize`.
"""

import pandas as pd
import pytest

from src import game_log, schemes


def _log(rows):
    """A game log frame from (scheme, points for, points against) triples."""
    return pd.DataFrame([
        {"GAME_ID": i + 1, "Team": "GB", "Opponent": "CHI",
         schemes.OFF_SCHEME: scheme, "Points_For": pf,
         "Points_Against": pa, "Score_Diff": pf - pa,
         "Result": "W" if pf > pa else ("L" if pf < pa else "T"),
         "Total_Yards": 350, "Pass_Yards": 250, "Rush_Yards": 100,
         "Turnovers": 1, "Takeaways": 1, "Sacks_For": 2}
        for i, (scheme, pf, pa) in enumerate(rows)])


class TestNormalize:
    def test_case_and_spacing_variants_land_on_one_scheme(self):
        # The defect this exists for: "  westcoast   zone run " logged as
        # its own scheme, identical on screen to the 22-game one and
        # splitting the comparison in half.
        for typed in ("westcoast zone run", "  WESTCOAST  ZONE RUN  ",
                      "WestCoastZoneRun", "West Coast Zone Run"):
            assert schemes.normalize(
                typed, schemes.OFF_SCHEME) == "WestCoast Zone Run"

    def test_a_value_already_in_the_log_wins_over_the_defaults(self):
        # The user's own spelling is canonical: they have 22 games under
        # it and the default list is only a suggestion.
        assert schemes.normalize(
            "air raid", schemes.OFF_SCHEME, known=["Air Raid"]) == "Air Raid"

    def test_an_unknown_value_is_kept_as_typed(self):
        assert schemes.normalize(
            "Wing-T Option", schemes.OFF_SCHEME) == "Wing-T Option"

    def test_blank_and_missing_come_back_empty(self):
        for value in ("", "   ", None, float("nan")):
            assert schemes.normalize(value, schemes.OFF_SCHEME) == ""


class TestSplitAndJoin:
    @pytest.mark.parametrize("text,expected", [
        ("WestCoast Zone Run", ("WestCoast", "Zone Run")),
        ("Vertical Power Run", ("Vertical", "Power Run")),
        ("Run N Gun Zone Run", ("Run N Gun", "Zone Run")),
        # Both shipped values must survive the round trip, or relabelling
        # a 22-game scheme would quietly rename it.
        ("Vertical Zone Run", ("Vertical", "Zone Run")),
    ])
    def test_known_schemes_split_into_pass_and_run(self, text, expected):
        assert schemes.split_off_scheme(text) == expected
        assert schemes.join_off_scheme(*expected) == text

    def test_a_scheme_with_no_known_run_half_stays_whole(self):
        assert schemes.split_off_scheme("Air Raid") == ("Air Raid", "")

    def test_a_bare_run_scheme_is_not_split_into_nothing(self):
        # "Zone Run" alone must not become ("", "Zone Run") and lose the
        # fact that no pass scheme was recorded... it has no pass half,
        # so it is kept whole rather than silently halved.
        assert schemes.split_off_scheme("Zone Run") == ("Zone Run", "")

    def test_join_tolerates_a_missing_half(self):
        assert schemes.join_off_scheme("Spread", "") == "Spread"
        assert schemes.join_off_scheme("", "Zone Run") == "Zone Run"


class TestOptions:
    def test_used_values_come_before_the_defaults(self):
        df = _log([("Air Raid", 30, 20)])
        assert schemes.options(df, schemes.OFF_SCHEME)[0] == "Air Raid"

    def test_a_used_value_is_not_repeated_by_the_defaults(self):
        df = _log([("Spread Zone Run", 30, 20)])
        opts = schemes.options(df, schemes.OFF_SCHEME)
        assert opts.count("Spread Zone Run") == 1

    def test_current_is_the_most_recent_not_the_alphabetically_last(self):
        # The defect this exists for. `sorted(values)[-1]` reads as "the
        # one used last" but isn't: a franchise that switched to Air Raid
        # got WestCoast prefilled every week after, and the mislabelled
        # games fed straight into the comparison.
        df = _log([("WestCoast Zone Run", 30, 20), ("Air Raid", 28, 14)])
        assert schemes.current(df, schemes.OFF_SCHEME) == "Air Raid"

    def test_current_is_empty_for_a_log_with_no_schemes(self):
        assert schemes.current(_log([(None, 20, 10)]),
                               schemes.OFF_SCHEME) == ""


class TestUnlabelled:
    def test_counts_blanks_and_missing_values(self):
        df = _log([("Spread Zone Run", 30, 10), (None, 3, 40), ("  ", 7, 35)])
        assert schemes.unlabelled(df, schemes.OFF_SCHEME) == 2

    def test_a_nan_is_not_mistaken_for_the_text_nan(self):
        # `str(nan).strip()` is "nan", which is truthy — so the obvious
        # blank test reports a log where nothing is recorded as fully
        # labelled, and the prompt to go and label it never appears.
        df = _log([(None, 20, 10)] * 3)
        assert schemes.unlabelled(df, schemes.OFF_SCHEME) == 3

    def test_a_column_the_log_lacks_counts_every_game(self):
        assert schemes.unlabelled(
            _log([("Spread Zone Run", 30, 10)] * 4), schemes.DEF_SCHEME) == 4

    def test_the_shipped_log_has_its_fourteen_unlabelled_games(self):
        assert schemes.unlabelled(
            pd.read_csv("data/game_logs.csv"), schemes.OFF_SCHEME) == 14


class TestCompare:
    def test_unlabelled_games_are_not_their_own_scheme(self):
        # 14 of the 42 shipped games have no scheme. Grouping them would
        # make "" the second-biggest scheme in the comparison.
        rows = schemes.compare(
            _log([("Spread Zone Run", 30, 10), (None, 3, 40), ("", 7, 35)]),
            schemes.OFF_SCHEME)
        assert [r["value"] for r in rows] == ["Spread Zone Run"]

    def test_ranked_on_margin_and_small_samples_sort_last(self):
        rows = schemes.compare(_log(
            # A 1-game scheme with a huge margin must not outrank a
            # 5-game one; that is the whole point of MIN_GAMES.
            [("Blowout", 50, 0)]
            + [("Steady", 24, 20)] * 5), schemes.OFF_SCHEME)
        assert [r["value"] for r in rows] == ["Steady", "Blowout"]
        assert rows[0]["ranked"] and not rows[1]["ranked"]

    def test_record_counts_a_tie_as_a_tie(self):
        rows = schemes.compare(_log([("Spread Zone Run", 20, 20)]),
                               schemes.OFF_SCHEME)
        assert rows[0]["record"] == "0-0-1"

    def test_spacing_variants_are_one_group(self):
        rows = schemes.compare(
            _log([("Spread Zone Run", 30, 10),
                  ("Spread Zone Run ", 28, 14)]), schemes.OFF_SCHEME)
        assert len(rows) == 1 and rows[0]["games"] == 2

    def test_a_missing_column_is_empty_not_an_error(self):
        assert schemes.compare(_log([("Spread Zone Run", 30, 10)]),
                               schemes.DEF_SCHEME) == []

    def test_an_empty_log_is_empty_not_an_error(self):
        assert schemes.compare(pd.DataFrame(), schemes.OFF_SCHEME) == []


class TestVerdict:
    def test_refuses_to_crown_a_winner_on_thin_evidence(self):
        rows = schemes.compare(_log(
            [("A", 40, 0), ("B", 0, 40)]), schemes.OFF_SCHEME)
        said = schemes.verdict(rows, schemes.OFF_SCHEME)
        assert "worth acting on" in said and "A" not in said.split("**")[0:1]

    def test_calls_a_close_gap_inconclusive(self):
        rows = schemes.compare(
            _log([("A", 24, 21)] * 5 + [("B", 24, 22)] * 5),
            schemes.OFF_SCHEME)
        assert "schedule rather than the scheme" in schemes.verdict(
            rows, schemes.OFF_SCHEME)

    def test_calls_a_wide_gap_real(self):
        rows = schemes.compare(
            _log([("A", 35, 10)] * 5 + [("B", 17, 20)] * 5),
            schemes.OFF_SCHEME)
        said = schemes.verdict(rows, schemes.OFF_SCHEME)
        assert "**A**" in said and "real" in said

    def test_one_scheme_asks_for_a_second_rather_than_declaring_it_best(self):
        rows = schemes.compare(_log([("A", 35, 10)] * 5), schemes.OFF_SCHEME)
        assert "Only one" in schemes.verdict(rows, schemes.OFF_SCHEME)

    def test_nothing_logged_says_nothing(self):
        assert schemes.verdict([], schemes.OFF_SCHEME) == ""


class TestSides:
    def test_a_defensive_dimension_is_not_graded_on_your_own_offence(self):
        keys = [m[0] for m in schemes.metrics_for(schemes.DEF_SCHEME)]
        assert "opp_ppg" in keys and "ppg" not in keys
        assert "total_ypg_allowed" in keys and "pass_ypg" not in keys

    def test_an_offensive_dimension_is_graded_on_offence(self):
        keys = [m[0] for m in schemes.metrics_for(schemes.OFF_PLAYBOOK)]
        assert "ppg" in keys and "opp_ppg" not in keys

    def test_every_dimension_reports_record_and_margin(self):
        for column in schemes.SCHEME_COLUMNS:
            keys = [m[0] for m in schemes.metrics_for(column)]
            assert "win_pct" in keys and "margin" in keys


class TestAgainstTheWriteLayer:
    def test_every_scheme_column_is_writable_by_the_entry_form(self):
        for column in schemes.SCHEME_COLUMNS:
            assert column in game_log.ENTRY_FIELDS

    def test_every_scheme_column_can_be_corrected_later(self):
        # The gap this feature closes: a game logged under the wrong
        # scheme used to be fixable only by hand-editing the CSV.
        for column in schemes.SCHEME_COLUMNS:
            assert column in game_log.BACKFILL_FIELDS

    def test_the_offensive_scheme_still_lives_in_the_legacy_column(self):
        # Renaming it would mean rewriting every row of the user's CSV
        # and breaking every Sheet pointed at this dashboard.
        assert schemes.OFF_SCHEME == "Playbook"
        assert "Playbook" in pd.read_csv("data/game_logs.csv").columns

    def test_the_shipped_schemes_are_offered_before_the_defaults(self):
        df = pd.read_csv("data/game_logs.csv")
        opts = schemes.options(df, schemes.OFF_SCHEME)
        assert set(opts[:2]) == {"WestCoast Zone Run", "Vertical Zone Run"}
