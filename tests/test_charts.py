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


def test_no_derived_size_column_is_read_back_in_a_hover():
    """The stand-in size must not be shown as the stat it stands for.

    `bubble_size` fills a missing value so plotly will draw the point;
    a hover read off that column then prints the fill as the number.
    A game logged without its yardage read `Total yards=1`. Labelling
    that column correctly is not enough — the number itself is the
    fill. It has to be hidden from the hover outright, with
    `bubble_text` showing the real one in its place.
    """
    source = _app_source()
    shared = _chart_labels()
    derived = set(re.findall(r'size="(_\w+)"', source))
    assert derived, "no derived size columns found — the naming changed"
    for name in derived:
        assert f'"{name}": False' in source, (
            f'size="{name}" is not hidden from its chart\'s hover, so the '
            "stand-in it carries for a missing value is on show")
        assert name not in shared, (
            f"{name} is labelled in _CHART_LABELS, where a reader cannot "
            "tell it apart from a column holding a real measurement")


def test_every_bubble_chart_shows_the_real_column_not_the_size():
    """Each `bubble_size` call is paired with a `bubble_text` call.

    The pairing is the whole guard: without it the chart is back to
    showing the fill. Both bubble charts in `app.py` — the Strategy
    Map and the turnovers scatter — have to do it.
    """
    source = _app_source()
    sizes = source.count("charts.bubble_size(")
    texts = source.count("charts.bubble_text(")
    assert sizes >= 2, f"expected both bubble charts, found {sizes}"
    assert sizes == texts, (
        f"{sizes} bubble_size call(s) but {texts} bubble_text — a chart "
        "sizes its bubbles from a filled column without saying so")


def test_a_missing_value_reads_as_missing_not_as_a_number():
    """`not recorded`, not `1` and not `0`: both read as a measurement."""
    text = charts.bubble_text(pd.Series([380.0, None, "12%", 0]))
    assert list(text) == ["380", charts.MISSING_TEXT, charts.MISSING_TEXT, "0"]


def test_a_whole_number_is_not_shown_with_a_decimal_tail():
    """`380`, not `380.0` — the log holds whole yards."""
    assert list(charts.bubble_text(pd.Series([380.0, 412.0]))) == ["380", "412"]


def test_the_text_lines_up_with_the_sizes_it_explains():
    """One entry per point, in the same order, or the hover is wrong."""
    values = pd.Series([350, None, 420, "oops"])
    assert len(charts.bubble_text(values)) == len(charts.bubble_size(values))
