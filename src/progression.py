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
    # Append to existing log
    if os.path.exists(_PROG_CSV):
        existing = pd.read_csv(_PROG_CSV)
        # Remove duplicate entries for same season/week/team
        existing = existing[
            ~((existing["Season"] == season) &
              (existing["Week"] == week) &
              (existing["Team"] == team))
        ]
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    try:
        combined.to_csv(_PROG_CSV, index=False)
    except OSError:
        return 0  # read-only filesystem
    return len(new_rows)


def get_progression(team: str) -> pd.DataFrame:
    """Return the progression log for a team with computed deltas."""
    _ensure_log()
    if not os.path.exists(_PROG_CSV):
        return pd.DataFrame()
    log = pd.read_csv(_PROG_CSV)
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

    deltas = []
    for name in common:
        d = int(last[name]) - int(first[name])
        if d != 0:
            pos = log[log["Name"] == name].iloc[0]["Pos"]
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
