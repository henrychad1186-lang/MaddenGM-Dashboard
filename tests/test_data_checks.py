"""Game-log consistency checks."""

import pandas as pd
import pytest

from src import data_checks as dc


def _row(**kw):
    base = {"GAME_ID": 1, "Opponent": "CHI", "Result": "W",
            "Points_For": 24, "Points_Against": 17, "Point_Differential": 7,
            "Pass_Yards": 250, "Rush_Yards": 100, "Total_Yards": 350,
            "Pass_Yards_Allowed": 200, "Rush_Yards_Allowed": 90,
            "Total_Yards_Allowed": 290, "TOP": "22:30"}
    base.update(kw)
    return base


def _checks(rows, **kw):
    return [(i["game"], i["check"]) for i in dc.check_log(pd.DataFrame(rows), **kw)]


def test_clean_log_has_no_issues():
    assert dc.check_log(pd.DataFrame([_row(), _row(GAME_ID=2, TOP="21:10")])) == []


@pytest.mark.parametrize("empty", [None, pd.DataFrame()])
def test_no_log_no_issues(empty):
    assert dc.check_log(empty) == []


def test_return_yards_in_total_allowed_is_flagged_with_the_hint():
    [issue] = dc.check_log(pd.DataFrame([_row(Total_Yards_Allowed=380)]))
    assert issue["check"] == "Defense yards don't add up"
    assert "+90" in issue["detail"] and "return yards" in issue["detail"]


def test_small_gap_gets_no_return_yards_hint():
    [issue] = dc.check_log(pd.DataFrame([_row(Total_Yards=355)]))
    assert issue["check"] == "Offense yards don't add up"
    assert "+5" in issue["detail"] and "return yards" not in issue["detail"]


def test_total_below_components_is_flagged_without_hint():
    [issue] = dc.check_log(pd.DataFrame([_row(Total_Yards_Allowed=250)]))
    assert "-40" in issue["detail"] and "return yards" not in issue["detail"]


def test_blank_total_with_components_is_flagged():
    assert _checks([_row(Total_Yards_Allowed=None)]) == [("1", "Defense total yards missing")]


def test_missing_components_skip_the_sum_check():
    assert _checks([_row(Pass_Yards=None, Rush_Yards=None, Total_Yards=221)]) == []


def test_point_differential_and_result_mismatches():
    got = _checks([_row(Point_Differential=10), _row(GAME_ID=2, Result="L")])
    assert got == [("1", "Point differential wrong"), ("2", "Result doesn't match score")]


def test_prepared_result_labels_are_understood():
    tie = _row(GAME_ID=2, Result="TIE", Points_Against=24, Point_Differential=0)
    assert _checks([_row(Result="WIN"), tie]) == []


@pytest.mark.parametrize("top, flagged", [
    ("0:31", True), ("8:15", True), ("10:59", True), ("11:00", False),
    ("33:00", False), ("33:01", True), ("not a time", False)])
def test_implausible_time_of_possession(top, flagged):
    got = _checks([_row(TOP=top)])
    assert (("1", "Time of possession implausible") in got) == flagged


def test_game_length_is_configurable():
    assert _checks([_row(TOP="8:15")], game_minutes=32) == []


def test_placeholder_run_of_one_minute_steps():
    rows = [_row(GAME_ID=i, TOP=t) for i, t in
            enumerate(["14:01", "15:01", "16:01", "19:40", "20:40"], start=1)]
    got = _checks(rows)
    assert got == [(str(i), "Time of possession looks like a placeholder") for i in (1, 2, 3)]


def test_run_at_end_of_log_is_flagged():
    rows = [_row(GAME_ID=i, TOP=t) for i, t in
            enumerate(["19:40", "20:01", "21:01", "22:01"], start=1)]
    assert [g for g, _ in _checks(rows)] == ["2", "3", "4"]


def test_two_step_run_is_not_a_placeholder():
    rows = [_row(GAME_ID=i, TOP=t) for i, t in enumerate(["20:01", "21:01"], start=1)]
    assert _checks(rows) == []


def test_top_minutes_parsing():
    assert dc.top_minutes("17:35") == pytest.approx(17 + 35 / 60)
    for bad in ("17", "17:75", "a:b", None, 17.5):
        assert dc.top_minutes(bad) is None


def test_summary_counts_in_first_seen_order():
    issues = [{"check": "B"}, {"check": "A"}, {"check": "B"}]
    assert dc.summary(issues) == {"B": 2, "A": 1}


def test_shipped_log_findings():
    """Pins what the checks find in the shipped log, so a data fix or a
    check change shows up here on purpose."""
    s = dc.summary(dc.check_log(pd.read_csv("data/game_logs.csv")))
    assert s == {"Offense yards don't add up": 3,
                 "Time of possession implausible": 4,
                 "Time of possession looks like a placeholder": 9}
