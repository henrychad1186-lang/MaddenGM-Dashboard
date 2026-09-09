"""
Regression cover for roster loading failures found in code review.

Each case here previously either killed the app at import or silently
destroyed the user's roster file. `_load_rosters` runs at module import,
so anything it raises happens before Streamlit can render the panel that
would have explained the problem.
"""

import importlib

import pandas as pd
import pytest


@pytest.fixture
def roster_module(tmp_path, monkeypatch):
    """Import a fresh src.roster pointed at a throwaway CSV path.

    Returns a factory: call it with file contents (or None for "no file")
    and get back the freshly imported module.
    """
    csv_path = tmp_path / "packers_roster.csv"

    def _load(contents: "str | None"):
        if contents is not None:
            csv_path.write_text(contents)
        import src.roster as roster
        monkeypatch.setattr(roster, "_ROSTER_CSV", str(csv_path))
        roster = importlib.reload(roster)
        monkeypatch.setattr(roster, "_ROSTER_CSV", str(csv_path))
        roster.SOURCE_COLUMN_ISSUES.clear()
        roster.SOURCE_COLUMNS.clear()
        roster.UNKNOWN_POSITIONS.clear()
        return roster, roster._load_rosters()

    return _load


class TestLoadNeverRaises:
    """The docstring promised a fallback; these paths did not honour it."""

    def test_empty_file(self, roster_module):
        roster, df = roster_module("")
        assert len(df) == 1  # demo
        assert roster.SOURCE_COLUMN_ISSUES

    def test_header_only_file(self, roster_module):
        roster, df = roster_module("Player Name,Position,Age,OVR\n")
        assert len(df) == 0 or len(df) == 1

    def test_ragged_row_does_not_crash_and_is_caught_downstream(self, roster_module):
        # pandas does not raise on this shape — it silently treats the
        # first field as an index, shifting every column left, so OVR
        # ends up holding "EXTRA". The load must survive it (it used to
        # raise AttributeError once Pos became an int), and
        # validate_roster_df is what surfaces the corruption.
        from src.roster import validate_roster_df
        roster, df = roster_module(
            "Player Name,Position,Age,OVR\nA. Player,QB,25,80,EXTRA\n")
        assert not df.empty
        assert any("not a number" in w for w in validate_roster_df(df))

    def test_blank_position_cell(self, roster_module):
        # A blank cell arrives as float nan; nan.upper() used to raise
        # AttributeError inside _normalize_pos during import.
        roster, df = roster_module(
            "Player Name,Position,Age,OVR\nA. Player,,25,80\n")
        assert not df.empty

    def test_garbage_contents(self, roster_module):
        roster, df = roster_module("\x00\x01 not a csv at all\n\x02")
        assert len(df) >= 1
        assert roster.SOURCE_COLUMN_ISSUES


class TestBothLoadersSurviveBadFiles:
    """roster.py is not the only importer of this CSV.

    trade_engine.py reads it too, at import, and guarding only roster.py
    left an empty file still raising EmptyDataError from there — the app
    stayed dead. Any check that a bad CSV is survivable has to exercise
    both modules, which is exactly what the roster-only tests missed.
    """

    @pytest.mark.parametrize("contents", [
        "",                                                   # empty
        "Player Name,Position,Age,OVR\n",                     # header only
        "Player Name,Position,Age,OVR\nA. Player,,25,80\n",   # blank position
        "Player Name,Age\nA. Player,25\n",                    # required missing
        "\x00\x01 not a csv\n",                               # garbage
    ])
    def test_trade_engine_import_survives(self, contents, tmp_path, monkeypatch):
        import src.trade_engine as trade_engine
        csv_path = tmp_path / "roster.csv"
        csv_path.write_text(contents)
        monkeypatch.setattr(trade_engine, "_ROSTER_CSV", str(csv_path))
        # Must not raise; falls back to the CPU demo teams at minimum.
        df = trade_engine._load_trade_rosters()
        assert not df.empty
        assert set(df["Team"]) >= {"CHI", "DET", "MIN"}


