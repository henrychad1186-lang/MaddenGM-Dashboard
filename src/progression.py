"""
Player Progression Tracker — snapshot and track OVR changes over time.
"""

import os
import pandas as pd

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_PROG_CSV = os.path.join(_DATA_DIR, "progression_log.csv")


def _ensure_log():
    """Create progression log CSV if it doesn't exist."""
    if not os.path.exists(_PROG_CSV):
        try:
            pd.DataFrame(columns=["Name", "Pos", "Team", "Season", "Week", "OVR"]).to_csv(
                _PROG_CSV, index=False
            )
        except OSError:
            pass  # read-only filesystem (Streamlit Cloud)


def snapshot_roster(team: str, season: int, week: int):
    """Save current roster OVRs as a progression snapshot."""
    from src.roster import get_roster

    _ensure_log()
    roster = get_roster(team, "All")
    if roster.empty:
        return 0

    new_rows = []
    for _, row in roster.iterrows():
        new_rows.append({
            "Name": row["Name"],
            "Pos": row["Pos"],
            "Team": team,
            "Season": season,
            "Week": week,
            "OVR": int(row["OVR"]),
        })

    new_df = pd.DataFrame(new_rows)
    existing = _read_log_strict()
    if existing is None:
        return 0  # unreadable: overwriting it would lose every snapshot
    # Append to existing log
    if not existing.empty:
        # Remove duplicate entries for same season/week/team
        existing = existing[
            ~((existing["Season"] == season) &
              (existing["Week"] == week) &
              (existing["Team"] == team))
        ]
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    # Through a temp file, so a failed write can't truncate the log.
    tmp = _PROG_CSV + ".tmp"
    try:
        combined.to_csv(tmp, index=False)
        os.replace(tmp, _PROG_CSV)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return 0  # read-only filesystem
    return len(new_rows)


_LOG_COLUMNS = ["Name", "Pos", "Team", "Season", "Week", "OVR"]


def _read_log() -> pd.DataFrame:
    """The log, or an empty frame if it is missing, unreadable or not a log.

    An unguarded read_csv here raised on an empty or hand-mangled file,
    which took down the Progression tab and the game-log form's snapshot.
    """
    log = _read_log_strict()
    return pd.DataFrame(columns=_LOG_COLUMNS) if log is None else log


def _read_log_strict() -> "pd.DataFrame | None":
    """The log; an empty frame if there is none yet; None if unreadable.

    For writers. `_read_log` reads an unreadable file as empty, which is
    right for display but not for a write: the snapshot then replaced a
    hand-edited log (a renamed column, a stray quote) with one week's
    rows, and logging a game snapshots automatically. A file holding only
    whitespace has nothing to lose and counts as empty.
    """
    if not os.path.exists(_PROG_CSV):
        return pd.DataFrame(columns=_LOG_COLUMNS)
    try:
        with open(_PROG_CSV, "r", errors="replace") as handle:
            if not handle.read().strip():
                return pd.DataFrame(columns=_LOG_COLUMNS)
        log = pd.read_csv(_PROG_CSV)
    except Exception:
        return None
    if not set(_LOG_COLUMNS) <= set(log.columns):
        return None
    return log


def get_progression(team: str) -> pd.DataFrame:
    """Return the progression log for a team with computed deltas."""
    log = _read_log()
    log = log[log["Team"] == team]
    return log.sort_values(["Name", "Season", "Week"])


def get_movers(team: str) -> dict:
    """Return biggest gainers and losers between first and last snapshot."""
    log = get_progression(team)
    if log.empty:
        return {"gainers": [], "losers": []}

    # Get first and last OVR per player
    first = log.drop_duplicates("Name", keep="first").set_index("Name")["OVR"]
    last = log.drop_duplicates("Name", keep="last").set_index("Name")["OVR"]
    common = first.index.intersection(last.index)

    # One lookup table instead of a boolean scan of the log per player.
    first_pos = log.drop_duplicates("Name", keep="first").set_index("Name")["Pos"]

    deltas = []
    for name in common:
        d = int(last[name]) - int(first[name])
        if d != 0:
            pos = first_pos[name]
            deltas.append({
                "Name": name, "Pos": pos,
                "Start_OVR": int(first[name]),
                "Current_OVR": int(last[name]),
                "Delta": d,
            })

    deltas.sort(key=lambda x: x["Delta"], reverse=True)
    return {
        "gainers": [d for d in deltas if d["Delta"] > 0][:5],
        "losers": [d for d in deltas if d["Delta"] < 0][-5:],
    }
