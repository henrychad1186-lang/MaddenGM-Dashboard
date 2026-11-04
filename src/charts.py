"""Chart encodings that cannot take a missing value.

Plotly refuses NaN for a marker size outright, so a single blank cell
in the column driving `size=` raises and stops the Streamlit script —
blanking that tab and every tab after it. A blank stat cell is an
ordinary state here, not a corruption: `data_checks` has a dedicated
"total yards missing" check, and the backfill forms exist because
games are logged without their numbers.

`app.py` already learned this twice — the Strategy Map builds its size
column with `fillna`, and the Dynasty timeline drops the rows before
plotting — but the Wear tab's turnovers scatter was still passing
`Total_Yards` straight through. This is that rule in one place, and in
a module a test can import, which `app.py` is not.
"""

import pandas as pd

# Plotly needs a positive number for every point. 1 is the smallest
# bubble it will draw, which is the least misleading stand-in: a game
# whose yardage was never recorded should not look bigger than one
# that was.
_MIN_SIZE = 1


def bubble_size(values) -> pd.Series:
    """`values` as positive numbers, usable as a Plotly `size=` column.

    Anything that is not a number — blank, or text left by one odd
    cell — becomes the minimum size rather than NaN. The point stays on
    the chart, because dropping it would hide a game that has a real x
    and y, and its size simply carries no information.
    """
    numeric = pd.to_numeric(pd.Series(values), errors="coerce")
    return numeric.fillna(_MIN_SIZE).clip(lower=_MIN_SIZE)


# What the tooltip says in place of a number nobody recorded. Not "0"
# and not the stand-in size: both read as a measurement.
MISSING_TEXT = "not recorded"


def bubble_text(values) -> pd.Series:
    """What the hover should say for a column `bubble_size` stands in for.

    `bubble_size` fills a missing value with `_MIN_SIZE` so plotly will
    draw the point at all, and that stand-in must never reach the
    tooltip. A hover read off the size column shows a game logged
    without its yardage as `Total yards=1` — a number nobody recorded,
    sitting where the recorded one belongs, which is the same mistake
    as the chart claiming the game was a one-yard afternoon.

    So the chart hides its size column from the hover and shows this
    instead: the value where there is one, and plainly nothing where
    there is not.
    """
    numeric = pd.to_numeric(pd.Series(values), errors="coerce")
    return numeric.map(lambda v: MISSING_TEXT if pd.isna(v) else f"{v:g}")
