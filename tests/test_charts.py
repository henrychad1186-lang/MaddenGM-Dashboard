"""Chart encodings that cannot take a missing value.

Plotly rejects NaN for a marker size outright, so one blank cell in the
column driving `size=` raises and stops the script — taking the tab and
every tab after it. `app.py` already guards two such charts (the
Strategy Map builds its size with `fillna`, the Dynasty timeline drops
the rows), and this is the rule those two follow, in a place a test can
reach.
"""

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
