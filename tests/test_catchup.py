"""The catch-up grid: what it shows, and what it writes.

The grid is drawn on a canvas that a synthetic keypress cannot
reliably edit — a Playwright click selects a cell but typing into it
does not register — so driving it in a browser proves only that it
renders. These exercise the two functions that decide what reaches the
CSV, which is the part that can be wrong destructively.
"""

import pandas as pd
import pytest

from src import catchup
from src import game_log
from src import schemes


def _label(df, game_id):
    return f"#{game_id}"


@pytest.fixture
def log():
    return pd.DataFrame([
        {"GAME_ID": 1, "Season": None, "Week": None, "Opponent": "CHI",
         "Third_Down_Att": 11, "Third_Down_Conv": 4, "Playbook": "Air Raid"},
        {"GAME_ID": 2, "Season": 2026, "Week": 3, "Opponent": "DET",
         "Third_Down_Att": None, "Third_Down_Conv": None, "Playbook": ""},
    ])


def test_every_editable_column_gets_a_box(log):
    """Three of the four scheme columns are absent from a fresh log.

    Skipping absent columns would hide exactly the ones that have never
    been recorded, which are the ones the grid exists to fill.
    """
    out = catchup.frame(log, _label)
    for column in catchup.COLUMNS:
        assert column in out.columns, column
    assert list(out["Game"]) == [1, 2]
    assert out.loc[0, "Third_Down_Att"] == 11
    assert pd.isna(out.loc[0, "Season"])


def test_an_empty_log_still_yields_the_columns(log):
    out = catchup.frame(pd.DataFrame(), _label)
    assert out.empty and "Season" in out.columns


def test_a_log_whose_ids_are_all_unusable_still_yields_the_columns():
    """Rows exist and GAME_ID exists, but no id parses.

    The opening guard passes — the frame is not empty and the column is
    there — and then the loop produces nothing, so the result had no
    columns at all and casting raised `KeyError: 'Season'`. The grid is
    built unconditionally on Franchise Home, inside an expander whose
    body runs whether or not it is open, so that took the whole
    dashboard down rather than leaving these games uneditable.
    """
    df = pd.DataFrame([{"GAME_ID": "", "Opponent": "CHI"},
                       {"GAME_ID": "n/a", "Opponent": "DET"}])
    out = catchup.frame(df, _label)
    assert out.empty
    for column in catchup.COLUMNS:
        assert column in out.columns, column


def test_only_edited_cells_are_written(log):
    before = catchup.frame(log, _label)
    after = before.copy()
    after.loc[0, "Season"] = 2026
    after.loc[0, "Week"] = 1
    assert catchup.changes(before, after) == {1: {"Season": 2026, "Week": 1}}


def test_an_untouched_grid_writes_nothing(log):
    before = catchup.frame(log, _label)
    assert catchup.changes(before, before.copy()) == {}


def test_clearing_a_cell_is_not_an_edit(log):
    """The one mis-click that would be silently destructive.

    `update_games` has no way to say "unset", so a blanked cell must
    read as "left alone" rather than as a value to write. Game 1 has a
    real 11 attempts; emptying that box must not reach the CSV.
    """
    before = catchup.frame(log, _label)
    after = before.copy()
    after.loc[0, "Third_Down_Att"] = None
    assert catchup.changes(before, after) == {}


def test_a_scheme_can_be_set_on_a_game_that_never_had_one(log):
    before = catchup.frame(log, _label)
    after = before.copy()
    after.loc[1, schemes.DEF_SCHEME] = "Cover 3"
    assert catchup.changes(before, after) == {2: {schemes.DEF_SCHEME: "Cover 3"}}


def test_whitespace_alone_is_not_a_scheme_change(log):
    """`normalize` folds spacing, so a stray space is not an edit.

    A trailing space used to be enough to start a rival scheme that
    looked identical in the UI and split the Schemes comparison in two.
    """
    before = catchup.frame(log, _label)
    after = before.copy()
    after.loc[0, schemes.OFF_SCHEME] = "  Air   Raid "
    assert catchup.changes(before, after) == {}


def test_what_the_grid_produces_is_what_the_writer_accepts(tmp_path):
    """The two halves, joined: edit the frame, write it, read it back.

    Neither function is useful if the fields it emits are ones
    `update_games` refuses, and that contract is the kind that drifts.
    """
    path = tmp_path / "game_logs.csv"
    path.write_text("GAME_ID,Season,Week,Team,Third_Down_Att\n"
                    "1,,,GB,\n2,,,GB,\n")
    existing = game_log.read_log(str(path))
    before = catchup.frame(existing, _label)
    after = before.copy()
    after.loc[0, "Season"] = 2026
    after.loc[0, "Week"] = 1
    after.loc[0, "Third_Down_Att"] = 12
    after.loc[1, "Season"] = 2026
    after.loc[1, "Week"] = 2
    after.loc[1, schemes.DEF_SCHEME] = "Cover 3"

    ok, message = game_log.update_games(
        str(path), catchup.changes(before, after))
    assert ok, message
    out = pd.read_csv(path).set_index("GAME_ID")
    assert out.loc[1, "Week"] == 1 and out.loc[2, "Week"] == 2
    assert out.loc[1, "Third_Down_Att"] == 12
    assert out.loc[2, "Def_Scheme"] == "Cover 3"


def test_a_grid_that_double_books_a_week_is_refused(tmp_path):
    path = tmp_path / "game_logs.csv"
    path.write_text("GAME_ID,Season,Week,Team\n1,,,GB\n2,,,GB\n")
    existing = game_log.read_log(str(path))
    before = catchup.frame(existing, _label)
    after = before.copy()
    after.loc[0, ["Season", "Week"]] = [2026, 5]
    after.loc[1, ["Season", "Week"]] = [2026, 5]
    was = path.read_bytes()
    ok, message = game_log.update_games(
        str(path), catchup.changes(before, after))
    assert not ok and "week 5" in message
    assert path.read_bytes() == was
