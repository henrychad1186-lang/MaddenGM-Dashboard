"""Game-log consistency checks."""

import pandas as pd
import pytest

from src import data_checks as dc
from src import game_log


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


def test_blank_time_of_possession_is_not_flagged():
    rows = [_row(GAME_ID=1, TOP=None), _row(GAME_ID=2, TOP=""), _row(GAME_ID=3)]
    assert _checks(rows) == []
    # Blank cells read back from a CSV arrive as NaN.
    assert dc.check_log(pd.DataFrame({"TOP": [float("nan"), "21:00"]})) == []


def test_blank_breaks_a_placeholder_run():
    rows = [_row(GAME_ID=i, TOP=t) for i, t in
            enumerate(["14:01", "15:01", None, "16:01", "17:01"], start=1)]
    assert _checks(rows) == []


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


def test_sheets_time_format_is_range_checked():
    # A Sheet exports a typed "8:05" as "8:05:00"; the checks used
    # their own parser, which skipped it, so the outlier went unflagged.
    assert _checks([_row(TOP="8:05:00")]) == [
        ("1", "Time of possession implausible")]


def test_summary_counts_in_first_seen_order():
    issues = [{"check": "B"}, {"check": "A"}, {"check": "B"}]
    assert dc.summary(issues) == {"B": 2, "A": 1}


def test_shipped_log_findings():
    """Pins what the checks find in the shipped log, so a data fix or a
    check change shows up here on purpose."""
    s = dc.summary(dc.check_log(pd.read_csv("data/game_logs.csv")))
    assert s == {"Offense yards don't add up": 3}


def test_data_checks_ignore_the_sidebar_filters():
    """Checks run on the whole log: the TOP placeholder check compares
    neighbouring games, which a filtered view would put side by side,
    and the item count shouldn't change with the sidebar."""
    testing = pytest.importorskip("streamlit.testing.v1")
    import pathlib
    app = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")
    at = testing.AppTest.from_file(app, default_timeout=120).run()
    full = dc.summary(dc.check_log(pd.read_csv("data/game_logs.csv")))
    want = f"Data checks: {sum(full.values())} item(s)"

    def label():
        return [e.label for e in at.expander if "Data checks" in str(e.label)]

    assert any(want in lbl for lbl in label()), label()
    results = [m for m in at.multiselect if m.label == "Results"][0]
    results.set_value(["WIN"]).run()
    assert not at.exception, at.exception
    assert any(want in lbl for lbl in label()), label()


@pytest.mark.parametrize("made,att,cols,label", [
    (7, 5, ("Third_Down_Conv", "Third_Down_Att"), "3rd-down conversions exceed attempts"),
    (4, 3, ("RZ_TD_Made", "RZ_Att"), "Red zone TDs exceed trips"),
])
def test_made_above_attempts_is_flagged(made, att, cols, label):
    df = pd.DataFrame({"GAME_ID": [1, 2], cols[0]: [made, 2], cols[1]: [att, 5]})
    issues = dc.check_log(df)
    assert [(i["game"], i["check"]) for i in issues] == [("1", label)]


@pytest.mark.parametrize("blank", [None, 0])
def test_made_without_attempts_is_not_flagged(blank):
    """Conversions logged without attempts are a supported, untracked case.

    Blank and 0 both mean "not tracked" everywhere else: the entry form
    writes `int(td_att) if td_att else ""`, so a 0 leaves it as blank,
    and `game_log.efficiency_rates` treats `(conv == 0) & (att == 0)` as
    a sentinel rather than a 0-for-0 game. A Sheet or CSV — the input
    this check exists for — is the one place that still writes the 0,
    so the two have to read the same here too.
    """
    df = pd.DataFrame({"Third_Down_Conv": [6, 2], "Third_Down_Att": [blank, blank],
                       "RZ_TD_Made": [3, 1], "RZ_Att": [blank, 2]})
    assert dc.check_log(df) == []


def test_zero_attempts_cannot_skew_the_rate_it_is_checked_against():
    """Why 0 attempts is exempt and not merely tolerated.

    The check earns its place by protecting the KPI rates, and
    `game_log._rate` already filters on `a > 0`, so a zero-attempt row
    cannot reach them. Flagging it would send the user to the box score
    over a number nothing reads.
    """
    with_zero = pd.DataFrame({"Third_Down_Conv": [6, 5],
                              "Third_Down_Att": [0, 10]})
    assert (game_log.efficiency_rates(with_zero)["third_down_pct"]
            == game_log.efficiency_rates(with_zero.iloc[1:])["third_down_pct"])


def test_the_all_clear_names_every_category_it_checked():
    """The clean-state caption enumerates the checks by name, so a new
    check has to be added to it or the app under-reports what it read.

    Parsed rather than grepped: the caption is two adjacent string
    literals, and which words straddle the join moves whenever the
    wording is reflowed. `ast` folds them into the one string the user
    actually sees.
    """
    import ast
    import pathlib
    app = pathlib.Path(__file__).resolve().parent.parent / "app.py"
    tree = ast.parse(app.read_text(encoding="utf-8"))
    captions = [
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and node.args
        and isinstance(node.func, ast.Attribute) and node.func.attr == "caption"
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and node.args[0].value.startswith("✅ Data checks:")
    ]
    assert len(captions) == 1, captions
    for word in ("yards", "scores", "time of possession", "efficiency"):
        assert word in captions[0], f"{word!r} missing from {captions[0]!r}"
