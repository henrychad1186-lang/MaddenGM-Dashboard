"""
Append-only writer for the game log CSV.

Lives in `src/` rather than `app.py` so the write path can be tested
without a Streamlit runtime — `_prepare_game_log` is trapped at module
scope in `app.py` and cannot be imported outside one.

The append discipline here is the same one `roster_csv.rows_to_source_schema`
settled on: read the file's own header, emit exactly those columns, and
never rewrite a row the user already has. Rebuilding a frame from
normalised values is lossy, and it silently rewrote roster rows once
already.
"""

import os

import pandas as pd

# What the entry form asks for. Everything else in the file is either
# derived (see `derive_fields`) or bookkeeping (`GAME_ID`, `Team`).
ENTRY_FIELDS = [
    "Season", "Week", "Opponent",
    "Points_For", "Points_Against",
    "Pass_Yards", "Rush_Yards", "First_Downs", "Turnovers",
    "TOP", "RZ_TD_Made",
    "Pass_Yards_Allowed", "Rush_Yards_Allowed", "Sacks_For", "Takeaways",
    "Playbook",
]


def derive_fields(entry: dict) -> dict:
    """Fill in the columns that follow from what was typed.

    Totals and the differential are arithmetic on fields already in the
    form; asking for them again invites a row that contradicts itself.
    """
    out = dict(entry)

    def _num(key):
        value = pd.to_numeric(out.get(key), errors="coerce")
        return 0 if pd.isna(value) else value

    pf, pa = _num("Points_For"), _num("Points_Against")
    out["Total_Yards"] = _num("Pass_Yards") + _num("Rush_Yards")
    out["Total_Yards_Allowed"] = (
        _num("Pass_Yards_Allowed") + _num("Rush_Yards_Allowed"))
    out["Point_Differential"] = pf - pa
    # Ties are rare but real. Emitting "L" for a 20-20 game would record a
    # result that did not happen; `app.py` maps "T" through to "TIE".
    out["Result"] = "W" if pf > pa else ("L" if pf < pa else "T")
    return out


def next_game_id(existing: pd.DataFrame) -> int:
    """One past the highest GAME_ID on file (1 for an empty log)."""
    if existing.empty or "GAME_ID" not in existing.columns:
        return 1
    ids = pd.to_numeric(existing["GAME_ID"], errors="coerce").dropna()
    return int(ids.max()) + 1 if len(ids) else 1


NFL_TEAMS = [
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
    "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
]


def parse_top(text: str) -> "float | None":
    """Minutes from a "MM:SS" time of possession, or None if unparseable.

    Mirrors the reader in `app.py`, which silently yields None on a bad
    value — the form validates up front so a typo does not become a row
    that quietly drops out of every TOP chart.
    """
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    if not isinstance(text, str) or ":" not in text:
        return None
    minutes, _, seconds = text.partition(":")
    try:
        minutes, seconds = int(minutes), int(seconds)
    except ValueError:
        return None
    if minutes < 0 or not 0 <= seconds < 60:
        return None
    return minutes + seconds / 60


def duplicate_week(existing: pd.DataFrame, season, week, team: str) -> bool:
    """True if this team already has a game logged for that season/week.

    Blank legacy rows never count as a match — every one of the 28 games
    predating these columns would otherwise collide with each other.
    """
    if existing.empty:
        return False
    if not {"Season", "Week", "Team"} <= set(existing.columns):
        return False
    season = pd.to_numeric(season, errors="coerce")
    week = pd.to_numeric(week, errors="coerce")
    if pd.isna(season) or pd.isna(week):
        return False
    match = (
        (pd.to_numeric(existing["Season"], errors="coerce") == season)
        & (pd.to_numeric(existing["Week"], errors="coerce") == week)
        & (existing["Team"].astype(str) == str(team))
    )
    return bool(match.any())


def next_season_week(existing: pd.DataFrame, team: str) -> "tuple[int, int]":
    """Suggest the season/week to log next, from what is already recorded."""
    if existing.empty or not {"Season", "Week", "Team"} <= set(existing.columns):
        return 1, 1
    mine = existing[existing["Team"].astype(str) == str(team)]
    seasons = pd.to_numeric(mine.get("Season"), errors="coerce").dropna()
    if not len(seasons):
        return 1, 1
    season = int(seasons.max())
    weeks = pd.to_numeric(
        mine[pd.to_numeric(mine["Season"], errors="coerce") == season]["Week"],
        errors="coerce").dropna()
    if not len(weeks):
        return season, 1
    return season, int(weeks.max()) + 1


def read_log(path: str) -> pd.DataFrame:
    """Read the log, returning an empty frame rather than raising.

    A missing or unreadable file must not stop the user logging a game —
    that is the situation the form exists to get them out of.
    """
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def row_to_log_schema(entry: dict, existing: pd.DataFrame,
                      team: str) -> pd.DataFrame:
    """Shape one derived entry into a single row matching the file's columns.

    Columns the file has but the entry does not are written blank, not
    zero — a blank cell reads as "not recorded", a 0 reads as a real
    measurement of nothing.
    """
    row = derive_fields(entry)
    row["GAME_ID"] = next_game_id(existing)
    row["Team"] = team

    columns = (list(existing.columns) if len(existing.columns)
               else ["GAME_ID", "Season", "Week", "Team"] + [
                   c for c in ENTRY_FIELDS if c not in ("Season", "Week")] + [
                   "Result", "Total_Yards", "Total_Yards_Allowed",
                   "Point_Differential"])
    ordered = {}
    for column in columns:
        value = row.get(column, "")
        ordered[column] = "" if value is None or value == "" else value
    return pd.DataFrame([ordered], columns=columns)


def _format(value) -> str:
    """Render one cell without pandas' float coercion.

    `27` must stay `27`, not become `27.0`.
    """
    if value is None or value == "" or (
            isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def append_game(path: str, entry: dict, team: str) -> "tuple[bool, str]":
    """Append one game to the log as text. Returns (ok, message).

    The row is appended to the file, not written by re-serialising a
    frame. Round-tripping through pandas rewrites rows nobody touched:
    the shipped log already has a game missing four stats, which forces
    those columns to float, so `to_csv` renders every other row's `25`
    as `25.0`. Appending a line cannot corrupt what is above it.
    """
    existing = read_log(path)
    try:
        added = row_to_log_schema(entry, existing, team)
        line = ",".join(
            _csv_cell(_format(added[column].iloc[0]))
            for column in added.columns)

        if existing.empty and not os.path.exists(path):
            header = ",".join(_csv_cell(c) for c in added.columns)
            body = f"{header}\n{line}\n"
            with open(path, "w", newline="") as handle:
                handle.write(body)
        else:
            with open(path, "r", newline="") as handle:
                needs_newline = not handle.read().endswith("\n")
            with open(path, "a", newline="") as handle:
                handle.write(("\n" if needs_newline else "") + line + "\n")
    except OSError:
        # Streamlit Cloud serves from a read-only filesystem.
        return False, ("Could not write the game log — the filesystem is "
                       "read-only. Download the CSV and log locally.")
    except Exception as exc:
        return False, f"Could not write the game log: {exc}"
    return True, f"Logged game #{int(added['GAME_ID'].iloc[0])}."


def _csv_cell(text: str) -> str:
    """Quote a cell if it carries a comma, quote or newline."""
    text = str(text)
    if any(ch in text for ch in (",", '"', "\n", "\r")):
        return '"' + text.replace('"', '""') + '"'
    return text
