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

from src.season import DEFAULT_SEASON, WEEK_MIN

# What the entry form asks for. Everything else in the file is either
# derived (see `derive_fields`) or bookkeeping (`GAME_ID`, `Team`).
ENTRY_FIELDS = [
    "Season", "Week", "Opponent",
    "Points_For", "Points_Against",
    "Pass_Yards", "Rush_Yards", "First_Downs", "Turnovers",
    "TOP", "RZ_TD_Made",
    "Pass_Yards_Allowed", "Rush_Yards_Allowed", "Sacks_For", "Takeaways",
    "Playbook",
    "Third_Down_Att", "Third_Down_Conv", "RZ_Att",
]

# Added after the first 28 games were logged, so older logs lack them.
# Without attempts, third-down rate and red zone TD% — the two stats this
# franchise's results track best — could not be computed at all:
# RZ_TD_Made alone says how many, not out of how many.
EFFICIENCY_FIELDS = ["Third_Down_Att", "Third_Down_Conv", "RZ_Att"]


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

    A number is taken as minutes already; NaN (a blank cell) is None.

    Mirrors the reader in `app.py`, which silently yields None on a bad
    value — the form validates up front so a typo does not become a row
    that quietly drops out of every TOP chart.
    """
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return None if pd.isna(text) else float(text)
    if not isinstance(text, str) or ":" not in text:
        return None
    parts = text.strip().split(":")
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return None
    # Google Sheets reads a typed or imported "19:39" as a time and
    # exports it as "19:39:00"; a duration-formatted cell exports
    # "0:19:39". Both are MM:SS underneath. Any other H:MM:SS is not a
    # time of possession.
    if len(parts) == 3:
        if parts[0] == 0:
            parts = parts[1:]
        elif parts[2] == 0:
            parts = parts[:2]
    if len(parts) != 2:
        return None
    minutes, seconds = parts
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
    """Suggest the season/week to log next, from what is already recorded.

    Falls back to `season.DEFAULT_SEASON` rather than 1: seasons are
    calendar years, and every shipped row has a blank Season, so a fresh
    franchise gets that fallback rather than a derived value.
    """
    if existing.empty or not {"Season", "Week", "Team"} <= set(existing.columns):
        return DEFAULT_SEASON, WEEK_MIN
    mine = existing[existing["Team"].astype(str) == str(team)]
    seasons = pd.to_numeric(mine.get("Season"), errors="coerce").dropna()
    if not len(seasons):
        return DEFAULT_SEASON, WEEK_MIN
    season = int(seasons.max())
    weeks = pd.to_numeric(
        mine[pd.to_numeric(mine["Season"], errors="coerce") == season]["Week"],
        errors="coerce").dropna()
    if not len(weeks):
        return season, WEEK_MIN
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

    columns = (list(existing.columns) if looks_like_a_log(existing)
               else ["GAME_ID", "Season", "Week", "Team"] + [
                   c for c in ENTRY_FIELDS if c not in ("Season", "Week")] + [
                   "Result", "Total_Yards", "Total_Yards_Allowed",
                   "Point_Differential"])
    ordered = {}
    for column in columns:
        value = row.get(column, "")
        ordered[column] = "" if value is None or value == "" else value
    return pd.DataFrame([ordered], columns=columns)


def looks_like_a_log(df: pd.DataFrame) -> bool:
    """True if the parsed frame plausibly is a game log.

    pandas parses almost anything: a file of binary noise comes back as a
    single column named after the noise, which passes a bare "does it
    have a header" check and then gets a row appended into a schema that
    shares nothing with a game.
    """
    if not len(df.columns):
        return False
    known = set(ENTRY_FIELDS) | {"GAME_ID", "Team", "Result"}
    return bool(known & set(df.columns))


def _has_content(path: str) -> bool:
    """True if the file exists and holds more than whitespace.

    Distinguishes a truncated log (safe to start fresh) from one that is
    unreadable for some other reason (must not be overwritten).
    """
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", newline="", errors="replace") as handle:
            return bool(handle.read().strip())
    except OSError:
        return True  # unreadable: assume it holds something


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
    # Whether to write a header depends on whether the file already has
    # one, not on whether it exists. Keying this off os.path.exists meant
    # a truncated log got a headerless row appended: pandas then read the
    # game itself as the header and the file came back with zero rows,
    # while the form reported success.
    has_header = looks_like_a_log(existing)
    if not has_header and _has_content(path):
        return False, ("The game log exists but could not be read, so "
                       "nothing was written — overwriting it would lose "
                       "whatever is in it. Check data/game_logs.csv.")
    try:
        if has_header:
            new_cols = [c for c in EFFICIENCY_FIELDS
                        if c not in existing.columns
                        and entry.get(c) not in (None, "")]
            if new_cols:
                _extend_header(path, new_cols)
                existing = read_log(path)
        added = row_to_log_schema(entry, existing, team)
        line = ",".join(
            _csv_cell(_format(added[column].iloc[0]))
            for column in added.columns)

        if not has_header:
            header = ",".join(_csv_cell(c) for c in added.columns)
            with open(path, "w", newline="") as handle:
                handle.write(f"{header}\n{line}\n")
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
    # Read from the entry, not from `added`: a log of the user's own
    # making need not carry a GAME_ID column at all.
    return True, f"Logged game #{next_game_id(existing)}."


def _extend_header(path: str, columns: "list[str]") -> None:
    """Add columns to the end of the header line, leaving every row as is.

    Older rows then have fewer cells than the header, which pandas (and
    Sheets/Excel) read as blanks — "not recorded", which is the truth for
    games logged before these stats existed. Only the header line is
    rewritten; no existing game row is re-serialised.
    """
    with open(path, "r", newline="") as handle:
        text = handle.read()
    first_break = len(text)
    for sep in ("\r\n", "\n"):
        idx = text.find(sep)
        if idx != -1:
            first_break = min(first_break, idx)
    header, rest = text[:first_break], text[first_break:]
    header += "".join("," + _csv_cell(c) for c in columns)
    with open(path, "w", newline="") as handle:
        handle.write(header + rest)


def _rate(df: pd.DataFrame, made: str, att: str) -> "tuple[float | None, int]":
    """(made / att across games that recorded attempts, games counted)."""
    if made not in df.columns or att not in df.columns:
        return None, 0
    m = pd.to_numeric(df[made], errors="coerce")
    a = pd.to_numeric(df[att], errors="coerce")
    ok = a.notna() & m.notna() & (a > 0)
    if not ok.any():
        return None, 0
    return float(m[ok].sum() / a[ok].sum() * 100), int(ok.sum())


def efficiency_rates(df: pd.DataFrame) -> dict:
    """Third-down conversion % and red zone TD %, over games that have them.

    Rates are totals over totals (conversions / attempts across games),
    not an average of per-game percentages, which would weight a 1-for-1
    game the same as a 9-for-16 one. Games without attempts recorded are
    left out rather than counted as 0-for-0.

    Older games were logged with conversions but no attempts, so
    conversions are also averaged per game over every game that recorded
    them ("third_down_conv_per_game"): a weaker number than the rate, but
    a real one, for logs that can't supply attempts. (Attempts are on
    Madden's post-game Team Stats tab: "3rd Down Conv. 7/11 (63%)".)
    """
    empty = {"third_down_pct": None, "third_down_games": 0,
             "third_down_conv_per_game": None, "third_down_conv_games": 0,
             "rz_td_pct": None, "rz_games": 0}
    if df is None or df.empty:
        return empty
    td, td_n = _rate(df, "Third_Down_Conv", "Third_Down_Att")
    rz, rz_n = _rate(df, "RZ_TD_Made", "RZ_Att")
    out = {**empty, "third_down_pct": td, "third_down_games": td_n,
           "rz_td_pct": rz, "rz_games": rz_n}
    if "Third_Down_Conv" in df.columns:
        conv = pd.to_numeric(df["Third_Down_Conv"], errors="coerce")
        att = pd.to_numeric(df.get("Third_Down_Att"), errors="coerce")
        sentinel = (conv == 0) & (att == 0)  # "0/0" means not tracked, not a 0-conv game
        conv = conv[conv.notna() & ~sentinel]
        if len(conv):
            out["third_down_conv_per_game"] = float(conv.mean())
            out["third_down_conv_games"] = int(len(conv))
    return out


def filter_by_playbook(df: pd.DataFrame, selected: "list[str]",
                       options: "list[str]") -> pd.DataFrame:
    """Rows whose Playbook is in `selected`.

    A game with no playbook recorded is kept while every playbook is
    selected (the default), and dropped once the user narrows the
    selection. A plain isin() dropped those games from every tab even
    with nothing filtered, because a blank is never in the list.
    """
    if "Playbook" not in df.columns or not options:
        return df
    if not selected:
        return df.iloc[0:0]
    keep = df["Playbook"].isin(selected)
    if set(selected) >= set(options):
        blank = df["Playbook"].isna() | (df["Playbook"].astype(str).str.strip() == "")
        keep |= blank
    return df[keep]


def _csv_cell(text: str) -> str:
    """Quote a cell if it carries a comma, quote or newline."""
    text = str(text)
    if any(ch in text for ch in (",", '"', "\n", "\r")):
        return '"' + text.replace('"', '""') + '"'
    return text
