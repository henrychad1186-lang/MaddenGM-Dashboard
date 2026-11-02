"""The catch-up grid's data: what to show, and what the user changed.

Lives here rather than in `app.py` so it can be tested. Nothing under
`tests/` can import `app.py` — importing it runs the whole Streamlit
script — so logic left in that file is only ever exercised through a
browser, and the grid is drawn on a canvas that a synthetic keypress
cannot reliably edit. The rendering stays in `app.py`; the two
functions that decide what is written live here.
"""

import pandas as pd

from src import game_log
from src import schemes

# Season and Week first because placement is what the rest of the app
# is waiting on: the duplicate-week check, the bye planner and
# `next_season_week` are all inert until a game has a place in time.
NUMERIC = ["Season", "Week", "Third_Down_Att", "Third_Down_Conv",
           "RZ_Att", "RZ_TD_Made"]
COLUMNS = NUMERIC + list(schemes.SCHEME_COLUMNS)


def _empty() -> pd.DataFrame:
    """A frame with the grid's columns and no rows.

    One definition, so the two ways of having nothing to show cannot
    disagree about the schema.
    """
    return pd.DataFrame(columns=["Game", "Matchup"] + COLUMNS)


def frame(existing: pd.DataFrame, label) -> pd.DataFrame:
    """One row per logged game, with every editable column present.

    Columns absent from the CSV are added empty rather than skipped: a
    scheme that has never been recorded is exactly the one needing a
    box, and three of the four are absent on a fresh log.
    """
    rows = []
    if existing is None or existing.empty or "GAME_ID" not in existing.columns:
        return _empty()
    for game_id in [int(v) for v in pd.to_numeric(
            existing["GAME_ID"], errors="coerce").dropna()]:
        current = game_log.row_for_game(existing, game_id)
        row = {"Game": game_id, "Matchup": label(existing, game_id)}
        for column in NUMERIC:
            value = pd.to_numeric(current.get(column), errors="coerce")
            row[column] = None if pd.isna(value) else int(value)
        for column in schemes.SCHEME_COLUMNS:
            row[column] = schemes.normalize(current.get(column), column) or ""
        rows.append(row)
    if not rows:
        # The guard above passes for a log that has rows and a GAME_ID
        # column whose values are all blank or unparseable. The loop
        # then yields nothing, and a frame built from no rows has no
        # columns, so the cast below raised KeyError: 'Season'. The
        # grid is built unconditionally on Franchise Home, inside an
        # expander whose body runs whether or not it is open, so that
        # took the dashboard down rather than leaving those games
        # uneditable.
        return _empty()
    out = pd.DataFrame(rows)
    # Numeric, so an edit comes back as a number rather than text.
    #
    # The editor draws every empty cell as the word "None" whatever is
    # behind it — checked in isolation against float NaN, Int64 pd.NA,
    # object None and "", all four identical — so the dtype cannot fix
    # that display and the caption says what it means instead.
    for column in NUMERIC:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    return out


def changes(before: pd.DataFrame, after: pd.DataFrame) -> dict:
    """`{game_id: {column: value}}` for the cells actually moved.

    Only changed cells are sent. Writing every cell back would rewrite
    rows nobody touched, and `game_log.update_games` splices bytes
    precisely so untouched rows keep theirs.

    Clearing a cell is deliberately not an edit. The writer has no way
    to say "unset", and blanking a recorded number is the one mis-click
    that would be silently destructive — so a value can be corrected
    but not erased here.
    """
    out: dict = {}
    if before is None or after is None or before.empty or after.empty:
        return out
    base = before.set_index("Game")
    # A log can carry the same GAME_ID twice. `base.loc[id]` is then a
    # frame rather than a row and every comparison below raises "The
    # truth value of a Series is ambiguous", which aborts the whole
    # Streamlit run — even when the edit was to a different, unique
    # game. Those rows are left for `update_games` to refuse by name.
    ambiguous = set(base.index[base.index.duplicated(keep=False)])
    for _, row in after.iterrows():
        game_id = int(row["Game"])
        if game_id not in base.index or game_id in ambiguous:
            continue
        old = base.loc[game_id]
        fields = {}
        for column in NUMERIC:
            wanted = pd.to_numeric(row.get(column), errors="coerce")
            if pd.isna(wanted):
                continue
            was = pd.to_numeric(old.get(column), errors="coerce")
            if pd.isna(was) or int(wanted) != int(was):
                fields[column] = int(wanted)
        for column in schemes.SCHEME_COLUMNS:
            wanted = schemes.normalize(row.get(column), column)
            # Blank is "left alone", not "erase", the same as a cleared
            # number above — the contract this function documents was
            # only being honoured on the numeric branch, so clearing a
            # box wrote the empty string over a recorded playbook.
            # Clearing one is still supported on *Correct a logged
            # game*, which says so in as many words.
            if wanted and wanted != schemes.normalize(old.get(column), column):
                fields[column] = wanted
        if fields:
            out[game_id] = fields
    return out
