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

# Madden's side-specific labels -> the positions the app grades and
# weights. Lives here rather than in roster.py so trade_engine can share
# it without a circular import: trade_engine used to map only REDG/LEDG,
# so GB's SAM/WILL linebackers matched no CPU "OLB" and every partner
# reported "No SAM on roster — fills critical need".
POSITION_ALIASES = {
    "REDG": "EDGE", "LEDG": "EDGE",
    "LOLB": "OLB", "ROLB": "OLB", "SAM": "OLB", "WILL": "OLB",
    "MIKE": "MLB",
}


def normalize_position(pos) -> str:
    """Upper-cased position with Madden's side labels folded in.

    Takes str() defensively: a blank CSV cell arrives as float nan.
    """
    pos_upper = str(pos).upper().strip()
    return POSITION_ALIASES.get(pos_upper, pos_upper)


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


def drop_unrated(df: pd.DataFrame) -> "tuple[pd.DataFrame, list[str]]":
    """(rows with a numeric OVR and Age, names of the rows that lacked one).

    Every view does arithmetic on these two (int(OVR), age curves, room
    ratings), so one blank cell raised "cannot convert float NaN to
    integer" in the Home tab, which stops the script and blanks every tab
    after it, including the Roster tab that would explain why. Those rows
    are set aside and reported instead. OVR and Age come back numeric.
    """
    df = df.copy()
    for col in ("OVR", "Age"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    present = [c for c in ("OVR", "Age") if c in df.columns]
    if not present:
        return df, []
    bad = df[present].isna().any(axis=1)
    names = [str(n) for n in df.loc[bad, "Name"]] if "Name" in df.columns \
        else [f"row {i + 2}" for i in df.index[bad]]
    df = df[~bad].reset_index(drop=True)
    # A blank cell makes the whole column float; the survivors are whole
    # numbers, so hand back ints ("OVR 88", not "88.0").
    for col in present:
        if (df[col] % 1 == 0).all():
            df[col] = df[col].astype(int)
    return df, names


def load_roster_csv(path: str) -> pd.DataFrame:
    """Read and normalise the roster CSV at `path`."""
    return normalize_roster_df(pd.read_csv(path))


def missing_required_columns(df: pd.DataFrame) -> "list[str]":
    """Required columns absent after normalisation (empty when loadable)."""
    return [c for c in REQUIRED_COLUMNS if c not in df.columns]


def source_column_for(canonical: str, raw: pd.DataFrame) -> str:
    """The heading `raw` actually uses for a canonical column name.

    "Name" is "Player Name" in the exported schema and "Name" in the
    canonical one; callers that need to look a value up in the file
    itself have to ask which.
    """
    for source, target in COLUMN_ALIASES.items():
        if target == canonical and source in raw.columns \
                and canonical not in raw.columns:
            return source
    return canonical


def existing_player_keys(raw: pd.DataFrame) -> "set[tuple[str, str]]":
    """(name, position) pairs already in the file.

    Name alone was the old key, which skipped a new "J. Smith" WR because
    a J. Smith CB was on file, then reported the save as done. Position
    is normalised, so a stored REDG and an added EDGE are the same slot.
    """
    name_col = source_column_for("Name", raw)
    pos_col = source_column_for("Pos", raw)
    if name_col not in raw.columns:
        return set()
    positions = raw[pos_col] if pos_col in raw.columns else [""] * len(raw)
    return {(str(n).strip(), normalize_position(p) if p == p else "")
            for n, p in zip(raw[name_col], positions) if n == n}


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

    to_canonical = {v: k for k, v in reverse_names.items()}
    rows = []
    for player in players:
        row = {}
        for column in raw.columns:
            canonical = to_canonical.get(column, column)
            value = player.get(canonical, player.get(column, ""))
            if column == dev_column:
                value = reverse_dev.get(value, value)
            row[column] = value
        rows.append(row)

    return pd.DataFrame(rows, columns=list(raw.columns))
