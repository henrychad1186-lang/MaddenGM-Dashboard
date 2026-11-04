"""Chart encodings that cannot take a missing value.

Plotly rejects NaN for a marker size outright, so one blank cell in the
column driving `size=` raises and stops the script — taking the tab and
every tab after it. `app.py` already guards two such charts (the
Strategy Map builds its size with `fillna`, the Dynasty timeline drops
the rows), and this is the rule those two follow, in a place a test can
reach.
"""

import ast
import pathlib
import re

import pandas as pd
import pytest

from src import charts


def test_a_missing_value_does_not_reach_plotly():
    """The crash: `size="Total_Yards"` with one blank cell.

    `Invalid element(s) received for the 'size' property of
    scatter.marker: [nan]` — raised on the Wear tab and blanked it.
    """
    sizes = charts.bubble_size(pd.Series([350.0, None, 420.0]))
    assert not sizes.isna().any(), list(sizes)


def test_text_is_treated_as_missing_not_as_a_crash():
    """A column left as text by one odd cell must not raise either."""
    sizes = charts.bubble_size(pd.Series(["350", "12%", "420"]))
    assert not sizes.isna().any(), list(sizes)
    assert sizes.iloc[0] == 350 and sizes.iloc[2] == 420


def test_real_values_are_not_rescaled():
    """The guard must not quietly change the sizes it was given."""
    sizes = charts.bubble_size(pd.Series([350, 400, 420]))
    assert list(sizes) == [350, 400, 420]


def test_sizes_stay_positive():
    """Plotly also refuses a negative marker size.

    `Point_Differential` is not used for size today, but nothing stops
    a future caller passing a column that goes below zero.
    """
    assert (charts.bubble_size(pd.Series([-5, 0, 10])) > 0).all()


@pytest.mark.parametrize("empty", [pd.Series([], dtype=float),
                                   pd.Series([None, None], dtype=object)])
def test_a_column_with_nothing_in_it_is_still_plottable(empty):
    sizes = charts.bubble_size(empty)
    assert not sizes.isna().any()


# The size guard above keeps a chart from raising. These keep it from
# lying: plotly builds the hover text from `labels=`, and an encoding
# whose label is already spoken for is dropped rather than repeated. A
# size column derived from one stat and labelled with another's name
# therefore replaces that stat in the tooltip instead of sitting
# beside it.
#
# `app.py` runs Streamlit at import, so a test cannot import it; the
# Remodel HQ scope tests parse their source for the same reason.
def _app_source() -> str:
    return (pathlib.Path(__file__).resolve().parent.parent
            / "app.py").read_text(encoding="utf-8")


def _chart_labels() -> dict:
    """`app.py`'s `_CHART_LABELS`, read without importing the app."""
    for node in ast.parse(_app_source()).body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "_CHART_LABELS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("_CHART_LABELS not found in app.py")


def test_no_two_columns_share_a_chart_label():
    """Two columns, one label: plotly keeps only one of the encodings.

    `size="_size"` labelled "Points scored" collided with `Points_For`
    on the turnovers chart, and the hover went from
    `Points scored=%{y}` + `Total yards=%{marker.size}` to a single
    `Points scored=%{marker.size}` — the points gone, the yardage
    wearing their name.
    """
    seen: "dict[str, str]" = {}
    clashes = []
    for column, label in _chart_labels().items():
        if label in seen:
            clashes.append(f"{seen[label]!r} and {column!r} are both "
                           f"labelled {label!r}")
        seen[label] = column
    assert not clashes, "; ".join(clashes)


def test_every_derived_size_column_carries_its_own_label():
    """A size column with no label shows plotly's raw `_yds_size`.

    These are deliberately absent from `_CHART_LABELS`: each is
    labelled at its own chart, where its label can be read against the
    axes it will sit beside. One shared entry is what let the turnovers
    chart inherit the Strategy Map's wording.
    """
    source = _app_source()
    shared = _chart_labels()
    derived = set(re.findall(r'size="(_\w+)"', source))
    assert derived, "no derived size columns found — the naming changed"
    for name in derived:
        assert f'"{name}": "' in source, f'size="{name}" has no label'
        assert name not in shared, (
            f"{name} is labelled in _CHART_LABELS, where its label "
            "cannot be checked against the axes of the chart using it")
