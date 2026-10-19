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
import tempfile

import pandas as pd

from src.season import (DEFAULT_SEASON, SEASON_MAX, SEASON_MIN, WEEK_MAX,
                        WEEK_MIN)

# What the entry form asks for. Everything else in the file is either
# derived (see `derive_fields`) or bookkeeping (`GAME_ID`, `Team`).
ENTRY_FIELDS = [
    "Season", "Week", "Opponent",
    "Points_For", "Points_Against",
    "Pass_Yards", "Rush_Yards", "First_Downs", "Turnovers",
    "TOP", "RZ_TD_Made",
    "Pass_Yards_Allowed", "Rush_Yards_Allowed", "Sacks_For", "Takeaways",
    "Playbook", "Off_Playbook", "Def_Scheme", "Def_Playbook",
    "Third_Down_Att", "Third_Down_Conv", "RZ_Att",
]

# Added after the first 28 games were logged, so older logs lack them.
# Without attempts, third-down rate and red zone TD% — the two stats this
# franchise's results track best — could not be computed at all:
# RZ_TD_Made alone says how many, not out of how many.
EFFICIENCY_FIELDS = ["Third_Down_Att", "Third_Down_Conv", "RZ_Att"]

# What a game was run with. `Playbook` is the odd name out: it predates
# the other three and holds the *offensive scheme* ("WestCoast Zone
# Run"), which is what the 42 shipped games put in it. Renaming it would
# mean rewriting every row of the user's CSV — the operation this module
# exists to avoid — so the name stays and `src/schemes.py` owns the
# vocabulary, the canonical spellings and the comparison.
#
# Listed as plain strings rather than imported from `schemes` on
# purpose: `schemes` imports this module, and the dependency only makes
# sense in that direction. This module owns the CSV schema.
SCHEME_FIELDS = ["Playbook", "Off_Playbook", "Def_Scheme", "Def_Playbook"]

