"""
Single reader for data/packers_roster.csv.

`roster.py` and `trade_engine.py` each used to call `pd.read_csv` on this
file and normalise it their own way. That is the same duplication that
produced the dead-cap bug — two readers of one file drifting apart — and
it bit again when the roster was exported with different column headings:
both loaders raised `KeyError: 'Pos'` at import, which took the whole app
down, not just the tests.

One reader now, which accepts either heading style.

The exported schema drops the six physical attributes (SPD/ACC/AGI/COD/
STR/AWR) entirely. Nothing here invents them: every consumer reads them
with `.get()` and skips what is missing, so the athleticism term in
`get_trade_value`, the Trade Machine radar chart and the AI GM's
strengths/weaknesses simply have less to work with until those columns
come back.
"""

import pandas as pd

# Exported heading -> the name the code uses. Applied only when the
# canonical column is absent, so a file already in canonical form is
# untouched.
COLUMN_ALIASES = {
    "Player Name": "Name",
    "Position": "Pos",
    "Dev Trait": "Dev",
    "Cap Savings": "Savings",
    "Cap Penalty": "Penalty",
}

# Madden's in-game label for the tier above Superstar. The trade engine's
# DEV_MULTIPLIERS keys it as "Superstar X"; without this an X-Factor
# player would silently fall back to the 1.00 "Normal" multiplier.
DEV_ALIASES = {
    "X-Factor": "Superstar X",
}

# Columns the rest of the app requires to exist after loading.
REQUIRED_COLUMNS = ["Name", "Pos", "Age", "OVR"]


def normalize_roster_df(df: pd.DataFrame) -> pd.DataFrame:
    """Rename exported columns to canonical ones and normalise Dev values.

    Returns a copy; the caller's frame is left alone.
    """
    df = df.copy()

    renames = {
        source: target
        for source, target in COLUMN_ALIASES.items()
        if source in df.columns and target not in df.columns
    }
    if renames:
        df = df.rename(columns=renames)

    if "Dev" in df.columns:
        df["Dev"] = df["Dev"].replace(DEV_ALIASES)

    # The export is a single team's roster and carries no Team column.
    if "Team" not in df.columns:
        df["Team"] = "GB"
    if "Dev" not in df.columns:
        df["Dev"] = "Normal"

    return df


def load_roster_csv(path: str) -> pd.DataFrame:
    """Read and normalise the roster CSV at `path`."""
    return normalize_roster_df(pd.read_csv(path))


def try_load_roster_csv(path: str):
    """Best-effort read of a roster CSV.

    Returns (df, source_columns, error_message), where df is None on read
    failure and error_message is None on success.
    """
    try:
        raw = pd.read_csv(path)
    except (OSError, UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        return None, [], (
            f"Could not read roster CSV ({type(exc).__name__}): {exc}"
        )
    return normalize_roster_df(raw), list(raw.columns), None


def missing_required_columns(df: pd.DataFrame) -> "list[str]":
    """Required columns absent after normalisation (empty when loadable)."""
    return [c for c in REQUIRED_COLUMNS if c not in df.columns]


def to_source_schema(df: pd.DataFrame, source_columns: "list[str]") -> pd.DataFrame:
    """Rename canonical columns back to the headings a file was read with.

    Writing the roster back out (the AI GM Assistant's "Save to roster
    CSV") would otherwise silently rewrite an exported file into the
    canonical schema, quietly changing headings the user did not choose.
    """
    reverse = {
        target: source
        for source, target in COLUMN_ALIASES.items()
        if source in source_columns and target in df.columns
    }
    return df.rename(columns=reverse) if reverse else df
