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


class TestTryLoadRosterCsv:

    def test_returns_error_for_malformed_csv_instead_of_raising(self, tmp_path):
        bad_csv = tmp_path / "bad_roster.csv"
        bad_csv.write_text('Name,Pos,Age,OVR\n"unterminated')

        df, source_columns, error = roster_csv.try_load_roster_csv(str(bad_csv))

        assert df is None
        assert source_columns == []
        assert error is not None
        assert "Could not read roster CSV" in error


class TestToSourceSchema:

    def test_renames_back_for_an_exported_file(self):
        source = list(_exported_row())
        df = pd.DataFrame([_canonical_row()])
        out = roster_csv.to_source_schema(df, source)
        assert "Player Name" in out.columns and "Name" not in out.columns
        assert "Position" in out.columns and "Pos" not in out.columns

    def test_canonical_file_is_written_back_unchanged(self):
        source = list(_canonical_row())
        df = pd.DataFrame([_canonical_row()])
        out = roster_csv.to_source_schema(df, source)
        assert "Name" in out.columns and "Player Name" not in out.columns

    def test_round_trip_preserves_headings(self):
        raw = pd.DataFrame([_exported_row()])
        source = list(raw.columns)
        normalized = roster_csv.normalize_roster_df(raw)
        # Team is added by the loader, so it is expected on the way out.
        out = roster_csv.to_source_schema(
            normalized.drop(columns=["Team"]), source)
        assert list(out.columns) == source

    def test_empty_source_columns_is_a_no_op(self):
        df = pd.DataFrame([_canonical_row()])
        assert list(roster_csv.to_source_schema(df, []).columns) == list(df.columns)


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

    def test_roster_module_falls_back_to_demo_on_read_error(self, tmp_path):
        from src import roster as roster_mod

        bad_csv = tmp_path / "bad_roster.csv"
        bad_csv.write_text('Name,Pos,Age,OVR\n"unterminated')

        old_path = roster_mod._ROSTER_CSV
        try:
            roster_mod._ROSTER_CSV = str(bad_csv)
            df = roster_mod._load_rosters()
        finally:
            roster_mod._ROSTER_CSV = old_path

        assert len(df) == 1
        assert df.iloc[0]["Name"] == "Demo Player"
        assert roster_mod.SOURCE_COLUMN_ISSUES
        assert "Could not read roster CSV" in roster_mod.SOURCE_COLUMN_ISSUES[0]