# Columns that arrived after games had already been logged, so an
# existing file may not have them. `append_game` adds any of these the
# user actually supplies; everything else must already be in the header,
# because inventing a column from a stray key is how a typo becomes
# schema.
LATE_FIELDS = EFFICIENCY_FIELDS + SCHEME_FIELDS


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
            new_cols = [c for c in LATE_FIELDS
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


def _field_spans(line: str) -> "list[tuple[int, int]]":
    """Character span of each CSV field in one raw line.

    Returned as offsets rather than values so a caller can splice one
    field and leave every other byte of the line exactly as it was —
    including quoting it would not have chosen itself. Splitting on ","
    would shred a quoted Playbook like `"Shanahan, Wide Zone"`.
    """
    spans = []
    i, n = 0, len(line)
    while True:
        start = i
        if i < n and line[i] == '"':
            i += 1
            while i < n:
                if line[i] != '"':
                    i += 1
                elif i + 1 < n and line[i + 1] == '"':
                    i += 2  # an escaped quote inside the field
                else:
                    i += 1
                    break
        while i < n and line[i] != ",":
            i += 1
        spans.append((start, i))
        if i < n and line[i] == ",":
            i += 1
            continue
        return spans


def _splice(line: str, index: int, value: str) -> str:
    """`line` with field `index` replaced by `value`, padding if short.

    `_extend_header` adds columns without touching existing rows, so a
    legacy row genuinely has fewer fields than there are columns. Those
    rows are padded with empty fields rather than skipped.
    """
    cell = _csv_cell(value)
    spans = _field_spans(line)
    if index < len(spans):
        start, end = spans[index]
        return line[:start] + cell + line[end:]
    return line + "," * (index - len(spans) + 1) + cell


# What a backfill may write. Deliberately not every column: the point is
# to supply stats a game was logged without, not to re-open scores and
# yardage that `derive_fields` computes from each other. A wider set
# would need the derived columns recomputed too, and this writer exists
# precisely because recomputing a row is how rows get corrupted.
#
# The scheme columns are safe to re-open for the opposite reason: no
# derived column reads them, so correcting one cannot make a row
# contradict itself. They also have to be re-openable. They are the one
# thing on a row the user can only discover is wrong *later* — 14 of the
# shipped games carry no scheme at all, and a game logged under the
# wrong one silently skews the very comparison it was recorded for.
BACKFILL_FIELDS = EFFICIENCY_FIELDS + ["RZ_TD_Made"] + SCHEME_FIELDS


def _untracked(df: pd.DataFrame, column: str) -> pd.Series:
    """Rows where `column` holds no usable count, as an aligned Series.

    Blank and 0 both mean "not tracked": the entry form writes blank
    for a 0 and `_rate` filters on `a > 0`. An absent column means no
    row has it — returned as an all-True Series rather than the scalar
    NaN `pd.to_numeric(df.get(missing))` would give, whose `.isna()`
    raises AttributeError.
    """
    if column not in df.columns:
        return pd.Series(True, index=df.index, dtype=bool)
    value = pd.to_numeric(df[column], errors="coerce")
    return value.isna() | (value == 0)


def games_missing_efficiency(df: pd.DataFrame) -> pd.DataFrame:
    """The games a backfill could still improve — missing either stat."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    return df[_untracked(df, "Third_Down_Att") | _untracked(df, "RZ_Att")]


def backfill_changes(current: dict, td_att, td_conv, rz_att) -> dict:
    """The columns a backfill should actually write.

    Takes what the row already holds so a submitted value that matches
    it is dropped rather than rewritten — re-saving a prefilled form
    touches nothing. Conversions ride along with attempts, because
    `Third_Down_Conv` on its own cannot produce a rate; 0 attempts
    still means "not tracked" and writes neither.
    """
    proposed = {}
    if td_att:
        proposed["Third_Down_Att"] = int(td_att)
        proposed["Third_Down_Conv"] = int(td_conv)
    if rz_att:
        proposed["RZ_Att"] = int(rz_att)

    changes = {}
    for column, value in proposed.items():
        now = pd.to_numeric(current.get(column), errors="coerce")
        if pd.isna(now) or now != value:
            changes[column] = value
    return changes


def scheme_changes(current: dict, values: dict) -> dict:
    """The scheme/playbook columns a relabel should actually write.

    The text counterpart of `backfill_changes`: drops anything already
    matching the row so re-saving a prefilled form writes nothing, and
    compares on the stripped value so re-saving a legacy row carrying a
    stray trailing space doesn't count as an edit.

    A blank submission clears the column. That is deliberate — a game
    labelled with the wrong scheme must be settable back to "not
    recorded", which is honest, rather than being stuck on a wrong
    answer because the form only accepts non-empty ones.
    """
    changes = {}
    for column, value in values.items():
        if column not in SCHEME_FIELDS:
            continue
        new = "" if value is None else " ".join(str(value).split())
        now = current.get(column)
        now = "" if now is None or (
            isinstance(now, float) and pd.isna(now)) else " ".join(
                str(now).split())
        if new != now:
            changes[column] = new
    return changes


def _write_atomically(path: str, text: str) -> None:
    """Replace `path` with `text`, or leave it exactly as it was.

    Opening the live file with "w" truncates it before `write` runs, so
    a full disk used to return a failure *and* an empty log — an error
    message on screen and the franchise gone. The new content is staged
    beside the original (same directory, so `os.replace` is a rename
    within one filesystem) and swapped in only once it is safely down.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    handle = tempfile.NamedTemporaryFile(
        "w", newline="", dir=directory, prefix=".game_log-", suffix=".tmp",
        delete=False)
    try:
        with handle:
            handle.write(text)
        os.replace(handle.name, path)
    except BaseException:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise


def update_game(path: str, game_id, fields: dict) -> "tuple[bool, str]":
    """Write `fields` into the logged game `game_id`. Returns (ok, message).

    Splices the new values into that game's own line and leaves every
    other byte of the file alone. The obvious implementation — read with
    pandas, set a cell, write back — is exactly what `append_game`'s
    docstring warns about: the shipped log has a game missing four
    stats, so those columns read as float and `to_csv` renders every
    other row's `25` as `25.0`.
    """
    existing = read_log(path)
    refusal = _why_not(existing, game_id, fields)
    if refusal:
        return False, refusal + " Nothing was written."

    try:
        with open(path, "r", newline="") as handle:
            lines = handle.read().splitlines(keepends=True)
        # A quoted field may hold a newline, in which case raw line N is
        # not row N and splicing by line index writes into the wrong
        # game. The entry form cannot produce one; an uploaded CSV can.
        if len(lines) - 1 != len(existing):
            return False, ("A field in this log spans more than one line, "
                           "so the row to edit cannot be located safely. "
                           "Nothing was written.")

        columns = list(existing.columns)
        new_columns = [c for c in fields if c not in columns]
        if new_columns:
            _extend_header(path, new_columns)
            with open(path, "r", newline="") as handle:
                lines = handle.read().splitlines(keepends=True)
            columns += new_columns

        index = _row_numbers(existing, game_id)[0] + 1  # header is line 0
        raw = lines[index]
        body = raw.rstrip("\r\n")
        for column, value in fields.items():
            body = _splice(body, columns.index(column), _format(value))
        lines[index] = body + raw[len(raw.rstrip("\r\n")):]

        _write_atomically(path, "".join(lines))
    except OSError:
        return False, ("Could not write the game log — the filesystem is "
                       "read-only. Download the CSV and edit locally.")
    except Exception as exc:
        return False, f"Could not update the game log: {exc}"
    return True, (f"Updated game #{game_id}: "
                  + ", ".join(f"{k} {_format(v)}" for k, v in fields.items())
                  + ".")


def _row_numbers(existing: pd.DataFrame, game_id) -> "list[int]":
    """Positions of the rows carrying this GAME_ID (usually exactly one)."""
    if "GAME_ID" not in existing.columns:
        return []
    wanted = pd.to_numeric(game_id, errors="coerce")
    ids = pd.to_numeric(existing["GAME_ID"], errors="coerce")
    return [i for i, v in enumerate(ids) if v == wanted]


def _why_not(existing: pd.DataFrame, game_id, fields: dict) -> "str | None":
    """Why this backfill must not be written, or None to go ahead.

    Every check runs before the file is opened for writing, so a refusal
    leaves the log untouched rather than half-edited.
    """
    bad = [key for key in fields if key not in BACKFILL_FIELDS]
    if bad:
        return (f"{', '.join(sorted(bad))} cannot be backfilled — only "
                f"{', '.join(BACKFILL_FIELDS)}.")
    if not looks_like_a_log(existing):
        return ("The game log could not be read, so overwriting it would "
                "lose whatever is in it.")
    if "GAME_ID" not in existing.columns:
        return ("This log has no GAME_ID column, so there is no way to say "
                "which game to update.")
    rows = _row_numbers(existing, game_id)
    if not rows:
        return f"No game #{game_id} in the log."
    if len(rows) > 1:
        return (f"Game #{game_id} appears {len(rows)} times, so the one to "
                "edit is ambiguous.")
    return _impossible_pair({**row_for_game(existing, game_id), **fields})


def unreadable_placements(df: pd.DataFrame) -> "list[str]":
    """Season/Week cells holding text that loading is about to discard.

    The loader coerces both columns with `errors="coerce"`, so "Wk 3"
    and an empty cell arrive as the same `<NA>`. A game whose placement
    was typed rather than numbered then reads as *not placed yet*:
    `data_checks._check_placement` has nothing left to object to — by
    design, since an unplaced game is not an error — and
    `games_missing_season_week` offers it for backfill as though the
    cell had always been empty.

    Nothing downstream can tell the two apart, because by then the
    original text is gone. So it has to be said here, while it is still
    readable, or a Sheet column of "Wk 1".."Wk 18" vanishes in silence.
    """
    if df is None or df.empty:
        return []
    notes = []
    for column in ("Season", "Week"):
        if column not in df.columns:
            continue
        text = df[column].astype("string").str.strip()
        lost = text.notna() & (text != "") \
            & pd.to_numeric(df[column], errors="coerce").isna()
        if not lost.any():
            continue
        shown = sorted(set(text[lost]))[:3]
        notes.append(
            f"{int(lost.sum())} row(s) have a {column} that is not a number "
            f"({', '.join(repr(v) for v in shown)}). Those games will read "
            f"as unplaced until the cell holds a plain number.")
    return notes


def games_missing_season_week(df: pd.DataFrame) -> pd.DataFrame:
    """Games with no place in the franchise timeline.

    Season and Week are blank on every shipped row, which makes two
    features inert rather than wrong: `duplicate_week` has no week to
    collide with, so it protects nothing, and `next_season_week` keeps
    suggesting the first week of the default season however many games
    are on file.
    """
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    return df[_untracked_label(df, "Season") | _untracked_label(df, "Week")]


def _untracked_label(df: pd.DataFrame, column: str) -> pd.Series:
    """Rows with no value in `column`, as an aligned boolean Series.

    Unlike `_untracked`, 0 is not a sentinel here — it is simply out of
    range for both a season and a week, and `_valid_placement` refuses
    it with a message rather than treating it as "not recorded".
    """
    if column not in df.columns:
        return pd.Series(True, index=df.index, dtype=bool)
    return pd.to_numeric(df[column], errors="coerce").isna()


def plan_season_weeks(existing: pd.DataFrame, first_game_id, season,
                      start_week) -> dict:
    """Suggest consecutive weeks for the games from `first_game_id` on.

    A suggestion, never a derivation, and nothing is written. The log
    has gaps in GAME_ID (7, 8, 9, 28 and 34 are absent from the shipped
    file) and a real season carries a bye, so consecutive numbering is
    a starting point for the user to correct — which is why the form
    shows the whole plan in an editable table before saving any of it.

    Weeks follow the games that exist, not the numbering of the ones
    that do not: a missing GAME_ID does not consume a week.
    """
    if existing is None or existing.empty or "GAME_ID" not in existing.columns:
        return {}
    ids = pd.to_numeric(existing["GAME_ID"], errors="coerce").dropna()
    ordered = [int(v) for v in ids]
    wanted = pd.to_numeric(first_game_id, errors="coerce")
    if pd.isna(wanted) or int(wanted) not in ordered:
        return {}

    season = int(pd.to_numeric(season, errors="coerce"))
    week = int(pd.to_numeric(start_week, errors="coerce"))
    plan = {}
    for game_id in ordered[ordered.index(int(wanted)):]:
        if week > WEEK_MAX:
            break
        plan[game_id] = (season, week)
        week += 1
    return plan


def _in_range(mapping: dict, known: set) -> "str | None":
    """Every game real and every slot inside the season's bounds."""
    for game_id, (season, week) in mapping.items():
        if int(game_id) not in known:
            return f"No game #{game_id} in the log."
        if not SEASON_MIN <= int(season) <= SEASON_MAX:
            return f"Season {season} is outside {SEASON_MIN}-{SEASON_MAX}."
        if not WEEK_MIN <= int(week) <= WEEK_MAX:
            return f"Week {week} is outside {WEEK_MIN}-{WEEK_MAX}."
    return None


def _week_already_taken(mapping: dict, existing: pd.DataFrame) -> "str | None":
    """Two games in one week, whether both are new or one is on file.

    This is the protection `duplicate_week` was written to give and
    never has, because no game has ever carried a week to collide with.
    """
    seen = {}
    for game_id, slot in mapping.items():
        if slot in seen:
            return (f"Games #{seen[slot]} and #{game_id} would both be "
                    f"season {slot[0]} week {slot[1]}.")
        seen[slot] = game_id
    if not {"Season", "Week"} <= set(existing.columns):
        return None
    on_file = zip(pd.to_numeric(existing["GAME_ID"], errors="coerce"),
                  pd.to_numeric(existing["Season"], errors="coerce"),
                  pd.to_numeric(existing["Week"], errors="coerce"))
    moving = {int(g) for g in mapping}
    for game_id, season, week in on_file:
        if pd.isna(season) or pd.isna(week):
            continue
        # A game in this mapping is leaving its old slot, so that slot is
        # free. Counting it blocked every re-plan that shifts placed games
        # (a bye moves 40-47 up a week: 40 takes 41's week 7 while 41
        # moves to 8, and the write was refused as a clash with 41).
        if pd.notna(game_id) and int(game_id) in moving:
            continue
        slot = (int(season), int(week))
        if slot in seen:
            # A row with no readable GAME_ID still holds its week, so it
            # still blocks the slot — it just cannot be named. Naming it
            # anyway raised `ValueError: cannot convert float NaN to
            # integer` from inside the refusal, turning a message the
            # user could act on into a crash that took the tab down.
            who = (f"Game #{int(game_id)}" if pd.notna(game_id)
                   else "Another game")
            return f"{who} is already season {slot[0]} week {slot[1]}."
    return None


def _valid_placement(mapping: dict, existing: pd.DataFrame) -> "str | None":
    """Why this season/week assignment cannot be written, or None."""
    if not mapping:
        return "No games to place."
    return (_in_range(mapping, set(_row_numbers_by_id(existing)))
            or _week_already_taken(mapping, existing))


def _row_numbers_by_id(existing: pd.DataFrame) -> dict:
    """{GAME_ID: row position}, for locating lines to splice."""
    if existing is None or existing.empty or "GAME_ID" not in existing.columns:
        return {}
    ids = pd.to_numeric(existing["GAME_ID"], errors="coerce")
    return {int(v): i for i, v in enumerate(ids) if pd.notna(v)}


def assign_season_week(path: str, mapping: dict) -> "tuple[bool, str]":
    """Place games in the franchise timeline. `{game_id: (season, week)}`.

    One atomic write for the whole mapping rather than a call to
    `update_game` per game: 42 rewrites would be 42 chances to fail
    partway, and a half-numbered season is worse than an unnumbered one.
    """
    existing = read_log(path)
    if not looks_like_a_log(existing):
        return False, ("The game log could not be read, so nothing was "
                       "written — overwriting it would lose whatever is "
                       "in it. Check the CSV.")
    if "GAME_ID" not in existing.columns:
        return False, ("This log has no GAME_ID column, so there is no way "
                       "to say which game to place. Nothing was written.")
    refusal = _valid_placement(mapping, existing)
    if refusal:
        return False, refusal + " Nothing was written."

    try:
        with open(path, "r", newline="") as handle:
            lines = handle.read().splitlines(keepends=True)
        if len(lines) - 1 != len(existing):
            return False, ("A field in this log spans more than one line, "
                           "so the rows to edit cannot be located safely. "
                           "Nothing was written.")

        columns = list(existing.columns)
        new_columns = [c for c in ("Season", "Week") if c not in columns]
        if new_columns:
            _extend_header(path, new_columns)
            with open(path, "r", newline="") as handle:
                lines = handle.read().splitlines(keepends=True)
            columns += new_columns

        positions = _row_numbers_by_id(existing)
        for game_id, (season, week) in mapping.items():
            index = positions[int(game_id)] + 1  # the header is line 0
            raw = lines[index]
            body = raw.rstrip("\r\n")
            ending = raw[len(body):]
            body = _splice(body, columns.index("Season"), _format(int(season)))
            body = _splice(body, columns.index("Week"), _format(int(week)))
            lines[index] = body + ending

        _write_atomically(path, "".join(lines))
    except OSError:
        return False, ("Could not write the game log — the filesystem is "
                       "read-only. Download the CSV and edit locally.")
    except Exception as exc:
        return False, f"Could not update the game log: {exc}"

    seasons = sorted({int(s) for s, _ in mapping.values()})
    return True, (f"Placed {len(mapping)} game(s) in "
                  f"season {', '.join(str(s) for s in seasons)}.")


def row_for_game(existing: pd.DataFrame, game_id) -> dict:
    """The named game's current values, or {} if it isn't there.

    Used for two things that both need to know what is already on the
    row: validating a partial edit ("conversions cannot exceed
    attempts" has to hold against the merge of old and new), and
    prefilling the backfill form so supplying one stat cannot write
    another away.
    """
    if existing is None or existing.empty or "GAME_ID" not in existing.columns:
        return {}
    ids = pd.to_numeric(existing["GAME_ID"], errors="coerce")
    hit = existing[ids == pd.to_numeric(game_id, errors="coerce")]
    return {} if hit.empty else hit.iloc[0].to_dict()


def _impossible_pair(row: dict) -> "str | None":
    """Why this row cannot be real, or None.

    Same rule as the entry form and `data_checks`: made cannot exceed
    attempted, and zero attempts means "not tracked" rather than a
    contradiction, so it is exempt.
    """
    for made, att, label, denom in (
            ("Third_Down_Conv", "Third_Down_Att", "3rd down conversions",
             "attempts"),
            ("RZ_TD_Made", "RZ_Att", "Red zone TDs", "field goal range "
             "trips")):
        m = pd.to_numeric(row.get(made), errors="coerce")
        a = pd.to_numeric(row.get(att), errors="coerce")
        if pd.notna(m) and pd.notna(a) and a > 0 and m > a:
            return (f"{label} ({_format(m)}) cannot exceed {denom} "
                    f"({_format(a)}).")
    return None


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
    _write_atomically(path, header + rest)


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
