"""Tests for validate_roster_df — catches roster data-quality issues
(corrupted names, out-of-range stats, missing fields, duplicates)
automatically instead of by chance, per the "?. ???ams" incident where a
garbled name sat in the CSV since the repo's first commit undetected."""

import pandas as pd

from src.roster import validate_roster_df


def test_clean_data_has_no_warnings():
    df = pd.DataFrame([{"Name": "A. Normal", "Pos": "WR", "OVR": 80, "Age": 25}])
    assert validate_roster_df(df) == []


def test_missing_required_column_is_flagged():
    df = pd.DataFrame([{"Name": "A. Normal", "Pos": "WR", "OVR": 80}])  # no Age
    warnings = validate_roster_df(df)
    assert any("Missing expected column" in w for w in warnings)


def test_question_mark_name_is_flagged_as_possibly_corrupted():
    df = pd.DataFrame([{"Name": "?. ???ams", "Pos": "EDGE", "OVR": 90, "Age": 24}])
    warnings = validate_roster_df(df)
    assert any("corrupted name" in w for w in warnings)


def test_empty_name_is_flagged():
    df = pd.DataFrame([{"Name": "", "Pos": "WR", "OVR": 80, "Age": 25}])
    warnings = validate_roster_df(df)
    assert any("no Name" in w for w in warnings)


def test_ovr_out_of_range_is_flagged():
    df = pd.DataFrame([{"Name": "X. Player", "Pos": "CB", "OVR": 150, "Age": 26}])
    warnings = validate_roster_df(df)
    assert any("outside the normal 1-99 range" in w for w in warnings)


def test_non_numeric_ovr_is_flagged():
    df = pd.DataFrame([{"Name": "Z. Player", "Pos": "RB", "OVR": "not-a-number", "Age": 25}])
    warnings = validate_roster_df(df)
    assert any("is not a number" in w for w in warnings)


def test_unrealistic_age_is_flagged():
    df = pd.DataFrame([{"Name": "Y. Player", "Pos": "QB", "OVR": 80, "Age": 5}])
    warnings = validate_roster_df(df)
    assert any("looks unrealistic" in w for w in warnings)


def test_duplicate_rows_are_flagged():
    df = pd.DataFrame([
        {"Name": "Dup Guy", "Pos": "WR", "OVR": 80, "Age": 25},
        {"Name": "Dup Guy", "Pos": "WR", "OVR": 80, "Age": 25},
    ])
    warnings = validate_roster_df(df)
    assert any("duplicate" in w.lower() for w in warnings)


def test_same_name_different_stats_is_not_flagged_as_duplicate():
    # Two real players can share a name (the AI GM Assistant explicitly
    # allows this) — only exact Name+Pos+OVR+Age matches should trip it.
    df = pd.DataFrame([
        {"Name": "Same Name", "Pos": "WR", "OVR": 80, "Age": 25},
        {"Name": "Same Name", "Pos": "CB", "OVR": 74, "Age": 26},
    ])
    warnings = validate_roster_df(df)
    assert not any("duplicate" in w.lower() for w in warnings)


def test_never_raises_on_malformed_input():
    df = pd.DataFrame([{"Name": None, "Pos": None, "OVR": None, "Age": None}])
    warnings = validate_roster_df(df)
    assert isinstance(warnings, list)