class TestSourceColumnsGuard:
    """SOURCE_COLUMNS is the signal persist_roster trusts before writing."""

    def test_recorded_on_a_good_load(self, roster_module):
        roster, df = roster_module(
            "Player Name,Position,Age,OVR\nA. Player,QB,25,80\n")
        assert roster.SOURCE_COLUMNS == ["Player Name", "Position", "Age", "OVR"]

    def test_stays_empty_when_a_required_column_is_missing(self, roster_module):
        # Previously recorded before the check, so a fallback-to-demo still
        # looked writable and "Save to roster CSV" replaced the real file
        # with the single demo row.
        roster, df = roster_module("Player Name,Position,Age\nA. Player,QB,25\n")
        assert roster.SOURCE_COLUMNS == []
        assert len(df) == 1

    def test_stays_empty_when_the_file_is_unreadable(self, roster_module):
        roster, df = roster_module("")
        assert roster.SOURCE_COLUMNS == []

    def test_error_names_the_files_own_headings(self, roster_module):
        # The message used to list post-normalisation names, telling the
        # user to look for columns their file does not contain.
        roster, df = roster_module("Player Name,Position,Age\nA. Player,QB,25\n")
        message = roster.SOURCE_COLUMN_ISSUES[0]
        assert "Player Name" in message and "Position" in message
        assert "OVR" in message  # the missing one


class TestLinebackerPositions:
    """SAM/WILL/MIKE are Madden linebacker labels, not offensive players."""

    @pytest.mark.parametrize("pos", ["SAM", "WILL", "MIKE"])
    def test_classified_as_defense(self, pos):
        from src.roster import _assign_group
        assert _assign_group(pos) == "Defense"

    @pytest.mark.parametrize("pos,expected", [
        ("SAM", "OLB"), ("WILL", "OLB"), ("MIKE", "MLB"),
        ("REDG", "EDGE"), ("LEDG", "EDGE"), ("LOLB", "OLB"),
    ])
    def test_normalized_to_a_weighted_position(self, pos, expected):
        from src.roster import _normalize_pos
        from src.trade_engine import POSITION_WEIGHTS
        assert _normalize_pos(pos) == expected
        # An unweighted position silently takes the 0.85 default.
        assert expected in POSITION_WEIGHTS

    def test_normalize_handles_a_nan_cell(self):
        from src.roster import _normalize_pos
        assert _normalize_pos(float("nan")) == "NAN"

    def test_unknown_positions_are_recorded(self):
        from src.roster import _assign_group, UNKNOWN_POSITIONS
        UNKNOWN_POSITIONS.discard("ZZZ")
        _assign_group("ZZZ")
        assert "ZZZ" in UNKNOWN_POSITIONS


class TestShippedRoster:

    def test_every_position_is_recognised(self):
        from src.roster import (ALL_ROSTERS, _OFFENSE_POS, _DEFENSE_POS,
                                _ST_POS)
        known = _OFFENSE_POS | _DEFENSE_POS | _ST_POS
        unknown = {p for p in ALL_ROSTERS["Pos"].unique() if p not in known}
        assert not unknown, f"unclassified positions default to Offense: {unknown}"

    def test_linebackers_are_not_filed_as_offense(self):
        from src.roster import ALL_ROSTERS
        backers = ALL_ROSTERS[ALL_ROSTERS["Pos"].isin(["OLB", "MLB"])]
        assert (backers["Group"] == "Defense").all()


class TestPersistRoster:

    def test_refuses_to_write_when_the_load_fell_back(self, monkeypatch):
        from src import ai_gm, roster as roster_mod
        monkeypatch.setattr(roster_mod, "SOURCE_COLUMNS", [])
        assert ai_gm.persist_roster("GB", [{"Name": "X", "Pos": "QB"}]) is False

    def test_no_extras_is_a_no_op_success(self):
        from src import ai_gm
        assert ai_gm.persist_roster("GB", []) is True

    def test_appends_without_disturbing_existing_rows(self, tmp_path, monkeypatch):
        from src import ai_gm, roster as roster_mod
        csv_path = tmp_path / "roster.csv"
        original = ("Player Name,Position,Age,OVR,Dev Trait\n"
                    "M. Parsons,REDG,27,98,X-Factor\n")
        csv_path.write_text(original)

        monkeypatch.setattr(roster_mod, "_ROSTER_CSV", str(csv_path))
        monkeypatch.setattr(roster_mod, "SOURCE_COLUMNS",
                            ["Player Name", "Position", "Age", "OVR", "Dev Trait"])

        ok = ai_gm.persist_roster("GB", [{
            "Name": "R. Rookie", "Pos": "WR", "Age": 22, "OVR": 74,
            "Dev": "Superstar X", "_id": "x1",
        }])
        assert ok

        out = pd.read_csv(csv_path)
        assert len(out) == 2
        # The pre-existing row is untouched: REDG not rewritten to EDGE,
        # X-Factor not rewritten to Superstar X, no Team column added.
        assert out.iloc[0]["Position"] == "REDG"
        assert out.iloc[0]["Dev Trait"] == "X-Factor"
        assert "Team" not in out.columns
        assert "_id" not in out.columns
        # The appended row uses the file's own dev vocabulary.
        assert out.iloc[1]["Dev Trait"] == "X-Factor"
