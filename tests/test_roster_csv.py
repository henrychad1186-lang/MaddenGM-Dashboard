"""
Tests for the shared roster CSV reader.

Regression cover for the break that took the whole app down: a roster
exported with different column headings ("Player Name", "Position",
"Dev Trait", ...) made both `roster.py` and `trade_engine.py` raise
`KeyError: 'Pos'` at import, so `streamlit run app.py` failed before
rendering anything.
"""

import pandas as pd

from src import roster_csv


def _exported_row(**overrides):
    """A row in the exported heading style (no physical attributes)."""
    row = {
        "Player Name": "M. Parsons",
        "Position": "REDG",
        "Age": 27,
        "OVR": 98,
        "Dev Trait": "X-Factor",
        "Cap Savings": "$750K",
        "Cap Penalty": "$105M",
        "Trade Value Index": 81.4,
    }
    row.update(overrides)
    return row


def _canonical_row(**overrides):
    """A row already using the names the code reads."""
    row = {
        "Name": "M. Parsons", "Pos": "EDGE", "Age": 27, "OVR": 98,
        "Dev": "Superstar X", "Savings": "$750K", "Penalty": "$105M",
        "Team": "GB",
    }
    row.update(overrides)
    return row


class TestNormalizeRosterDf:

    def test_exported_headings_are_renamed(self):
        df = roster_csv.normalize_roster_df(pd.DataFrame([_exported_row()]))
        for column in ["Name", "Pos", "Dev", "Savings", "Penalty"]:
            assert column in df.columns
        assert df["Name"].iloc[0] == "M. Parsons"
        assert df["Pos"].iloc[0] == "REDG"
        assert df["Savings"].iloc[0] == "$750K"

    def test_canonical_file_is_left_alone(self):
        df = roster_csv.normalize_roster_df(pd.DataFrame([_canonical_row()]))
        assert df["Name"].iloc[0] == "M. Parsons"
        assert df["Dev"].iloc[0] == "Superstar X"

    def test_x_factor_maps_to_the_engines_dev_tier(self):
        # Without this an X-Factor player falls back to the 1.00 "Normal"
        # multiplier in trade_engine.DEV_MULTIPLIERS.
        df = roster_csv.normalize_roster_df(pd.DataFrame([_exported_row()]))
        assert df["Dev"].iloc[0] == "Superstar X"

    def test_other_dev_values_are_untouched(self):
        df = roster_csv.normalize_roster_df(
            pd.DataFrame([_exported_row(**{"Dev Trait": "Superstar"})]))
        assert df["Dev"].iloc[0] == "Superstar"

    def test_missing_team_defaults_to_gb(self):
        df = roster_csv.normalize_roster_df(pd.DataFrame([_exported_row()]))
        assert df["Team"].iloc[0] == "GB"

    def test_missing_dev_column_defaults_to_normal(self):
        row = _exported_row()
        del row["Dev Trait"]
        df = roster_csv.normalize_roster_df(pd.DataFrame([row]))
        assert df["Dev"].iloc[0] == "Normal"

    def test_canonical_column_wins_when_both_present(self):
        # A file carrying both must not have its real column clobbered.
        df = roster_csv.normalize_roster_df(
            pd.DataFrame([{"Name": "Real", "Player Name": "Other",
                           "Pos": "QB", "Age": 25, "OVR": 80}]))
        assert df["Name"].iloc[0] == "Real"

    def test_does_not_mutate_the_caller_frame(self):
        raw = pd.DataFrame([_exported_row()])
        roster_csv.normalize_roster_df(raw)
        assert "Name" not in raw.columns

    def test_extra_export_columns_are_preserved(self):
        df = roster_csv.normalize_roster_df(pd.DataFrame([_exported_row()]))
        assert df["Trade Value Index"].iloc[0] == 81.4


class TestMissingRequiredColumns:

    def test_exported_file_satisfies_requirements(self):
        df = roster_csv.normalize_roster_df(pd.DataFrame([_exported_row()]))
        assert roster_csv.missing_required_columns(df) == []

    def test_reports_what_is_absent(self):
        df = pd.DataFrame([{"Name": "A", "Age": 25}])
        assert roster_csv.missing_required_columns(df) == ["Pos", "OVR"]

    def test_physical_attributes_are_not_required(self):
        # The export drops SPD/ACC/AGI/COD/STR/AWR; consumers read them
        # with .get() and skip what is missing, so the file is still usable.
        df = roster_csv.normalize_roster_df(pd.DataFrame([_exported_row()]))
        assert roster_csv.missing_required_columns(df) == []
        assert "SPD" not in df.columns


