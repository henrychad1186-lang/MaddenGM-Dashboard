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


def missing_required_columns(df: pd.DataFrame) -> "list[str]":
    """Required columns absent after normalisation (empty when loadable)."""
    return [c for c in REQUIRED_COLUMNS if c not in df.columns]


def rows_to_source_schema(players: "list[dict]", raw: pd.DataFrame) -> pd.DataFrame:
    """Render session-added players as rows matching `raw`'s own schema.

    Used to append to the roster CSV without touching what is already in
    it. An earlier version rebuilt the whole file from the normalised
    frame and renamed the columns back, which looked equivalent but was
    not: normalisation is lossy and one-way. Round-tripping the shipped
    roster through it rewrote every `REDG` to `EDGE` and every `X-Factor`
    to `Superstar X`, and added a `Team` column the file never had —
    silently editing 37 rows the user had not asked to change.

    `REDG` vs `LEDG` cannot be recovered from `EDGE` at all, which is why
    existing rows are now preserved verbatim rather than regenerated.
    """
    reverse_names = {
        target: source
        for source, target in COLUMN_ALIASES.items()
        if source in raw.columns and target not in raw.columns
    }

    # Match the vocabulary already in the file: appending "Superstar X" to
    # a column whose other rows read "X-Factor" would split one dev tier
    # across two spellings.
    dev_column = reverse_names.get("Dev", "Dev")
    reverse_dev = {}
    if dev_column in raw.columns:
        existing = set(raw[dev_column].dropna().astype(str))
        reverse_dev = {
            canonical: alias
            for alias, canonical in DEV_ALIASES.items()
            if alias in existing
        }

    rows = []
    for player in players:
        row = {}
        for column in raw.columns:
            canonical = {v: k for k, v in reverse_names.items()}.get(column, column)
            value = player.get(canonical, player.get(column, ""))
            if column == dev_column:
                value = reverse_dev.get(value, value)
            row[column] = value
        rows.append(row)

    return pd.DataFrame(rows, columns=list(raw.columns))