class TestRowsToSourceSchema:
    """Appending must not disturb what is already in the file.

    Replaces tests for an earlier `to_source_schema`, which rebuilt the
    whole file from the normalised frame. Those passed only because one
    of them dropped the synthetic `Team` column by hand — the production
    caller did not, so the real round trip added a column and rewrote
    `REDG`->`EDGE` and `X-Factor`->`Superstar X` across every row.
    """

    def _raw(self):
        return pd.DataFrame([_exported_row()])

    def _new_player(self, **overrides):
        player = {"Name": "R. Rookie", "Pos": "WR", "Age": 22, "OVR": 74,
                  "Dev": "Star", "Savings": "$1M", "Penalty": "$0",
                  "Team": "GB", "_id": "abc123"}
        player.update(overrides)
        return player

    def test_output_matches_the_files_columns_exactly(self):
        raw = self._raw()
        out = roster_csv.rows_to_source_schema([self._new_player()], raw)
        assert list(out.columns) == list(raw.columns)

    def test_no_team_column_is_introduced(self):
        # The loader synthesises Team; the export never had it.
        raw = self._raw()
        out = roster_csv.rows_to_source_schema([self._new_player()], raw)
        assert "Team" not in out.columns

    def test_internal_id_is_not_written_out(self):
        raw = self._raw()
        out = roster_csv.rows_to_source_schema([self._new_player()], raw)
        assert "_id" not in out.columns

    def test_values_land_under_the_exported_headings(self):
        raw = self._raw()
        out = roster_csv.rows_to_source_schema([self._new_player()], raw)
        assert out["Player Name"].iloc[0] == "R. Rookie"
        assert out["Position"].iloc[0] == "WR"
        assert out["Cap Savings"].iloc[0] == "$1M"

    def test_dev_matches_the_vocabulary_already_in_the_file(self):
        # The file spells the top tier "X-Factor"; appending "Superstar X"
        # would split one tier across two spellings.
        raw = self._raw()
        out = roster_csv.rows_to_source_schema(
            [self._new_player(Dev="Superstar X")], raw)
        assert out["Dev Trait"].iloc[0] == "X-Factor"

    def test_canonical_file_keeps_canonical_dev_values(self):
        raw = pd.DataFrame([_canonical_row()])
        out = roster_csv.rows_to_source_schema(
            [self._new_player(Dev="Superstar X")], raw)
        assert out["Dev"].iloc[0] == "Superstar X"

    def test_appending_leaves_existing_rows_byte_identical(self):
        raw = self._raw()
        before = raw.to_csv(index=False)
        added = roster_csv.rows_to_source_schema([self._new_player()], raw)
        combined = pd.concat([raw, added], ignore_index=True)
        assert combined.to_csv(index=False).startswith(before.rstrip("\n"))
        assert len(combined) == len(raw) + 1

    def test_missing_field_becomes_empty_not_an_error(self):
        raw = self._raw()
        out = roster_csv.rows_to_source_schema(
            [{"Name": "R. Rookie", "Pos": "WR"}], raw)
        assert out["Trade Value Index"].iloc[0] == ""


class TestRealRosterFile:

    def test_the_shipped_csv_loads(self):
        from src.roster import _ROSTER_CSV
        df = roster_csv.load_roster_csv(_ROSTER_CSV)
        assert roster_csv.missing_required_columns(df) == []
        assert len(df) > 0

    def test_every_dev_value_is_known_to_the_trade_engine(self):
        from src.roster import _ROSTER_CSV
        from src.trade_engine import DEV_MULTIPLIERS
        df = roster_csv.load_roster_csv(_ROSTER_CSV)
        unknown = set(df["Dev"].dropna().unique()) - set(DEV_MULTIPLIERS)
        assert not unknown, f"unmapped dev traits fall back to 1.00: {unknown}"
